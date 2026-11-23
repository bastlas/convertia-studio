"""Page « Image » : recadrage, redimensionnement, rotation, compression."""

from __future__ import annotations

import os

from PIL import __version__ as pillow_version
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QSizePolicy, QSlider, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from ...image import engine, formats
from .. import theme, widgets
from ..crop_dialog import CropDialog, load_preview_pixmap
from ..worker import (ImageConvertWorker, ImageDescribeWorker,
                      ImageEstimateWorker, ImagePreviewWorker)

FILE_FILTER = (
    "Images (*.png *.jpg *.jpeg *.jpe *.jfif *.webp *.avif *.tif *.tiff "
    "*.bmp *.gif *.ico);;Tous les fichiers (*)"
)

MIRRORS = (("Aucun", (False, False)), ("Horizontal", (True, False)),
           ("Vertical", (False, True)), ("Les deux", (True, True)))

ANGLES = (("Aucune", 0), ("90° horaire", 90), ("180°", 180),
          ("90° antihoraire", 270))


def _small_ghost(text, icon_kind=None):
    """Bouton secondaire compact pour les rangées de réglages."""
    button = widgets.GhostButton(text, icon_kind=icon_kind)
    button.setFixedHeight(28)
    button.setFont(theme.ui_font(11, QFont.Weight.Medium))
    return button


class ImageSourceCard(QFrame):
    """Carte affichant l'image chargée."""

    changeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.glyph = widgets.GlyphWidget("image", theme.COLORS["violet"], 24)
        top.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setSpacing(1)
        self.title = QLabel("—")
        self.title.setObjectName("H2")
        self.path = QLabel("")
        self.path.setObjectName("Mono")
        text_column.addWidget(self.title)
        text_column.addWidget(self.path)
        top.addLayout(text_column, 1)

        self.kind_pill = widgets.Pill("IMAGE", theme.COLORS["violet"])
        top.addWidget(self.kind_pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self.details = QLabel("")
        self.details.setObjectName("Faint")
        self.details.setWordWrap(True)
        self.details.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Maximum)
        layout.addWidget(self.details)

        bottom = QHBoxLayout()
        self.change = _small_ghost("Changer d'image", "folder")
        self.change.clicked.connect(self.changeRequested)
        bottom.addWidget(self.change)
        self.meta = QLabel("")
        self.meta.setObjectName("Faint")
        bottom.addWidget(self.meta, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bottom)

    def set_source(self, info):
        self.title.setText(info.title)
        self.path.setText(widgets.elide(info.path, 70))
        self.details.setText("\n".join(info.details[:3]))
        self.setToolTip("\n".join(info.details))
        self.meta.setText("%s · %s" % (info.dimensions, info.size_label))

    def clear(self):
        self.title.setText("—")
        self.path.setText("")
        self.details.setText("")
        self.meta.setText("")


