"""Registre des formats audio de sortie et encodage via ffmpeg.

Chaque format décrit son conteneur, son codec, son extension, ses réglages
possibles (débit, profondeur PCM) et ses arguments ffmpeg.  L'encodage accepte
deux entrées :

* ``encode_samples`` : un tableau numpy (issu du mixage d'un projet Audacity) ;
* ``encode_file`` : n'importe quel fichier audio, laissé à ffmpeg.
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
from dataclasses import dataclass

import numpy as np

from .. import ffmpeg_tools

#: Débits proposés dans l'interface pour les formats avec perte
BITRATE_CHOICES = ("96k", "128k", "160k", "192k", "256k", "320k")

#: Profondeurs PCM proposées
DEPTH_CHOICES = (("16 bits", "16"), ("24 bits", "24"), ("32 bits flottant", "32f"))

#: Fréquences d'échantillonnage proposées (None = celle de la source)
RATE_CHOICES = (("Source", None), ("44 100 Hz", 44100), ("48 000 Hz", 48000),
                ("96 000 Hz", 96000))


@dataclass(frozen=True)
class AudioFormat:
    """Description d'un format de sortie audio."""

    key: str
    label: str
    extension: str
    codec: str
    family: str                 # "lossy", "lossless" ou "pcm"
    description: str = ""
    default_bitrate: str | None = None
    supports_bitrate: bool = False
    supports_depth: bool = False
    container_args: tuple = ()
    muxer: str | None = None   # muxeur ffmpeg imposé (indépendant de l'extension)

    @property
    def display(self):
        return self.label

    @property
    def badge(self):
        return {"lossy": "compressé", "lossless": "sans perte",
                "pcm": "non compressé"}.get(self.family, self.family)


FORMATS = (
    AudioFormat("mp4", "MP4 · AAC", ".mp4", "aac", "lossy",
                "Vidéo-compatible, lecture partout", "256k", True, False,
                ("-movflags", "+faststart", "-vn"), muxer="mp4"),
    AudioFormat("m4a", "M4A · AAC", ".m4a", "aac", "lossy",
                "Même audio qu'un MP4, sans conteneur vidéo", "256k", True, False,
                ("-movflags", "+faststart"), muxer="ipod"),
    AudioFormat("alac", "M4A · ALAC", ".m4a", "alac", "lossless",
                "Sans perte, compatible Apple", None, False, False,
                ("-movflags", "+faststart"), muxer="ipod"),
    AudioFormat("mp3", "MP3", ".mp3", "libmp3lame", "lossy",
                "Universel, poids minimal", "192k", True, False, muxer="mp3"),
    AudioFormat("ogg", "OGG · Vorbis", ".ogg", "libvorbis", "lossy",
                "Ouvert, bon rendu à bas débit", "192k", True, False, muxer="ogg"),
    AudioFormat("opus", "OPUS", ".opus", "libopus", "lossy",
                "Le plus efficace en voix et podcast", "128k", True, False, muxer="opus"),
    AudioFormat("flac", "FLAC", ".flac", "flac", "lossless",
                "Sans perte, compressé", None, False, False, muxer="flac"),
    AudioFormat("wav", "WAV", ".wav", "", "pcm",
                "PCM brut, montage et archivage", None, False, True, muxer="wav"),
    AudioFormat("aiff", "AIFF", ".aiff", "", "pcm",
                "PCM Apple, sans perte", None, False, True, muxer="aiff"),
)

FORMAT_KEYS = tuple(fmt.key for fmt in FORMATS)

_PCM_CODECS = {
    "wav": {"16": "pcm_s16le", "24": "pcm_s24le", "32f": "pcm_f32le"},
    "aiff": {"16": "pcm_s16be", "24": "pcm_s24be", "32f": "pcm_f32be"},
}


class FormatError(Exception):
    """Format inconnu ou réglage invalide."""


def get_format(key):
    """Retourne la description du format ``key``."""
    for fmt in FORMATS:
        if fmt.key == key:
            return fmt
    raise FormatError("format de sortie inconnu : %r" % (key,))


