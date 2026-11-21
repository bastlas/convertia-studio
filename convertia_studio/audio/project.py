"""Lecture d'un projet Audacity (.aup3 / .aup4) et mixage en memoire.

Les deux formats sont des bases SQLite 3 de meme structure, qui contiennent :

  * ``project``    : colonnes ``dict`` + ``doc``, la version enregistree du
                     projet ;
  * ``autosave``   : memes colonnes, version "sauvegarde automatique" (c'est
                     elle qui porte le document quand ``project`` est vide,
                     par exemple dans un fichier ``.aup4unsaved``) ;
  * ``sampleblocks`` : les echantillons audio bruts, un blob par bloc (16 bits,
                     24 bits ou float 32 bits, non compresse) ;
  * ``project_history`` : les 10 dernieres sauvegardes (Audacity 4 seulement,
    non exploitees ici).

Le document (``doc``) n'est pas du XML texte mais un flux binaire de jetons
"binary XML" (classe ``ProjectSerializer`` d'Audacity) precede d'un
dictionnaire de noms (``dict``).  Le format est decode ici d'apres le source
officiel d'Audacity (``au3/libraries/au3-project-file-io/ProjectSerializer.cpp``) :

  octet 0             : FT_CharSize, suivi de la taille d'un caractere (1, 2, 4)
  FT_Name      (15)   : id (u16), longueur (u16), nom (chaine)
  FT_StartTag  (1)    : id (u16)
  FT_EndTag    (2)    : id (u16)
  FT_String    (3)    : id (u16), longueur (i32), valeur
  FT_Int       (4)    : id (u16), i32
  FT_Bool      (5)    : id (u16), u8
  FT_Long      (6)    : id (u16), i32
  FT_LongLong  (7)    : id (u16), i64
  FT_SizeT     (8)    : id (u16), u32
  FT_Float     (9)    : id (u16), f32, chiffres (i32)
  FT_Double    (10)   : id (u16), f64, chiffres (i32)
  FT_Data      (11)   : longueur (i32), texte
  FT_Raw       (12)   : longueur (i32), texte (ignore a la lecture)
  FT_Push      (13)   : (sans champ)
  FT_Pop       (14)   : (sans champ)
  FT_Blob      (16)   : id (u16), longueur (i32), octets bruts

Tout est en little-endian ; les chaines sont en UTF-8, UTF-16LE ou UTF-32LE
selon FT_CharSize (4 sur Linux/macOS, 2 sur Windows).

Un clip contient une ``<sequence>`` par canal : les versions recentes
d'Audacity (3.4+) ecrivent un ``<wavetrack>`` par canal avec une sequence par
clip, alors que les projets 3.0 a 3.3 rangeaient les deux canaux dans un seul
``<wavetrack>`` (deux sequences dans le meme clip).  Les deux dispositions sont
gerees ici.

Geometrie d'un clip (source : ``WaveClip`` et ``WaveTrack`` d'Audacity) :

  * ``offset``       = debut de la sequence sur la timeline ;
  * ``trimLeft`` / ``trimRight`` = parties rognees, en secondes ;
  * debut audible    = ``offset + trimLeft`` ;
  * fin audible      = ``offset - trimRight + numSamples * etirement / rate`` ;
  * gain par canal   = ``gain`` x loi de panoramique lineaire d'Audacity
    (aucune attenuation au centre : une piste mono est copiee a l'identique
    sur les deux canaux).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
from collections import OrderedDict
from urllib.parse import quote

import numpy as np

# --------------------------------------------------------------------------
# Constantes du format
# --------------------------------------------------------------------------

FT_CHARSIZE, FT_START, FT_END, FT_STRING = 0, 1, 2, 3
FT_INT, FT_BOOL, FT_LONG, FT_LONGLONG = 4, 5, 6, 7
FT_SIZET, FT_FLOAT, FT_DOUBLE, FT_DATA = 8, 9, 10, 11
FT_RAW, FT_PUSH, FT_POP, FT_NAME, FT_BLOB = 12, 13, 14, 15, 16

#: sampleformat (valeur stockee par Audacity) -> (nom, octets par echantillon)
SAMPLE_FORMATS = {
    0x00020001: ("int16", 2),
    0x00040001: ("int24", 4),  # 24 bits ranges dans un entier de 4 octets
    0x0004000F: ("float32", 4),
}

#: Nombre de blocs audio gardes en cache (1 Mio chacun au pire cas)
BLOCK_CACHE_SIZE = 12

APP_ID_AUDACITY = 0x41554459  # 'AUDY'


class Aup4Error(Exception):
    """Erreur de lecture du projet."""


# --------------------------------------------------------------------------
# Decodage du document binaire ("binary XML")
# --------------------------------------------------------------------------


class Node:
    """Un element du document (balise, attributs, enfants, blobs)."""

    __slots__ = ("tag", "attrs", "children", "blobs")

    def __init__(self, tag):
        self.tag = tag
        self.attrs = {}
        self.children = []
        self.blobs = {}

    def get(self, name, default=None):
        return self.attrs.get(name, default)

    def get_float(self, name, default=0.0):
        try:
            return float(self.attrs[name])
        except (KeyError, TypeError, ValueError):
            return default

    def get_int(self, name, default=0):
        try:
            return int(self.attrs[name])
        except (KeyError, TypeError, ValueError):
            return default

    def get_bool(self, name, default=False):
        value = self.attrs.get(name)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes")

    def find(self, tag):
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def find_all(self, tag):
        return [child for child in self.children if child.tag == tag]

    def __repr__(self):  # pragma: no cover - confort de debogage
        return "<%s %s (%d enfants)>" % (self.tag, self.attrs, len(self.children))


class _Cursor:
    """Petit lecteur sequentiel little-endian sur un buffer d'octets."""

    __slots__ = ("data", "pos")

    def __init__(self, data):
        self.data = data
        self.pos = 0

    def eof(self):
        return self.pos >= len(self.data)

    def take(self, count):
        end = self.pos + count
        if end > len(self.data):
            raise Aup4Error(
                "document tronque : %d octets demandes, %d disponibles"
                % (count, len(self.data) - self.pos))
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]

    def f32(self):
        return struct.unpack("<f", self.take(4))[0]

    def f64(self):
        return struct.unpack("<d", self.take(8))[0]


