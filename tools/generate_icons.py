"""Erzeugt die Programm- und Dateisymbole (assets/*.ico, assets/*.png).

Die Symbole werden – wie alle Grafiken der Anwendung – programmatisch mit
QPainter gezeichnet. Aufruf aus dem Projektordner:

    python tools/generate_icons.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import icons, styles  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def file_icon_image(size: int) -> QImage:
    """Dokumentsymbol mit eingebettetem Programmsymbol."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 64.0
    p.scale(s, s)
    p.setPen(QPen(QColor(styles.DARK.border_strong), 2))
    p.setBrush(QColor("#E9ECF1"))
    p.drawRoundedRect(QRectF(10, 3, 44, 58), 5, 5)
    p.resetTransform()
    inner = icons.render_app_icon(int(size * 0.62))
    p.drawPixmap(int(size * 0.19), int(size * 0.2), inner)
    if size >= 48:
        p.scale(s, s)
        p.setPen(QColor("#3A6CB2"))
        font = QFont("Segoe UI")
        font.setPixelSize(9)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(10, 49, 44, 10), int(Qt.AlignmentFlag.AlignCenter), "PAP")
    p.end()
    return image


def save_ico(images: list[QImage], path: str) -> None:
    # Qt schreibt eine .ico-Datei mit der größten Auflösung; für mehrere
    # Auflösungen wird die Datei manuell zusammengesetzt (PNG-komprimiert).
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    blobs = []
    for image in images:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        blobs.append((image.width(), image.height(), bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    payload = b""
    for width, height, blob in blobs:
        entries += struct.pack("<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(blob), offset + len(payload))
        payload += blob
    with open(path, "wb") as handle:
        handle.write(header + entries + payload)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    assets = os.path.join(ROOT, "assets")
    os.makedirs(assets, exist_ok=True)
    app_images = [icons.render_app_icon(size).toImage() for size in SIZES]
    file_images = [file_icon_image(size) for size in SIZES]
    save_ico(app_images, os.path.join(assets, "app_icon.ico"))
    save_ico(file_images, os.path.join(assets, "file_icon.ico"))
    app_images[-1].save(os.path.join(assets, "app_icon.png"), "PNG")
    file_images[-1].save(os.path.join(assets, "file_icon.png"), "PNG")
    print("Symbole erzeugt in", assets)
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
