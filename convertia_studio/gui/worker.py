"""Tâches exécutées hors du fil graphique (analyse et conversion)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .. import jobs


class DescribeWorker(QThread):
    """Analyse une source (projet Audacity ou fichier audio)."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            self.done.emit(jobs.describe(self._path))
        except Exception as error:  # noqa: BLE001 - message destiné à l'utilisateur
            self.failed.emit(str(error))


class ConvertWorker(QThread):
    """Convertit une source vers un format donné."""

    progress = Signal(float, str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, source, dest, format_key, options, parent=None):
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._format_key = format_key
        self._options = options

    def run(self):
        try:
            result = jobs.convert(
                self._source, self._dest, self._format_key, self._options,
                progress=lambda fraction, message: self.progress.emit(fraction, message))
            self.done.emit(result)
        except Exception as error:  # noqa: BLE001 - message destiné à l'utilisateur
            self.failed.emit(str(error))
