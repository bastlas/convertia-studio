"""Registre des formats d'image gérés par Convertia Studio.

Chaque format décrit ce que l'interface affiche (libellé, extension, badge) et
ce que le moteur d'encodage doit savoir (qualité, transparence, format Pillow).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageFormat:
    """Un format de sortie image."""

    key: str                 # clé interne ("jpeg")
    label: str               # nom affiché ("JPEG")
    extension: str           # ".jpg"
    description: str
    family: str              # "lossy", "lossless" ou "raw"
    badge: str               # pastille affichée sur la carte
    supports_quality: bool   # curseur de compression utile
    supports_alpha: bool     # transparence conservable
    pillow_format: str       # nom de format attendu par Pillow
    default_quality: int = 85


#: Ordre d'affichage dans l'interface.
FORMATS = (
    ImageFormat(
        key="jpeg", label="JPEG", extension=".jpg",
        description="Photo compressée, lue partout, poids minimal.",
        family="lossy", badge="PHOTO", supports_quality=True,
        supports_alpha=False, pillow_format="JPEG", default_quality=85),
    ImageFormat(
        key="webp", label="WebP", extension=".webp",
        description="Moderne et compact, avec transparence possible.",
        family="lossy", badge="WEB", supports_quality=True,
        supports_alpha=True, pillow_format="WEBP", default_quality=80),
    ImageFormat(
        key="heic", label="HEIC", extension=".heic",
        description="Photo Apple compacte, transparence et qualité réglable.",
        family="lossy", badge="APPLE", supports_quality=True,
        supports_alpha=True, pillow_format="HEIF", default_quality=80),
    ImageFormat(
        key="avif", label="AVIF", extension=".avif",
        description="Le plus compact à qualité égale (encodage plus lent).",
        family="lossy", badge="NEXT", supports_quality=True,
        supports_alpha=True, pillow_format="AVIF", default_quality=62),
    ImageFormat(
        key="png", label="PNG", extension=".png",
        description="Sans perte, transparence et captures d'écran.",
        family="lossless", badge="SANS PERTE", supports_quality=False,
        supports_alpha=True, pillow_format="PNG"),
    ImageFormat(
        key="tiff", label="TIFF", extension=".tiff",
        description="Sans perte, pour l'impression et l'archivage.",
        family="lossless", badge="ARCHIVE", supports_quality=False,
        supports_alpha=True, pillow_format="TIFF"),
    ImageFormat(
        key="bmp", label="BMP", extension=".bmp",
        description="Brut Windows, sans compression ni transparence.",
        family="raw", badge="BRUT", supports_quality=False,
        supports_alpha=False, pillow_format="BMP"),
)

FORMAT_KEYS = tuple(fmt.key for fmt in FORMATS)
_BY_KEY = {fmt.key: fmt for fmt in FORMATS}
_BY_EXTENSION = {}
for _fmt in FORMATS:
    _BY_EXTENSION[_fmt.extension] = _fmt
_BY_EXTENSION[".jpeg"] = _BY_KEY["jpeg"]
_BY_EXTENSION[".tif"] = _BY_KEY["tiff"]

#: Fichiers RAW d'appareil photo (décodés par LibRaw / rawpy).
RAW_SUFFIXES = (
    ".raw", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2",
    ".raf", ".srw", ".pef", ".rwl", ".3fr", ".erf", ".kdc", ".mrw",
    ".x3f", ".sr2", ".srf",
)

#: Extensions acceptées en entrée (Pillow en décode au moins le premier cadre).
INPUT_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".webp", ".avif",
    ".heic", ".heif", ".tif", ".tiff", ".bmp", ".gif", ".ico",
    ".tga", ".ppm", ".pgm",
) + RAW_SUFFIXES


def get_format(key):
    """Format de sortie correspondant à ``key`` (lève ``KeyError`` sinon)."""
    return _BY_KEY[key]


def guess_format(path):
    """Format déduit d'une extension, ou ``None``."""
    if not path:
        return None
    import os

    fmt = _BY_EXTENSION.get(os.path.splitext(path)[1].lower())
    return fmt.key if fmt else None


def is_supported(path):
    """Vrai si l'extension est une image connue."""
    import os

    return os.path.splitext(path)[1].lower() in INPUT_SUFFIXES


def label_for_pillow(name):
    """Nom lisible d'un format Pillow (« JPEG » pour ``JPEG``)."""
    return {
        "MPO": "JPEG", "JPG": "JPEG", "MPEG": "MPEG",
        "HEIF": "HEIC", "HEIC": "HEIC",
    }.get((name or "").upper(), (name or "?").upper()[:8])
