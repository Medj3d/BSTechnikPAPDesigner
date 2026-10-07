"""Vorschau eines Bausteins während Drag & Drop aus der Werkzeugpalette.

Zeigt exakt die (am Raster eingerastete) Position, an der der neue Baustein
beim Loslassen entstehen wird.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from app import styles
from app.items.base_item import LAYER_OVERLAY
from app.items.shapes import geometry_for
from app.model.element_types import (LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, ElementType, spec_for)


class GhostItem(QGraphicsItem):
    def __init__(self, element_type: ElementType):
        super().__init__()
        self.element_type = ElementType(element_type)
        spec = spec_for(self.element_type)
        self._w = float(spec.default_width)
        self._h = float(spec.default_height)
        self._geometry = geometry_for(self.element_type)
        # Eine Schleife wird als Paar (Beginn + Ende) eingefügt
        self._loop_pair = self.element_type is ElementType.LOOP
        self._pair_offset = self._h + 60.0 if self._loop_pair else 0.0
        self.setZValue(LAYER_OVERLAY)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setOpacity(0.75)

    def boundingRect(self) -> QRectF:
        extra = self._pair_offset
        return QRectF(-self._w / 2 - 4, -self._h / 2 - 4, self._w + 8, self._h + 8 + extra)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        theme = styles.current_theme()
        colors = theme.element_colors(self.element_type)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(colors.border), 1.5)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([4.0, 3.0])
        fill = QColor(colors.fill)
        fill.setAlphaF(0.6)
        painter.setPen(pen)
        painter.setBrush(fill)
        if self._loop_pair:
            painter.drawPath(self._geometry.outline(self._w, self._h, {LOOP_PART_KEY: LOOP_BEGIN}))
            painter.save()
            painter.translate(0, self._pair_offset)
            painter.drawPath(self._geometry.outline(self._w, self._h, {LOOP_PART_KEY: LOOP_END}))
            painter.restore()
            painter.drawLine(0, int(self._h / 2), 0, int(self._pair_offset - self._h / 2))
        else:
            painter.drawPath(self._geometry.outline(self._w, self._h))
            decoration = self._geometry.decoration(self._w, self._h)
            if decoration is not None:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(decoration)
