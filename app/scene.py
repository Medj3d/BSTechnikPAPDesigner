"""Die Diagrammszene.

Die Szene verwaltet alle Bausteine und Verbindungen eines Diagramms über
eindeutige IDs, setzt Benutzeraktionen in Undo-fähige Befehle um und
implementiert die Interaktion auf der Arbeitsfläche (Einrasten, Verbinden,
Inline-Bearbeitung, Drop-Vorschau, Tastatursteuerung).
"""

from __future__ import annotations

import math
from contextlib import contextmanager

import shiboken6
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QGuiApplication, QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from app import config, styles
from app.commands import (AddConnectionCommand, AddElementsCommand, DeleteCommand,
                          EditLabelCommand, EditTextCommand, MoveItemsCommand,
                          SetElementPropertyCommand, SetRoutingCommand, ZOrderCommand)
from app.connections import routing
from app.connections import endpoints
from app.connections.connection import ConnectionItem, rect_from_qrect
from app.connections.endpoints import ConnectionEndpoint
from app.connections.label import ConnectionLabel, label_font
from app.connections.temp_connection import (STATE_BLOCKED, STATE_OK, STATE_WARNING, AnchorMarker,
                                             TempConnectionItem)
from app.i18n import tr
from app.inline_editor import InlineTextEditor
from app.items.base_item import FlowItem, shared_item_font
from app.items.factory import create_item, new_element_data
from app.items.ghost_item import GhostItem
from app.labels import yes_label
from app.model import rules
from app.model.diagram import ConnectionData, DiagramSettings, ElementData, new_id
from app.model.element_types import (LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, PORT_BOTTOM, PORT_LEFT,
                                     PORT_RIGHT, PORT_TOP, TRUNK_IN_KEY, TRUNK_OUT_KEY, ElementType,
                                     default_text_for, display_name_for, is_default_text, spec_for)

# Bausteine, die in eine bestehende Verbindung eingefügt werden können
INSERTABLE_TYPES = {
    ElementType.INPUT, ElementType.OUTPUT, ElementType.PROCESS, ElementType.SUBPROGRAM,
    ElementType.DECISION, ElementType.LOOP,
}
VERTICAL_GAP = 60.0
SIDE_GAP = 60.0
MIN_INSERT_GAP = 40.0
LABEL_EDIT_WIDTH = 220.0
# Auswahlzone um Pfeile beim Anschließen (Bildschirmpixel bzw. Szeneneinheiten)
EDGE_HIT_PX = 8.0
EDGE_HIT_MIN = 5.0
EDGE_HIT_MAX = 24.0


def snap_to(value: float, grid: float) -> float:
    """Rundet auf das nächste Rastervielfache (x,5 immer aufwärts).

    Bewusst nicht ``round()``: Dessen „Banker's Rounding“ (0,5 → 0, 1,5 → 2)
    würde beim gemeinsamen Verschieben mehrerer Bausteine unterschiedliche
    Versätze erzeugen und so ihre relative Anordnung verändern.
    """
    return math.floor(value / grid + 0.5) * grid if grid > 0 else value


