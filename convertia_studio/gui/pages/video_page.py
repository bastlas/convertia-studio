"""Page « Vidéo » : découpe, recadrage, compression et conversion."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QSizePolicy, QSlider,
                               QStackedWidget, QVBoxLayout, QWidget)

from ...image import engine as image_engine
from ...video import engine, formats
from .. import theme, widgets
from ..worker import (VideoConvertWorker, VideoDescribeWorker,
                      VideoThumbWorker)

FILE_FILTER = (
    "Vidéos (*.mp4 *.m4v *.mkv *.webm *.mov *.avi *.wmv *.flv *.mpg *.mpeg "
    "*.ts *.m2ts *.3gp *.ogv);;Tous les fichiers (*)"
)

SIZE_PRESETS = (
    ("Originale", None),
    ("HD", (1280, 720)),
    ("Full HD", (1920, 1080)),
    ("2K", (2560, 1440)),
    ("Ultra HD", (3840, 2160)),
    ("8K", (7680, 4320)),
    ("Portrait", (1080, 1920)),
    ("Carré", (1080, 1080)),
)
CUSTOM_SIZE = "custom"

ANGLES = (("Aucune", 0), ("90° horaire", 90), ("180°", 180),
          ("90° antihoraire", 270))

SPEEDS = (("0,5×", 0.5), ("1×", 1.0), ("1,5×", 1.5), ("2×", 2.0))

FPS_CHOICES = (("Originale", None), ("24", 24), ("25", 25), ("30", 30),
               ("50", 50), ("60", 60))


class VideoSourceCard(QFrame):
    """Carte affichant la vidéo chargée."""

    changeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.glyph = widgets.GlyphWidget("video", theme.COLORS["magenta"], 24)
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
        self.kind_pill = widgets.Pill("VIDÉO", theme.COLORS["magenta"])
        top.addWidget(self.kind_pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self.details = QLabel("")
        self.details.setObjectName("Faint")
        self.details.setWordWrap(True)
        self.details.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Maximum)
        layout.addWidget(self.details)

        bottom = QHBoxLayout()
        self.change = widgets.small_ghost("Changer de vidéo", "folder")
        self.change.clicked.connect(self.changeRequested)
        bottom.addWidget(self.change)
        self.meta = QLabel("")
        self.meta.setObjectName("Faint")
        bottom.addWidget(self.meta, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bottom)

    def set_source(self, info):
        self.title.setText(info.title)
        self.path.setText(widgets.elide(info.path, 66))
        self.details.setText("\n".join(info.details[:3]))
        self.setToolTip("\n".join(info.details))
        self.meta.setText("%s · %s · %s" % (info.dimensions,
                                            info.duration_label,
                                            info.size_label))

    def clear(self):
        self.title.setText("—")
        self.path.setText("")
        self.details.setText("")
        self.meta.setText("")


class VideoPage(QWidget):
    """Page principale : préparer et convertir une vidéo."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info = None
        self._format_key = "mp4"
        self._busy = False
        self._estimate = None
        self._last_auto_output = ""
        self._loading = False
        self._last_target = (0, 0)

        self._describe_worker = None
        self._convert_worker = None
        self._thumb_worker = None
        self._thumb_pending = False
        self._thumb_token = 0

        self.setAcceptDrops(True)
        self._build()

        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(260)
        self._thumb_timer.timeout.connect(self._start_thumbnail)

        self._set_note("Déposez une vidéo pour commencer.")
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
        body.addWidget(self._build_right(), 4)
        root.addLayout(body, 1)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(14)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Vidéo")
        title.setObjectName("H1")
        subtitle = QLabel("Découper, recadrer, compresser et convertir vos "
                          "vidéos — avec aperçu, vignette et poids estimé.")
        subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        header.addWidget(widgets.Pill("FFMPEG", theme.COLORS["green"]), 0,
                         Qt.AlignmentFlag.AlignTop)
        return header

    def _build_left(self):
        column = QVBoxLayout()
        column.setSpacing(12)

        self.source_stack = QStackedWidget()
        self.drop_zone = widgets.DropZone(
            glyph="video", title="Déposez une vidéo ici",
            subtitle="MP4, MKV, WebM, MOV, AVI… — ou cliquez pour parcourir")
        self.drop_zone.clicked.connect(self.browse)
        self.drop_zone.fileDropped.connect(self.load_source)
        self.source_card = VideoSourceCard()
        self.source_card.changeRequested.connect(self.browse)
        self.source_stack.addWidget(self.drop_zone)
        self.source_stack.addWidget(self.source_card)
        column.addWidget(self.source_stack, 0)

        preview_card = widgets.Card(padding=14, spacing=8)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(widgets.SectionLabel("Aperçu"))
        self.preview_time = QLabel("—")
        self.preview_time.setObjectName("Faint")
        head.addWidget(self.preview_time)
        head.addStretch(1)
        self.grab_button = widgets.small_ghost("Extraire l'image", "image")
        self.grab_button.setToolTip("Enregistrer l'image affichée en PNG")
        self.grab_button.clicked.connect(self._grab_frame)
        head.addWidget(self.grab_button)
        preview_card.add_layout(head)

        self.preview = widgets.PreviewPane()
        self.preview.setMinimumHeight(120)
        self.preview.set_empty("Déposez une vidéo pour voir une image.")
        preview_card.body().addWidget(self.preview, 1)

        scrub = QHBoxLayout()
        scrub.setSpacing(8)
        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setRange(0, 999)
        self.scrub_slider.setValue(0)
        self.scrub_slider.valueChanged.connect(self._scrub_changed)
        scrub.addWidget(self.scrub_slider, 1)
        self.scrub_time = QLabel("—")
        self.scrub_time.setObjectName("Mono")
        self.scrub_time.setMinimumWidth(92)
        self.scrub_time.setAlignment(Qt.AlignmentFlag.AlignRight |
                                     Qt.AlignmentFlag.AlignVCenter)
        scrub.addWidget(self.scrub_time)
        preview_card.add_layout(scrub)

        trim = QHBoxLayout()
        trim.setSpacing(6)
        caption = QLabel("DÉCOUPE")
        caption.setObjectName("SectionLabel")
        caption.setFixedWidth(58)
        trim.addWidget(caption)
        self.start_spin = self._time_spin()
        self.end_spin = self._time_spin()
        self.start_spin.valueChanged.connect(self._trim_changed)
        self.end_spin.valueChanged.connect(self._trim_changed)
        trim.addWidget(self.start_spin, 1)
        arrow = QLabel("→")
        arrow.setObjectName("Faint")
        trim.addWidget(arrow)
        trim.addWidget(self.end_spin, 1)
        self.start_here = widgets.small_ghost("Début ici")
        self.start_here.setToolTip("Utiliser la position de l'aperçu comme début")
        self.start_here.clicked.connect(lambda: self._set_trim_edge("start"))
        trim.addWidget(self.start_here)
        self.end_here = widgets.small_ghost("Fin ici")
        self.end_here.setToolTip("Utiliser la position de l'aperçu comme fin")
        self.end_here.clicked.connect(lambda: self._set_trim_edge("end"))
        trim.addWidget(self.end_here)
        preview_card.add_layout(trim)
        column.addWidget(preview_card, 1)

        column.addWidget(widgets.SectionLabel("Format de sortie"))
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self._format_group = QButtonGroup(self)
        self._format_group.setExclusive(True)
        self._format_cards = {}
        for index, video_format in enumerate(formats.FORMATS):
            card = widgets.FormatCard(video_format)
            card.setMinimumHeight(76)
            card.setMaximumHeight(76)
            if not engine.format_supported(video_format.key):
                card.setEnabled(False)
                card.setToolTip("%s n'est pas disponible dans le ffmpeg "
                                "installé." % video_format.label)
            card.setChecked(video_format.key == self._format_key)
            card.clicked.connect(
                lambda _checked=False, key=video_format.key: self.set_format(key))
            self._format_group.addButton(card)
            self._format_cards[video_format.key] = card
            grid.addWidget(card, index // 2, index % 2)
        for col in range(2):
            grid.setColumnStretch(col, 1)
        column.addWidget(grid_host, 0)

        self.format_hint = QLabel("")
        self.format_hint.setObjectName("Faint")
        self.format_hint.setWordWrap(True)
        column.addWidget(self.format_hint)
        self._update_format_hint()
        return column

    def _time_spin(self):
        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setRange(0.0, 359999.0)
        spin.setSuffix(" s")
        spin.setKeyboardTracking(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setFixedWidth(92)
        return spin

    def _build_right(self):
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)

        settings = widgets.Card(padding=12, spacing=6)
        settings.body().addWidget(widgets.SectionLabel("Encodage"))

        self.crf_slider = QSlider(Qt.Orientation.Horizontal)
        self.crf_slider.setValue(23)
        self.crf_slider.valueChanged.connect(self._crf_changed)
        self.crf_value = QLabel("CRF 23")
        self.crf_value.setObjectName("Mono")
        self.crf_value.setMinimumWidth(72)
        self.crf_value.setAlignment(Qt.AlignmentFlag.AlignRight |
                                    Qt.AlignmentFlag.AlignVCenter)
        self.crf_slider.setToolTip("Plus le CRF est bas, meilleure est la "
                                   "qualité et plus le fichier est lourd.")
        settings.add_layout(self._row("Qualité", self.crf_slider,
                                      self.crf_value))

        self.speed_combo = QComboBox()
        for key, (label, _preset, _cpu) in engine.SPEED_PRESETS.items():
            self.speed_combo.addItem(label, key)
        self.speed_combo.setCurrentIndex(
            max(0, self.speed_combo.findData("balanced")))
        self.speed_combo.currentIndexChanged.connect(self._speed_changed)
        settings.add_layout(self._row("Vitesse", self.speed_combo))

        self.size_combo = QComboBox()
        for label, value in SIZE_PRESETS:
            self.size_combo.addItem(label, value)
        self.size_combo.addItem("Personnalisé…", CUSTOM_SIZE)
        self.size_combo.setMinimumContentsLength(6)
        self.size_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.size_combo.setMinimumWidth(108)
        self.size_combo.setToolTip(
            "Cadre de sortie : l'image est ajustée avec des bandes noires, "
            "ou rognée si « Remplir » est coché.")
        self.size_combo.currentIndexChanged.connect(self._size_mode_changed)
        self.size_result = QLabel("—")
        self.size_result.setObjectName("Mono")
        self.size_result.setMinimumWidth(86)
        self.size_result.setAlignment(Qt.AlignmentFlag.AlignRight |
                                      Qt.AlignmentFlag.AlignVCenter)
        settings.add_layout(self._row("Taille :", self.size_combo,
                                      self.size_result))

        self.width_spin = self._dimension_spin()
        self.height_spin = self._dimension_spin()
        self.width_spin.valueChanged.connect(self._width_changed)
        self.height_spin.valueChanged.connect(self._height_changed)
        self.lock_ratio = QCheckBox("Lier")
        self.lock_ratio.setChecked(True)
        cross = QLabel("×")
        cross.setObjectName("Faint")
        custom_layout = QHBoxLayout()
        custom_layout.setContentsMargins(12, 0, 0, 0)
        custom_layout.setSpacing(6)
        custom_layout.addWidget(self.width_spin, 1)
        custom_layout.addWidget(cross, 0)
        custom_layout.addWidget(self.height_spin, 1)
        custom_layout.addWidget(self.lock_ratio, 0)
        self.custom_dims = QWidget()
        self.custom_dims.setLayout(custom_layout)
        self.custom_dims.setVisible(False)
        settings.add(self.custom_dims)

        self.fill_check = QCheckBox("Remplir le cadre (rogner les bords)")
        self.fill_check.setToolTip(
            "Décoché : image entière avec des bandes noires. Coché : "
            "l'image remplit le cadre et les bords sont rognés.")
        self.fill_check.setVisible(False)
        self.fill_check.stateChanged.connect(self._settings_changed)
        settings.add(self.fill_check)

        self.fps_combo = QComboBox()
        for label, value in FPS_CHOICES:
            self.fps_combo.addItem(label, value)
        self.fps_combo.currentIndexChanged.connect(self._settings_changed)
        settings.add_layout(self._row("Images/s", self.fps_combo))

        self.angle_combo = QComboBox()
        for label, value in ANGLES:
            self.angle_combo.addItem(label, value)
        self.angle_combo.currentIndexChanged.connect(self._rotation_changed)
        self.speed_factor_combo = QComboBox()
        for label, value in SPEEDS:
            self.speed_factor_combo.addItem(label, value)
        self.speed_factor_combo.currentIndexChanged.connect(self._speed_factor_changed)
        settings.add_layout(self._row("Rotation", self.angle_combo,
                                      self.speed_factor_combo))

        self.audio_combo = QComboBox()
        self.audio_combo.currentIndexChanged.connect(self._settings_changed)
        settings.add_layout(self._row("Audio", self.audio_combo))
        column.addWidget(settings)

        output = widgets.Card(padding=12, spacing=6)
        output.body().addWidget(widgets.SectionLabel("Sortie et conversion"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("chemin du fichier à créer")
        self.output_edit.textChanged.connect(lambda _text: self._refresh_controls())
        output.add(self.output_edit)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self.browse_output = widgets.small_ghost("Choisir…", "folder")
        self.browse_output.clicked.connect(self._browse_output)
        output_row.addWidget(self.browse_output)
        output_row.addStretch(1)
        self.delta_pill = widgets.Pill("—", theme.COLORS["text_faint"])
        output_row.addWidget(self.delta_pill)
        output.add_layout(output_row)

        self.compare_bars = widgets.CompareBars()
        output.add(self.compare_bars)

        self.convert_button = widgets.NeonButton("Convertir la vidéo",
                                                 icon_kind="spark")
        self.convert_button.clicked.connect(self.start_conversion)
        output.add(self.convert_button)
        self.progress = widgets.GradientProgress()
        output.add(self.progress)
        self.status = QLabel("En attente d'une vidéo")
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        output.add(self.status)
        self.note = QLabel("")
        self.note.setObjectName("Faint")
        self.note.setWordWrap(True)
        self.note.setMaximumHeight(26)
        output.add(self.note)
        column.addWidget(output)

        column.addStretch(1)
        return widgets.scroll_column(content)

    def _dimension_spin(self):
        spin = QDoubleSpinBox()
        spin.setDecimals(0)
        spin.setSingleStep(2)
        spin.setRange(16, 16384)
        spin.setKeyboardTracking(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Fixed)
        spin.setMinimumWidth(56)
        return spin

    def _row(self, caption, *items):
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel(caption.upper())
        label.setObjectName("SectionLabel")
        label.setFixedWidth(70)
        row.addWidget(label)
        for item in items:
            if isinstance(item, (QComboBox, QSlider, QDoubleSpinBox)):
                if isinstance(item, QComboBox):
                    item.setSizePolicy(QSizePolicy.Policy.Ignored,
                                       QSizePolicy.Policy.Fixed)
                    item.setMinimumWidth(88)
                row.addWidget(item, 1)
            else:
                row.addWidget(item, 0)
        return row

    # -- état -----------------------------------------------------------
    def _size_mode(self):
        data = self.size_combo.currentData()
        if data == CUSTOM_SIZE:
            return "custom"
        if data is None:
            return "original"
        return "preset"

    def _base_output_size(self):
        if not self._info:
            return 1920, 1080
        width, height = self._info.width, self._info.height
        if int(self.angle_combo.currentData() or 0) % 180 == 90:
            width, height = height, width
        return width, height

    def _frame_size(self):
        """Cadre demandé (None, None si taille d'origine)."""
        mode = self._size_mode()
        if mode == "original":
            return None, None
        if mode == "preset":
            return self.size_combo.currentData()
        return (int(self.width_spin.value()), int(self.height_spin.value()))

    def _settings(self):
        width, height = self._frame_size()
        audio_mode, audio_bitrate = self.audio_combo.currentData() or (
            "auto", None)
        end = None
        if self._info and self._info.duration:
            value = float(self.end_spin.value())
            if value < self._info.duration - 0.05:
                end = value
        return engine.VideoSettings(
            crf=self.crf_slider.value(),
            speed=self.speed_combo.currentData() or "balanced",
            width=width, height=height, fill=self.fill_check.isChecked(),
            fps=self.fps_combo.currentData(),
            rotation=int(self.angle_combo.currentData() or 0),
            speed_factor=float(self.speed_factor_combo.currentData() or 1.0),
            start=float(self.start_spin.value()),
            end=end,
            audio_mode=audio_mode, audio_bitrate=audio_bitrate)

    def _update_size_result(self):
        if not self._info:
            self.size_result.setText("—")
            return
        width, height = engine.target_size(self._info, self._settings())
        self.size_result.setText("%d×%d px" % (width, height))
        self._last_target = (width, height)

    def _sync_dims(self):
        width, height = self._base_output_size()
        self._loading = True
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        self._loading = False
        self._update_size_result()

    def _size_mode_changed(self, _index=None):
        mode = self._size_mode()
        custom = mode == "custom"
        self.custom_dims.setVisible(custom)
        self.fill_check.setVisible(mode != "original")
        if custom:
            width, height = self._last_target or self._base_output_size()
            self._loading = True
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)
            self._loading = False
        self._update_size_result()
        self._refresh_controls()
        self._settings_changed()

    def _width_changed(self, value):
        if self._loading or not self._info:
            return
        if self.lock_ratio.isChecked():
            width, height = self._base_output_size()
            self._loading = True
            self.height_spin.setValue(max(2, round(value * height / width)))
            self._loading = False
        self._update_size_result()
        self._settings_changed()

    def _height_changed(self, value):
        if self._loading or not self._info:
            return
        if self.lock_ratio.isChecked():
            width, height = self._base_output_size()
            self._loading = True
            self.width_spin.setValue(max(2, round(value * width / height)))
            self._loading = False
        self._update_size_result()
        self._settings_changed()

    def _rotation_changed(self, _index=None):
        self._update_size_result()
        self._settings_changed()

    def _speed_changed(self, _index=None):
        self._refresh_audio_combo()
        self._settings_changed()

    def _speed_factor_changed(self, _index=None):
        self._refresh_audio_combo()
        self._settings_changed()

    def _crf_changed(self, value):
        self.crf_value.setText("CRF %d" % value)
        self._settings_changed()

    def _settings_changed(self, *_args):
        if not self._info or self._busy:
            return
        info = self._info
        settings = self._settings()
        self._estimate = engine.estimate_size(info, self._format_key, settings)
        self._update_compare()

    def _set_note(self, text, tint=None):
        self.note.setText(text)
        self.note.setToolTip(text)
        self.note.setStyleSheet("color: %s;"
                                % (tint or theme.COLORS["text_faint"]))

    def _refresh_controls(self):
        busy = self._busy
        has_source = self._info is not None
        custom = has_source and not busy and self._size_mode() == "custom"
        for spin in (self.width_spin, self.height_spin):
            spin.setEnabled(custom)
        self.lock_ratio.setEnabled(custom)
        for widget in (self.size_combo, self.speed_combo, self.fps_combo,
                       self.angle_combo, self.speed_factor_combo):
            widget.setEnabled(has_source and not busy)
        self.crf_slider.setEnabled(has_source and not busy)
        self.fill_check.setEnabled(has_source and not busy)
        self.audio_combo.setEnabled(has_source and not busy
                                    and self._info.has_audio)
        self.browse_output.setEnabled(not busy)
        self.output_edit.setEnabled(not busy)
        self.start_spin.setEnabled(has_source and not busy)
        self.end_spin.setEnabled(has_source and not busy)
        self.scrub_slider.setEnabled(has_source and not busy)
        self.grab_button.setEnabled(has_source and not busy)
        self.start_here.setEnabled(has_source and not busy)
        self.end_here.setEnabled(has_source and not busy)
        for card in self._format_cards.values():
            card.setEnabled(not busy and engine.format_supported(
                card.format.key))
        self.convert_button.setEnabled(
            not busy and has_source and bool(self.output_edit.text().strip()))
        self.convert_button.setText("Conversion…" if busy
                                    else "Convertir la vidéo")

    def _update_format_hint(self):
        video_format = formats.get_format(self._format_key)
        self.format_hint.setText("%s — %s" % (video_format.label,
                                              video_format.description))

    def set_format(self, key):
        if key == self._format_key:
            return
        self._format_key = key
        card = self._format_cards.get(key)
        if card is not None and not card.isChecked():
            card.setChecked(True)
        video_format = formats.get_format(key)
        self.crf_slider.blockSignals(True)
        self.crf_slider.setRange(video_format.crf_min, video_format.crf_max)
        self.crf_slider.setValue(video_format.default_crf)
        self.crf_slider.blockSignals(False)
        self.crf_value.setText("CRF %d" % video_format.default_crf)
        self._update_format_hint()
        self._refresh_audio_combo()
        self._sync_auto_output()
        self._update_size_result()
        self._refresh_controls()
        if self._info:
            self._settings_changed()

    def _refresh_audio_combo(self):
        video_format = formats.get_format(self._format_key)
        previous = self.audio_combo.currentData()
        previous_bitrate = previous[1] if previous else None
        speed_factor = float(self.speed_factor_combo.currentData() or 1.0)
        self.audio_combo.blockSignals(True)
        self.audio_combo.clear()
        if self._info is not None and not self._info.has_audio:
            self.audio_combo.addItem("Aucune piste audio", ("none", None))
            self.audio_combo.blockSignals(False)
            return
        codec = "Opus" if video_format.audio_codec == "libopus" else "AAC"
        for bitrate in video_format.audio_bitrates:
            self.audio_combo.addItem("%s %s kb/s" % (codec, bitrate[:-1]),
                                     ("auto", bitrate))
        if (self._info is not None
                and engine.audio_copy_supported(self._info, video_format)
                and abs(speed_factor - 1.0) < 1e-6):
            self.audio_combo.addItem("Copier la piste source", ("copy", None))
        self.audio_combo.addItem("Sans audio", ("none", None))
        target = video_format.default_audio_bitrate
        index = -1
        if previous and previous[0] == "copy":
            index = self._audio_index("copy")
        if index < 0 and previous and previous[0] == "none":
            index = self._audio_index("none")
        if index < 0 and previous_bitrate:
            index = self._audio_index("auto", previous_bitrate)
        if index < 0:
            index = self._audio_index("auto", target)
        self.audio_combo.setCurrentIndex(max(0, index))
        self.audio_combo.blockSignals(False)

    def _audio_index(self, mode, bitrate=None):
        """Index d'une entrée audio (les tuples ne marchent pas avec findData)."""
        for index in range(self.audio_combo.count()):
            data = self.audio_combo.itemData(index)
            if not data or data[0] != mode:
                continue
            if bitrate is None or data[1] == bitrate:
                return index
        return -1

    def _sync_auto_output(self):
        if not self._info:
            return
        suggested = engine.default_output_path(self._info.path,
                                               self._format_key)
        current = self.output_edit.text().strip()
        if not current or current == self._last_auto_output:
            self._last_auto_output = suggested
            self.output_edit.setText(suggested)

    # -- chargement ------------------------------------------------------
    def load_source(self, path):
        if self._busy:
            return
        path = os.fspath(path)
        if not formats.is_supported_input(path):
            self._set_note("Extension non vidéo : %s"
                           % widgets.elide(os.path.basename(path), 40),
                           theme.COLORS["amber"])
            return
        self._set_note("Analyse de la vidéo…")
        self.status.setText("Analyse du fichier…")
        self.progress.set_indeterminate(True)
        self._describe_worker = VideoDescribeWorker(path, self)
        self._describe_worker.done.connect(self._source_ready)
        self._describe_worker.failed.connect(self._source_failed)
        self._describe_worker.start()

    def _source_ready(self, info):
        self.progress.set_indeterminate(False)
        self.progress.set_value(0)
        self._info = info
        self.source_card.set_source(info)
        self.source_stack.setCurrentWidget(self.source_card)

        duration = info.duration or 0.0
        self._loading = True
        self.start_spin.setRange(0.0, max(0.0, duration))
        self.end_spin.setRange(0.0, max(0.0, duration))
        self.start_spin.setValue(0.0)
        self.end_spin.setValue(duration)
        self._loading = False
        self.scrub_slider.blockSignals(True)
        self.scrub_slider.setRange(0, 999)
        self.scrub_slider.setValue(100 if duration else 0)
        self.scrub_slider.blockSignals(False)

        self.angle_combo.blockSignals(True)
        self.angle_combo.setCurrentIndex(0)
        self.angle_combo.blockSignals(False)
        self.speed_factor_combo.blockSignals(True)
        self.speed_factor_combo.setCurrentIndex(1)
        self.speed_factor_combo.blockSignals(False)
        self.fps_combo.blockSignals(True)
        self.fps_combo.setCurrentIndex(0)
        self.fps_combo.blockSignals(False)
        self.size_combo.blockSignals(True)
        self.size_combo.setCurrentIndex(0)
        self.size_combo.blockSignals(False)
        self.custom_dims.setVisible(False)
        self.fill_check.setVisible(False)
        self._sync_dims()

        guessed = formats.guess_format(info.path)
        if not guessed or not engine.format_supported(guessed):
            guessed = next((key for key in formats.FORMAT_KEYS
                            if engine.format_supported(key)), "mp4")
        self._format_key = ""
        self.set_format(guessed)

        self._last_auto_output = ""
        self._sync_auto_output()
        self._update_scene_labels()
        self._preview_start()

        warnings = list(info.warnings)
        self._set_note(" ; ".join(warnings) if warnings else
                       "Prêt : choisissez le format puis convertissez.",
                       theme.COLORS["amber"] if warnings else None)
        self.status.setText("Prêt à convertir")
        self.statusMessage.emit("Vidéo chargée")
        self._refresh_controls()
        self._settings_changed()

    def _source_failed(self, message):
        self.progress.set_indeterminate(False)
        self._info = None
        self.source_stack.setCurrentWidget(self.drop_zone)
        self.status.setText("Impossible de lire cette vidéo")
        self._set_note(message, theme.COLORS["red"])
        self.preview.set_empty("Déposez une vidéo pour voir une image.")
        self.preview_time.setText("—")
        self._refresh_controls()

    def browse(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "Choisir une vidéo", "", FILE_FILTER)
        if path:
            self.load_source(path)

    def _browse_output(self):
        video_format = formats.get_format(self._format_key)
        suggested = self.output_edit.text().strip() or (
            engine.default_output_path(self._info.path, self._format_key)
            if self._info else "")
        path, _selected = QFileDialog.getSaveFileName(
            self, "Fichier de sortie", suggested,
            "%s (*%s);;Tous les fichiers (*)" % (video_format.label,
                                                 video_format.extension))
        if path:
            self.output_edit.setText(path)
            self._last_auto_output = path

    # -- aperçu -----------------------------------------------------------
    def _position(self):
        if not self._info or not self._info.duration:
            return 0.0
        return self._info.duration * self.scrub_slider.value() / 1000.0

    def _update_scene_labels(self):
        duration = self._info.duration if self._info else None
        position = self._position()
        self.scrub_time.setText("%s / %s" % (engine.timecode(position),
                                             engine.timecode(duration)))
        self.preview_time.setText(engine.timecode(position))

    def _preview_start(self):
        self._update_scene_labels()
        self._thumb_timer.start()

    def _scrub_changed(self, _value):
        self._update_scene_labels()
        if self._info:
            self._thumb_timer.start()

    def _start_thumbnail(self):
        if not self._info or self._busy:
            return
        if self._thumb_worker is not None and self._thumb_worker.isRunning():
            self._thumb_pending = True
            return
        self._thumb_token += 1
        token = self._thumb_token
        worker = VideoThumbWorker(self._info.path, self._position(), token,
                                  parent=self)
        worker.done.connect(self._thumb_ready)
        worker.failed.connect(self._thumb_failed)
        worker.finished.connect(
            lambda worker=worker: self._thumb_finished(worker))
        self._thumb_worker = worker
        worker.start()

    def _thumb_ready(self, token, data, seconds):
        if token != self._thumb_token:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.preview.set_pixmap(
                pixmap, "APERÇU · %s" % engine.timecode(seconds))
            self.preview_time.setText(engine.timecode(seconds))

    def _thumb_finished(self, worker):
        if worker is not self._thumb_worker:
            return
        if self._thumb_pending:
            self._thumb_pending = False
            self._start_thumbnail()

    def _thumb_failed(self, token, message):
        if token == self._thumb_token:
            self._set_note("Aperçu impossible : %s" % message,
                           theme.COLORS["amber"])

    def _trim_changed(self, _value):
        if self._loading or not self._info:
            return
        if self.start_spin.value() >= self.end_spin.value():
            self._loading = True
            if self.sender() is self.start_spin:
                self.end_spin.setValue(min(self._info.duration or 0.0,
                                           self.start_spin.value() + 0.1))
            else:
                self.start_spin.setValue(max(0.0,
                                             self.end_spin.value() - 0.1))
            self._loading = False
        self._settings_changed()

    def _set_trim_edge(self, edge):
        if not self._info:
            return
        position = round(self._position(), 1)
        self._loading = True
        if edge == "start":
            self.start_spin.setValue(max(0.0, min(
                position, self.end_spin.value() - 0.1)))
        else:
            self.end_spin.setValue(min(self._info.duration or position,
                                       max(position,
                                           self.start_spin.value() + 0.1)))
        self._loading = False
        self._settings_changed()

    def _grab_frame(self):
        if not self._info:
            return
        base = os.path.splitext(os.path.basename(self._info.path))[0]
        suggested = os.path.join(os.path.dirname(os.path.abspath(
            self._info.path)), "%s-%s.png" % (base,
                                              engine.timecode(
                                                  self._position()).replace(
                                                      ":", "-")))
        path, _selected = QFileDialog.getSaveFileName(
            self, "Enregistrer l'image", suggested, "PNG (*.png)")
        if not path:
            return
        try:
            engine.grab_frame(self._info.path, self._position(), path)
        except engine.VideoError as error:
            self._set_note(str(error), theme.COLORS["red"])
            return
        self._set_note("Image enregistrée : %s" % widgets.elide(path, 44),
                       theme.COLORS["green"])

    # -- comparaison et conversion ----------------------------------------
    def _update_compare(self):
        if not self._info:
            return
        before = self._info.size
        after = self._estimate
        self.compare_bars.set_sizes(before, after, approximate=True)
        if after and before:
            self.delta_pill.setText(image_engine.delta_label(before, after))
            self.delta_pill.set_tint(theme.COLORS["green"] if after <= before
                                     else theme.COLORS["red"])
        else:
            self.delta_pill.setText("—")
            self.delta_pill.set_tint(theme.COLORS["text_faint"])

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
        video_format = formats.get_format(self._format_key)
        warnings = []
        if os.path.exists(destination):
            warnings.append("%s existe déjà : il sera remplacé."
                            % os.path.basename(destination))
        extension = os.path.splitext(destination)[1].lower()
        if extension and extension != video_format.extension:
            warnings.append("extension %s inattendue : le fichier contiendra "
                            "du %s." % (extension, video_format.label))
        self._busy = True
        self._thumb_timer.stop()
        self.progress.set_indeterminate(False)
        self.progress.set_value(0)
        self._refresh_controls()
        self.status.setText("Conversion en cours…")
        self._convert_worker = VideoConvertWorker(
            self._info.path, destination, self._format_key, self._settings(),
            self)
        self._convert_worker.progress.connect(self._on_progress)
        self._convert_worker.done.connect(self._on_finished)
        self._convert_worker.failed.connect(self._on_failed)
        self._convert_worker.start()
        self._set_note("Encodage %s…%s"
                       % (video_format.label,
                          " · " + " · ".join(warnings) if warnings else ""),
                       theme.COLORS["amber"] if warnings else None)

    def _on_progress(self, fraction, message):
        self.progress.set_value(fraction)
        self.status.setText(message)

    def _on_finished(self, result):
        self._busy = False
        self.progress.set_value(1.0)
        self._estimate = result["size"]
        self._update_compare()
        self.status.setText("Terminé — %s · %d × %d px · %s · %s"
                            % (result["format"].label, result["width"],
                               result["height"],
                               engine.format_duration(result["duration"]),
                               widgets.human_size(result["size"])))
        delta = image_engine.delta_label(result["source_size"],
                                         result["size"])
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

    # -- glisser-déposer ---------------------------------------------------
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
