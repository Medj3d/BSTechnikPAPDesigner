"""Gerichtete Verbindung zwischen zwei Bausteinen.

Eine Verbindung ist ein echtes Szenenobjekt. Sie kennt ihre Quelle und ihr
Ziel (und deren Anschlüsse), berechnet ihren Linienverlauf über
``routing.route`` und wird automatisch neu berechnet, sobald sich einer der
beiden Bausteine bewegt oder seine Größe ändert. Die Pfeilspitze liegt immer
exakt am Zielanschluss.
"""

from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from app import styles
from app.connections import routing
from app.connections.label import ConnectionLabel
from app.i18n import tr
from app.items.base_item import LAYER_CONNECTION, FlowItem
from app.model.diagram import ConnectionData
from app.model.element_types import TRUNK_IN_KEY

ARROW_LENGTH = 10.0
ARROW_HALF_WIDTH = 4.5
JUNCTION_DOT_RADIUS = 4.0


def rect_from_qrect(rect: QRectF) -> routing.Rect:
    return routing.Rect(rect.left(), rect.top(), rect.right(), rect.bottom())


def build_arrow(tip: tuple, previous: tuple) -> QPolygonF:
    dx, dy = tip[0] - previous[0], tip[1] - previous[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    bx, by = tip[0] - ux * ARROW_LENGTH, tip[1] - uy * ARROW_LENGTH
    px, py = -uy * ARROW_HALF_WIDTH, ux * ARROW_HALF_WIDTH
    return QPolygonF([QPointF(*tip), QPointF(bx + px, by + py), QPointF(bx - px, by - py)])


def build_line_path(points: list, shorten_end: float) -> QPainterPath:
    path = QPainterPath()
    if len(points) < 2:
        return path
    path.moveTo(QPointF(*points[0]))
    for p in points[1:-1]:
        path.lineTo(QPointF(*p))
    last, prev = points[-1], points[-2]
    if shorten_end > 0:
        dx, dy = last[0] - prev[0], last[1] - prev[1]
        length = math.hypot(dx, dy)
        if length > shorten_end:
            last = (last[0] - dx / length * shorten_end, last[1] - dy / length * shorten_end)
    path.lineTo(QPointF(*last))
    return path


class ConnectionItem(QGraphicsObject):
    SHAPE_WIDTH = 10.0

    def __init__(self, data: ConnectionData, source: FlowItem, target: FlowItem):
        super().__init__()
        self.data = data
        self.source = source
        self.target = target
        self._points: list = []
        self._line_path = QPainterPath()
        self._arrow = QPolygonF()
        self._shape = QPainterPath()
        self._bounds = QRectF()
        self._hovered = False
        self._drop_highlight = False
        self._segment_drag: dict | None = None
        self._last_route_key: tuple | None = None
        self._warning: str | None = None
        # Erstellungsreihenfolge (von der Szene vergeben; bestimmt bei
        # Konflikten, welche Verbindung als Warnung markiert wird)
        self.order: int | None = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(LAYER_CONNECTION)
        self.label = ConnectionLabel(self)
        self.label.set_text(data.label)

    # ------------------------------------------------------------------ Daten
    @property
    def connection_id(self) -> str:
        return self.data.id

    @property
    def is_annotation(self) -> bool:
        return self.source.is_comment or self.target.is_comment

    def points(self) -> list:
        return list(self._points)

    def set_label(self, text: str) -> None:
        self.data.label = text or ""
        self.label.set_text(self.data.label)

    def set_routing(self, routing_info: dict) -> None:
        self.data.routing = copy.deepcopy(routing_info) if routing_info else {"mode": "auto"}
        self.update_route()

    def has_manual_routing(self) -> bool:
        return self.data.routing.get("mode") == "manual"

    def set_drop_highlight(self, highlighted: bool) -> None:
        if highlighted != self._drop_highlight:
            self._drop_highlight = highlighted
            self.update()

    # ------------------------------------------------------------ Warnung
    @property
    def warning(self) -> str | None:
        """Fachliche Warnung (Verbindung möglicherweise falsch) oder ``None``."""
        return self._warning

    def set_warning(self, message: str | None) -> None:
        if message != self._warning:
            self._warning = message
            self.setToolTip(tr("Hinweis: {message}", message=message) if message else "")
            self.update()
            self.label.update()

    # ------------------------------------------------------------ Knoten
    @property
    def ends_in_trunk(self) -> bool:
        """Eingehender Stammteil eines Verbindungsknotens (ohne Pfeilspitze)."""
        return self.target.is_junction and self.target.data.properties.get(TRUNK_IN_KEY) == self.data.id

    # ---------------------------------------------------------------- Routing
    def _route_key(self) -> tuple:
        s = self.source.port_scene_pos(self.data.source_port)
        t = self.target.port_scene_pos(self.data.target_port)
        return (s.x(), s.y(), t.x(), t.y(), self.data.source_port, self.data.target_port,
                self.source.width, self.source.height, self.target.width, self.target.height)

    def update_route(self, allow_translate: bool = False) -> None:
        """Aktualisiert den Linienverlauf.

        Wurden Quelle und Ziel um denselben Betrag verschoben (z. B. beim
        gemeinsamen Verschieben mehrerer Bausteine), wird der bestehende
        Linienzug nur verschoben – das ist schnell und bewahrt die Form. Eine
        manuell gesetzte Mittelachse wandert dabei mit.
        """
        if self.source is None or self.target is None:
            return
        key = self._route_key()
        last = self._last_route_key
        if allow_translate and last is not None and self._points and last[4:] == key[4:]:
            dx, dy = key[0] - last[0], key[1] - last[1]
            if abs((key[2] - last[2]) - dx) < 1e-6 and abs((key[3] - last[3]) - dy) < 1e-6:
                if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                    return
                if self.has_manual_routing():
                    axis = self.data.routing.get("axis")
                    try:
                        value = float(self.data.routing.get("value", 0.0))
                    except (TypeError, ValueError):
                        value = 0.0
                    self.data.routing = {"mode": "manual", "axis": axis,
                                         "value": value + (dx if axis == "x" else dy)}
                self._last_route_key = key
                self.set_points([(x + dx, y + dy) for x, y in self._points])
                return
        sp, tp = self.data.source_port, self.data.target_port
        s = self.source.port_scene_pos(sp)
        t = self.target.port_scene_pos(tp)
        scene = self.scene()
        obstacles = scene.routing_obstacles(self) if scene is not None and hasattr(scene, "routing_obstacles") else []
        # Ein Verbindungsknoten hat keinen „Körper“, den die Linie meiden müsste
        source_rect = None if self.source.is_junction else rect_from_qrect(self.source.scene_rect())
        target_rect = None if self.target.is_junction else rect_from_qrect(self.target.scene_rect())
        points = routing.route((s.x(), s.y()), sp, (t.x(), t.y()), tp, source_rect, target_rect,
                               obstacles, self.data.routing)
        self._last_route_key = key
        self.set_points(points)

    def adopt_path(self, points: list) -> bool:
        """Übernimmt einen gespeicherten Linienverlauf, wenn er zu den Anschlüssen passt.

        Passt er nicht (z. B. weil ein Baustein inzwischen eine andere Größe
        hat), bleibt der frisch berechnete Verlauf bestehen.
        """
        key = self._route_key()
        try:
            path = [(float(x), float(y)) for x, y in points]
        except (TypeError, ValueError):
            return False
        if len(path) < 2:
            return False
        (sx, sy), (tx, ty) = path[0], path[-1]
        if max(abs(sx - key[0]), abs(sy - key[1]), abs(tx - key[2]), abs(ty - key[3])) > 0.01:
            return False
        self._last_route_key = key
        self.set_points(path)
        return True

    def _arrow_polygon(self, points: list) -> QPolygonF:
        if not points:
            return QPolygonF()
        tip = points[-1]
        previous = points[-2] if len(points) >= 2 else tip
        if abs(tip[0] - previous[0]) + abs(tip[1] - previous[1]) < 1.0:
            # Entartetes letztes Segment: Pfeil in Richtung des Zielanschlusses
            dx, dy = routing.DIRECTIONS.get(self.data.target_port, (0.0, -1.0))
            previous = (tip[0] + dx * ARROW_LENGTH, tip[1] + dy * ARROW_LENGTH)
        return build_arrow(tip, previous)

    def set_points(self, points: list) -> None:
        self.prepareGeometryChange()
        self._points = points
        no_arrow = self.is_annotation or self.ends_in_trunk
        drawn = points
        if not no_arrow and self.target.is_junction and len(points) >= 2:
            # Pfeilspitze endet am Rand des Knotenpunkts, nicht darunter
            (px, py), (tx, ty) = points[-2], points[-1]
            length = math.hypot(tx - px, ty - py)
            if length > JUNCTION_DOT_RADIUS + 2:
                ratio = (JUNCTION_DOT_RADIUS + 1) / length
                drawn = points[:-1] + [(tx - (tx - px) * ratio, ty - (ty - py) * ratio)]
        self._line_path = build_line_path(drawn, 0.0 if no_arrow else ARROW_LENGTH * 0.8)
        self._arrow = QPolygonF() if no_arrow else self._arrow_polygon(drawn)
        full = QPainterPath(self._line_path)
        if not self._arrow.isEmpty():
            full.addPolygon(self._arrow)
        stroker = QPainterPathStroker()
        stroker.setWidth(self.SHAPE_WIDTH)
        stroker.setCapStyle(Qt.PenCapStyle.SquareCap)
        self._shape = stroker.createStroke(full)
        self._shape.addPolygon(self._arrow)
        self._bounds = self._shape.boundingRect().adjusted(-8, -8, 8, 8)
        self.label.update_position()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def shape(self) -> QPainterPath:
        return self._shape

    # ------------------------------------------------------------- Zeichnen
    def paint(self, painter: QPainter, option, widget=None) -> None:
        if len(self._points) < 2:
            return
        scene = self.scene()
        theme = getattr(scene, "theme", styles.current_theme()) if scene is not None else styles.current_theme()
        exporting = bool(getattr(scene, "exporting", False))
        color = QColor(theme.connection)
        width = 1.5
        if not exporting:
            if self._drop_highlight:
                color = QColor(theme.selection)
                width = 2.4
            elif self._warning:
                # Warnung: rot, auch wenn ausgewählt (dann etwas kräftiger)
                color = QColor(theme.connection_invalid)
                width = 2.2 if self.isSelected() else 1.7
                if self._hovered and not self.isSelected():
                    color = color.lighter(115)
            elif self.isSelected():
                color = QColor(theme.selection)
                width = 1.9
            elif self._hovered:
                color = QColor(theme.connection_hover)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(color, width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        if self.is_annotation:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([3.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._line_path)
        if not self._arrow.isEmpty():
            painter.setPen(QPen(color, 1.0))
            painter.setBrush(color)
            painter.drawPolygon(self._arrow)
        if self.isSelected() and not exporting:
            self._paint_segment_handles(painter, theme)

    def _paint_segment_handles(self, painter: QPainter, theme) -> None:
        pen = QPen(QColor(theme.selection), 1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(theme.canvas_bg))
        for index in routing.interior_segments(self._points):
            a, b = self._points[index], self._points[index + 1]
            center = QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            painter.drawEllipse(center, 3.5, 3.5)

    # -------------------------------------------------------------- Events
    def _view_scale(self) -> float:
        scene = self.scene()
        if scene is not None and scene.views():
            return max(0.01, scene.views()[0].transform().m11())
        return 1.0

    def interior_segment_at(self, scene_pos: QPointF) -> int | None:
        tolerance = max(5.0, 6.0 / self._view_scale())
        x, y = scene_pos.x(), scene_pos.y()
        for index in routing.interior_segments(self._points):
            (x1, y1), (x2, y2) = self._points[index], self._points[index + 1]
            if abs(x1 - x2) < 1e-6:
                if abs(x - x1) <= tolerance and min(y1, y2) - tolerance <= y <= max(y1, y2) + tolerance:
                    return index
            elif abs(y1 - y2) < 1e-6:
                if abs(y - y1) <= tolerance and min(x1, x2) - tolerance <= x <= max(x1, x2) + tolerance:
                    return index
        return None

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event) -> None:
        index = self.interior_segment_at(event.scenePos()) if self.isSelected() else None
        if index is not None:
            axis = routing.segment_axis(self._points, index)
            self.setCursor(Qt.CursorShape.SplitHCursor if axis == "x" else Qt.CursorShape.SplitVCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if event.button() == Qt.MouseButton.LeftButton and not ctrl:
            index = self.interior_segment_at(event.scenePos())
            if index is not None:
                scene = self.scene()
                if not self.isSelected() and scene is not None:
                    scene.clearSelection()
                    self.setSelected(True)
                axis = routing.segment_axis(self._points, index)
                if axis is not None:
                    self._segment_drag = {"axis": axis, "old": copy.deepcopy(self.data.routing)}
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._segment_drag is not None:
            axis = self._segment_drag["axis"]
            value = event.scenePos().x() if axis == "x" else event.scenePos().y()
            scene = self.scene()
            if scene is not None and hasattr(scene, "snap_value"):
                value = scene.snap_value(value)
            new_routing = {"mode": "manual", "axis": axis, "value": float(value)}
            if new_routing != self.data.routing:
                self.data.routing = new_routing
                self.update_route()
            event.accept()
            return
        super().mouseMoveEvent(event)

    @property
    def is_segment_dragging(self) -> bool:
        return self._segment_drag is not None

    def end_segment_drag(self, cancel: bool, commit: bool = True) -> None:
        """Beendet das Verschieben des Mittelsegments (Esc = verwerfen)."""
        if self._segment_drag is None:
            return
        old = self._segment_drag["old"]
        self._segment_drag = None
        if cancel:
            if old != self.data.routing:
                self.set_routing(old)
            return
        new = copy.deepcopy(self.data.routing)
        scene = self.scene()
        if commit and old != new and scene is not None and hasattr(scene, "commit_routing_change"):
            scene.commit_routing_change(self, old, new)

    def reset_hover_state(self) -> None:
        self._hovered = False
        self._drop_highlight = False
        self.unsetCursor()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._segment_drag is not None:
            self.end_segment_drag(cancel=False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        scene = self.scene()
        if event.button() == Qt.MouseButton.LeftButton and scene is not None and hasattr(scene, "begin_label_edit"):
            scene.begin_label_edit(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
