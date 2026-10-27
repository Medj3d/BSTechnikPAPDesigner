"""Export (PNG, SVG, PDF) und Drucken.

Exportiert wird ausschließlich das Diagramm – ohne Raster, Auswahlrahmen,
Anschlusspunkte oder sonstige UI-Elemente. Für Dokumente und Ausdrucke steht
ein helles Farbschema zur Verfügung.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass

from PySide6.QtCore import QMarginsF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

from app import config, styles
from app.i18n import tr


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


def _not_written(path: str) -> str:
    return tr("Die Datei „{name}“ konnte nicht geschrieben werden.", name=os.path.basename(path))


def _source_rect(scene, margin: float) -> QRectF:
    bounds = scene.diagram_bounds()
    if bounds.isNull() or bounds.isEmpty():
        raise ExportError(tr("Das Diagramm ist leer – es gibt nichts zu exportieren."))
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


def _image(scene, source: QRectF, options: ExportOptions) -> QImage:
    scale = max(0.5, min(8.0, options.scale))
    width = int(source.width() * scale)
    height = int(source.height() * scale)
    if width * height > 400_000_000:
        raise ExportError(tr("Das Bild wäre zu groß. Bitte eine kleinere Auflösung wählen."))
    # RGBA8888 statt ARGB32: sonst glättet Qt unter Windows Text mit ClearType
    # (farbige Säume im exportierten Bild)
    image = QImage(QSize(max(1, width), max(1, height)), QImage.Format.Format_RGBA8888_Premultiplied)
    if image.isNull():
        raise ExportError(tr("Für das Bild steht nicht genügend Speicher zur Verfügung."))
    # Auflösung angeben: Word & Co. zeigen das Bild dann in Originalgröße (nicht doppelt so groß)
    image.setDotsPerMeterX(int(96 * scale / 0.0254))
    image.setDotsPerMeterY(int(96 * scale / 0.0254))
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        _render(scene, painter, QRectF(0, 0, width, height), source, options,
                fill_background=not options.transparent)
    finally:
        painter.end()
    return image


def export_png(scene, path: str, options: ExportOptions) -> None:
    image = _image(scene, _source_rect(scene, options.margin), options)
    if not image.save(path, "PNG"):
        raise ExportError(_not_written(path))


@contextmanager
def _only(scene, element_ids: set):
    """Blendet beim Rendern alles aus, was nicht zu den Bausteinen gehört (Verbindungen nur zwischen ihnen)."""
    hidden = [item for item in scene.elements() if item.element_id not in element_ids]
    hidden += [conn for conn in scene.connections()
               if conn.data.source_id not in element_ids or conn.data.target_id not in element_ids]
    hidden = [item for item in hidden if item.isVisible()]
    # Qt hebt beim Ausblenden die Auswahl auf – sie gehört aber weiter dem Benutzer (z. B. für Strg+X)
    selected = [item for item in hidden if item.isSelected()]
    for item in hidden:
        item.setVisible(False)
    try:
        yield
    finally:
        for item in hidden:
            item.setVisible(True)
        for item in selected:
            item.setSelected(True)


def render_image(scene, options: ExportOptions, element_ids=None) -> QImage:
    """Das Diagramm – oder nur die Bausteine ``element_ids`` samt Verbindungen zwischen ihnen – als Bild,
    so wie beim PNG-Export (z. B. für die Zwischenablage)."""
    if not element_ids:
        return _image(scene, _source_rect(scene, options.margin), options)
    element_ids = set(element_ids)
    with _only(scene, element_ids):
        bounds = QRectF()
        for item in scene.elements():
            if item.element_id in element_ids:
                bounds = bounds.united(item.scene_rect())
        for conn in scene.connections():
            if conn.isVisible():
                bounds = bounds.united(conn.mapToScene(conn.shape().boundingRect()).boundingRect())
                if conn.label.isVisible():
                    bounds = bounds.united(conn.label.mapToScene(conn.label.boundingRect()).boundingRect())
        if bounds.isNull() or bounds.isEmpty():
            raise ExportError(tr("Das Diagramm ist leer – es gibt nichts zu exportieren."))
        margin = options.margin
        return _image(scene, bounds.adjusted(-margin, -margin, margin, margin), options)


def export_svg(scene, path: str, options: ExportOptions) -> None:
    try:
        from PySide6.QtSvg import QSvgGenerator
    except ImportError as exc:  # pragma: no cover - PySide6 enthält QtSvg
        raise ExportError(tr("SVG-Export ist in dieser Installation nicht verfügbar.")) from exc
    source = _source_rect(scene, options.margin)
    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(QSize(int(source.width()), int(source.height())))
    generator.setViewBox(QRectF(0, 0, source.width(), source.height()))
    generator.setTitle(config.APP_NAME)
    generator.setDescription(tr("Programmablaufplan, erstellt mit {app}", app=config.APP_NAME))
    painter = QPainter()
    if not painter.begin(generator):
        raise ExportError(_not_written(path))
    try:
        _render(scene, painter, QRectF(0, 0, source.width(), source.height()), source, options,
                fill_background=not options.transparent)
    finally:
        painter.end()
    if not os.path.exists(path):
        raise ExportError(_not_written(path))


def _scene_list(scenes) -> list:
    """Eine Szene oder eine Liste von Szenen (Seiten eines Projekts) als Liste."""
    return list(scenes) if isinstance(scenes, (list, tuple)) else [scenes]


def _pdf_layout(source: QRectF) -> QPageLayout:
    # Seitengröße = Diagrammgröße (96 dpi → Punkt: 72/96)
    page_size = QPageSize(QSizeF(source.width() * 72 / 96, source.height() * 72 / 96),
                          QPageSize.Unit.Point, tr("Diagramm"), QPageSize.SizeMatchPolicy.ExactMatch)
    return QPageLayout(page_size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))


def export_pdf(scenes, path: str, options: ExportOptions) -> None:
    """PDF mit einer Seite je Szene (Hauptprogramm und Unterprogramme), jede so groß wie ihr Diagramm."""
    scenes = _scene_list(scenes)
    sources = [_source_rect(scene, options.margin) for scene in scenes]
    writer = QPdfWriter(path)
    writer.setCreator(config.APP_NAME)
    writer.setTitle(tr("Programmablaufplan"))
    writer.setResolution(300)
    writer.setPageLayout(_pdf_layout(sources[0]))
    painter = QPainter()
    if not painter.begin(writer):
        raise ExportError(_not_written(path))
    try:
        for index, (scene, source) in enumerate(zip(scenes, sources)):
            if index:
                writer.setPageLayout(_pdf_layout(source))
                writer.newPage()
            target = QRectF(0, 0, writer.width(), writer.height())
            _render(scene, painter, target, source, options, fill_background=True)
    finally:
        painter.end()


def print_scene(scenes, printer, options: ExportOptions) -> None:
    """Druckt jedes Diagramm auf eine eigene Seite (seitenfüllend, Seitenverhältnis bleibt)."""
    scenes = _scene_list(scenes)
    sources = [_source_rect(scene, options.margin) for scene in scenes]
    painter = QPainter()
    if not painter.begin(printer):
        raise ExportError(tr("Der Druck konnte nicht gestartet werden."))
    try:
        for index, (scene, source) in enumerate(zip(scenes, sources)):
            if index and not printer.newPage():
                raise ExportError(tr("Der Druck konnte nicht gestartet werden."))
            page = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))
            page = QRectF(0, 0, page.width(), page.height())
            _render(scene, painter, page, source, options, fill_background=False)
    finally:
        painter.end()


def ensure_extension(path: str, extension: str) -> str:
    return path if path.lower().endswith(extension.lower()) else path + extension
