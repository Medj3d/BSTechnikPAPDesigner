"""Unterprogramm: Rechteck mit doppelten senkrechten Seitenlinien."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class SubprogramItem(FlowItem):
    ELEMENT_TYPE = ElementType.SUBPROGRAM
