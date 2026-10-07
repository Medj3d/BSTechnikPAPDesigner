"""Befehl: Bausteine verschieben."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QUndoCommand

MOVE_COMMAND_ID = 1001


class MoveItemsCommand(QUndoCommand):
    """Verschiebt Bausteine. ``moves`` = {element_id: ((alt_x, alt_y), (neu_x, neu_y))}.

    Tastatur-Verschiebungen (``mergeable=True``) werden zu einem Schritt
    zusammengefasst, solange dieselben Bausteine bewegt werden.
    """

    def __init__(self, scene, moves: dict, text: str = "Verschieben", mergeable: bool = False,
                 parent=None):
        super().__init__(text, parent)
        self._scene = scene
        self._moves = dict(moves)
        self._mergeable = mergeable

    def id(self) -> int:
        return MOVE_COMMAND_ID if self._mergeable else -1

    def mergeWith(self, other) -> bool:
        if not isinstance(other, MoveItemsCommand) or not (self._mergeable and other._mergeable):
            return False
        if set(other._moves) != set(self._moves):
            return False
        for eid, (_, new) in other._moves.items():
            old, _ = self._moves[eid]
            self._moves[eid] = (old, new)
        return True

    def _apply(self, index: int) -> None:
        scene = self._scene
        rects = []
        with scene.batch_routing():
            for eid, positions in self._moves.items():
                item = scene.element(eid)
                if item is None:
                    continue
                w, h = item.width, item.height
                for x, y in positions:  # alte und neue Lage
                    rects.append(QRectF(x - w / 2, y - h / 2, w, h))
                x, y = positions[index]
                item.setPos(QPointF(x, y))
        # Verbindungen, die an den Bausteinen vorbeiführen, ggf. neu führen
        scene.refresh_routes_around(rects, moved_ids=set(self._moves))

    def redo(self) -> None:
        self._apply(1)

    def undo(self) -> None:
        self._apply(0)