class PreviewPane(QWidget):
    """Aperçu de l'image, damier derrière la transparence."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._pixmap = QPixmap()
        self._caption = ""
        self._empty = "Déposez une image pour voir l'aperçu."
        self._checker = None

    def set_pixmap(self, pixmap, caption):
        self._pixmap = pixmap
        self._caption = caption
        self.update()

    def set_empty(self, text):
        self._pixmap = QPixmap()
        self._caption = ""
        self._empty = text
        self.update()

    def _checker_brush(self):
        if self._checker is None:
            tile = QPixmap(20, 20)
            tile.fill(QColor("#0B111D"))
            painter = QPainter(tile)
            painter.fillRect(0, 0, 10, 10, QColor("#101A2B"))
            painter.fillRect(10, 10, 10, 10, QColor("#101A2B"))
            painter.end()
            self._checker = QBrush(tile)
        return self._checker

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QColor(theme.COLORS["bg_alt"]))
        painter.setPen(QPen(QColor(theme.COLORS["line_soft"]), 1))
        painter.drawRoundedRect(outer, 12, 12)

        if self._pixmap.isNull():
            painter.setPen(QColor(theme.COLORS["text_faint"]))
            painter.setFont(theme.ui_font(12))
            painter.drawText(outer.adjusted(18, 18, -18, -18),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self._empty)
            return

        available = outer.adjusted(10, 10, -10, -10)
        size = self._pixmap.size()
        scale = min(available.width() / size.width(),
                    available.height() / size.height())
        width = size.width() * scale
        height = size.height() * scale
        target = QRectF(available.x() + (available.width() - width) / 2,
                        available.y() + (available.height() - height) / 2,
                        width, height)
        painter.setClipRect(target)
        painter.fillRect(target, self._checker_brush())
        painter.setClipRect(outer)
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))

        if self._caption:
            painter.setFont(theme.mono_font(10))
            metrics = painter.fontMetrics()
            box_width = metrics.horizontalAdvance(self._caption) + 16
            box = QRectF(target.left() + 8, target.top() + 8, box_width, 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(5, 7, 14, 205))
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(theme.COLORS["cyan"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._caption)


class CompareBars(QWidget):
    """Deux barres proportionnelles : poids avant / poids estimé."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self._before = 0
        self._after = None

    def set_sizes(self, before, after):
        self._before = before or 0
        self._after = after
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(theme.ui_font(10, QFont.Weight.DemiBold))
        label_width = 44
        value_width = 66
        bar_width = max(20, self.width() - label_width - value_width - 10)
        maximum = max(self._before, self._after or 0, 1)
        rows = (("AVANT", self._before, QColor(theme.COLORS["text_faint"])),
                ("APRÈS", self._after,
                 QColor(theme.COLORS["green"] if
                       (self._after is None or self._after <= self._before)
                       else theme.COLORS["red"])))
        painter.setPen(Qt.PenStyle.NoPen)
        for index, (label, value, colour) in enumerate(rows):
            y = 4 + index * 23
            painter.setPen(QColor(theme.COLORS["text_faint"] if index == 0
                                  else theme.COLORS["text_dim"]))
            painter.drawText(QRectF(0, y, label_width, 16),
                             Qt.AlignmentFlag.AlignVCenter, label)
            track = QRectF(label_width, y + 3, bar_width, 10)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.COLORS["line_soft"]))
            painter.drawRoundedRect(track, 5, 5)
            if value:
                width = max(6.0, bar_width * value / maximum)
                if value is self._after and index == 1:
                    colour = QColor(colour)
                    colour.setAlpha(230)
                painter.setBrush(colour)
                painter.drawRoundedRect(QRectF(track.x(), track.y(), width,
                                               track.height()), 5, 5)
            painter.setFont(theme.mono_font(10))
            painter.setPen(QColor(theme.COLORS["text_dim"]))
            text = "calcul…" if (index == 1 and value is None) else (
                engine.human_size(value) if value else "—")
            painter.drawText(QRectF(label_width + bar_width + 8, y - 1,
                                    value_width, 16),
                             Qt.AlignmentFlag.AlignVCenter |
                             Qt.AlignmentFlag.AlignRight, text)
            painter.setFont(theme.ui_font(10, QFont.Weight.DemiBold))


