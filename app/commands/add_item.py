"""Befehl: Bausteine (und Verbindungen) hinzufügen."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from app.connections.connection import ConnectionItem
from app.items.factory import create_item
from app.model.diagram import ConnectionData, ElementData


class AddElementsCommand(QUndoCommand):
    """Fügt Bausteine sowie optional Verbindungen hinzu.

    Verbindungen dürfen sowohl neue als auch bereits vorhandene Bausteine
    referenzieren (z. B. beim Einfügen in einen bestehenden Ablauf). Die
    grafischen Objekte werden beim ersten ``redo`` erzeugt und danach
    wiederverwendet, sodass alle weiteren Befehle über IDs darauf zugreifen
    können.
    """

    def __init__(self, scene, elements: list[ElementData], connections: list[ConnectionData] = (),
                 text: str = "Baustein einfügen", select: bool = True, parent=None,
                 select_ids: list[str] | None = None):
        super().__init__(text, parent)
        self._scene = scene
        self._element_data = [e.copy() for e in elements]
        self._connection_data = [c.copy() for c in connections]
        self._select = select
        # None = alle neuen Bausteine auswählen
        self._select_ids = set(select_ids) if select_ids is not None else None
        self._items: list | None = None
        self._connections: list = []

    @property
    def element_ids(self) -> list[str]:
        return [e.id for e in self._element_data]

    def _build(self) -> None:
        self._items = [create_item(data) for data in self._element_data]
        by_id = {item.element_id: item for item in self._items}
        self._connections = []
        for data in self._connection_data:
            source = by_id.get(data.source_id) or self._scene.element(data.source_id)
            target = by_id.get(data.target_id) or self._scene.element(data.target_id)
            if source is None or target is None:
                continue
            self._connections.append(ConnectionItem(data, source, target))

    def redo(self) -> None:
        if self._items is None:
            self._build()
        scene = self._scene
        with scene.batch_routing():
            for item in self._items:
                scene.add_element_item(item)
            for conn in self._connections:
                scene.add_connection_item(conn)
            # bestehende Linien, die jetzt einen neuen Baustein kreuzen, neu führen
            scene.refresh_routes_around([item.scene_rect() for item in self._items])
        if self._select:
            scene.select_items([item for item in self._items
                                if self._select_ids is None or item.element_id in self._select_ids])

    def undo(self) -> None:
        scene = self._scene
        rects = [item.scene_rect() for item in self._items or []]
        with scene.batch_routing():
            for conn in reversed(self._connections):
                scene.remove_connection_item(conn)
            for item in reversed(self._items or []):
                scene.remove_element_item(item)
            scene.refresh_routes_around(rects)
