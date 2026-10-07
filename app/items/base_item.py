"""Basisklasse aller PAP-Bausteine auf der Arbeitsfläche."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from app import config, styles
from app.items.shapes import TextBlock, geometry_for, paint_shape
from app.model.diagram import ElementData
from app.model.element_types import PORT_DIRECTIONS, ElementType, spec_for

# Zeichenebenen: Kommentare liegen unter Verbindungen, Verbindungen unter Bausteinen.
LAYER_COMMENT = -30.0
LAYER_CONNECTION = -20.0
LAYER_FLOW = 0.0
LAYER_OVERLAY = 1000.0
Z_ORDER_LIMIT = 9999.0

_ITEM_FONT = None


def shared_item_font():
    global _ITEM_FONT
    if _ITEM_FONT is None:
        _ITEM_FONT = styles.item_font()
    return _ITEM_FONT


def _ceil_to(value: float, step: float) -> float:
    return math.ceil(value / step - 1e-9) * step


class FlowItem(QGraphicsObject):
    """Grafische Darstellung eines Diagrammelements.

    Das Item hält eine Referenz auf seine ``ElementData`` und hält diese bei
    Verschieben und Textänderungen aktuell. Die Größe ergibt sich aus dem Text
    (quantisiert, mit typabhängiger Mindestgröße und Umbruchbreite).
    """

    ELEMENT_TYPE: ElementType = ElementType.PROCESS

    BOUNDS_MARGIN = 26.0
    SELECTION_PADDING = 5.0
    HANDLE_SIZE = 6.0
    PORT_RADIUS_PX = 4.5
    PORT_HIT_RADIUS_PX = 9.0

    def __init__(self, data: ElementData):
        super().__init__()
        self.data = data
        self.spec = spec_for(data.type)
        self.geometry = geometry_for(data.type)
        self.connections: list = []
        self._hovered = False
        self._hover_port: str | None = None
        self._ports_highlighted = False
        self._highlight_port: str | None = None
        self._editing = False
        self._preview_text: str | None = None
        self._w = float(data.width or self.spec.default_width)
        self._h = float(data.height or self.spec.default_height)
        self._text_block: TextBlock | None = None
        self._outline = QPainterPath()
        self._decoration = None
        self._shape = QPainterPath()
        self._bounds = QRectF()

        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setToolTip("")
        self.setPos(QPointF(data.x, data.y))
        self.apply_z()
        self._rebuild(notify=False)

    # ------------------------------------------------------------------ Daten
    @property
    def element_id(self) -> str:
        return self.data.id

    @property
    def element_type(self) -> ElementType:
        return self.data.type

    @property
    def is_comment(self) -> bool:
        return self.data.type is ElementType.COMMENT

    @property
    def is_junction(self) -> bool:
        return self.data.type is ElementType.JUNCTION

    @property
    def width(self) -> float:
        return self._w

    @property
    def height(self) -> float:
        return self._h

    def layer(self) -> float:
        return LAYER_COMMENT if self.is_comment else LAYER_FLOW

    def apply_z(self) -> None:
        self.data.z = max(-Z_ORDER_LIMIT, min(Z_ORDER_LIMIT, float(self.data.z)))
        self.setZValue(self.layer() + self.data.z * 1e-4)

    def set_z_order(self, value: float) -> None:
        self.data.z = value
        self.apply_z()

    def set_text(self, text: str) -> None:
        self.data.text = text
        self._preview_text = None
        self._rebuild()

    def set_preview_text(self, text: str | None) -> None:
        """Zeigt während der Inline-Bearbeitung die spätere Darstellung an."""
        self._preview_text = text
        self._rebuild()

    def set_property(self, key: str, value) -> None:
        if value is None:
            self.data.properties.pop(key, None)
        else:
            self.data.properties[key] = value
        self._rebuild()

    def set_editing(self, editing: bool) -> None:
        self._editing = editing
        self.update()

    # -------------------------------------------------------------- Geometrie
    def _theme(self):
        scene = self.scene()
        return getattr(scene, "theme", styles.current_theme()) if scene is not None else styles.current_theme()

    def _rebuild(self, notify: bool = True) -> None:
        text = self._preview_text if self._preview_text is not None else self.data.text
        font = shared_item_font()
        props = self.data.properties
        block = TextBlock(text, font, self.spec.max_text_width, self.geometry.text_alignment)
        line_height = QFontMetricsF(font).height()
        tw = block.natural_width
        th = max(block.height, line_height)
        w, h = self.geometry.size_for_text(tw, th, props)
        w = _ceil_to(max(w, self.spec.default_width), config.SIZE_STEP_WIDTH)
        h = _ceil_to(max(h, self.spec.default_height), config.SIZE_STEP_HEIGHT)

        old_rect = self.scene_rect()
        size_changed = (w, h) != (self._w, self._h)
        self.prepareGeometryChange()
        self._w, self._h = w, h
        if self._preview_text is None:
            self.data.width, self.data.height = w, h
        self._text_block = block
        self._outline = self.geometry.outline(w, h, props)
        self._decoration = self.geometry.decoration(w, h, props)
        m = self.BOUNDS_MARGIN
        self._bounds = QRectF(-w / 2 - m, -h / 2 - m, w + 2 * m, h + 2 * m)
        stroker = QPainterPathStroker()
        stroker.setWidth(6.0)
        self._shape = self._outline.united(stroker.createStroke(self._outline))
        self.update()
        if notify:
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_item_geometry_changed"):
                scene.on_item_geometry_changed(self)
                if size_changed and hasattr(scene, "on_item_resized"):
                    scene.on_item_resized(self, old_rect)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def shape(self) -> QPainterPath:
        return self._shape

    def local_rect(self) -> QRectF:
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def scene_rect(self) -> QRectF:
        return self.local_rect().translated(self.pos())

    def text_layout_info(self) -> tuple[QPointF, float, Qt.AlignmentFlag]:
        """Mittelpunkt (lokal), Umbruchbreite und Ausrichtung des Textblocks."""
        width = self.spec.max_text_width
        center = self.geometry.text_center(self._w, self._h, width, self.data.properties)
        return center, float(width), self.geometry.text_alignment

    # ---------------------------------------------------------- Anschlüsse
    @property
    def ports(self) -> tuple:
        return self.spec.ports

    def port_local_pos(self, port: str) -> QPointF:
        return self.geometry.port_point(port, self._w, self._h, self.data.properties)

    def port_scene_pos(self, port: str) -> QPointF:
        return self.mapToScene(self.port_local_pos(port))

    @staticmethod
    def port_direction(port: str) -> tuple[float, float]:
        return PORT_DIRECTIONS[port]

    def _view_scale(self) -> float:
        scene = self.scene()
        if scene is not None and scene.views():
            return max(0.01, scene.views()[0].transform().m11())
        return 1.0

    def port_hit_radius(self) -> float:
        return max(self.PORT_HIT_RADIUS_PX / self._view_scale(), 6.0)

    def port_at(self, scene_pos: QPointF) -> str | None:
        radius = self.port_hit_radius()
        if self._outline.contains(self.mapFromScene(scene_pos)):
            # Innerhalb der Form bleibt die Mitte immer zum Verschieben frei –
            # auch bei kleinem Zoom, wo der Radius sonst den Baustein überdeckt.
            radius = min(radius, max(6.0, 0.3 * min(self._w, self._h)))
        best, best_dist = None, radius
        for port in self.ports:
            p = self.port_scene_pos(port)
            dist = math.hypot(p.x() - scene_pos.x(), p.y() - scene_pos.y())
            if dist <= best_dist:
                best, best_dist = port, dist
        return best

    def nearest_port(self, scene_pos: QPointF, candidates=None) -> str:
        ports = candidates or self.ports
        return min(ports, key=lambda port: _dist2(self.port_scene_pos(port), scene_pos))

    def set_hover_port(self, port: str | None) -> None:
        if port is None:
            self.unsetCursor()
        if port != self._hover_port:
            self._hover_port = port
            if port is not None:
                self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()

    def reset_hover_state(self) -> None:
        """Hover-Zustand zurücksetzen (Qt sendet beim Entfernen kein hoverLeave)."""
        self._hovered = False
        self._ports_highlighted = False
        self._highlight_port = None
        self.set_hover_port(None)
        self.update()

    def set_ports_highlighted(self, highlighted: bool, port: str | None = None) -> None:
        if highlighted != self._ports_highlighted or port != self._highlight_port:
            self._ports_highlighted = highlighted
            self._highlight_port = port
            self.update()

    def _ports_visible(self) -> bool:
        if self._ports_highlighted or self._hovered or self._hover_port is not None:
            return True
        scene = self.scene()
        return self.isSelected() and scene is not None and getattr(scene, "single_selected", None) is self

    # ------------------------------------------------------------- Zeichnen
    def paint(self, painter: QPainter, option, widget=None) -> None:
        scene = self.scene()
        theme = self._theme()
        exporting = bool(getattr(scene, "exporting", False))
        colors = theme.element_colors(self.data.type)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        border = QColor(colors.border)
        fill = QColor(colors.fill)
        if self._hovered and not exporting:
            border = border.lighter(118)
            fill = fill.lighter(122)
        paint_shape(painter, self.geometry, self._w, self._h, colors, self.data.properties,
                    1.6, border, fill)

        if not self._editing and self._text_block is not None:
            painter.setPen(QColor(colors.text))
            center, _, _ = self.text_layout_info()
            self._text_block.draw(painter, center)

        if exporting:
            return
        if self.isSelected():
            self._paint_selection(painter, theme)
        if self._ports_visible():
            self._paint_ports(painter, theme)

    def _paint_selection(self, painter: QPainter, theme) -> None:
        pad = self.SELECTION_PADDING
        rect = self.local_rect().adjusted(-pad, -pad, pad, pad)
        color = QColor(theme.selection)
        pen = QPen(color, 1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 3.0, 3.0)
        size = self.HANDLE_SIZE / min(self._view_scale(), 1.5) if self._view_scale() > 0 else self.HANDLE_SIZE
        size = max(4.0, min(size, 12.0))
        painter.setBrush(QColor(theme.canvas_bg))
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
            painter.drawRect(QRectF(corner.x() - size / 2, corner.y() - size / 2, size, size))

    def _paint_ports(self, painter: QPainter, theme) -> None:
        scale = self._view_scale()
        radius = self.PORT_RADIUS_PX / scale
        accent = QColor(theme.selection)
        for port in self.ports:
            p = self.port_local_pos(port)
            active = port == self._hover_port or (self._ports_highlighted and port == self._highlight_port)
            pen = QPen(accent, 1.4)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if active:
                painter.setBrush(accent)
                r = radius * 1.35
            else:
                painter.setBrush(QColor(theme.port_fill))
                r = radius
            painter.drawEllipse(p, r, r)

    # -------------------------------------------------------------- Events
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.scene()
            if scene is not None and hasattr(scene, "constrain_item_position"):
                return scene.constrain_item_position(self, value)
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.data.x = float(value.x())
            self.data.y = float(value.y())
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_item_geometry_changed"):
                scene.on_item_geometry_changed(self)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.set_hover_port(None)
        self.update()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            if scene is not None and hasattr(scene, "begin_element_edit"):
                scene.begin_element_edit(self, select_all=True)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


def _dist2(a: QPointF, b: QPointF) -> float:
    dx, dy = a.x() - b.x(), a.y() - b.y()
    return dx * dx + dy * dy