class ImagePage(QWidget):
    """Page principale : préparer et convertir une image."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info = None
        self._format_key = "jpeg"
        self._busy = False
        self._crop = None
        self._auto_dims = True
        self._loading_spins = False
        self._before_pixmap = None
        self._after_pixmap = None
        self._show_before = False
        self._estimate = None
        self._last_auto_output = ""
        self._describe_worker = None
        self._preview_worker = None
        self._preview_pending = False
        self._preview_token = 0
        self._estimate_worker = None
        self._estimate_pending = False
        self._estimate_token = 0
        self._convert_worker = None

        self.setAcceptDrops(True)
        self._build()

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(220)
        self._preview_timer.timeout.connect(self._start_preview)

        self._estimate_timer = QTimer(self)
        self._estimate_timer.setSingleShot(True)
        self._estimate_timer.setInterval(650)
        self._estimate_timer.timeout.connect(self._start_estimate)

        self._set_note("Déposez une image pour commencer.")
        self._refresh_controls()

    # -- construction ---------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(16)
        root.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addLayout(self._build_left(), 6)
        body.addLayout(self._build_right(), 4)
        root.addLayout(body, 1)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(14)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Image")
        title.setObjectName("H1")
        subtitle = QLabel("Recadrer, redimensionner, pivoter et compresser vos "
                          "images — avec aperçu et comparaison du poids.")
        subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.engine_pill = widgets.Pill(
            "PIL %s" % pillow_version.split(".")[0], theme.COLORS["violet"])
        header.addWidget(self.engine_pill, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_left(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        self.source_stack = QStackedWidget()
        self.drop_zone = widgets.DropZone(
            glyph="image", title="Déposez une image ici",
            subtitle="PNG, JPEG, WebP, AVIF, TIFF, BMP, GIF — ou cliquez pour "
                     "parcourir")
        self.drop_zone.clicked.connect(self.browse)
        self.drop_zone.fileDropped.connect(self.load_source)
        self.source_card = ImageSourceCard()
        self.source_card.changeRequested.connect(self.browse)
        self.source_stack.addWidget(self.drop_zone)
        self.source_stack.addWidget(self.source_card)
        column.addWidget(self.source_stack, 0)

        preview_card = widgets.Card(padding=14, spacing=8)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(widgets.SectionLabel("Aperçu"))
        self.preview_dims = QLabel("")
        self.preview_dims.setObjectName("Faint")
        head.addWidget(self.preview_dims)
        head.addStretch(1)
        self.compare_toggle = _small_ghost("Voir l'original")
        self.compare_toggle.clicked.connect(self._toggle_preview)
        self.compare_toggle.setEnabled(False)
        head.addWidget(self.compare_toggle)
        preview_card.add_layout(head)
        self.preview = PreviewPane()
        preview_card.body().addWidget(self.preview, 1)
        column.addWidget(preview_card, 1)

        labels = QHBoxLayout()
        labels.addWidget(widgets.SectionLabel("Format de sortie"))
        labels.addStretch(1)
        column.addLayout(labels)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self._format_group = QButtonGroup(self)
        self._format_group.setExclusive(True)
        self._format_cards = {}
        for index, image_format in enumerate(formats.FORMATS):
            card = widgets.FormatCard(image_format)
            card.setMinimumHeight(80)
            card.setMaximumHeight(80)
            if not engine.output_supported(image_format.key):
                card.setEnabled(False)
                card.setToolTip("%s n'est pas disponible avec cette version de "
                                "Pillow." % image_format.label)
            card.setChecked(image_format.key == self._format_key)
            card.clicked.connect(
                lambda _checked=False, key=image_format.key: self.set_format(key))
            self._format_group.addButton(card)
            self._format_cards[image_format.key] = card
            grid.addWidget(card, index // 3, index % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        column.addWidget(grid_host, 0)

        self.format_hint = QLabel("")
        self.format_hint.setObjectName("Faint")
        self.format_hint.setWordWrap(True)
        column.addWidget(self.format_hint)
        self._update_format_hint()
        return column

    def _build_right(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        settings = widgets.Card(padding=14, spacing=8)
        settings.body().addWidget(widgets.SectionLabel("Traitement"))

        self.crop_label = QLabel("Toute l'image")
        self.crop_label.setObjectName("Muted")
        self.crop_label.setToolTip("Zone conservée de l'image")
        self.crop_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Preferred)
        self.crop_button = _small_ghost("Recadrer…", "image")
        self.crop_button.clicked.connect(self._open_crop)
        self.crop_clear = _small_ghost("Tout")
        self.crop_clear.clicked.connect(self._clear_crop)
        settings.add_layout(self._row("Recadrage", self.crop_label,
                                      self.crop_button, self.crop_clear))

        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(1, 60000)
            spin.setKeyboardTracking(False)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.width_spin.valueChanged.connect(self._width_changed)
        self.height_spin.valueChanged.connect(self._height_changed)
        self.lock_ratio = QCheckBox("Lier")
        self.lock_ratio.setChecked(True)
        self.lock_ratio.setToolTip("Conserver les proportions")
        cross = QLabel("×")
        cross.setObjectName("Faint")
        reset_dims = _small_ghost("Orig.")
        reset_dims.setToolTip("Revenir à la taille de l'image")
        reset_dims.clicked.connect(self._reset_dims)
        self.width_spin.setToolTip("Largeur de sortie en pixels")
        self.height_spin.setToolTip("Hauteur de sortie en pixels")
        settings.add_layout(self._row(
            "Taille", self.width_spin, cross, self.height_spin,
            self.lock_ratio, reset_dims))

        self.angle_combo = QComboBox()
        for label, value in ANGLES:
            self.angle_combo.addItem(label, value)
        self.mirror_combo = QComboBox()
        for label, _value in MIRRORS:
            self.mirror_combo.addItem(label)
        self.angle_combo.currentIndexChanged.connect(self._rotation_changed)
        self.mirror_combo.currentIndexChanged.connect(self._settings_changed)
        settings.add_layout(self._row("Rotation", self.angle_combo,
                                      self.mirror_combo))

        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(85)
        self.quality_slider.valueChanged.connect(self._quality_changed)
        self.quality_value = QLabel("85")
        self.quality_value.setObjectName("Mono")
        self.quality_value.setMinimumWidth(64)
        self.quality_value.setAlignment(Qt.AlignmentFlag.AlignRight |
                                        Qt.AlignmentFlag.AlignVCenter)
        settings.add_layout(self._row("Qualité", self.quality_slider,
                                      self.quality_value))
        column.addWidget(settings)

        output = widgets.Card(padding=14, spacing=8)
        output.body().addWidget(widgets.SectionLabel("Sortie et conversion"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("chemin du fichier à créer")
        self.output_edit.textChanged.connect(lambda _text: self._refresh_controls())
        output.add(self.output_edit)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self.browse_output = _small_ghost("Choisir…", "folder")
        self.browse_output.clicked.connect(self._browse_output)
        output_row.addWidget(self.browse_output)
        output_row.addStretch(1)
        self.delta_pill = widgets.Pill("—", theme.COLORS["text_faint"])
        output_row.addWidget(self.delta_pill)
        output.add_layout(output_row)

        weights = QHBoxLayout()
        weights.setSpacing(8)
        self.before_label = QLabel("—")
        self.before_label.setObjectName("Muted")
        arrow = QLabel("→")
        arrow.setObjectName("Faint")
        self.after_label = QLabel("—")
        self.after_label.setObjectName("Value")
        weights.addWidget(QLabel("Poids"))
        weights.addWidget(self.before_label)
        weights.addWidget(arrow)
        weights.addWidget(self.after_label)
        weights.addStretch(1)
        output.add_layout(weights)
        self.compare_bars = CompareBars()
        output.add(self.compare_bars)

        self.convert_button = widgets.NeonButton("Convertir l'image",
                                                 icon_kind="spark")
        self.convert_button.clicked.connect(self.start_conversion)
        output.add(self.convert_button)
        self.progress = widgets.GradientProgress()
        output.add(self.progress)
        self.status = QLabel("En attente d'une image")
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        output.add(self.status)
        self.note = QLabel("")
        self.note.setObjectName("Faint")
        self.note.setWordWrap(True)
        self.note.setMaximumHeight(32)
        output.add(self.note)
        column.addWidget(output)

        column.addStretch(1)
        return column

    def _row(self, caption, *widgets_):
        """Rangée compacte « intitulé + champs »."""
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel(caption.upper())
        label.setObjectName("SectionLabel")
        label.setFixedWidth(78)
        row.addWidget(label)
        for widget in widgets_:
            if isinstance(widget, (QSpinBox, QComboBox, QSlider)):
                row.addWidget(widget, 1)
            else:
                row.addWidget(widget, 0)
        return row

    # -- état -----------------------------------------------------------
    def _settings(self):
        flip_h, flip_v = MIRRORS[self.mirror_combo.currentIndex()][1]
        return engine.ImageSettings(
            crop=self._crop,
            width=None if self._auto_dims else self.width_spin.value(),
            height=None if self._auto_dims else self.height_spin.value(),
            angle=float(self.angle_combo.currentData() or 0),
            flip_h=flip_h, flip_v=flip_v,
            quality=self.quality_slider.value())

    def _crop_size(self):
        if self._crop:
            return self._crop[2], self._crop[3]
        if self._info:
            return self._info.width, self._info.height
        return 1, 1

    def _output_size(self):
        width, height = self._crop_size()
        if int(self.angle_combo.currentData() or 0) % 180 == 90:
            width, height = height, width
        return width, height

    def _sync_dims(self):
        width, height = self._output_size()
        self._loading_spins = True
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        self._loading_spins = False
        self._auto_dims = True

    def _width_changed(self, value):
        if self._loading_spins or not self._info:
            return
        self._auto_dims = False
        if self.lock_ratio.isChecked():
            width, height = self._output_size()
            self._loading_spins = True
            self.height_spin.setValue(max(1, round(value * height / width)))
            self._loading_spins = False
        self._settings_changed()

    def _height_changed(self, value):
        if self._loading_spins or not self._info:
            return
        self._auto_dims = False
        if self.lock_ratio.isChecked():
            width, height = self._output_size()
            self._loading_spins = True
            self.width_spin.setValue(max(1, round(value * width / height)))
            self._loading_spins = False
        self._settings_changed()

    def _reset_dims(self):
        self._sync_dims()
        self._settings_changed()

    def _rotation_changed(self, _index):
        if self._auto_dims:
            self._sync_dims()
        self._settings_changed()

    def _quality_changed(self, value):
        self.quality_value.setText(str(value))
        self._settings_changed()

    def _settings_changed(self, *_args):
        if not self._info or self._busy:
            return
        self._preview_token += 1
        self._estimate_token += 1
        self._preview_timer.start()
        self._estimate_timer.start()
        self._estimate = None
        self.after_label.setText("calcul…")
        self.delta_pill.setText("…")
        self.delta_pill.set_tint(theme.COLORS["text_faint"])
        self.compare_bars.set_sizes(self._info.size, None)

    def _set_note(self, text, tint=None):
        self.note.setText(text)
        self.note.setToolTip(text)
        colour = tint or theme.COLORS["text_faint"]
        self.note.setStyleSheet("color: %s;" % colour)

    def _refresh_controls(self):
        image_format = formats.get_format(self._format_key)
        busy = self._busy
        has_source = self._info is not None
        self.quality_slider.setEnabled(image_format.supports_quality and not busy)
        self.quality_slider.setVisible(image_format.supports_quality)
        self.quality_value.setText(
            str(self.quality_slider.value()) if image_format.supports_quality
            else "sans perte")
        self.crop_button.setEnabled(has_source and not busy)
        self.crop_clear.setEnabled(has_source and not busy and self._crop is not None)
        for spin in (self.width_spin, self.height_spin):
            spin.setEnabled(has_source and not busy)
        self.lock_ratio.setEnabled(has_source and not busy)
        self.angle_combo.setEnabled(has_source and not busy)
        self.mirror_combo.setEnabled(has_source and not busy)
        self.browse_output.setEnabled(not busy)
        self.output_edit.setEnabled(not busy)
        for card in self._format_cards.values():
            card.setEnabled(not busy)
        self.convert_button.setEnabled(
            not busy and has_source and bool(self.output_edit.text().strip()))
        self.convert_button.setText("Conversion…" if busy
                                    else "Convertir l'image")

    def _update_format_hint(self):
        image_format = formats.get_format(self._format_key)
        self.format_hint.setText("%s — %s" % (image_format.label,
                                              image_format.description))

    def set_format(self, key):
        if key == self._format_key:
            return
        self._format_key = key
        card = self._format_cards.get(key)
        if card is not None and not card.isChecked():
            card.setChecked(True)
        image_format = formats.get_format(key)
        if image_format.supports_quality:
            self.quality_slider.blockSignals(True)
            self.quality_slider.setValue(image_format.default_quality)
            self.quality_slider.blockSignals(False)
            self.quality_value.setText(str(image_format.default_quality))
        self._update_format_hint()
        self._sync_auto_output()
        self._refresh_controls()
        if self._info:
            self._settings_changed()

    def _sync_auto_output(self):
        if not self._info:
            return
        suggested = engine.default_output_path(self._info.path, self._format_key)
        current = self.output_edit.text().strip()
        if not current or current == self._last_auto_output:
            self._last_auto_output = suggested
            self.output_edit.setText(suggested)

    # -- chargement ------------------------------------------------------
    def load_source(self, path):
        if self._busy:
            return
        path = os.fspath(path)
        if not engine.is_image(path):
            self._set_note("Ce fichier n'est pas une image reconnue : %s"
                           % widgets.elide(os.path.basename(path), 40),
                           theme.COLORS["amber"])
            return
        self._set_note("Analyse de l'image…")
        self.status.setText("Analyse du fichier…")
        self.progress.set_indeterminate(True)
        self._describe_worker = ImageDescribeWorker(path, self)
        self._describe_worker.done.connect(self._source_ready)
        self._describe_worker.failed.connect(self._source_failed)
        self._describe_worker.start()

    def _source_ready(self, info):
        self.progress.set_indeterminate(False)
        self.progress.set_value(0)
        self._info = info
        self._crop = None
        self._estimate = None
        self._show_before = False
        self.source_card.set_source(info)
        self.source_stack.setCurrentWidget(self.source_card)

        self.angle_combo.blockSignals(True)
        self.angle_combo.setCurrentIndex(0)
        self.angle_combo.blockSignals(False)
        self.mirror_combo.blockSignals(True)
        self.mirror_combo.setCurrentIndex(0)
        self.mirror_combo.blockSignals(False)
        self._sync_dims()

        guessed = formats.guess_format(info.path)
        if guessed and not engine.output_supported(guessed):
            guessed = None
        self._format_key = ""
        self.set_format(guessed or "jpeg")

        self._before_pixmap = load_preview_pixmap(
            info.path, info.width, info.height, max_side=1600)
        self._after_pixmap = None
        self.preview.set_pixmap(self._before_pixmap, "ORIGINAL")
        self.preview_dims.setText(info.dimensions)
        self.compare_toggle.setEnabled(False)
        self.compare_toggle.setText("Voir l'original")

        self._last_auto_output = ""
        self._sync_auto_output()
        self.before_label.setText(engine.human_size(info.size))
        self.after_label.setText("calcul…")
        self.delta_pill.setText("…")
        self.delta_pill.set_tint(theme.COLORS["text_faint"])
        self.compare_bars.set_sizes(info.size, None)

        warnings = list(info.warnings)
        if info.has_alpha and not formats.get_format(
                self._format_key).supports_alpha:
            warnings.append("transparence aplatie sur fond blanc")
        if warnings:
            self._set_note(" ; ".join(warnings), theme.COLORS["amber"])
        else:
            self._set_note("Prêt : ajustez les réglages puis convertissez.")
        self.status.setText("Prêt à convertir")
        self.statusMessage.emit("Image chargée")
        self._update_crop_label()
        self._refresh_controls()
        self._preview_timer.start()
        self._estimate_timer.start()

    def _source_failed(self, message):
        self.progress.set_indeterminate(False)
        self._info = None
        self.source_stack.setCurrentWidget(self.drop_zone)
        self.status.setText("Impossible de lire cette image")
        self._set_note(message, theme.COLORS["red"])
        self.preview.set_empty("Déposez une image pour voir l'aperçu.")
        self.preview_dims.setText("")
        self._refresh_controls()

    def browse(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "Choisir une image", "", FILE_FILTER)
        if path:
            self.load_source(path)

    def _browse_output(self):
        image_format = formats.get_format(self._format_key)
        suggested = self.output_edit.text().strip() or (
            engine.default_output_path(self._info.path, self._format_key)
            if self._info else "")
        path, _selected = QFileDialog.getSaveFileName(
            self, "Fichier de sortie", suggested,
            "%s (*%s);;Tous les fichiers (*)" % (image_format.label,
                                                 image_format.extension))
        if path:
            self.output_edit.setText(path)
            self._last_auto_output = path

    # -- recadrage -------------------------------------------------------
    def _open_crop(self):
        if not self._info or self._busy:
            return
        dialog = CropDialog(self._info.path, self._info.width,
                           self._info.height, self._crop, self)
        if dialog.exec():
            self._crop = dialog.result_crop
            self._update_crop_label()
            if self._auto_dims:
                self._sync_dims()
            self._settings_changed()

    def _clear_crop(self):
        if not self._info:
            return
        self._crop = None
        self._update_crop_label()
        if self._auto_dims:
            self._sync_dims()
        self._settings_changed()

    def _update_crop_label(self):
        if not self._info:
            self.crop_label.setText("—")
            return
        if not self._crop:
            self.crop_label.setText("Toute l'image")
            self.crop_label.setToolTip(
                "Aucun recadrage · %d × %d px" % (self._info.width,
                                                 self._info.height))
        else:
            x, y, width, height = self._crop
            self.crop_label.setText("%d × %d px" % (width, height))
            self.crop_label.setToolTip(
                "Sélection %d × %d px à partir de x %d, y %d"
                % (width, height, x, y))
        self._refresh_controls()

    # -- aperçu et estimation --------------------------------------------
    def _start_preview(self):
        if not self._info or self._busy:
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_pending = True
            return
        self._preview_token += 1
        token = self._preview_token
        worker = ImagePreviewWorker(self._info.path, self._settings(),
                                    self._format_key, token, parent=self)
        worker.done.connect(self._preview_ready)
        worker.failed.connect(self._preview_failed)
        worker.finished.connect(
            lambda worker=worker: self._preview_finished(worker))
        self._preview_worker = worker
        worker.start()

    def _preview_ready(self, token, data, width, height):
        if token != self._preview_token:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            image_format = formats.get_format(self._format_key)
            quality = (" · %d %%" % self.quality_slider.value()
                       if image_format.supports_quality else "")
            self._after_pixmap = pixmap
            self._show_before = False
            self.preview_dims.setText("%d × %d px · %s%s"
                                      % (width, height, image_format.label,
                                         quality))
            self._update_preview_view()
            self.compare_toggle.setEnabled(True)

    def _preview_finished(self, worker):
        if worker is not self._preview_worker:
            return
        if self._preview_pending:
            self._preview_pending = False
            self._start_preview()

    def _preview_failed(self, token, message):
        if token == self._preview_token:
            self._set_note("Aperçu impossible : %s" % message,
                           theme.COLORS["amber"])

    def _update_preview_view(self):
        if not self._info:
            return
        if self._show_before and self._before_pixmap is not None:
            self.preview.set_pixmap(self._before_pixmap, "AVANT")
            self.preview_dims.setText(self._info.dimensions)
            self.compare_toggle.setText("Voir le résultat")
        elif self._after_pixmap is not None:
            self.preview.set_pixmap(self._after_pixmap, "APRÈS")
            self.compare_toggle.setText("Voir l'original")

    def _toggle_preview(self):
        if self._after_pixmap is None:
            return
        self._show_before = not self._show_before
        self._update_preview_view()

    def _start_estimate(self):
        if not self._info or self._busy:
            return
        if (self._estimate_worker is not None
                and self._estimate_worker.isRunning()):
            self._estimate_pending = True
            return
        self._estimate_token += 1
        token = self._estimate_token
        worker = ImageEstimateWorker(self._info.path, self._settings(),
                                     self._format_key, token, parent=self)
        worker.done.connect(self._estimate_ready)
        worker.failed.connect(self._estimate_failed)
        worker.finished.connect(
            lambda worker=worker: self._estimate_finished(worker))
        self._estimate_worker = worker
        worker.start()

    def _estimate_ready(self, token, size):
        if token != self._estimate_token:
            return
        self._estimate = size
        self._update_compare()

    def _estimate_finished(self, worker):
        if worker is not self._estimate_worker:
            return
        if self._estimate_pending:
            self._estimate_pending = False
            self._start_estimate()

    def _estimate_failed(self, token, message):
        if token == self._estimate_token:
            self.after_label.setText("?")
            self.delta_pill.setText("erreur")
            self.delta_pill.set_tint(theme.COLORS["red"])
            self._set_note("Estimation impossible : %s" % message,
                           theme.COLORS["amber"])

    def _update_compare(self):
        if not self._info:
            return
        before = self._info.size
        after = self._estimate
        self.after_label.setText(engine.human_size(after) if after
                                 else "calcul…")
        self.compare_bars.set_sizes(before, after)
        if after and before:
            self.delta_pill.setText(engine.delta_label(before, after))
            self.delta_pill.set_tint(theme.COLORS["green"] if after <= before
                                     else theme.COLORS["red"])
        elif after:
            self.delta_pill.setText("—")

    # -- conversion -------------------------------------------------------
    def start_conversion(self):
        if self._busy or not self._info:
            return
        destination = self.output_edit.text().strip()
        if not destination:
            self._set_note("Choisissez d'abord un fichier de sortie.",
                           theme.COLORS["amber"])
            return
        if os.path.abspath(destination) == os.path.abspath(self._info.path):
            self._set_note("Le fichier de sortie ne peut pas être la source.",
                           theme.COLORS["red"])
            return
        image_format = formats.get_format(self._format_key)
        warnings = []
        if os.path.exists(destination):
            warnings.append("%s existe déjà : il sera remplacé."
                            % os.path.basename(destination))
        accepted = {image_format.extension}
        if image_format.key == "jpeg":
            accepted.add(".jpeg")
        if image_format.key == "tiff":
            accepted.add(".tif")
        extension = os.path.splitext(destination)[1].lower()
        if extension and extension not in accepted:
            warnings.append("extension %s inattendue : le fichier contiendra du "
                            "%s." % (extension, image_format.label))
        self._busy = True
        self.progress.set_indeterminate(False)
        self.progress.set_value(0)
        self._refresh_controls()
        self.status.setText("Conversion en cours…")
        self._convert_worker = ImageConvertWorker(
            self._info.path, destination, self._format_key, self._settings(),
            self)
        self._convert_worker.progress.connect(self._on_progress)
        self._convert_worker.done.connect(self._on_finished)
        self._convert_worker.failed.connect(self._on_failed)
        self._convert_worker.start()
        if warnings:
            self._set_note("Encodage %s… · %s"
                           % (image_format.label, " · ".join(warnings)),
                           theme.COLORS["amber"])
        else:
            self._set_note("Encodage %s…" % image_format.label)

    def _on_progress(self, fraction, message):
        self.progress.set_value(fraction)
        self.status.setText(message)

    def _on_finished(self, result):
        self._busy = False
        self.progress.set_value(1.0)
        self._estimate = result["size"]
        self._update_compare()
        self.status.setText("Terminé — %s · %d × %d px · %s"
                            % (result["format"].label, result["width"],
                               result["height"],
                               engine.human_size(result["size"])))
        delta = engine.delta_label(result["source_size"], result["size"])
        self._set_note("Fichier écrit : %s (%s)"
                       % (os.path.basename(result["path"]), delta),
                       theme.COLORS["green"])
        self.statusMessage.emit("Conversion terminée")
        self._refresh_controls()

    def _on_failed(self, message):
        self._busy = False
        self.progress.set_value(0)
        self.status.setText("Échec de la conversion")
        self._set_note(message, theme.COLORS["red"])
        self.statusMessage.emit("Échec de la conversion")
        self._refresh_controls()

    # -- glisser-déposer --------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.load_source(path)
                break
        event.acceptProposedAction()
