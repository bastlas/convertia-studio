"""Point d'entrée de l'interface graphique."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__
from . import theme
from .window import MainWindow, window_icon


def run(argv=None):
    """Ouvre la fenêtre et bloque jusqu'à sa fermeture."""
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(window_icon())
    theme.apply_palette(app)

    initial = None
    candidates = [arg for arg in argv[1:] if not arg.startswith("-")]
    if candidates:
        initial = candidates[0]

    window = MainWindow(initial_path=initial)
    window.show()
    return app.exec()
