"""Orchestration : décrire une source puis la convertir vers un format choisi.

Deux familles de sources sont gérées :

* les projets Audacity (``.aup3``, ``.aup4`` et leurs variantes ``*unsaved``),
  décodés et mixés par :mod:`convertia_studio.audio.project` ;
* tous les autres fichiers audio, confiés à ffmpeg.

Le module est volontairement indépendant de l'interface : la CLI et la fenêtre
Qt utilisent les mêmes fonctions.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from . import SUPPORTED_PROJECT_SUFFIXES, ffmpeg_tools
from .audio import formats
from .audio.project import Aup4Error, Project, format_duration

#: Extensions de fichiers audio « classiques » acceptées en entrée
AUDIO_SUFFIXES = (
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".aiff",
    ".aif", ".wma", ".alac", ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
    ".mp2", ".ac3", ".wv", ".mka", ".caf",
)

PROJECT_LABEL = "projet Audacity"


class ConvertError(Exception):
    """Erreur de conversion (message destiné à l'utilisateur)."""


@dataclass
class SourceInfo:
    """Ce que l'on sait d'un fichier avant conversion."""

    path: str
    kind: str                      # "audacity" ou "audio"
    title: str
    duration: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    codec: str | None = None
    details: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def duration_label(self):
        return format_duration(self.duration) if self.duration else "inconnue"

    @property
    def kind_label(self):
        return "Projet Audacity" if self.kind == "audacity" else "Fichier audio"


def is_project(path):
    """Vrai si le fichier est un projet Audacity (par son extension)."""
    return os.path.splitext(path)[1].lower() in SUPPORTED_PROJECT_SUFFIXES


def describe(path):
    """Analyse ``path`` et retourne un :class:`SourceInfo`."""
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise ConvertError("fichier introuvable : %s" % path)
    if is_project(path):
        return _describe_project(path)
    return _describe_audio(path)


def _describe_project(path):
    try:
        project = Project(path)
    except Aup4Error as error:
        raise ConvertError(str(error)) from error
    try:
        duration = project.duration()
        tracks = len(project.tracks)
        clips = sum(track.clip_count for track in project.tracks)
        details = [
            "Audacity %s · document « %s »" % (
                project.audacity_version or "?", project.doc_source),
            "%s · %d piste%s · %d clip%s" % (
                format_duration(duration), tracks, _plural(tracks),
                clips, _plural(clips)),
            "Fréquence %g Hz · %d bloc%s audio" % (
                project.rate, project.block_count, _plural(project.block_count)),
        ]
        for index, track in enumerate(project.tracks, 1):
            flags = []
            if track.mute:
                flags.append("muet")
            if track.solo:
                flags.append("solo")
            details.append("  %d. %s — %s, gain %.2f%s" % (
                index, track.name or "piste", track.width, track.gain,
                " [%s]" % ", ".join(flags) if flags else ""))
        channels = 2 if any(t.width == "stereo" for t in project.tracks) else 1
        return SourceInfo(
            path=path, kind="audacity", title=os.path.basename(path),
            duration=duration, sample_rate=project.rate,
            channels=channels, details=details,
            warnings=list(project.warnings))
    finally:
        project.close()


def _describe_audio(path):
    info = ffmpeg_tools.probe(path)
    details = []
    if info["codec"]:
        details.append("Codec %s" % info["codec"])
    if info["sample_rate"]:
        details.append("Fréquence %s Hz" % info["sample_rate"])
    if info["channels"]:
        details.append("%d canal%s" % (info["channels"], _plural(info["channels"])))
    if info["format"]:
        details.append("Conteneur %s" % info["format"].split(",")[0])
    warnings = []
    extension = os.path.splitext(path)[1].lower()
    if extension and extension not in AUDIO_SUFFIXES:
        warnings.append("extension %s inconnue : ffmpeg tentera quand même la "
                        "conversion" % extension)
    if info["audio_streams"] == 0:
        warnings.append("aucune piste audio détectée dans ce fichier")
    if ffmpeg_tools.ffmpeg() is None:
        warnings.append("ffmpeg est introuvable : la conversion est impossible")
    return SourceInfo(
        path=path, kind="audio", title=os.path.basename(path),
        duration=info["duration"], sample_rate=info["sample_rate"],
        channels=info["channels"], codec=info["codec"], details=details,
        warnings=warnings)


def default_output_path(source, format_key, directory=None):
    """Nom de sortie proposé : ``<source>.<extension>``."""
    fmt = formats.get_format(format_key)
    base, _ = os.path.splitext(os.path.basename(source))
    directory = directory or os.path.dirname(os.path.abspath(source))
    return os.path.join(directory, base + fmt.extension)


def convert(source, dest, format_key, options=None, progress=None):
    """Convertit ``source`` vers ``dest``.

    ``progress`` est appelé avec ``(fraction, message)``.  Retourne un
    dictionnaire décrivant le fichier produit.
    """
    options = dict(options or {})
    fmt = formats.get_format(format_key)
    started = time.time()
    if os.path.abspath(source) == os.path.abspath(dest):
        raise ConvertError("le fichier de sortie ne peut pas être la source")

    directory = os.path.dirname(os.path.abspath(dest))
    if directory and not os.path.isdir(directory):
        raise ConvertError("dossier de sortie introuvable : %s" % directory)

    info = describe(source)
    if progress:
        progress(0.0, "préparation…")

    if info.kind == "audacity":
        _convert_project(source, dest, fmt, options, progress)
    else:
        options.setdefault("duration", info.duration)
        _report(progress, 0.05, "conversion %s → %s" % (info.kind_label, fmt.label))
        try:
            formats.encode_file(dest, source, format_key, options,
                                on_progress=lambda f, m: _report(progress, f, m))
        except formats.FormatError as error:
            raise ConvertError(str(error)) from error

    if not os.path.isfile(dest):
        raise ConvertError("aucun fichier produit (ffmpeg n'a rien écrit)")
    size = os.path.getsize(dest)
    if progress:
        progress(1.0, "terminé")
    return {
        "path": dest,
        "format": fmt,
        "size": size,
        "duration": info.duration,
        "elapsed": time.time() - started,
        "warnings": list(info.warnings),
    }


def _convert_project(source, dest, fmt, options, progress):
    try:
        project = Project(source)
    except Aup4Error as error:
        raise ConvertError(str(error)) from error
    try:
        if progress:
            progress(0.02, "mixage du projet…")
        samples, rate = project.render(
            progress=lambda f, m: _report(progress, 0.02 + f * 0.55, m),
            mono=bool(options.get("mono")))
        peak = float(abs(samples).max()) if samples.size else 0.0
        if peak <= 0.0:
            raise ConvertError("le projet ne contient aucun son audible")
        if peak > 1.0 and fmt.family != "lossless" and not (
                fmt.family == "pcm" and str(options.get("depth")) == "32f"):
            _report(progress, 0.6,
                    "crête à %.2f : écrêtage à l'encodage" % peak)
        try:
            formats.encode_samples(
                dest, samples, rate, fmt.key, options,
                on_progress=lambda f, m: _report(progress, 0.6 + f * 0.4, m))
        except formats.FormatError as error:
            raise ConvertError(str(error)) from error
    finally:
        project.close()


def _report(progress, fraction, message):
    if progress:
        progress(max(0.0, min(1.0, fraction)), message)


def _plural(count):
    return "s" if abs(count) > 1 else ""
