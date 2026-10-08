"""Befehle für Element- und Projekteigenschaften."""

from __future__ import annotations

import copy

from PySide6.QtGui import QUndoCommand

from app.i18n import tr


class SetElementPropertyCommand(QUndoCommand):
    """Setzt eine Elementeigenschaft (z. B. Schleifenbeginn/-ende) und optional den Text."""

    def __init__(self, scene, element_id: str, key: str, old_value, new_value,
                 old_text: str | None = None, new_text: str | None = None,
                 text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Eigenschaft ändern"), parent)
        self._scene = scene
        self._element_id = element_id
        self._key = key
        self._old = copy.deepcopy(old_value)
        self._new = copy.deepcopy(new_value)
        self._old_text = old_text
        self._new_text = new_text

    def _apply(self, value, text) -> None:
        item = self._scene.element(self._element_id)
        if item is None:
            return
        with self._scene.batch_routing():
            item.set_property(self._key, copy.deepcopy(value))
            if text is not None:
                item.set_text(text)

    def redo(self) -> None:
        self._apply(self._new, self._new_text)

    def undo(self) -> None:
        self._apply(self._old, self._old_text)


class ProjectPropertiesCommand(QUndoCommand):
    """Ändert Projektmetadaten und Rastergröße eines Dokuments."""

    def __init__(self, document, old_meta, new_meta, old_grid: int, new_grid: int,
                 text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Projekteigenschaften ändern"), parent)
        self._document = document
        self._old_meta = old_meta.copy()
        self._new_meta = new_meta.copy()
        self._old_grid = old_grid
        self._new_grid = new_grid

    def _apply(self, meta, grid) -> None:
        self._document.apply_properties(meta.copy(), grid)

    def redo(self) -> None:
        self._apply(self._new_meta, self._new_grid)

    def undo(self) -> None:
        self._apply(self._old_meta, self._old_grid)
