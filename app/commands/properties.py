"""Befehle für Element- und Projekteigenschaften."""

from __future__ import annotations

import copy
import dataclasses

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
        # Nur die geänderten Angaben gehören zu diesem Schritt: Was das Programm später selbst setzt (z. B. den Namen
        # aus dem Dateinamen beim ersten Speichern), bleibt bei Rückgängig/Wiederholen erhalten.
        self._fields = [f.name for f in dataclasses.fields(new_meta)
                        if getattr(old_meta, f.name) != getattr(new_meta, f.name)]

    def _apply(self, source, grid) -> None:
        meta = self._document.meta.copy()
        for name in self._fields:
            setattr(meta, name, copy.deepcopy(getattr(source, name)))
        self._document.apply_properties(meta, grid)

    def redo(self) -> None:
        self._apply(self._new_meta, self._new_grid)

    def undo(self) -> None:
        self._apply(self._old_meta, self._old_grid)
