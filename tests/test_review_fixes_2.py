"""Regressionstests für die zweite Review-Runde."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsSceneHoverEvent

from app import clipboard
from app.connections import routing
from app.model.element_types import ElementType
from tests.conftest import add, connect


def vp(view, scene_point):
    return view.mapFromScene(scene_point)


def key(key_code, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
    return QKeyEvent(QEvent.Type.KeyPress, key_code, modifiers, text)


def send_mouse(view, kind, pos, buttons):
    widget = view.viewport()
    event = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(pos)), Qt.MouseButton.LeftButton,
                        buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def crosses_any(points, rect):
    r = routing.Rect(rect.left(), rect.top(), rect.right(), rect.bottom())
    return any(routing.segment_crosses_rect(a, b, r) for a, b in zip(points, points[1:]))


def make_window(qapp):
    from app.main_window import MainWindow
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    qapp.processEvents()
    return window


def test_quit_while_editing_commits_text_and_asks(qapp, monkeypatch):
    window = make_window(qapp)
    window.new_document()
    doc = window.current_document()
    item = add(doc.scene, ElementType.PROCESS, 0, 0)
    doc.undo_stack.setClean()
    doc.scene.begin_element_edit(item, select_all=True)
    doc.scene._editor.setPlainText("Wichtiger Text")
    asked = []
    monkeypatch.setattr(window, "maybe_save", lambda d: asked.append(d) or False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert item.data.text == "Wichtiger Text"
    assert asked == [doc]
    assert not event.isAccepted()
    doc.undo_stack.setClean()
    window.close()


def test_escape_cancels_element_drag(view, scene, document, qapp):
    item = add(scene, ElementType.PROCESS, 0, 0)
    count = document.undo_stack.count()
    start = vp(view, item.pos())
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), start + QPoint(100, 0))
    assert item.pos() != QPointF(0, 0)
    scene.handle_escape()
    assert item.pos() == QPointF(0, 0)
    QTest.mouseMove(view.viewport(), start + QPoint(160, 0))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       start + QPoint(160, 0))
    assert item.pos() == QPointF(0, 0)
    assert document.undo_stack.count() == count


def test_escape_cancels_segment_drag(scene, document):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 300, 300)
    conn = connect(scene, a, "bottom", b, "top")
    old = dict(conn.data.routing)
    count = document.undo_stack.count()
    scene.select_items([conn])
    conn._segment_drag = {"axis": "y", "old": old}
    conn.data.routing = {"mode": "manual", "axis": "y", "value": 200.0}
    conn.update_route()
    scene.end_pointer_interaction(cancel=True)
    assert conn.data.routing == old
    assert not conn.is_segment_dragging
    assert document.undo_stack.count() == count


def test_label_click_wins_over_port_at_low_zoom(view, scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    p = add(scene, ElementType.PROCESS, 0, 240)
    conn = connect(scene, d, "bottom", p, "top")
    view.set_zoom(0.3)
    center = conn.label.sceneBoundingRect().center()
    assert scene._port_hit(center) is None


def test_occluded_port_does_not_steal_click(scene):
    add(scene, ElementType.COMMENT, 0, 0)            # rechter Anschluss bei (80, 0)
    process = add(scene, ElementType.PROCESS, 100, 0)  # Körper x = 20..180
    hit = scene._port_hit(QPointF(80, 0))
    assert hit is None or hit[0] is process


def test_paste_and_duplicate_respect_odd_grid(scene):
    scene.settings.grid_size = 25
    a = add(scene, ElementType.PROCESS, 0, 250)
    scene.select_items([a])
    clipboard.copy_selection(scene)
    ids = clipboard.paste_payload(scene, clipboard.clipboard_payload(), offset=QPointF(40, 40))
    item = scene.element(ids[0])
    assert item.pos().x() % 25 == 0 and item.pos().y() % 25 == 0


def test_keyboard_nudge_does_not_reroute_internal_connections(scene, monkeypatch):
    items = [add(scene, ElementType.PROCESS, 0, y * 120) for y in range(10)]
    for upper, lower in zip(items, items[1:]):
        connect(scene, upper, "bottom", lower, "top")
    scene.select_items(items)
    calls = []
    original = routing.route
    monkeypatch.setattr(routing, "route", lambda *a, **k: calls.append(1) or original(*a, **k))
    scene.keyPressEvent(key(Qt.Key.Key_Right))
    assert calls == []


def test_select_items_emits_once(scene):
    items = [add(scene, ElementType.PROCESS, x * 200, 0) for x in range(20)]
    emitted = []
    scene.selection_state_changed.connect(lambda: emitted.append(1))
    scene.select_items(items)
    assert len(emitted) == 1
    assert len(scene.selectedItems()) == 20


def test_double_click_jitter_does_not_move_item(view, scene, document, qapp):
    item = add(scene, ElementType.PROCESS, 0, 100)
    count = document.undo_stack.count()
    pos = vp(view, item.pos())
    left = Qt.MouseButton.LeftButton
    send_mouse(view, QEvent.Type.MouseButtonPress, pos, left)
    send_mouse(view, QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.NoButton)
    send_mouse(view, QEvent.Type.MouseButtonDblClick, pos, left)
    send_mouse(view, QEvent.Type.MouseMove, pos + QPoint(2, 1), left)
    send_mouse(view, QEvent.Type.MouseButtonRelease, pos + QPoint(2, 1), Qt.MouseButton.NoButton)
    assert item.pos() == QPointF(0, 100)
    scene.commit_edit()
    assert document.undo_stack.count() == count


def test_smart_insert_on_decision_uses_free_ports(scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    scene.select_items([d])
    p1 = scene.element(scene.insert_element_smart(ElementType.PROCESS, QPointF(0, 0)))
    scene.select_items([d])
    p2 = scene.element(scene.insert_element_smart(ElementType.PROCESS, QPointF(0, 0)))
    outgoing = sorted((c for c in d.connections if c.source is d), key=lambda c: c.data.label)
    assert {c.data.source_port for c in outgoing} == {"bottom", "right"}
    assert outgoing[0].label.scenePos() != outgoing[1].label.scenePos()
    for conn in outgoing:
        other = p2 if conn.target is p1 else p1
        assert not crosses_any(conn.points(), other.scene_rect())


def test_smart_insert_after_loop_begin_goes_into_loop_body(scene):
    scene.insert_element(ElementType.LOOP, QPointF(0, 0))
    begin = scene.single_selected
    assert begin is not None and begin.data.properties["part"] == "begin"
    new = scene.element(scene.insert_element_smart(ElementType.PROCESS, QPointF(0, 0)))
    pairs = {(c.source.data.text, c.target.data.text) for c in scene.connections()}
    assert ("Schleifenbeginn", "Vorgang") in pairs and ("Vorgang", "Schleifenende") in pairs
    end = [e for e in scene.elements() if e.data.properties.get("part") == "end"][0]
    assert not new.scene_rect().intersects(end.scene_rect())


def test_hover_leave_clears_crosshair_cursor(scene):
    item = add(scene, ElementType.PROCESS, 0, 0)
    item.set_hover_port("bottom")
    assert item.hasCursor()
    item.hoverLeaveEvent(QGraphicsSceneHoverEvent(QEvent.Type.GraphicsSceneHoverLeave))
    assert not item.hasCursor()


def test_hover_state_reset_after_delete_and_undo(scene, document):
    item = add(scene, ElementType.PROCESS, 0, 0)
    item._hovered = True
    scene.select_items([item])
    scene.delete_selection()
    document.undo_stack.undo()
    assert not item._hovered


def test_insert_into_upward_back_edge(scene):
    d = add(scene, ElementType.DECISION, 0, 0)
    p = add(scene, ElementType.PROCESS, 0, 200)
    connect(scene, d, "bottom", p, "top")
    back = connect(scene, p, "left", d, "left")
    segment = [(a, b) for a, b in zip(back.points(), back.points()[1:]) if a[0] == b[0]][0]
    x = segment[0][0]
    y = (segment[0][1] + segment[1][1]) / 2
    new = scene.element(scene.drop_element(ElementType.PROCESS, QPointF(x, y)))
    incoming = [c for c in new.connections if c.target is new][0]
    outgoing = [c for c in new.connections if c.source is new][0]
    assert incoming.data.target_port == "bottom" and outgoing.data.source_port == "top"


def test_keyboard_context_menu_opens(qapp, monkeypatch):
    window = make_window(qapp)
    window.new_document()
    view = window.current_view()
    opened = []
    monkeypatch.setattr(window, "show_context_menu", lambda *args: opened.append(args))
    view.context_menu_requested.disconnect()
    view.context_menu_requested.connect(window.show_context_menu)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(10, 10), view.mapToGlobal(QPoint(10, 10)))
    QApplication.sendEvent(view, event)
    assert opened
    window.current_document().undo_stack.setClean()
    window.close()


def test_typing_after_loop_insert_edits_loop_begin(scene):
    scene.insert_element(ElementType.LOOP, QPointF(0, 0))
    scene.keyPressEvent(key(Qt.Key.Key_W, text="W"))
    assert scene.is_editing
    scene.cancel_edit()


def test_altgr_character_starts_editing(scene):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.select_items([item])
    mods = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    scene.keyPressEvent(key(Qt.Key.Key_At, mods, "@"))
    assert scene.is_editing
    scene.commit_edit()
    assert item.data.text == "@"
