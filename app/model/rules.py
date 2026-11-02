"""Regeln für Verbindungen.

Es gibt drei klar getrennte Stufen. Die Verbindung wird in den ersten beiden
Fällen trotzdem erstellt und gespeichert; der Benutzer entscheidet selbst.

**Fehler** (rot): Der Plan ist an dieser Stelle sicher falsch.

    * Start-Element mit eingehender bzw. Ende-Element mit ausgehender Verbindung
    * mehr als ein Ausgang bei einem Baustein, der nur einen Nachfolger hat
    * Baustein mit sich selbst verbunden (ohne Bedingung läuft er endlos)
    * Pfeil mit losem Ende

**Unsicher** (gelb): Kann gewollt sein, ist aber auffällig.

    * doppelte Verbindung zwischen denselben Bausteinen
    * Abzweigung an einem Verbindungspunkt ohne Bedingung
    * Kommentar mit Kommentar verbunden, doppelte Kommentarzuordnung
    * mit der erweiterten Prüfung: siehe ``extended_findings``

**Blockierender Fehler** („Diese Verbindung kann überhaupt nicht erstellt werden.“)
    Nur technisch unmögliche Fälle, z. B. Anfang und Ende am selben Anschluss
    oder ein nicht vorhandener Anschluss.

Nicht markiert werden Rückwärtsverbindungen und Zyklen (Schleifen), eine
Verzweigung, die zu sich selbst zurückführt (Warteschleife), und eine
Verzweigung, deren beide Ausgänge zum selben Ziel führen.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import labels
from app.i18n import tr
from app.model.element_types import ElementType, display_name_for, spec_for

ERROR = "error"
CAUTION = "caution"


@dataclass(frozen=True)
class Finding:
    """Grund, warum eine Verbindung markiert ist, und wie sicher er ist."""
    message: str
    level: str = ERROR


@dataclass(frozen=True)
class ConnectionEnd:
    element_id: str
    element_type: ElementType
    port: str


@dataclass(frozen=True)
class ConnectionInfo:
    """Alles, was die fachliche Bewertung über eine Verbindung wissen muss."""
    id: str
    source_id: str
    source_type: ElementType
    source_port: str
    target_id: str
    target_type: ElementType
    target_port: str


@dataclass(frozen=True)
class ExistingConnection:
    source_id: str
    target_id: str
    is_annotation: bool


def is_annotation(source_type: ElementType, target_type: ElementType) -> bool:
    return ElementType.COMMENT in (ElementType(source_type), ElementType(target_type))


def blocking_error(source: ConnectionEnd, target: ConnectionEnd) -> str | None:
    """Technisch unmögliche Verbindung? Nur dann wird die Erstellung verhindert."""
    source_spec = spec_for(source.element_type)
    target_spec = spec_for(target.element_type)
    if source.port not in source_spec.ports:
        return tr("„{name}“ besitzt keinen Anschluss an dieser Stelle.", name=display_name_for(source.element_type))
    if target.port not in target_spec.ports:
        return tr("„{name}“ besitzt keinen Anschluss an dieser Stelle.", name=display_name_for(target.element_type))
    if source.element_id == target.element_id and source.port == target.port:
        return tr("Anfang und Ende der Verbindung liegen am selben Anschluss.")
    return None


def _finding_for(info: ConnectionInfo, seen_pairs: set, seen_annotations: set, outgoing: dict) -> Finding | None:
    source_spec = spec_for(info.source_type)
    target_spec = spec_for(info.target_type)
    if is_annotation(info.source_type, info.target_type):
        pair = frozenset((info.source_id, info.target_id))
        duplicate = pair in seen_annotations
        seen_annotations.add(pair)
        if info.source_type is ElementType.COMMENT and info.target_type is ElementType.COMMENT:
            return Finding(tr("Kommentare werden normalerweise nicht miteinander verbunden."), CAUTION)
        if duplicate:
            return Finding(tr("Der Kommentar ist diesem Baustein bereits zugeordnet."), CAUTION)
        return None

    pair = (info.source_id, info.target_id)
    duplicate = pair in seen_pairs
    seen_pairs.add(pair)
    count = outgoing.get(info.source_id, 0)
    outgoing[info.source_id] = count + 1
    decision = info.source_type is ElementType.DECISION

    if info.source_id == info.target_id and not decision:
        return Finding(tr("Der Baustein ist mit sich selbst verbunden."))
    if not source_spec.can_be_source:
        return Finding(tr("Ein „{name}“-Element hat normalerweise keine ausgehende Verbindung.",
                          name=display_name_for(info.source_type)))
    if not target_spec.can_be_target:
        return Finding(tr("Ein „{name}“-Element hat normalerweise keine eingehende Verbindung.",
                          name=display_name_for(info.target_type)))
    if decision:
        return None  # zurück zu sich selbst und beide Ausgänge zum selben Ziel sind gültige Abläufe
    if info.source_type is ElementType.JUNCTION:
        if duplicate:
            return Finding(tr("Diese Verbindung existiert bereits."), CAUTION)
        if source_spec.max_outgoing is not None and count >= source_spec.max_outgoing:
            return Finding(tr("Abzweigung ohne Verzweigung: Der Ablauf teilt sich hier ohne Bedingung. "
                              "Für mehrere Ausgänge ist normalerweise eine Verzweigung vorgesehen."), CAUTION)
        return None
    if duplicate:
        return Finding(tr("Diese Verbindung existiert bereits."), CAUTION)
    if source_spec.max_outgoing is not None and count >= source_spec.max_outgoing:
        return Finding(tr("„{name}“ hat normalerweise nur einen Ausgang. "
                          "Für mehrere Ausgänge ist eine Verzweigung vorgesehen.",
                          name=display_name_for(info.source_type)))
    return None


def evaluate_connections(connections: list[ConnectionInfo]) -> dict[str, Finding]:
    """Bewertet alle Verbindungen in Erstellungsreihenfolge.

    Gibt ``{connection_id: Befund}`` für problematische Verbindungen zurück.
    Bei Konflikten (z. B. zweiter Ausgang, Duplikat) wird die jeweils später
    erstellte Verbindung markiert.
    """
    seen_pairs: set = set()
    seen_annotations: set = set()
    outgoing: dict = {}
    findings: dict[str, Finding] = {}
    for info in connections:
        finding = _finding_for(info, seen_pairs, seen_annotations, outgoing)
        if finding is not None:
            findings[info.id] = finding
    return findings


def extended_findings(graph) -> dict[str, Finding]:
    """Zusätzliche, gelbe Hinweise der erweiterten Prüfung (``graph``: Ablaufgraph einer Seite).

    * Ausgang einer Verzweigung ohne Beschriftung, doppelte Beschriftung, nur ein Ausgang
    * Verbindung auf einem Weg, der kein Ende mehr erreicht (Sackgasse oder Endlosschleife)
    * Verbindung von einem Baustein, den der Ablauf nie erreicht
    """
    findings: dict[str, Finding] = {}
    nodes = graph.nodes
    ends = [node_id for node_id, node in nodes.items() if node.type is ElementType.END]
    reaches_end = set(ends)
    stack = list(ends)
    while stack:
        for edge in graph.incoming(stack.pop()):
            if edge.source not in reaches_end:
                reaches_end.add(edge.source)
                stack.append(edge.source)
    reached: set = set()
    for node in nodes.values():
        if node.type is ElementType.START:
            reached |= graph.reachable_from(node.id)

    for edge in graph.edges:
        source = nodes.get(edge.source)
        if source is None:
            continue
        if reached and edge.source not in reached:
            findings[edge.id] = Finding(tr("Dieser Weg wird vom Start aus nie erreicht."), CAUTION)
        elif ends and edge.target not in reaches_end:
            findings[edge.id] = Finding(tr("Von hier aus wird das Ende nie erreicht."), CAUTION)
    for node in nodes.values():
        if node.type is not ElementType.DECISION:
            continue
        exits = graph.outgoing(node.id)
        if len(exits) == 1:
            findings.setdefault(exits[0].id, Finding(tr("Die Verzweigung hat nur diesen einen Ausgang."), CAUTION))
            continue
        written = [" ".join(edge.label.split()).lower() for edge in exits]
        for edge, label in zip(exits, written):
            if not label:
                findings.setdefault(edge.id, Finding(tr("Dieser Ausgang der Verzweigung ist nicht beschriftet."),
                                                     CAUTION))
            elif written.count(label) > 1:
                findings.setdefault(edge.id, Finding(tr("Diese Beschriftung kommt an der Verzweigung mehrfach vor."),
                                                     CAUTION))
    return findings


def validate_connection(source: ConnectionEnd, target: ConnectionEnd,
                        existing: list[ExistingConnection]) -> str | None:
    """Bewertet eine geplante Verbindung gegenüber den vorhandenen.

    Gibt den Grund einer Markierung bzw. (bei technisch unmöglichen Verbindungen)
    die Fehlermeldung zurück, sonst ``None``.
    """
    error = blocking_error(source, target)
    if error is not None:
        return error
    seen_pairs: set = set()
    seen_annotations: set = set()
    outgoing: dict = {}
    for conn in existing:
        if conn.is_annotation:
            seen_annotations.add(frozenset((conn.source_id, conn.target_id)))
        else:
            seen_pairs.add((conn.source_id, conn.target_id))
            outgoing[conn.source_id] = outgoing.get(conn.source_id, 0) + 1
    info = ConnectionInfo("__neu__", source.element_id, ElementType(source.element_type), source.port,
                          target.element_id, ElementType(target.element_type), target.port)
    finding = _finding_for(info, seen_pairs, seen_annotations, outgoing)
    return finding.message if finding is not None else None


def suggest_decision_label(existing_labels: list[str]) -> str:
    """Schlägt für einen weiteren Ausgang einer Verzweigung eine Beschriftung vor."""
    # vorhandene Beschriftungen stammen aus der Projektdatei und können in jeder Sprache stehen
    if not any(labels.is_yes(label) for label in existing_labels):
        return labels.yes_label()
    if not any(labels.is_no(label) for label in existing_labels):
        return labels.no_label()
    return ""
