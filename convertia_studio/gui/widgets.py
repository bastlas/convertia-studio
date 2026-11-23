"""Composants graphiques maison de Convertia Studio (thème néon sombre)."""

from __future__ import annotations

import os

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPointF, QPropertyAnimation,
                            QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsDropShadowEffect, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QTextEdit,
                               QVBoxLayout, QWidget)

from . import theme


# --------------------------------------------------------------------------
# Icônes dessinées (aucune dépendance à une police d'icônes)
# --------------------------------------------------------------------------


def _paint_icon(painter, kind, rect, color):
    pen = QPen(color, max(1.6, rect.width() * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

    if kind == "audio":
        levels = (0.35, 0.72, 1.0, 0.55, 0.85)
        gap = w / (len(levels) + 1)
        for index, level in enumerate(levels):
            cx = x + gap * (index + 1)
            half = h * level * 0.5
            painter.drawLine(QPointF(cx, y + h * 0.5 - half),
                             QPointF(cx, y + h * 0.5 + half))
    elif kind == "image":
        frame = QRectF(x, y + h * 0.12, w, h * 0.76)
        painter.drawRoundedRect(frame, 3, 3)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(frame.right() - w * 0.24, frame.top() + h * 0.24),
                            max(1.2, w * 0.07), max(1.2, w * 0.07))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(frame.left() + w * 0.1, frame.bottom() - h * 0.08))
        path.lineTo(frame.left() + w * 0.38, frame.bottom() - h * 0.34)
        path.lineTo(frame.left() + w * 0.58, frame.bottom() - h * 0.16)
        path.lineTo(frame.left() + w * 0.78, frame.bottom() - h * 0.3)
        painter.drawPath(path)
    elif kind == "video":
        frame = QRectF(x, y + h * 0.12, w, h * 0.76)
        painter.drawRoundedRect(frame, 3, 3)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        triangle = QPainterPath(QPointF(frame.left() + w * 0.38, frame.top() + h * 0.2))
        triangle.lineTo(frame.left() + w * 0.38, frame.bottom() - h * 0.2)
        triangle.lineTo(frame.right() - w * 0.2, frame.center().y())
        triangle.closeSubpath()
        painter.drawPath(triangle)
    elif kind == "spark":
        centre = QPointF(x + w * 0.5, y + h * 0.5)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            painter.drawLine(QPointF(centre.x() + dx * w * 0.14, centre.y() + dy * h * 0.14),
                             QPointF(centre.x() + dx * w * 0.46, centre.y() + dy * h * 0.46))
        painter.drawEllipse(centre, w * 0.1, h * 0.1)
    elif kind == "folder":
        path = QPainterPath(QPointF(x, y + h * 0.22))
        path.lineTo(x + w * 0.4, y + h * 0.22)
        path.lineTo(x + w * 0.5, y + h * 0.36)
        path.lineTo(x + w, y + h * 0.36)
        path.lineTo(x + w, y + h * 0.82)
        path.lineTo(x, y + h * 0.82)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "check":
        path = QPainterPath(QPointF(x + w * 0.2, y + h * 0.55))
        path.lineTo(x + w * 0.43, y + h * 0.76)
        path.lineTo(x + w * 0.82, y + h * 0.26)
        painter.drawPath(path)
    elif kind == "waveform":
        levels = (0.2, 0.45, 0.7, 0.95, 0.55, 0.8, 0.35, 0.6, 0.25)
        gap = w / (len(levels) + 1)
        for index, level in enumerate(levels):
            cx = x + gap * (index + 1)
            half = h * level * 0.5
            painter.drawLine(QPointF(cx, y + h * 0.5 - half),
                             QPointF(cx, y + h * 0.5 + half))
    else:  # "dot"
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x + w / 2, y + h / 2), w * 0.28, h * 0.28)


def make_pixmap(kind, color="#E7EEFA", size=22, ratio=2.0):
    """Dessine une icône vectorielle dans un QPixmap."""
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _paint_icon(painter, kind, QRectF(0, 0, size, size), QColor(color))
    painter.end()
    return pixmap


def make_icon(kind, color="#E7EEFA", size=22):
    """QIcon prêt à l'emploi."""
    return QIcon(make_pixmap(kind, color, size))


