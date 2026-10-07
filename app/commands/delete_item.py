"""Befehl: Bausteine und/oder Verbindungen löschen."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand


class DeleteCommand(QUndoCommand):
    """Löscht Bausteine inklusive aller zugehörigen Verbindungen.

    Beim Rückgängigmachen werden Bausteine und Verbindungen vollständig
    wiederhergestellt (gleiche Objekte, gleiche IDs, gleiche Beschriftungen).
    """

    def __init__(self, scene, element_ids: list[str], connection_ids: list[str] = (),
                 text: str = "Löschen", parent=None):
        super().__init__(text, parent)
        self._scene = scene
        self._items = [scene.element(eid) for eid in element_ids]
        self._items = [item for item in self._items if item is not None]
        connections = []
        seen = set()
        for cid in connection_ids:
            conn = scene.connection(cid)
            if conn is not None and conn.connection_id not in seen:
                connections.append(conn)
                seen.add(conn.connection_id)
        for item in self._items:
            for conn in list(item.connections):
                if conn.connection_id not in seen:
                    connections.append(conn)
                    seen.add(conn.connection_id)
        self._connections = connections

    def is_empty(self) -> bool:
        return not self._items and not self._connections

    def redo(self) -> None:
        scene = self._scene
        rects = [item.scene_rect() for item in self._items]
        with scene.batch_routing():
            for conn in self._connections:
                scene.remove_connection_item(conn)
            for item in self._items:
                scene.remove_element_item(item)
            # Umwege um gelöschte Bausteine werden überflüssig
            scene.refresh_routes_around(rects)

    def undo(self) -> None:
        scene = self._scene
        with scene.batch_routing():
            for item in self._items:
                scene.add_element_item(item)
            for conn in self._connections:
                scene.add_connection_item(conn)
            scene.refresh_routes_around([item.scene_rect() for item in self._items])
        scene.select_items(self._items + self._connections)
