"""Fenêtre principale : navigation latérale, pages et pied de page."""

from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, APP_TAGLINE, __version__, ffmpeg_tools
from ..image import engine as image_engine
from . import theme, widgets
from .pages.audio_page import AudioPage
from .pages.coming_soon import ComingSoonPage
from .pages.image_page import ImagePage


class BrandMark(QWidget):
    """Pastille dégradée avec une forme d'onde."""

    def __init__(self, size=38, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self._size, self._size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(theme.accent_gradient(0, 0, self._size,
                                                      self._size)))
        painter.drawRoundedRect(rect, self._size * 0.29, self._size * 0.29)
        inset = self._size * 0.24
        widgets._paint_icon(painter, "waveform",
                            QRectF(inset, inset, self._size - 2 * inset,
                                   self._size - 2 * inset),
                            theme.color("bg"))
        painter.end()


def window_icon():
    """Icône de la fenêtre (et du raccourci sous Windows)."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(theme.accent_gradient(0, 0, size, size)))
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), 16, 16)
    widgets._paint_icon(painter, "waveform", QRectF(16, 16, 32, 32),
                        theme.color("bg"))
    painter.end()
    return QIcon(pixmap)


class Sidebar(QFrame):
    """Colonne de navigation de gauche."""

    pageSelected = Signal(int)

    ENTRIES = (("Audio", "audio"), ("Image", "image"), ("Vidéo", "video"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(228)
        self.setStyleSheet(
            "QFrame#Sidebar { background: rgba(8, 13, 24, 140);"
            " border-right: 1px solid %s; }" % theme.COLORS["line_soft"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(8)
        layout.addLayout(self._build_brand())
        layout.addSpacing(20)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons = []
        for index, (label, glyph) in enumerate(self.ENTRIES):
            button = widgets.NavButton(label, glyph)
            button.clicked.connect(lambda _checked=False, i=index: self.select(i))
            self._group.addButton(button)
            layout.addWidget(button)
            self.buttons.append(button)

        layout.addStretch(1)
        layout.addWidget(self._build_engine_card())
        layout.addSpacing(8)
        footer = QLabel("%s v%s" % (APP_NAME, __version__))
        footer.setObjectName("Faint")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        self.select(0, emit=False)

    def _build_brand(self):
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(BrandMark())

        text = QVBoxLayout()
        text.setSpacing(0)
        for word, tint in (("CONVERTIA", theme.COLORS["text"]),
                           ("STUDIO", theme.COLORS["cyan"])):
            label = QLabel(word)
            label.setFont(theme.ui_font(13, QFont.Weight.Bold, letter_spacing=2.4))
            label.setStyleSheet("color: %s;" % tint)
            text.addWidget(label)
        brand.addLayout(text, 1)
        return brand

    def _build_engine_card(self):
        card = QFrame()
        card.setObjectName("CardFlat")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        caption = QLabel("MOTEUR")
        caption.setObjectName("SectionLabel")
        layout.addWidget(caption)
        version = ffmpeg_tools.version()
        label = QLabel("ffmpeg %s" % version if version else "ffmpeg introuvable")
        label.setObjectName("Mono" if version else "Faint")
        if not version:
            label.setStyleSheet("color: %s;" % theme.COLORS["amber"])
        layout.addWidget(label)
        return card

    def select(self, index, emit=True):
        for position, button in enumerate(self.buttons):
            button.setChecked(position == index)
        if emit:
            self.pageSelected.emit(index)


class MainWindow(QMainWindow):
    """Fenêtre principale de Convertia Studio."""

    def __init__(self, initial_path=None):
        super().__init__()
        self.setWindowTitle("%s — %s" % (APP_NAME, APP_TAGLINE.split(" · ")[0]))
        self.setMinimumSize(1120, 760)
        self.resize(1264, 844)
        self.setWindowIcon(window_icon())

        background = widgets.AuroraBackground()
        self.setCentralWidget(background)
        root = QHBoxLayout(background)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.pages = QStackedWidget()
        self.audio_page = AudioPage()
        self.image_page = ImagePage()
        self.video_page = ComingSoonPage(
            "Vidéo",
            "Convertir, découper et extraire l'audio de vos vidéos — section à venir.",
            "video", theme.COLORS["magenta"],
            (("Conteneurs", "MP4, MKV, WebM et MOV, avec choix des codecs."),
             ("Découpe", "Extraire un passage, remplacer la piste audio."),
             ("Audio", "Récupérer la piste son d'une vidéo dans tous les formats de "
                       "la page Audio.")),
            "Comme pour l'image, on en reparlera pour décider du contenu exact et "
            "des priorités.")
        self.pages.addWidget(self.audio_page)
        self.pages.addWidget(self.image_page)
        self.pages.addWidget(self.video_page)
        content_layout.addWidget(self.pages, 1)
        content_layout.addWidget(self._build_footer())
        root.addWidget(content, 1)

        self.sidebar.pageSelected.connect(self._switch_page)
        self.audio_page.statusMessage.connect(self.footer_status.setText)
        self.image_page.statusMessage.connect(self.footer_status.setText)

        self.setAcceptDrops(True)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.open_file)
        QShortcut(QKeySequence("Ctrl+Return"), self,
                  activated=self.trigger_conversion)

        if initial_path and os.path.isfile(initial_path):
            self._route_file(initial_path)

    def _build_footer(self):
        footer = QFrame()
        footer.setFixedHeight(30)
        footer.setStyleSheet("border-top: 1px solid %s;" % theme.COLORS["line_soft"])
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(26, 0, 22, 0)
        self.footer_status = QLabel("Prêt")
        self.footer_status.setObjectName("Faint")
        layout.addWidget(self.footer_status, 1)
        hint = QLabel("Glissez un fichier n'importe où dans la fenêtre")
        hint.setObjectName("Faint")
        layout.addWidget(hint)
        return footer

    # -- glisser-déposer sur toute la fenêtre ---------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._route_file(path)
                break
        event.acceptProposedAction()

    # -- routage des fichiers -------------------------------------------
    def _route_file(self, path):
        """Ouvre le fichier sur la page correspondant à son type."""
        if image_engine.is_image(path):
            self.sidebar.select(1)
            self.image_page.load_source(path)
        else:
            self.sidebar.select(0)
            self.audio_page.load_source(path)

    def open_file(self):
        widget = self.pages.currentWidget()
        if widget is self.image_page:
            self.image_page.browse()
        else:
            self.audio_page._browse()

    def trigger_conversion(self):
        widget = self.pages.currentWidget()
        if widget is self.image_page:
            self.image_page.start_conversion()
        else:
            self.audio_page.start_conversion()

    def _switch_page(self, index):
        widget = self.pages.widget(index)
        if widget is None or widget is self.pages.currentWidget():
            return
        self.pages.setCurrentIndex(index)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        animation.start()
        self._fade_animation = animation
