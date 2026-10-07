"""Definition der PAP-Bausteintypen.

Jeder Typ besitzt eine feste semantische Bedeutung (entsprechend der klassischen
Programmablaufplan-Notation), eine Standardgröße, erlaubte Anschlusspunkte und
Regeln für ein- und ausgehende Verbindungen. Die grafische Form wird in
``app.items.shapes`` definiert.

Die Texte in ``ElementSpec`` sind der deutsche Quelltext (Schlüssel der Übersetzung). Angezeigt wird immer
über ``display_name_for``, ``description_for`` und ``default_text_for``; ob ein Text noch der Standardtext
ist, sagt ``is_default_text`` – in jeder Sprache, denn der Standardtext steht in der Projektdatei.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app import i18n
from app.i18n import N_, tr


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
        ElementType.START, N_("Start", ctx="Baustein"), N_("Beginn eines Ablaufs"), N_("Start", ctx="Standardtext"),
        120, 40, 200, (PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
        can_be_target=False,
    ),
    ElementType.END: ElementSpec(
        ElementType.END, N_("Ende", ctx="Baustein"), N_("Ende eines Ablaufs"), N_("Ende", ctx="Standardtext"),
        120, 40, 200, (PORT_TOP, PORT_LEFT, PORT_RIGHT),
        can_be_source=False, max_outgoing=0,
    ),
    ElementType.INPUT: ElementSpec(
        ElementType.INPUT, N_("Eingabe", ctx="Baustein"), N_("Eingabe von Daten oder Werten"),
        N_("Eingabe", ctx="Standardtext"),
        160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.OUTPUT: ElementSpec(
        ElementType.OUTPUT, N_("Ausgabe", ctx="Baustein"), N_("Ausgabe von Informationen, Text oder Werten"),
        N_("Ausgabe", ctx="Standardtext"),
        160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.PROCESS: ElementSpec(
        ElementType.PROCESS, N_("Vorgang", ctx="Baustein"), N_("Verarbeitung, Berechnung oder Anweisung"),
        N_("Vorgang", ctx="Standardtext"),
        160, 60, 260, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.SUBPROGRAM: ElementSpec(
        ElementType.SUBPROGRAM, N_("Unterprogramm", ctx="Baustein"),
        N_("Aufruf eines Unterprogramms bzw. einer Funktion"),
        N_("Unterprogramm", ctx="Standardtext"), 160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.DECISION: ElementSpec(
        ElementType.DECISION, N_("Verzweigung", ctx="Baustein"),
        N_("Entscheidung mit mehreren Ausgängen (z. B. ja/nein)"),
        N_("Bedingung?", ctx="Standardtext"), 160, 120, 180, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
        max_outgoing=None,
    ),
    ElementType.LOOP: ElementSpec(
        ElementType.LOOP, N_("Schleife", ctx="Baustein"),
        N_("Schleifenbegrenzung (Schleifenbeginn und Schleifenende)"),
        N_("Schleife", ctx="Standardtext"), 160, 60, 240, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
    ElementType.COMMENT: ElementSpec(
        ElementType.COMMENT, N_("Kommentar", ctx="Baustein"), N_("Beschreibender Text, nicht Teil des Ablaufs"),
        N_("Kommentar", ctx="Standardtext"), 160, 60, 260, (PORT_LEFT, PORT_RIGHT),
        max_outgoing=None, is_flow=False,
    ),
    ElementType.JUNCTION: ElementSpec(
        ElementType.JUNCTION, N_("Verbindungspunkt", ctx="Baustein"),
        N_("Knoten auf einem Pfeil, an dem weitere Verbindungen ansetzen"),
        "", JUNCTION_SIZE, JUNCTION_SIZE, 0, (PORT_TOP, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT),
    ),
}

# Standardtexte der beiden Schleifenteile (deutscher Quelltext)
_LOOP_BEGIN_TEXT = N_("Schleifenbeginn", ctx="Standardtext")
_LOOP_END_TEXT = N_("Schleifenende", ctx="Standardtext")

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


def display_name_for(element_type: ElementType | str) -> str:
    """Name des Bausteintyps in der eingestellten Sprache („Vorgang“, „Process“, …)."""
    return tr(spec_for(element_type).display_name, ctx="Baustein")


def description_for(element_type: ElementType | str) -> str:
    """Kurze Beschreibung des Bausteintyps in der eingestellten Sprache."""
    return tr(spec_for(element_type).description)


def _default_text_source(element_type: ElementType, properties: dict | None) -> str:
    """Der deutsche Standardtext (Schlüssel der Übersetzung)."""
    if ElementType(element_type) is ElementType.LOOP:
        part = (properties or {}).get(LOOP_PART_KEY, LOOP_BEGIN)
        return _LOOP_END_TEXT if part == LOOP_END else _LOOP_BEGIN_TEXT
    return spec_for(element_type).default_text


def default_text_for(element_type: ElementType, properties: dict | None = None) -> str:
    """Text, den ein neuer Baustein anfangs trägt – in der eingestellten Sprache."""
    source = _default_text_source(ElementType(element_type), properties)
    return tr(source, ctx="Standardtext") if source else ""


def is_default_text(text: str, element_type: ElementType, properties: dict | None = None) -> bool:
    """Ist ``text`` der Standardtext des Bausteins – in **irgendeiner** Sprache?

    Der Standardtext steht in der Projektdatei; ein Plan, der in einer anderen Sprache angelegt wurde, soll
    trotzdem als „noch mit Standardtext“ erkannt werden.
    """
    source = _default_text_source(ElementType(element_type), properties)
    return bool(source) and text in i18n.all_translations(source, ctx="Standardtext")


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
