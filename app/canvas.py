"""Die Arbeitsfläche (Ansicht auf eine Diagrammszene).

* Punktraster im Hintergrund, adaptiv je nach Zoomstufe
* Zoom mit dem Mausrad, am Mauszeiger orientiert (25 % … 400 %)
* Schwenken mit gedrückter rechter (oder mittlerer) Maustaste bzw. Leertaste
* Rechtsklick ohne Bewegung öffnet das Kontextmenü
* Drag & Drop von Bausteinen aus der Werkzeugpalette mit Vorschau
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QFrame, QGraphicsView

from app import config, styles
from app.document import DiagramDocument
from app.model.element_types import ElementType, is_valid_type

ELEMENT_MIME_TYPE = "application/x-bstechnik-element"
PAN_CLICK_TOLERANCE = 4
MIN_DOT_SPACING_PX = 10.0


class DiagramView(QGraphicsView):
    zoom_changed = Signal(float)
    cursor_scene_pos_changed = Signal(QPointF)
    context_menu_requested = Signal(QPointF, QPoint)

    def __init__(self, document: DiagramDocument, parent=None):
        super().__init__(document.scene, parent)
        self.document = document
        self._zoom = 1.0
        self._pan_button = None
        self._pan_last = QPoint()
        self._pan_origin = QPoint()
        self._pan_moved = False
        self._space_pressed = False
        self._drop_type: ElementType | None = None
        self._wheel_anchor: tuple[tuple, QPointF] | None = None

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Maus-Kontextmenüs öffnen beim Loslassen der rechten Taste (siehe
        # mouseReleaseEvent); contextMenuEvent behandelt nur die Tastatur.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        document.view_state_provider = self.view_state
        document.settings_changed.connect(self.refresh_background)
        self.restore_view_state()

    # ================================================================ Zoom
    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, zoom: float, anchor: QPoint | None = None, scene_anchor: QPointF | None = None) -> None:
        """Setzt die Zoomstufe; der Szenenpunkt ``scene_anchor`` bleibt unter ``anchor``."""
        zoom = max(config.MIN_ZOOM, min(config.MAX_ZOOM, zoom))
        if abs(zoom - self._zoom) < 1e-9:
            return
        if anchor is None:
            anchor = self.viewport().rect().center()
        if scene_anchor is None:
            scene_anchor = self.mapToScene(anchor)
        self._zoom = zoom
        self.setTransform(QTransform.fromScale(zoom, zoom))
        # Neue Bildmitte so wählen, dass der Ankerpunkt am selben Bildschirmort bleibt
        viewport = self.viewport()
        center_view = QPointF(viewport.width() / 2.0, viewport.height() / 2.0)
        offset = (center_view - QPointF(anchor)) / zoom
        self.centerOn(scene_anchor + offset)
        self.resetCachedContent()
        viewport.update()
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * config.ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / config.ZOOM_STEP)

    def zoom_reset(self) -> None:
        self.set_zoom(1.0)

    def fit_diagram(self) -> None:
        bounds = self.document.scene.diagram_bounds()
        if bounds.isNull() or bounds.isEmpty():
            self.set_zoom(1.0)
            self.centerOn(0, 0)
            return
        bounds = bounds.adjusted(-40, -40, 40, 40)
        view = self.viewport().rect()
        zoom = min(view.width() / bounds.width(), view.height() / bounds.height())
        self.set_zoom(zoom)
        self.centerOn(bounds.center())

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta == 0:
            event.accept()
            return
        factor = config.ZOOM_STEP ** (delta / 120.0)
        pos = event.position().toPoint()
        # Solange Mauszeiger und Ansicht unverändert sind, bleibt derselbe
        # Szenenpunkt der Anker – so summieren sich bei feinen Touchpad-Schritten
        # keine Rundungsfehler.
        state = (pos.x(), pos.y(), self.horizontalScrollBar().value(), self.verticalScrollBar().value(),
                 self._zoom)
        if self._wheel_anchor is not None and self._wheel_anchor[0] == state:
            scene_anchor = self._wheel_anchor[1]
        else:
            scene_anchor = self.mapToScene(pos)
        self.set_zoom(self._zoom * factor, pos, scene_anchor)
        self._wheel_anchor = ((pos.x(), pos.y(), self.horizontalScrollBar().value(),
                               self.verticalScrollBar().value(), self._zoom), QPointF(scene_anchor))
        event.accept()

    # ============================================================ Ansicht
    def view_state(self) -> tuple[float, float, float]:
        # Die Mitte genau so bestimmen, wie centerOn() sie beim Wiederherstellen
        # setzt (halbe Breite/Höhe, nicht der ganzzahlige Mittelpunkt) – sonst
        # wandert die Ansicht bei jedem Öffnen und Speichern um ein Pixel.
        viewport = self.viewport()
        origin = self.mapToScene(QPoint(0, 0))
        return (self._zoom, origin.x() + viewport.width() / (2.0 * self._zoom),
                origin.y() + viewport.height() / (2.0 * self._zoom))

    def restore_view_state(self) -> None:
        settings = self.document.settings
        zoom = max(config.MIN_ZOOM, min(config.MAX_ZOOM, settings.zoom or 1.0))
        self._zoom = zoom
        self.setTransform(QTransform.fromScale(zoom, zoom))
        self.centerOn(QPointF(settings.view_center_x, settings.view_center_y))

    def visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def visible_center(self) -> QPointF:
        return self.mapToScene(self.viewport().rect().center())

    def refresh_background(self) -> None:
        self.resetCachedContent()
        self.viewport().update()

    # ============================================================ Raster
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        theme = styles.current_theme()
        painter.fillRect(rect, QColor(theme.canvas_bg))
        settings = self.document.settings
        if not settings.grid_visible:
            return
        grid = max(config.MIN_GRID_SIZE, int(settings.grid_size))
        scale = self.transform().m11()
        step = float(grid)
        # adaptiv: bei starkem Herauszoomen nur jeden 2./4./... Punkt zeichnen
        while step * scale < MIN_DOT_SPACING_PX:
            step *= 2
        major = step * 5

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        dot_px = 1.6 if scale >= 0.75 else 1.3
        self._draw_dots(painter, rect, step, QColor(theme.grid_dot), dot_px)
        if major * scale >= 40:
            self._draw_dots(painter, rect, major, QColor(theme.grid_dot_major), dot_px + 0.6)
        painter.restore()

    @staticmethod
    def _draw_dots(painter: QPainter, rect: QRectF, step: float, color: QColor, size_px: float) -> None:
        pen = QPen(color, size_px)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        left = math.floor(rect.left() / step) * step
        top = math.floor(rect.top() / step) * step
        columns = int((rect.right() - left) / step) + 2
        rows = int((rect.bottom() - top) / step) + 2
        if columns * rows > 250_000:
            return
        row = QPolygonF([QPointF(left + i * step, 0.0) for i in range(columns)])
        for j in range(rows):
            painter.drawPoints(row.translated(0.0, top + j * step))

    # ======================================================= Maus / Pan
    def _start_pan(self, event, button) -> None:
        self._pan_button = button
        self._pan_last = event.position().toPoint()
        self._pan_origin = self._pan_last
        self._pan_moved = False
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mousePressEvent(self, event) -> None:
        button = event.button()
        if button in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) or (
                button == Qt.MouseButton.LeftButton and self._space_pressed):
            if self._pan_button is None:
                self._start_pan(event, button)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._pan_button is not None:
            delta = pos - self._pan_last
            self._pan_last = pos
            if (pos - self._pan_origin).manhattanLength() > PAN_CLICK_TOLERANCE:
                self._pan_moved = True
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)
        self.cursor_scene_pos_changed.emit(self.mapToScene(pos))

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_button is not None and event.button() == self._pan_button:
            was_click = not self._pan_moved and self._pan_button == Qt.MouseButton.RightButton
            self._pan_button = None
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if self._space_pressed
                                      else Qt.CursorShape.ArrowCursor)
            if was_click:
                pos = event.position().toPoint()
                self.context_menu_requested.emit(self.mapToScene(pos), self.viewport().mapToGlobal(pos))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        # Maus-Kontextmenüs werden beim Loslassen der rechten Taste ausgelöst;
        # hier nur die Kontextmenü-Taste der Tastatur behandeln.
        if event.reason() == event.Reason.Keyboard:
            scene = self.document.scene
            selected = scene.selectedItems()
            if selected:
                scene_pos = selected[0].sceneBoundingRect().center()
            else:
                scene_pos = self.visible_center()
            view_pos = self.mapFromScene(scene_pos)
            self.context_menu_requested.emit(scene_pos, self.viewport().mapToGlobal(view_pos))
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and not self.document.scene.is_editing:
            self._space_pressed = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._space_pressed:
            self._space_pressed = False
            if self._pan_button is None:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        self._space_pressed = False
        super().focusOutEvent(event)

    # ====================================================== Drag & Drop
    @staticmethod
    def _element_type_from_mime(mime) -> ElementType | None:
        if mime is None or not mime.hasFormat(ELEMENT_MIME_TYPE):
            return None
        value = bytes(mime.data(ELEMENT_MIME_TYPE)).decode("utf-8", errors="ignore")
        return ElementType(value) if is_valid_type(value) else None

    def dragEnterEvent(self, event) -> None:
        element_type = self._element_type_from_mime(event.mimeData())
        if element_type is not None:
            self._drop_type = element_type
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.document.scene.update_drop_preview(element_type, self.mapToScene(event.position().toPoint()))
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._drop_type is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.document.scene.update_drop_preview(self._drop_type, self.mapToScene(event.position().toPoint()))
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._drop_type = None
        self.document.scene.clear_drop_preview()
        event.accept()

    def dropEvent(self, event) -> None:
        element_type = self._element_type_from_mime(event.mimeData()) or self._drop_type
        self._drop_type = None
        if element_type is None:
            self.document.scene.clear_drop_preview()
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.document.scene.drop_element(element_type, self.mapToScene(event.position().toPoint()))
        self.setFocus(Qt.FocusReason.OtherFocusReason)