def decode_document(dict_blob, doc_blob):
    """Decode ``dict`` + ``doc`` en arbre de :class:`Node`.

    Audacity enregistre le dictionnaire des noms et le document dans deux
    colonnes, mais les relit concatenes : c'est ce flux que l'on decode.
    """
    reader = _Cursor(bytes(dict_blob) + bytes(doc_blob))
    names = {}
    stack = []
    root = Node("#document")
    current = root
    char_size = 4  # valeur usuelle sur Linux/macOS, corrigee par FT_CharSize

    def read_string(length):
        raw = reader.take(length)
        if char_size == 1:
            return raw.decode("utf-8", "replace")
        if char_size == 2:
            return raw.decode("utf-16-le", "replace")
        if char_size == 4:
            return raw.decode("utf-32-le", "replace")
        raise Aup4Error("taille de caractere non supportee : %r" % (char_size,))

    while not reader.eof():
        field = reader.u8()

        if field == FT_CHARSIZE:
            char_size = reader.u8()
            if char_size not in (1, 2, 4):
                raise Aup4Error("taille de caractere invalide : %d" % char_size)

        elif field == FT_NAME:
            name_id = reader.u16()
            names[name_id] = read_string(reader.u16())

        elif field == FT_START:
            node = Node(_name(names, reader.u16()))
            current.children.append(node)
            stack.append(current)
            current = node

        elif field == FT_END:
            expected = _name(names, reader.u16())
            if current is root or current.tag != expected:
                raise Aup4Error(
                    "document incoherent : </%s> alors que <%s> est ouvert"
                    % (expected, current.tag))
            current = stack.pop()

        elif field == FT_STRING:
            key = _name(names, reader.u16())
            current.attrs[key] = read_string(reader.i32())

        elif field in (FT_INT, FT_LONG):
            key = _name(names, reader.u16())
            current.attrs[key] = reader.i32()

        elif field == FT_BOOL:
            key = _name(names, reader.u16())
            current.attrs[key] = reader.u8() != 0

        elif field == FT_LONGLONG:
            key = _name(names, reader.u16())
            current.attrs[key] = reader.i64()

        elif field == FT_SIZET:
            key = _name(names, reader.u16())
            current.attrs[key] = reader.u32()

        elif field == FT_FLOAT:
            key = _name(names, reader.u16())
            value = reader.f32()
            reader.i32()  # nombre de chiffres significatifs
            current.attrs[key] = value

        elif field == FT_DOUBLE:
            key = _name(names, reader.u16())
            value = reader.f64()
            reader.i32()
            current.attrs[key] = value

        elif field == FT_DATA:
            reader.take(reader.i32())  # contenu textuel des balises

        elif field == FT_RAW:
            reader.take(reader.i32())  # en-tete XML / doctype, ignore

        elif field == FT_BLOB:
            key = _name(names, reader.u16())
            current.blobs[key] = reader.take(reader.i32())

        elif field == FT_PUSH:
            pass  # sous-arbre : le dictionnaire actif est simplement conserve

        elif field == FT_POP:
            pass

        else:
            raise Aup4Error("type de champ inconnu : %d (offset %d)"
                            % (field, reader.pos - 1))

    if current is not root:
        raise Aup4Error("document tronque : <%s> n'est pas ferme" % current.tag)
    return root


