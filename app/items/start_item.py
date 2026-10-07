"""Start: abgerundetes Element, nur ausgehende Verbindungen."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class StartItem(FlowItem):
    ELEMENT_TYPE = ElementType.START
