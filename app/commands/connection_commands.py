"""Befehle rund um Verbindungen."""

from __future__ import annotations

import copy

from PySide6.QtGui import QUndoCommand

from app.connections.connection import ConnectionItem
from app.i18n import tr
from app.model.diagram import ConnectionData


class AddConnectionCommand(QUndoCommand):
    """Erzeugt eine Verbindung von Baustein A (Quelle) nach Baustein B (Ziel)."""

    def __init__(self, scene, data: ConnectionData, text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Verbindung erstellen"), parent)
        self._scene = scene
        self._data = data.copy()
        self._conn: ConnectionItem | None = None

    @property
    def connection_id(self) -> str:
        return self._data.id

    def redo(self) -> None:
        scene = self._scene
        if self._conn is None:
            source = scene.element(self._data.source_id)
            target = scene.element(self._data.target_id)
            if source is None or target is None:
                self.setObsolete(True)
                return
            self._conn = ConnectionItem(self._data, source, target)
        scene.add_connection_item(self._conn)

    def undo(self) -> None:
        if self._conn is not None:
            self._scene.remove_connection_item(self._conn)


class SetRoutingCommand(QUndoCommand):
    """Ändert die (manuelle) Linienführung einer Verbindung."""

    def __init__(self, scene, connection_id: str, old_routing: dict, new_routing: dict,
                 text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Linienführung ändern"), parent)
        self._scene = scene
        self._connection_id = connection_id
        self._old = copy.deepcopy(old_routing)
        self._new = copy.deepcopy(new_routing)

    def _apply(self, value: dict) -> None:
        conn = self._scene.connection(self._connection_id)
        if conn is not None:
            conn.set_routing(value)

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)
