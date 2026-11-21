"""Interface en ligne de commande de Convertia Studio.

    python3 -m convertia_studio projet.aup4                  # → projet.mp4
    python3 -m convertia_studio projet.aup4 -f flac
    python3 -m convertia_studio chant.mp3 -f opus -b 128k
    python3 -m convertia_studio --list-formats
"""

from __future__ import annotations

import argparse
import os
import sys

from . import APP_NAME, APP_TAGLINE, __version__, ffmpeg_tools
from . import jobs
from .audio import formats


def build_parser():
    parser = argparse.ArgumentParser(
        prog="convertia_studio",
        description="%s — %s" % (APP_NAME, APP_TAGLINE),
        epilog="Sources acceptées : projets Audacity (.aup3/.aup4, y compris "
               "*unsaved) et fichiers audio courants (wav, mp3, m4a, flac…).")
    parser.add_argument("source", nargs="?",
                        help="fichier à convertir (projet Audacity ou audio)")
    parser.add_argument("-o", "--output", metavar="FICHIER",
                        help="fichier de sortie (défaut : <source>.<format>)")
    parser.add_argument("-f", "--format", metavar="FORMAT",
                        help="format de sortie : %s (défaut : mp4)"
                             % ", ".join(formats.FORMAT_KEYS))
    parser.add_argument("-b", "--bitrate", metavar="DÉBIT",
                        help="débit pour les formats compressés (ex. 192k)")
    parser.add_argument("--depth", default=None,
                        choices=[value for _, value in formats.DEPTH_CHOICES],
                        help="profondeur PCM pour wav/aiff (16, 24 ou 32f)")
    parser.add_argument("--sample-rate", type=int, metavar="HZ",
                        help="fréquence de sortie (par défaut celle de la source)")
    parser.add_argument("--mono", action="store_true", help="mixe en un canal")
    parser.add_argument("--info", action="store_true",
                        help="affiche les informations sur la source et s'arrête")
    parser.add_argument("--list-formats", action="store_true",
                        help="liste les formats de sortie disponibles")
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
    if not args.source:
        parser.print_help()
        return 2

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
