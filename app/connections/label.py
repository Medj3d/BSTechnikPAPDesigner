"""Beschriftung einer Verbindung (z. B. „ja“/„nein“ an Verzweigungen).

Die Beschriftung ist ein Kindobjekt der Verbindung und gehört damit logisch
zu ihr. Sie wird automatisch am Anfang der Verbindung neben der Linie
platziert und wandert mit der Verbindung mit.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from app import config, styles

_LABEL_FONT = None


def label_font() -> QFont:
    global _LABEL_FONT
    if _LABEL_FONT is None:
        _LABEL_FONT = styles.item_font(config.LABEL_FONT_PIXEL_SIZE)
    return _LABEL_FONT


class ConnectionLabel(QGraphicsItem):
    PAD_X = 4.0
    PAD_Y = 1.5
    OFFSET = 6.0

    def __init__(self, connection):
        super().__init__(connection)
        self.connection = connection
        self._text = ""
        self._editing = False
        self._rect = QRectF()
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        self._text = text or ""
        self._relayout()

    def set_editing(self, editing: bool) -> None:
        self._editing = editing
        self.update()

    def _relayout(self) -> None:
        fm = QFontMetricsF(label_font())
        lines = self._text.split("\n") if self._text else [""]
        width = max(fm.horizontalAdvance(line) for line in lines)
        height = fm.height() * len(lines)
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, width + 2 * self.PAD_X, height + 2 * self.PAD_Y)
        self.setVisible(bool(self._text) or self._editing)
        self.update_position()

    def text_rect_size(self) -> tuple[float, float]:
        return self._rect.width(), self._rect.height()

    def update_position(self) -> None:
        """Platziert die Beschriftung neben dem ersten Liniensegment."""
        points = self.connection.points()
        if len(points) < 2:
            return
        (x1, y1), (x2, y2) = points[0], points[1]
        w, h = self._rect.width(), self._rect.height()
        o = self.OFFSET
        if abs(x1 - x2) < 1e-6:  # erstes Segment vertikal
            if y2 >= y1:   # nach unten
                pos = QPointF(x1 + o, y1 + o)
            else:          # nach oben
                pos = QPointF(x1 + o, y1 - o - h)
        else:  # erstes Segment horizontal
            if x2 >= x1:   # nach rechts
                pos = QPointF(x1 + o, y1 - o - h)
            else:          # nach links
                pos = QPointF(x1 - o - w, y1 - o - h)
        self.setPos(pos)

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-1, -1, 1, 1)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._text or self._editing:
            return
        scene = self.scene()
        theme = getattr(scene, "theme", styles.current_theme()) if scene is not None else styles.current_theme()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg = QColor(theme.label_bg)
        bg.setAlphaF(0.92)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(self._rect, 3.0, 3.0)
        painter.setFont(label_font())
        color = QColor(theme.label_text)
        if self.connection.isSelected() and not getattr(scene, "exporting", False):
            color = QColor(theme.selection)
        painter.setPen(QPen(color))
        painter.drawText(self._rect.adjusted(self.PAD_X, self.PAD_Y, -self.PAD_X, -self.PAD_Y),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self._text)

    # Klick auf die Beschriftung wählt die Verbindung aus
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            if scene is not None and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                scene.clearSelection()
            self.connection.setSelected(not self.connection.isSelected()
                                        if event.modifiers() & Qt.KeyboardModifier.ControlModifier
                                        else True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        scene = self.scene()
        if scene is not None and hasattr(scene, "begin_label_edit"):
            scene.begin_label_edit(self.connection)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
