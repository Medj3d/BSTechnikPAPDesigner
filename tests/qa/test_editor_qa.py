"""Additional editor QA through Qt input and public document operations."""

import time

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest

from app import alignment, clipboard, preferences
from app.document import DiagramDocument
from app.model.diagram import ConnectionData, ElementData
from app.model.element_types import ElementType
from tests.conftest import add

LEFT = Qt.MouseButton.LeftButton
NONE = Qt.KeyboardModifier.NoModifier


def drag(view, start, finish, button=LEFT, modifiers=NONE):
    viewport = view.viewport()
    first = view.mapFromScene(start)
    last = view.mapFromScene(finish)
    QTest.mouseMove(viewport, first)
    QTest.mousePress(viewport, button, modifiers, first)
    QTest.mouseMove(viewport, (first + last) / 2)
    QTest.mouseMove(viewport, last)
    QTest.mouseRelease(viewport, button, modifiers, last)


@pytest.mark.parametrize("text", ["", "ÄÖÜ ß — 😀 ≠ <&> \"'\"", "langer Text " * 180])
def test_edit_geometry_unicode_save_and_undo(text, scene, view, document, tmp_path):
    item = add(scene, ElementType.PROCESS, 0, 0)
    original_size = item.width, item.height
    path = tmp_path / "Übungsblatt Nr 1 😀.pap"
    document.save(str(path))
    QTest.mouseDClick(view.viewport(), LEFT, NONE, view.mapFromScene(item.pos()))
    assert scene.is_editing
    scene._editor.setPlainText(text)
    QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
    assert item.data.text == text.rstrip()
    if len(text) > 1000:
        assert item.width * item.height > original_size[0] * original_size[1]
    assert document.is_modified
    document.save(str(path))
    assert not document.is_modified
    document.undo_stack.undo()
    assert item.data.text == "Vorgang"
    assert document.is_modified
    document.undo_stack.redo()
    assert item.data.text == text.rstrip() and not document.is_modified
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.scene.element(item.element_id).data.text == text.rstrip()


def test_mouse_can_make_a_decision_return_to_itself(scene, view, qapp):
    decision = add(scene, ElementType.DECISION, 0, 0)
    first = decision.port_scene_pos("right")
    last = decision.port_scene_pos("top")
    start_px = view.mapFromScene(first)
    QTest.mousePress(view.viewport(), LEFT, NONE, start_px)
    QTest.mouseMove(view.viewport(), start_px + QPoint(60, -30))
    QTest.mouseMove(view.viewport(), view.mapFromScene(last))
    QTest.mouseRelease(view.viewport(), LEFT, NONE, view.mapFromScene(last))
    qapp.processEvents()
    assert len(scene.connections()) == 1
    connection = scene.connections()[0]
    assert connection.source is decision and connection.target is decision


def test_loose_target_reattach_selection_delete_and_undo(scene, view, document, qapp):
    preferences.set_enabled(preferences.LOOSE_ENDS, True)
    decision = add(scene, ElementType.DECISION, -100, 0)
    yes = add(scene, ElementType.PROCESS, -160, 200)
    no = add(scene, ElementType.PROCESS, 200, 40)
    drag(view, decision.port_scene_pos("bottom"), yes.pos())
    loose_tip = QPointF(200, -140)
    drag(view, decision.port_scene_pos("right"), loose_tip)
    assert len(scene.connections()) == 2
    assert any(c.has_loose_end for c in scene.connections())
    drag(view, loose_tip, no.pos())
    qapp.processEvents()
    assert {c.data.label for c in scene.connections()} == {"ja", "nein"}
    assert all(not c.has_loose_end for c in scene.connections())
    scene.select_items([decision, yes])
    payload = clipboard.selection_payload(scene)
    assert payload is not None and len(payload.connections) == 1
    assert len(clipboard.paste_payload(scene, payload, offset=QPointF(-260, 0))) == 2
    scene.select_items([decision, no])
    scene.delete_selection()
    assert len(scene.connections()) == 1
    document.undo_stack.undo()
    assert len(scene.connections()) == 3
    assert {c.data.label for c in scene.element(decision.element_id).connections} == {"ja", "nein"}


def test_alignment_after_rubber_band_and_wheel_zoom(scene, view, qapp):
    a = add(scene, ElementType.PROCESS, -120, -120)
    b = add(scene, ElementType.PROCESS, 100, 100)
    scene.clearSelection()
    drag(view, QPointF(-240, -200), QPointF(220, 200))
    assert set(scene.selected_elements()) == {a, b}
    moves = alignment.compute_moves(scene.selected_elements(), alignment.ALIGN_LEFT)
    scene.apply_moves(moves, "Links ausrichten")
    assert a.scene_rect().left() == b.scene_rect().left()
    scene.undo_stack.undo()
    assert b.pos() == QPointF(100, 100)
    pos = QPointF(200, 200)
    wheel = QWheelEvent(pos, view.viewport().mapToGlobal(pos.toPoint()), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, NONE, Qt.ScrollPhase.NoScrollPhase, False)
    qapp.sendEvent(view.viewport(), wheel)
    assert view.zoom == pytest.approx(1.15)


def test_large_edit_undo_save_reload(scene, document, tmp_path):
    def sample(index):
        x = (index % 15) * 220
        y = (index // 15) * 140
        return ElementData(str(index), ElementType.PROCESS, x, y, 160, 60, f"Vorgang {index}")

    elems = [sample(i) for i in range(525)]
    edges = [ConnectionData(f"c{i}", str(i), str(i + 1), "right", "left")
             for i in range(524) if i % 15 != 14]
    started = time.perf_counter()
    assert not scene.load_content(elems, edges)
    loaded = time.perf_counter()
    for item in scene.elements()[:120]:
        scene.begin_element_edit(item)
        scene._editor.setPlainText(item.data.text + " geändert")
        scene.commit_edit()
    edited = time.perf_counter()
    assert document.undo_stack.count() == 120
    for _ in range(120):
        document.undo_stack.undo()
    assert [i.data.text for i in scene.elements()] == [e.text for e in elems]
    for _ in range(120):
        document.undo_stack.redo()
    redone = time.perf_counter()
    path = tmp_path / "525 Vorgänge.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert len(reopened.scene.elements()) == 525
    assert len(reopened.scene.connections()) == len(edges)
    assert reopened.scene.element("119").data.text == "Vorgang 119 geändert"
    done = time.perf_counter()
    print(f"Load {loaded-started:.3f}s, 120 edits {edited-loaded:.3f}s, "
          f"120 undo+redo {redone-edited:.3f}s, save+open {done-redone:.3f}s, "
          f"PAP {path.stat().st_size} bytes")


def test_fit_shows_entire_tall_diagram(scene, view):
    for i in range(35):
        add(scene, ElementType.PROCESS, 0, i * 150)
    view.fit_diagram()
    assert view.visible_scene_rect().contains(scene.diagram_bounds())
