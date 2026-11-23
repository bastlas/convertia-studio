"""Localisation de ffmpeg / ffprobe et interrogation des fichiers médias.

Les binaires embarqués (``bin/`` à côté de l'exécutable) sont essayés en
premier, puis ceux du ``PATH``.  Chaque candidat est réellement exécuté
(``-version``, résultat mis en cache) : un binaire cassé — par exemple lié à
des bibliothèques absentes de la distribution — est ignoré au profit du
suivant.  Sous Windows, l'extension ``.exe`` est ajoutée automatiquement.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys


class FFmpegMissingError(Exception):
    """ffmpeg est introuvable."""


def _candidate_dirs():
    here = os.path.dirname(os.path.abspath(__file__))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    roots = [os.path.join(here, "bin"), os.path.join(here, os.pardir, "bin"),
             os.path.join(exe_dir, "bin")]
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(os.path.join(meipass, "bin"))
            roots.append(meipass)
    return [os.path.normpath(root) for root in roots]


_working_cache = {}


def _works(binary):
    """Vrai si le binaire s'exécute réellement (bibliothèques présentes)."""
    if binary in _working_cache:
        return _working_cache[binary]
    try:
        completed = subprocess.run(
            [binary, "-version"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=8)
        result = completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        result = False
    _working_cache[binary] = result
    return result


def _find(name):
    suffix = ".exe" if os.name == "nt" else ""
    candidates = [os.path.join(directory, name + suffix)
                  for directory in _candidate_dirs()]
    in_path = shutil.which(name)
    if in_path:
        candidates.append(in_path)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK) \
                and _works(candidate):
            return candidate
    return None


def ffmpeg():
    """Chemin de ffmpeg, ou ``None`` s'il est absent."""
    return _find("ffmpeg")


def ffprobe():
    """Chemin de ffprobe, ou ``None`` s'il est absent."""
    return _find("ffprobe")


def require_ffmpeg():
    binary = ffmpeg()
    if binary is None:
        raise FFmpegMissingError(
            "ffmpeg est introuvable ou inutilisable : il est nécessaire pour "
            "encoder dans ce format. Installe-le (paquet ffmpeg) ou place un "
            "binaire valide à côté du programme.")
    return binary


_version_cache = {}


def version(binary=None):
    """Version de ffmpeg (« 7.1 » par exemple), ou ``None``."""
    binary = binary or ffmpeg()
    if binary is None:
        return None
    if binary in _version_cache:
        return _version_cache[binary]
    try:
        out = subprocess.run(
            [binary, "-hide_banner", "-version"], capture_output=True,
            text=True, timeout=20).stdout
        first = out.splitlines()[0] if out else ""
        pretty = first.replace("ffmpeg version", "").strip().split(" ")[0]
        _version_cache[binary] = pretty or None
    except (OSError, subprocess.SubprocessError):
        _version_cache[binary] = None
    return _version_cache[binary]


def filters_available(binary=None):
    """Ensemble des filtres audio connus de ffmpeg (pour l'étirement de clips)."""
    binary = binary or ffmpeg()
    if binary is None:
        return set()
    try:
        out = subprocess.run([binary, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and not line.startswith("Filters:"):
            names.add(parts[1])
    return names


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_CHANNELS = {"mono": 1, "stereo": 2, "2.1": 3, "quad": 4, "5.1": 6, "7.1": 8}
_RATE_RE = re.compile(r"(\d+)\s*Hz")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*: Audio: ([a-z0-9_]+).*?")


def _probe_with_ffmpeg(path, info):
    """Analyse de secours quand ffprobe n'est pas disponible.

    ``ffmpeg -i fichier`` écrit les informations dans stderr puis se termine en
    erreur : on récupère la durée, le codec, la fréquence et le nombre de canaux.
    """
    binary = ffmpeg()
    if binary is None:
        return info
    try:
        completed = subprocess.run([binary, "-hide_banner", "-i", path],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return info
    text = completed.stderr or ""

    match = _DURATION_RE.search(text)
    if match:
        hours, minutes, seconds = match.groups()
        info["duration"] = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    match = _RATE_RE.search(text)
    if match:
        info["sample_rate"] = int(match.group(1))
    match = _AUDIO_RE.search(text)
    if match:
        info["codec"] = match.group(1)
        info["audio_streams"] = 1
        for name, count in _CHANNELS.items():
            if name in text:
                info["channels"] = count
                break
    return info


def probe(path):
    """Informations générales sur un fichier média (via ffprobe).

    Retourne un dictionnaire ``{duration, sample_rate, channels, codec,
    format, audio_streams}`` ; les valeurs inconnues sont ``None``.
    """
    info = {"duration": None, "sample_rate": None, "channels": None,
            "codec": None, "format": None, "audio_streams": 0}
    binary = ffprobe()
    if binary is None:
        return _probe_with_ffmpeg(path, info)
    command = [binary, "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=60)
    except (OSError, subprocess.SubprocessError):
        return info
    if completed.returncode != 0 or not completed.stdout:
        return info
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return info

    audio = [stream for stream in data.get("streams", [])
             if stream.get("codec_type") == "audio"]
    info["audio_streams"] = len(audio)
    if audio:
        first = audio[0]
        info["codec"] = first.get("codec_name")
        info["channels"] = first.get("channels")
        try:
            info["sample_rate"] = int(first.get("sample_rate"))
        except (TypeError, ValueError):
            info["sample_rate"] = None
    try:
        info["duration"] = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        info["duration"] = None
    info["format"] = data.get("format", {}).get("format_name")
    return info
