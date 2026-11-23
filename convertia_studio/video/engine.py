"""Moteur vidéo : analyse, vignette, estimation et encodage via ffmpeg."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field

from .. import ffmpeg_tools
from ..image.engine import human_size
from . import formats

SPEED_PRESETS = {
    # clé -> (libellé, preset x264/x265, cpu-used VP9)
    "fast": ("Rapide", "veryfast", 4),
    "balanced": ("Équilibré", "medium", 2),
    "quality": ("Qualité", "slow", 0),
}

class VideoError(Exception):
    """Erreur de traitement vidéo (message destiné à l'utilisateur)."""


@dataclass
class VideoInfo:
    path: str
    duration: float | None
    width: int
    height: int
    fps: float | None
    video_codec: str
    audio_codec: str | None
    audio_channels: int | None
    audio_bitrate: int | None
    bit_rate: int | None
    size: int
    container: str
    has_audio: bool
    rotation: int = 0
    details: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def title(self):
        return os.path.basename(self.path)

    @property
    def kind_label(self):
        return "Vidéo"

    @property
    def dimensions(self):
        return "%d × %d px" % (self.width, self.height)

    @property
    def fps_label(self):
        if not self.fps:
            return "i/s inconnues"
        return ("%.2f" % self.fps).rstrip("0").rstrip(".") + " i/s"

    @property
    def duration_label(self):
        return format_duration(self.duration)

    @property
    def size_label(self):
        return human_size(self.size)


@dataclass
class VideoSettings:
    """Réglages d'encodage vidéo."""

    crf: int = 23
    speed: str = "balanced"          # fast / balanced / quality
    width: int | None = None         # cadre cible exact
    height: int | None = None
    fill: bool = False               # remplir le cadre (rogner) au lieu de letterbox
    fps: int | None = None
    rotation: int = 0                # 0 / 90 / 180 / 270 (horaire)
    speed_factor: float = 1.0        # 0.5 / 1 / 1.5 / 2
    start: float = 0.0
    end: float | None = None
    audio_mode: str = "auto"         # auto / copy / none
    audio_bitrate: str | None = None

    def duration(self, source_duration):
        """Durée produite, en secondes (coupe et vitesse comprises)."""
        start = max(0.0, float(self.start or 0.0))
        end = source_duration if self.end is None else float(self.end)
        if source_duration:
            end = min(end, source_duration)
        length = max(0.0, end - start)
        factor = self.speed_factor or 1.0
        return length / factor


def format_duration(seconds):
    """« 2 min 14 s » ou « 45 s »."""
    if seconds is None:
        return "durée inconnue"
    seconds = max(0, round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d h %02d min" % (hours, minutes)
    if minutes:
        return "%d min %02d s" % (minutes, secs)
    return "%d s" % secs


def timecode(seconds):
    """« 01:23 » ou « 1:02:03 », pour les repères de lecture."""
    if seconds is None:
        return "—"
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


def parse_timecode(text, default=None):
    """Lit « 83 », « 1:23 » ou « 1:02:03 » et retourne des secondes."""
    if text is None:
        return default
    text = str(text).strip().replace(",", ".")
    if not text:
        return default
    parts = text.split(":")
    try:
        values = [float(part) for part in parts]
    except ValueError as error:
        raise VideoError("temps invalide : %r" % text) from error
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return values[0] * 60 + values[1]
    if len(values) == 3:
        return values[0] * 3600 + values[1] * 60 + values[2]
    raise VideoError("temps invalide : %r" % text)


def _fraction(text):
    if not text:
        return None
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            denominator = float(denominator)
            return float(numerator) / denominator if denominator else None
        return float(text)
    except (TypeError, ValueError):
        return None


def _rotation_of(stream):
    try:
        for side in stream.get("side_data_list", []) or []:
            if "rotation" in side:
                return int(round(float(side["rotation"])))
    except (TypeError, ValueError):
        pass
    try:
        return int(round(float(stream.get("tags", {}).get("rotate", 0))))
    except (TypeError, ValueError):
        return 0


def _probe_command():
    binary = ffmpeg_tools.ffprobe()
    if binary is None:
        raise VideoError("ffprobe est introuvable ou inutilisable : installe "
                         "ffmpeg (paquet ffmpeg) ou place un binaire valide "
                         "dans bin/.")
    return binary


def describe(path):
    """Analyse une vidéo (pistes, dimensions affichées, débit, durée)."""
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise VideoError("fichier introuvable : %s" % path)
    command = [_probe_command(), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoError("impossible d'analyser la vidéo : %s" % error) from error
    if completed.returncode != 0 or not completed.stdout:
        message = (completed.stderr or "").strip().splitlines()
        raise VideoError("ffprobe a échoué : %s"
                         % (message[-1] if message else "format inconnu"))
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise VideoError("réponse ffprobe illisible") from error

    streams = data.get("streams", [])
    video = next((stream for stream in streams
                  if stream.get("codec_type") == "video"
                  and not (stream.get("disposition") or {}).get("attached_pic")),
                 None)
    if video is None:
        raise VideoError("aucune piste vidéo dans ce fichier")
    audio = next((stream for stream in streams
                  if stream.get("codec_type") == "audio"), None)
    container = data.get("format", {})
    duration = _fraction(container.get("duration"))
    if duration is None:
        duration = _fraction(video.get("duration"))
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    rotation = _rotation_of(video)
    if abs(rotation) % 180 == 90:
        width, height = height, width
    fps = _fraction(video.get("avg_frame_rate")) or _fraction(
        video.get("r_frame_rate"))
    try:
        bit_rate = int(container.get("bit_rate") or video.get("bit_rate") or 0)
    except (TypeError, ValueError):
        bit_rate = 0
    try:
        size = int(container.get("size") or os.path.getsize(path))
    except (TypeError, ValueError):
        size = os.path.getsize(path)
    audio_bitrate = None
    if audio:
        try:
            audio_bitrate = int(audio.get("bit_rate") or 0) or None
        except (TypeError, ValueError):
            audio_bitrate = None

    details = [
        "%s · %d × %d px · %s"
        % (formats_label(container.get("format_name"), path), width, height,
           human_size(size)),
        "%s · %s%s" % (
            (video.get("codec_name") or "?").upper(), format_duration(duration),
            " · %s" % _bitrate_label(bit_rate) if bit_rate else ""),
    ]
    if audio:
        details.append("Audio %s · %d canal%s · %s"
                       % ((audio.get("codec_name") or "?").upper(),
                          audio.get("channels") or 0,
                          "x" if (audio.get("channels") or 0) > 1 else "",
                          _bitrate_label(audio_bitrate) if audio_bitrate
                          else "débit inconnu"))
    else:
        details.append("Aucune piste audio")

    warnings = []
    if duration is None:
        warnings.append("durée inconnue : la progression sera approximative")
    if rotation:
        warnings.append("vidéo tournée de %d° (appliquée à l'affichage)"
                        % rotation)
    if fps and fps < 1:
        warnings.append("fréquence d'images inhabituelle : %s" % fps)
    if not audio:
        warnings.append("aucune piste audio")

    return VideoInfo(
        path=path, duration=duration, width=width, height=height, fps=fps,
        video_codec=video.get("codec_name") or "?", audio_codec=(
            audio.get("codec_name") if audio else None),
        audio_channels=(audio.get("channels") if audio else None),
        audio_bitrate=audio_bitrate, bit_rate=bit_rate or None, size=size,
        container=formats_label(container.get("format_name"), path),
        has_audio=audio is not None, rotation=rotation, details=details,
        warnings=warnings)


def formats_label(name, path=None):
    """Nom lisible d'un conteneur (« mp4,mov » → « MP4 »)."""
    extension = os.path.splitext(path)[1].lower() if path else ""
    by_extension = {".mp4": "MP4", ".m4v": "M4V", ".mov": "MOV",
                    ".mkv": "MKV", ".webm": "WebM", ".avi": "AVI",
                    ".ts": "TS", ".m2ts": "M2TS", ".wmv": "WMV",
                    ".flv": "FLV", ".ogv": "OGV", ".3gp": "3GP"}
    if extension in by_extension:
        return by_extension[extension]
    if not name:
        return "?"
    first = str(name).split(",")[0]
    return {"matroska": "MKV", "webm": "WebM", "mov": "MOV",
            "mpegts": "TS", "avi": "AVI"}.get(first, first.upper())


def _bitrate_label(bits_per_second):
    if not bits_per_second:
        return "débit inconnu"
    return "%.0f kb/s" % (bits_per_second / 1000.0)


def is_video(path):
    """Vrai si le fichier contient une piste vidéo (analyse rapide)."""
    if not formats.is_supported_input(path):
        return False
    binary = ffmpeg_tools.ffprobe()
    if binary is None:
        return True
    try:
        completed = subprocess.run(
            [binary, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return True
    return bool((completed.stdout or "").strip())


_encoder_cache = None


def known_encoders():
    """Encodeurs vidéo disponibles dans le ffmpeg courant."""
    global _encoder_cache
    if _encoder_cache is not None:
        return _encoder_cache
    binary = ffmpeg_tools.ffmpeg()
    if binary is None:
        _encoder_cache = set()
        return _encoder_cache
    try:
        completed = subprocess.run([binary, "-hide_banner", "-encoders"],
                                   capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        _encoder_cache = set()
        return _encoder_cache
    names = set()
    for line in (completed.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    _encoder_cache = names
    return names


def format_supported(key):
    return formats.get_format(key).video_codec in known_encoders()


def audio_copy_supported(info, fmt):
    """Vrai si la piste audio source peut être copiée dans ce conteneur."""
    if not info.has_audio or not info.audio_codec:
        return False
    allowed = fmt.audio_copy_codecs
    return allowed is None or not allowed or info.audio_codec in allowed


def target_size(info, settings):
    """Dimensions exactes du cadre de sortie."""
    if settings.width or settings.height:
        width = int(settings.width) if settings.width else info.width
        height = int(settings.height) if settings.height else info.height
    else:
        width, height = info.width, info.height
        if int(settings.rotation or 0) % 180 == 90:
            width, height = height, width
    # ffmpeg préfère des dimensions paires pour les codecs 4:2:0
    return max(2, width - width % 2), max(2, height - height % 2)


def _video_filters(info, settings):
    chain = []
    rotation = int(settings.rotation or 0) % 360
    if rotation == 90:
        chain.append("transpose=clock")
    elif rotation == 180:
        chain.append("hflip,vflip")
    elif rotation == 270:
        chain.append("transpose=cclock")
    width, height = target_size(info, settings)
    if settings.width or settings.height:
        if settings.fill:
            chain.append(
                "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d"
                % (width, height, width, height))
        else:
            chain.append(
                "scale=%d:%d:force_original_aspect_ratio=decrease,"
                "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black"
                % (width, height, width, height))
    if settings.fps:
        chain.append("fps=%d" % int(settings.fps))
    if abs(float(settings.speed_factor or 1.0) - 1.0) > 1e-6:
        chain.append("setpts=PTS/%.4f" % float(settings.speed_factor))
    return chain


def _tempo_chain(factor):
    """Chaîne atempo valide (0,5 à 2 par étage)."""
    factor = float(factor)
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append("atempo=%.4f" % factor)
    return ",".join(parts)


def build_command(info, dest, format_key, settings):
    """Commande ffmpeg complète (utile aux tests et au journal)."""
    fmt = formats.get_format(format_key)
    binary = ffmpeg_tools.require_ffmpeg()
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    start = max(0.0, float(settings.start or 0.0))
    if start:
        command += ["-ss", "%.3f" % start]
    command += ["-i", info.path]
    produced = settings.duration(info.duration)
    if settings.end is not None or start:
        command += ["-t", "%.3f" % max(0.05, produced)]

    command += ["-map", "0:v:0"]
    if settings.audio_mode != "none" and info.has_audio:
        command += ["-map", "0:a:0?"]
    filters = _video_filters(info, settings)
    if filters:
        command += ["-vf", ",".join(filters)]
    command += ["-c:v", fmt.video_codec]

    if fmt.video_codec == "libvpx-vp9":
        _, _, cpu_used = SPEED_PRESETS.get(settings.speed,
                                          SPEED_PRESETS["balanced"])
        command += ["-b:v", "0", "-crf", str(settings.crf),
                    "-deadline", "good", "-cpu-used", str(cpu_used),
                    "-row-mt", "1"]
    else:
        _, preset, _ = SPEED_PRESETS.get(settings.speed,
                                         SPEED_PRESETS["balanced"])
        command += ["-preset", preset, "-crf", str(settings.crf),
                    "-pix_fmt", "yuv420p"]
        if fmt.video_codec == "libx265":
            command += ["-tag:v", "hvc1"]

    if settings.audio_mode == "none" or not info.has_audio:
        command += ["-an"]
    elif settings.audio_mode == "copy" and audio_copy_supported(info, fmt) \
            and abs(float(settings.speed_factor or 1.0) - 1.0) < 1e-6:
        command += ["-c:a", "copy"]
    else:
        command += ["-c:a", fmt.audio_codec,
                    "-b:a", settings.audio_bitrate or fmt.default_audio_bitrate]
        if abs(float(settings.speed_factor or 1.0) - 1.0) > 1e-6:
            command += ["-filter:a", _tempo_chain(settings.speed_factor)]

    if fmt.container == "mp4":
        command += ["-movflags", "+faststart"]
    command += ["-f", fmt.container, "-progress", "pipe:1", "-nostats", dest]
    return command


def estimate_size(info, format_key, settings):
    """Estimation heuristique du poids final (octets)."""
    fmt = formats.get_format(format_key)
    width, height = target_size(info, settings)
    fps = settings.fps or info.fps or 25.0
    duration = settings.duration(info.duration) or 0.0
    bits_per_pixel = {"libx264": 0.075, "libx265": 0.05,
                      "libvpx-vp9": 0.055}.get(fmt.video_codec, 0.07)
    default = max(1, fmt.default_crf)
    factor = 2.0 ** ((default - settings.crf) / 6.0)
    video_bps = max(1.0, width * height * fps * bits_per_pixel * factor)
    audio_bps = 0.0
    if settings.audio_mode != "none" and info.has_audio:
        if settings.audio_mode == "copy":
            audio_bps = float(info.audio_bitrate or 128000)
        else:
            bitrate = (settings.audio_bitrate
                       or fmt.default_audio_bitrate).rstrip("k")
            try:
                audio_bps = float(bitrate) * 1000.0
            except ValueError:
                audio_bps = 128000.0
    return int((video_bps + audio_bps) * duration / 8.0)


def thumbnail(path, seconds=0.0, max_side=960):
    """Image PNG extraite à ``seconds`` (octets)."""
    binary = ffmpeg_tools.require_ffmpeg()
    for position in (max(0.0, float(seconds or 0.0)), 0.0):
        command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-ss", "%.3f" % position, "-i", path, "-frames:v", "1",
                   "-vf", "scale='min(%d,iw)':-2" % int(max_side),
                   "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=90)
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0 and completed.stdout:
            return completed.stdout
        if position == 0.0:
            break
    raise VideoError("impossible d'extraire une image de cette vidéo")


def grab_frame(path, seconds, dest):
    """Enregistre une image pleine résolution à ``seconds``."""
    binary = ffmpeg_tools.require_ffmpeg()
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-ss", "%.3f" % max(0.0, float(seconds or 0.0)),
               "-i", path, "-frames:v", "1", dest]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise VideoError("extraction impossible : %s" % error) from error
    if completed.returncode != 0 or not os.path.isfile(dest):
        raise VideoError("extraction impossible : %s"
                         % ((completed.stderr or "").strip() or "échec ffmpeg"))
    return dest


def convert(source, dest, format_key, settings, progress=None):
    """Encode la vidéo et retourne un compte rendu."""
    source = os.fspath(source)
    dest = os.fspath(dest)
    if not os.path.isfile(source):
        raise VideoError("fichier introuvable : %s" % source)
    if os.path.abspath(source) == os.path.abspath(dest):
        raise VideoError("le fichier de sortie ne peut pas être la source")
    directory = os.path.dirname(os.path.abspath(dest))
    if directory and not os.path.isdir(directory):
        raise VideoError("dossier de sortie introuvable : %s" % directory)
    fmt = formats.get_format(format_key)

    _report(progress, 0.02, "analyse de la vidéo…")
    info = describe(source)
    produced = settings.duration(info.duration)
    width, height = target_size(info, settings)
    command = build_command(info, dest, format_key, settings)
    started = time.time()
    _report(progress, 0.05, "encodage %s…" % fmt.label)

    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    total = max(0.1, produced)
    speed_label = ""
    for raw in process.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("speed="):
            value = line.split("=", 1)[1].strip()
            if value and value != "N/A":
                speed_label = " · ×%s" % value.rstrip("x")
        elif line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                done = int(line.split("=", 1)[1]) / 1_000_000.0
            except ValueError:
                continue
            if done >= 0:
                _report(progress, min(0.97, 0.05 + 0.92 * done / total),
                        "encodage %s%s" % (fmt.label, speed_label))
    process.stdout.close()
    errors = process.stderr.read().decode("utf-8", "replace").strip()
    process.stderr.close()
    code = process.wait()
    if code != 0:
        tail = "\n".join(errors.splitlines()[-6:]) or "(sans message)"
        raise VideoError("ffmpeg a échoué (code %d) :\n%s" % (code, tail))
    if not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        raise VideoError("aucun fichier produit (ffmpeg n'a rien écrit)")

    _report(progress, 1.0, "terminé")
    size = os.path.getsize(dest)
    source_size = info.size
    return {
        "path": dest,
        "format": fmt,
        "size": size,
        "source_size": source_size,
        "width": width,
        "height": height,
        "duration": produced,
        "elapsed": time.time() - started,
        "ratio": (size / source_size) if source_size else None,
        "warnings": list(info.warnings),
    }


def default_output_path(source, format_key, directory=None):
    fmt = formats.get_format(format_key)
    base, _extension = os.path.splitext(os.path.basename(source))
    directory = directory or os.path.dirname(os.path.abspath(source))
    candidate = os.path.join(directory, base + fmt.extension)
    if os.path.abspath(candidate) == os.path.abspath(source):
        candidate = os.path.join(directory, base + "-converti" + fmt.extension)
    return candidate


def _report(progress, fraction, message):
    if progress:
        progress(max(0.0, min(1.0, fraction)), message)
