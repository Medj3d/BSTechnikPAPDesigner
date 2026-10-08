"""Prüfungen des gesamten Plans für die Hinweisliste.

Jede Prüfung liefert ``Issue``-Objekte mit Schweregrad, Meldung und den
betroffenen Elementen bzw. Verbindungen (für die Navigation im Plan).
Nichts davon verhindert etwas – es sind reine Hinweise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.ast import DoWhileLoop, If, LimitLoop, Loop, Unstructured, WhileLoop
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.i18n import tr
from app.model.element_types import ElementType, display_name_for, is_default_text

WARNING = "warning"
INFO = "info"

TEXT_REQUIRED = {ElementType.INPUT, ElementType.OUTPUT, ElementType.PROCESS, ElementType.SUBPROGRAM,
                 ElementType.DECISION}


@dataclass
class Issue:
    severity: str
    message: str
    element_ids: list = field(default_factory=list)
    connection_ids: list = field(default_factory=list)


def _name(node) -> str:
    text = " ".join((node.text or "").split())
    label = display_name_for(node.type)
    if not text:
        return label
    if len(text) > 40:
        text = text[:37] + "…"
    return tr("{block} „{text}“", block=label, text=text)


def run_checks(scene) -> list[Issue]:
    """Prüft das Diagramm einer Szene und liefert sortierte Hinweise."""
    issues: list[Issue] = []
    elements = scene.element_data()
    connections = scene.connection_data()
    graph = FlowGraph.from_diagram(elements, connections)
    flow_nodes = graph.nodes
    positions = {e.id: (e.y, e.x) for e in elements}

    # rot markierte Verbindungen (in Erstellungsreihenfolge – dieselbe wie nach dem Öffnen der Datei)
    for conn in scene.ordered_connections():
        if conn.warning:
            issues.append(Issue(WARNING, tr("Verbindung: {warning}", warning=conn.warning), [],
                                    [conn.connection_id]))

    if flow_nodes:
        starts = [n for n in flow_nodes.values() if n.type is ElementType.START]
        ends = [n for n in flow_nodes.values() if n.type is ElementType.END]
        if not starts:
            issues.append(Issue(WARNING, tr("Der Plan hat kein Start-Element.")))
        if not ends:
            issues.append(Issue(WARNING, tr("Der Plan hat kein Ende-Element.")))

        reachable: set[str] = set()
        for start in starts:
            reachable |= graph.reachable_from(start.id)
        for node in flow_nodes.values():
            outs = graph.outgoing(node.id)
            if node.type is ElementType.START and not outs:
                issues.append(Issue(WARNING, tr("{name} ist mit keinem Baustein verbunden.", name=_name(node)),
                                    [node.id]))
                continue
            if starts and node.id not in reachable and node.type is not ElementType.START:
                issues.append(Issue(WARNING, tr("{name} wird vom Start aus nie erreicht.", name=_name(node)),
                                    [node.id]))
            if node.type not in (ElementType.END,) and not outs and node.type is not ElementType.START:
                issues.append(Issue(WARNING, tr("{name} hat keinen Nachfolger (Sackgasse).", name=_name(node)),
                                    [node.id]))
            if node.type is ElementType.DECISION:
                if len(outs) < 2:
                    issues.append(Issue(WARNING, tr("{name} hat weniger als zwei Ausgänge.", name=_name(node)),
                                        [node.id]))
                labels = [e.label.strip().lower() for e in outs]
                if len(outs) >= 2 and any(not label for label in labels):
                    issues.append(Issue(INFO, tr("{name}: Nicht alle Ausgänge sind beschriftet.", name=_name(node)),
                                        [node.id], [e.id for e in outs if not e.label.strip()]))
                duplicates = {label for label in labels if label and labels.count(label) > 1}
                if duplicates:
                    issues.append(Issue(WARNING, tr("{name}: Beschriftung „{label}“ kommt mehrfach vor.",
                                                    name=_name(node), label=sorted(duplicates)[0]), [node.id],
                                        [e.id for e in outs if e.label.strip().lower() in duplicates]))

        _structure_issues(graph, issues)

    # Texte
    for e in elements:
        etype = ElementType(e.type)
        if etype not in TEXT_REQUIRED and etype is not ElementType.LOOP:
            continue
        text = (e.text or "").strip()
        node_name = _name(flow_nodes[e.id]) if e.id in flow_nodes else display_name_for(etype)
        if not text:
            issues.append(Issue(INFO, tr("{name} ohne Text.", name=display_name_for(etype)), [e.id]))
        elif is_default_text(text, etype, e.properties):
            # der Standardtext steht in der Projektdatei – auch der einer anderen Sprache zählt
            issues.append(Issue(INFO, tr("{name} hat noch den Standardtext.", name=node_name), [e.id]))

    def sort_key(issue: Issue):
        first = issue.element_ids[0] if issue.element_ids else None
        pos = positions.get(first, (float("inf"), float("inf")))
        return (0 if issue.severity == WARNING else 1, pos)
    issues.sort(key=sort_key)
    return _dedupe(issues)


def _structure_issues(graph: FlowGraph, issues: list[Issue]) -> None:
    """Schleifenpaare und nicht strukturierbare Teile über den Strukturbaum prüfen."""
    try:
        programs = structure_diagram(graph)
    except Exception:  # Analyse darf die Hinweisliste nie verhindern
        return
    paired_begins: set[str] = set()
    paired_ends: set[str] = set()

    def walk(block) -> None:
        for stmt in block:
            if isinstance(stmt, LimitLoop):
                paired_begins.add(stmt.begin_id)
                if stmt.end_id:
                    paired_ends.add(stmt.end_id)
                walk(stmt.body)
            elif isinstance(stmt, If):
                walk(stmt.then_block)
                walk(stmt.else_block)
            elif isinstance(stmt, (WhileLoop, DoWhileLoop, Loop)):
                walk(stmt.body)
            elif isinstance(stmt, Unstructured):
                issues.append(Issue(INFO, tr("Nicht strukturierter Ablauf: {note}", note=stmt.note),
                                    list(stmt.element_ids)))

    for program in programs:
        walk(program.body)
        for warning in program.warnings:
            # alles, was dem Benutzer sagt, dass Code/Struktogramm vom Plan abweichen können
            issues.append(Issue(INFO, warning))
    for node in graph.nodes.values():
        if node.is_loop_begin and node.id not in paired_begins and _reached(graph, node.id):
            issues.append(Issue(WARNING, tr("{name} hat kein passendes Schleifenende.", name=_name(node)),
                                [node.id]))
        if node.is_loop_end and node.id not in paired_ends and _reached(graph, node.id):
            issues.append(Issue(WARNING, tr("{name} hat keinen passenden Schleifenbeginn.", name=_name(node)),
                                [node.id]))


def _reached(graph: FlowGraph, node_id: str) -> bool:
    return any(node_id in graph.reachable_from(start.id) for start in graph.starts())


def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen = set()
    result = []
    for issue in issues:
        key = (issue.severity, issue.message, tuple(issue.element_ids), tuple(issue.connection_ids))
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result
