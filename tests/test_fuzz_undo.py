"""Zufallstest: gemischte Operationen, Invarianten, vollständiges Undo/Redo, Speichern/Laden."""

import random

import pytest
from PySide6.QtCore import QPointF

from app import alignment, clipboard
from app.connections.connection import ConnectionItem
from app.document import DiagramDocument
from app.items.base_item import FlowItem
from app.connections.endpoints import ConnectionEndpoint
from app.model import rules
from app.model.element_types import TRUNK_IN_KEY, TRUNK_OUT_KEY, ElementType

TYPES = [ElementType.START, ElementType.END, ElementType.INPUT, ElementType.OUTPUT, ElementType.PROCESS,
         ElementType.SUBPROGRAM, ElementType.DECISION, ElementType.LOOP, ElementType.COMMENT]


def snapshot(scene):
    elements = sorted((e.id, e.type.value, round(e.x, 3), round(e.y, 3), e.text, e.z,
                       tuple(sorted(e.properties.items()))) for e in scene.element_data())
    connections = sorted((c.id, c.source_id, c.target_id, c.source_port, c.target_port, c.label,
                          tuple(sorted((k, round(v, 3) if isinstance(v, float) else v)
                                       for k, v in c.routing.items())))
                         for c in scene.connection_data())
    return elements, connections


def check_invariants(scene):
    items = [it for it in scene.items() if isinstance(it, FlowItem)]
    conns = [it for it in scene.items() if isinstance(it, ConnectionItem)]
    assert {it.element_id for it in items} == set(scene._elements)
    assert {c.connection_id for c in conns} == set(scene._connections)
    for item in items:
        assert (item.data.x, item.data.y) == (item.pos().x(), item.pos().y())
        assert (item.data.width, item.data.height) == (item.width, item.height)
        for conn in item.connections:
            assert conn.scene() is scene
    for conn in conns:
        assert conn.source.scene() is scene and conn.target.scene() is scene
        assert conn in conn.source.connections and conn in conn.target.connections
        points = conn.points()
        s = conn.source.port_scene_pos(conn.data.source_port)
        t = conn.target.port_scene_pos(conn.data.target_port)
        assert points[0] == pytest.approx((s.x(), s.y()))
        assert points[-1] == pytest.approx((t.x(), t.y()))
    # Warnungen entsprechen jederzeit der fachlichen Bewertung
    expected = rules.evaluate_connections([scene._connection_info(c) for c in scene.ordered_connections()])
    assert scene.connection_warnings() == expected
    # Stamm-Verweise von Verbindungspunkten sind konsistent, sofern vorhanden
    for item in items:
        if item.is_junction:
            trunk_in = scene.connection(item.data.properties.get(TRUNK_IN_KEY, ""))
            trunk_out = scene.connection(item.data.properties.get(TRUNK_OUT_KEY, ""))
            assert trunk_in is None or trunk_in.target is item
            assert trunk_out is None or trunk_out.source is item