class GlyphWidget(QWidget):
    """Petit widget qui affiche une icône dessinée."""

    def __init__(self, kind, color="#E7EEFA", size=22, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._color = QColor(color)
        self._size = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_icon(painter, self._kind, QRectF(0, 0, self._size, self._size), self._color)


# --------------------------------------------------------------------------
# Fond « aurore »
# --------------------------------------------------------------------------


class AuroraBackground(QWidget):
    """Fond sombre avec deux halos colorés et une grille discrète."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, theme.color("bg"))

        for centre, radius, tint, alpha in (
                (QPointF(rect.width() * 0.12, rect.height() * -0.05),
                 rect.width() * 0.55, theme.color("cyan"), 46),
                (QPointF(rect.width() * 1.02, rect.height() * 0.92),
                 rect.width() * 0.5, theme.color("violet"), 38),
                (QPointF(rect.width() * 0.75, rect.height() * 0.05),
                 rect.width() * 0.35, theme.color("magenta"), 16)):
            gradient = QRadialGradient(centre, radius)
            start = QColor(tint)
            start.setAlpha(alpha)
            end = QColor(tint)
            end.setAlpha(0)
            gradient.setColorAt(0.0, start)
            gradient.setColorAt(1.0, end)
            painter.fillRect(rect, QBrush(gradient))

        pen = QPen(theme.color("line_soft"))
        pen.setWidth(1)
        painter.setPen(pen)
        step = 64
        for x in range(0, rect.width(), step):
            painter.drawLine(x, 0, x, rect.height())
        for y in range(0, rect.height(), step):
            painter.drawLine(0, y, rect.width(), y)


# --------------------------------------------------------------------------
# Petits éléments
# --------------------------------------------------------------------------


class SectionLabel(QLabel):
    """Intitulé de section en petites capitales espacées."""

    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("SectionLabel")


class Pill(QLabel):
    """Étiquette arrondie colorée."""

    def __init__(self, text="", tint=None, parent=None):
        super().__init__(text, parent)
        self._tint = QColor(tint or theme.COLORS["cyan"])
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.ui_font(11, QFont.Weight.DemiBold))
        self.setFixedHeight(22)
        self._refresh()

    def _refresh(self):
        base = QColor(self._tint)
        self.setStyleSheet(
            "QLabel { color: %s; background: rgba(%d,%d,%d,40);"
            " border: 1px solid rgba(%d,%d,%d,90); border-radius: 11px;"
            " padding: 0 10px; }"
            % (base.name(), base.red(), base.green(), base.blue(),
               base.red(), base.green(), base.blue()))

    def set_tint(self, tint):
        self._tint = QColor(tint)
        self._refresh()


class Card(QFrame):
    """Panneau arrondi du thème."""

    def __init__(self, parent=None, padding=18, spacing=12, flat=False):
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(spacing)

    def body(self):
        return self._layout

    def add(self, widget, stretch=0):
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout):
        self._layout.addLayout(layout)
        return layout


# --------------------------------------------------------------------------
# Boutons
# --------------------------------------------------------------------------


class NeonButton(QPushButton):
    """Bouton principal à dégradé cyan → violet, avec halo."""

    def __init__(self, text, parent=None, icon_kind=None, height=46):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(height)
        self.setFont(theme.ui_font(14, QFont.Weight.DemiBold))
        self._hover = 0.0
        self._pressed = False
        self._icon_kind = icon_kind
        self._animation = QPropertyAnimation(self, b"hover", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(32)
        glow.setOffset(0, 6)
        glow.setColor(theme.color("cyan", 90))
        self.setGraphicsEffect(glow)
        self._glow = glow

    def get_hover(self):
        return self._hover

    def set_hover(self, value):
        self._hover = value
        self.update()

    hover = Property(float, get_hover, set_hover)

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def _animate(self, target):
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange:
            self._glow.setEnabled(self.isEnabled())
        super().changeEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        enabled = self.isEnabled()

        if not enabled:
            painter.setPen(QPen(theme.color("line"), 1))
            painter.setBrush(theme.color("card"))
        else:
            start = QColor(theme.ACCENT_START)
            end = QColor(theme.ACCENT_END)
            if self._hover:
                start = start.lighter(100 + int(18 * self._hover))
                end = end.lighter(100 + int(18 * self._hover))
            if self._pressed:
                start = start.darker(115)
                end = end.darker(115)
            gradient = theme.accent_gradient(rect.left(), rect.top(),
                                             rect.right(), rect.bottom())
            gradient.setColorAt(0.0, start)
            gradient.setColorAt(1.0, end)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))

        painter.drawRoundedRect(rect, radius, radius)

        if enabled:
            highlight = QColor(255, 255, 255, 30 + int(20 * self._hover))
            painter.setPen(QPen(highlight, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                    radius, radius)

        painter.setPen(QColor("#04070E" if enabled else theme.COLORS["text_faint"]))
        painter.setFont(self.font())
        text_rect = rect
        if self._icon_kind:
            icon_size = 18
            total = painter.fontMetrics().horizontalAdvance(self.text()) + icon_size + 10
            icon_rect = QRectF(rect.center().x() - total / 2, rect.center().y() - icon_size / 2,
                               icon_size, icon_size)
            _paint_icon(painter, self._icon_kind, icon_rect,
                        QColor("#04070E" if enabled else theme.COLORS["text_faint"]))
            text_rect = QRectF(icon_rect.right() + 10, rect.top(),
                               rect.right() - icon_rect.right() - 10, rect.height())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignVCenter, self.text())
        else:
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())


class GhostButton(QPushButton):
    """Bouton secondaire discret (contour)."""

    def __init__(self, text, parent=None, icon_kind=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setFont(theme.ui_font(12, QFont.Weight.Medium))
        self._icon_kind = icon_kind
        self.setStyleSheet("""
            QPushButton {
                color: %(text_dim)s;
                background: transparent;
                border: 1px solid %(line)s;
                border-radius: 10px;
                padding: 0 14px;
            }
            QPushButton:hover {
                color: %(text)s;
                border: 1px solid #2E4160;
                background: #101A2B;
            }
            QPushButton:disabled { color: %(text_faint)s; }
        """ % theme.COLORS)
        if icon_kind:
            self.setIcon(make_icon(icon_kind, theme.COLORS["text_dim"], 16))
            self.setIconSize(QSize(16, 16))


class NavButton(QAbstractButton):
    """Entrée de la colonne de navigation."""

    def __init__(self, text, icon_kind, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._icon_kind = icon_kind
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFont(theme.ui_font(13, QFont.Weight.Medium))
        self._hover = False
        self._hover_progress = 0.0
        self._animation = QPropertyAnimation(self, b"hoverProgress", self)
        self._animation.setDuration(130)

    def get_hover_progress(self):
        return self._hover_progress

    def set_hover_progress(self, value):
        self._hover_progress = value
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def _animate(self, target):
        self._animation.stop()
        self._animation.setStartValue(self._hover_progress)
        self._animation.setEndValue(target)
        self._animation.start()

    def sizeHint(self):
        return QSize(180, 46)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(6, 3, -6, -3)
        checked = self.isChecked()
        tint = self._hover_progress * (0.0 if checked else 1.0)

        if checked:
            gradient = theme.accent_gradient(rect.left(), rect.top(),
                                             rect.right(), rect.bottom())
            base = QColor(theme.ACCENT_START)
            base.setAlpha(38)
            top = QColor(theme.ACCENT_END)
            top.setAlpha(18)
            gradient.setColorAt(0.0, base)
            gradient.setColorAt(1.0, top)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(rect, 12, 12)
        elif tint:
            fill = theme.color("card_hover")
            fill.setAlpha(int(180 * tint))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 12, 12)

        if checked:
            bar = QRectF(rect.left(), rect.top() + 10, 3, rect.height() - 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(theme.accent_gradient(bar.left(), bar.top(),
                                                          bar.right(), bar.bottom())))
            painter.drawRoundedRect(bar, 1.5, 1.5)

        icon_color = theme.COLORS["cyan"] if checked else (
            theme.COLORS["text"] if self._hover_progress > 0.5 else theme.COLORS["text_dim"])
        icon_rect = QRectF(rect.left() + 16, rect.center().y() - 9, 18, 18)
        _paint_icon(painter, self._icon_kind, icon_rect, QColor(icon_color))

        painter.setPen(QColor(theme.COLORS["text"] if checked else
                              (theme.COLORS["text"] if self._hover_progress > 0.5
                               else theme.COLORS["text_dim"])))
        painter.setFont(self.font())
        painter.drawText(QRectF(icon_rect.right() + 12, rect.top(),
                                rect.width() - 50, rect.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.text())


# --------------------------------------------------------------------------
# Cartes de format
# --------------------------------------------------------------------------


class FormatCard(QAbstractButton):
    """Carte sélectionnable représentant un format de sortie."""

    def __init__(self, audio_format, parent=None):
        super().__init__(parent)
        self.format = audio_format
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._hover = 0.0
        self._fade = 0.0
        self._animation = QPropertyAnimation(self, b"hoverProgress", self)
        self._animation.setDuration(150)
        self._fade_animation = QPropertyAnimation(self, b"selectProgress", self)
        self._fade_animation.setDuration(220)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setToolTip(audio_format.description)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        self._fade_animation.stop()
        self._fade_animation.setStartValue(self._fade)
        self._fade_animation.setEndValue(1.0 if checked else 0.0)
        self._fade_animation.start()

    def get_hover_progress(self):
        return self._hover

    def set_hover_progress(self, value):
        self._hover = value
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def get_select_progress(self):
        return self._fade

    def set_select_progress(self, value):
        self._fade = value
        self.update()

    selectProgress = Property(float, get_select_progress, set_select_progress)

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def _animate(self, target):
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 13
        accent = QColor(theme.FAMILY_COLORS.get(self.format.family,
                                                theme.COLORS["cyan"]))

        background = QColor(theme.COLORS["card"])
        if self._hover:
            background = background.lighter(100 + int(14 * self._hover))
        if self._fade:
            background = QColor(background.red(), background.green(),
                                background.blue())
        painter.setBrush(background)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        if self._fade > 0.01:
            tint = QColor(accent)
            tint.setAlpha(int(26 * self._fade))
            painter.setBrush(tint)
            painter.drawRoundedRect(rect, radius, radius)

        border = QColor(theme.COLORS["line_soft"])
        if self._fade > 0.01:
            gradient = theme.accent_gradient(rect.left(), rect.top(),
                                             rect.right(), rect.bottom())
            gradient.setColorAt(0.0, QColor(theme.ACCENT_START.red(),
                                            theme.ACCENT_START.green(),
                                            theme.ACCENT_START.blue(),
                                            int(60 + 195 * self._fade)))
            gradient.setColorAt(1.0, QColor(theme.ACCENT_END.red(),
                                            theme.ACCENT_END.green(),
                                            theme.ACCENT_END.blue(),
                                            int(60 + 195 * self._fade)))
            pen = QPen(QBrush(gradient), 1.6)
        else:
            border.setAlpha(150 + int(80 * self._hover))
            pen = QPen(border, 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)

        # pastille d'accent
        dot = QRectF(rect.right() - 24, rect.top() + 13, 8, 8)
        dot_color = QColor(accent)
        dot_color.setAlpha(int(70 + 185 * max(self._fade, self._hover * 0.7)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)
        painter.drawEllipse(dot)

        # titre
        painter.setPen(QColor(theme.COLORS["text"]))
        painter.setFont(theme.ui_font(14, QFont.Weight.DemiBold))
        painter.drawText(QRectF(rect.left() + 16, rect.top() + 13,
                                rect.width() - 46, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.format.label)

        # extension
        painter.setPen(QColor(theme.COLORS["text_faint"]))
        painter.setFont(theme.mono_font(11))
        painter.drawText(QRectF(rect.left() + 16, rect.top() + 34,
                                rect.width() - 32, 14),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.format.extension)

        # badge famille
        badge_rect = QRectF(rect.left() + 16, rect.bottom() - 31, 0, 18)
        painter.setFont(theme.ui_font(10, QFont.Weight.DemiBold))
        badge_text = self.format.badge
        badge_width = painter.fontMetrics().horizontalAdvance(badge_text) + 16
        badge_rect.setWidth(badge_width)
        tint = QColor(accent)
        tint.setAlpha(38)
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 110), 1))
        painter.setBrush(tint)
        painter.drawRoundedRect(badge_rect, 9, 9)
        painter.setPen(QColor(accent))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)


# --------------------------------------------------------------------------
# Zone de dépôt
# --------------------------------------------------------------------------


class DropZone(QFrame):
    """Zone de glisser-déposer (ou clic pour parcourir)."""

    clicked = Signal()
    fileDropped = Signal(str)
    folderDropped = Signal(str)

    def __init__(self, parent=None, glyph="waveform",
                 title="Déposez un fichier ici",
                 subtitle="projet Audacity (.aup3 / .aup4) ou fichier audio — "
                          "ou cliquez pour parcourir"):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(148)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._hover = 0.0
        self._animation = QPropertyAnimation(self, b"hoverProgress", self)
        self._animation.setDuration(160)
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon = GlyphWidget(glyph, theme.COLORS["cyan"], 34)
        self.title = QLabel(title)
        self.title.setFont(theme.ui_font(15, QFont.Weight.DemiBold))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("Faint")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)

        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def get_hover_progress(self):
        return self._hover

    def set_hover_progress(self, value):
        self._hover = value
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def _animate(self, target):
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._dragging = True
            self._animate(1.0)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._dragging = False
        self._animate(0.0)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._dragging = False
        self._animate(0.0)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                if os.path.isdir(path):
                    self.folderDropped.emit(path)
                else:
                    self.fileDropped.emit(path)
                break
        event.acceptProposedAction()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        radius = 16
        strength = max(self._hover, 1.0 if self._dragging else 0.0)

        fill = QColor(theme.COLORS["card"])
        if strength:
            fill = fill.lighter(100 + int(18 * strength))
        painter.setBrush(fill)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        pen = QPen(QColor(theme.COLORS["line"]), 1.4, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        if strength:
            gradient = theme.accent_gradient(rect.left(), rect.top(),
                                             rect.right(), rect.bottom())
            pen = QPen(QBrush(gradient), 1.6, Qt.PenStyle.DashLine)
            pen.setDashPattern([5, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)


class PreviewPanel(QFrame):
    """Grand panneau vide illustré (sections à venir)."""

    def __init__(self, glyph, accent, text, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._accent = QColor(accent)
        self._text = text
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.COLORS["card"]))
        painter.drawRoundedRect(rect, 16, 16)

        pen = QPen(QColor(self._accent.red(), self._accent.green(),
                          self._accent.blue(), 70), 1.3, Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 5])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 16, 16)

        size = min(rect.height() * 0.42, 120)
        iconic = QRectF(rect.center().x() - size / 2,
                        rect.center().y() - size * 0.72, size, size)
        ghost = QColor(self._accent)
        ghost.setAlpha(70)
        _paint_icon(painter, self._glyph, iconic, ghost)

        painter.setPen(QColor(theme.COLORS["text_faint"]))
        painter.setFont(theme.ui_font(13))
        painter.drawText(QRectF(rect.left(), iconic.bottom() + 18,
                                rect.width(), 24),
                         Qt.AlignmentFlag.AlignHCenter, self._text)


# --------------------------------------------------------------------------
# Barre de progression
# --------------------------------------------------------------------------


class GradientProgress(QWidget):
    """Barre de progression à dégradé, avec pourcentage et état indéterminé."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._value = 0.0
        self._display = 0.0
        self._indeterminate = False
        self._phase = 0.0
        self._animation = QPropertyAnimation(self, b"displayValue", self)
        self._animation.setDuration(320)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def get_display_value(self):
        return self._display

    def set_display_value(self, value):
        self._display = value
        self.update()

    displayValue = Property(float, get_display_value, set_display_value)

    def set_value(self, value):
        """Valeur 0..1 (animée)."""
        self._value = max(0.0, min(1.0, value))
        self._animation.stop()
        self._animation.setStartValue(self._display)
        self._animation.setEndValue(self._value)
        self._animation.start()

    def value(self):
        return self._value

    def set_indeterminate(self, enabled):
        self._indeterminate = bool(enabled)
        if self._indeterminate:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.02) % 1.0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 1.5, 0, -1.5)
        radius = rect.height() / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.COLORS["line"]))
        painter.drawRoundedRect(rect, radius, radius)

        if self._indeterminate:
            width = rect.width() * 0.28
            x = rect.left() - width + (rect.width() + width) * self._phase
            segment = QRectF(x, rect.top(), width, rect.height())
            segment = segment.intersected(rect)
            if segment.width() > 0:
                gradient = theme.accent_gradient(segment.left(), segment.top(),
                                                 segment.right(), segment.bottom())
                painter.setBrush(QBrush(gradient))
                painter.drawRoundedRect(segment, radius, radius)
            return

        if self._display <= 0.001:
            return
        filled = QRectF(rect.left(), rect.top(),
                        max(rect.height(), rect.width() * self._display),
                        rect.height())
        gradient = theme.accent_gradient(filled.left(), filled.top(),
                                         filled.right(), filled.bottom())
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(filled, radius, radius)

        highlight = QRectF(filled.left(), filled.top() + 1,
                           filled.width(), filled.height() * 0.4)
        painter.setBrush(QColor(255, 255, 255, 45))
        painter.drawRoundedRect(highlight, radius / 2, radius / 2)


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------


