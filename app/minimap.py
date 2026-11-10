"""Minikarte wie in VS Code: ein schmaler Streifen am rechten Rand der Arbeitsfläche mit dem ganzen Plan.

Der Plan wird auf die Breite des Streifens verkleinert. Ein durchscheinender Schieber zeigt den sichtbaren
Ausschnitt; ihn ziehen verschiebt die Ansicht, ein Klick daneben springt dorthin. Ist der Plan höher als der
Streifen, läuft die Karte beim Blättern mit (wie in VS Code). Über dem Streifen wird der Schieber deutlicher.
Zuschaltbar über Einstellungen → Zusatzknöpfe → Minikarte.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app import styles

MINIMAP_WIDTH = 120      # Breite des Streifens (Pixel)
CONTENT_PADDING = 8      # Innenabstand links und rechts (Pixel)
MAX_SCALE = 0.2          # kleine Pläne werden nicht größer gezeichnet (wie die feste Schriftgröße in VS Code)
SCENE_MARGIN = 40        # Rand um den Plan (Szeneneinheiten)
MAX_PIXMAP_HEIGHT = 6000


class Minimap(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self._view = view
        self._scene = None
        self._pixmap: QPixmap | None = None
        self._source = QRectF()
        self._drag_offset: QPointF | None = None
        self._hover = False
        self.setFixedWidth(MINIMAP_WIDTH)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.invalidate)
        view.installEventFilter(self)
        view.horizontalScrollBar().valueChanged.connect(self.update)
        view.verticalScrollBar().valueChanged.connect(self.update)
        view.zoom_changed.connect(lambda _zoom: self.update())
        self.place()

    # ------------------------------------------------------------ Lage
    def place(self) -> None:
        """Rechts neben der Arbeitsfläche, über die ganze Höhe – die Arbeitsfläche rückt dafür zur Seite,
        damit die Karte nichts vom Plan verdeckt (wie in VS Code)."""
        area = self._view.viewport().geometry()
        self.setFixedHeight(max(1, area.height()))
        self.move(area.right() + 1, area.top())
        self.raise_()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._view and event.type() in (QEvent.Type.Resize, QEvent.Type.Show,
                                                      QEvent.Type.LayoutRequest):
            self.place()
            self._pixmap = None
        return False

    # ------------------------------------------------------------ Inhalt
    def _watch_scene(self) -> None:
        scene = self._view.scene()
        if scene is self._scene:
            return
        if self._scene is not None:
            try:
                self._scene.changed.disconnect(self._schedule)
            except (RuntimeError, TypeError):
                pass
        self._scene = scene
        if scene is not None:
            scene.changed.connect(self._schedule)
        self._pixmap = None

    def _schedule(self, *_args) -> None:
        if self.isVisible():
            self._timer.start()

    def invalidate(self) -> None:
        self._pixmap = None
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._view.setViewportMargins(0, 0, self.width(), 0)
        self.place()
        self.invalidate()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if not self._view.isHidden():
            self._view.setViewportMargins(0, 0, 0, 0)

    def scale(self) -> float:
        if self._source.isEmpty():
            return 1.0
        return min(MAX_SCALE, (self.width() - 2 * CONTENT_PADDING) / self._source.width())

    def content_height(self) -> float:
        return self._source.height() * self.scale()

    def scroll_offset(self) -> float:
        """Wie weit die Karte nach oben verschoben ist, wenn der Plan höher als der Streifen ist (wie VS Code)."""
        overflow = self.content_height() - self.height()
        if overflow <= 0 or self._source.isEmpty():
            return 0.0
        visible = self._view.visible_scene_rect()
        travel = self._source.height() - visible.height()
        if travel <= 0:
            return 0.0
        fraction = (visible.top() - self._source.top()) / travel
        return max(0.0, min(1.0, fraction)) * overflow

    def _origin(self) -> QPointF:
        """Lage der linken oberen Ecke des Plans im Streifen (waagerecht mittig)."""
        width = self._source.width() * self.scale()
        return QPointF((self.width() - width) / 2, -self.scroll_offset())

    def _render(self) -> None:
        scene = self._scene
        bounds = scene.diagram_bounds() if scene is not None else QRectF()
        if bounds.isNull() or bounds.isEmpty():
            self._source = QRectF()
            self._pixmap = QPixmap()
            return
        self._source = bounds.adjusted(-SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN, SCENE_MARGIN)
        scale = self.scale()
        ratio = self.devicePixelRatioF()
        width = max(1, int(self._source.width() * scale * ratio))
        height = max(1, min(MAX_PIXMAP_HEIGHT, int(self._source.height() * scale * ratio)))
        pixmap = QPixmap(width, height)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        scene.render(painter, QRectF(0, 0, width / ratio, height / ratio), self._source,
                     Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        self._pixmap = pixmap

    def slider_rect(self) -> QRectF:
        """Der sichtbare Ausschnitt als Schieber im Streifen."""
        if self._source.isEmpty():
            return QRectF()
        scale, origin = self.scale(), self._origin()
        visible = self._view.visible_scene_rect()
        rect = QRectF(origin.x() + (visible.left() - self._source.left()) * scale,
                      origin.y() + (visible.top() - self._source.top()) * scale,
                      visible.width() * scale, visible.height() * scale)
        # wie in VS Code über die ganze Breite des Streifens, solange der Ausschnitt breiter als der Plan ist
        if visible.width() >= self._source.width():
            rect.setLeft(0)
            rect.setRight(self.width())
        return rect.intersected(QRectF(self.rect()))

    def paintEvent(self, _event) -> None:
        self._watch_scene()
        if self._pixmap is None:
            self._render()
        theme = styles.current_theme()
        painter = QPainter(self)
        background = QColor(theme.canvas_bg)
        painter.fillRect(self.rect(), background.darker(108) if theme.name == "dark" else background.darker(103))
        painter.setPen(QPen(QColor(theme.border), 1))
        painter.drawLine(0, 0, 0, self.height())
        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(self._origin(), self._pixmap)
            slider = self.slider_rect()
            if not slider.isEmpty():
                shade = QColor(theme.text)
                shade.setAlpha(60 if (self._hover or self._drag_offset is not None) else 30)
                painter.fillRect(slider, shade)
        painter.end()

    # ------------------------------------------------------------ Maus
    def scene_point(self, pos: QPointF) -> QPointF | None:
        if self._source.isEmpty():
            return None
        scale, origin = self.scale(), self._origin()
        return QPointF(self._source.left() + (pos.x() - origin.x()) / scale,
                       self._source.top() + (pos.y() - origin.y()) / scale)

    def _center_on(self, pos: QPointF) -> None:
        point = self.scene_point(pos)
        if point is not None:
            self._view.centerOn(point)
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._source.isEmpty():
            slider = self.slider_rect()
            if not slider.contains(event.position()):
                self._center_on(event.position())   # Klick daneben: dorthin springen …
                slider = self.slider_rect()
            # … und von dort aus weiterziehen, ohne dass der Schieber unter der Maus wegspringt
            self._drag_offset = event.position() - slider.center()
            self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._center_on(event.position() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        self.update()
        event.accept()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        # Mausrad über der Karte blättert die Arbeitsfläche (wie in VS Code), zoomt aber nicht
        bar = self._view.verticalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())
        event.accept()
