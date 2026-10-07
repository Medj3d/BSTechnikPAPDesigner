"""Export (PNG, SVG, PDF) und Drucken.

Exportiert wird ausschließlich das Diagramm – ohne Raster, Auswahlrahmen,
Anschlusspunkte oder sonstige UI-Elemente. Für Dokumente und Ausdrucke steht
ein helles Farbschema zur Verfügung.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QMarginsF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

from app import config, styles


class ExportError(Exception):
    pass


@dataclass
class ExportOptions:
    theme_name: str = "light"
    scale: float = config.EXPORT_DEFAULT_PNG_SCALE
    transparent: bool = False
    margin: float = config.EXPORT_MARGIN

    @property
    def theme(self):
        return styles.THEMES.get(self.theme_name, styles.LIGHT)


def _source_rect(scene, margin: float) -> QRectF:
    bounds = scene.diagram_bounds()
    if bounds.isNull() or bounds.isEmpty():
        raise ExportError("Das Diagramm ist leer – es gibt nichts zu exportieren.")
    return bounds.adjusted(-margin, -margin, margin, margin)


def _render(scene, painter: QPainter, target: QRectF, source: QRectF, options: ExportOptions,
            fill_background: bool = True) -> None:
    theme = options.theme
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    if fill_background:
        painter.fillRect(target, QColor(theme.canvas_bg))
    with scene.export_mode(theme):
        scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)


def export_png(scene, path: str, options: ExportOptions) -> None:
    source = _source_rect(scene, options.margin)
    scale = max(0.5, min(8.0, options.scale))
    width = int(source.width() * scale)
    height = int(source.height() * scale)
    if width * height > 400_000_000:
        raise ExportError("Das Bild wäre zu groß. Bitte eine kleinere Auflösung wählen.")
    # RGBA8888 statt ARGB32: sonst glättet Qt unter Windows Text mit ClearType
    # (farbige Säume im exportierten Bild)
    image = QImage(QSize(max(1, width), max(1, height)), QImage.Format.Format_RGBA8888_Premultiplied)
    if image.isNull():
        raise ExportError("Für das Bild steht nicht genügend Speicher zur Verfügung.")
    image.setDotsPerMeterX(int(96 * scale / 0.0254))
    image.setDotsPerMeterY(int(96 * scale / 0.0254))
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        _render(scene, painter, QRectF(0, 0, width, height), source, options,
                fill_background=not options.transparent)
    finally:
        painter.end()
    if not image.save(path, "PNG"):
        raise ExportError(f"Die Datei „{os.path.basename(path)}“ konnte nicht geschrieben werden.")


def export_svg(scene, path: str, options: ExportOptions) -> None:
    try:
        from PySide6.QtSvg import QSvgGenerator
    except ImportError as exc:  # pragma: no cover - PySide6 enthält QtSvg
        raise ExportError("SVG-Export ist in dieser Installation nicht verfügbar.") from exc
    source = _source_rect(scene, options.margin)
    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(QSize(int(source.width()), int(source.height())))
    generator.setViewBox(QRectF(0, 0, source.width(), source.height()))
    generator.setTitle(config.APP_NAME)
    generator.setDescription(f"Programmablaufplan, erstellt mit {config.APP_NAME}")
    painter = QPainter()
    if not painter.begin(generator):
        raise ExportError(f"Die Datei „{os.path.basename(path)}“ konnte nicht geschrieben werden.")
    try:
        _render(scene, painter, QRectF(0, 0, source.width(), source.height()), source, options,
                fill_background=not options.transparent)
    finally:
        painter.end()
    if not os.path.exists(path):
        raise ExportError(f"Die Datei „{os.path.basename(path)}“ konnte nicht geschrieben werden.")


def export_pdf(scene, path: str, options: ExportOptions) -> None:
    source = _source_rect(scene, options.margin)
    writer = QPdfWriter(path)
    writer.setCreator(config.APP_NAME)
    writer.setTitle("Programmablaufplan")
    writer.setResolution(300)
    # Seitengröße = Diagrammgröße (96 dpi → Punkt: 72/96)
    page_size = QPageSize(QSizeF(source.width() * 72 / 96, source.height() * 72 / 96),
                          QPageSize.Unit.Point, "Diagramm", QPageSize.SizeMatchPolicy.ExactMatch)
    writer.setPageLayout(QPageLayout(page_size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
    painter = QPainter()
    if not painter.begin(writer):
        raise ExportError(f"Die Datei „{os.path.basename(path)}“ konnte nicht geschrieben werden.")
    try:
        target = QRectF(0, 0, writer.width(), writer.height())
        _render(scene, painter, target, source, options, fill_background=True)
    finally:
        painter.end()


def print_scene(scene, printer, options: ExportOptions) -> None:
    """Druckt das Diagramm auf eine Seite (seitenfüllend, Seitenverhältnis bleibt)."""
    source = _source_rect(scene, options.margin)
    painter = QPainter()
    if not painter.begin(printer):
        raise ExportError("Der Druck konnte nicht gestartet werden.")
    try:
        page = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))
        page = QRectF(0, 0, page.width(), page.height())
        _render(scene, painter, page, source, options, fill_background=False)
    finally:
        painter.end()


def ensure_extension(path: str, extension: str) -> str:
    return path if path.lower().endswith(extension.lower()) else path + extension