def _name(names, name_id):
    try:
        return names[name_id]
    except KeyError:
        raise Aup4Error("identifiant de nom inconnu : %d" % name_id) from None


# --------------------------------------------------------------------------
# Modele du projet
# --------------------------------------------------------------------------


class Clip:
    """Un <waveclip> : une vue sur une plage d'echantillons d'une ou plusieurs sequences.

    ``sequences[j]`` est la liste ``(premier echantillon, blockid)`` du canal
    ``j`` du clip.  Un clip n'a qu'une sequence dans les projets recents (un
    ``<wavetrack>`` par canal), deux dans les projets Audacity 3.0 a 3.3.
    """

    def __init__(self, node, rate):
        self.name = str(node.get("name") or "")
        self.offset = node.get_float("offset")
        self.trim_left = max(0.0, node.get_float("trimLeft"))
        self.trim_right = max(0.0, node.get_float("trimRight"))
        self.stretch = node.get_float("clipStretchRatio", 1.0) or 1.0
        self.rate = rate
        self.num_samples = 0
        self.sequences = []  # par canal : [(premier echantillon, blockid), ...]
        self.envelope = []   # (instant absolu, valeur de gain)

        for sequence in node.find_all("sequence"):
            blocks = []
            num_samples = max(self.num_samples, sequence.get_int("numsamples"))
            for block in sequence.find_all("waveblock"):
                block_id = block.get_int("blockid")
                if block_id == 0:
                    continue
                # blockid negatif = bloc silencieux de -blockid echantillons :
                # inutile de l'enregistrer, la sortie est deja a zero.
                blocks.append((block.get_int("start"), block_id))
            blocks.sort()
            self.sequences.append(blocks)
            self.num_samples = num_samples
        if not self.sequences:
            self.sequences.append([])

        envelope = node.find("envelope")
        if envelope is not None:
            for point in envelope.find_all("controlpoint"):
                self.envelope.append(
                    (point.get_float("t"), point.get_float("val", 1.0)))
            self.envelope.sort()

    @property
    def n_sequences(self):
        """Nombre de canaux portes par ce clip."""
        return len(self.sequences)

    @property
    def play_start(self):
        """Instant (sur la timeline) du premier echantillon audible."""
        return self.offset + self.trim_left

    @property
    def play_end(self):
        """Instant de fin : ``offset - trimRight + numSamples * etirement / rate``."""
        return self.offset - self.trim_right + self.num_samples * self.stretch / self.rate

    def visible_range(self):
        """(index du premier echantillon visible, nombre d'echantillons visibles)."""
        first = int(round(self.trim_left * self.rate))
        last = self.num_samples - int(round(self.trim_right * self.rate))
        first = max(0, min(first, self.num_samples))
        last = max(first, min(last, self.num_samples))
        return first, last - first

    def envelope_values(self, start_time, count, sample_period):
        """Gains d'envelope pour ``count`` echantillons a partir de ``start_time``."""
        if not self.envelope:
            return None
        times = start_time + np.arange(count, dtype=np.float64) * sample_period
        points_t = np.array([point[0] for point in self.envelope], dtype=np.float64)
        points_v = np.array([point[1] for point in self.envelope], dtype=np.float64)
        return np.interp(times, points_t, points_v).astype(np.float32)

    def __repr__(self):  # pragma: no cover
        return "<Clip %r %.3f->%.3f>" % (self.name, self.play_start, self.play_end)