class DiagramScene(QGraphicsScene):
    status_message = Signal(str)
    selection_state_changed = Signal()
    content_changed = Signal()
    editing_changed = Signal(bool)

    def __init__(self, settings: DiagramSettings, undo_stack: QUndoStack, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.undo_stack = undo_stack
        self.theme = styles.current_theme()
        self.exporting = False
        self.single_selected: FlowItem | None = None
        self._elements: dict[str, FlowItem] = {}
        self._connections: dict[str, ConnectionItem] = {}
        self._batch_depth = 0
        self._pending_routes: dict[str, ConnectionItem] = {}
        self._drag_move_active = False
        self._move_start: dict[str, tuple] = {}
        self._connect_drag: dict | None = None
        self._temp_connection: TempConnectionItem | None = None
        self._ghost: GhostItem | None = None
        self._drop_connection: ConnectionItem | None = None
        self._editor: InlineTextEditor | None = None
        self._edit_state: dict | None = None
        self._hover_port_item: FlowItem | None = None
        self._selection_batch = False
        self._order_counter = 0
        self._validation_dirty = False
        self._pending_heal_updates: list[tuple] = []
        # Teile eines aufgetrennten Pfeils erben dessen Erstellungsreihenfolge,
        # damit Warnungen nicht auf den Stamm „überspringen“.
        self._order_hints: dict[str, float] = {}
        self._hover_edge_marker: TempConnectionItem | None = None
        half = config.SCENE_HALF_EXTENT
        self.setSceneRect(-half, -half, 2 * half, 2 * half)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.selectionChanged.connect(self._on_selection_changed)

    # ================================================================ Registry
    def element(self, element_id: str) -> FlowItem | None:
        return self._elements.get(element_id)

    def connection(self, connection_id: str) -> ConnectionItem | None:
        return self._connections.get(connection_id)

    def elements(self) -> list[FlowItem]:
        return list(self._elements.values())

    def connections(self) -> list[ConnectionItem]:
        return list(self._connections.values())

    def add_element_item(self, item: FlowItem) -> None:
        if item.scene() is not self:
            self.addItem(item)
        self._elements[item.element_id] = item
        item.apply_z()
        self.content_changed.emit()

    def remove_element_item(self, item: FlowItem) -> None:
        if self._edit_state and self._edit_state.get("item") is item:
            self.cancel_edit()
        if self._hover_port_item is item:
            self._hover_port_item = None
        if self._connect_drag and item in (self._connect_drag.get("source"), self._connect_drag.get("target")):
            self._cancel_connection_drag()
        if self.mouseGrabberItem() is item:
            # Ziehen wird hier nur abgebrochen: innerhalb eines Befehls darf
            # kein weiterer Befehl auf den Undo-Stapel gelegt werden.
            self._drag_move_active = False
            self._move_start = {}
            item.ungrabMouse()
        item.setSelected(False)
        item.reset_hover_state()
        if item.scene() is self:
            self.removeItem(item)
        self._elements.pop(item.element_id, None)
        self._move_start.pop(item.element_id, None)
        self.content_changed.emit()

    def add_connection_item(self, conn: ConnectionItem) -> None:
        if conn.scene() is not self:
            self.addItem(conn)
        self._connections[conn.connection_id] = conn
        if conn.order is None:
            inherited = self._order_hints.pop(conn.connection_id, None)
            if inherited is not None:
                conn.order = inherited
            else:
                self._order_counter += 1
                conn.order = self._order_counter
        for end in (conn.source, conn.target):
            if conn not in end.connections:
                end.connections.append(conn)
        self._schedule_route(conn)
        self._request_validation()
        self.content_changed.emit()

    def remove_connection_item(self, conn: ConnectionItem) -> None:
        if self._edit_state and self._edit_state.get("connection") is conn:
            self.cancel_edit()
        if self._drop_connection is conn:
            self._drop_connection = None
        if self.mouseGrabberItem() is conn:
            if conn.is_segment_dragging:
                conn.end_segment_drag(cancel=True, commit=False)
            conn.ungrabMouse()
        conn.setSelected(False)
        conn.reset_hover_state()
        if conn.scene() is self:
            self.removeItem(conn)
        self._connections.pop(conn.connection_id, None)
        self._pending_routes.pop(conn.connection_id, None)
        for end in (conn.source, conn.target):
            if conn in end.connections:
                end.connections.remove(conn)
        conn.set_warning(None)
        self._request_validation()
        self.content_changed.emit()

    def clear_diagram(self) -> None:
        self.cancel_edit()
        for conn in self.connections():
            self.remove_connection_item(conn)
        for item in self.elements():
            self.remove_element_item(item)

    # ============================================================== Laden/Export
    def load_content(self, elements: list[ElementData], connections: list[ConnectionData]) -> list[str]:
        """Baut die Szene aus Modelldaten auf. Gibt Warnungen zurück."""
        warnings: list[str] = []
        loaded: list[ConnectionItem] = []
        with self.batch_routing():
            for data in elements:
                if data.id in self._elements:
                    warnings.append(tr("Doppelte Element-ID „{id}“ wurde übersprungen.", id=data.id))
                    continue
                self.add_element_item(create_item(data))
            for data in connections:
                if data.id in self._connections:
                    warnings.append(tr("Doppelte Verbindungs-ID „{id}“ wurde übersprungen.", id=data.id))
                    continue
                source = self.element(data.source_id)
                target = self.element(data.target_id)
                if source is None or target is None:
                    warnings.append(tr("Eine Verbindung verweist auf ein nicht vorhandenes Element "
                                       "und wurde entfernt."))
                    continue
                if data.source_port not in source.ports:
                    data.source_port = PORT_BOTTOM if PORT_BOTTOM in source.ports else source.ports[0]
                    warnings.append(tr("Ein ungültiger Quellanschluss wurde korrigiert."))
                if data.target_port not in target.ports:
                    data.target_port = PORT_TOP if PORT_TOP in target.ports else target.ports[0]
                    warnings.append(tr("Ein ungültiger Zielanschluss wurde korrigiert."))
                if source is target and data.source_port == data.target_port:
                    warnings.append(tr("Eine Verbindung ohne Länge (gleicher Anschluss) wurde entfernt."))
                    continue
                conn = ConnectionItem(data, source, target)
                self.add_connection_item(conn)
                loaded.append(conn)
        # Gespeicherten Linienverlauf übernehmen: Die Linien verlaufen dann genau
        # wie beim Speichern, auch wo die automatische Führung heute anders wählte.
        for conn in loaded:
            path, conn.data.path = conn.data.path, None
            if path and conn.scene() is self:
                conn.adopt_path(path)
        return warnings

    def element_data(self) -> list[ElementData]:
        return [item.data.copy() for item in self._elements.values()]

    def ordered_connections(self) -> list[ConnectionItem]:
        """Verbindungen in Erstellungsreihenfolge."""
        return sorted(self._connections.values(), key=lambda conn: conn.order or 0)

    def connection_data(self) -> list[ConnectionData]:
        """Verbindungen in Erstellungsreihenfolge, jeweils mit ihrem angezeigten Linienverlauf."""
        result = []
        for conn in self.ordered_connections():
            data = conn.data.copy()
            data.path = [(float(x), float(y)) for x, y in conn.points()] or None
            result.append(data)
        return result

    # ======================================================== Warnungen
    def _request_validation(self) -> None:
        self._validation_dirty = True
        if self._batch_depth == 0:
            self._revalidate()

    def _connection_info(self, conn: ConnectionItem) -> rules.ConnectionInfo:
        data = conn.data
        return rules.ConnectionInfo(data.id, data.source_id, conn.source.element_type, data.source_port,
                                    data.target_id, conn.target.element_type, data.target_port)

    def _revalidate(self) -> None:
        """Fachliche Prüfung aller Verbindungen: Problematische werden rot markiert.

        Die Prüfung verhindert nichts – sie markiert nur (siehe ``rules``).
        """
        self._validation_dirty = False
        conns = self.ordered_connections()
        warnings = rules.evaluate_connections([self._connection_info(conn) for conn in conns])
        for conn in conns:
            conn.set_warning(warnings.get(conn.connection_id))

    def connection_warnings(self) -> dict[str, str]:
        return {conn.connection_id: conn.warning for conn in self._connections.values() if conn.warning}

    def diagram_bounds(self) -> QRectF:
        rect = QRectF()
        for item in self._elements.values():
            rect = rect.united(item.scene_rect())
        for conn in self._connections.values():
            rect = rect.united(conn.mapToScene(conn.shape().boundingRect()).boundingRect())
            if conn.label.isVisible():
                rect = rect.united(conn.label.mapToScene(conn.label.boundingRect()).boundingRect())
        return rect

    @contextmanager
    def export_mode(self, theme):
        """Rendert ohne Auswahl, Hover, Anschlusspunkte und Hilfsobjekte."""
        self.commit_edit()
        old_theme, old_exporting = self.theme, self.exporting
        helpers = [it for it in (self._temp_connection, self._ghost, self._hover_edge_marker)
                   if it is not None and it.isVisible()]
        for helper in helpers:
            helper.setVisible(False)
        self.theme = theme
        self.exporting = True
        try:
            yield
        finally:
            self.theme = old_theme
            self.exporting = old_exporting
            for helper in helpers:
                helper.setVisible(True)
            self.update()

    # ================================================================ Routing
    @contextmanager
    def batch_routing(self):
        """Fasst Neuberechnungen von Verbindungen zusammen (jede nur einmal)."""
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._flush_routes()

    def _schedule_route(self, conn: ConnectionItem, force: bool = False) -> None:
        """Plant die Aktualisierung einer Verbindung.

        ``force=False`` erlaubt die schnelle Verschiebung des bestehenden
        Linienzugs, wenn Quelle und Ziel um denselben Betrag bewegt wurden;
        ``force=True`` erzwingt eine vollständige Neuberechnung.
        """
        if self._batch_depth > 0:
            previous = self._pending_routes.get(conn.connection_id)
            self._pending_routes[conn.connection_id] = (conn, force or (previous is not None and previous[1]))
        elif conn.scene() is self:
            conn.update_route(allow_translate=not force)

    def _flush_routes(self) -> None:
        pending, self._pending_routes = self._pending_routes, {}
        for conn, force in pending.values():
            if conn.scene() is self:
                conn.update_route(allow_translate=not force)
        if self._validation_dirty:
            self._revalidate()

    def on_item_geometry_changed(self, item: FlowItem) -> None:
        for conn in item.connections:
            self._schedule_route(conn)
        if self._edit_state and self._edit_state.get("item") is item:
            self._position_editor()

    def on_item_resized(self, item: FlowItem, old_rect: QRectF) -> None:
        """Nach einer Größenänderung Linien um den Baustein herum neu führen."""
        self.refresh_routes_around([old_rect, item.scene_rect()])

    def refresh_routes_around(self, rects: list[QRectF], moved_ids: set | None = None) -> None:
        """Berechnet Verbindungen neu, die durch Änderungen betroffen sein könnten.

        Kandidaten werden über den räumlichen Index der Szene gesucht.
        Verbindungen, deren Quelle und Ziel beide mitbewegt wurden, sind
        bereits konsistent verschoben und werden nur neu berechnet, wenn sie
        jetzt einen anderen Baustein durchqueren.
        """
        rects = [r for r in rects if r is not None and not r.isNull()]
        if not rects:
            return
        candidates: dict[str, ConnectionItem] = {}
        for rect in rects:
            for item in self.items(rect, Qt.ItemSelectionMode.IntersectsItemBoundingRect):
                if isinstance(item, ConnectionItem) and item.connection_id in self._connections:
                    candidates[item.connection_id] = item
        with self.batch_routing():
            for conn in candidates.values():
                if moved_ids and conn.data.source_id in moved_ids and conn.data.target_id in moved_ids \
                        and not self._route_blocked(conn):
                    continue
                self._schedule_route(conn, force=True)

    def _route_blocked(self, conn: ConnectionItem) -> bool:
        """True, wenn der aktuelle Linienzug einen fremden Baustein durchquert."""
        points = conn.points()
        if len(points) < 2:
            return True
        obstacles = self.routing_obstacles(conn)
        return any(routing.segment_crosses_rect(a, b, rect)
                   for a, b in zip(points[:-1], points[1:]) for rect in obstacles)

    def routing_obstacles(self, conn: ConnectionItem) -> list:
        s = conn.source.scene_rect()
        t = conn.target.scene_rect()
        area = s.united(t).adjusted(-240, -240, 240, 240)
        obstacles = []
        for item in self.items(area, Qt.ItemSelectionMode.IntersectsItemBoundingRect):
            if isinstance(item, FlowItem) and item is not conn.source and item is not conn.target \
                    and not item.is_comment:
                obstacles.append(rect_from_qrect(item.scene_rect().adjusted(-4, -4, 4, 4)))
        return obstacles

    # ================================================================ Raster
    @property
    def grid_size(self) -> int:
        return max(config.MIN_GRID_SIZE, int(self.settings.grid_size))

    def snap_value(self, value: float) -> float:
        if not self.settings.snap_to_grid:
            return value
        return snap_to(value, self.grid_size)

    def snap_point(self, point: QPointF) -> QPointF:
        return QPointF(self.snap_value(point.x()), self.snap_value(point.y()))

    def force_snap_point(self, point: QPointF) -> QPointF:
        g = self.grid_size
        return QPointF(snap_to(point.x(), g), snap_to(point.y(), g))

    def clamp_point(self, point: QPointF) -> QPointF:
        limit = config.SCENE_HALF_EXTENT - 1000
        return QPointF(max(-limit, min(limit, point.x())), max(-limit, min(limit, point.y())))

    def constrain_item_position(self, item: FlowItem, value) -> QPointF:
        point = QPointF(value)
        if self._drag_move_active:
            # Jeder tatsächlich bewegte Baustein wird für Undo erfasst – auch ein
            # per Strg+Ziehen mitbewegter, nicht ausgewählter Baustein.
            if item.element_id not in self._move_start:
                self._move_start[item.element_id] = (item.pos().x(), item.pos().y())
            point = self.snap_point(point)
        return self.clamp_point(point)

    # ============================================================== Auswahl
    def selected_elements(self) -> list[FlowItem]:
        return [it for it in self.selectedItems() if isinstance(it, FlowItem)]

    def selected_connections(self) -> list[ConnectionItem]:
        return [it for it in self.selectedItems() if isinstance(it, ConnectionItem)]

    def select_items(self, items) -> None:
        """Setzt die Auswahl; Auswertung und Signal erfolgen nur einmal am Ende."""
        self._selection_batch = True
        try:
            self.clearSelection()
            for item in items:
                if item.scene() is self:
                    item.setSelected(True)
        finally:
            self._selection_batch = False
        self._on_selection_changed()

    def select_all(self) -> None:
        self.select_items(self.elements() + self.connections())

    def _on_selection_changed(self) -> None:
        if not shiboken6.isValid(self) or self._selection_batch:
            return
        selected = self.selectedItems()
        previous = self.single_selected
        self.single_selected = selected[0] if len(selected) == 1 and isinstance(selected[0], FlowItem) else None
        for item in (previous, self.single_selected):
            # Beim Schließen eines Projekts können Items bereits zerstört sein
            if item is not None and shiboken6.isValid(item):
                item.update()
        self.selection_state_changed.emit()

    def handle_escape(self) -> None:
        """Esc: laufende Aktion abbrechen, sonst Auswahl aufheben."""
        if self._connect_drag is not None:
            self._cancel_connection_drag()
        elif self._editor is not None:
            self.cancel_edit()
        elif self.pointer_interaction_active():
            self.end_pointer_interaction(cancel=True)
        else:
            self.clearSelection()

    def _segment_dragging_connection(self) -> ConnectionItem | None:
        grabber = self.mouseGrabberItem()
        if isinstance(grabber, ConnectionItem) and grabber.is_segment_dragging:
            return grabber
        for conn in self.selected_connections():
            if conn.is_segment_dragging:
                return conn
        return None

    def pointer_interaction_active(self) -> bool:
        return self._drag_move_active or self._segment_dragging_connection() is not None

    def end_pointer_interaction(self, cancel: bool) -> None:
        """Beendet ein laufendes Ziehen mit der Maus.

        ``cancel=True`` (Esc) stellt den Zustand vor dem Ziehen wieder her;
        sonst wird das Ziehen regulär abgeschlossen (z. B. bevor Löschen oder
        Rückgängig ausgeführt werden), damit die Historie konsistent bleibt.
        """
        if self._connect_drag is not None:
            self._cancel_connection_drag()
        grabber = self.mouseGrabberItem()
        if self._drag_move_active:
            self._drag_move_active = False
            if cancel:
                starts, self._move_start = self._move_start, {}
                with self.batch_routing():
                    for eid, (x, y) in starts.items():
                        item = self.element(eid)
                        if item is not None:
                            item.setPos(QPointF(x, y))
                self.status_message.emit(tr("Verschieben abgebrochen."))
            else:
                self._finish_interactive_move()
        segment_conn = self._segment_dragging_connection()
        if segment_conn is not None:
            segment_conn.end_segment_drag(cancel)
        if grabber is not None and shiboken6.isValid(grabber) and grabber.scene() is self:
            grabber.ungrabMouse()

    # ============================================================ Bausteine
    def _build_new_elements(self, element_type: ElementType, pos: QPointF):
        """Erzeugt Daten für einen neuen Baustein (bzw. ein Schleifenpaar)."""
        element_type = ElementType(element_type)
        if element_type is ElementType.LOOP:
            begin = new_element_data(ElementType.LOOP, pos.x(), pos.y(), properties={LOOP_PART_KEY: LOOP_BEGIN})
            offset = begin.height / 2 + VERTICAL_GAP + spec_for(ElementType.LOOP).default_height / 2
            end = new_element_data(ElementType.LOOP, pos.x(), pos.y() + offset,
                                   properties={LOOP_PART_KEY: LOOP_END})
            link = ConnectionData(new_id(), begin.id, end.id, PORT_BOTTOM, PORT_TOP)
            return [begin, end], [link]
        return [new_element_data(element_type, pos.x(), pos.y())], []

    def prepare_for_command(self) -> None:
        """Offene Texteingabe übernehmen und laufendes Ziehen abschließen."""
        self.commit_edit()
        if self.pointer_interaction_active() or self._connect_drag is not None:
            self.end_pointer_interaction(cancel=False)

    def insert_element(self, element_type: ElementType, pos: QPointF, snap: bool = True,
                       connect_from: FlowItem | None = None,
                       into_connection: ConnectionItem | None = None,
                       flow_axis: str | None = None, connect_port: str | None = None) -> str | None:
        """Fügt einen neuen Baustein ein (ein Undo-Schritt). Gibt die ID zurück.

        Mit ``into_connection`` wird der Baustein in eine bestehende Verbindung
        eingefügt (A → neu → B). Nachfolgende Bausteine werden dabei bei Bedarf
        verschoben, damit genügend Platz entsteht. Mit ``connect_from`` wird
        der neue Baustein vom Anschluss ``connect_port`` (Standard: unten) des
        angegebenen Bausteins aus verbunden.
        """
        self.prepare_for_command()
        element_type = ElementType(element_type)
        point = self.clamp_point(self.snap_point(pos) if snap else pos)
        elements, connections = self._build_new_elements(element_type, point)
        first, last = elements[0], elements[-1]
        name = display_name_for(element_type)
        # Bei einer Schleife nur den Schleifenbeginn auswählen, damit direkt
        # weitergetippt werden kann.
        select_ids = [first.id]

        if into_connection is not None and element_type in INSERTABLE_TYPES \
                and not into_connection.is_annotation and into_connection.scene() is self:
            old = into_connection.data
            source, target = into_connection.source, into_connection.target
            if flow_axis not in ("x", "y"):
                dx = target.pos().x() - source.pos().x()
                dy = target.pos().y() - source.pos().y()
                flow_axis = "y" if abs(dy) >= abs(dx) else "x"
            if flow_axis == "y":
                if target.pos().y() < source.pos().y():  # Rückwärtsverbindung nach oben
                    entry, exit_port = PORT_BOTTOM, PORT_TOP
                else:
                    entry, exit_port = PORT_TOP, PORT_BOTTOM
            elif target.pos().x() >= source.pos().x():
                entry, exit_port = PORT_LEFT, PORT_RIGHT
            else:
                entry, exit_port = PORT_RIGHT, PORT_LEFT
            moves = self._make_room(source, target, elements, flow_axis)
            exit_label = yes_label() if element_type is ElementType.DECISION else ""
            part_in = ConnectionData(new_id(), old.source_id, first.id, old.source_port, entry, old.label)
            part_out = ConnectionData(new_id(), last.id, old.target_id, exit_port, old.target_port, exit_label)
            connections = connections + [part_in, part_out]
            # War die Verbindung Stammteil eines Verbindungsknotens, zeigt der
            # Knoten danach auf den neuen Teil.
            trunk_updates = self._trunk_updates(into_connection, part_in.id, part_out.id)
            self._inherit_order(into_connection, part_in.id)
            self.undo_stack.beginMacro(tr("„{name}“ in Ablauf einfügen", name=name))
            if moves:
                self.undo_stack.push(MoveItemsCommand(self, moves, text=tr("Platz schaffen")))
            self.undo_stack.push(DeleteCommand(self, [], [old.id], text=tr("Verbindung ersetzen")))
            self.undo_stack.push(AddElementsCommand(self, elements, connections,
                                                    text=tr("„{name}“ einfügen", name=name),
                                                    select_ids=select_ids))
            self._push_trunk_updates(trunk_updates)
            self.undo_stack.endMacro()
            return first.id

        if connect_from is not None and connect_from.scene() is self:
            source_port = connect_port or (PORT_BOTTOM if PORT_BOTTOM in connect_from.ports else None)
            if source_port in connect_from.ports and PORT_TOP in spec_for(element_type).ports:
                error = self.validate_new_connection(connect_from, source_port, None, PORT_TOP,
                                                     target_type=element_type, target_id=first.id)
                if error is None:
                    label = self._suggest_label(connect_from)
                    connections = connections + [ConnectionData(new_id(), connect_from.element_id, first.id,
                                                                source_port, PORT_TOP, label)]
        self.undo_stack.push(AddElementsCommand(self, elements, connections,
                                                text=tr("„{name}“ einfügen", name=name),
                                                select_ids=select_ids))
        return first.id

    def _make_room(self, source: FlowItem, target: FlowItem, new_elements: list[ElementData],
                   axis: str) -> dict:
        """Schafft Platz für einen in den Ablauf eingefügten Block.

        Der neue Block wird hinter die Quelle gesetzt; alle Bausteine hinter
        der Quelle (in Flussrichtung) rücken gemeinsam weiter, falls der
        Abstand nicht ausreicht. Rückwärtsverbindungen bleiben unverändert.
        Gibt die nötigen Verschiebungen für einen ``MoveItemsCommand`` zurück.
        """
        g = self.grid_size

        def ceil_grid(value: float) -> float:
            return math.ceil(value / g - 1e-9) * g

        def block_rect() -> QRectF:
            rect = QRectF()
            for e in new_elements:
                rect = rect.united(QRectF(e.x - e.width / 2, e.y - e.height / 2, e.width, e.height))
            return rect

        vertical = axis == "y"
        forward = (target.pos().y() > source.pos().y()) if vertical else (target.pos().x() != source.pos().x())
        if not forward:
            return {}
        direction = 1.0 if vertical or target.pos().x() > source.pos().x() else -1.0
        src = source.scene_rect()
        block = block_rect()

        # Block mit Mindestabstand hinter die Quelle setzen
        if vertical:
            deficit = (src.bottom() + MIN_INSERT_GAP) - block.top()
        elif direction > 0:
            deficit = (src.right() + MIN_INSERT_GAP) - block.left()
        else:
            deficit = block.right() - (src.left() - MIN_INSERT_GAP)
        if deficit > 0:
            shift = ceil_grid(deficit)
            for e in new_elements:
                if vertical:
                    e.y += shift
                else:
                    e.x += shift * direction
            block = block_rect()

        # Nachfolgende Bausteine bei Bedarf verschieben
        if vertical:
            behind = [it for it in self._elements.values()
                      if it is not source and it.scene_rect().top() >= src.bottom() - 1e-6]
            if not behind:
                return {}
            need = block.bottom() + MIN_INSERT_GAP - min(it.scene_rect().top() for it in behind)
        elif direction > 0:
            behind = [it for it in self._elements.values()
                      if it is not source and it.scene_rect().left() >= src.right() - 1e-6]
            if not behind:
                return {}
            need = block.right() + MIN_INSERT_GAP - min(it.scene_rect().left() for it in behind)
        else:
            behind = [it for it in self._elements.values()
                      if it is not source and it.scene_rect().right() <= src.left() + 1e-6]
            if not behind:
                return {}
            need = max(it.scene_rect().right() for it in behind) - (block.left() - MIN_INSERT_GAP)
        if need <= 0:
            return {}
        shift = ceil_grid(need)
        moves = {}
        for it in behind:
            old = (it.pos().x(), it.pos().y())
            new = (old[0], old[1] + shift) if vertical else (old[0] + shift * direction, old[1])
            moves[it.element_id] = (old, new)
        return moves

    def insert_element_smart(self, element_type: ElementType, fallback_center: QPointF) -> str | None:
        """Einfügen über Menü/Palette-Klick.

        Ist genau ein Ablaufbaustein ausgewählt, wird der neue Baustein daran
        angehängt:

        * Verzweigung: am nächsten freien Ausgang (unten, rechts, links),
        * Baustein mit bereits belegtem Ausgang (z. B. Schleifenbeginn): in
          den bestehenden Ablauf eingefügt, Nachfolger rücken auf,
        * sonst: darunter platziert und verbunden.

        Ohne Auswahl wird in der Mitte des sichtbaren Bereichs an einer freien
        Stelle eingefügt.
        """
        self.prepare_for_command()
        element_type = ElementType(element_type)
        spec = spec_for(element_type)
        anchor = self.single_selected
        if anchor is not None and not anchor.is_comment and element_type is not ElementType.COMMENT:
            below_y = anchor.pos().y() + anchor.height / 2 + VERTICAL_GAP + spec.default_height / 2
            if anchor.element_type is ElementType.DECISION:
                taken = self._outgoing_ports(anchor) | self._incoming_ports(anchor)
                port = next((p for p in (PORT_BOTTOM, PORT_RIGHT, PORT_LEFT) if p not in taken), None)
                x = anchor.pos().x()
                if port == PORT_RIGHT:
                    x += anchor.width / 2 + SIDE_GAP + spec.default_width / 2
                elif port == PORT_LEFT:
                    x -= anchor.width / 2 + SIDE_GAP + spec.default_width / 2
                pos = self._free_position(self.force_snap_point(QPointF(x, below_y)), spec.default_width,
                                          spec.default_height, direction=(0, 1))
                if port is None:
                    return self.insert_element(element_type, pos)
                return self.insert_element(element_type, pos, connect_from=anchor, connect_port=port)
            outgoing = [c for c in anchor.connections if c.source is anchor and not c.is_annotation]
            limit = anchor.spec.max_outgoing
            if outgoing and limit is not None and len(outgoing) >= limit and element_type in INSERTABLE_TYPES:
                return self.insert_element(element_type, QPointF(anchor.pos().x(), below_y),
                                           into_connection=outgoing[0], flow_axis="y")
            pos = self._free_position(QPointF(anchor.pos().x(), below_y), spec.default_width, spec.default_height,
                                      direction=(0, 1))
            return self.insert_element(element_type, pos, connect_from=anchor)
        pos = self._free_position(self.force_snap_point(fallback_center), spec.default_width,
                                  spec.default_height, direction=(1, 1))
        return self.insert_element(element_type, pos)

    def _free_position(self, pos: QPointF, width: float, height: float, direction=(0, 1)) -> QPointF:
        """Sucht ab ``pos`` schrittweise eine Stelle mit genügend Abstand zu anderen Bausteinen."""
        step = max(self.grid_size, 20)
        point = QPointF(pos)
        margin = MIN_INSERT_GAP - 1
        for _ in range(200):
            rect = QRectF(point.x() - width / 2, point.y() - height / 2, width, height).adjusted(
                -margin, -margin, margin, margin)
            if not any(item.scene_rect().intersects(rect) for item in self._elements.values()):
                return point
            point = QPointF(point.x() + direction[0] * step, point.y() + direction[1] * step)
        return point

    def delete_selection(self) -> None:
        self.prepare_for_command()
        element_ids = [it.element_id for it in self.selected_elements()]
        connection_ids = [c.connection_id for c in self.selected_connections()]
        if not element_ids and not connection_ids:
            return
        count = len(element_ids) + len(connection_ids)
        text = tr("Löschen") if count == 1 else tr("{count} Objekte löschen", count=count)
        self._pending_heal_updates = []
        extra_junctions, heals = self._plan_junction_healing(set(element_ids), set(connection_ids))
        updates, self._pending_heal_updates = self._pending_heal_updates, []
        command = DeleteCommand(self, element_ids + extra_junctions, connection_ids, text=text)
        if command.is_empty():
            return
        if heals:
            self.undo_stack.beginMacro(text)
            self.undo_stack.push(command)
            self.undo_stack.push(AddElementsCommand(self, [], heals, text=tr("Pfeil wieder verbinden"),
                                                    select=False))
            self._push_trunk_updates(updates)
            self.undo_stack.endMacro()
        else:
            self.undo_stack.push(command)

    def _plan_junction_healing(self, element_ids: set, connection_ids: set) -> tuple[list[str], list]:
        """Fügt aufgetrennte Pfeile wieder zusammen, wenn ein Verbindungsknoten wegfällt.

        * Wird ein Verbindungsknoten gelöscht, wird sein Stamm (A → Knoten → B)
          wieder zu A → B verbunden.
        * Bleibt nach dem Löschen einer Abzweigung nur noch der Stamm am Knoten,
          wird der Knoten entfernt und der Pfeil ebenfalls wieder verbunden.

        Gibt zusätzlich zu löschende Knoten und die neuen Verbindungen zurück.
        """
        doomed = set(connection_ids)
        for eid in element_ids:
            item = self.element(eid)
            if item is not None:
                doomed.update(c.connection_id for c in item.connections)
        candidates = [item for item in self._elements.values() if item.is_junction
                      and (item.element_id in element_ids
                           or any(c.connection_id in doomed for c in item.connections))]
        healed: dict[str, tuple] = {}
        for junction in candidates:
            trunk_in = self.connection(junction.data.properties.get(TRUNK_IN_KEY, ""))
            trunk_out = self.connection(junction.data.properties.get(TRUNK_OUT_KEY, ""))
            if trunk_in is None or trunk_out is None or trunk_in.target is not junction \
                    or trunk_out.source is not junction:
                continue
            if trunk_in.connection_id in connection_ids or trunk_out.connection_id in connection_ids:
                continue  # Stamm wurde ausdrücklich gelöscht
            if junction.element_id not in element_ids:
                remaining = {c.connection_id for c in junction.connections if c.connection_id not in doomed}
                if remaining != {trunk_in.connection_id, trunk_out.connection_id}:
                    continue
            healed[junction.element_id] = (trunk_in, trunk_out)

        extra = [jid for jid in healed if jid not in element_ids]
        removed = set(element_ids) | set(healed)
        heals = []
        for jid, (trunk_in, _trunk_out) in healed.items():
            if trunk_in.source.element_id in healed:
                continue  # Kette: wird vom ersten Knoten aus behandelt
            start = trunk_in
            end = healed[jid][1]
            while end.target.element_id in healed:
                end = healed[end.target.element_id][1]
            if start.source.element_id in removed or end.target.element_id in removed:
                continue
            if start.source is end.target and start.data.source_port == end.data.target_port:
                continue
            heal = ConnectionData(new_id(), start.data.source_id, end.data.target_id,
                                  start.data.source_port, end.data.target_port, start.data.label)
            heals.append(heal)
            self._inherit_order(start, heal.id)
            # benachbarte Knoten zeigen danach auf die wiederhergestellte Verbindung
            self._pending_heal_updates.extend(
                update for update in self._trunk_updates(start, heal.id, heal.id) if update[1] == TRUNK_OUT_KEY)
            self._pending_heal_updates.extend(
                update for update in self._trunk_updates(end, heal.id, heal.id) if update[1] == TRUNK_IN_KEY)
        return extra, heals

    def apply_moves(self, moves: dict, text: str) -> None:
        self.prepare_for_command()
        moves = {eid: (old, new) for eid, (old, new) in moves.items()
                 if abs(old[0] - new[0]) > 1e-6 or abs(old[1] - new[1]) > 1e-6}
        if moves:
            self.undo_stack.push(MoveItemsCommand(self, moves, text=text))

    def move_selection_by(self, dx: float, dy: float) -> None:
        self.prepare_for_command()
        items = self.selected_elements()
        if not items:
            return
        moves = {}
        for item in items:
            old = (item.pos().x(), item.pos().y())
            base = self.snap_point(item.pos())
            new = self.clamp_point(QPointF(base.x() + dx, base.y() + dy))
            moves[item.element_id] = (old, (new.x(), new.y()))
        moves = {eid: mv for eid, mv in moves.items() if mv[0] != mv[1]}
        if moves:
            self.undo_stack.push(MoveItemsCommand(self, moves, text=tr("Verschieben"), mergeable=True))

    def bring_to_front(self) -> None:
        self._change_z(front=True)

    def send_to_back(self) -> None:
        self._change_z(front=False)

    def _change_z(self, front: bool) -> None:
        self.prepare_for_command()
        selected = self.selected_elements()
        if not selected:
            return
        changes = {}
        for layer_is_comment in (False, True):
            group = [it for it in selected if it.is_comment == layer_is_comment]
            if not group:
                continue
            others = [it.data.z for it in self._elements.values() if it.is_comment == layer_is_comment]
            group.sort(key=lambda it: it.data.z)
            if front:
                base = max(others) + 1
                for i, item in enumerate(group):
                    changes[item.element_id] = (item.data.z, base + i)
            else:
                base = min(others) - len(group)
                for i, item in enumerate(group):
                    changes[item.element_id] = (item.data.z, base + i)
        if changes:
            self.undo_stack.push(ZOrderCommand(self, changes,
                                               text=tr("Nach vorne") if front else tr("Nach hinten")))

    def toggle_loop_part(self, item: FlowItem) -> None:
        if item.element_type is not ElementType.LOOP:
            return
        self.prepare_for_command()
        old_part = item.data.properties.get(LOOP_PART_KEY, LOOP_BEGIN)
        new_part = LOOP_END if old_part != LOOP_END else LOOP_BEGIN
        old_text = item.data.text
        new_text = None
        if is_default_text(old_text, ElementType.LOOP, {LOOP_PART_KEY: old_part}):
            new_text = default_text_for(ElementType.LOOP, {LOOP_PART_KEY: new_part})
        self.undo_stack.push(SetElementPropertyCommand(
            self, item.element_id, LOOP_PART_KEY, old_part, new_part,
            old_text if new_text is not None else None, new_text,
            text=tr("Schleifenteil ändern")))

    # ============================================================ Verbindungen
    #
    # Ablauf beim Verbinden (bewusst in dieser Reihenfolge):
    #   Verbindung ziehen → Ziel erkennen (Block, Knoten oder Pfeil)
    #   → Verbindung erstellen → fachliche Prüfung → ggf. rot markieren.
    # Nur technisch unmögliche Verbindungen werden verhindert.

    def _existing_connections(self) -> list[rules.ExistingConnection]:
        return [rules.ExistingConnection(c.data.source_id, c.data.target_id, c.is_annotation)
                for c in self.ordered_connections()]

    def validate_new_connection(self, source: FlowItem, source_port: str, target: FlowItem | None,
                                target_port: str, target_type: ElementType | None = None,
                                target_id: str | None = None) -> str | None:
        """Bewertet eine geplante Block-Verbindung (Warnung oder technischer Fehler)."""
        t_type = target.element_type if target is not None else target_type
        t_id = target.element_id if target is not None else target_id
        return rules.validate_connection(
            rules.ConnectionEnd(source.element_id, source.element_type, source_port),
            rules.ConnectionEnd(t_id, t_type, target_port),
            self._existing_connections(),
        )

    def _suggest_label(self, source: FlowItem) -> str:
        if source.element_type is not ElementType.DECISION:
            return ""
        labels = [c.data.label for c in source.connections
                  if c.source is source and not c.is_annotation]
        return rules.suggest_decision_label(labels)

    @staticmethod
    def _outgoing_ports(item: FlowItem) -> set[str]:
        return {c.data.source_port for c in item.connections if c.source is item and not c.is_annotation}

    @staticmethod
    def _incoming_ports(item: FlowItem) -> set[str]:
        return {c.data.target_port for c in item.connections if c.target is item and not c.is_annotation}

    def _effective_source_port(self, source: FlowItem, port: str, target: FlowItem | None,
                               target_port: str | None, goal: QPointF | None = None) -> str:
        """Anschluss, an dem die neue Verbindung die Quelle tatsächlich verlässt.

        * Verzweigung: Wird von einem bereits belegten Ausgang erneut gezogen,
          wird der freie Anschluss gewählt, der dem Ziel am nächsten liegt – so
          überlagern sich weder Linien noch „ja“/„nein“.
        * Verbindungsknoten: der freie Anschluss in Richtung des Ziels.
        """
        if goal is None:
            if target is None:
                return port
            goal = target.port_scene_pos(target_port) if target_port else target.scenePos()
        if source.is_junction:
            return endpoints.port_toward(source.scenePos(), goal,
                                         self._outgoing_ports(source) | self._incoming_ports(source))
        if source.element_type is not ElementType.DECISION or (target is not None and target.is_comment):
            return port
        used = self._outgoing_ports(source)
        if port not in used:
            return port
        free = [p for p in source.ports if p not in used and p not in self._incoming_ports(source)]
        if not free:
            return port
        return min(free, key=lambda p: math.hypot(source.port_scene_pos(p).x() - goal.x(),
                                                  source.port_scene_pos(p).y() - goal.y()))

    def _resolve_ports(self, source: ConnectionEndpoint, target: ConnectionEndpoint) -> tuple[str, str]:
        """Bestimmt die Anschlüsse beider Enden (für Blöcke, Knoten und Pfeile)."""
        source_pos = source.scene_pos()
        target_pos = target.scene_pos()
        # Ziel: seitlicher Knotenanschluss bzw. freier Knotenanschluss zur Quelle hin
        if target.is_edge:
            target_port = endpoints.branch_port(target.direction, target.point, source_pos)
        elif target.item.is_junction:
            target_port = endpoints.port_toward(target.item.scenePos(), source_pos,
                                                self._outgoing_ports(target.item)
                                                | self._incoming_ports(target.item))
        else:
            target_port = target.port
        if source.is_edge:
            source_port = endpoints.branch_port(source.direction, source.point, target_pos)
        else:
            goal = target.item.port_scene_pos(target_port) if not target.is_edge else target.point
            source_port = self._effective_source_port(source.item, source.port,
                                                      None if target.is_edge else target.item,
                                                      target_port, goal)
        return source_port, target_port

    def _blocking_error(self, source: ConnectionEndpoint, target: ConnectionEndpoint | None,
                        source_port: str | None = None, target_port: str | None = None) -> str | None:
        """Nur technisch unmögliche Verbindungen werden verhindert."""
        if target is None:
            return tr("Kein Ziel für die Verbindung.")
        if source.is_edge and target.is_edge and source.edge is target.edge:
            return tr("Ein Pfeil kann nicht mit sich selbst verbunden werden.")
        for end in (source, target):
            if end.is_edge and (end.edge.scene() is not self or end.edge.is_annotation):
                return tr("An diese Linie kann nicht angeschlossen werden.")
        if not source.is_edge and not target.is_edge:
            return rules.blocking_error(
                rules.ConnectionEnd(source.item.element_id, source.item.element_type, source_port or source.port),
                rules.ConnectionEnd(target.item.element_id, target.item.element_type, target_port or target.port))
        return None

    def _preview_warning(self, source: ConnectionEndpoint, target: ConnectionEndpoint,
                         source_port: str, target_port: str) -> str | None:
        """Fachliche Warnung für eine geplante Verbindung (inkl. künftiger Knoten)."""
        # Künftige Stammteile stehen an der Stelle des aufgetrennten Pfeils
        virtual: dict[str, list] = {}

        def node(end: ConnectionEndpoint, key: str) -> tuple[str, ElementType]:
            if not end.is_edge:
                return end.item.element_id, end.item.element_type
            host = end.edge
            in_port, out_port = endpoints.trunk_ports(end.direction)
            virtual.setdefault(host.connection_id, []).extend([
                rules.ConnectionInfo(f"{key}-in", host.data.source_id, host.source.element_type,
                                     host.data.source_port, key, ElementType.JUNCTION, in_port),
                rules.ConnectionInfo(f"{key}-out", key, ElementType.JUNCTION, out_port,
                                     host.data.target_id, host.target.element_type, host.data.target_port),
            ])
            return key, ElementType.JUNCTION

        source_id, source_type = node(source, "__knoten_quelle__")
        target_id, target_type = node(target, "__knoten_ziel__")
        infos = []
        for conn in self.ordered_connections():
            infos.extend(virtual.get(conn.connection_id) or [self._connection_info(conn)])
        infos.append(rules.ConnectionInfo("__neu__", source_id, source_type, source_port,
                                          target_id, target_type, target_port))
        return rules.evaluate_connections(infos).get("__neu__")

    def _split_edge(self, end: ConnectionEndpoint, elements: list, connections: list,
                    replaced: list, trunk_updates: list) -> str:
        """Trennt den Pfeil am Anschlusspunkt auf: A → B wird A → Knoten → B."""
        host = end.edge
        junction = new_element_data(ElementType.JUNCTION, end.point.x(), end.point.y())
        in_port, out_port = endpoints.trunk_ports(end.direction)
        part_in = ConnectionData(new_id(), host.data.source_id, junction.id, host.data.source_port, in_port,
                                 host.data.label)
        part_out = ConnectionData(new_id(), junction.id, host.data.target_id, out_port, host.data.target_port)
        junction.properties = {TRUNK_IN_KEY: part_in.id, TRUNK_OUT_KEY: part_out.id}
        self._inherit_order(host, part_in.id, part_out.id)
        elements.append(junction)
        connections.extend([part_in, part_out])
        replaced.append(host.connection_id)
        trunk_updates.extend(self._trunk_updates(host, part_in.id, part_out.id))
        return junction.id

    def _inherit_order(self, host: ConnectionItem, *connection_ids: str) -> None:
        if host.order is not None:
            for connection_id in connection_ids:
                self._order_hints[connection_id] = host.order

    def _trunk_updates(self, host: ConnectionItem, first_id: str, last_id: str) -> list[tuple]:
        """Stamm-Verweise benachbarter Knoten, wenn deren Stammteil ersetzt wird."""
        updates = []
        if host.target.is_junction and host.target.data.properties.get(TRUNK_IN_KEY) == host.connection_id:
            updates.append((host.target.element_id, TRUNK_IN_KEY, host.connection_id, last_id))
        if host.source.is_junction and host.source.data.properties.get(TRUNK_OUT_KEY) == host.connection_id:
            updates.append((host.source.element_id, TRUNK_OUT_KEY, host.connection_id, first_id))
        return updates

    def _push_trunk_updates(self, updates: list[tuple]) -> None:
        for element_id, key, old, new in updates:
            self.undo_stack.push(SetElementPropertyCommand(self, element_id, key, old, new,
                                                           text=tr("Verbindungspunkt aktualisieren")))

    def connect_endpoints(self, source: ConnectionEndpoint, target: ConnectionEndpoint) -> str | None:
        """Erstellt eine Verbindung zwischen zwei beliebigen Zielen (ein Undo-Schritt).

        Liegt ein Ende auf einem bestehenden Pfeil, wird dieser dort mit einem
        Verbindungsknoten aufgetrennt. Anschließend wird die fachliche
        Prüfung ausgeführt; eine problematische Verbindung wird nur rot
        markiert, aber nicht verhindert.
        """
        source_port, target_port = self._resolve_ports(source, target)
        error = self._blocking_error(source, target, source_port, target_port)
        if error is not None:
            self.status_message.emit(error)
            return None
        self.prepare_for_command()
        if source.is_edge or target.is_edge:
            elements, connections, replaced, trunk_updates = [], [], [], []
            source_id = self._split_edge(source, elements, connections, replaced, trunk_updates) \
                if source.is_edge else source.item.element_id
            target_id = self._split_edge(target, elements, connections, replaced, trunk_updates) \
                if target.is_edge else target.item.element_id
            label = "" if source.is_edge else self._suggest_label(source.item)
            data = ConnectionData(new_id(), source_id, target_id, source_port, target_port, label)
            connections.append(data)
            self.undo_stack.beginMacro(tr("An Pfeil anschließen"))
            self.undo_stack.push(DeleteCommand(self, [], replaced, text=tr("Pfeil auftrennen")))
            self.undo_stack.push(AddElementsCommand(self, elements, connections,
                                                    text=tr("Verbindungspunkt einfügen"), select=False))
            self._push_trunk_updates(trunk_updates)
            self.undo_stack.endMacro()
        else:
            annotation = rules.is_annotation(source.item.element_type, target.item.element_type)
            label = "" if annotation else self._suggest_label(source.item)
            data = ConnectionData(new_id(), source.item.element_id, target.item.element_id,
                                  source_port, target_port, label)
            self.undo_stack.push(AddConnectionCommand(
                self, data, text=tr("Kommentar zuordnen") if annotation else tr("Verbindung erstellen")))
        conn = self.connection(data.id)
        if conn is not None and conn.warning:
            self.status_message.emit(tr("Hinweis: {warning} Die Verbindung wurde trotzdem erstellt "
                                        "und ist rot markiert.", warning=conn.warning))
        return data.id

    def create_connection(self, source: FlowItem, source_port: str, target: FlowItem,
                          target_port: str) -> str | None:
        """Block-zu-Block-Verbindung (fachliche Probleme erzeugen nur eine Warnung)."""
        return self.connect_endpoints(ConnectionEndpoint(item=source, port=source_port),
                                      ConnectionEndpoint(item=target, port=target_port))

    def connect_to_edge(self, source: FlowItem, source_port: str, edge: ConnectionItem,
                        pos: QPointF) -> str | None:
        """Verbindung von einem Block an einen bestehenden Pfeil (nächster Punkt zu ``pos``)."""
        end = self._edge_endpoint(edge, pos)
        if end is None:
            return None
        return self.connect_endpoints(ConnectionEndpoint(item=source, port=source_port), end)

    def commit_routing_change(self, conn: ConnectionItem, old: dict, new: dict) -> None:
        self.undo_stack.push(SetRoutingCommand(self, conn.connection_id, old, new))

    def reset_routing(self, conn: ConnectionItem) -> None:
        self.prepare_for_command()
        if conn.has_manual_routing():
            self.undo_stack.push(SetRoutingCommand(self, conn.connection_id, conn.data.routing,
                                                   {"mode": "auto"}, text=tr("Linienführung zurücksetzen")))

    # ------------------------------------------------------ Trefferprüfung
    def _view_scale(self) -> float:
        return self.views()[0].transform().m11() if self.views() else 1.0

    def _port_hit(self, pos: QPointF) -> tuple[FlowItem, str] | None:
        # Das oberste Objekt direkt unter dem Mauszeiger hat Vorrang: Eine
        # Beschriftung bleibt anklickbar, und ein Anschluss eines verdeckten
        # Bausteins darf keinen darüberliegenden Baustein „stehlen“.
        for item in self.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder):
            if isinstance(item, (ConnectionLabel, InlineTextEditor)) and item.isVisible():
                return None
            if isinstance(item, FlowItem) and item.isVisible():
                port = item.port_at(pos)
                return (item, port) if port is not None else None
        radius = max(FlowItem.PORT_HIT_RADIUS_PX / max(self._view_scale(), 0.01), 6.0)
        area = QRectF(pos.x() - radius, pos.y() - radius, 2 * radius, 2 * radius)
        candidates = [it for it in self.items(area, Qt.ItemSelectionMode.IntersectsItemBoundingRect,
                                              Qt.SortOrder.DescendingOrder)
                      if isinstance(it, FlowItem) and it.isVisible()]
        for item in candidates:
            port = item.port_at(pos)
            if port is not None:
                return item, port
        return None

    def _element_at(self, pos: QPointF, exclude=None) -> FlowItem | None:
        for item in self.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder):
            if isinstance(item, FlowItem) and item is not exclude:
                return item
        hit = self._port_hit(pos)
        if hit is not None and hit[0] is not exclude:
            return hit[0]
        return None

    def _connection_at(self, pos: QPointF) -> ConnectionItem | None:
        for item in self.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder):
            if isinstance(item, ConnectionItem):
                return item
        return None

    def edge_hit_tolerance(self) -> float:
        """Auswahlzone um Pfeile: komfortabel, aber klein genug für dichte Linien."""
        return min(EDGE_HIT_MAX, max(EDGE_HIT_MIN, EDGE_HIT_PX / max(self._view_scale(), 0.01)))

    def _edge_at(self, pos: QPointF, exclude=()) -> tuple[ConnectionItem, int] | None:
        """Nächstgelegener Pfeil innerhalb der Auswahlzone (nach echter Distanz)."""
        tolerance = self.edge_hit_tolerance()
        area = QRectF(pos.x() - tolerance, pos.y() - tolerance, 2 * tolerance, 2 * tolerance)
        best = None
        for item in self.items(area, Qt.ItemSelectionMode.IntersectsItemBoundingRect):
            if not isinstance(item, ConnectionItem) or item in exclude or item.is_annotation \
                    or item.connection_id not in self._connections:
                continue
            hit = endpoints.nearest_segment(item.points(), pos)
            if hit is not None and hit[0] <= tolerance and (best is None or hit[0] < best[0]):
                best = (hit[0], item, hit[1])
        return (best[1], best[2]) if best is not None else None

    def _edge_endpoint(self, edge: ConnectionItem, pos: QPointF, index: int | None = None) -> ConnectionEndpoint | None:
        points = edge.points()
        if len(points) < 2:
            return None
        if index is None:
            hit = endpoints.nearest_segment(points, pos)
            if hit is None:
                return None
            index = hit[1]
        point, direction = endpoints.anchor_on_edge(points, index, pos, self.snap_value)
        return ConnectionEndpoint(edge=edge, point=point, direction=direction)

    def _endpoint_at(self, pos: QPointF, source: ConnectionEndpoint) -> ConnectionEndpoint | None:
        """Ziel unter dem Mauszeiger: Block/Knoten haben Vorrang vor Pfeilen."""
        exclude_item = source.item if not source.is_edge else None
        item = self._element_at(pos, exclude=exclude_item)
        if item is not None:
            if item.is_junction:
                return ConnectionEndpoint(item=item, port=item.ports[0])
            start = source.scene_pos()
            port = item.port_at(pos) or self._best_target_port(start, source, item, pos)
            return ConnectionEndpoint(item=item, port=port)
        exclude = [source.edge] if source.is_edge else []
        hit = self._edge_at(pos, exclude)
        if hit is None:
            return None
        return self._edge_endpoint(hit[0], pos, hit[1])

    def _best_target_port(self, start: QPointF, source: ConnectionEndpoint, target: FlowItem,
                          pos: QPointF) -> str:
        """Wählt beim Loslassen auf dem Baustein einen passenden Zielanschluss.

        Nähe zum Mauszeiger und zur Quelle entscheiden; Anschlüsse, von denen
        bereits ein Ausgang des Ziels abgeht, werden gemieden, damit sich ein-
        und ausgehende Linien nicht überlagern.
        """
        outgoing = self._outgoing_ports(target)
        source_is_comment = not source.is_edge and source.item.is_comment

        def score(port: str) -> float:
            p = target.port_scene_pos(port)
            value = math.hypot(p.x() - pos.x(), p.y() - pos.y()) + 0.35 * math.hypot(p.x() - start.x(),
                                                                                    p.y() - start.y())
            if port in outgoing and not source_is_comment and not target.is_comment:
                value += 1000.0
            return value
        return min(target.ports, key=score)

    # ------------------------------------------------------ Verbinden ziehen
    def _set_endpoint_highlight(self, end: ConnectionEndpoint | None, on: bool, port: str | None = None) -> None:
        if end is None:
            return
        if end.is_edge:
            if end.edge.scene() is self:
                end.edge.set_drop_highlight(on)
        elif end.item.scene() is self:
            end.item.set_ports_highlighted(on, port if on else None)

    def _begin_connection_drag(self, item: FlowItem, port: str, pos: QPointF) -> None:
        self._begin_endpoint_drag(ConnectionEndpoint(item=item, port=port), pos)
        if not item.isSelected():
            self.select_items([item])

    def _begin_edge_drag(self, edge: ConnectionItem, pos: QPointF, index: int | None = None) -> bool:
        """Verbindung an einem bestehenden Pfeil beginnen (Umschalt + Ziehen)."""
        end = self._edge_endpoint(edge, pos, index)
        if end is None:
            return False
        self._begin_endpoint_drag(end, pos)
        return True

    def _begin_endpoint_drag(self, source: ConnectionEndpoint, pos: QPointF) -> None:
        self._hide_edge_marker()
        self._connect_drag = {"source": source, "target": None, "source_port": source.port,
                              "target_port": None, "error": None, "warning": None}
        self._temp_connection = TempConnectionItem()
        self.addItem(self._temp_connection)
        self._set_endpoint_highlight(source, True, source.port)
        self._update_connection_drag(pos)

    def _update_connection_drag(self, pos: QPointF) -> None:
        drag = self._connect_drag
        source: ConnectionEndpoint = drag["source"]
        target = self._endpoint_at(pos, source)
        previous: ConnectionEndpoint | None = drag["target"]
        if previous is not None and not previous.same_target(target):
            self._set_endpoint_highlight(previous, False)

        error = warning = None
        markers = [source.point] if source.is_edge else []
        start = source.scene_pos()
        if target is not None:
            source_port, target_port = self._resolve_ports(source, target)
            error = self._blocking_error(source, target, source_port, target_port)
            if error is None:
                warning = self._preview_warning(source, target, source_port, target_port)
            self._set_endpoint_highlight(target, True, target_port)
            end = target.scene_pos()
            if target.is_edge:
                markers.append(target.point)
        else:
            if source.is_edge:
                source_port = endpoints.branch_port(source.direction, source.point, pos)
            elif source.item.is_junction:
                source_port = self._effective_source_port(source.item, source.port, None, None, pos)
            else:
                source_port = source.port
            target_port = None
            end = pos
        if not source.is_edge:
            self._set_endpoint_highlight(source, True, source_port)
        start = source.point if source.is_edge else source.item.port_scene_pos(source_port)
        drag.update(target=target, source_port=source_port, target_port=target_port, error=error,
                    warning=warning)

        source_rect = None
        if not source.is_edge and not source.item.is_junction:
            source_rect = rect_from_qrect(source.item.scene_rect())
        target_rect = None
        if target is not None and not target.is_edge and not target.item.is_junction:
            target_rect = rect_from_qrect(target.item.scene_rect())
        points = routing.route((start.x(), start.y()), source_port, (end.x(), end.y()), target_port,
                               source_rect, target_rect)
        state = STATE_BLOCKED if error else (STATE_WARNING if warning else STATE_OK)
        if self._temp_connection is not None:
            self._temp_connection.set_points(points, state, markers)
        if error:
            self.status_message.emit(tr("Nicht möglich: {error}", error=error))
        elif warning:
            self.status_message.emit(tr("Hinweis: {warning} Die Verbindung kann trotzdem erstellt werden.",
                                        warning=warning))
        elif target is not None and target.is_edge:
            self.status_message.emit(tr("Loslassen, um die Verbindung an diesem Pfeil anzuschließen."))
        else:
            self.status_message.emit("")

    def _finish_connection_drag(self) -> None:
        drag = self._connect_drag
        self._cleanup_connection_drag()
        if drag is None or drag["target"] is None:
            return
        if drag["error"]:
            self.status_message.emit(tr("Nicht möglich: {error}", error=drag["error"]))
            return
        source: ConnectionEndpoint = drag["source"]
        target: ConnectionEndpoint = drag["target"]
        if not source.is_edge:
            source = ConnectionEndpoint(item=source.item, port=drag["source_port"])
        if not target.is_edge:
            target = ConnectionEndpoint(item=target.item, port=drag["target_port"])
        self.connect_endpoints(source, target)

    def _cancel_connection_drag(self) -> None:
        self._cleanup_connection_drag()
        self.status_message.emit(tr("Verbinden abgebrochen."))

    def _cleanup_connection_drag(self) -> None:
        drag = self._connect_drag
        self._connect_drag = None
        if drag is not None:
            self._set_endpoint_highlight(drag["source"], False)
            self._set_endpoint_highlight(drag["target"], False)
        if self._temp_connection is not None:
            if self._temp_connection.scene() is self:
                self.removeItem(self._temp_connection)
            self._temp_connection = None

    @property
    def is_connecting(self) -> bool:
        return self._connect_drag is not None

    # Hinweis beim Überfahren eines Pfeils mit gedrückter Umschalttaste
    def _show_edge_marker(self, point: QPointF | None) -> None:
        if point is None:
            self._hide_edge_marker()
            return
        if self._hover_edge_marker is None:
            self._hover_edge_marker = AnchorMarker()
            self.addItem(self._hover_edge_marker)
        self._hover_edge_marker.setPos(point)
        self._hover_edge_marker.setVisible(True)

    def _hide_edge_marker(self) -> None:
        if self._hover_edge_marker is not None:
            self._hover_edge_marker.setVisible(False)

    # ======================================================= Drop-Vorschau
    def update_drop_preview(self, element_type: ElementType, pos: QPointF) -> None:
        element_type = ElementType(element_type)
        if self._ghost is None or self._ghost.element_type is not element_type:
            self.clear_drop_preview()
            self._ghost = GhostItem(element_type)
            self.addItem(self._ghost)
        target = self._drop_target_connection(element_type, pos)
        point = self.snap_point(pos)
        if target is not None:
            point, _axis = self._align_to_segment(target, pos, point)
        if self._drop_connection is not target:
            if self._drop_connection is not None:
                self._drop_connection.set_drop_highlight(False)
            if target is not None:
                target.set_drop_highlight(True)
            self._drop_connection = target
        self._ghost.setPos(self.clamp_point(point))

    def _drop_target_connection(self, element_type: ElementType, pos: QPointF) -> ConnectionItem | None:
        if element_type not in INSERTABLE_TYPES:
            return None
        conn = self._connection_at(pos)
        if conn is None or conn.is_annotation:
            return None
        return conn

    def _align_to_segment(self, conn: ConnectionItem, pos: QPointF, point: QPointF) -> tuple[QPointF, str]:
        """Richtet den neuen Baustein am getroffenen Liniensegment aus.

        Gibt den (eingerasteten) Punkt und die Flussachse zurück: ``"y"`` für
        ein senkrechtes Segment (Baustein übernimmt die Spalte), sonst ``"x"``.
        """
        points = conn.points()
        best, best_dist = None, float("inf")
        for a, b in zip(points[:-1], points[1:]):
            # Abstand Punkt–Segment
            cx = min(max(pos.x(), min(a[0], b[0])), max(a[0], b[0]))
            cy = min(max(pos.y(), min(a[1], b[1])), max(a[1], b[1]))
            dist = math.hypot(pos.x() - cx, pos.y() - cy)
            if dist < best_dist:
                best, best_dist = (a, b), dist
        if best is None:
            return point, "y"
        a, b = best
        if abs(a[0] - b[0]) < 1e-6:  # senkrechtes Segment: Spalte übernehmen
            return QPointF(self.snap_value(a[0]), point.y()), "y"
        return QPointF(point.x(), self.snap_value(a[1])), "x"

    def clear_drop_preview(self) -> None:
        if self._ghost is not None:
            if self._ghost.scene() is self:
                self.removeItem(self._ghost)
            self._ghost = None
        if self._drop_connection is not None:
            self._drop_connection.set_drop_highlight(False)
            self._drop_connection = None

    def drop_element(self, element_type: ElementType, pos: QPointF) -> str | None:
        element_type = ElementType(element_type)
        target = self._drop_target_connection(element_type, pos)
        point = self.snap_point(pos)
        axis = None
        if target is not None:
            point, axis = self._align_to_segment(target, pos, point)
        self.clear_drop_preview()
        return self.insert_element(element_type, point, snap=False, into_connection=target, flow_axis=axis)

    # ======================================================= Inline-Bearbeitung
    @property
    def is_editing(self) -> bool:
        return self._editor is not None

    def begin_element_edit(self, item: FlowItem, initial_text: str | None = None,
                           select_all: bool = False) -> None:
        if item.scene() is not self or item.is_junction:
            return
        self.commit_edit()
        self.select_items([item])
        center, width, alignment = item.text_layout_info()
        editor = InlineTextEditor(shared_item_font(), width, alignment,
                                  self._on_editor_changed, self._on_editor_finished)
        self._edit_state = {"kind": "element", "item": item, "original": item.data.text}
        self._editor = editor
        self.addItem(editor)
        item.set_editing(True)
        text = item.data.text if initial_text is None else initial_text
        editor.set_initial_text(text, select_all and initial_text is None)
        if initial_text is not None:
            item.set_preview_text(initial_text)
        self._position_editor()
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.editing_changed.emit(True)

    def begin_label_edit(self, conn: ConnectionItem) -> None:
        if conn.scene() is not self:
            return
        if conn.is_annotation:
            self.status_message.emit(tr("Kommentarlinien besitzen keine Beschriftung."))
            return
        self.commit_edit()
        self.select_items([conn])
        editor = InlineTextEditor(label_font(), LABEL_EDIT_WIDTH, Qt.AlignmentFlag.AlignLeft,
                                  self._on_editor_changed, self._on_editor_finished)
        self._edit_state = {"kind": "label", "connection": conn, "original": conn.data.label}
        self._editor = editor
        self.addItem(editor)
        conn.label.set_editing(True)
        conn.label.set_text(conn.data.label)
        editor.set_initial_text(conn.data.label, True)
        self._position_editor()
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.editing_changed.emit(True)

    def _position_editor(self) -> None:
        editor, state = self._editor, self._edit_state
        if editor is None or state is None:
            return
        if state["kind"] == "element":
            item = state["item"]
            center, width, _ = item.text_layout_info()
            scene_center = item.mapToScene(center)
            editor.setPos(scene_center.x() - width / 2, scene_center.y() - editor.content_height() / 2)
        else:
            label = state["connection"].label
            editor.setPos(label.scenePos() + QPointF(label.PAD_X, label.PAD_Y))

    def _on_editor_changed(self, text: str) -> None:
        state = self._edit_state
        if state is None:
            return
        if state["kind"] == "element":
            state["item"].set_preview_text(text.replace(" ", "\n").replace(" ", "\n"))
        else:
            state["connection"].label.set_text(text.replace(" ", "\n").replace(" ", "\n"))
        self._position_editor()

    def _on_editor_finished(self, commit: bool, text: str) -> None:
        state, editor = self._edit_state, self._editor
        self._edit_state = None
        self._editor = None
        if editor is not None and editor.scene() is self:
            self.removeItem(editor)
        if state is None:
            return
        if state["kind"] == "element":
            item = state["item"]
            item.set_editing(False)
            item.set_preview_text(None)
            if commit and text != state["original"] and item.scene() is self:
                self.undo_stack.push(EditTextCommand(self, item.element_id, state["original"], text))
        else:
            conn = state["connection"]
            conn.label.set_editing(False)
            conn.label.set_text(conn.data.label)
            text = text.strip()
            if commit and text != state["original"] and conn.scene() is self:
                self.undo_stack.push(EditLabelCommand(self, conn.connection_id, state["original"], text))
        self.editing_changed.emit(False)
        for view in self.views():
            view.setFocus(Qt.FocusReason.OtherFocusReason)

    def commit_edit(self) -> None:
        if self._editor is not None:
            self._editor.finish(True)

    def cancel_edit(self) -> None:
        if self._editor is not None:
            self._editor.finish(False)

    # ================================================================ Maus
    def mousePressEvent(self, event) -> None:
        pos = event.scenePos()
        if self._editor is not None and self._editor not in self.items(pos):
            self.commit_edit()
        if event.button() == Qt.MouseButton.LeftButton and self._editor is None:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            hit = self._port_hit(pos)
            if hit is not None and not ctrl:
                self._begin_connection_drag(hit[0], hit[1], pos)
                event.accept()
                return
            if shift and not ctrl:
                # Umschalt + Ziehen auf einem Pfeil: neue Verbindung an diesem Pfeil beginnen
                edge = self._edge_at(pos)
                if edge is not None and self._element_at(pos) is None \
                        and self._begin_edge_drag(edge[0], pos, edge[1]):
                    event.accept()
                    return
        super().mousePressEvent(event)
        self._track_item_drag(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # Auch der zweite Klick eines Doppelklicks kann ein Ziehen einleiten;
        # es wird ebenso eingerastet und als Undo-Schritt erfasst.
        super().mouseDoubleClickEvent(event)
        self._track_item_drag(event)

    def _track_item_drag(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and isinstance(self.mouseGrabberItem(), FlowItem):
            self._drag_move_active = True
            self._move_start = {it.element_id: (it.pos().x(), it.pos().y()) for it in self.selected_elements()}

    def mouseMoveEvent(self, event) -> None:
        if self._connect_drag is not None:
            self._update_connection_drag(event.scenePos())
            event.accept()
            return
        # Alle Positionsänderungen eines Mausschritts gemeinsam behandeln: jede
        # Verbindung wird höchstens einmal aktualisiert, Verbindungen zwischen
        # zwei mitbewegten Bausteinen werden nur verschoben statt neu berechnet.
        with self.batch_routing():
            super().mouseMoveEvent(event)
        if event.buttons() == Qt.MouseButton.NoButton:
            self._update_port_hover(event.scenePos(), event.modifiers())

    def mouseReleaseEvent(self, event) -> None:
        if self._connect_drag is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish_connection_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._drag_move_active:
            self._drag_move_active = False
            self._finish_interactive_move()

    def _finish_interactive_move(self) -> None:
        moves = {}
        for eid, old in self._move_start.items():
            item = self.element(eid)
            if item is None:
                continue
            new = (item.pos().x(), item.pos().y())
            if abs(new[0] - old[0]) > 1e-6 or abs(new[1] - old[1]) > 1e-6:
                moves[eid] = (old, new)
        self._move_start = {}
        if moves:
            count = len(moves)
            # Der Befehl führt beim Ablegen auch die Linien um alte und neue
            # Positionen herum neu.
            self.undo_stack.push(MoveItemsCommand(
                self, moves,
                text=tr("Verschieben") if count == 1 else tr("{count} Bausteine verschieben", count=count)))

    def _update_port_hover(self, pos: QPointF, modifiers=None) -> None:
        hit = self._port_hit(pos)
        item, port = hit if hit is not None else (None, None)
        if self._hover_port_item is not None and self._hover_port_item is not item:
            self._hover_port_item.set_hover_port(None)
        self._hover_port_item = item
        if item is not None:
            item.set_hover_port(port)
        # Mit Umschalt zeigt ein Marker, wo an einem Pfeil angesetzt würde
        if modifiers is None:
            modifiers = QGuiApplication.queryKeyboardModifiers()
        marker = None
        if item is None and modifiers & Qt.KeyboardModifier.ShiftModifier and self._element_at(pos) is None:
            edge = self._edge_at(pos)
            if edge is not None:
                end = self._edge_endpoint(edge[0], pos, edge[1])
                marker = end.point if end is not None else None
        self._show_edge_marker(marker)

    # ============================================================== Tastatur
    def keyPressEvent(self, event) -> None:
        if self._editor is not None or self.focusItem() is not None:
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        ctrl_alt = mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)

        if key == Qt.Key.Key_Escape:
            self.handle_escape()
            event.accept()
            return

        arrows = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1),
                  Qt.Key.Key_Down: (0, 1)}
        if key in arrows and self.selected_elements() and not ctrl_alt:
            step = self.grid_size if self.settings.snap_to_grid else 1
            if mods & Qt.KeyboardModifier.ShiftModifier:
                step *= 5
            dx, dy = arrows[key]
            self.move_selection_by(dx * step, dy * step)
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2) and not ctrl_alt:
            if self.single_selected is not None:
                self.begin_element_edit(self.single_selected, select_all=True)
                event.accept()
                return
            conns = self.selected_connections()
            if len(conns) == 1 and len(self.selectedItems()) == 1:
                self.begin_label_edit(conns[0])
                event.accept()
                return

        text = event.text()
        # AltGr erscheint unter Windows als Strg+Alt – solche Zeichen (@ { [ \ € ~)
        # sind normale Texteingabe.
        altgr = bool(mods & Qt.KeyboardModifier.ControlModifier) and bool(mods & Qt.KeyboardModifier.AltModifier)
        if text and text.isprintable() and not text.isspace() and (not ctrl_alt or altgr) \
                and self.single_selected is not None:
            self.begin_element_edit(self.single_selected, initial_text=text)
            event.accept()
            return
        super().keyPressEvent(event)
