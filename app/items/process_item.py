"""Vorgang: Rechteck."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class ProcessItem(FlowItem):
    ELEMENT_TYPE = ElementType.PROCESS