def random_operation(rng, scene):
    elements = scene.elements()
    connections = scene.connections()
    op = rng.choice(["add", "add", "add", "connect", "connect", "move", "text", "label", "delete", "paste",
                     "insert", "align", "z", "loop", "routing", "smart", "edge", "edge", "edge_start"])
    if op == "add" or not elements:
        scene.insert_element(rng.choice(TYPES), QPointF(rng.randint(-20, 20) * 40, rng.randint(-20, 20) * 40))
    elif op == "connect" and len(elements) >= 2:
        a, b = rng.sample(elements, 2)
        scene.create_connection(a, rng.choice(a.ports), b, rng.choice(b.ports))
    elif op == "move":
        chosen = rng.sample(elements, min(len(elements), rng.randint(1, 4)))
        dx, dy = rng.randint(-5, 5) * 20, rng.randint(-5, 5) * 20
        scene.apply_moves({it.element_id: ((it.pos().x(), it.pos().y()), (it.pos().x() + dx, it.pos().y() + dy))
                           for it in chosen}, "m")
    elif op == "text" and any(not e.is_junction for e in elements):
        item = rng.choice([e for e in elements if not e.is_junction])
        scene.begin_element_edit(item, select_all=True)
        scene._editor.setPlainText(rng.choice(["x = 1", "Berechne\nMittelwert", "", "Ein längerer Text " * 4]))
        scene.commit_edit()
    elif op == "label" and connections:
        conn = rng.choice(connections)
        if not conn.is_annotation:
            scene.begin_label_edit(conn)
            scene._editor.setPlainText(rng.choice(["ja", "nein", "", "i < n"]))
            scene.commit_edit()
    elif op == "delete":
        chosen = rng.sample(elements, min(len(elements), rng.randint(1, 3)))
        scene.select_items(chosen + rng.sample(connections, min(len(connections), rng.randint(0, 2))))
        scene.delete_selection()
    elif op == "paste":
        scene.select_items(rng.sample(elements, min(len(elements), rng.randint(1, 4))))
        payload = clipboard.selection_payload(scene)
        if payload:
            clipboard.paste_payload(scene, payload, offset=QPointF(rng.randint(1, 6) * 40, rng.randint(1, 6) * 40))
    elif op == "insert" and connections:
        conn = rng.choice(connections)
        if not conn.is_annotation:
            a, b = conn.points()[0], conn.points()[-1]
            scene.drop_element(rng.choice([ElementType.PROCESS, ElementType.DECISION, ElementType.LOOP]),
                               QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    elif op == "align" and len(elements) >= 3:
        chosen = rng.sample(elements, 3)
        mode = rng.choice([alignment.ALIGN_LEFT, alignment.ALIGN_TOP, alignment.ALIGN_CENTER_X,
                           alignment.DISTRIBUTE_V])
        scene.apply_moves(alignment.compute_moves(chosen, mode, snap_value=scene.snap_value), "a")
    elif op == "z":
        scene.select_items(rng.sample(elements, 1))
        scene.bring_to_front() if rng.random() < 0.5 else scene.send_to_back()
    elif op == "loop":
        loops = [e for e in elements if e.element_type is ElementType.LOOP]
        if loops:
            scene.toggle_loop_part(rng.choice(loops))
    elif op == "routing" and connections:
        conn = rng.choice(connections)
        old = dict(conn.data.routing)
        conn.data.routing = {"mode": "manual", "axis": rng.choice("xy"), "value": float(rng.randint(-10, 10) * 20)}
        conn.update_route()
        scene.commit_routing_change(conn, old, dict(conn.data.routing))
    elif op in ("edge", "edge_start") and connections:
        flows = [conn for conn in connections if not conn.is_annotation and len(conn.points()) >= 2]
        others = [e for e in elements if not e.is_junction]
        if flows and others:
            host = rng.choice(flows)
            a, b = host.points()[0], host.points()[-1]
            end = scene._edge_endpoint(host, QPointF((a[0] + b[0]) / 2 + rng.randint(-20, 20),
                                                     (a[1] + b[1]) / 2 + rng.randint(-20, 20)))
            item = rng.choice(others)
            block = ConnectionEndpoint(item=item, port=rng.choice(item.ports))
            if rng.random() < 0.2 and len(flows) >= 2:
                other_host = rng.choice([conn for conn in flows if conn is not host])
                p = other_host.points()[len(other_host.points()) // 2]
                scene.connect_endpoints(end, scene._edge_endpoint(other_host, QPointF(*p)))
            elif op == "edge":
                scene.connect_endpoints(block, end)
            else:
                scene.connect_endpoints(end, block)
    elif op == "smart":
        scene.select_items(rng.sample(elements, 1))
        scene.insert_element_smart(rng.choice(TYPES), QPointF(0, 0))


@pytest.mark.parametrize("seed", range(12))
def test_random_operations_undo_redo_and_roundtrip(qapp, seed, tmp_path):
    rng = random.Random(seed)
    document = DiagramDocument()
    scene = document.scene
    stack = document.undo_stack
    initial = snapshot(scene)
    states = [initial]
    for _ in range(60):
        before = stack.index()
        random_operation(rng, scene)
        check_invariants(scene)
        if stack.index() != before:
            states.append(snapshot(scene))
    final = snapshot(scene)

    # vollständig rückgängig – jeder Zwischenstand muss exakt wieder erreicht werden
    for expected in reversed(states[:-1]):
        stack.undo()
        check_invariants(scene)
        assert snapshot(scene) == expected
    assert snapshot(scene) == initial
    # vollständig wiederholen
    while stack.canRedo():
        stack.redo()
        check_invariants(scene)
    assert snapshot(scene) == final

    # Speichern und Laden ergibt dasselbe Modell
    path = tmp_path / f"fuzz{seed}.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == []
    assert snapshot(reopened.scene) == final
    check_invariants(reopened.scene)
    scene.clear_diagram()
    reopened.scene.clear_diagram()
