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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="convertia_studio",
        description="%s — %s" % (APP_NAME, APP_TAGLINE),
        epilog="Sources acceptées : projets Audacity (.aup3/.aup4, y compris "
               "*unsaved), fichiers audio courants (wav, mp3, m4a, flac…) et "
               "images (png, jpg, webp, avif, tiff, bmp, gif).")
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
    parser.add_argument("--info", action="store_true",
                        help="affiche les informations sur la source et s'arrête")
    parser.add_argument("--list-formats", action="store_true",
                        help="liste les formats audio de sortie disponibles")
    parser.add_argument("--list-image-formats", action="store_true",
                        help="liste les formats d'image de sortie disponibles")
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
    if not args.source:
        parser.print_help()
        return 2

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
