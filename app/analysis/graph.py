"""Der Ablaufgraph eines Diagramms – unabhängig von Qt und der Darstellung.

Knoten sind die Ablaufbausteine (ohne Kommentare), Kanten die gerichteten
Ablaufverbindungen (ohne Kommentarlinien). Verbindungspunkte (Junctions)
bleiben zunächst eigene Knoten; ``collapse_junctions`` überbrückt reine
Durchgangsknoten, damit Analysen (Strukturierung, Code, Struktogramm) nur
die fachlichen Bausteine sehen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.model.diagram import ConnectionData, ElementData
from app.model.element_types import LOOP_END, LOOP_PART_KEY, ElementType

YES_LABELS = {"ja", "j", "yes", "y", "wahr", "true", "1", "w", "t", "+", "richtig", "stimmt", "ok", "erfüllt"}
NO_LABELS = {"nein", "n", "no", "falsch", "false", "0", "f", "-", "stimmt nicht", "nicht erfüllt"}
ELSE_LABELS = {"sonst", "andernfalls", "ansonsten", "else", "default", "sonstiges"}
PORT_ORDER = {"bottom": 0, "right": 1, "left": 2, "top": 3}


@dataclass(frozen=True)
class Node:
    id: str
    type: ElementType
    text: str
    properties: dict = field(default_factory=dict, hash=False, compare=False)
    x: float = 0.0
    y: float = 0.0

    @property
    def is_loop_end(self) -> bool:
        return self.type is ElementType.LOOP and self.properties.get(LOOP_PART_KEY) == LOOP_END

    @property
    def is_loop_begin(self) -> bool:
        return self.type is ElementType.LOOP and not self.is_loop_end


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    label: str = ""
    source_port: str = "bottom"
    target_port: str = "top"

    @property
    def is_yes(self) -> bool:
        return self.label.strip().lower() in YES_LABELS

    @property
    def is_no(self) -> bool:
        label = " ".join(self.label.split()).lower()
        return label in NO_LABELS or label.startswith(("nicht ", "kein ", "keine "))

    @property
    def is_else(self) -> bool:
        return self.label.strip().lower() in ELSE_LABELS


def yes_no_edges(outs: list) -> tuple:
    """Ordnet die zwei Ausgänge einer Verzweigung zu: (Ja-Ausgang, Nein-Ausgang).

    Maßgeblich ist die Beschriftung; ist nur ein Ausgang erkennbar beschriftet,
    ist der andere das Gegenteil. Ohne erkennbare Beschriftung gilt der erste
    Ausgang als „ja“. Bei nur einem Ausgang fehlt der andere (``None``).
    """
    if not outs:
        return None, None
    if len(outs) == 1:
        return (None, outs[0]) if outs[0].is_no else (outs[0], None)
    first, second = outs[0], outs[1]
    if second.is_yes and not first.is_yes:
        return second, first
    if first.is_no and not second.is_no:
        return second, first
    return first, second


def has_yes_no_labels(outs: list) -> bool:
    """Trägt mindestens ein Ausgang eine Ja/Nein-Beschriftung („1“/„0“ nur als Paar)?"""
    labels = [" ".join(edge.label.split()).lower() for edge in outs]
    digits = [label for label in labels if label in ("0", "1")]
    words = [edge for edge, label in zip(outs, labels) if label not in ("0", "1") and (edge.is_yes or edge.is_no)]
    return bool(words) or sorted(digits) == ["0", "1"]


class FlowGraph:
    def __init__(self, nodes: dict[str, Node], edges: list[Edge],
                 annotations: dict[str, list[str]] | None = None):
        self.nodes = dict(nodes)
        self.edges = list(edges)
        # Kommentartexte, die per Kommentarlinie einem Baustein zugeordnet sind
        self.annotations = {k: list(v) for k, v in (annotations or {}).items()}
        self._out: dict[str, list[Edge]] = {nid: [] for nid in self.nodes}
        self._in: dict[str, list[Edge]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            self._out.setdefault(edge.source, []).append(edge)
            self._in.setdefault(edge.target, []).append(edge)
        for nid, out in self._out.items():
            out.sort(key=self._edge_sort_key)

    # ------------------------------------------------------------ Aufbau
    @classmethod
    def from_diagram(cls, elements: list[ElementData], connections: list[ConnectionData]) -> "FlowGraph":
        nodes: dict[str, Node] = {}
        comments: dict[str, str] = {}
        for e in elements:
            etype = ElementType(e.type)
            if etype is ElementType.COMMENT:
                comments[e.id] = e.text
                continue
            nodes[e.id] = Node(e.id, etype, e.text or "", dict(e.properties), float(e.x), float(e.y))
        edges: list[Edge] = []
        annotations: dict[str, list[str]] = {}
        for c in connections:
            if c.source_id in comments and c.target_id in nodes:
                annotations.setdefault(c.target_id, []).append(comments[c.source_id])
                continue
            if c.target_id in comments and c.source_id in nodes:
                annotations.setdefault(c.source_id, []).append(comments[c.target_id])
                continue
            if c.source_id in nodes and c.target_id in nodes:
                edges.append(Edge(c.id, c.source_id, c.target_id, c.label or "", c.source_port, c.target_port))
        return cls(nodes, edges, annotations)

    @classmethod
    def from_scene(cls, scene) -> "FlowGraph":
        return cls.from_diagram(scene.element_data(), scene.connection_data())

    def collapse_junctions(self) -> "FlowGraph":
        """Überbrückt Verbindungspunkte mit genau einem Ausgang.

        A → ● → B und C → ● werden zu A → B und C → B. Beschriftungen der
        eingehenden Kanten bleiben erhalten. Verbindungspunkte mit mehreren
        Ausgängen (Abzweigung ohne Bedingung) bleiben als Knoten bestehen.
        """
        nodes = dict(self.nodes)
        edges = list(self.edges)
        changed = True
        while changed:
            changed = False
            for nid, node in list(nodes.items()):
                if node.type is not ElementType.JUNCTION:
                    continue
                outs = [e for e in edges if e.source == nid]
                if len(outs) != 1:
                    continue
                out = outs[0]
                if out.target == nid:
                    continue
                ins = [e for e in edges if e.target == nid]
                edges = [e for e in edges if e.source != nid and e.target != nid]
                for e in ins:
                    edges.append(Edge(e.id, e.source, out.target, e.label or out.label, e.source_port,
                                      out.target_port))
                del nodes[nid]
                changed = True
                break
        return FlowGraph(nodes, edges, self.annotations)

    # ------------------------------------------------------------ Abfragen
    def _edge_sort_key(self, edge: Edge) -> tuple:
        # Verzweigungen: „ja“ vor „nein“ vor sonstigen, „sonst“ zuletzt, dann nach Anschluss
        if edge.is_yes:
            rank = 0
        elif edge.is_no:
            rank = 1
        elif edge.is_else:
            rank = 3
        else:
            rank = 2
        return rank, PORT_ORDER.get(edge.source_port, 9), edge.id

    def outgoing(self, node_id: str) -> list[Edge]:
        return list(self._out.get(node_id, []))

    def incoming(self, node_id: str) -> list[Edge]:
        return list(self._in.get(node_id, []))

    def successors(self, node_id: str) -> list[str]:
        return [e.target for e in self.outgoing(node_id)]

    def starts(self) -> list[Node]:
        """Start-Elemente: zuerst das Hauptprogramm, dann Unterprogramme.

        Ein Ablauf, dessen Start-Text einem Unterprogramm-Aufruf entspricht
        (z. B. Start „Fehlermeldung“ und Unterprogramm „Fehlermeldung“), ist
        ein Unterprogramm und kommt nach dem Hauptprogramm; ansonsten wird von
        oben nach unten und links nach rechts sortiert.
        """
        from app.analysis.text import call_parts, slug

        called = set()
        for node in self.nodes.values():
            if node.type is ElementType.SUBPROGRAM and node.text.strip():
                call = call_parts(node.text)  # „berechne(x, y)“ ruft den Ablauf „berechne“
                called.add(slug(call[0] if call else node.text))
        found = [n for n in self.nodes.values() if n.type is ElementType.START]
        return sorted(found, key=lambda n: (slug(n.text) in called, n.y, n.x, n.id))

    def reachable_from(self, node_id: str) -> set[str]:
        seen = {node_id}
        stack = [node_id]
        while stack:
            current = stack.pop()
            for nxt in self.successors(current):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen
