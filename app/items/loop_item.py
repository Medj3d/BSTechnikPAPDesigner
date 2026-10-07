"""Schleife: Schleifenbegrenzung nach DIN 66001.

Eine Schleife besteht aus einem Schleifenbeginn (obere Ecken abgeschrägt) und
einem Schleifenende (untere Ecken abgeschrägt). Beim Einfügen einer Schleife
werden beide Teile gemeinsam erzeugt und verbunden; der Schleifenrumpf wird
zwischen die beiden Teile gesetzt.
"""

from app.items.base_item import FlowItem
from app.model.element_types import LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, ElementType


class LoopItem(FlowItem):
    ELEMENT_TYPE = ElementType.LOOP

    @property
    def loop_part(self) -> str:
        return LOOP_END if self.data.properties.get(LOOP_PART_KEY) == LOOP_END else LOOP_BEGIN

    @property
    def is_loop_end(self) -> bool:
        return self.loop_part == LOOP_END
