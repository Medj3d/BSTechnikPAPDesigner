"""Verbindungsknoten (Junction) auf einem bestehenden Pfeil.

Wird eine Verbindung an einen vorhandenen Pfeil A → B angeschlossen, wird
der Pfeil an dieser Stelle aufgetrennt: A → Knoten → B. Die neue Verbindung
beginnt bzw. endet am Knoten. So entsteht eine echte logische Verbindung
zwischen den Kanten des Ablaufgraphen – nicht bloß eine Linie, die optisch
über dem Pfeil liegt.

Der Knoten merkt sich die beiden Teile des ursprünglichen Pfeils („Stamm“).
Der eingehende Stammteil wird ohne Pfeilspitze gezeichnet, damit der Pfeil
optisch durchgehend bleibt; beim Löschen der Abzweigung wird der Pfeil
wieder zusammengefügt.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from app.items.base_item import FlowItem
from app.model.element_types import JUNCTION_SIZE, TRUNK_IN_KEY, TRUNK_OUT_KEY, ElementType

DOT_RADIUS = 4.0
HIT_RADIUS = 7.0


class JunctionItem(FlowItem):
    ELEMENT_TYPE = ElementType.JUNCTION

    @property
    def trunk_in(self) -> str | None:
        return self.data.properties.get(TRUNK_IN_KEY)

    @property
    def trunk_out(self) -> str | None:
        return self.data.properties.get(TRUNK_OUT_KEY)

    def _rebuild(self, notify: bool = True) -> None:
        size = float(JUNCTION_SIZE)
        self.prepareGeometryChange()
        self._w = self._h = size
        self.data.width = self.data.height = size
        self.data.text = ""
        self._text_block = None
        self._outline = QPainterPath()
        self._outline.addEllipse(QPointF(0.0, 0.0), size / 2, size / 2)
        self._decoration = None
        margin = self.BOUNDS_MARGIN
        self._bounds = QRectF(-size / 2 - margin, -size / 2 - margin, size + 2 * margin, size + 2 * margin)
        self._shape = QPainterPath()
        self._shape.addEllipse(QPointF(0.0, 0.0), HIT_RADIUS, HIT_RADIUS)
        self.update()
        if notify:
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_item_geometry_changed"):
                scene.on_item_geometry_changed(self)

    def set_text(self, text: str) -> None:
        # Verbindungspunkte tragen keinen Text
        self.data.text = ""

    def set_property(self, key: str, value) -> None:
        super().set_property(key, value)
        # Stamm-Zuordnung beeinflusst die Pfeilspitzen der angeschlossenen Linien
        for conn in self.connections:
            conn.set_points(conn.points())

    def text_layout_info(self):
        return QPointF(0.0, 0.0), 0.0, Qt.AlignmentFlag.AlignHCenter

    def paint(self, painter: QPainter, option, widget=None) -> None:
        scene = self.scene()
        theme = self._theme()
        exporting = bool(getattr(scene, "exporting", False))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(theme.element_colors(ElementType.JUNCTION).border)
        highlighted = not exporting and (self.isSelected() or self._ports_highlighted or self._hover_port
                                         or self._hovered)
        if highlighted:
            color = QColor(theme.selection)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = DOT_RADIUS + (1.0 if highlighted else 0.0)
        painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
        if not exporting and (self.isSelected() or self._ports_highlighted):
            pen = QPen(QColor(theme.selection), 1.2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0.0, 0.0), radius + 4.0, radius + 4.0)

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()  # kein Text zu bearbeiten
