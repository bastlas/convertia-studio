"""Boîte de dialogue de recadrage avec sélection à la souris."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..image import engine
from . import theme, widgets


def load_preview_pixmap(path, image_width, image_height, max_side=2000):
    """Charge une image en QPixmap, réduite pour l'affichage (Pillow en secours)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_side:
        scale = max_side / max(size.width(), size.height())
        reader.setScaledSize(QSize(max(1, round(size.width() * scale)),
                                   max(1, round(size.height() * scale))))
    image = reader.read()
    if not image.isNull():
        return QPixmap.fromImage(image)
    data, _width, _height, _warnings = engine.preview(
        path, engine.ImageSettings(), max_side=max_side)
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return pixmap


class CropCanvas(QWidget):
    """Affiche l'image et la sélection ; déplacement et coins manipulables."""

    cropChanged = Signal(object)   # QRectF en pixels source

    MARGIN = 14
    HANDLE = 10
    MIN_SIZE = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(420, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._pixmap = QPixmap()
        self._image_size = QSize(0, 0)
        self._crop = QRectF()
        self._aspect = None
        self._mode = None
        self._anchor = QPointF()
        self._press = QPointF()
        self._original = QRectF()
        self._original_crop = QRectF()

    # -- données --------------------------------------------------------
    def set_image(self, pixmap, image_width, image_height, crop=None):
        self._pixmap = pixmap
        self._image_size = QSize(image_width, image_height)
        full = QRectF(0, 0, image_width, image_height)
        self._original = QRectF(full)
        if crop:
            rect = QRectF(crop[0], crop[1], crop[2], crop[3]).intersected(full)
            self._crop = rect if rect.width() >= self.MIN_SIZE else QRectF(full)
        else:
            self._crop = QRectF(full)
        self._emit()

    def crop(self):
        """Sélection en pixels entiers ``(x, y, largeur, hauteur)``."""
        rect = self._crop.intersected(self._original)
        x = int(round(rect.x()))
        y = int(round(rect.y()))
        width = max(1, int(round(rect.width())))
        height = max(1, int(round(rect.height())))
        width = min(width, self._image_size.width() - x)
        height = min(height, self._image_size.height() - y)
        return x, y, width, height

    def is_full(self):
        crop = self.crop()
        return crop == (0, 0, self._image_size.width(),
                        self._image_size.height())

    def set_aspect(self, aspect):
        self._aspect = aspect
        if aspect:
            self._crop = self._fit_aspect(self._crop, max_size=True)
        self._emit()

    def reset(self):
        self._crop = QRectF(self._original)
        self._emit()

    # -- géométrie ------------------------------------------------------
    def _image_rect(self):
        if self._image_size.isEmpty() or self._pixmap.isNull():
            return QRectF()
        available = QRectF(self.rect()).adjusted(self.MARGIN, self.MARGIN,
                                                 -self.MARGIN, -self.MARGIN)
        scale = min(available.width() / self._image_size.width(),
                    available.height() / self._image_size.height())
        width = self._image_size.width() * scale
        height = self._image_size.height() * scale
        return QRectF(available.x() + (available.width() - width) / 2,
                      available.y() + (available.height() - height) / 2,
                      width, height)

    def _scale(self):
        image_rect = self._image_rect()
        if self._image_size.width() <= 0:
            return 1.0
        return image_rect.width() / self._image_size.width()

    def _to_widget(self, rect):
        image_rect = self._image_rect()
        scale = self._scale()
        return QRectF(image_rect.x() + rect.x() * scale,
                      image_rect.y() + rect.y() * scale,
                      rect.width() * scale, rect.height() * scale)

    def _to_image(self, point):
        image_rect = self._image_rect()
        scale = self._scale() or 1.0
        return QPointF(min(max((point.x() - image_rect.x()) / scale, 0.0),
                           self._image_size.width()),
                       min(max((point.y() - image_rect.y()) / scale, 0.0),
                           self._image_size.height()))

    def _corners(self):
        rect = self._to_widget(self._crop)
        return {
            "tl": rect.topLeft(), "tr": rect.topRight(),
            "bl": rect.bottomLeft(), "br": rect.bottomRight(),
        }

    def _corner_at(self, pos):
        for name, point in self._corners().items():
            if (abs(pos.x() - point.x()) <= self.HANDLE + 4 and
                    abs(pos.y() - point.y()) <= self.HANDLE + 4):
                return name
        return None

    def _fit_aspect(self, rect, max_size=False):
        if not self._aspect:
            return rect
        width = rect.width()
        height = width / self._aspect
        if max_size:
            if height > self._image_size.height():
                height = self._image_size.height()
                width = height * self._aspect
            if width > self._image_size.width():
                width = self._image_size.width()
                height = width / self._aspect
        centre = rect.center()
        fitted = QRectF(centre.x() - width / 2, centre.y() - height / 2,
                        width, height)
        return self._clamp_inside(fitted)

    def _clamp_inside(self, rect):
        full = QRectF(0, 0, self._image_size.width(), self._image_size.height())
        if rect.width() > full.width():
            rect.setWidth(full.width())
        if rect.height() > full.height():
            rect.setHeight(full.height())
        x = min(max(rect.x(), 0.0), full.width() - rect.width())
        y = min(max(rect.y(), 0.0), full.height() - rect.height())
        rect.moveTo(x, y)
        return rect

    def _rect_from_anchor(self, anchor, point):
        dx = point.x() - anchor.x()
        dy = point.y() - anchor.y()
        sign_x = 1.0 if dx >= 0 else -1.0
        sign_y = 1.0 if dy >= 0 else -1.0
        width = abs(dx)
        height = abs(dy)
        if self._aspect:
            if width / self._aspect >= height:
                height = width / self._aspect
            else:
                width = height * self._aspect
        max_width = (self._image_size.width() - anchor.x() if sign_x > 0
                     else anchor.x())
        max_height = (self._image_size.height() - anchor.y() if sign_y > 0
                      else anchor.y())
        width = max(self.MIN_SIZE, min(width, max_width))
        height = max(self.MIN_SIZE, min(height, max_height))
        if self._aspect:
            if width / self._aspect > max_height:
                width = max_height * self._aspect
            if height * self._aspect > max_width:
                height = max_width / self._aspect
            if width / self._aspect >= height:
                height = width / self._aspect
            else:
                width = height * self._aspect
        x = anchor.x() if sign_x > 0 else anchor.x() - width
        y = anchor.y() if sign_y > 0 else anchor.y() - height
        return self._clamp_inside(QRectF(x, y, width, height))

    def _emit(self):
        self.update()
        self.cropChanged.emit(self._crop)

    # -- peinture -------------------------------------------------------
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QColor(theme.COLORS["bg_alt"]))
        painter.setPen(QPen(QColor(theme.COLORS["line_soft"]), 1))
        painter.drawRoundedRect(outer, 12, 12)

        image_rect = self._image_rect()
        if self._pixmap.isNull() or image_rect.isEmpty():
            painter.setPen(QColor(theme.COLORS["text_faint"]))
            painter.drawText(outer, Qt.AlignmentFlag.AlignCenter,
                             "Aucun aperçu disponible")
            return

        painter.save()
        painter.setClipRect(image_rect)
        painter.drawPixmap(image_rect, self._pixmap,
                           QRectF(self._pixmap.rect()))
        painter.restore()

        crop = self._to_widget(self._crop)
        shade = QColor(4, 7, 14, 180)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shade)
        for rect in (
                QRectF(image_rect.left(), image_rect.top(),
                       image_rect.width(), max(0.0, crop.top() - image_rect.top())),
                QRectF(image_rect.left(), crop.bottom(), image_rect.width(),
                       max(0.0, image_rect.bottom() - crop.bottom())),
                QRectF(image_rect.left(), crop.top(),
                       max(0.0, crop.left() - image_rect.left()), crop.height()),
                QRectF(crop.right(), crop.top(),
                       max(0.0, image_rect.right() - crop.right()), crop.height()),
        ):
            painter.drawRect(rect)

        accent = QColor(theme.COLORS["cyan"])
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(accent, 1.6))
        painter.drawRect(crop)

        thirds = QPen(QColor(accent.red(), accent.green(), accent.blue(), 70), 1)
        thirds.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(thirds)
        for index in (1, 2):
            x = crop.left() + crop.width() * index / 3
            y = crop.top() + crop.height() * index / 3
            painter.drawLine(QPointF(x, crop.top()), QPointF(x, crop.bottom()))
            painter.drawLine(QPointF(crop.left(), y), QPointF(crop.right(), y))

        painter.setPen(QPen(QColor(theme.COLORS["bg"]), 1.4))
        painter.setBrush(accent)
        for point in self._corners().values():
            painter.drawRoundedRect(
                QRectF(point.x() - self.HANDLE / 2, point.y() - self.HANDLE / 2,
                       self.HANDLE, self.HANDLE), 2.5, 2.5)

        # taille de la sélection
        label = "%d × %d" % (round(self._crop.width()),
                             round(self._crop.height()))
        painter.setFont(theme.mono_font(11))
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(label) + 16
        box = QRectF(crop.left(), max(image_rect.top() + 6, crop.top() - 26),
                     width, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(5, 7, 14, 200))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QColor(theme.COLORS["text"]))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)

    # -- souris ---------------------------------------------------------
    def mousePressEvent(self, event):
        if self._pixmap.isNull() or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        point = self._to_image(pos)
        corner = self._corner_at(pos)
        if corner:
            self._mode = "resize"
            opposite = {"tl": "br", "tr": "bl", "bl": "tr", "br": "tl"}[corner]
            self._anchor = self._corners()[opposite]
            self._anchor = self._to_image(self._anchor)
        elif self._to_widget(self._crop).contains(pos):
            self._mode = "move"
            self._press = point
            self._original_crop = QRectF(self._crop)
        else:
            self._mode = "new"
            self._anchor = point
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._mode is None:
            corner = self._corner_at(pos)
            if corner:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor if corner in
                               ("tl", "br") else Qt.CursorShape.SizeBDiagCursor)
            elif self._to_widget(self._crop).contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
            return
        point = self._to_image(pos)
        if self._mode == "move":
            delta = point - self._press
            moved = QRectF(self._original_crop)
            moved.moveTo(self._original_crop.x() + delta.x(),
                         self._original_crop.y() + delta.y())
            self._crop = self._clamp_inside(moved)
        else:
            self._crop = self._rect_from_anchor(self._anchor, point)
        self._emit()

    def mouseReleaseEvent(self, _event):
        self._mode = None
        self.update()


