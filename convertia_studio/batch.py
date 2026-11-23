"""Traitement par lot d'un dossier : analyse, plan et conversion.

Le module est indépendant de Qt.  Il classe les fichiers d'un dossier par
famille (image, vidéo, audio), construit les chemins de sortie et délègue
chaque conversion au moteur correspondant.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import SUPPORTED_PROJECT_SUFFIXES, jobs
from .audio import formats as audio_formats
from .image import engine as image_engine
from .image import formats as image_formats
from .video import engine as video_engine
from .video import formats as video_formats

KINDS = ("image", "video", "audio")

KIND_LABELS = {
    "image": "Images",
    "video": "Vidéos",
    "audio": "Audio",
}

KIND_GLYPHS = {
    "image": "image",
    "video": "video",
    "audio": "audio",
}

DEFAULT_OUTPUT_NAME = "converti"


@dataclass
class BatchTemplate:
    """Réglages d'une famille, repris de la page correspondante."""

    kind: str
    format_key: str
    summary: str
    settings: object = None


@dataclass
class BatchEntry:
    """Une conversion à effectuer."""

    kind: str
    source: str
    destination: str
    format_key: str

    @property
    def name(self):
        return os.path.basename(self.source)


@dataclass
class ScanResult:
    files: dict = field(default_factory=dict)
    ignored: int = 0
    size: int = 0

    def count(self, kind):
        return len(self.files.get(kind, ()))

    @property
    def total(self):
        return sum(self.count(kind) for kind in KINDS)


def classify(path):
    """Famille d'un fichier d'après son extension, ou ``None``."""
    extension = os.path.splitext(path)[1].lower()
    if extension in image_formats.INPUT_SUFFIXES:
        return "image"
    if extension in video_formats.VIDEO_SUFFIXES:
        return "video"
    if extension in SUPPORTED_PROJECT_SUFFIXES or extension in jobs.AUDIO_SUFFIXES:
        return "audio"
    return None


def format_extension(kind, format_key):
    if kind == "image":
        return image_formats.get_format(format_key).extension
    if kind == "video":
        return video_formats.get_format(format_key).extension
    return audio_formats.get_format(format_key).extension


def scan(folder, recursive=False, exclude=()):
    """Classe les fichiers du dossier (sans lire leur contenu)."""
    folder = os.path.abspath(folder)
    excluded = [os.path.abspath(path) for path in exclude if path]
    files = {kind: [] for kind in KINDS}
    ignored = [0]
    size = [0]

    def is_excluded(path):
        absolute = os.path.abspath(path)
        return any(absolute == root or absolute.startswith(root + os.sep)
                   for root in excluded)

    def visit(directory):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive and not is_excluded(entry.path):
                        visit(entry.path)
                    continue
                if not entry.is_file():
                    continue
                if is_excluded(entry.path):
                    continue
                kind = classify(entry.path)
                if kind is None:
                    ignored[0] += 1
                    continue
                files[kind].append(entry.path)
                size[0] += entry.stat().st_size
            except OSError:
                continue

    visit(folder)
    for kind in KINDS:
        files[kind].sort(key=lambda path: path.casefold())
    return ScanResult(files=files, ignored=ignored[0], size=size[0])


def build_entries(scan_result, selected, formats_by_kind, source_root,
                  output_root, recursive=False):
    """Construit la liste des conversions (noms uniques, sans écraser)."""
    source_root = os.path.abspath(source_root)
    output_root = os.path.abspath(output_root)
    entries = []
    planned = set()

    for kind in KINDS:
        if kind not in selected:
            continue
        format_key = formats_by_kind.get(kind)
        if not format_key:
            continue
        extension = format_extension(kind, format_key)
        for source in scan_result.files.get(kind, ()):
            if recursive:
                relative = os.path.relpath(source, source_root)
            else:
                relative = os.path.basename(source)
            relative_dir = os.path.dirname(relative)
            stem = os.path.splitext(os.path.basename(relative))[0]
            destination = os.path.join(output_root, relative_dir,
                                       stem + extension)
            if (os.path.abspath(destination) == os.path.abspath(source)
                    or destination in planned or os.path.exists(destination)):
                counter = 2
                while True:
                    candidate = os.path.join(
                        output_root, relative_dir,
                        "%s-%d%s" % (stem, counter, extension))
                    if (candidate not in planned
                            and os.path.abspath(candidate)
                            != os.path.abspath(source)
                            and not os.path.exists(candidate)):
                        destination = candidate
                        break
                    counter += 1
            planned.add(destination)
            entries.append(BatchEntry(kind=kind, source=source,
                                      destination=destination,
                                      format_key=format_key))
    return entries


def convert_entry(entry, settings, progress=None):
    """Convertit une entrée vers son moteur (image, vidéo ou audio)."""
    directory = os.path.dirname(entry.destination)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if entry.kind == "image":
        return image_engine.convert(entry.source, entry.destination,
                                    entry.format_key, settings,
                                    progress=progress)
    if entry.kind == "video":
        return video_engine.convert(entry.source, entry.destination,
                                    entry.format_key, settings,
                                    progress=progress)
    return jobs.convert(entry.source, entry.destination, entry.format_key,
                        settings, progress=progress)


def size_label(size):
    """Taille lisible (« 3,4 Mio »)."""
    from .image.engine import human_size

    return human_size(size)


def category_size(scan_result, kind):
    return sum(os.path.getsize(path) for path in scan_result.files.get(kind, ()))


def destination_directory(folder):
    return os.path.join(os.path.abspath(folder), DEFAULT_OUTPUT_NAME)
