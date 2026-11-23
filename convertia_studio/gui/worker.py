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


class ImageDescribeWorker(QThread):
    """Analyse une image (dimensions, format, poids)."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            from ..image import engine

            self.done.emit(engine.describe(self._path))
        except Exception as error:  # noqa: BLE001 - message destiné à l'utilisateur
            self.failed.emit(str(error))


class ImagePreviewWorker(QThread):
    """Prépare l'aperçu graphique d'une transformation."""

    done = Signal(int, bytes, int, int)
    failed = Signal(int, str)

    def __init__(self, path, settings, format_key, token, max_side=1600,
                 parent=None):
        super().__init__(parent)
        self._path = path
        self._settings = settings
        self._format_key = format_key
        self._token = token
        self._max_side = max_side

    def run(self):
        try:
            from ..image import engine

            data, width, height, _warnings = engine.preview(
                self._path, self._settings, max_side=self._max_side,
                format_key=self._format_key)
            self.done.emit(self._token, data, width, height)
        except Exception as error:  # noqa: BLE001 - message destiné à l'utilisateur
            self.failed.emit(self._token, str(error))


class ImageEstimateWorker(QThread):
    """Calcule le poids final sans écrire le fichier."""

    done = Signal(int, int)
    failed = Signal(int, str)

    def __init__(self, path, settings, format_key, token, parent=None):
        super().__init__(parent)
        self._path = path
        self._settings = settings
        self._format_key = format_key
        self._token = token

    def run(self):
        try:
            from ..image import engine

            size, _width, _height = engine.estimate(
                self._path, self._settings, self._format_key)
            self.done.emit(self._token, size)
        except Exception as error:  # noqa: BLE001 - message destiné à l'utilisateur
            self.failed.emit(self._token, str(error))


class ImageConvertWorker(QThread):
    """Applique les transformations et écrit le fichier final."""

    progress = Signal(float, str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, source, dest, format_key, settings, parent=None):
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._format_key = format_key
        self._settings = settings

    def run(self):
        try:
            from ..image import engine

            result = engine.convert(
                self._source, self._dest, self._format_key, self._settings,
                progress=lambda fraction, message: self.progress.emit(
                    fraction, message))
            self.done.emit(result)
        except Exception as error:  # noqa: BLE001 - message destiné à l'utilisateur
            self.failed.emit(str(error))
