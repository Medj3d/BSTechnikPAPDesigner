"""Regeln für Verbindungen.

Es gibt zwei klar getrennte Stufen:

**Warnung** („Diese Verbindung ist möglicherweise falsch.“)
    Fachliche PAP-Prüfung. Die Verbindung wird trotzdem erstellt, gespeichert
    und rot markiert. Der Benutzer entscheidet selbst, ob sie sinnvoll ist.

    * Baustein mit sich selbst verbunden
    * Start-Element mit eingehender bzw. Ende-Element mit ausgehender Verbindung
    * doppelte Verbindung zwischen denselben Bausteinen
    * mehr als ein Ausgang bei einem Baustein, der nur einen Nachfolger hat
      (alle außer der Verzweigung; auch eine Abzweigung an einem
      Verbindungspunkt ohne Bedingung)
    * Kommentar mit Kommentar verbunden, doppelte Kommentarzuordnung

**Blockierender Fehler** („Diese Verbindung kann überhaupt nicht erstellt werden.“)
    Nur technisch unmögliche Fälle, z. B. Anfang und Ende am selben Anschluss
    oder ein nicht vorhandener Anschluss.

Rückwärtsverbindungen und Zyklen (Schleifen) sind immer unproblematisch.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import labels
from app.i18n import tr
from app.model.element_types import ElementType, display_name_for, spec_for


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


def _warning_for(info: ConnectionInfo, seen_pairs: set, seen_annotations: set, outgoing: dict) -> str | None:
    source_spec = spec_for(info.source_type)
    target_spec = spec_for(info.target_type)
    if is_annotation(info.source_type, info.target_type):
        pair = frozenset((info.source_id, info.target_id))
        duplicate = pair in seen_annotations
        seen_annotations.add(pair)
        if info.source_type is ElementType.COMMENT and info.target_type is ElementType.COMMENT:
            return tr("Kommentare werden normalerweise nicht miteinander verbunden.")
        if duplicate:
            return tr("Der Kommentar ist diesem Baustein bereits zugeordnet.")
        return None

    pair = (info.source_id, info.target_id)
    duplicate = pair in seen_pairs
    seen_pairs.add(pair)
    count = outgoing.get(info.source_id, 0)
    outgoing[info.source_id] = count + 1

    if info.source_id == info.target_id:
        return tr("Der Baustein ist mit sich selbst verbunden.")
    if not source_spec.can_be_source:
        return tr("Ein „{name}“-Element hat normalerweise keine ausgehende Verbindung.",
                  name=display_name_for(info.source_type))
    if not target_spec.can_be_target:
        return tr("Ein „{name}“-Element hat normalerweise keine eingehende Verbindung.",
                  name=display_name_for(info.target_type))
    if duplicate:
        return tr("Diese Verbindung existiert bereits.")
    if source_spec.max_outgoing is not None and count >= source_spec.max_outgoing:
        if info.source_type is ElementType.JUNCTION:
            return tr("Abzweigung ohne Verzweigung: Der Ablauf teilt sich hier ohne Bedingung. "
                      "Für mehrere Ausgänge ist normalerweise eine Verzweigung vorgesehen.")
        return tr("„{name}“ hat normalerweise nur einen Ausgang. "
                  "Für mehrere Ausgänge ist eine Verzweigung vorgesehen.", name=display_name_for(info.source_type))
    return None


def evaluate_connections(connections: list[ConnectionInfo]) -> dict[str, str]:
    """Bewertet alle Verbindungen in Erstellungsreihenfolge.

    Gibt ``{connection_id: warnung}`` für problematische Verbindungen zurück.
    Bei Konflikten (z. B. zweiter Ausgang, Duplikat) wird die jeweils später
    erstellte Verbindung markiert.
    """
    seen_pairs: set = set()
    seen_annotations: set = set()
    outgoing: dict = {}
    warnings: dict[str, str] = {}
    for info in connections:
        message = _warning_for(info, seen_pairs, seen_annotations, outgoing)
        if message:
            warnings[info.id] = message
    return warnings


def validate_connection(source: ConnectionEnd, target: ConnectionEnd,
                        existing: list[ExistingConnection]) -> str | None:
    """Bewertet eine geplante Verbindung gegenüber den vorhandenen.

    Gibt eine Warnung bzw. (bei technisch unmöglichen Verbindungen) die
    Fehlermeldung zurück, sonst ``None``.
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
    return _warning_for(info, seen_pairs, seen_annotations, outgoing)


def suggest_decision_label(existing_labels: list[str]) -> str:
    """Schlägt für einen weiteren Ausgang einer Verzweigung eine Beschriftung vor."""
    # vorhandene Beschriftungen stammen aus der Projektdatei und können in jeder Sprache stehen
    if not any(labels.is_yes(label) for label in existing_labels):
        return labels.yes_label()
    if not any(labels.is_no(label) for label in existing_labels):
        return labels.no_label()
    return ""
