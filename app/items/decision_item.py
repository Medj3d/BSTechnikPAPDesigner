"""Verzweigung: Raute mit mehreren (beschriftbaren) Ausgängen."""

from app.items.base_item import FlowItem
from app.model.element_types import ElementType


class DecisionItem(FlowItem):
    ELEMENT_TYPE = ElementType.DECISION
