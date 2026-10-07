"""Definition der PAP-Bausteintypen.

Jeder Typ besitzt eine feste semantische Bedeutung (entsprechend der klassischen
Programmablaufplan-Notation), eine Standardgröße, erlaubte Anschlusspunkte und
Regeln für ein- und ausgehende Verbindungen. Die grafische Form wird in
``app.items.shapes`` definiert.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ElementType(str, Enum):
    START = "start"
    END = "end"
    INPUT = "input"
    OUTPUT = "output"
    PROCESS = "process"
    SUBPROGRAM = "subprogram"
    DECISION = "decision"
    LOOP = "loop"
    COMMENT = "comment"
    # Verbindungsknoten auf einem bestehenden Pfeil (entsteht beim Anschließen
    # einer Verbindung an einen Pfeil; nicht in der Werkzeugpalette)
    JUNCTION = "junction"


# Anschlusspunkte
PORT_TOP = "top"
PORT_BOTTOM = "bottom"
PORT_LEFT = "left"
PORT_RIGHT = "right"
ALL_PORTS = (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT)

# Richtung (Normalenvektor), in die eine Verbindung einen Anschluss verlässt
PORT_DIRECTIONS = {
    PORT_TOP: (0.0, -1.0),
    PORT_BOTTOM: (0.0, 1.0),
    PORT_LEFT: (-1.0, 0.0),
    PORT_RIGHT: (1.0, 0.0),
}

# Teile einer Schleife (Schleifenbegrenzung nach DIN 66001)
LOOP_PART_KEY = "part"
LOOP_BEGIN = "begin"
LOOP_END = "end"

# Verbindungsknoten: IDs der beiden Teile des ursprünglichen Pfeils
# („Stamm“), der am Knoten aufgetrennt wurde
TRUNK_IN_KEY = "trunk_in"
TRUNK_OUT_KEY = "trunk_out"
JUNCTION_SIZE = 12


@dataclass(frozen=True)
class ElementSpec:
    type: ElementType
    display_name: str
    description: str
    default_text: str
    default_width: int
    default_height: int
    # maximale Breite des Textblocks, danach wird umbrochen
    max_text_width: int
    ports: tuple
    can_be_source: bool = True
    can_be_target: bool = True
    # maximale Anzahl ausgehender Ablaufverbindungen (None = beliebig viele)
    max_outgoing: int | None = 1
    # gehört der Baustein zum Ablaufgraphen? (Kommentare nicht)
    is_flow: bool = True


_SPECS = {
    ElementType.START: ElementSpec(
        ElementType.START, "Start", "Beginn eines Ablaufs", "Start",
        120, 40, 200, (PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
        can_be_target=False,
    ),
    ElementType.END: ElementSpec(
        ElementType.END, "Ende", "Ende eines Ablaufs", "Ende",
        120, 40, 200, (PORT_TOP, PORT_LEFT, PORT_RIGHT),
        can_be_source=False, max_outgoing=0,
    ),
    ElementType.INPUT: ElementSpec(
        ElementType.INPUT, "Eingabe", "Eingabe von Daten oder Werten", "Eingabe",
        160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.OUTPUT: ElementSpec(
        ElementType.OUTPUT, "Ausgabe", "Ausgabe von Informationen, Text oder Werten", "Ausgabe",
        160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.PROCESS: ElementSpec(
        ElementType.PROCESS, "Vorgang", "Verarbeitung, Berechnung oder Anweisung", "Vorgang",
        160, 60, 260, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.SUBPROGRAM: ElementSpec(
        ElementType.SUBPROGRAM, "Unterprogramm", "Aufruf eines Unterprogramms bzw. einer Funktion",
        "Unterprogramm", 160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.DECISION: ElementSpec(
        ElementType.DECISION, "Verzweigung", "Entscheidung mit mehreren Ausgängen (z. B. ja/nein)",
        "Bedingung?", 160, 120, 180, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
        max_outgoing=None,
    ),
    ElementType.LOOP: ElementSpec(
        ElementType.LOOP, "Schleife", "Schleifenbegrenzung (Schleifenbeginn und Schleifenende)",
        "Schleife", 160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.COMMENT: ElementSpec(
        ElementType.COMMENT, "Kommentar", "Beschreibender Text, nicht Teil des Ablaufs",
        "Kommentar", 160, 60, 260, (PORT_LEFT, PORT_RIGHT),
        max_outgoing=None, is_flow=False,
    ),
    ElementType.JUNCTION: ElementSpec(
        ElementType.JUNCTION, "Verbindungspunkt",
        "Knoten auf einem Pfeil, an dem weitere Verbindungen ansetzen",
        "", JUNCTION_SIZE, JUNCTION_SIZE, 0, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
}

# Reihenfolge in Werkzeugpalette und Menüs (entspricht der Referenz)
PALETTE_ORDER = (
    ElementType.INPUT,
    ElementType.OUTPUT,
    ElementType.PROCESS,
    ElementType.SUBPROGRAM,
    ElementType.DECISION,
    ElementType.LOOP,
    ElementType.COMMENT,
)
FLOW_TERMINALS = (ElementType.START, ElementType.END)


def spec_for(element_type: ElementType | str) -> ElementSpec:
    return _SPECS[ElementType(element_type)]


def all_specs() -> list[ElementSpec]:
    return list(_SPECS.values())


def default_text_for(element_type: ElementType, properties: dict | None = None) -> str:
    element_type = ElementType(element_type)
    if element_type is ElementType.LOOP:
        part = (properties or {}).get(LOOP_PART_KEY, LOOP_BEGIN)
        return "Schleifenende" if part == LOOP_END else "Schleifenbeginn"
    return spec_for(element_type).default_text


def default_properties_for(element_type: ElementType) -> dict:
    if ElementType(element_type) is ElementType.LOOP:
        return {LOOP_PART_KEY: LOOP_BEGIN}
    return {}


def is_valid_type(value) -> bool:
    try:
        ElementType(value)
    except ValueError:
        return False
    return True
