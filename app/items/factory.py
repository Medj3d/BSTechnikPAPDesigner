"""Erzeugt Bausteine aus Elementdaten."""

from __future__ import annotations

import math

from app.items.base_item import FlowItem
from app.items.comment_item import CommentItem
from app.items.decision_item import DecisionItem
from app.items.end_item import EndItem
from app.items.input_item import InputItem
from app.items.junction_item import JunctionItem
from app.items.loop_item import LoopItem
from app.items.output_item import OutputItem
from app.items.process_item import ProcessItem
from app.items.start_item import StartItem
from app.items.subprogram_item import SubprogramItem
from app.model.diagram import ElementData, new_id
from app.model.element_types import (ElementType, default_properties_for, default_text_for,
                                     spec_for)

ITEM_CLASSES: dict[ElementType, type[FlowItem]] = {
    ElementType.START: StartItem,
    ElementType.END: EndItem,
    ElementType.INPUT: InputItem,
    ElementType.OUTPUT: OutputItem,
    ElementType.PROCESS: ProcessItem,
    ElementType.SUBPROGRAM: SubprogramItem,
    ElementType.DECISION: DecisionItem,
    ElementType.LOOP: LoopItem,
    ElementType.COMMENT: CommentItem,
    ElementType.JUNCTION: JunctionItem,
}


def create_item(data: ElementData) -> FlowItem:
    return ITEM_CLASSES[ElementType(data.type)](data)


def new_element_data(element_type: ElementType, x: float, y: float, text: str | None = None,
                     properties: dict | None = None) -> ElementData:
    """Erzeugt die Daten eines neuen Bausteins mit Standardwerten."""
    element_type = ElementType(element_type)
    spec = spec_for(element_type)
    props = default_properties_for(element_type)
    if properties:
        props.update(properties)
    return ElementData(
        id=new_id(),
        type=element_type,
        x=float(x),
        y=float(y),
        width=float(spec.default_width),
        height=float(spec.default_height),
        text=default_text_for(element_type, props) if text is None else text,
        z=0.0,
        properties=props,
    )


def snapped(value: float, grid: int) -> float:
    return math.floor(value / grid + 0.5) * grid if grid > 0 else value
