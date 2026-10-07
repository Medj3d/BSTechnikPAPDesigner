"""Befehl: Zeichenreihenfolge (nach vorne / nach hinten)."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand


class ZOrderCommand(QUndoCommand):
    """``changes`` = {element_id: (alt_z, neu_z)}"""

    def __init__(self, scene, changes: dict, text: str = "Reihenfolge ändern", parent=None):
        super().__init__(text, parent)
        self._scene = scene
        self._changes = dict(changes)

    def _apply(self, index: int) -> None:
        for eid, values in self._changes.items():
            item = self._scene.element(eid)
            if item is not None:
                item.set_z_order(values[index])

    def redo(self) -> None:
        self._apply(1)

    def undo(self) -> None:
        self._apply(0)
