"""Einem Pfeil bis zu seinem Baustein folgen („Zum Anfang/Ziel des Pfeils“).

Endet ein Pfeil an einem Verbindungspunkt, geht es auf dem Stamm weiter (dem Pfeil, den der Punkt
aufgetrennt hat) bzw. auf der einzigen Linie, die dort weiterführt – bis zu einem echten Baustein.
Ist der Weg nicht eindeutig (z. B. ein loses Ende oder mehrere Abzweige ohne Stamm), bleibt es beim
Verbindungspunkt.
"""

from __future__ import annotations

from app.model.element_types import TRUNK_IN_KEY, TRUNK_OUT_KEY


def _next_line(junction, forward: bool):
    """Die Linie, auf der es am Verbindungspunkt weitergeht – oder ``None``, wenn das nicht eindeutig ist."""
    if forward:
        lines = [c for c in junction.connections if c.source is junction and not c.is_annotation]
        trunk = junction.data.properties.get(TRUNK_OUT_KEY)
    else:
        lines = [c for c in junction.connections if c.target is junction and not c.is_annotation]
        trunk = junction.data.properties.get(TRUNK_IN_KEY)
    for line in lines:
        if trunk and line.data.id == trunk:
            return line
    return lines[0] if len(lines) == 1 else None


def line_end(connection, forward: bool):
    """Der Baustein am Ziel (``forward``) bzw. am Anfang des Pfeils; Verbindungspunkte werden übersprungen."""
    item = connection.target if forward else connection.source
    seen = {id(item)}
    while item is not None and item.is_junction:
        line = _next_line(item, forward)
        if line is None:
            break
        following = line.target if forward else line.source
        if id(following) in seen:   # Kreis nur aus Verbindungspunkten
            break
        seen.add(id(following))
        item = following
    return item
