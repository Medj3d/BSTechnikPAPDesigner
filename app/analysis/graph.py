"""Der Ablaufgraph eines Diagramms – unabhängig von Qt und der Darstellung.

Knoten sind die Ablaufbausteine (ohne Kommentare), Kanten die gerichteten
Ablaufverbindungen (ohne Kommentarlinien). Verbindungspunkte (Junctions)
bleiben zunächst eigene Knoten; ``collapse_junctions`` überbrückt reine
Durchgangsknoten, damit Analysen (Strukturierung, Code, Struktogramm) nur
die fachlichen Bausteine sehen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import labels
from app.model.diagram import ConnectionData, ElementData
from app.model.element_types import LOOP_END, LOOP_PART_KEY, ElementType

# Die Wörter stehen in ``app.labels`` (alle Sprachen); die Namen bleiben hier für Aufrufer erhalten
YES_LABELS = labels.YES_WORDS
NO_LABELS = labels.NO_WORDS
ELSE_LABELS = labels.ELSE_WORDS
PORT_ORDER = {"bottom": 0, "right": 1, "left": 2, "top": 3}


@dataclass(frozen=True)
class Node:
    id: str
    type: ElementType
    text: str
    properties: dict = field(default_factory=dict, hash=False, compare=False)
    x: float = 0.0
    y: float = 0.0
    # Seite des Projekts: 0 = Hauptprogramm, 1, 2, … = Unterprogramm-Seiten
    page: int = 0

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

    # Die Beschriftung steht in der Projektdatei, in der Sprache des Plans: erkannt werden die Wörter aller Sprachen
    @property
    def is_yes(self) -> bool:
        return labels.is_yes(self.label)

    @property
    def is_no(self) -> bool:
        return labels.is_no(self.label)

    @property
    def is_else(self) -> bool:
        return labels.is_else(self.label)


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


# Zuweisung vor einem Aufruf: „ergebnis := berechne(x)“, „bool ok = pruefe(a)“, „x ← f()“
_ASSIGNMENT = re.compile(r"(?::=|←|<-|(?<![<>!=])=(?!=))")


def routine_label(text: str) -> str:
    """Name eines Ablaufs bzw. des aufgerufenen Ablaufs, wie ihn auch der PapDesigner zuordnet.

    Steht eine Klammer im Text, zählt das Wort direkt davor – ohne Rückgabetyp, Zuweisung oder „return“:
    „bool isDateValid(int day, int month)“, „ok := isDateValid(d, m)“ und „isDateValid(1, 2)“ ergeben
    „isDateValid“. Sonst ist es der ganze Text („Summe berechnen“).
    """
    text = " ".join(str(text or "").split())
    head, bracket, _rest = text.partition("(")
    if bracket and head.strip():
        head = _ASSIGNMENT.split(head)[-1]
        words = head.split()
        if words:
            return words[-1]
    return text


def routine_name(text: str) -> str:
    """Bezeichner zu ``routine_label`` („Summe berechnen“ → „summeberechnen“, „isDateValid(…)“ → „isdatevalid“).

    Ein Unterprogramm-Baustein ruft den Ablauf auf, bei dem dieser Bezeichner gleich ist – im Schreibtischtest,
    in der Code-Erzeugung, in den Hinweisen und beim Öffnen. Leer, wenn der Text keinen Namen enthält.
    """
    from app.analysis.text import slug

    # Wie beim PapDesigner zählen Leerzeichen und Bindestriche nicht: „Summe berechnen“ = „Summe-berechnen“ =
    # „Summeberechnen“
    return slug(routine_label(text), "").replace("_", "")


def _exact_routine_name(text: str) -> str:
    from app.analysis.text import slug

    return slug(routine_label(text), "")


def resolve_routine(text: str, names: list[str], exclude: int | None = None) -> int | None:
    """Welchen der Abläufe ``names`` ein Unterprogramm-Text aufruft (Index) – oder ``None``.

    Zuerst zählt eine genaue Übereinstimmung, erst danach die tolerante ohne Leerzeichen und Bindestriche (so
    bleiben „ab_c“ und „a_bc“ verschieden). Passen mehrere, geht ein anderer als ``exclude`` (das laufende
    Hauptprogramm) vor. Schreibtischtest, Code-Erzeugung, Hinweise und Öffnen nutzen alle diese Zuordnung.
    """
    for key in (_exact_routine_name, routine_name):
        wanted = key(text)
        if not wanted:
            return None
        found = [index for index, name in enumerate(names) if key(name) == wanted]
        if found:
            others = [index for index in found if index != exclude]
            return (others or found)[0]
    return None


# Ein Aufruf und der Name eines Ablaufs folgen derselben Regel
call_target = routine_name
flow_name = routine_name


def subprogram_call_name(node: Node) -> str:
    """Bezeichner des aufgerufenen Ablaufs für einen Unterprogramm-Baustein, sonst leer."""
    if node.type is not ElementType.SUBPROGRAM or not node.text.strip():
        return ""
    return call_target(node.text)


def has_yes_no_labels(outs: list) -> bool:
    """Trägt mindestens ein Ausgang eine Ja/Nein-Beschriftung („1“/„0“ nur als Paar)?"""
    labels = [" ".join(edge.label.split()).lower() for edge in outs]
    digits = [label for label in labels if label in ("0", "1")]
    words = [edge for edge, label in zip(outs, labels) if label not in ("0", "1") and (edge.is_yes or edge.is_no)]
    return bool(words) or sorted(digits) == ["0", "1"]


class FlowGraph:
    def __init__(self, nodes: dict[str, Node], edges: list[Edge],
                 annotations: dict[str, list[str]] | None = None, page_names: dict[int, str] | None = None):
        self.nodes = dict(nodes)
        self.edges = list(edges)
        # Kommentartexte, die per Kommentarlinie einem Baustein zugeordnet sind
        self.annotations = {k: list(v) for k, v in (annotations or {}).items()}
        # Namen der Unterprogramm-Seiten (Seite → Name). Der erste Start einer Seite heißt wie die Seite –
        # so auch im PapDesigner, dessen Unterprogramme oft mit einem Start „Start“ beginnen.
        self.page_names = {int(k): v for k, v in (page_names or {}).items() if v and str(v).strip()}
        self._out: dict[str, list[Edge]] = {nid: [] for nid in self.nodes}
        self._in: dict[str, list[Edge]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            self._out.setdefault(edge.source, []).append(edge)
            self._in.setdefault(edge.target, []).append(edge)
        for nid, out in self._out.items():
            out.sort(key=self._edge_sort_key)

    # ------------------------------------------------------------ Aufbau
    @classmethod
    def from_diagram(cls, elements: list[ElementData], connections: list[ConnectionData],
                     pages: dict[str, int] | None = None) -> "FlowGraph":
        """``pages``: Seite je Element-ID (fehlt eine Angabe, gilt Seite 0 – das Hauptprogramm)."""
        pages = pages or {}
        nodes: dict[str, Node] = {}
        comments: dict[str, str] = {}
        for e in elements:
            etype = ElementType(e.type)
            if etype is ElementType.COMMENT:
                comments[e.id] = e.text
                continue
            nodes[e.id] = Node(e.id, etype, e.text or "", dict(e.properties), float(e.x), float(e.y),
                               pages.get(e.id, 0))
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

    @classmethod
    def from_scenes(cls, scenes, page_names: dict[int, str] | None = None) -> "FlowGraph":
        """Ein Graph über alle Seiten eines Projekts (Hauptprogramm zuerst, dann die Unterprogramme).

        Verbindungen gibt es nur innerhalb einer Seite; ein Unterprogramm-Baustein ruft den Ablauf
        einer anderen Seite über dessen Namen auf (``page_names``: Seite → Name des Unterprogramms).
        """
        elements, connections, pages = [], [], {}
        for index, scene in enumerate(scenes):
            page_elements = scene.element_data()
            elements += page_elements
            connections += scene.connection_data()
            pages.update((e.id, index) for e in page_elements)
        graph = cls.from_diagram(elements, connections, pages)
        graph.page_names = {int(k): v for k, v in (page_names or {}).items() if v and str(v).strip()}
        return graph

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
        return FlowGraph(nodes, edges, self.annotations, self.page_names)

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

        Abläufe der Hauptseite kommen vor denen der Unterprogramm-Seiten (in
        deren Reihenfolge). Auf einer Seite ist ein Ablauf, dessen Start-Text
        einem Unterprogramm-Aufruf entspricht (z. B. Start „Fehlermeldung“ und
        Unterprogramm „Fehlermeldung“), ein Unterprogramm und kommt nach dem
        Hauptprogramm; ansonsten wird von oben nach unten und links nach rechts
        sortiert.
        """
        called = self.called_names()
        found = [n for n in self.nodes.values() if n.type is ElementType.START]
        return sorted(found, key=lambda n: (n.page, routine_name(self.flow_label(n.id)) in called, n.y, n.x, n.id))

    def flow_label(self, start_id: str) -> str:
        """Name des Ablaufs, der an diesem Start-Element beginnt: auf einer Unterprogramm-Seite der Name der
        Seite (für ihren ersten Start), sonst der Text des Start-Elements."""
        node = self.nodes[start_id]
        name = self.page_names.get(node.page)
        if name and node.page > 0:
            first = min((n for n in self.nodes.values() if n.type is ElementType.START and n.page == node.page),
                        key=lambda n: (n.y, n.x, n.id))
            if first.id == start_id:
                return " ".join(name.split())
        return node.text

    def start_for_call(self, text: str, exclude: str | None = None) -> str | None:
        """Start-Element des Ablaufs, den ein Unterprogramm-Text aufruft (``exclude``: das laufende Programm,
        das nur gemeint ist, wenn kein anderer Ablauf so heißt) – oder ``None``."""
        starts = self.starts()
        ids = [start.id for start in starts]
        index = resolve_routine(text, [self.flow_label(start_id) for start_id in ids],
                                ids.index(exclude) if exclude in ids else None)
        return ids[index] if index is not None else None

    def called_names(self) -> set[str]:
        """Namen (als Bezeichner) aller Abläufe, die ein Unterprogramm-Baustein aufruft."""
        return {name for node in self.nodes.values() if (name := subprogram_call_name(node))}

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