class Console(QTextEdit):
    """Journal coloré (messages d'information, d'alerte et d'erreur)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Console")
        self.setReadOnly(True)
        self.setAcceptRichText(True)
        self.setUndoRedoEnabled(False)
        self.setMinimumHeight(90)

    def _append(self, text, tint):
        if not text:
            return
        escaped = (text.replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;").replace("\n", "<br>"))
        self.append('<span style="color:%s">%s</span>' % (tint, escaped))
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def info(self, text):
        self._append(text, theme.COLORS["text_dim"])

    def ok(self, text):
        self._append("✓ " + text, theme.COLORS["green"])

    def warn(self, text):
        self._append("⚠ " + text, theme.COLORS["amber"])

    def error(self, text):
        self._append("✕ " + text, theme.COLORS["red"])

    def accent(self, text):
        self._append(text, theme.COLORS["cyan"])

    def divider(self):
        self._append("─" * 46, theme.COLORS["line"])


# --------------------------------------------------------------------------
# Divers
# --------------------------------------------------------------------------


def labelled(label_text, widget, hint=None):
    """Petit bloc « intitulé au-dessus du champ »."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    caption = QLabel(label_text.upper())
    caption.setObjectName("SectionLabel")
    layout.addWidget(caption)
    layout.addWidget(widget)
    if hint:
        note = QLabel(hint)
        note.setObjectName("Faint")
        layout.addWidget(note)
    return container


