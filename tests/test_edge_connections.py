"""Akzeptanztests: Warnungen statt Sperre, Verbindungen an bestehende Pfeile."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from app import clipboard
from app.connections import routing
from app.document import DiagramDocument
from app.model.element_types import TRUNK_IN_KEY, TRUNK_OUT_KEY, ElementType
from tests.conftest import add, connect

LEFT = Qt.MouseButton.LeftButton
NONE = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def vp(view, point):
    return view.mapFromScene(point)


def drag(view, start: QPointF, end: QPointF, modifiers=NONE, steps=4):
    """Zieht mit der linken Maustaste von ``start`` nach ``end`` (Szenenkoordinaten)."""
    a, b = vp(view, start), vp(view, end)
    QTest.mouseMove(view.viewport(), a)
    QTest.mousePress(view.viewport(), LEFT, modifiers, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(view.viewport(), a + (b - a) * i / steps)
    QTest.mouseRelease(view.viewport(), LEFT, modifiers, b)


def junctions(scene):
    return [e for e in scene.elements() if e.element_type is ElementType.JUNCTION]


def conn_between(scene, source, target):
    found = [c for c in scene.connections() if c.source is source and c.target is target]
    return found[0] if found else None


def point_on_polyline(points, x, y):
    return any(routing.segment_crosses_rect(a, b, routing.Rect(x - 1, y - 1, x + 1, y + 1))
               or (abs(a[0] - x) < 1e-6 and abs(a[1] - y) < 1e-6) for a, b in zip(points, points[1:]))


# --------------------------------------------------------------- Test 1 / 6
def test_1_problematic_second_connection_is_created_and_red(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    c = add(scene, ElementType.PROCESS, 300, 200)
    first = connect(scene, a, "bottom", b, "top")
    assert first.warning is None
    # zweite Verbindung vom Vorgang A (nur ein Ausgang vorgesehen) per Maus ziehen
    drag(view, a.port_scene_pos("right"), c.pos())
    qapp.processEvents()
    second = conn_between(scene, a, c)
    assert second is not None, "problematische Verbindung muss trotzdem erstellt werden"
    assert second.warning, "problematische Verbindung muss als Warnung markiert sein"
    assert first.warning is None
    # gleiche Richtung A → B noch einmal: ebenfalls erlaubt, aber rot
    drag(view, a.port_scene_pos("left"), b.pos() + QPointF(-40, 0))
    duplicates = [conn for conn in scene.connections() if conn.source is a and conn.target is b]
    assert len(duplicates) == 2 and duplicates[1].warning


def test_6_red_connection_survives_save_and_reload(scene, document, tmp_path):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    c = add(scene, ElementType.PROCESS, 300, 200)
    connect(scene, a, "bottom", b, "top")
    red = connect(scene, a, "right", c, "top")
    assert red.warning
    path = tmp_path / "rot.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    restored = reopened.scene.connection(red.connection_id)
    assert restored is not None and restored.warning
    others = [conn for conn in reopened.scene.connections() if conn is not restored]
    assert all(conn.warning is None for conn in others)
    reopened.scene.clear_diagram()


def test_warning_clears_when_conflict_disappears(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    c = add(scene, ElementType.PROCESS, 300, 200)
    first = connect(scene, a, "bottom", b, "top")
    second = connect(scene, a, "right", c, "top")
    assert second.warning
    scene.select_items([first])
    scene.delete_selection()
    assert second.warning is None
    document.undo_stack.undo()
    assert first.warning is None and second.warning


def test_warning_stays_on_the_later_connection_after_split(scene):
    p = add(scene, ElementType.PROCESS, 0, 0)
    x = add(scene, ElementType.PROCESS, 0, 200)
    y = add(scene, ElementType.PROCESS, 300, 200)
    r = add(scene, ElementType.PROCESS, -300, 100)
    first = connect(scene, p, "bottom", x, "top")
    red = connect(scene, p, "right", y, "top")
    assert red.warning and first.warning is None
    scene.connect_to_edge(r, "right", first, QPointF(0, 100))  # erster Pfeil wird aufgetrennt
    (j,) = junctions(scene)
    assert conn_between(scene, p, j).warning is None, "Stammteil übernimmt die Reihenfolge des Pfeils"
    assert red.warning


def test_only_technically_impossible_connection_is_blocked(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    assert connect(scene, a, "bottom", a, "bottom") is None


# --------------------------------------------------------------- Test 2
def test_2_connect_block_to_middle_of_horizontal_arrow(view, scene, document, qapp):
    a = add(scene, ElementType.PROCESS, -200, 0)
    b = add(scene, ElementType.PROCESS, 200, 0)
    c = add(scene, ElementType.PROCESS, 0, -200)
    host = connect(scene, a, "right", b, "left")
    drag(view, c.port_scene_pos("bottom"), QPointF(0, 2))
    qapp.processEvents()
    assert scene.connection(host.connection_id) is None, "der Pfeil muss am Knoten aufgetrennt werden"
    (j,) = junctions(scene)
    assert (j.pos().x(), j.pos().y()) == (0, 0), "Knoten liegt exakt auf dem Pfeil"
    trunk_in, trunk_out, branch = conn_between(scene, a, j), conn_between(scene, j, b), conn_between(scene, c, j)
    assert trunk_in and trunk_out and branch
    assert j.data.properties[TRUNK_IN_KEY] == trunk_in.connection_id
    assert j.data.properties[TRUNK_OUT_KEY] == trunk_out.connection_id
    assert (trunk_in.data.target_port, trunk_out.data.source_port) == ("left", "right")
    assert branch.data.target_port == "top"
    assert branch.points()[-1] == (0.0, 0.0), "neue Verbindung endet geometrisch am Knoten"
    assert trunk_in.ends_in_trunk, "der Stamm läuft optisch durch (keine Pfeilspitze am Knoten)"
    assert branch.warning is None and trunk_in.warning is None and trunk_out.warning is None
    # ein Undo-Schritt stellt den ursprünglichen Pfeil wieder her
    document.undo_stack.undo()
    assert junctions(scene) == [] and scene.connection(host.connection_id) is host


# --------------------------------------------------------------- Test 3
def test_3_connect_block_to_middle_of_vertical_arrow(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 280, -100)
    connect(scene, a, "bottom", b, "top")
    drag(view, c.port_scene_pos("bottom"), QPointF(3, 150))
    qapp.processEvents()
    (j,) = junctions(scene)
    assert j.pos().x() == 0 and 30 < j.pos().y() < 270
    branch = conn_between(scene, c, j)
    assert branch.data.target_port == "right", "Anschluss seitlich, zur Seite des neuen Elements"
    assert conn_between(scene, a, j).data.target_port == "top"
    assert conn_between(scene, j, b).data.source_port == "bottom"


# --------------------------------------------------------------- Test 4
def test_4_arrow_is_recognised_and_highlighted_while_dragging(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 280, 150)
    host = connect(scene, a, "bottom", b, "top")
    start = vp(view, c.port_scene_pos("left"))
    QTest.mouseMove(view.viewport(), start)
    QTest.mousePress(view.viewport(), LEFT, NONE, start)
    QTest.mouseMove(view.viewport(), vp(view, QPointF(100, 150)))
    QTest.mouseMove(view.viewport(), vp(view, QPointF(4, 150)))
    target = scene._connect_drag["target"]
    assert target is not None and target.is_edge and target.edge is host
    assert host._drop_highlight, "Pfeil muss als Ziel hervorgehoben sein"
    assert scene._temp_connection._markers, "Anschlusspunkt muss markiert sein"
    marker = scene._temp_connection._markers[-1]
    assert marker.x() == 0
    # vom Pfeil weg: Hervorhebung verschwindet sofort
    QTest.mouseMove(view.viewport(), vp(view, QPointF(150, 60)))
    assert not host._drop_highlight
    QTest.mouseRelease(view.viewport(), LEFT, NONE, vp(view, QPointF(150, 60)))
    assert junctions(scene) == []


# --------------------------------------------------------------- Test 5
def test_5_block_to_block_unchanged(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    drag(view, a.port_scene_pos("bottom"), b.pos())
    conn = conn_between(scene, a, b)
    assert conn is not None and conn.data.target_port == "top" and conn.warning is None
    assert junctions(scene) == []


# ------------------------------------------------- Richtung und Pfeilformen
def test_arrow_directions_up_and_left(scene):
    a = add(scene, ElementType.PROCESS, 0, 300)
    b = add(scene, ElementType.PROCESS, 0, 0)
    up = connect(scene, a, "top", b, "bottom")   # Pfeil nach oben
    c = add(scene, ElementType.PROCESS, 300, 150)
    scene.connect_to_edge(c, "left", up, QPointF(0, 150))
    (j,) = junctions(scene)
    assert conn_between(scene, a, j).data.target_port == "bottom"
    assert conn_between(scene, j, b).data.source_port == "top"
    d = add(scene, ElementType.PROCESS, 600, -300)
    e = add(scene, ElementType.PROCESS, 200, -300)
    left = connect(scene, d, "left", e, "right")  # Pfeil nach links
    f = add(scene, ElementType.PROCESS, 400, -500)
    scene.connect_to_edge(f, "bottom", left, QPointF(400, -300))
    j2 = [j for j in junctions(scene) if j.pos().y() == -300][0]
    assert conn_between(scene, d, j2).data.target_port == "right"
    assert conn_between(scene, j2, e).data.source_port == "left"


def test_connect_to_segment_of_bent_arrow(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 400, 300)
    bent = connect(scene, a, "right", b, "top")
    points = bent.points()
    assert len(points) >= 3
    (x1, y1), (x2, y2) = points[0], points[1]
    mid = QPointF((x1 + x2) / 2, (y1 + y2) / 2)
    c = add(scene, ElementType.PROCESS, 200, -250)
    scene.connect_to_edge(c, "bottom", bent, mid)
    (j,) = junctions(scene)
    assert point_on_polyline(points, j.pos().x(), j.pos().y())


def test_nearest_of_two_close_arrows_is_chosen(view, scene):
    a1 = add(scene, ElementType.PROCESS, 0, 0)
    b1 = add(scene, ElementType.PROCESS, 0, 300)
    a2 = add(scene, ElementType.START, 30, -200)
    first = connect(scene, a1, "bottom", b1, "top")
    second = connect(scene, a2, "right", b1, "right")
    from app.connections.endpoints import ConnectionEndpoint
    source = ConnectionEndpoint(item=add(scene, ElementType.PROCESS, 400, 150), port="left")
    hit_first = scene._endpoint_at(QPointF(3, 150), source)
    assert hit_first is not None and hit_first.edge is first
    assert scene.edge_hit_tolerance() < 30


# ------------------------------------------------- Start am Pfeil (Umschalt)
def test_shift_drag_starts_connection_at_arrow(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 150)
    host = connect(scene, a, "bottom", b, "top")
    drag(view, QPointF(2, 150), c.pos(), modifiers=SHIFT)
    qapp.processEvents()
    assert scene.connection(host.connection_id) is None
    (j,) = junctions(scene)
    branch = conn_between(scene, j, c)
    assert branch is not None and branch.data.source_port == "right"
    assert branch.warning, "Abzweigung ohne Verzweigung wird als Warnung markiert"
    assert conn_between(scene, j, b).warning is None


def test_connection_from_arrow_to_another_arrow(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 400, 0)
    d = add(scene, ElementType.PROCESS, 400, 300)
    left = connect(scene, a, "bottom", b, "top")
    right = connect(scene, c, "bottom", d, "top")
    from app.connections.endpoints import ConnectionEndpoint
    source = scene._edge_endpoint(left, QPointF(0, 140))
    target = scene._edge_endpoint(right, QPointF(400, 180))
    new_id = scene.connect_endpoints(source, target)
    assert new_id is not None and len(junctions(scene)) == 2
    conn = scene.connection(new_id)
    assert conn.source.is_junction and conn.target.is_junction
    assert scene.connect_endpoints(scene._edge_endpoint(conn, QPointF(200, 140)),
                                   scene._edge_endpoint(conn, QPointF(200, 140))) is None
    assert ConnectionEndpoint  # Import verwendet


def test_drop_onto_existing_junction_reuses_it(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 100)
    d = add(scene, ElementType.PROCESS, -300, 100)
    host = connect(scene, a, "bottom", b, "top")
    scene.connect_to_edge(c, "left", host, QPointF(0, 140))
    (j,) = junctions(scene)
    drag(view, d.port_scene_pos("right"), j.pos())
    assert len(junctions(scene)) == 1
    merge = conn_between(scene, d, j)
    assert merge is not None and merge.data.target_port == "left"


# ------------------------------------------------- Löschen / Undo / Datei
def test_deleting_branch_rejoins_arrow(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 150)
    connect(scene, a, "bottom", b, "top")
    host = scene.connections()[0]
    scene.connect_to_edge(c, "left", host, QPointF(0, 150))
    branch = conn_between(scene, c, junctions(scene)[0])
    scene.select_items([branch])
    scene.delete_selection()
    assert junctions(scene) == []
    rejoined = conn_between(scene, a, b)
    assert rejoined is not None and (rejoined.data.source_port, rejoined.data.target_port) == ("bottom", "top")
    document.undo_stack.undo()
    assert len(junctions(scene)) == 1 and conn_between(scene, c, junctions(scene)[0]) is not None


def test_deleting_junction_rejoins_arrow_and_removes_branch(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 150)
    host = connect(scene, a, "bottom", b, "top")
    scene.connect_to_edge(c, "left", host, QPointF(0, 150))
    scene.select_items(junctions(scene))
    scene.delete_selection()
    assert junctions(scene) == []
    assert conn_between(scene, a, b) is not None
    assert all(conn.source is not c and conn.target is not c for conn in scene.connections())


def test_junction_roundtrip_and_copy_paste(scene, document, tmp_path):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 150)
    host = connect(scene, a, "bottom", b, "top")
    scene.connect_to_edge(c, "left", host, QPointF(0, 150))
    path = tmp_path / "knoten.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == []
    (rj,) = junctions(reopened.scene)
    assert reopened.scene.connection(rj.data.properties[TRUNK_IN_KEY]).ends_in_trunk
    reopened.scene.clear_diagram()
    scene.select_items(scene.elements())
    clipboard.copy_selection(scene)
    new_ids = clipboard.paste_payload(scene, clipboard.clipboard_payload(), offset=QPointF(600, 0))
    pasted_junction = [scene.element(i) for i in new_ids if scene.element(i).is_junction][0]
    trunk_in = scene.connection(pasted_junction.data.properties[TRUNK_IN_KEY])
    assert trunk_in is not None and trunk_in.target is pasted_junction


def test_palette_insert_into_trunk_updates_junction(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 400)
    c = add(scene, ElementType.PROCESS, 300, 250)
    host = connect(scene, a, "bottom", b, "top")
    scene.connect_to_edge(c, "left", host, QPointF(0, 250))
    (j,) = junctions(scene)
    trunk_in = scene.connection(j.data.properties[TRUNK_IN_KEY])
    new_id = scene.drop_element(ElementType.PROCESS, QPointF(0, 120))
    assert scene.connection(trunk_in.connection_id) is None
    new_trunk = scene.connection(j.data.properties[TRUNK_IN_KEY])
    assert new_trunk is not None and new_trunk.source is scene.element(new_id) and new_trunk.target is j
