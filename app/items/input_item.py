"""Eingabe: Parallelogramm."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class InputItem(FlowItem):
    ELEMENT_TYPE = ElementType.INPUT
