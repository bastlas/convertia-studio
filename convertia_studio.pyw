#!/usr/bin/env python3
"""Lanceur de Convertia Studio (double-clic sous Windows, `python3` ailleurs).

Sans argument : ouvre la fenêtre.  Avec ``--cli`` : bascule sur la ligne de
commande (utile pour l'exécutable Windows, qui est compilé sans console).
"""

from __future__ import annotations

import sys


def _attach_console():
    """Rattache la sortie au terminal parent (exécutable Windows sans console)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.AttachConsole(-1)  # ATTACH_PARENT_PROCESS
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:  # noqa: BLE001 - la fenêtre reste utilisable sans console
        pass


def _utf8_output():
    """Force l'UTF-8 sur les sorties standard (accents sous Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    _utf8_output()
    if argv and argv[0] in ("--cli", "cli"):
        _attach_console()
        from convertia_studio.cli import main as cli_main

        return cli_main(argv[1:])
    from convertia_studio.gui.app import run

    return run([sys.argv[0]] + argv)


if __name__ == "__main__":
    sys.exit(main())
