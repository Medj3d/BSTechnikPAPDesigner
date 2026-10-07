"""Regressionstests für Befunde aus dem Code-Review."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest

from app import clipboard
from app.connections import routing
from app.model.element_types import ElementType
from tests.conftest import add, connect


def vp(view, scene_point):
    return view.mapFromScene(scene_point)


def crosses_any(points, rect):
    r = routing.Rect(rect.left(), rect.top(), rect.right(), rect.bottom())
    return any(routing.segment_crosses_rect(a, b, r) for a, b in zip(points, points[1:]))


def test_ctrl_drag_of_unselected_item_is_undoable(view, scene, document, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 300, 0)
    scene.select_items([a])
    document.undo_stack.setClean()
    start = vp(view, b.pos())
    ctrl = Qt.KeyboardModifier.ControlModifier
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, ctrl, start)
    QTest.mouseMove(view.viewport(), start + QPoint(60, 80))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, ctrl, start + QPoint(60, 80))
    qapp.processEvents()
    assert b.pos() != QPointF(300, 0)
    assert document.is_modified
    document.undo_stack.undo()
    assert b.pos() == QPointF(300, 0)
    assert a.pos() == QPointF(0, 0)


def test_group_drag_translates_internal_connections(view, scene, qapp, monkeypatch):
    items = [add(scene, ElementType.PROCESS, 0, y * 120) for y in range(8)]
    for upper, lower in zip(items, items[1:]):
        connect(scene, upper, "bottom", lower, "top")
    scene.select_all()
    calls = []
    original = routing.route
    monkeypatch.setattr(routing, "route", lambda *a, **k: calls.append(1) or original(*a, **k))
    start = vp(view, items[0].pos())
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), start + QPoint(40, 20))
    QTest.mouseMove(view.viewport(), start + QPoint(80, 40))
    assert calls == []  # nur verschoben, nicht neu berechnet
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       start + QPoint(80, 40))
    for conn in scene.connections():
        s = conn.source.port_scene_pos(conn.data.source_port)
        assert conn.points()[0] == (s.x(), s.y())


def test_group_drag_keeps_relative_layout_on_half_grid_steps(view, scene, qapp):
    # Versatz von genau einem halben Rasterfeld: alle Bausteine müssen gleich einrasten
    view.set_zoom(0.5)
    view.centerOn(QPointF(0, 140))
    qapp.processEvents()
    items = [add(scene, ElementType.PROCESS, 0, y) for y in (0, 140, 280)]
    scene.select_all()
    start = vp(view, items[1].pos())
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), start + QPoint(5, 5))  # = 10 Szeneneinheiten
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       start + QPoint(5, 5))
    ys = [it.pos().y() for it in items]
    assert ys[1] - ys[0] == 140 and ys[2] - ys[1] == 140


def test_snap_rounds_half_up_consistently(scene):
    from app.scene import snap_to
    assert [snap_to(v, 20) for v in (10, 30, 50, -10, -30)] == [20, 40, 60, 0, -20]


def test_manual_axis_moves_with_both_endpoints(scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    p = add(scene, ElementType.PROCESS, 240, 200)
    conn = connect(scene, d, "bottom", p, "top")
    conn.set_routing({"mode": "manual", "axis": "y", "value": 140})
    scene.apply_moves({d.element_id: ((0, 0), (300, 200)), p.element_id: ((240, 200), (540, 400))}, "m")
    assert conn.data.routing["value"] == 340
    assert not crosses_any(conn.points(), d.scene_rect())


def test_manual_axis_crossing_endpoint_falls_back_to_auto(scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    p = add(scene, ElementType.PROCESS, 240, 200)
    conn = connect(scene, d, "bottom", p, "top")
    conn.set_routing({"mode": "manual", "axis": "y", "value": -40})  # mitten durch die Quelle
    assert not crosses_any(conn.points(), d.scene_rect())


def test_paste_translates_manual_axis(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 240, 200)
    conn = connect(scene, a, "bottom", b, "top")
    conn.set_routing({"mode": "manual", "axis": "y", "value": 120})
    scene.select_items([a, b])
    clipboard.copy_selection(scene)
    clipboard.paste_payload(scene, clipboard.clipboard_payload(), offset=QPointF(0, 400))
    pasted = [c for c in scene.connections() if c is not conn][0]
    assert pasted.data.routing["value"] == 520


def test_new_element_on_line_causes_reroute(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    c = add(scene, ElementType.PROCESS, 0, 400)
    conn = connect(scene, a, "bottom", c, "top")
    b = add(scene, ElementType.SUBPROGRAM, 0, 200)
    assert not crosses_any(conn.points(), b.scene_rect())
    scene.select_items([b])
    scene.delete_selection()
    assert len(conn.points()) == 2  # Umweg wieder entfernt


def test_growing_text_reroutes_neighbouring_lines(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    c = add(scene, ElementType.PROCESS, 0, 400)
    conn = connect(scene, a, "bottom", c, "top")
    b = add(scene, ElementType.PROCESS, 300, 200)
    b.set_text("\n".join(["sehr breiter Text in dieser Zeile"] * 8))
    assert not crosses_any(conn.points(), b.scene_rect())


def test_insert_into_connection_makes_room(scene, document):
    start = add(scene, ElementType.START, 0, 0)
    scene.select_items([start])
    process = scene.element(scene.insert_element_smart(ElementType.PROCESS, QPointF(0, 0)))
    conn = [c for c in scene.connections()][0]
    before = process.pos()
    mid = conn.points()[0][1] / 2 + conn.points()[-1][1] / 2
    new = scene.element(scene.drop_element(ElementType.PROCESS, QPointF(0, mid)))
    assert not new.scene_rect().intersects(process.scene_rect())
    assert not new.scene_rect().intersects(start.scene_rect())
    for c in scene.connections():
        assert routing.path_length(c.points()) >= 20
    document.undo_stack.undo()
    assert process.pos() == before and scene.element(new.element_id) is None


def test_insert_loop_into_connection_makes_room(scene):
    start = add(scene, ElementType.START, 0, 0)
    scene.select_items([start])
    process = scene.element(scene.insert_element_smart(ElementType.PROCESS, QPointF(0, 0)))
    conn = scene.connections()[0]
    scene.drop_element(ElementType.LOOP, QPointF(0, 70))
    rects = [e.scene_rect() for e in scene.elements()]
    for i, r in enumerate(rects):
        for other in rects[i + 1:]:
            assert not r.intersects(other)
    assert conn.scene() is None
    for c in scene.connections():
        for item in scene.elements():
            if item not in (c.source, c.target):
                assert not crosses_any(c.points(), item.scene_rect())
    assert process.pos().y() > 120


def test_port_hit_leaves_centre_free_at_low_zoom(view, scene):
    item = add(scene, ElementType.PROCESS, 0, 0)
    start = add(scene, ElementType.START, 0, -200)
    view.set_zoom(0.25)
    assert item.port_at(item.pos()) is None
    assert start.port_at(start.pos()) is None
    assert item.port_at(item.port_scene_pos("bottom")) == "bottom"


def test_drop_on_horizontal_segment_is_snapped(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 200, 240)
    conn = connect(scene, a, "bottom", b, "top")
    horizontal = [(p, q) for p, q in zip(conn.points(), conn.points()[1:]) if p[1] == q[1] and p[0] != q[0]]
    assert horizontal
    (x1, y), (x2, _) = horizontal[0]
    new = scene.element(scene.drop_element(ElementType.PROCESS, QPointF((x1 + x2) / 2, y)))
    assert new.pos().x() % 20 == 0 and new.pos().y() % 20 == 0


def test_second_decision_exit_uses_free_port(scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    p1 = add(scene, ElementType.PROCESS, 0, 240)
    p2 = add(scene, ElementType.PROCESS, 300, 240)
    c1 = connect(scene, d, "bottom", p1, "top")
    c2 = connect(scene, d, "bottom", p2, "top")
    assert c1.data.source_port == "bottom"
    assert c2.data.source_port == "right"
    assert c1.label.scenePos() != c2.label.scenePos()


def test_back_edge_avoids_outgoing_port(scene):
    p0 = add(scene, ElementType.PROCESS, 0, 0)
    d = add(scene, ElementType.DECISION, 0, 200)
    connect(scene, p0, "bottom", d, "top")
    from app.connections.endpoints import ConnectionEndpoint
    port = scene._best_target_port(d.port_scene_pos("left"), ConnectionEndpoint(item=d, port="left"), p0,
                                   QPointF(-30, 5))
    assert port != "bottom"


def test_touchpad_zoom_does_not_drift(view):
    pos = QPointF(300, 200)
    before = view.mapToScene(pos.toPoint())
    for _ in range(120):
        event = QWheelEvent(pos, view.viewport().mapToGlobal(pos), QPoint(0, 0), QPoint(0, 12),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        view.wheelEvent(event)
    after = view.mapToScene(pos.toPoint())
    assert abs(after.x() - before.x()) < 2 and abs(after.y() - before.y()) < 2
