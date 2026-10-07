"""Interaktionstests mit echter Ansicht (Maus, Tastatur, Zoom)."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest

from app import config
from app.model.element_types import ElementType
from tests.conftest import add


def vp(view, scene_point):
    return view.mapFromScene(scene_point)


def key(key_code, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
    return QKeyEvent(QEvent.Type.KeyPress, key_code, modifiers, text)


def test_zoom_is_clamped(view):
    view.set_zoom(100)
    assert view.zoom == config.MAX_ZOOM
    view.set_zoom(0.001)
    assert view.zoom == config.MIN_ZOOM


def test_zoom_keeps_point_under_cursor(view):
    anchor = QPoint(200, 150)
    before = view.mapToScene(anchor)
    view.set_zoom(2.0, anchor)
    after = view.mapToScene(anchor)
    assert abs(before.x() - after.x()) <= 1.0 and abs(before.y() - after.y()) <= 1.0


def test_drag_moves_item_on_grid(view, scene, document, qapp):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.clearSelection()
    start = vp(view, QPointF(0, 0))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), start + QPoint(33, 47))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       start + QPoint(33, 47))
    qapp.processEvents()
    x, y = item.pos().x(), item.pos().y()
    assert (x, y) != (0, 0)
    assert x % 20 == 0 and y % 20 == 0
    document.undo_stack.undo()
    assert item.pos() == QPointF(0, 0)


def test_right_drag_pans_without_selecting(view, scene):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.clearSelection()
    start = vp(view, QPointF(0, 0))
    center_before = view.visible_center()
    QTest.mousePress(view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 6):
        QTest.mouseMove(view.viewport(), start + QPoint(20 * step, 10 * step))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier,
                       start + QPoint(100, 50))
    assert not item.isSelected()
    assert item.pos() == QPointF(0, 0)
    center_after = view.visible_center()
    assert abs(center_after.x() - center_before.x()) > 50


def test_connection_drag_creates_connection(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    port = vp(view, a.port_scene_pos("bottom"))
    target = vp(view, b.pos())
    QTest.mouseMove(view.viewport(), port)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, port)
    QTest.mouseMove(view.viewport(), port + QPoint(0, 60))
    QTest.mouseMove(view.viewport(), target)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target)
    qapp.processEvents()
    connections = scene.connections()
    assert len(connections) == 1
    conn = connections[0]
    assert conn.source is a and conn.target is b
    assert conn.data.target_port == "top"
    assert a.pos() == QPointF(0, 0)  # Baustein wurde nicht verschoben


def test_connection_drag_to_empty_space_creates_nothing(view, scene, qapp):
    a = add(scene, ElementType.PROCESS, 0, 0)
    port = vp(view, a.port_scene_pos("bottom"))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, port)
    QTest.mouseMove(view.viewport(), port + QPoint(0, 150))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       port + QPoint(0, 150))
    assert scene.connections() == []
    assert scene._temp_connection is None


def test_enter_confirms_and_shift_enter_inserts_newline(scene, view):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.begin_element_edit(item, initial_text="Zeile 1")
    editor = scene._editor
    editor.keyPressEvent(key(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier, "\r"))
    assert scene.is_editing
    editor.textCursor().insertText("Zeile 2")
    editor.keyPressEvent(key(Qt.Key.Key_Return, text="\r"))
    assert not scene.is_editing
    assert item.data.text == "Zeile 1\nZeile 2"


def test_escape_cancels_editing(scene, view):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.begin_element_edit(item, select_all=True)
    scene._editor.setPlainText("Neu")
    scene._editor.keyPressEvent(key(Qt.Key.Key_Escape))
    assert not scene.is_editing
    assert item.data.text == "Vorgang"


def test_typing_starts_editing_selected_item(scene, view):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.select_items([item])
    scene.keyPressEvent(key(Qt.Key.Key_B, text="B"))
    assert scene.is_editing
    scene._editor.textCursor().insertText("erechne")
    scene.commit_edit()
    assert item.data.text == "Berechne"


def test_editor_preview_resizes_item(scene, view):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.begin_element_edit(item, select_all=True)
    scene._editor.setPlainText("Ein wirklich sehr langer Text für diesen Vorgang mit vielen Wörtern")
    assert item.width > 160 or item.height > 60
    scene.cancel_edit()
    assert (item.width, item.height) == (160, 60)


def test_arrow_keys_move_selection(scene, view, document):
    item = add(scene, ElementType.PROCESS, 0, 0)
    scene.select_items([item])
    scene.keyPressEvent(key(Qt.Key.Key_Right))
    scene.keyPressEvent(key(Qt.Key.Key_Right))
    assert item.pos() == QPointF(40, 0)
    document.undo_stack.undo()  # zusammengefasst
    assert item.pos() == QPointF(0, 0)


def test_label_edit(scene, view):
    d = add(scene, ElementType.DECISION, 0, 0)
    p = add(scene, ElementType.PROCESS, 0, 200)
    conn_id = scene.create_connection(d, "bottom", p, "top")
    conn = scene.connection(conn_id)
    assert conn.data.label == "ja"
    scene.begin_label_edit(conn)
    scene._editor.setPlainText("wahr")
    scene.commit_edit()
    assert conn.data.label == "wahr"
    assert conn.label.text() == "wahr"


def test_drop_preview_and_drop(scene, view):
    scene.update_drop_preview(ElementType.PROCESS, QPointF(13, 27))
    assert scene._ghost is not None and scene._ghost.pos() == QPointF(20, 20)
    new_id = scene.drop_element(ElementType.PROCESS, QPointF(13, 27))
    assert scene._ghost is None
    assert scene.element(new_id).pos() == QPointF(20, 20)


def test_export_mode_hides_ui(scene, view, tmp_path):
    from app import export
    a = add(scene, ElementType.PROCESS, 0, 0)
    scene.select_items([a])
    export.export_png(scene, str(tmp_path / "a.png"), export.ExportOptions())
    export.export_svg(scene, str(tmp_path / "a.svg"), export.ExportOptions())
    export.export_pdf(scene, str(tmp_path / "a.pdf"), export.ExportOptions())
    assert all((tmp_path / name).stat().st_size > 0 for name in ("a.png", "a.svg", "a.pdf"))
    assert not scene.exporting and a.isSelected()
