"""Page « Audio » : source, format, réglages, conversion."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from ... import batch, jobs
from ...audio import formats
from .. import theme, widgets
from ..worker import ConvertWorker, DescribeWorker

FILE_FILTER = (
    "Médias pris en charge (*.aup3 *.aup3unsaved *.aup4 *.aup4unsaved "
    "*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aiff *.aif *.wma *.mp4 *.mkv *.webm);;"
    "Projets Audacity (*.aup3 *.aup3unsaved *.aup4 *.aup4unsaved);;"
    "Fichiers audio (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aiff *.aif *.wma);;"
    "Tous les fichiers (*)"
)


class SourceCard(QFrame):
    """Carte affichant la source chargée (remplace la zone de dépôt)."""

    changeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.glyph = widgets.GlyphWidget("audio", theme.COLORS["cyan"], 26)
        top.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.title = QLabel("—")
        self.title.setObjectName("H2")
        self.path = QLabel("")
        self.path.setObjectName("Mono")
        text_column.addWidget(self.title)
        text_column.addWidget(self.path)
        top.addLayout(text_column, 1)

        self.kind_pill = widgets.Pill("source", theme.COLORS["cyan"])
        top.addWidget(self.kind_pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self.details = QLabel("")
        self.details.setObjectName("Faint")
        self.details.setWordWrap(True)
        self.details.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Maximum)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)

        bottom = QHBoxLayout()
        self.change = widgets.GhostButton("Changer de fichier", icon_kind="folder")
        self.change.clicked.connect(self.changeRequested)
        bottom.addWidget(self.change)
        self.meta = QLabel("")
        self.meta.setObjectName("Faint")
        bottom.addWidget(self.meta, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bottom)

    def set_source(self, info):
        self.title.setText(info.title)
        self.path.setText(widgets.elide(info.path, 72))
        self.kind_pill.setText(info.kind_label.upper())
        self.kind_pill.set_tint(theme.COLORS["cyan"] if info.kind == "audacity"
                                else theme.COLORS["violet"])
        self.glyph.set_color(theme.COLORS["cyan"] if info.kind == "audacity"
                             else theme.COLORS["violet"])
        lines = list(info.details)
        if len(lines) > 5:
            lines = lines[:5] + ["… %d ligne(s) supplémentaire(s)" % (len(info.details) - 5)]
        self.details.setText("\n".join(lines))
        self.setToolTip("\n".join(info.details))
        bits = [info.duration_label]
        if info.sample_rate:
            bits.append("%s Hz" % int(info.sample_rate))
        if info.channels:
            bits.append("%d canal%s" % (info.channels,
                                        "x" if info.channels > 2 else
                                        ("s" if info.channels > 1 else "")))
        self.meta.setText(" · ".join(bits))

    def clear(self):
        self.title.setText("—")
        self.path.setText("")
        self.details.setText("")
        self.meta.setText("")


class AudioPage(QWidget):
    """Page principale : convertir un projet Audacity ou un fichier audio."""

    statusMessage = Signal(str)
    folderDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None            # SourceInfo
        self._format_key = "mp4"
        self._describe_worker = None
        self._convert_worker = None
        self._busy = False
        self._last_auto_output = ""

        self.setAcceptDrops(True)
        self._build()
        self.console.info("Prêt. Déposez un projet Audacity (.aup3/.aup4) ou un "
                          "fichier audio pour commencer.")
        self._refresh_controls()

    # -- construction ---------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(18)

        root.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addLayout(self._build_left(), 5)
        body.addLayout(self._build_right(), 4)
        root.addLayout(body, 1)

        self.console = widgets.Console()
        self.console.setFixedHeight(112)
        root.addWidget(self.console, 0)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(14)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel("Audio")
        title.setObjectName("H1")
        subtitle = QLabel("Convertir un projet Audacity ou un fichier audio vers "
                          "MP4, MP3, FLAC, WAV, Opus…")
        subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        self.engine_pill = widgets.Pill("FFMPEG", theme.COLORS["green"])
        header.addWidget(self.engine_pill, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_left(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        self.source_stack = QStackedWidget()
        self.drop_zone = widgets.DropZone()
        self.drop_zone.clicked.connect(self._browse)
        self.drop_zone.fileDropped.connect(self.load_source)
        self.drop_zone.folderDropped.connect(self.folderDropped.emit)
        self.source_card = SourceCard()
        self.source_card.changeRequested.connect(self._browse)
        self.source_stack.addWidget(self.drop_zone)
        self.source_stack.addWidget(self.source_card)
        column.addWidget(self.source_stack, 0)

        column.addWidget(widgets.SectionLabel("Format de sortie"))
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self._format_group = QButtonGroup(self)
        self._format_group.setExclusive(True)
        self._format_cards = {}
        for index, audio_format in enumerate(formats.FORMATS):
            card = widgets.FormatCard(audio_format)
            card.setChecked(audio_format.key == self._format_key)
            card.clicked.connect(
                lambda _checked=False, key=audio_format.key: self.set_format(key))
            self._format_group.addButton(card)
            self._format_cards[audio_format.key] = card
            grid.addWidget(card, index // 3, index % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        column.addWidget(grid_host, 1)

        self.format_hint = QLabel("")
        self.format_hint.setObjectName("Faint")
        self.format_hint.setWordWrap(True)
        column.addWidget(self.format_hint)

        self._update_format_hint()
        return column

    def _build_right(self):
        column = QVBoxLayout()
        column.setSpacing(14)

        settings = widgets.Card()
        settings.body().addWidget(widgets.SectionLabel("Réglages"))
        row = QGridLayout()
        row.setHorizontalSpacing(12)
        row.setVerticalSpacing(10)

        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(list(formats.BITRATE_CHOICES))
        self.bitrate_combo.setCurrentText(formats.get_format("mp4").default_bitrate)
        self.bitrate_combo.currentTextChanged.connect(self._options_changed)

        self.depth_combo = QComboBox()
        for label, value in formats.DEPTH_CHOICES:
            self.depth_combo.addItem(label, value)
        self.depth_combo.setCurrentIndex(1)
        self.depth_combo.currentIndexChanged.connect(self._options_changed)

        self.rate_combo = QComboBox()
        for label, value in formats.RATE_CHOICES:
            self.rate_combo.addItem(label, value)
        self.rate_combo.currentIndexChanged.connect(self._options_changed)

        row.addWidget(widgets.labelled("Débit", self.bitrate_combo), 0, 0)
        row.addWidget(widgets.labelled("Profondeur", self.depth_combo), 0, 1)
        row.addWidget(widgets.labelled("Fréquence", self.rate_combo), 1, 0)
        self.mono_check = QCheckBox("Mixe en mono")
        self.mono_check.stateChanged.connect(self._options_changed)
        mono_host = widgets.labelled("Canaux", self.mono_check)
        row.addWidget(mono_host, 1, 1)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 1)
        settings.add_layout(row)
        column.addWidget(settings)

        output = widgets.Card()
        output.body().addWidget(widgets.SectionLabel("Fichier de sortie"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("chemin du fichier à créer")
        self.output_edit.textChanged.connect(lambda _text: self._refresh_controls())
        output.add(self.output_edit)
        browse_row = QHBoxLayout()
        self.browse_output = widgets.GhostButton("Choisir…", icon_kind="folder")
        self.browse_output.clicked.connect(self._browse_output)
        browse_row.addWidget(self.browse_output)
        self.size_hint = QLabel("")
        self.size_hint.setObjectName("Faint")
        browse_row.addWidget(self.size_hint, 1, Qt.AlignmentFlag.AlignRight)
        output.add_layout(browse_row)
        column.addWidget(output)

        action = widgets.Card()
        self.convert_button = widgets.NeonButton("Convertir", icon_kind="spark")
        self.convert_button.clicked.connect(self.start_conversion)
        action.add(self.convert_button)
        self.progress = widgets.GradientProgress()
        action.add(self.progress)
        self.status = QLabel("En attente d'un fichier")
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        action.add(self.status)
        column.addWidget(action)

        column.addStretch(1)
        return column

    # -- état -----------------------------------------------------------
    def _current_options(self):
        return {
            "bitrate": self.bitrate_combo.currentText(),
            "depth": self.depth_combo.currentData(),
            "sample_rate": self.rate_combo.currentData(),
            "mono": self.mono_check.isChecked(),
        }

    def batch_template(self):
        """Réglages actuels, réutilisables pour un dossier entier."""
        audio_format = formats.get_format(self._format_key)
        options = self._current_options()
        bits = []
        if audio_format.supports_bitrate:
            bits.append(options["bitrate"])
        if audio_format.supports_depth:
            bits.append("%s bits" % options["depth"])
        if options["sample_rate"]:
            bits.append("%s Hz" % int(options["sample_rate"]))
        if options["mono"]:
            bits.append("mono")
        summary = "Page Audio · " + " · ".join(bits) if bits else "Page Audio"
        return batch.BatchTemplate("audio", self._format_key, summary, options)

    def _refresh_controls(self):
        audio_format = formats.get_format(self._format_key)
        self.bitrate_combo.setEnabled(audio_format.supports_bitrate)
        self.depth_combo.setEnabled(audio_format.supports_depth)
        self.browse_output.setEnabled(not self._busy)
        self.convert_button.setEnabled(
            not self._busy and self._source is not None
            and bool(self.output_edit.text().strip()))
        self.convert_button.setText("Conversion…" if self._busy else "Convertir")
        self._update_size_hint()

    def _update_size_hint(self):
        info = self._source
        if not info or not info.duration:
            self.size_hint.setText("")
            return
        audio_format = formats.get_format(self._format_key)
        seconds = info.duration
        if audio_format.supports_bitrate:
            bitrate = self.bitrate_combo.currentText().rstrip("k")
            estimate = float(bitrate or 192) * 1000 / 8 * seconds
        elif audio_format.family == "pcm":
            depth = {"16": 2, "24": 3, "32f": 4}.get(self.depth_combo.currentData(), 3)
            estimate = seconds * (info.sample_rate or 44100) * depth * (
                1 if self.mono_check.isChecked() else 2)
        else:  # flac, alac
            estimate = seconds * (info.sample_rate or 44100) * 3 * (
                1 if self.mono_check.isChecked() else 2) * 0.6
        self.size_hint.setText("≈ %.1f Mio" % (estimate / (1024 * 1024)))

    def set_format(self, key):
        if key == self._format_key:
            return
        self._format_key = key
        card = self._format_cards.get(key)
        if card is not None and not card.isChecked():
            card.setChecked(True)
        self._update_format_hint()
        self._sync_auto_output()
        self._refresh_controls()

    def _sync_auto_output(self):
        if not self._source:
            return
        suggested = jobs.default_output_path(self._source.path, self._format_key)
        current = self.output_edit.text().strip()
        if not current or current == self._last_auto_output:
            self._last_auto_output = suggested
            self.output_edit.setText(suggested)

    def _options_changed(self, *_args):
        self._update_size_hint()

    def _update_format_hint(self):
        audio_format = formats.get_format(self._format_key)
        self.format_hint.setText("%s — %s" % (audio_format.label,
                                              audio_format.description))

    # -- chargement d'une source ---------------------------------------
    def load_source(self, path):
        if self._busy:
            return
        path = os.fspath(path)
        self.console.divider()
        self.console.info("Analyse de %s…" % widgets.elide(path, 60))
        self.status.setText("Analyse du fichier…")
        self.progress.set_indeterminate(True)
        self._describe_worker = DescribeWorker(path, self)
        self._describe_worker.done.connect(self._source_ready)
        self._describe_worker.failed.connect(self._source_failed)
        self._describe_worker.start()

    def _source_ready(self, info):
        self.progress.set_indeterminate(False)
        self.progress.set_value(0)
        self._source = info
        self.source_card.set_source(info)
        self.source_stack.setCurrentWidget(self.source_card)
        self.console.accent("%s · %s · %s" % (info.kind_label, info.title,
                                              info.duration_label))
        for line in info.details:
            self.console.info(line)
        for warning in info.warnings:
            self.console.warn(warning)
        self._last_auto_output = ""
        self._sync_auto_output()
        self.status.setText("Prêt à convertir")
        self.statusMessage.emit("Source chargée")
        self._refresh_controls()

    def _source_failed(self, message):
        self.progress.set_indeterminate(False)
        self._source = None
        self.source_stack.setCurrentWidget(self.drop_zone)
        self.status.setText("Impossible de lire ce fichier")
        self.console.error(message)
        self._refresh_controls()

    def _browse(self):
        path, _selected = QFileDialog.getOpenFileName(
            self, "Choisir un média", "", FILE_FILTER)
        if path:
            self.load_source(path)

    def _browse_output(self):
        audio_format = formats.get_format(self._format_key)
        suggested = self.output_edit.text().strip() or (
            jobs.default_output_path(self._source.path, self._format_key)
            if self._source else "")
        path, _selected = QFileDialog.getSaveFileName(
            self, "Fichier de sortie", suggested,
            "%s (*%s);;Tous les fichiers (*)" % (audio_format.label,
                                                 audio_format.extension))
        if path:
            self.output_edit.setText(path)
            self._last_auto_output = path

    # -- conversion -----------------------------------------------------
    def start_conversion(self):
        if self._busy or not self._source:
            return
        destination = self.output_edit.text().strip()
        if not destination:
            self.console.error("Choisissez d'abord un fichier de sortie.")
            return
        if os.path.abspath(destination) == os.path.abspath(self._source.path):
            self.console.error("Le fichier de sortie ne peut pas être la source.")
            return
        if os.path.exists(destination):
            self.console.warn("%s existe déjà : il sera remplacé."
                              % os.path.basename(destination))

        options = self._current_options()
        self._busy = True
        self.progress.set_indeterminate(False)
        self.progress.set_value(0)
        self._refresh_controls()
        self.status.setText("Conversion en cours…")
        self.console.divider()
        self.console.accent("Conversion → %s (%s)"
                            % (formats.get_format(self._format_key).label,
                               options["bitrate"] if
                               formats.get_format(self._format_key).supports_bitrate
                               else options["depth"]))

        self._convert_worker = ConvertWorker(
            self._source.path, destination, self._format_key, options, self)
        self._convert_worker.progress.connect(self._on_progress)
        self._convert_worker.done.connect(self._on_finished)
        self._convert_worker.failed.connect(self._on_failed)
        self._convert_worker.start()

    def _on_progress(self, fraction, message):
        self.progress.set_value(fraction)
        self.status.setText(message)

    def _on_finished(self, result):
        self._busy = False
        self.progress.set_value(1.0)
        audio_format = result["format"]
        size = result["size"] / (1024 * 1024)
        self.status.setText("Terminé — %s (%.1f Mio)" % (audio_format.label, size))
        self.console.ok("%s → %s · %.1f Mio en %.1f s"
                        % (audio_format.label, widgets.elide(result["path"], 48),
                           size, result["elapsed"]))
        for warning in result.get("warnings", []):
            self.console.warn(warning)
        self.statusMessage.emit("Conversion terminée")
        self._refresh_controls()

    def _on_failed(self, message):
        self._busy = False
        self.progress.set_value(0)
        self.status.setText("Échec de la conversion")
        self.console.error(message)
        self.statusMessage.emit("Échec de la conversion")
        self._refresh_controls()

    # -- glisser-déposer sur toute la page -----------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                if os.path.isdir(path):
                    self.folderDropped.emit(path)
                else:
                    self.load_source(path)
                break
        event.acceptProposedAction()
