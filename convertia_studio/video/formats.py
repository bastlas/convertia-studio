"""Formats vidéo de sortie de Convertia Studio."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoFormat:
    """Un conteneur et son couple de codecs vidéo / audio."""

    key: str
    label: str
    extension: str
    container: str          # muxer ffmpeg : mp4, matroska, webm
    video_codec: str        # encodeur ffmpeg : libx264, libx265, libvpx-vp9
    audio_codec: str        # aac ou libopus
    description: str
    badge: str
    family: str
    default_crf: int
    crf_min: int
    crf_max: int
    audio_bitrates: tuple
    default_audio_bitrate: str
    audio_copy_codecs: tuple = ()   # None = tout accepter (Matroska)


FORMATS = (
    VideoFormat(
        key="mp4", label="MP4 · H.264", extension=".mp4", container="mp4",
        video_codec="libx264", audio_codec="aac",
        description="Universel : téléviseurs, téléphones, réseaux sociaux.",
        badge="UNIVERSEL", family="lossy", default_crf=23,
        crf_min=16, crf_max=34,
        audio_bitrates=("96k", "128k", "192k", "256k", "320k"),
        default_audio_bitrate="192k",
        audio_copy_codecs=("aac", "mp3", "ac3", "eac3", "alac")),
    VideoFormat(
        key="h265", label="MP4 · H.265", extension=".mp4", container="mp4",
        video_codec="libx265", audio_codec="aac",
        description="Plus compact à qualité égale, liseurs récents.",
        badge="COMPACT", family="lossy", default_crf=26,
        crf_min=18, crf_max=36,
        audio_bitrates=("96k", "128k", "192k", "256k"),
        default_audio_bitrate="192k",
        audio_copy_codecs=("aac", "mp3", "ac3", "eac3", "alac")),
    VideoFormat(
        key="mov", label="MOV · H.264", extension=".mov", container="mov",
        video_codec="libx264", audio_codec="aac",
        description="QuickTime, compatible Apple et logiciels de montage.",
        badge="APPLE", family="lossy", default_crf=23,
        crf_min=16, crf_max=34,
        audio_bitrates=("96k", "128k", "192k", "256k", "320k"),
        default_audio_bitrate="192k",
        audio_copy_codecs=("aac", "mp3", "ac3", "eac3", "alac")),
    VideoFormat(
        key="webm", label="WebM · VP9", extension=".webm", container="webm",
        video_codec="libvpx-vp9", audio_codec="libopus",
        description="Ouvert et léger, idéal pour le web et les logiciels libres.",
        badge="WEB", family="lossy", default_crf=33,
        crf_min=20, crf_max=45,
        audio_bitrates=("64k", "96k", "128k", "160k", "192k"),
        default_audio_bitrate="128k",
        audio_copy_codecs=("opus", "vorbis")),
    VideoFormat(
        key="mkv", label="MKV · H.264", extension=".mkv", container="matroska",
        video_codec="libx264", audio_codec="aac",
        description="Conteneur souple : plusieurs pistes, sous-titres, chapitres.",
        badge="SOUPLE", family="lossy", default_crf=23,
        crf_min=16, crf_max=34,
        audio_bitrates=("96k", "128k", "192k", "256k", "320k"),
        default_audio_bitrate="192k",
        audio_copy_codecs=()),   # Matroska accepte à peu près tout
)

FORMAT_KEYS = tuple(fmt.key for fmt in FORMATS)
_BY_KEY = {fmt.key: fmt for fmt in FORMATS}
_BY_EXTENSION = {}
for _fmt in FORMATS:
    # MP4 et H.265 partagent « .mp4 » : le conteneur H.264 reste le choix par
    # défaut d'une extension seule.
    _BY_EXTENSION.setdefault(_fmt.extension, _fmt)
_BY_EXTENSION[".m4v"] = _BY_KEY["mp4"]
_BY_EXTENSION[".mov"] = _BY_KEY["mov"]
_BY_EXTENSION[".mka"] = _BY_KEY["mkv"]

#: Extensions reconnues comme vidéo (le flux vidéo est vérifié ensuite).
VIDEO_SUFFIXES = (
    ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".mts", ".3gp", ".ogv", ".mxf",
)


def get_format(key):
    return _BY_KEY[key]


def guess_format(path):
    if not path:
        return None
    import os

    fmt = _BY_EXTENSION.get(os.path.splitext(path)[1].lower())
    return fmt.key if fmt else None


def is_supported_input(path):
    import os

    return os.path.splitext(path)[1].lower() in VIDEO_SUFFIXES
