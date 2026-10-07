"""Ergänzt die oben abgeschnittene Spitze der weißen Raute im Schullogo.

Das gelieferte Bild (``tools/bs_technik_logo_original.png``) endet oben mitten in der Raute: Am Bildrand ist sie
noch über 100 Pixel breit, ihre Spitze fehlt. Dieses Skript verlängert die beiden Kanten bis zum Schnittpunkt
(die Raute ist ein um 45° gedrehtes Quadrat) und zeichnet die fehlende Spitze dazu. Ergebnis:
``assets/bs_technik_logo.png`` – Raute vollständig, Logo darin unverändert.

    python tools\\complete_logo.py
"""

from __future__ import annotations

import math
import os
import sys

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SOURCE = os.path.join(ROOT, "tools", "bs_technik_logo_original.png")
TARGET = os.path.join(ROOT, "assets", "bs_technik_logo.png")
MARGIN = 8  # schwarzer Rand um die fertige Raute (Pixel)


def is_white(image: QImage, x: int, y: int) -> bool:
    color = QColor(image.pixel(x, y))
    return color.red() > 200 and color.green() > 200 and color.blue() > 200


def white_run(image: QImage, y: int) -> tuple[int, int] | None:
    """Erstes und letztes weißes Pixel einer Zeile."""
    xs = [x for x in range(image.width()) if is_white(image, x, y)]
    return (xs[0], xs[-1]) if xs else None


def complete_top_apex(image: QImage) -> QImage:
    """Das Bild mit vollständiger oberer Spitze (und schwarzem Rand). Bleibt unverändert, wenn die Spitze da ist."""
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    top = white_run(image, 0)
    if top is None or top[1] - top[0] < 4:
        return image  # Spitze ist (nahezu) vollständig sichtbar
    lower_y = 40
    lower = white_run(image, lower_y)
    if lower is None:
        raise SystemExit("Die Raute ließ sich nicht vermessen.")
    # Die Kanten steigen gleichmäßig: pro Zeile wächst die Breite um (lower - top) / lower_y.
    growth_left = (top[0] - lower[0]) / lower_y        # Pixel, die die linke Kante je Zeile nach links wandert
    growth_right = (lower[1] - top[1]) / lower_y
    if growth_left <= 0 or growth_right <= 0:
        raise SystemExit("Die Kanten der Raute verlaufen nicht wie erwartet.")
    left_edge, right_edge = top[0] - 0.5, top[1] + 0.5  # Pixelränder in Zeile 0
    rows_to_apex = min((right_edge - left_edge) / (growth_left + growth_right), 200.0)
    apex_x = left_edge + rows_to_apex * growth_left
    missing = math.ceil(rows_to_apex)
    offset_y = missing + MARGIN
    canvas = QImage(image.width() + 2 * MARGIN, image.height() + offset_y + MARGIN, QImage.Format.Format_RGB32)
    canvas.fill(QColor(0, 0, 0))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QColor(255, 255, 255, 0))
    painter.setBrush(QColor(255, 255, 255))
    overlap = 3  # das Dreieck reicht ein Stück ins Bild hinein, das Original deckt es dort wieder zu
    ox, oy = MARGIN, offset_y
    painter.drawPolygon(QPolygonF([
        QPointF(ox + left_edge - growth_left * overlap, oy + overlap),
        QPointF(ox + apex_x, oy - rows_to_apex),
        QPointF(ox + right_edge + growth_right * overlap, oy + overlap)]))
    painter.drawImage(ox, oy, image)
    painter.end()
    return crop_to_diamond(canvas)


def crop_to_diamond(image: QImage) -> QImage:
    """Beschneidet das Bild gleichmäßig auf die weiße Raute plus ``MARGIN`` Pixel Rand ringsum."""
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height()):
        for x in range(image.width()):
            if is_white(image, x, y):
                xs.append(x)
                ys.append(y)
    left, top, right, bottom = min(xs) - MARGIN, min(ys) - MARGIN, max(xs) + MARGIN, max(ys) + MARGIN
    cropped = QImage(right - left + 1, bottom - top + 1, QImage.Format.Format_RGB32)
    cropped.fill(QColor(0, 0, 0))
    painter = QPainter(cropped)
    painter.drawImage(-left, -top, image)
    painter.end()
    return cropped


def main() -> int:
    source = QImage(SOURCE)
    if source.isNull():
        print("Das Original fehlt:", SOURCE)
        return 1
    result = complete_top_apex(source)
    result.save(TARGET, "PNG")
    print(f"{source.width()}x{source.height()} -> {result.width()}x{result.height()}: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
