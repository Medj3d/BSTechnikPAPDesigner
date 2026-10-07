"""Temporäre Linie, die während des Verbindens angezeigt wird.

Zustände:

* ``ok``       – gültiges Ziel (Akzentfarbe)
* ``warning``  – Verbindung ist möglicherweise falsch, wird aber erstellt (rot)
* ``blocked``  – Verbindung ist technisch nicht möglich (rot, blass)

Liegt ein Endpunkt auf einem bestehenden Pfeil, wird der künftige
Verbindungsknoten als Kreis markiert.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem

from app import styles
from app.connections.connection import ARROW_LENGTH, build_arrow, build_line_path
from app.items.base_item import LAYER_OVERLAY

STATE_OK = "ok"
STATE_WARNING = "warning"
STATE_BLOCKED = "blocked"
MARKER_RADIUS = 5.0


class TempConnectionItem(QGraphicsItem):
    def __init__(self):
        super().__init__()
        self._path = QPainterPath()
        self._arrow = QPolygonF()
        self._state = STATE_OK
        self._markers: list[QPointF] = []
        self._bounds = QRectF()
        self.setZValue(LAYER_OVERLAY)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)

    @property
    def state(self) -> str:
        return self._state

    def set_points(self, points: list, state=STATE_OK, markers: list[QPointF] | None = None) -> None:
        if state is True:
            state = STATE_OK
        elif state is False:
            state = STATE_WARNING
        self.prepareGeometryChange()
        self._state = state
        self._markers = list(markers or [])
        self._path = build_line_path(points, ARROW_LENGTH * 0.8)
        self._arrow = build_arrow(points[-1], points[-2]) if len(points) >= 2 else QPolygonF()
        bounds = self._path.boundingRect().united(self._arrow.boundingRect())
        for marker in self._markers:
            bounds = bounds.united(QRectF(marker.x() - 10, marker.y() - 10, 20, 20))
        self._bounds = bounds.adjusted(-6, -6, 6, 6)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter: QPainter, option, widget=None) -> None:
        theme = styles.current_theme()
        if self._state == STATE_OK:
            color = QColor(theme.selection)
        else:
            color = QColor(theme.connection_invalid)
            if self._state == STATE_BLOCKED:
                color.setAlphaF(0.55)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(color, 1.6)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)
        if not self._arrow.isEmpty():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(self._arrow)
        # künftiger Verbindungsknoten auf einem bestehenden Pfeil
        for marker in self._markers:
            paint_anchor(painter, marker)


def paint_anchor(painter: QPainter, center: QPointF) -> None:
    """Markierung eines (künftigen) Verbindungsknotens: Ring mit Punkt."""
    theme = styles.current_theme()
    ring = QPen(QColor(theme.selection), 1.6)
    ring.setCosmetic(True)
    painter.setPen(ring)
    painter.setBrush(QColor(theme.canvas_bg))
    painter.drawEllipse(center, MARKER_RADIUS + 2, MARKER_RADIUS + 2)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.selection))
    painter.drawEllipse(center, MARKER_RADIUS - 1.5, MARKER_RADIUS - 1.5)


class AnchorMarker(QGraphicsItem):
    """Zeigt beim Überfahren eines Pfeils mit gedrückter Umschalttaste,
    wo eine neue Verbindung angesetzt würde."""

    def __init__(self):
        super().__init__()
        self.setZValue(LAYER_OVERLAY)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)

    def boundingRect(self) -> QRectF:
        r = MARKER_RADIUS + 5
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_anchor(painter, QPointF(0.0, 0.0))