class CropDialog(QDialog):
    """Sélection interactive d'une zone de l'image."""

    ASPECTS = (
        ("Libre", None),
        ("Originale", "original"),
        ("Carré 1:1", 1.0),
        ("Photo 4:3", 4 / 3),
        ("Photo 3:2", 3 / 2),
        ("Écran 16:9", 16 / 9),
        ("Portrait 9:16", 9 / 16),
    )

    def __init__(self, path, image_width, image_height, crop=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recadrer l'image")
        self.setModal(True)
        self.resize(1020, 720)
        self.result_crop = None
        self._image_size = (image_width, image_height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Recadrer l'image")
        title.setObjectName("H1")
        subtitle = QLabel("Faites glisser la sélection, tirez ses coins pour la "
                          "redimensionner.")
        subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.size_pill = widgets.Pill("%d × %d" % (image_width, image_height),
                                      theme.COLORS["violet"])
        header.addWidget(self.size_pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)

        self.canvas = CropCanvas()
        pixmap = load_preview_pixmap(path, image_width, image_height)
        self.canvas.set_image(pixmap, image_width, image_height, crop)
        self.canvas.cropChanged.connect(self._on_crop_changed)
        body.addWidget(self.canvas, 1)

        panel = widgets.Card()
        panel.setFixedWidth(248)
        panel.body().addWidget(widgets.SectionLabel("Proportions"))
        self.aspect_combo = QComboBox()
        for label, _value in self.ASPECTS:
            self.aspect_combo.addItem(label)
        self.aspect_combo.currentIndexChanged.connect(self._aspect_changed)
        panel.add(self.aspect_combo)

        panel.body().addSpacing(6)
        panel.body().addWidget(widgets.SectionLabel("Sélection"))
        self.crop_label = QLabel("—")
        self.crop_label.setObjectName("H2")
        panel.add(self.crop_label)
        self.position_label = QLabel("")
        self.position_label.setObjectName("Faint")
        self.position_label.setWordWrap(True)
        panel.add(self.position_label)

        panel.body().addSpacing(6)
        reset = widgets.GhostButton("Toute l'image", icon_kind="image")
        reset.clicked.connect(self._reset)
        panel.add(reset)
        panel.body().addStretch(1)
        note = QLabel("Le recadrage s'applique avant la rotation et le "
                      "redimensionnement.")
        note.setObjectName("Faint")
        note.setWordWrap(True)
        panel.add(note)
        body.addWidget(panel)
        layout.addLayout(body, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        cancel = widgets.GhostButton("Annuler")
        cancel.setMinimumWidth(110)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        accept = widgets.NeonButton("Recadrer", icon_kind="check")
        accept.setMinimumWidth(168)
        accept.clicked.connect(self._accept)
        buttons.addWidget(accept)
        layout.addLayout(buttons)

        self._on_crop_changed(self.canvas.crop())

    # -- événements -----------------------------------------------------
    def _aspect_changed(self, index):
        value = self.ASPECTS[index][1]
        if value == "original":
            width, height = self._image_size
            value = width / height if height else 1.0
        self.canvas.set_aspect(value)

    def _reset(self):
        self.aspect_combo.setCurrentIndex(0)
        self.canvas.set_aspect(None)
        self.canvas.reset()

    def _on_crop_changed(self, rect):
        x, y, width, height = self.canvas.crop()
        self.crop_label.setText("%d × %d px" % (width, height))
        self.position_label.setText("Position x %d · y %d" % (x, y))
        share = 100.0 * (width * height) / max(
            1, self._image_size[0] * self._image_size[1])
        self.size_pill.setText("%d %% de l'image" % round(share))

    def _accept(self):
        crop = self.canvas.crop()
        self.result_crop = None if self.canvas.is_full() else crop
        self.accept()
