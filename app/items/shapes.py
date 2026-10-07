"""Programmatisch erzeugte PAP-Formen.

Jede Form ist um den Ursprung (0, 0) zentriert. Eine ``ShapeGeometry`` liefert

* die Umrisslinie (``outline``),
* optionale Zusatzlinien (``decoration``, z. B. die Doppelstriche des
  Unterprogramms),
* die Mindestgröße für einen gegebenen Textblock (``size_for_text``),
* die Lage der Anschlusspunkte (``port_point``).

Die Formen entsprechen der klassischen PAP-Notation (DIN 66001):

* Start/Ende        – abgerundetes Element (Oval/Stadion)
* Eingabe/Ausgabe   – Parallelogramm
* Vorgang           – Rechteck
* Unterprogramm     – Rechteck mit doppelten senkrechten Seitenlinien
* Verzweigung       – Raute
* Schleife          – Schleifenbegrenzung: Beginn mit abgeschrägten oberen,
                      Ende mit abgeschrägten unteren Ecken
* Kommentar         – Text mit offener eckiger Klammer
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QTextLayout, QTextOption)

from app.model.element_types import (LOOP_END, LOOP_PART_KEY, PORT_BOTTOM, PORT_LEFT,
                                     PORT_RIGHT, PORT_TOP, ElementType)


class ShapeGeometry:
    pad_x = 14.0
    pad_y = 10.0
    text_alignment = Qt.AlignmentFlag.AlignHCenter
    draw_outline_border = True
    translucent_fill = False

    def outline(self, w: float, h: float, props: dict | None = None) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(-w / 2, -h / 2, w, h))
        return path

    def decoration(self, w: float, h: float, props: dict | None = None) -> QPainterPath | None:
        return None

    def size_for_text(self, tw: float, th: float, props: dict | None = None) -> tuple[float, float]:
        return tw + 2 * self.pad_x, th + 2 * self.pad_y

    def text_center(self, w: float, h: float, layout_width: float,
                    props: dict | None = None) -> QPointF:
        return QPointF(0.0, 0.0)

    def port_point(self, port: str, w: float, h: float, props: dict | None = None) -> QPointF:
        if port == PORT_TOP:
            return QPointF(0.0, -h / 2)
        if port == PORT_BOTTOM:
            return QPointF(0.0, h / 2)
        if port == PORT_LEFT:
            return QPointF(-w / 2, 0.0)
        return QPointF(w / 2, 0.0)


class RectGeometry(ShapeGeometry):
    radius = 3.0

    def outline(self, w, h, props=None):
        path = QPainterPath()
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), self.radius, self.radius)
        return path


class ParallelogramGeometry(ShapeGeometry):
    max_skew = 20.0

    def skew(self, h: float) -> float:
        return min(self.max_skew, h * 0.35)

    def outline(self, w, h, props=None):
        s = self.skew(h)
        poly = QPolygonF([
            QPointF(-w / 2 + s, -h / 2),
            QPointF(w / 2, -h / 2),
            QPointF(w / 2 - s, h / 2),
            QPointF(-w / 2, h / 2),
        ])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        return path

    def size_for_text(self, tw, th, props=None):
        return tw + 2 * self.max_skew + 2 * self.pad_x, th + 2 * self.pad_y

    def port_point(self, port, w, h, props=None):
        s = self.skew(h)
        if port == PORT_LEFT:
            return QPointF(-w / 2 + s / 2, 0.0)
        if port == PORT_RIGHT:
            return QPointF(w / 2 - s / 2, 0.0)
        return super().port_point(port, w, h, props)


class SubprogramGeometry(RectGeometry):
    bar_inset = 10.0
    radius = 2.0

    def decoration(self, w, h, props=None):
        path = QPainterPath()
        x = w / 2 - self.bar_inset
        path.moveTo(-x, -h / 2)
        path.lineTo(-x, h / 2)
        path.moveTo(x, -h / 2)
        path.lineTo(x, h / 2)
        return path

    def size_for_text(self, tw, th, props=None):
        return tw + 2 * (self.bar_inset + self.pad_x), th + 2 * self.pad_y


class DiamondGeometry(ShapeGeometry):
    aspect = 160.0 / 120.0
    pad_x = 8.0
    pad_y = 6.0

    def outline(self, w, h, props=None):
        poly = QPolygonF([
            QPointF(0.0, -h / 2),
            QPointF(w / 2, 0.0),
            QPointF(0.0, h / 2),
            QPointF(-w / 2, 0.0),
        ])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        return path

    def size_for_text(self, tw, th, props=None):
        # Ein zentriertes Textrechteck (tw x th) passt in eine Raute (W x H),
        # wenn tw/W + th/H <= 1 gilt. Bei festem Seitenverhältnis ergibt sich:
        width = (tw + 2 * self.pad_x) + self.aspect * (th + 2 * self.pad_y)
        return width, width / self.aspect


class LoopGeometry(ShapeGeometry):
    """Schleifenbegrenzung: Beginn oben abgeschrägt, Ende unten abgeschrägt."""

    def chamfer(self, h: float) -> float:
        return min(16.0, h * 0.3)

    @staticmethod
    def is_end(props: dict | None) -> bool:
        return bool(props) and props.get(LOOP_PART_KEY) == LOOP_END

    def outline(self, w, h, props=None):
        c = self.chamfer(h)
        l, r, t, b = -w / 2, w / 2, -h / 2, h / 2
        if self.is_end(props):
            points = [QPointF(l, t), QPointF(r, t), QPointF(r, b - c), QPointF(r - c, b),
                      QPointF(l + c, b), QPointF(l, b - c)]
        else:
            points = [QPointF(l + c, t), QPointF(r - c, t), QPointF(r, t + c), QPointF(r, b),
                      QPointF(l, b), QPointF(l, t + c)]
        path = QPainterPath()
        path.addPolygon(QPolygonF(points))
        path.closeSubpath()
        return path

    def size_for_text(self, tw, th, props=None):
        return tw + 2 * (16.0 + 6.0), th + 2 * self.pad_y


class StadiumGeometry(ShapeGeometry):
    """Start/Ende: abgerundetes Element."""

    def outline(self, w, h, props=None):
        path = QPainterPath()
        radius = min(h / 2, w / 2)
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), radius, radius)
        return path

    def size_for_text(self, tw, th, props=None):
        h = th + 2 * self.pad_y
        return tw + 2 * self.pad_x + h * 0.6, h


class CommentGeometry(ShapeGeometry):
    """Kommentar: freier Text mit offener eckiger Klammer auf der linken Seite."""

    bracket_width = 10.0
    text_alignment = Qt.AlignmentFlag.AlignLeft
    draw_outline_border = False
    translucent_fill = True

    def outline(self, w, h, props=None):
        path = QPainterPath()
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), 3.0, 3.0)
        return path

    def decoration(self, w, h, props=None):
        path = QPainterPath()
        path.moveTo(-w / 2 + self.bracket_width, -h / 2)
        path.lineTo(-w / 2, -h / 2)
        path.lineTo(-w / 2, h / 2)
        path.lineTo(-w / 2 + self.bracket_width, h / 2)
        return path

    def text_center(self, w, h, layout_width, props=None):
        return QPointF(-w / 2 + self.pad_x + layout_width / 2, 0.0)


class JunctionGeometry(ShapeGeometry):
    """Verbindungsknoten: kleiner Punkt, alle Anschlüsse liegen im Mittelpunkt."""

    def outline(self, w, h, props=None):
        path = QPainterPath()
        path.addEllipse(QPointF(0.0, 0.0), w / 2, h / 2)
        return path

    def port_point(self, port, w, h, props=None):
        return QPointF(0.0, 0.0)


GEOMETRIES: dict[ElementType, ShapeGeometry] = {
    ElementType.JUNCTION: JunctionGeometry(),
    ElementType.START: StadiumGeometry(),
    ElementType.END: StadiumGeometry(),
    ElementType.INPUT: ParallelogramGeometry(),
    ElementType.OUTPUT: ParallelogramGeometry(),
    ElementType.PROCESS: RectGeometry(),
    ElementType.SUBPROGRAM: SubprogramGeometry(),
    ElementType.DECISION: DiamondGeometry(),
    ElementType.LOOP: LoopGeometry(),
    ElementType.COMMENT: CommentGeometry(),
}


def geometry_for(element_type: ElementType) -> ShapeGeometry:
    return GEOMETRIES[ElementType(element_type)]


class TextBlock:
    """Umbrochener, zentrierbarer Textblock auf Basis von ``QTextLayout``.

    Umbruch an Wortgrenzen, bei sehr langen Wörtern notfalls innerhalb des
    Wortes. ``\\n`` erzeugt einen expliziten Zeilenumbruch.
    """

    def __init__(self, text: str, font: QFont, wrap_width: float,
                 alignment=Qt.AlignmentFlag.AlignHCenter):
        self.text = text
        self.wrap_width = float(wrap_width)
        layout_text = text.replace("\r\n", "\n").replace("\n", " ")
        self.layout = QTextLayout(layout_text, font)
        option = QTextOption(alignment)
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        option.setUseDesignMetrics(True)
        self.layout.setTextOption(option)
        self.layout.setCacheEnabled(True)
        self.layout.beginLayout()
        y = 0.0
        natural = 0.0
        while True:
            line = self.layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(self.wrap_width)
            line.setPosition(QPointF(0.0, y))
            y += line.height()
            natural = max(natural, line.naturalTextWidth())
        self.layout.endLayout()
        self.natural_width = natural
        self.height = y

    def draw(self, painter: QPainter, center: QPointF) -> None:
        origin = QPointF(center.x() - self.wrap_width / 2, center.y() - self.height / 2)
        self.layout.draw(painter, origin)


def render_shape_pixmap(element_type: ElementType, width: float, height: float, theme,
                        device_pixel_ratio: float = 1.0, scale: float = 1.0,
                        props: dict | None = None, opacity: float = 1.0) -> QPixmap:
    """Rendert eine Form als Pixmap (für Werkzeugpalette und Drag-Vorschau)."""
    geometry = geometry_for(element_type)
    colors = theme.element_colors(element_type)
    margin = 3.0
    pix_w = int((width * scale + 2 * margin) * device_pixel_ratio)
    pix_h = int((height * scale + 2 * margin) * device_pixel_ratio)
    pixmap = QPixmap(max(1, pix_w), max(1, pix_h))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(opacity)
    painter.translate(width * scale / 2 + margin, height * scale / 2 + margin)
    painter.scale(scale, scale)
    paint_shape(painter, geometry, width, height, colors, props, pen_width=1.6 / max(scale, 0.01))
    painter.end()
    return pixmap


def paint_shape(painter: QPainter, geometry: ShapeGeometry, w: float, h: float, colors,
                props: dict | None = None, pen_width: float = 1.6,
                border_override: QColor | None = None, fill_override: QColor | None = None) -> None:
    """Zeichnet Umriss und Zusatzlinien einer Form (ohne Text)."""
    border = QColor(border_override) if border_override is not None else QColor(colors.border)
    fill = QColor(fill_override) if fill_override is not None else QColor(colors.fill)
    if geometry.translucent_fill:
        fill.setAlphaF(min(fill.alphaF(), 0.55))
    pen = QPen(border, pen_width)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setBrush(fill)
    painter.setPen(pen if geometry.draw_outline_border else Qt.PenStyle.NoPen)
    painter.drawPath(geometry.outline(w, h, props))
    decoration = geometry.decoration(w, h, props)
    if decoration is not None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawPath(decoration)
