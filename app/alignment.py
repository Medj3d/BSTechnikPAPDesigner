"""Ausrichten und Verteilen ausgewählter Bausteine.

Alle Funktionen berechnen nur neue Positionen und liefern ein Dictionary
``{element_id: ((alt_x, alt_y), (neu_x, neu_y))}``; die Szene setzt es als
ein einziger Undo-Schritt um.
"""

from __future__ import annotations

from app.i18n import N_

ALIGN_LEFT = "left"
ALIGN_RIGHT = "right"
ALIGN_TOP = "top"
ALIGN_BOTTOM = "bottom"
ALIGN_CENTER_X = "center_x"   # gleiche senkrechte Mittelachse (Spalte)
ALIGN_CENTER_Y = "center_y"   # gleiche waagerechte Mittelachse (Zeile)
DISTRIBUTE_H = "distribute_h"
DISTRIBUTE_V = "distribute_v"
SNAP_TO_GRID = "snap"

# Deutscher Quelltext (Schlüssel der Übersetzung); angezeigt wird tr(LABELS[modus])
LABELS = {
    ALIGN_LEFT: N_("Links ausrichten"),
    ALIGN_RIGHT: N_("Rechts ausrichten"),
    ALIGN_TOP: N_("Oben ausrichten"),
    ALIGN_BOTTOM: N_("Unten ausrichten"),
    ALIGN_CENTER_X: N_("Mittig ausrichten (Spalte)"),
    ALIGN_CENTER_Y: N_("Mittig ausrichten (Zeile)"),
    DISTRIBUTE_H: N_("Horizontal verteilen"),
    DISTRIBUTE_V: N_("Vertikal verteilen"),
    SNAP_TO_GRID: N_("Am Raster ausrichten"),
}

MIN_ITEMS = {
    ALIGN_LEFT: 2, ALIGN_RIGHT: 2, ALIGN_TOP: 2, ALIGN_BOTTOM: 2,
    ALIGN_CENTER_X: 2, ALIGN_CENTER_Y: 2, DISTRIBUTE_H: 3, DISTRIBUTE_V: 3, SNAP_TO_GRID: 1,
}


def compute_moves(items, mode: str, snap_value=None, force_snap=None) -> dict:
    """Berechnet die neuen Positionen.

    ``items``: FlowItems (Position = Mittelpunkt, ``width``/``height``)
    ``snap_value``: Funktion zum Einrasten eines Einzelwertes (falls Snap aktiv)
    ``force_snap``: Funktion (x, y) → (x, y), die immer auf das Raster rundet
    """
    items = list(items)
    if len(items) < MIN_ITEMS.get(mode, 2):
        return {}
    positions = {it.element_id: (it.pos().x(), it.pos().y()) for it in items}
    new = dict(positions)

    def left(it):
        return positions[it.element_id][0] - it.width / 2

    def right(it):
        return positions[it.element_id][0] + it.width / 2

    def top(it):
        return positions[it.element_id][1] - it.height / 2

    def bottom(it):
        return positions[it.element_id][1] + it.height / 2

    if mode == ALIGN_LEFT:
        target = min(left(it) for it in items)
        for it in items:
            new[it.element_id] = (target + it.width / 2, positions[it.element_id][1])
    elif mode == ALIGN_RIGHT:
        target = max(right(it) for it in items)
        for it in items:
            new[it.element_id] = (target - it.width / 2, positions[it.element_id][1])
    elif mode == ALIGN_TOP:
        target = min(top(it) for it in items)
        for it in items:
            new[it.element_id] = (positions[it.element_id][0], target + it.height / 2)
    elif mode == ALIGN_BOTTOM:
        target = max(bottom(it) for it in items)
        for it in items:
            new[it.element_id] = (positions[it.element_id][0], target - it.height / 2)
    elif mode == ALIGN_CENTER_X:
        target = sum(positions[it.element_id][0] for it in items) / len(items)
        if snap_value is not None:
            target = snap_value(target)
        for it in items:
            new[it.element_id] = (target, positions[it.element_id][1])
    elif mode == ALIGN_CENTER_Y:
        target = sum(positions[it.element_id][1] for it in items) / len(items)
        if snap_value is not None:
            target = snap_value(target)
        for it in items:
            new[it.element_id] = (positions[it.element_id][0], target)
    elif mode == DISTRIBUTE_H:
        ordered = sorted(items, key=left)
        total = sum(it.width for it in ordered)
        span = right(ordered[-1]) - left(ordered[0])
        gap = (span - total) / (len(ordered) - 1)
        cursor = left(ordered[0])
        for it in ordered:
            x = cursor + it.width / 2
            if snap_value is not None and it not in (ordered[0], ordered[-1]):
                x = snap_value(x)
            new[it.element_id] = (x, positions[it.element_id][1])
            cursor += it.width + gap
    elif mode == DISTRIBUTE_V:
        ordered = sorted(items, key=top)
        total = sum(it.height for it in ordered)
        span = bottom(ordered[-1]) - top(ordered[0])
        gap = (span - total) / (len(ordered) - 1)
        cursor = top(ordered[0])
        for it in ordered:
            y = cursor + it.height / 2
            if snap_value is not None and it not in (ordered[0], ordered[-1]):
                y = snap_value(y)
            new[it.element_id] = (positions[it.element_id][0], y)
            cursor += it.height + gap
    elif mode == SNAP_TO_GRID:
        if force_snap is None:
            return {}
        for it in items:
            new[it.element_id] = force_snap(*positions[it.element_id])
    else:
        return {}

    return {eid: (positions[eid], new[eid]) for eid in positions
            if abs(positions[eid][0] - new[eid][0]) > 1e-6 or abs(positions[eid][1] - new[eid][1]) > 1e-6}
