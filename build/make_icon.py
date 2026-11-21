"""Génère l'icône de l'application (PNG + ICO) à partir du dessin Qt."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from convertia_studio.gui import theme, widgets  # noqa: E402


def render(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(theme.accent_gradient(0, 0, size, size)))
    radius = size * 0.26
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    inset = size * 0.26
    widgets._paint_icon(painter, "waveform",
                        QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
                        theme.color("bg"))
    painter.end()
    return pixmap


def main():
    app = QApplication([])  # noqa: F841 - nécessaire pour dessiner
    build = os.path.join(ROOT, "build")
    os.makedirs(build, exist_ok=True)

    sizes = (16, 24, 32, 48, 64, 128, 256)
    png_path = os.path.join(build, "convertia_studio.png")
    render(256).save(png_path, "PNG")

    try:
        from PIL import Image
    except ImportError:
        print("Pillow absent : seul le PNG a été généré (%s)" % png_path)
        return 0
    # rendu Qt -> PNG temporaire -> Pillow (évite les conversions de format)
    images = []
    for size in sizes:
        pixmap = render(size)
        temp = os.path.join(build, "_icon_%d.png" % size)
        pixmap.save(temp, "PNG")
        images.append(Image.open(temp))
        os.remove(temp)
    ico_path = os.path.join(build, "convertia_studio.ico")
    images[-1].save(ico_path, format="ICO",
                    sizes=[(size, size) for size in sizes])
    print("icône écrite : %s et %s" % (png_path, ico_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
