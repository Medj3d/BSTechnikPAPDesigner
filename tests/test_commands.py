"""Tests für Undo/Redo und Diagrammoperationen."""

from PySide6.QtCore import QPointF

from app import alignment
from app.model.element_types import ElementType
from tests.conftest import add, connect


def test_add_undo_redo(scene, document):
    item = add(scene, ElementType.PROCESS, 0, 0)
    assert len(scene.elements()) == 1
    document.undo_stack.undo()
    assert scene.elements() == []
    document.undo_stack.redo()
    assert scene.element(item.element_id) is item


def test_new_elements_snap_to_grid(scene):
    item = add(scene, ElementType.PROCESS, 13, 27)
    assert (item.pos().x(), item.pos().y()) == (20, 20)


def test_move_undo(scene, document):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.apply_moves({item.element_id: ((0, 0), (100, 60))}, "Verschieben")
    assert item.pos() == QPointF(100, 60)
    assert (item.data.x, item.data.y) == (100, 60)
    document.undo_stack.undo()
    assert item.pos() == QPointF(0, 0)


def test_text_edit_undo(scene, document):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.begin_element_edit(item, select_all=True)
    scene._editor.setPlainText("Berechne Mittelwert")
    scene.commit_edit()
    assert item.data.text == "Berechne Mittelwert"
    document.undo_stack.undo()
    assert item.data.text == "Vorgang"
    document.undo_stack.redo()
    assert item.data.text == "Berechne Mittelwert"


def test_cancel_edit_restores_text(scene, document):
    item = add(scene, ElementType.PROCESS, 0, 0)
    count = document.undo_stack.count()
    scene.begin_element_edit(item, select_all=True)
    scene._editor.setPlainText("verworfen")
    scene.cancel_edit()
    assert item.data.text == "Vorgang"
    assert document.undo_stack.count() == count


def test_delete_restores_connections(scene, document):
    a = add(scene, ElementType.START, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 120)
    c = add(scene, ElementType.END, 0, 240)
    connect(scene, a, "bottom", b, "top")
    connect(scene, b, "bottom", c, "top")
    assert len(scene.connections()) == 2
    scene.select_items([b])
    scene.delete_selection()
    assert scene.element(b.element_id) is None
    assert scene.connections() == []
    assert a.connections == [] and c.connections == []
    document.undo_stack.undo()
    assert scene.element(b.element_id) is b
    assert len(scene.connections()) == 2
    assert len(b.connections) == 2


def test_connection_undo(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 120)
    conn = connect(scene, a, "bottom", b, "top")
    assert conn is not None and conn.source is a and conn.target is b
    document.undo_stack.undo()
    assert scene.connections() == []
    assert a.connections == []


