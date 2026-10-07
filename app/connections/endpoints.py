"""Verbindungsziele.

Eine Verbindung kann an drei Arten von Zielen beginnen oder enden::

    ConnectionEndpoint
    ├── Block                (Baustein + Anschluss)
    ├── Verbindungsknoten    (Junction – ebenfalls ein Element)
    └── bestehender Pfeil    (Punkt auf einer Verbindung)

Wird ein Pfeil als Ziel gewählt, entsteht beim Erstellen an dieser Stelle ein
Verbindungsknoten: Der Pfeil A → B wird zu A → Knoten → B, und die neue
Verbindung setzt am Knoten an. Dieses Modul enthält die dafür nötige
Geometrie (Projektion auf den Pfeil, Einrasten, Richtung der Anschlüsse).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF

from app.model.element_types import (PORT_BOTTOM, PORT_DIRECTIONS, PORT_LEFT, PORT_RIGHT, PORT_TOP,
                                     ElementType)

# Mindestabstand eines Knotens zu den Enden des Pfeils (Anschluss bzw. Pfeilspitze)
END_MARGIN = 14.0
BEND_MARGIN = 4.0


@dataclass
class ConnectionEndpoint:
    """Anfang oder Ende einer (geplanten) Verbindung."""
    item: object | None = None      # FlowItem (Block oder Verbindungsknoten)
    port: str | None = None
    edge: object | None = None      # ConnectionItem (bestehender Pfeil)
    point: QPointF | None = None    # Anschlusspunkt auf dem Pfeil
    direction: tuple | None = None  # Flussrichtung des getroffenen Pfeilsegments

    @property
    def is_edge(self) -> bool:
        return self.edge is not None

    @property
    def element_type(self) -> ElementType:
        return ElementType.JUNCTION if self.is_edge else self.item.element_type

    def scene_pos(self) -> QPointF:
        if self.is_edge:
            return QPointF(self.point)
        if self.port is not None:
            return self.item.port_scene_pos(self.port)
        return self.item.scenePos()

    def same_target(self, other: "ConnectionEndpoint | None") -> bool:
        if other is None:
            return False
        if self.is_edge or other.is_edge:
            return self.edge is other.edge and self.is_edge == other.is_edge \
                and _close(self.point, other.point)
        return self.item is other.item and self.port == other.port


def _close(a: QPointF | None, b: QPointF | None) -> bool:
    return a is not None and b is not None and abs(a.x() - b.x()) < 0.5 and abs(a.y() - b.y()) < 0.5


def point_segment_distance(p: tuple, a: tuple, b: tuple) -> tuple[float, tuple]:
    """Abstand von ``p`` zum Segment a–b und der nächstgelegene Punkt."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-12:
        return math.hypot(p[0] - ax, p[1] - ay), (ax, ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(p[0] - cx, p[1] - cy), (cx, cy)


def nearest_segment(points: list, pos: QPointF) -> tuple[float, int] | None:
    """Kleinster Abstand von ``pos`` zum Linienzug und Index des Segments."""
    best = None
    p = (pos.x(), pos.y())
    for index, (a, b) in enumerate(zip(points[:-1], points[1:])):
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 1e-6:
            continue
        dist, _ = point_segment_distance(p, a, b)
        if best is None or dist < best[0]:
            best = (dist, index)
    return best


def segment_direction(a: tuple, b: tuple) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return (1.0 if dx >= 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy >= 0 else -1.0)


def anchor_on_edge(points: list, index: int, pos: QPointF, snap) -> tuple[QPointF, tuple[float, float]]:
    """Anschlusspunkt auf Segment ``index`` für den Mauspunkt ``pos``.

    Der Punkt wird auf das Segment projiziert, entlang des Segments am Raster
    ausgerichtet (``snap``) und so begrenzt, dass er nicht auf einem
    Anschluss oder in der Pfeilspitze liegt.
    """
    a, b = points[index], points[index + 1]
    direction = segment_direction(a, b)
    last = len(points) - 2
    margin_a = END_MARGIN if index == 0 else BEND_MARGIN
    margin_b = END_MARGIN if index == last else BEND_MARGIN
    horizontal = direction[1] == 0.0
    axis = 0 if horizontal else 1
    start, end = a[axis], b[axis]
    sign = 1.0 if end >= start else -1.0
    low = start + sign * margin_a
    high = end - sign * margin_b
    lo, hi = min(low, high), max(low, high)
    value = snap((pos.x(), pos.y())[axis])
    if (high - low) * sign < 0:  # Segment zu kurz: Mitte verwenden
        value = (start + end) / 2
    else:
        value = max(lo, min(hi, value))
    if horizontal:
        return QPointF(value, a[1]), direction
    return QPointF(a[0], value), direction


def port_for_vector(dx: float, dy: float) -> str:
    """Anschluss, dessen Richtung dem Vektor am ehesten entspricht."""
    if abs(dx) >= abs(dy):
        return PORT_RIGHT if dx >= 0 else PORT_LEFT
    return PORT_BOTTOM if dy >= 0 else PORT_TOP


def trunk_ports(direction: tuple[float, float]) -> tuple[str, str]:
    """Anschlüsse des Knotens für den aufgetrennten Pfeil: (Eingang, Ausgang).

    Der Pfeil kommt entgegen der Flussrichtung herein und läuft in
    Flussrichtung weiter – unabhängig davon, ob er nach unten, oben, links
    oder rechts zeigt.
    """
    dx, dy = direction
    return port_for_vector(-dx, -dy), port_for_vector(dx, dy)


def branch_port(direction: tuple[float, float], anchor: QPointF, other: QPointF) -> str:
    """Seitlicher Anschluss des Knotens für die neue Verbindung (zur Gegenseite hin)."""
    dx, dy = direction
    if dy == 0.0:  # waagerechter Pfeil: oben oder unten ansetzen
        return PORT_TOP if other.y() < anchor.y() else PORT_BOTTOM
    return PORT_LEFT if other.x() < anchor.x() else PORT_RIGHT


def port_toward(center: QPointF, point: QPointF, taken: set) -> str:
    """Freier Anschluss eines Knotens, der am besten in Richtung ``point`` zeigt."""
    vx, vy = point.x() - center.x(), point.y() - center.y()
    ranked = sorted(PORT_DIRECTIONS, key=lambda port: -(PORT_DIRECTIONS[port][0] * vx
                                                        + PORT_DIRECTIONS[port][1] * vy))
    for port in ranked:
        if port not in taken:
            return port
    return ranked[0]
