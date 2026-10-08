"""Befehle: Text eines Bausteins bzw. Beschriftung einer Verbindung ändern."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from app.i18n import tr


class EditTextCommand(QUndoCommand):
    def __init__(self, scene, element_id: str, old_text: str, new_text: str,
                 text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Text ändern"), parent)
        self._scene = scene
        self._element_id = element_id
        self._old = old_text
        self._new = new_text

    def _apply(self, value: str) -> None:
        item = self._scene.element(self._element_id)
        if item is not None:
            with self._scene.batch_routing():
                item.set_text(value)

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)


class EditLabelCommand(QUndoCommand):
    def __init__(self, scene, connection_id: str, old_label: str, new_label: str,
                 text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Beschriftung ändern"), parent)
        self._scene = scene
        self._connection_id = connection_id
        self._old = old_label
        self._new = new_label

    def _apply(self, value: str) -> None:
        conn = self._scene.connection(self._connection_id)
        if conn is not None:
            conn.set_label(value)

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)
