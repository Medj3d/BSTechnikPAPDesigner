"""Ende: abgerundetes Element, nur eingehende Verbindungen."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class EndItem(FlowItem):
    ELEMENT_TYPE = ElementType.END
