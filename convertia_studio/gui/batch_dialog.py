"""Dialogue « Traiter un dossier » : images, vidéos et audio en une fois."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QVBoxLayout,
                               QWidget)

from .. import batch
from ..audio import formats as audio_formats
from ..image import formats as image_formats
from ..video import engine as video_engine
from ..video import formats as video_formats
from . import theme, widgets
from .worker import BatchWorker

KIND_ORDER = ("image", "video", "audio")
KIND_COLORS = {
    "image": theme.COLORS["violet"],
    "video": theme.COLORS["magenta"],
    "audio": theme.COLORS["cyan"],
}

KIND_NAMES = {
    "image": ("image", "images"),
    "video": ("vidéo", "vidéos"),
    "audio": ("fichier audio", "fichiers audio"),
}


def format_choices(kind):
    if kind == "image":
        return [(fmt.key, "%s (%s)" % (fmt.label, fmt.extension))
                for fmt in image_formats.FORMATS]
    if kind == "video":
        return [(fmt.key, fmt.label) for fmt in video_formats.FORMATS
                if video_engine.format_supported(fmt.key)]
    return [(fmt.key, fmt.label) for fmt in audio_formats.FORMATS]


class BatchDialog(QDialog):
    """Analyse un dossier et convertit les fichiers sélectionnés."""

    def __init__(self, folder, templates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Traiter un dossier")
        self.setModal(True)
        self.resize(940, 760)
        self._folder = os.path.abspath(folder)
        self._templates = templates
        self._scan = None
        self._cards = {}
        self._entries = []
        self._worker = None
        self._busy = False
        self._auto_checked = set()
        self._build()
        self._output_edit.setText(batch.destination_directory(self._folder))
        self._rescan()

    # -- construction ---------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Traiter un dossier")
        title.setObjectName("H1")
        subtitle = QLabel("Convertit toutes les images, vidéos et fichiers "
                          "audio du dossier avec les réglages des pages "
                          "correspondantes.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        path = QLabel(self._folder)
        path.setObjectName("Mono")
        path.setToolTip(self._folder)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        titles.addWidget(path)
        header.addLayout(titles, 1)
        header.addWidget(widgets.Pill("LOT", theme.COLORS["green"]), 0,
                         Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        options = widgets.Card(padding=12, spacing=6)
        self._recursive = QCheckBox("Inclure les sous-dossiers")
        self._recursive.setToolTip(
            "Parcourt aussi les sous-dossiers du dossier choisi.")
        self._recursive.toggled.connect(lambda _checked: self._rescan())
        options.add(self._recursive)
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        caption = QLabel("Dossier de sortie")
        caption.setObjectName("SectionLabel")
        output_row.addWidget(caption)
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("dossier où écrire les fichiers")
        self._output_edit.editingFinished.connect(self._rescan)
        output_row.addWidget(self._output_edit, 1)
        choose = widgets.small_ghost("Choisir…", "folder")
        choose.clicked.connect(self._choose_output)
        output_row.addWidget(choose)
        options.add_layout(output_row)
        root.addWidget(options)

        categories = QVBoxLayout()
        categories.setSpacing(8)
        for kind in KIND_ORDER:
            template = self._templates.get(kind)
            if template is None:
                continue
            categories.addWidget(self._build_category(kind, template))
        root.addLayout(categories)

        self._plan_label = QLabel("Analyse du dossier…")
        self._plan_label.setObjectName("Faint")
        self._plan_label.setWordWrap(True)
        root.addWidget(self._plan_label)

        self.console = widgets.Console()
        self.console.setFixedHeight(112)
        self.console.info("Sélectionnez les familles à traiter puis lancez la "
                          "conversion.")
        root.addWidget(self.console)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.progress = widgets.GradientProgress()
        progress_row.addWidget(self.progress, 1)
        self.status = QLabel("Prêt")
        self.status.setObjectName("Faint")
        progress_row.addWidget(self.status, 0)
        root.addLayout(progress_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self._cancel = widgets.GhostButton("Annuler")
        self._cancel.clicked.connect(self._cancel_requested)
        self._cancel.setVisible(False)
        buttons.addWidget(self._cancel)
        buttons.addStretch(1)
        close = widgets.GhostButton("Fermer")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        self._convert = widgets.NeonButton("Convertir", icon_kind="spark")
        self._convert.clicked.connect(self._start)
        self._convert.setMinimumWidth(240)
        buttons.addWidget(self._convert)
        root.addLayout(buttons)

    def _build_category(self, kind, template):
        card = widgets.Card(padding=10, spacing=2)
        row = QHBoxLayout()
        row.setSpacing(10)
        check = QCheckBox()
        check.setToolTip("Traiter cette famille de fichiers")
        check.setChecked(True)
        check.stateChanged.connect(lambda _state: self._update_action())
        row.addWidget(check)
        row.addWidget(widgets.GlyphWidget(batch.KIND_GLYPHS[kind],
                                          KIND_COLORS[kind], 22))
        texts = QVBoxLayout()
        texts.setSpacing(0)
        title = QLabel(batch.KIND_LABELS[kind])
        title.setFont(theme.ui_font(13, QFont.Weight.DemiBold))
        details = QLabel("…")
        details.setObjectName("Faint")
        details.setWordWrap(True)
        summary = QLabel(template.summary)
        summary.setObjectName("Faint")
        summary.setWordWrap(True)
        summary.setToolTip("Réglages repris de la page %s"
                           % batch.KIND_LABELS[kind])
        texts.addWidget(title)
        texts.addWidget(details)
        texts.addWidget(summary)
        row.addLayout(texts, 1)

        combo = QComboBox()
        choices = format_choices(kind)
        for key, label in choices:
            combo.addItem(label, key)
        index = combo.findData(template.format_key)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.setMinimumContentsLength(8)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumWidth(168)
        combo.currentIndexChanged.connect(lambda _index: self._update_action())
        if not choices:
            check.setChecked(False)
            check.setEnabled(False)
            combo.setEnabled(False)
            details.setText("Encodeur indisponible dans ffmpeg")
        row.addWidget(combo, 0)
        card.add_layout(row)
        self._cards[kind] = {"check": check, "details": details,
                             "summary": summary, "combo": combo,
                             "title": title}
        return card

    # -- analyse ---------------------------------------------------------
    def _rescan(self, *_args):
        if self._busy:
            return
        output = self._output_edit.text().strip()
        excluded = [output] if output else []
        self._scan = batch.scan(self._folder, self._recursive.isChecked(),
                                exclude=excluded)
        for kind in KIND_ORDER:
            card = self._cards.get(kind)
            if not card:
                continue
            count = self._scan.count(kind)
            size = batch.category_size(self._scan, kind) if count else 0
            if count:
                card["details"].setText("%d fichier%s · %s"
                                        % (count, "s" if count > 1 else "",
                                           batch.size_label(size)))
            else:
                card["details"].setText("Aucun fichier")
            available = count > 0 and card["combo"].count() > 0
            card["check"].setEnabled(available)
            card["combo"].setEnabled(available)
            if not available:
                card["check"].setChecked(False)
                self._auto_checked.discard(kind)
            elif kind not in self._auto_checked:
                card["check"].setChecked(True)
                self._auto_checked.add(kind)
        self._update_action()

    def _choose_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de sortie", self._output_edit.text().strip()
            or self._folder)
        if folder:
            self._output_edit.setText(folder)
            self._rescan()

    def _selected_kinds(self):
        return [kind for kind in KIND_ORDER
                if kind in self._cards
                and self._cards[kind]["check"].isChecked()
                and self._scan is not None
                and self._scan.count(kind) > 0]

    def _total_selected(self):
        if self._scan is None:
            return 0
        return sum(self._scan.count(kind) for kind in self._selected_kinds())

    def _update_action(self):
        if self._busy:
            return
        total = self._total_selected()
        self._convert.setEnabled(total > 0)
        self._convert.setText("Convertir %d fichier%s"
                              % (total, "s" if total > 1 else "")
                              if total else "Aucun fichier sélectionné")
        if self._scan is None:
            return
        parts = []
        for kind in self._selected_kinds():
            count = self._scan.count(kind)
            singular, plural = KIND_NAMES[kind]
            parts.append("%d %s" % (count, singular if count == 1 else plural))
        size = sum(batch.category_size(self._scan, kind)
                   for kind in self._selected_kinds())
        if parts:
            text = "%s · %s à traiter · sortie : %s" % (
                " + ".join(parts), batch.size_label(size),
                os.path.basename(self._output_edit.text().strip())
                or "dossier de sortie")
            if self._scan.ignored:
                text += " · %d fichier%s ignoré%s" % (
                    self._scan.ignored,
                    "s" if self._scan.ignored > 1 else "",
                    "s" if self._scan.ignored > 1 else "")
            self._plan_label.setText(text)
        else:
            self._plan_label.setText("Aucune famille sélectionnée.")

    # -- conversion ------------------------------------------------------
    def _formats_by_kind(self):
        return {kind: self._cards[kind]["combo"].currentData()
                for kind in self._selected_kinds()}

    def _start(self):
        if self._busy:
            return
        self._rescan()
        output = self._output_edit.text().strip()
        if not output:
            self.console.warn("Choisissez un dossier de sortie.")
            return
        selected = self._selected_kinds()
        if not selected:
            self.console.warn("Aucun fichier à convertir.")
            return
        entries = batch.build_entries(
            self._scan, selected, self._formats_by_kind(), self._folder,
            output, recursive=self._recursive.isChecked())
        if not entries:
            self.console.warn("Aucun fichier à convertir avec ces formats.")
            return
        try:
            os.makedirs(output, exist_ok=True)
        except OSError as error:
            self.console.error("Dossier de sortie impossible : %s" % error)
            return
        settings = {kind: self._templates[kind].settings for kind in selected}
        self._entries = entries
        self._busy = True
        self.progress.set_value(0)
        self.status.setText("Conversion…")
        self.console.divider()
        self.console.accent("Lot · %d fichier%s → %s"
                            % (len(entries), "s" if len(entries) > 1 else "",
                               widgets.elide(output, 48)))
        self._set_controls(False)
        self._cancel.setVisible(True)
        self._cancel.setEnabled(True)
        self._worker = BatchWorker(entries, settings, self)
        self._worker.itemStarted.connect(self._on_item_started)
        self._worker.itemProgress.connect(self._on_item_progress)
        self._worker.itemDone.connect(self._on_item_done)
        self._worker.itemFailed.connect(self._on_item_failed)
        self._worker.allDone.connect(self._on_all_done)
        self._worker.start()

    def _on_item_started(self, index, source):
        self.status.setText("%s…" % os.path.basename(source))
        self.progress.set_value(index / max(1, len(self._entries)))

    def _on_item_progress(self, index, fraction, message):
        self.progress.set_value(
            (index + max(0.0, min(1.0, fraction))) / max(1, len(self._entries)))
        self.status.setText("%s · %s" % (os.path.basename(
            self._entries[index].source), message))

    def _on_item_done(self, index, result):
        entry = self._entries[index]
        size = result.get("size") or 0
        self.console.ok("%s · %s"
                        % (os.path.basename(entry.source),
                           batch.size_label(size) if size else "converti"))

    def _on_item_failed(self, index, message):
        entry = self._entries[index]
        self.console.error("%s : %s" % (os.path.basename(entry.source),
                                        message))

    def _on_all_done(self, converted, failed, remaining):
        self._busy = False
        self.progress.set_value(1.0 if not remaining else
                                (converted + failed)
                                / max(1, len(self._entries)))
        parts = ["%d converti%s" % (converted, "s" if converted > 1 else "")]
        if failed:
            parts.append("%d échec%s" % (failed, "s" if failed > 1 else ""))
        if remaining:
            parts.append("%d non traité%s" % (remaining,
                                              "s" if remaining > 1 else ""))
        self.status.setText("Terminé — " + " · ".join(parts))
        self.console.accent("Lot terminé — " + " · ".join(parts))
        self._cancel.setVisible(False)
        self._set_controls(True)
        self._convert.setText("Convertir à nouveau")
        self._convert.setEnabled(self._total_selected() > 0)

    def _set_controls(self, enabled):
        for widget in (self._recursive, self._output_edit):
            widget.setEnabled(enabled)
        for kind, card in self._cards.items():
            available = (enabled and self._scan is not None
                         and self._scan.count(kind) > 0
                         and card["combo"].count() > 0)
            card["check"].setEnabled(available)
            card["combo"].setEnabled(available)
        self._convert.setEnabled(enabled)

    def _cancel_requested(self):
        if self._worker is not None and self._busy:
            self._worker.cancel()
            self._cancel.setEnabled(False)
            self.status.setText("Annulation demandée…")

    def reject(self):
        if self._busy:
            self.status.setText("Conversion en cours : utilisez « Annuler » "
                                "avant de fermer.")
            return
        super().reject()