class Channel:
    """Un <wavetrack> : un canal audio (piste mono, ou un canal d'une piste stereo)."""

    def __init__(self, node, project_rate):
        self.name = str(node.get("name") or "")
        # 0 = premier canal du groupe, 1 = second canal (attribut ecrit par Audacity 4)
        self.channel_index = node.get_int("channel", 0)
        self.gain = node.get_float("gain", 1.0)
        self.pan = max(-1.0, min(1.0, node.get_float("pan", 0.0)))
        self.mute = node.get_bool("mute")
        self.solo = node.get_bool("solo")
        self.rate = node.get_float("rate", project_rate) or project_rate
        self.clips = [Clip(child, self.rate) for child in node.find_all("waveclip")]

    def volume(self, output_channel):
        """Gain applique par Audacity (``WaveTrack::GetChannelVolume``).

        Loi de panoramique lineaire, sans attenuation au centre.
        """
        left = right = 1.0
        if self.pan < 0:
            right = 1.0 + self.pan
        elif self.pan > 0:
            left = 1.0 - self.pan
        weight = left if output_channel % 2 == 0 else right
        return self.gain * weight

    def __repr__(self):  # pragma: no cover
        return "<Channel %r ch=%d gain=%.3f pan=%.3f clips=%d>" % (
            self.name, self.channel_index, self.gain, self.pan, len(self.clips))


class Track:
    """Groupe de canaux : 1 canal (mono) ou 2 canaux et plus (stereo)."""

    def __init__(self, channels):
        self.channels = channels

    @property
    def name(self):
        return self.channels[0].name

    @property
    def n_channels(self):
        return len(self.channels)

    @property
    def width(self):
        channels = self.n_channels
        for channel in self.channels:
            for clip in channel.clips:
                channels = max(channels, clip.n_sequences)
        return "stereo" if channels >= 2 else "mono"

    @property
    def mute(self):
        return all(channel.mute for channel in self.channels)

    @property
    def solo(self):
        return any(channel.solo for channel in self.channels)

    @property
    def gain(self):
        return max(channel.gain for channel in self.channels)

    @property
    def pan(self):
        return self.channels[0].pan

    @property
    def clip_count(self):
        return sum(len(channel.clips) for channel in self.channels)

    def __repr__(self):  # pragma: no cover
        return "<Track %r %s %d clips>" % (self.name, self.width, self.clip_count)


