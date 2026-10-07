"""Kommentar: frei platzierbarer, beschreibender Text.

Kommentare gehören nicht zum Ablaufgraphen. Sie liegen in einer eigenen
Zeichenebene unterhalb von Verbindungen und Bausteinen, damit sie andere
Elemente nicht verdecken, und werden bei der Linienführung nicht als
Hindernis betrachtet. Optional kann ein Kommentar über eine gestrichelte
Linie einem Baustein zugeordnet werden.
"""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class CommentItem(FlowItem):
    ELEMENT_TYPE = ElementType.COMMENT
