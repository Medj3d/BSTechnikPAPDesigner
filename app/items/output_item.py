"""Ausgabe: Parallelogramm."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class OutputItem(FlowItem):
    ELEMENT_TYPE = ElementType.OUTPUT