def test_connection_follows_moved_item(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    conn = connect(scene, a, "bottom", b, "top")
    scene.apply_moves({b.element_id: ((0, 200), (300, 200))}, "Verschieben")
    points = conn.points()
    assert points[0] == (a.port_scene_pos("bottom").x(), a.port_scene_pos("bottom").y())
    assert points[-1] == (b.port_scene_pos("top").x(), b.port_scene_pos("top").y())


def test_problematic_connection_is_created_with_warning(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    # technisch unmöglich: gleicher Anschluss als Anfang und Ende
    assert connect(scene, a, "bottom", a, "bottom") is None
    assert scene.connections() == []
    # fachlich fragwürdig: wird erstellt, aber als Warnung markiert
    loop = connect(scene, a, "bottom", a, "top")
    assert loop is not None and loop.warning
    s = add(scene, ElementType.START, 0, -200)
    into_start = connect(scene, a, "right", s, "bottom")
    assert into_start is not None and into_start.warning
    assert len(scene.connections()) == 2


def test_decision_labels(scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    x = add(scene, ElementType.PROCESS, -300, 200)
    y = add(scene, ElementType.PROCESS, 300, 200)
    c1 = connect(scene, d, "left", x, "top")
    c2 = connect(scene, d, "right", y, "top")
    assert (c1.data.label, c2.data.label) == ("ja", "nein")


def test_loop_inserts_pair(scene, document):
    add(scene, ElementType.LOOP, 0, 0)
    loops = [e for e in scene.elements() if e.element_type is ElementType.LOOP]
    assert len(loops) == 2
    assert {e.data.properties["part"] for e in loops} == {"begin", "end"}
    assert len(scene.connections()) == 1
    document.undo_stack.undo()
    assert scene.elements() == [] and scene.connections() == []


def test_insert_into_connection(scene, document):
    a = add(scene, ElementType.START, 0, 0)
    b = add(scene, ElementType.END, 0, 300)
    conn = connect(scene, a, "bottom", b, "top")
    new_id = scene.insert_element(ElementType.PROCESS, QPointF(0, 150), into_connection=conn)
    new = scene.element(new_id)
    pairs = {(c.source, c.target) for c in scene.connections()}
    assert pairs == {(a, new), (new, b)}
    document.undo_stack.undo()
    assert scene.element(new_id) is None
    assert {(c.source, c.target) for c in scene.connections()} == {(a, b)}


def test_smart_insert_connects_below_selection(scene):
    a = add(scene, ElementType.START, 0, 0)
    scene.select_items([a])
    new_id = scene.insert_element_smart(ElementType.PROCESS, QPointF(0, 0))
    new = scene.element(new_id)
    assert new.pos().y() > a.pos().y()
    assert any(c.source is a and c.target is new for c in scene.connections())


def test_z_order_undo(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 20, 20)
    scene.select_items([a])
    scene.bring_to_front()
    assert a.zValue() > b.zValue()
    document.undo_stack.undo()
    assert a.data.z == 0


def test_align_left_and_distribute(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 100, 200)
    c = add(scene, ElementType.DECISION, 40, 500)
    items = [a, b, c]
    moves = alignment.compute_moves(items, alignment.ALIGN_LEFT)
    scene.apply_moves(moves, "Links ausrichten")
    lefts = {round(it.pos().x() - it.width / 2, 3) for it in items}
    assert len(lefts) == 1
    document.undo_stack.undo()
    assert a.pos().x() == 0 and b.pos().x() == 100
    moves = alignment.compute_moves(items, alignment.DISTRIBUTE_V)
    scene.apply_moves(moves, "Verteilen")
    tops = sorted(it.pos().y() - it.height / 2 for it in items)
    bottoms = sorted(it.pos().y() + it.height / 2 for it in items)
    gaps = [tops[1] - bottoms[0], tops[2] - bottoms[1]]
    assert abs(gaps[0] - gaps[1]) < 1e-6


def test_properties_command(document):
    from app.commands import ProjectPropertiesCommand
    old = document.meta.copy()
    new = old.copy()
    new.name = "Neu"
    document.undo_stack.push(ProjectPropertiesCommand(document, old, new, 20, 40))
    assert document.meta.name == "Neu" and document.settings.grid_size == 40
    assert document.is_modified
    document.undo_stack.undo()
    assert document.meta.name == old.name and document.settings.grid_size == 20
    assert not document.is_modified


def test_modified_flag_and_save(scene, document, tmp_path):
    assert not document.is_modified
    add(scene, ElementType.PROCESS, 0, 0)
    assert document.is_modified
    path = tmp_path / "x.pap"
    document.save(str(path))
    assert not document.is_modified
    assert document.display_name == "x"


def test_text_grows_item_in_steps(scene):
    item = add(scene, ElementType.PROCESS, 0, 0)
    w0, h0 = item.width, item.height
    item.set_text("A")
    assert (item.width, item.height) == (w0, h0)
    item.set_text("Ein sehr langer Text, der auf jeden Fall mehrfach umbrochen werden muss, weil er "
                  "viel zu lang für eine oder zwei Zeilen innerhalb eines einzelnen Vorgangs ist")
    assert item.width % 40 == 0 and item.height % 20 == 0
    assert item.width <= 320
    assert item.height > h0
