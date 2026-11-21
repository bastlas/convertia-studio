"""Palette, typographie et feuille de style de Convertia Studio."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPalette
from PySide6.QtWidgets import QApplication

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

COLORS = {
    "bg": "#05070E",
    "bg_alt": "#080D18",
    "panel": "#0B1220",
    "card": "#0F1626",
    "card_hover": "#141E31",
    "line": "#1C2740",
    "line_soft": "#151E30",
    "text": "#E7EEFA",
    "text_dim": "#93A3BD",
    "text_faint": "#5E6E8A",
    "cyan": "#22D3EE",
    "violet": "#A78BFA",
    "magenta": "#F472B6",
    "green": "#34D399",
    "amber": "#FBBF24",
    "red": "#FB7185",
}

ACCENT_START = QColor(COLORS["cyan"])
ACCENT_END = QColor(COLORS["violet"])

#: Couleur associée à chaque famille de format audio
FAMILY_COLORS = {
    "lossy": COLORS["cyan"],
    "lossless": COLORS["green"],
    "pcm": COLORS["violet"],
}


def color(name, alpha=None):
    """QColor de la palette, avec alpha optionnel (0-255)."""
    value = QColor(COLORS.get(name, name))
    if alpha is not None:
        value.setAlpha(alpha)
    return value


def accent_gradient(x1, y1, x2, y2):
    """Dégradé cyan → violet."""
    gradient = QLinearGradient(x1, y1, x2, y2)
    gradient.setColorAt(0.0, ACCENT_START)
    gradient.setColorAt(1.0, ACCENT_END)
    return gradient


# --------------------------------------------------------------------------
# Typographie
# --------------------------------------------------------------------------

_UI_FAMILIES = ("Inter", "Segoe UI", "SF Pro Text", "Ubuntu", "Noto Sans",
                "DejaVu Sans", "Arial")
_MONO_FAMILIES = ("JetBrains Mono", "Cascadia Mono", "SF Mono", "Consolas",
                  "Noto Sans Mono", "DejaVu Sans Mono", "monospace")


def _first_available(candidates, fallback):
    installed = set(QFontDatabase.families())
    for name in candidates:
        if name in installed:
            return name
    return fallback


_ui_family = None
_mono_family = None


def ui_font(size=13, weight=QFont.Weight.Normal, letter_spacing=None):
    """Police d'interface à la taille demandée."""
    global _ui_family
    if _ui_family is None:
        _ui_family = _first_available(_UI_FAMILIES, QApplication.font().family())
    font = QFont(_ui_family)
    font.setPixelSize(size)
    font.setWeight(weight)
    if letter_spacing is not None:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
    return font


def mono_font(size=12, weight=QFont.Weight.Normal):
    """Police à chasse fixe (journal, chemins)."""
    global _mono_family
    if _mono_family is None:
        _mono_family = _first_available(_MONO_FAMILIES, "monospace")
    font = QFont(_mono_family)
    font.setPixelSize(size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


# --------------------------------------------------------------------------
# Feuille de style globale
# --------------------------------------------------------------------------

STYLESHEET = """
QWidget {
    color: %(text)s;
    font-family: "%(ui_family)s";
    font-size: 13px;
}
QMainWindow, QDialog {
    background: %(bg)s;
}

QToolTip {
    background: %(card)s;
    color: %(text)s;
    border: 1px solid %(line)s;
    border-radius: 6px;
    padding: 6px 8px;
}

/* ---- cartes et panneaux ---- */
QFrame#Card {
    background: %(card)s;
    border: 1px solid %(line_soft)s;
    border-radius: 14px;
}
QFrame#CardFlat {
    background: transparent;
    border: 1px solid %(line_soft)s;
    border-radius: 14px;
}

/* ---- textes ---- */
QLabel#H1 {
    font-size: 26px;
    font-weight: 700;
    color: %(text)s;
}
QLabel#H2 {
    font-size: 16px;
    font-weight: 600;
    color: %(text)s;
}
QLabel#SectionLabel {
    font-size: 10px;
    font-weight: 700;
    color: %(text_faint)s;
    letter-spacing: 2px;
}
QLabel#Muted {
    color: %(text_dim)s;
}
QLabel#Faint {
    color: %(text_faint)s;
    font-size: 12px;
}
QLabel#Mono {
    color: %(text_dim)s;
    font-family: "%(mono_family)s";
    font-size: 12px;
}
QLabel#Value {
    font-size: 13px;
    font-weight: 600;
}

/* ---- champs ---- */
QLineEdit {
    background: %(bg_alt)s;
    border: 1px solid %(line)s;
    border-radius: 10px;
    padding: 9px 12px;
    selection-background-color: %(cyan)s;
    selection-color: #04070E;
}
QLineEdit:focus {
    border: 1px solid %(cyan)s;
}
QLineEdit:read-only {
    color: %(text_dim)s;
}

QComboBox {
    background: %(bg_alt)s;
    border: 1px solid %(line)s;
    border-radius: 10px;
    padding: 8px 12px;
    min-width: 96px;
}
QComboBox:hover {
    border: 1px solid #2A3A58;
}
QComboBox:focus {
    border: 1px solid %(cyan)s;
}
QComboBox:disabled {
    color: %(text_faint)s;
    background: #0A101C;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: %(card)s;
    border: 1px solid %(line)s;
    border-radius: 10px;
    padding: 4px;
    outline: none;
    selection-background-color: #16233A;
    selection-color: %(text)s;
}

QCheckBox {
    spacing: 8px;
    color: %(text_dim)s;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid %(line)s;
    background: %(bg_alt)s;
}
QCheckBox::indicator:checked {
    background: %(cyan)s;
    border: 1px solid %(cyan)s;
}

/* ---- journal ---- */
QTextEdit#Console {
    background: %(bg_alt)s;
    border: 1px solid %(line_soft)s;
    border-radius: 12px;
    padding: 8px;
    font-family: "%(mono_family)s";
    font-size: 12px;
    color: %(text_dim)s;
}

/* ---- barres de défilement ---- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #22304A;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #2E4160;
}
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background: #22304A;
    border-radius: 5px;
    min-width: 30px;
}
"""


def stylesheet():
    """Feuille de style complète (familles de polices résolues)."""
    return STYLESHEET % {
        **COLORS,
        "ui_family": ui_font().family(),
        "mono_family": mono_font().family(),
    }


def apply_palette(app):
    """Applique la palette sombre à l'application Qt."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, color("bg"))
    palette.setColor(QPalette.ColorRole.WindowText, color("text"))
    palette.setColor(QPalette.ColorRole.Base, color("bg_alt"))
    palette.setColor(QPalette.ColorRole.AlternateBase, color("card"))
    palette.setColor(QPalette.ColorRole.Text, color("text"))
    palette.setColor(QPalette.ColorRole.Button, color("card"))
    palette.setColor(QPalette.ColorRole.ButtonText, color("text"))
    palette.setColor(QPalette.ColorRole.Highlight, color("cyan"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#04070E"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, color("card"))
    palette.setColor(QPalette.ColorRole.ToolTipText, color("text"))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())