def guess_format(path, default="mp4"):
    """Déduit la clé de format à partir de l'extension d'un fichier."""
    extension = os.path.splitext(path)[1].lower().lstrip(".")
    for fmt in FORMATS:
        if fmt.extension.lstrip(".") == extension:
            return fmt.key
    if extension == "aif":
        return "aiff"
    return default


def codec_args(fmt, options=None):
    """Arguments ffmpeg de codec (débit, profondeur, conteneur)."""
    options = options or {}
    args = ["-c:a", _codec_name(fmt, options)]
    if fmt.supports_bitrate:
        bitrate = options.get("bitrate") or fmt.default_bitrate
        if bitrate:
            args += ["-b:a", str(bitrate)]
    if fmt.key == "flac":
        args += ["-compression_level", "8"]
    return args + list(fmt.container_args)


def _codec_name(fmt, options):
    if fmt.family == "pcm":
        depth = str(options.get("depth") or "24")
        table = _PCM_CODECS.get(fmt.key, {})
        if depth not in table:
            raise FormatError("profondeur PCM non gérée pour %s : %r"
                              % (fmt.key, depth))
        return table[depth]
    return fmt.codec


def _muxer_args(fmt):
    """Impose le conteneur, pour rester juste quel que soit le nom de sortie."""
    return ["-f", fmt.muxer] if fmt.muxer else []


def _rate_args(options):
    rate = (options or {}).get("sample_rate")
    return ["-ar", str(int(rate))] if rate else []


def _channel_args(options):
    return ["-ac", "1"] if (options or {}).get("mono") else []


# --------------------------------------------------------------------------
# Encodage
# --------------------------------------------------------------------------


def encode_samples(dest, samples, rate, format_key, options=None, on_progress=None):
    """Écrit un mix numpy (float32, (n, canaux)) dans ``dest``."""
    fmt = get_format(format_key)
    options = options or {}
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    if samples.ndim != 2 or samples.shape[0] == 0:
        raise FormatError("aucun échantillon à écrire")

    if fmt.family == "pcm" and options.get("sample_rate") is None \
            and ffmpeg_tools.ffmpeg() is None:
        # Repli sans ffmpeg : WAV/AIFF écrit directement (aucun rééchantillonnage)
        write_pcm_file(dest, samples, rate, fmt.key,
                       options.get("depth") or "24")
        if on_progress:
            on_progress(1.0, "%s écrit" % fmt.label)
        return dest

    binary = ffmpeg_tools.require_ffmpeg()
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-f", "f32le", "-ar", str(int(round(rate))),
               "-ac", str(samples.shape[1]), "-i", "pipe:0"]
    command += codec_args(fmt, options) + _rate_args(options) + _channel_args(options)
    command += _muxer_args(fmt)
    command.append(dest)
    _pipe(command, samples, len(samples), on_progress, fmt)
    return dest


def encode_file(dest, source, format_key, options=None, on_progress=None):
    """Convertit un fichier média quelconque vers ``dest`` (via ffmpeg)."""
    fmt = get_format(format_key)
    options = options or {}
    binary = ffmpeg_tools.require_ffmpeg()
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-i", source, "-map", "0:a:0", "-nostats", "-progress", "pipe:1"]
    command += codec_args(fmt, options) + _rate_args(options) + _channel_args(options)
    command += _muxer_args(fmt)
    command.append(dest)
    _run(command, on_progress, fmt, duration=options.get("duration"))
    return dest


def write_pcm_file(dest, samples, rate, format_key, depth="24"):
    """Écrit un WAV ou un AIFF PCM sans passer par ffmpeg (chemin de secours)."""
    if format_key == "wav":
        write_wav(dest, samples, rate, depth)
    elif format_key == "aiff":
        write_aiff(dest, samples, rate, depth)
    else:
        raise FormatError("écriture directe impossible pour %r" % (format_key,))
    return dest


# -- WAV / AIFF écrits à la main -------------------------------------------


def to_pcm(samples, depth="24"):
    """Convertit un tableau float32 en entier PCM (avec saturation)."""
    depth = str(depth)
    if depth == "32f":
        return np.ascontiguousarray(samples, dtype="<f4")
    clipped = np.clip(samples, -1.0, 1.0)
    if depth == "16":
        return np.round(clipped * 32767.0).astype("<i2")
    if depth == "24":
        raw = np.round(clipped * 8388607.0).astype("<i4").tobytes()
        return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)[:, :3].reshape(-1)
    raise FormatError("profondeur non gérée : %r (16, 24 ou 32f)" % depth)