class Project:
    """Un projet .aup4 pret a etre mixe."""

    def __init__(self, path):
        self.path = os.fspath(path)
        self.warnings = []
        self.tracks = []
        self.rate = 44100.0
        self.audacity_version = ""
        self.format_version = ""
        self.doc_source = "project"
        self.block_count = 0
        self.block_bytes = 0
        self.sample_formats = {}
        self._tmpdir = None
        self._cache = OrderedDict()
        self._db = None
        self._db_uri = False
        self._open()

    # -- ouverture ------------------------------------------------------
    def _open(self):
        if not os.path.isfile(self.path):
            raise Aup4Error("fichier introuvable : %s" % self.path)

        self._check_header()
        target, self._db_uri = self._prepare_database()
        self._db = sqlite3.connect(target, uri=self._db_uri)
        try:
            self._load()
        except Exception:
            self.close()
            raise

    def _load(self):
        tables = {row[0] for row in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for required in ("project", "sampleblocks"):
            if required not in tables:
                raise Aup4Error(
                    "%s n'est pas un projet Audacity 4 (table %r absente)"
                    % (self.path, required))

        dict_blob, doc_blob, source = self._pick_document(tables)
        self.doc_source = source
        if source == "autosave":
            self.warnings.append(
                "le document principal ('project') etait vide : lecture de la "
                "sauvegarde automatique ('autosave')")
        if not doc_blob:
            raise Aup4Error(
                "aucun document de projet exploitable dans %s (ni 'project' ni "
                "'autosave') : fichier probablement vide ou corrompu" % self.path)

        self._load_blocks_info()
        self._load_document(decode_document(dict_blob, doc_blob))

    def _check_header(self):
        with open(self.path, "rb") as handle:
            header = handle.read(100)
        if len(header) < 100 or header[:16] != b"SQLite format 3\x00":
            raise Aup4Error(
                "%s n'est pas une base SQLite : est-ce bien un projet Audacity 4 "
                "(.aup4) ?" % self.path)
        application_id = struct.unpack(">I", header[68:72])[0]
        if application_id != APP_ID_AUDACITY:
            self.warnings.append(
                "application_id inattendu (0x%08X) : le fichier n'a pas ete ecrit "
                "par Audacity" % application_id)
        user_version = struct.unpack(">I", header[60:64])[0]
        major = (user_version >> 24) & 0xFF
        if major >= 3:
            self.audacity_version = "%d.%d.%d" % (
                major, (user_version >> 16) & 0xFF, (user_version >> 8) & 0xFF)

    def _prepare_database(self):
        """Retourne (cible sqlite, uri?) a ouvrir pour lire le projet."""
        wal = self.path + "-wal"
        if os.path.isfile(wal) and os.path.getsize(wal) > 0:
            # Un journal WAL non fusionne contient les dernieres modifications :
            # on copie le trio de fichiers et on le laisse se fusionner.
            self._tmpdir = tempfile.mkdtemp(prefix="aup4-")
            base = os.path.join(self._tmpdir, "project.aup4")
            shutil.copy2(self.path, base)
            for suffix in ("-wal", "-shm"):
                if os.path.isfile(self.path + suffix):
                    shutil.copy2(self.path + suffix, base + suffix)
            self.warnings.append(
                "journal WAL detecte : projet copie dans un dossier temporaire "
                "pour integrer les dernieres modifications")
            return base, False
        # immutable=1 : lecture stricte, aucun verrou, aucun fichier annexe cree
        return "file:%s?immutable=1" % quote(os.path.abspath(self.path)), True

    def _pick_document(self, tables):
        def read(source):
            try:
                row = self._db.execute(
                    "SELECT dict, doc FROM %s" % source).fetchone()
            except sqlite3.DatabaseError as error:
                raise Aup4Error("lecture de %r impossible : %s" % (source, error))
            return row if row else (None, None)

        dict_blob, doc_blob = read("project")
        if doc_blob:
            return dict_blob or b"", doc_blob, "project"
        if "autosave" in tables:
            dict_blob, doc_blob = read("autosave")
            if doc_blob:
                return dict_blob or b"", doc_blob, "autosave"
        return b"", b"", "project"

    def _load_blocks_info(self):
        rows = self._db.execute(
            "SELECT sampleformat, COUNT(*), COALESCE(SUM(LENGTH(samples)), 0) "
            "FROM sampleblocks GROUP BY sampleformat")
        for sample_format, count, size in rows:
            self.block_count += count
            self.block_bytes += size or 0
            name = SAMPLE_FORMATS.get(
                sample_format, ("inconnu-0x%08X" % sample_format, 4))[0]
            self.sample_formats[name] = self.sample_formats.get(name, 0) + count

    def _load_document(self, document):
        children = document.children
        if len(children) != 1 or children[0].tag != "project":
            raise Aup4Error(
                "document inattendu : racine <%s>"
                % (children[0].tag if children else "vide"))
        root = children[0]
        self.format_version = str(root.get("version") or "")
        self.audacity_version = str(root.get("audacityversion") or "") \
            or self.audacity_version
        self.rate = root.get_float("rate", 44100.0) or 44100.0

        channels = [Channel(node, self.rate) for node in root.find_all("wavetrack")]
        if not channels:
            raise Aup4Error("aucune piste audio (<wavetrack>) dans le projet")

        # Regroupement des canaux : channel=0 ouvre une piste, les canaux
        # suivants (channel=1, ...) appartiennent a la meme piste.
        current = []
        for channel in channels:
            if channel.channel_index == 0 and current:
                self.tracks.append(Track(current))
                current = []
            current.append(channel)
        if current:
            self.tracks.append(Track(current))

        for tag in ("labeltrack", "timetrack", "notetrack"):
            if root.find(tag) is not None:
                self.warnings.append(
                    "pistes <%s> presentes : elles ne contiennent pas d'audio et "
                    "sont ignorees" % tag)
        for effects in root.find_all("effects"):
            if effects.children:  # effets temps reel reellement presents
                _add_warning(
                    self.warnings,
                    "des effets temps reel sont declares sur les pistes : ils ne "
                    "sont PAS rendus (seul le mix stocke dans le projet est "
                    "restitue)")
                break
        for track in self.tracks:
            if track.n_channels > 2:
                self.warnings.append(
                    "piste %r a %d canaux : les canaux au-dela de 2 sont replies "
                    "sur gauche/droite" % (track.name, track.n_channels))

    # -- acces aux echantillons ----------------------------------------
    def _block(self, block_id):
        """Echantillons d'un bloc audio, en float32 mono."""
        cached = self._cache.get(block_id)
        if cached is not None:
            self._cache.move_to_end(block_id)
            return cached

        if block_id < 0:  # bloc silencieux : aucun enregistrement en base
            samples = np.zeros(-block_id, dtype=np.float32)
        else:
            row = self._db.execute(
                "SELECT sampleformat, samples FROM sampleblocks WHERE blockid = ?",
                (block_id,)).fetchone()
            if row is None or row[1] is None:
                self.warnings.append(
                    "bloc audio %d absent de la base : remplace par du silence"
                    % block_id)
                samples = np.zeros(0, dtype=np.float32)
            else:
                samples = _decode_samples(row[0], row[1])

        self._cache[block_id] = samples
        if len(self._cache) > BLOCK_CACHE_SIZE:
            self._cache.popitem(last=False)
        return samples

    def clip_samples(self, clip, sequence_index=0):
        """Echantillons visibles d'un clip (float32, a la frequence du canal)."""
        first, count = clip.visible_range()
        if count <= 0:
            return np.zeros(0, dtype=np.float32)
        out = np.zeros(count, dtype=np.float32)
        last = first + count
        for start, block_id in clip.sequences[sequence_index]:
            if block_id < 0:
                continue  # silence : la sortie est deja a zero
            samples = self._block(block_id)
            block_end = start + samples.size
            if block_end <= first or start >= last:
                continue
            low = max(start, first)
            high = min(block_end, last)
            out[low - first:high - first] = samples[low - start:high - start]
        return out

    # -- rendu ----------------------------------------------------------
    def duration(self):
        """Duree du mix, en secondes."""
        end = 0.0
        for track in self.tracks:
            for channel in track.channels:
                for clip in channel.clips:
                    end = max(end, clip.play_end)
        return end

    def render(self, progress=None, mono=False, respect_mute_solo=True):
        """Mixe le projet.

        Retourne ``(echantillons, frequence)`` avec ``echantillons`` un tableau
        float32 de forme ``(n, 1)`` (mono) ou ``(n, 2)`` (stereo).
        """
        tracks = list(self.tracks)
        if respect_mute_solo:
            soloed = [track for track in tracks if track.solo]
            if soloed:
                tracks = soloed
                _add_warning(self.warnings,
                             "mode solo actif dans le projet : seules les pistes "
                             "en solo sont rendues")
            audible = [track for track in tracks if not track.mute]
            if len(audible) != len(tracks):
                _add_warning(self.warnings, "pistes muettes ignorees")
                tracks = audible

        out_channels = 1 if mono else 2
        total = int(round(self.duration() * self.rate)) + 1
        if total <= 1:
            raise Aup4Error("le projet ne contient aucun echantillon audio audible")
        output = np.zeros((total, out_channels), dtype=np.float32)

        jobs = [channel for track in tracks for channel in track.channels]
        for index, channel in enumerate(jobs, 1):
            if progress:
                progress(index / max(1, len(jobs)),
                         "piste %r (canal %d)" % (channel.name, channel.channel_index))
            group_size = _group_size(tracks, channel)
            for clip in channel.clips:
                self._mix_clip(output, clip, channel, group_size, mono)
        if progress:
            progress(1.0, "mixage termine")
        return output, self.rate

    def _mix_clip(self, output, clip, channel, group_size, mono):
        start = int(round(clip.play_start * self.rate))
        if start >= len(output):
            return

        # Une piste mono (un seul canal et un seul sequence par clip) est
        # recopiee sur les deux sorties, sans attenuation au centre (comme
        # Audacity, qui applique simplement les gains de panoramique).
        mono_track = group_size <= 1 and clip.n_sequences == 1

        for index in range(clip.n_sequences):
            samples = self.clip_samples(clip, index)
            if samples.size == 0:
                continue

            trim = max(0, -start)  # clip qui commence avant zero : on rogne
            if trim:
                samples = samples[trim:]
            begin = max(start, 0)
            if begin >= len(output) or samples.size == 0:
                continue

            samples = self._transform(samples, clip, channel)
            samples = samples[:len(output) - begin]
            if samples.size == 0:
                continue

            envelope = clip.envelope_values(
                clip.play_start + trim / self.rate, samples.size, 1.0 / self.rate)
            if envelope is not None:
                samples = samples * envelope
            stop = begin + samples.size

            if mono_track:
                output[begin:stop, 0] += samples * channel.volume(0)
                if output.shape[1] > 1:
                    output[begin:stop, 1] += samples * channel.volume(1)
                continue

            logical = channel.channel_index if group_size > 1 else index
            if output.shape[1] == 1:
                output[begin:stop, 0] += samples * channel.volume(logical % 2)
            else:
                side = logical % 2
                output[begin:stop, side] += samples * channel.volume(side)

    def _transform(self, samples, clip, channel):
        """Applique etirement et changement de frequence, si necessaires."""
        stretched = abs(clip.stretch - 1.0) > 1e-9
        converted = abs(channel.rate - self.rate) > 1e-6
        if not (stretched or converted):
            return samples
        result = _transform_audio(samples, channel.rate, self.rate, clip.stretch)
        if result is None:  # ffmpeg absent ou filtre refuse : repli approximatif
            wanted = int(round(samples.size * clip.stretch * self.rate / channel.rate))
            result = _resample(samples, max(0, wanted))
            _add_warning(
                self.warnings,
                "clip %r : etirement/reechantillonnage approximatif (interpolation "
                "lineaire : ffmpeg indisponible, hauteur du son non preservee si le "
                "clip est etire, x%g)" % (clip.name, clip.stretch))
        return result

    # -- divers ---------------------------------------------------------
    def summary(self):
        lines = ["Fichier         : %s" % self.path,
                 "Document        : %s" % self.doc_source,
                 "Audacity        : %s (format %s)" % (
                     self.audacity_version or "?", self.format_version or "?"),
                 "Frequence       : %g Hz" % self.rate,
                 "Duree du mix    : %s (%d echantillons)" % (
                     format_duration(self.duration()),
                     int(round(self.duration() * self.rate)))]
        formats = ", ".join("%s x%d" % (name, count)
                           for name, count in sorted(self.sample_formats.items()))
        lines.append("Blocs audio     : %d (%s, %.1f Mio)" % (
            self.block_count, formats or "aucun",
            self.block_bytes / (1024 * 1024)))
        lines.append("Pistes          : %d" % len(self.tracks))
        for index, track in enumerate(self.tracks, 1):
            flags = []
            if track.mute:
                flags.append("muet")
            if track.solo:
                flags.append("solo")
            lines.append(
                "  %d. %-28s %-6s gain %.3f pan %+.2f  %d clip(s)%s" % (
                    index, track.name[:28], track.width, track.gain, track.pan,
                    track.clip_count,
                    "  [%s]" % ", ".join(flags) if flags else ""))
            for channel in track.channels:
                for clip in channel.clips:
                    lines.append(
                        "       canal %d  %8.3f s -> %8.3f s  %r" % (
                            channel.channel_index, clip.play_start, clip.play_end,
                            clip.name))
        return "\n".join(lines)

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        self._cache.clear()
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def _group_size(tracks, channel):
    """Nombre de canaux de la piste a laquelle appartient ``channel``."""
    for track in tracks:
        if any(candidate is channel for candidate in track.channels):
            return track.n_channels
    return 1


def _add_warning(warnings, message):
    if message not in warnings:
        warnings.append(message)


def _decode_samples(sample_format, blob):
    """Convertit un blob d'echantillons en float32."""
    info = SAMPLE_FORMATS.get(sample_format)
    if info is None:
        raise Aup4Error("format d'echantillon inconnu : 0x%08X" % sample_format)
    name = info[0]
    if name == "float32":
        return np.frombuffer(blob, dtype="<f4").astype(np.float32, copy=False)
    if name == "int16":
        return np.frombuffer(blob, dtype="<i2").astype(np.float32) / 32768.0
    # int24 : 24 bits ranges dans un entier de 4 octets (echelle 2^23)
    return np.frombuffer(blob, dtype="<i4").astype(np.float32) / 8388608.0


def _transform_audio(samples, rate_in, rate_out, stretch):
    """Etirement (hauteur preservee) et/ou conversion de frequence via ffmpeg.

    Retourne ``None`` si ffmpeg est absent ou refuse les filtres, pour laisser
    l'appelant se rabattre sur une interpolation lineaire.
    """
    binary = shutil.which("ffmpeg")
    if binary is None:
        return None

    has_stretch = abs(stretch - 1.0) > 1e-9
    has_rate = abs(rate_in - rate_out) > 1e-6
    if not (has_stretch or has_rate):
        return samples

    expected = int(round(samples.size * (stretch if has_stretch else 1.0)
                         * rate_out / rate_in))
    rate_filters = ["aresample=%d" % int(round(rate_out))] if has_rate else []

    if has_stretch:
        # rubberband (Audacity utilise aussi un etireur a hauteur constante) donne
        # la longueur exacte ; atempo sert de repli, avec correction de longueur.
        for chain, exact in ((_rubberband_filters(stretch), True),
                             (_atempo_filters(stretch), False)):
            audio = _run_ffmpeg_filters(binary, samples, rate_in, chain + rate_filters)
            if audio is None:
                continue
            if abs(audio.size - expected) <= 2:  # longueur exacte : rien a faire
                return audio
            if expected <= 0:
                return audio
            if audio.size >= expected * 0.5:
                # longueur approchee (atempo) : on ajuste legerement
                return _resample(audio, expected)
            if audio.size < expected:  # nettement trop court : on complete
                return np.concatenate(
                    [audio, np.zeros(expected - audio.size, dtype=np.float32)])
            return audio
        return None

    audio = _run_ffmpeg_filters(binary, samples, rate_in, rate_filters)
    if audio is None:
        return None
    return audio if abs(audio.size - expected) <= 2 else _resample(audio, expected)


def _rubberband_filters(stretch):
    """Filtre rubberband : etirement a hauteur constante de bonne qualite."""
    return ["rubberband=tempo=%.9f" % (1.0 / stretch)]


def _atempo_filters(stretch):
    """Filtre atempo, enchaine autant que necessaire (0,5 a 2,0 par instance)."""
    tempo = 1.0 / stretch
    filters = []
    while tempo > 2.0:
        filters.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        filters.append("atempo=0.5")
        tempo /= 0.5
    filters.append("atempo=%.9f" % tempo)
    return filters


def _run_ffmpeg_filters(binary, samples, rate_in, filters):
    """Passe un signal mono float32 dans une chaine de filtres ffmpeg."""
    if not filters:
        return samples
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "f32le", "-ar", "%d" % int(round(rate_in)), "-ac", "1",
               "-i", "pipe:0", "-filter:a", ",".join(filters),
               "-f", "f32le", "-ac", "1", "pipe:1"]
    try:
        completed = subprocess.run(
            command, input=np.ascontiguousarray(samples, dtype="<f4").tobytes(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    audio = np.frombuffer(completed.stdout, dtype="<f4").astype(np.float32, copy=False)
    return audio if audio.size else None


def _resample(samples, wanted):
    """Reechantillonnage lineaire (approximation de celui d'Audacity)."""
    if wanted == samples.size:
        return samples
    if wanted <= 0:
        return np.zeros(0, dtype=np.float32)
    if samples.size == 1:
        return np.repeat(samples, wanted)
    positions = np.linspace(0.0, samples.size - 1, wanted, dtype=np.float64)
    return np.interp(positions, np.arange(samples.size, dtype=np.float64),
                     samples).astype(np.float32)


def format_duration(seconds):
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(int(round(seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d h %02d min %02d s" % (hours, minutes, secs)
    if minutes:
        return "%d min %02d s" % (minutes, secs)
    return "%d s" % secs
