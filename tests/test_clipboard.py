"""Tests für Kopieren/Einfügen."""

from PySide6.QtCore import QPointF

from app import clipboard
from app.model.diagram import Diagram, ElementData
from app.model.element_types import ElementType
from tests.conftest import add, connect


def test_copy_paste_internal_connections_only(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 120)
    c = add(scene, ElementType.PROCESS, 0, 240)
    connect(scene, a, "bottom", b, "top")
    connect(scene, b, "bottom", c, "top")
    scene.select_items([a, b])
    assert clipboard.copy_selection(scene)
    payload = clipboard.clipboard_payload()
    new_ids = clipboard.paste_payload(scene, payload, offset=QPointF(400, 0))
    assert len(new_ids) == 2
    assert not set(new_ids) & {a.element_id, b.element_id, c.element_id}
    a2, b2 = sorted((scene.element(i) for i in new_ids), key=lambda it: it.pos().y())
    new_connections = [conn for conn in scene.connections() if conn.source in (a2, b2) or conn.target in (a2, b2)]
    assert len(new_connections) == 1
    assert new_connections[0].source is a2 and new_connections[0].target is b2
    assert all(conn.target is not c for conn in new_connections)
    assert len(scene.connections()) == 3
    document.undo_stack.undo()
    assert len(scene.elements()) == 3 and len(scene.connections()) == 2


def test_cut_and_paste(scene, document):
    a = add(scene, ElementType.INPUT, 0, 0)
    scene.select_items([a])
    assert clipboard.cut_selection(scene)
    assert scene.elements() == []
    new_ids = clipboard.paste_payload(scene, clipboard.clipboard_payload())
    assert len(new_ids) == 1
    assert scene.element(new_ids[0]).data.text == "Eingabe"


def test_paste_at_position(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    scene.select_items([a])
    clipboard.copy_selection(scene)
    new_ids = clipboard.paste_payload(scene, clipboard.clipboard_payload(), target_center=QPointF(500, 300))
    item = scene.element(new_ids[0])
    assert (item.pos().x(), item.pos().y()) == (500, 300)


def test_paste_tracker_offsets():
    tracker = clipboard.PasteTracker()
    payload = Diagram(elements=[ElementData("a", ElementType.PROCESS, 0, 0, 160, 60)])
    assert tracker.next_offset(payload, 40) == QPointF(40, 40)
    assert tracker.next_offset(payload, 40) == QPointF(80, 80)
    tracker.prime_after_cut(payload)
    assert tracker.next_offset(payload, 40) == QPointF(0, 0)
