"""Übergangsstelle (Konnektor nach DIN 66001): Kreis mit Marke.

Zwei Übergangsstellen mit derselben Marke gehören zusammen: In die eine führt ein Pfeil hinein, aus der anderen
führt ein Pfeil heraus. Der Ablauf springt von der einen zur anderen (siehe ``FlowGraph.from_diagram``). So muss
ein langer Rückpfeil nicht quer über den Plan laufen.
"""

from __future__ import annotations

import math

from PySide6.QtGui import QPainterPathStroker

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class ConnectorItem(FlowItem):
    ELEMENT_TYPE = ElementType.CONNECTOR

    def _rebuild(self, notify: bool = True) -> None:
        super()._rebuild(notify=False)
        # immer ein Kreis: Breite und Höhe gleich (das Raster der Bausteingrößen würde ein Oval daraus machen)
        side = float(math.ceil(max(self._w, self._h)))
        if (self._w, self._h) != (side, side):
            self.prepareGeometryChange()
            self._w = self._h = side
            if self._preview_text is None:
                self.data.width = self.data.height = side
            self._outline = self.geometry.outline(side, side, self.data.properties)
            margin = self.BOUNDS_MARGIN
            self._bounds = self._outline.boundingRect().adjusted(-margin, -margin, margin, margin)
            stroker = QPainterPathStroker()
            stroker.setWidth(6.0)
            self._shape = self._outline.united(stroker.createStroke(self._outline))
        self.update()
        if notify:
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_item_geometry_changed"):
                scene.on_item_geometry_changed(self)
