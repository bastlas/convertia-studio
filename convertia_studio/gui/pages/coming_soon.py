"""Page d'attente pour les sections Image et Vidéo (à venir)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme, widgets


class ComingSoonPage(QWidget):
    """Présente la section future et ce qu'elle proposera."""

    def __init__(self, title, subtitle, glyph, accent, features, note, parent=None):
        super().__init__(parent)
        self._accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(18)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("H1")
        caption = QLabel(subtitle)
        caption.setObjectName("Muted")
        caption.setWordWrap(True)
        titles.addWidget(heading)
        titles.addWidget(caption)
        header.addLayout(titles, 1)
        pill = widgets.Pill("BIENTÔT", accent)
        header.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        hero = widgets.Card()
        hero.body().setSpacing(10)
        row_head = QHBoxLayout()
        row_head.setSpacing(16)
        emblem = widgets.GlyphWidget(glyph, accent, 40)
        row_head.addWidget(emblem, 0, Qt.AlignmentFlag.AlignTop)
        headline_column = QVBoxLayout()
        headline_column.setSpacing(4)
        headline = QLabel("Section en préparation")
        headline.setFont(theme.ui_font(15, QFont.Weight.DemiBold))
        lead = QLabel(note)
        lead.setWordWrap(True)
        lead.setObjectName("Muted")
        headline_column.addWidget(headline)
        headline_column.addWidget(lead)
        row_head.addLayout(headline_column, 1)
        hero.add_layout(row_head)
        layout.addWidget(hero)

        row = QHBoxLayout()
        row.setSpacing(14)
        for feature_title, feature_text in features:
            card = widgets.Card(flat=True)
            card.body().setSpacing(6)
            label = QLabel(feature_title)
            label.setFont(theme.ui_font(13, QFont.Weight.DemiBold))
            text = QLabel(feature_text)
            text.setObjectName("Faint")
            text.setWordWrap(True)
            card.add(label)
            card.add(text)
            card.body().addStretch(1)
            row.addWidget(card, 1)
        layout.addLayout(row)

        preview = widgets.PreviewPanel(glyph, accent,
                                       "Aperçu à venir — cette zone accueillera "
                                       "l'interface dédiée.")
        layout.addWidget(preview, 1)