def write_wav(dest, samples, rate, depth="24"):
    """Écrit un WAV PCM 16/24 bits ou float 32 bits."""
    depth = str(depth)
    channels = samples.shape[1]
    data = to_pcm(samples, depth).tobytes()
    if depth == "16":
        tag, align, bits = 1, channels * 2, 16
    elif depth == "24":
        tag, align, bits = 1, channels * 3, 24
    else:
        tag, align, bits = 3, channels * 4, 32
    rate = int(round(rate))
    header = bytearray(b"RIFF")
    header += struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, tag, channels, rate,
                          rate * align, align, bits)
    header += b"data" + struct.pack("<I", len(data))
    with open(dest, "wb") as handle:
        handle.write(bytes(header))
        handle.write(data)
    return dest


def write_aiff(dest, samples, rate, depth="24"):
    """Écrit un AIFF (16/24 bits) ou un AIFC fl32 (32 bits flottant)."""
    depth = str(depth)
    channels = samples.shape[1]
    rate = int(round(rate))
    frames = samples.shape[0]

    if depth == "32f":
        # l'AIFF simple ne connaît que le PCM entier : on écrit un AIFC fl32
        payload = np.ascontiguousarray(samples, dtype=">f4").tobytes()
        sample_size, compression, form_type = 32, b"fl32", b"AIFC"
        name = b"32-bit float"
    else:
        if depth == "16":
            payload = np.ascontiguousarray(to_pcm(samples, "16").astype(">i2")).tobytes()
            sample_size = 16
        else:
            raw = to_pcm(samples, "24").reshape(-1, 3)
            payload = np.ascontiguousarray(raw[:, ::-1]).tobytes()
            sample_size = 24
        compression, form_type, name = b"NONE", b"AIFF", b"not compressed"

    # fréquence d'échantillonnage au format « 80-bit extended »
    mantissa, exponent = math.frexp(float(rate))
    rate_bytes = struct.pack(">HQ", exponent + 16382, int(mantissa * (1 << 64)))

    comm = struct.pack(">hIh", channels, frames, sample_size) + rate_bytes
    if form_type == b"AIFC":
        pascal = bytes([len(name)]) + name
        if len(pascal) % 2:
            pascal += b"\x00"  # remplissage : les blocs AIFF font une taille paire
        comm += compression + pascal

    ssnd = b"\x00" * 8 + payload  # offset (4) + taille de bloc (4) puis les données
    chunks = (b"COMM" + struct.pack(">I", len(comm)) + comm
              + b"SSND" + struct.pack(">I", len(ssnd)) + ssnd)
    body = form_type + chunks
    with open(dest, "wb") as handle:
        handle.write(b"FORM" + struct.pack(">I", len(body)) + body)
    return dest


# --------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------


def _pipe(command, samples, total, on_progress, fmt):
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    chunk = 1 << 18
    try:
        for start in range(0, total, chunk):
            process.stdin.write(
                np.ascontiguousarray(samples[start:start + chunk]).tobytes())
            if on_progress:
                on_progress(min(1.0, (start + chunk * 0.5) / total),
                            "encodage %s" % fmt.label)
    except BrokenPipeError:
        pass
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
    _finish(process)


def _run(command, on_progress, fmt, duration=None):
    """Lance ffmpeg et suit son avancement (option ``-progress pipe:1``)."""
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    total_us = (duration or 0) * 1_000_000
    for raw in process.stdout:
        if not on_progress or not total_us:
            continue
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_ms=") or line.startswith("out_time_us="):
            try:
                done = int(line.split("=", 1)[1])
            except ValueError:
                continue
            if done >= 0:
                on_progress(min(0.99, done / total_us), "encodage %s" % fmt.label)
    process.stdout.close()
    _finish(process)


def _finish(process):
    errors = process.stderr.read().decode("utf-8", "replace").strip()
    process.stderr.close()
    code = process.wait()
    if code != 0:
        raise FormatError("ffmpeg a échoué (code %d) :\n%s"
                          % (code, errors or "(sans message)"))
