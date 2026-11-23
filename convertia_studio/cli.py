"""Interface en ligne de commande de Convertia Studio.

    python3 -m convertia_studio projet.aup4                  # → projet.mp4
    python3 -m convertia_studio projet.aup4 -f flac
    python3 -m convertia_studio chant.mp3 -f opus -b 128k
    python3 -m convertia_studio --list-formats
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from . import APP_NAME, APP_TAGLINE, __version__, ffmpeg_tools
from . import jobs
from .audio import formats
from .image import engine as image_engine
from .image import formats as image_formats
from .video import engine as video_engine
from .video import formats as video_formats


def build_parser():
    parser = argparse.ArgumentParser(
        prog="convertia_studio",
        description="%s — %s" % (APP_NAME, APP_TAGLINE),
        epilog="Sources acceptées : projets Audacity (.aup3/.aup4, y compris "
               "*unsaved), fichiers audio courants (wav, mp3, m4a, flac…), "
               "images (png, jpg, webp, avif, tiff, bmp) et vidéos (mp4, "
               "mkv, webm, mov, avi…) avec --video.")
    parser.add_argument("source", nargs="?",
                        help="fichier à convertir (projet Audacity, audio ou image)")
    parser.add_argument("-o", "--output", metavar="FICHIER",
                        help="fichier de sortie (défaut : <source>.<format>)")
    parser.add_argument("-f", "--format", metavar="FORMAT",
                        help="format de sortie audio (%s) ou image (%s)"
                             % (", ".join(formats.FORMAT_KEYS),
                                ", ".join(image_formats.FORMAT_KEYS)))
    parser.add_argument("-b", "--bitrate", metavar="DÉBIT",
                        help="débit pour les formats audio compressés (ex. 192k)")
    parser.add_argument("--depth", default=None,
                        choices=[value for _, value in formats.DEPTH_CHOICES],
                        help="profondeur PCM pour wav/aiff (16, 24 ou 32f)")
    parser.add_argument("--sample-rate", type=int, metavar="HZ",
                        help="fréquence de sortie (par défaut celle de la source)")
    parser.add_argument("--mono", action="store_true", help="mixe en un canal")
    parser.add_argument("-Q", "--quality", type=int, metavar="1-100",
                        help="qualité des images compressées (jpeg, webp, avif)")
    parser.add_argument("--resize", metavar="LxH",
                        help="redimensionne l'image : 1920x1080, 1280x ou x720 "
                             "ou 50%%")
    parser.add_argument("--crop", metavar="X,Y,L,H",
                        help="recadre l'image (position et taille en pixels)")
    parser.add_argument("--rotate", type=float, default=0.0, metavar="DEGRÉS",
                        help="rotation horaire de l'image")
    parser.add_argument("--flip-h", action="store_true",
                        help="miroir horizontal de l'image")
    parser.add_argument("--flip-v", action="store_true",
                        help="miroir vertical de l'image")
    parser.add_argument("--video", action="store_true",
                        help="traite la source comme une vidéo (sinon un MP4 "
                             "est lu comme un fichier audio)")
    parser.add_argument("--crf", type=int, metavar="16-45",
                        help="qualité vidéo (plus bas = meilleur)")
    parser.add_argument("--video-speed", choices=tuple(video_engine.SPEED_PRESETS),
                        help="vitesse d'encodage vidéo (fast, balanced, quality)")
    parser.add_argument("--start", metavar="TEMPS",
                        help="début de l'extrait (secondes ou mm:ss)")
    parser.add_argument("--end", metavar="TEMPS",
                        help="fin de l'extrait (secondes ou mm:ss)")
    parser.add_argument("--fps", type=int, metavar="IMAGES/S",
                        help="fréquence d'images de sortie")
    parser.add_argument("--speed", type=float, metavar="FACTEUR",
                        help="vitesse de lecture (0.5, 1.5, 2…)")
    parser.add_argument("--fill", action="store_true",
                        help="remplir le cadre vidéo en rognant les bords")
    parser.add_argument("--no-audio", action="store_true",
                        help="supprime la piste audio vidéo")
    parser.add_argument("--audio-copy", action="store_true",
                        help="copie la piste audio sans réencodage")
    parser.add_argument("--audio-bitrate", metavar="DÉBIT",
                        help="débit audio vidéo (ex. 192k)")
    parser.add_argument("--info", action="store_true",
                        help="affiche les informations sur la source et s'arrête")
    parser.add_argument("--list-formats", action="store_true",
                        help="liste les formats audio de sortie disponibles")
    parser.add_argument("--list-image-formats", action="store_true",
                        help="liste les formats d'image de sortie disponibles")
    parser.add_argument("--list-video-formats", action="store_true",
                        help="liste les formats vidéo de sortie disponibles")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="n'affiche pas la progression")
    parser.add_argument("--force", action="store_true",
                        help="écrase la sortie si elle existe déjà")
    parser.add_argument("--version", action="version",
                        version="%s %s" % (APP_NAME, __version__))
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_formats:
        _print_formats()
        return 0
    if args.list_image_formats:
        _print_image_formats()
        return 0
    if args.list_video_formats:
        _print_video_formats()
        return 0
    if not args.source:
        parser.print_help()
        return 2

    if args.video:
        return _convert_video(args)

    if image_engine.is_image(args.source):
        return _convert_image(args)

    if args.format:
        if args.format not in formats.FORMAT_KEYS:
            print("erreur : format inconnu %r (voir --list-formats)" % args.format,
                  file=sys.stderr)
            return 2
        format_key = args.format
    else:
        format_key = formats.guess_format(args.output) if args.output else "mp4"

    fmt = formats.get_format(format_key)
    options = {
        "bitrate": args.bitrate or fmt.default_bitrate,
        "depth": args.depth or "24",
        "sample_rate": args.sample_rate,
        "mono": args.mono,
    }

    try:
        info = jobs.describe(args.source)
    except jobs.ConvertError as error:
        print("erreur : %s" % error, file=sys.stderr)
        return 1

    print("%s · %s · %s · %s" % (info.kind_label, info.title,
                                 info.duration_label,
                                 (fmt.label)))
    for line in info.details:
        print("  " + line)
    _print_warnings(info.warnings)

    if args.info:
        return 0

    output = args.output or jobs.default_output_path(info.path, format_key)
    if os.path.exists(output) and not args.force:
        print("erreur : %s existe déjà (utiliser --force pour l'écraser)" % output,
              file=sys.stderr)
        return 2

    try:
        result = jobs.convert(args.source, output, format_key, options,
                              progress=_progress_printer(args.quiet))
    except jobs.ConvertError as error:
        print("\nerreur : %s" % error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompu", file=sys.stderr)
        return 130

    _print_warnings(result["warnings"])
    print("OK : %s (%s · %s · %.1f Mio · %.1f s)"
          % (result["path"], result["format"].label,
             jobs.format_duration(result["duration"] or 0),
             result["size"] / (1024 * 1024), result["elapsed"]))
    return 0


def _convert_image(args):
    """Parcourt le mode image de la ligne de commande."""
    try:
        info = image_engine.describe(args.source)
    except image_engine.ImageError as error:
        print("erreur : %s" % error, file=sys.stderr)
        return 1

    print("Image · %s" % info.title)
    for line in info.details:
        print("  " + line)
    _print_warnings(info.warnings)
    if args.info:
        return 0

    format_key = args.format or image_formats.guess_format(args.output) or "jpeg"
    if format_key not in image_formats.FORMAT_KEYS:
        print("erreur : format image inconnu %r (voir --list-image-formats)"
              % format_key, file=sys.stderr)
        return 2
    image_format = image_formats.get_format(format_key)
    if not image_engine.output_supported(format_key):
        print("erreur : %s n'est pas disponible avec cette version de Pillow"
              % image_format.label, file=sys.stderr)
        return 2

    try:
        crop = _parse_crop(args.crop)
        width, height = _parse_resize(args.resize, info, crop)
    except ValueError as error:
        print("erreur : %s" % error, file=sys.stderr)
        return 2

    quality = image_format.default_quality if args.quality is None else args.quality
    if not 1 <= quality <= 100:
        print("erreur : la qualité doit être comprise entre 1 et 100",
              file=sys.stderr)
        return 2

    settings = image_engine.ImageSettings(
        crop=crop, width=width, height=height, angle=args.rotate,
        flip_h=args.flip_h, flip_v=args.flip_v, quality=quality)
    output = args.output or image_engine.default_output_path(
        info.path, format_key)
    if os.path.exists(output) and not args.force:
        print("erreur : %s existe déjà (utiliser --force pour l'écraser)"
              % output, file=sys.stderr)
        return 2

    try:
        result = image_engine.convert(
            info.path, output, format_key, settings,
            progress=_progress_printer(args.quiet))
    except image_engine.ImageError as error:
        print("\nerreur : %s" % error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompu", file=sys.stderr)
        return 130

    _print_warnings(result["warnings"])
    delta = " · " + image_engine.delta_label(result["source_size"],
                                             result["size"])
    print("OK : %s (%s · %d × %d px · %s%s · %.2f s)"
          % (result["path"], result["format"].label, result["width"],
             result["height"], image_engine.human_size(result["size"]), delta,
             result["elapsed"]))
    return 0


def _parse_crop(text):
    if not text:
        return None
    parts = [part.strip() for part in text.replace(";", ",").split(",")]
    if len(parts) != 4:
        raise ValueError("recadrage attendu sous la forme X,Y,LARGEUR,HAUTEUR")
    try:
        x, y, width, height = (int(float(part)) for part in parts)
    except ValueError as error:
        raise ValueError("recadrage invalide : %r" % text) from error
    if width <= 0 or height <= 0:
        raise ValueError("la largeur et la hauteur du recadrage doivent être "
                         "positives")
    return max(0, x), max(0, y), width, height


def _parse_resize(text, info, crop):
    if not text:
        return None, None
    text = text.strip()
    base_width, base_height = info.width, info.height
    if crop:
        base_width, base_height = crop[2], crop[3]
    if text.endswith("%"):
        try:
            factor = float(text[:-1])
        except ValueError as error:
            raise ValueError("pourcentage invalide : %r" % text) from error
        if factor <= 0:
            raise ValueError("le pourcentage doit être positif")
        return (max(1, round(base_width * factor / 100.0)),
                max(1, round(base_height * factor / 100.0)))
    match = re.fullmatch(r"(\d*)\s*[x×]\s*(\d*)", text)
    if match and (match.group(1) or match.group(2)):
        width = int(match.group(1)) if match.group(1) else None
        height = int(match.group(2)) if match.group(2) else None
        if (width is not None and width <= 0) or (
                height is not None and height <= 0):
            raise ValueError("les dimensions doivent être positives")
        return width, height
    if text.isdigit() and int(text) > 0:
        return int(text), None
    raise ValueError("redimensionnement invalide : %r (ex. 1920x1080, 50%%)"
                     % text)


def _convert_video(args):
    """Convertit une vidéo (mode --video)."""
    try:
        info = video_engine.describe(args.source)
    except video_engine.VideoError as error:
        print("erreur : %s" % error, file=sys.stderr)
        return 1

    print("Vidéo · %s" % info.title)
    for line in info.details:
        print("  " + line)
    _print_warnings(info.warnings)
    if args.info:
        return 0

    format_key = args.format or video_formats.guess_format(args.output) or "mp4"
    if format_key not in video_formats.FORMAT_KEYS:
        print("erreur : format vidéo inconnu %r (voir --list-video-formats)"
              % format_key, file=sys.stderr)
        return 2
    video_format = video_formats.get_format(format_key)
    if not video_engine.format_supported(format_key):
        print("erreur : l'encodeur %s est absent de ffmpeg"
              % video_format.video_codec, file=sys.stderr)
        return 2

    try:
        start = video_engine.parse_timecode(args.start, 0.0) or 0.0
        end = video_engine.parse_timecode(args.end, None)
        width, height = _parse_resize(args.resize, info, None)
    except (video_engine.VideoError, ValueError) as error:
        print("erreur : %s" % error, file=sys.stderr)
        return 2
    if info.duration and start >= info.duration:
        print("erreur : le début de l'extrait dépasse la durée (%.1f s)"
              % info.duration, file=sys.stderr)
        return 2
    if end is not None and end <= start:
        print("erreur : la fin de l'extrait doit suivre le début", file=sys.stderr)
        return 2
    if width and not height and info.width:
        height = max(2, round(width * info.height / info.width))
    elif height and not width and info.height:
        width = max(2, round(height * info.width / info.height))
    if args.rotate and int(args.rotate) % 90:
        print("erreur : la rotation vidéo doit être un multiple de 90°",
              file=sys.stderr)
        return 2

    crf = args.crf if args.crf is not None else video_format.default_crf
    if not video_format.crf_min <= crf <= video_format.crf_max:
        print("erreur : le CRF doit être compris entre %d et %d pour %s"
              % (video_format.crf_min, video_format.crf_max,
                 video_format.label), file=sys.stderr)
        return 2
    audio_mode = "none" if args.no_audio else (
        "copy" if args.audio_copy else "auto")
    settings = video_engine.VideoSettings(
        crf=crf, speed=args.video_speed or "balanced", width=width,
        height=height, fill=args.fill, fps=args.fps,
        rotation=int(args.rotate or 0), speed_factor=float(args.speed or 1.0),
        start=start, end=end, audio_mode=audio_mode,
        audio_bitrate=args.audio_bitrate or video_format.default_audio_bitrate)
    if audio_mode == "copy" and abs(settings.speed_factor - 1.0) > 1e-6:
        print("erreur : --audio-copy est incompatible avec --speed",
              file=sys.stderr)
        return 2

    output = args.output or video_engine.default_output_path(info.path,
                                                            format_key)
    if os.path.exists(output) and not args.force:
        print("erreur : %s existe déjà (utiliser --force pour l'écraser)"
              % output, file=sys.stderr)
        return 2

    try:
        result = video_engine.convert(
            info.path, output, format_key, settings,
            progress=_progress_printer(args.quiet))
    except video_engine.VideoError as error:
        print("\nerreur : %s" % error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompu", file=sys.stderr)
        return 130

    _print_warnings(result["warnings"])
    delta = " · " + image_engine.delta_label(result["source_size"],
                                             result["size"])
    print("OK : %s (%s · %d × %d px · %s · %s%s · %.1f s)"
          % (result["path"], result["format"].label, result["width"],
             result["height"], video_engine.format_duration(result["duration"]),
             image_engine.human_size(result["size"]), delta,
             result["elapsed"]))
    return 0


def _print_video_formats():
    print("%-8s %-12s %-8s %s" % ("CLÉ", "FORMAT", "EXT.", "DESCRIPTION"))
    for fmt in video_formats.FORMATS:
        state = "" if video_engine.format_supported(
            fmt.key) else "  (encodeur absent)"
        print("%-8s %-12s %-8s %s%s" % (fmt.key, fmt.label, fmt.extension,
                                        fmt.description, state))


def _print_image_formats():
    print("%-8s %-10s %-8s %s" % ("CLÉ", "FORMAT", "EXT.", "DESCRIPTION"))
    for fmt in image_formats.FORMATS:
        print("%-8s %-10s %-8s %s" % (fmt.key, fmt.label, fmt.extension,
                                      fmt.description))


def _print_formats():
    print("%-8s %-14s %-8s %s" % ("CLÉ", "FORMAT", "EXT.", "DESCRIPTION"))
    for fmt in formats.FORMATS:
        print("%-8s %-14s %-8s %s" % (fmt.key, fmt.label, fmt.extension,
                                      fmt.description))
    version = ffmpeg_tools.version()
    print("\nffmpeg : %s" % (version or "introuvable"))


def _print_warnings(warnings):
    for warning in warnings:
        print("attention : %s" % warning)


def _progress_printer(quiet):
    if quiet:
        return None
    state = {"last": -1}

    def report(fraction, message):
        percent = int(max(0.0, min(1.0, fraction)) * 100)
        if percent != state["last"]:
            state["last"] = percent
            sys.stderr.write("\r  %3d %%  %-44s" % (percent, message[:44]))
            sys.stderr.flush()
            if percent >= 100:
                sys.stderr.write("\n")
    return report


if __name__ == "__main__":
    sys.exit(main())