def hline():
    """Trait horizontal discret."""
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: %s;" % theme.COLORS["line_soft"])
    return line


def elide(text, limit=64):
    """Raccourcit un texte trop long pour l'affichage."""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def scroll_column(content):
    """Enveloppe une colonne de réglages dans une zone défilante transparente."""
    area = QScrollArea()
    area.setObjectName("SettingsScroll")
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content.setObjectName("SettingsContent")
    content.setAutoFillBackground(False)
    area.setWidget(content)
    area.viewport().setObjectName("SettingsViewport")
    area.viewport().setAutoFillBackground(False)
    area.viewport().setStyleSheet(
        "QWidget#SettingsViewport { background: transparent; }")
    content.setStyleSheet(
        "QWidget#SettingsContent { background: transparent; }")
    area.setStyleSheet(
        "QScrollArea#SettingsScroll { background: transparent; border: none; }")
    return area


def human_size(size):
    """Taille lisible façon française (« 2,4 Mio »)."""
    size = float(size)
    if size < 1024:
        return "%d o" % round(size)
    for unit in ("Kio", "Mio", "Gio"):
        size /= 1024.0
        if size < 1024 or unit == "Gio":
            text = "%.1f" % size if size < 100 else "%.0f" % size
            return "%s %s" % (text.replace(".", ","), unit)
    return ("%.1f Gio" % size).replace(".", ",")


def small_ghost(text, icon_kind=None):
    """Bouton secondaire compact pour les rangées de réglages."""
    button = GhostButton(text, icon_kind=icon_kind)
    button.setFixedHeight(28)
    button.setFont(theme.ui_font(11, QFont.Weight.Medium))
    return button


# --------------------------------------------------------------------------
# Aperçu d'image et comparaison de poids (partagés)
# --------------------------------------------------------------------------


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
        self._approximate = False

    def set_sizes(self, before, after, approximate=False):
        self._before = before or 0
        self._after = after
        self._approximate = approximate
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
                ("≈ " if self._approximate else "") + human_size(value)
                if value else "—")
            painter.drawText(QRectF(label_width + bar_width + 8, y - 1,
                                    value_width, 16),
                             Qt.AlignmentFlag.AlignVCenter |
                             Qt.AlignmentFlag.AlignRight, text)
            painter.setFont(theme.ui_font(10, QFont.Weight.DemiBold))
