"""Einstellungen, Suche, Baustein-Tasten, Pfeile und Prüfung (Wunschliste nach Version 1.10.1)."""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

from app import preferences
from app.actions import insert_action_name
from app.connections import routing
from app.diagnostics.checks import INFO, WARNING, run_checks
from app.dialogs.settings import SettingsDialog
from app.dialogs.shortcuts import ShortcutsDialog
from app.document import DiagramDocument
from app.layout.auto_layout import apply_layout, plan_auto_layout
from app.main_window import MainWindow
from app.model import rules
from app.model.element_types import LOOSE_END_KEY, ElementType as T
from app.search_text import matches, score
from tests.conftest import add, connect


@pytest.fixture
def window(qapp):
    created = MainWindow()
    yield created
    created.settings_store.set_shortcuts({})
    for preference in preferences.PREFERENCES:
        created.settings_store._settings.remove(f"preferences/{preference.name}")
    for view in created.views():
        view.document.undo_stack.setClean()
    created.close()


def vp(view, point):
    return view.mapFromScene(point)


def drag(view, start, end, steps=4):
    a, b = vp(view, start), vp(view, end)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for step in range(1, steps + 1):
        QTest.mouseMove(view.viewport(), a + (b - a) * step / steps)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)


def conn_between(scene, source, target):
    return next((c for c in scene.connections() if c.source is source and c.target is target), None)


# ---------------------------------------------------------------- Falsche rote Pfeile
def test_no_arrow_ever_leaves_a_selected_end(scene):
    start, end = add(scene, T.START, 0, 0), add(scene, T.END, 0, 200)
    connect(scene, start, "bottom", end, "top")
    scene.select_items([end])
    new = scene.element(scene.insert_element_smart(T.PROCESS, QPointF(400, 400)))
    assert conn_between(scene, start, new) and conn_between(scene, new, end)
    assert not scene.connection_warnings()


def test_new_start_is_never_attached(scene):
    block = add(scene, T.PROCESS, 0, 0)
    scene.select_items([block])
    new = scene.element(scene.insert_element_smart(T.START, QPointF(400, 400)))
    assert new.connections == [] and not scene.connection_warnings()


def test_second_end_does_not_become_a_second_exit(scene):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 200)
    connect(scene, a, "bottom", b, "top")
    scene.select_items([a])
    scene.insert_element_smart(T.END, QPointF(400, 400))
    assert not scene.connection_warnings()


def test_valid_decision_patterns_stay_unmarked(scene):
    d, b = add(scene, T.DECISION, 0, 0), add(scene, T.PROCESS, 0, 300)
    wait = connect(scene, d, "left", d, "top")
    both = [connect(scene, d, "bottom", b, "top"), connect(scene, d, "right", b, "right")]
    assert wait.warning is None and all(c.warning is None for c in both)


def test_levels_red_and_yellow(scene, document):
    a, b, c = (add(scene, T.PROCESS, x, 0) for x in (0, 300, 600))
    connect(scene, a, "bottom", b, "top")
    second = connect(scene, a, "right", c, "left")
    assert second.warning and second.warning_level == rules.ERROR
    j = scene.element(scene.insert_junction(conn_between(scene, a, b), QPointF(150, 60)))
    split = connect(scene, j, "right", c, "top")
    assert split.warning and split.warning_level == rules.CAUTION
    levels = {issue.severity for issue in run_checks(document) if issue.connection_ids}
    assert levels == {WARNING, INFO}


def test_changing_the_type_keeps_the_mark_on_the_same_arrow(scene):
    a, b, c = (add(scene, T.PROCESS, x, 0) for x in (0, 300, 600))
    first = connect(scene, a, "bottom", b, "top")
    second = connect(scene, a, "right", c, "left")
    assert scene.change_element_type(b, T.OUTPUT)
    assert scene.connection(first.connection_id).warning is None
    assert scene.connection(second.connection_id).warning


def test_extended_checks_only_when_switched_on(scene):
    s, d, a, e = add(scene, T.START, 0, 0), add(scene, T.DECISION, 0, 200), add(scene, T.PROCESS, 300, 200), \
        add(scene, T.END, 0, 500)
    connect(scene, s, "bottom", d, "top")
    yes = connect(scene, d, "bottom", e, "top")
    no = connect(scene, d, "right", a, "left")
    yes.set_label("")
    no.set_label("")
    assert not scene.connection_warnings()
    preferences.set_enabled(preferences.EXTENDED_CHECKS, True)
    scene.preferences_changed()
    assert yes.warning and yes.warning_level == rules.CAUTION
    assert no.warning  # führt nie zum Ende
    preferences.set_enabled(preferences.EXTENDED_CHECKS, False)
    scene.preferences_changed()
    assert not scene.connection_warnings()


def test_warning_mark_is_part_of_the_arrow_and_can_be_hidden(scene):
    a, b, c = (add(scene, T.PROCESS, x, 0) for x in (0, 300, 600))
    connect(scene, a, "bottom", b, "top")
    second = connect(scene, a, "right", c, "left")
    assert second._mark_center() is not None and second.toolTip()
    preferences.set_enabled(preferences.WARNING_MARKS, False)
    assert second._mark_center() is None


# ---------------------------------------------------------------- Pfeile verschieben
def test_straight_arrow_can_be_moved_sideways_and_stays_rectangular(scene, view, qapp):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300)
    conn = connect(scene, a, "bottom", b, "top")
    scene.select_items([conn])
    drag(view, QPointF(0, 150), QPointF(200, 150))
    qapp.processEvents()
    points = conn.points()
    assert conn.has_manual_routing() and any(abs(x - 200) < 1 for x, _y in points)
    assert routing._is_orthogonal(points)
    assert conn.source is a and conn.target is b and points[0] == pytest.approx((0, 30))
    scene.undo_stack.undo()
    assert not conn.has_manual_routing() and len(conn.points()) == 2


def test_moved_line_follows_blocks_and_survives_saving(document, tmp_path, view, qapp):
    scene = document.scene
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300)
    conn = connect(scene, a, "bottom", b, "top")
    scene.select_items([conn])
    drag(view, QPointF(0, 150), QPointF(200, 150))
    a.setPos(QPointF(40, 0))
    qapp.processEvents()
    assert conn.points()[0] == pytest.approx((40, 30)) and routing._is_orthogonal(conn.points())
    path = tmp_path / "linie.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == []
    assert reopened.scene.connections()[0].data.routing == conn.data.routing


def test_moving_both_blocks_moves_the_drawn_line_with_them(scene, view, qapp):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300)
    conn = connect(scene, a, "bottom", b, "top")
    scene.select_items([conn])
    drag(view, QPointF(0, 150), QPointF(200, 150))
    before = conn.points()
    with scene.batch_routing():
        a.setPos(QPointF(100, 0))
        b.setPos(QPointF(100, 300))
    assert conn.points() == [(x + 100, y) for x, y in before]


def test_bend_changes_only_the_look(scene):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300)
    conn = connect(scene, a, "bottom", b, "top")
    scene.add_bend(conn, QPointF(0, 150))
    assert len(conn.points()) > 2 and routing._is_orthogonal(conn.points())
    assert conn.source is a and conn.target is b
    scene.undo_stack.undo()
    assert len(conn.points()) == 2


def test_rounded_corners_do_not_change_the_points(scene):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 300, 300)
    conn = connect(scene, a, "bottom", b, "top")
    points = conn.points()
    assert conn._line_path.elementCount() > 2 * len(points)  # Bögen statt Ecken
    preferences.set_enabled(preferences.ROUNDED_LINES, False)
    scene.preferences_changed()
    assert conn.points() == points and conn._line_path.elementCount() == len(points)


def test_lines_keep_distance_from_blocks_and_other_lines():
    blocker = routing.Rect(-80, 100, 80, 160)
    points = routing.route((0, 0), "bottom", (0, 300), "top", None, None, [blocker])
    assert all(not routing.segment_crosses_rect(a, b, blocker.inflated(routing.CLEARANCE))
               for a, b in zip(points[:-1], points[1:]))
    other = [((200, 0), (200, 300))]
    free = routing.route((200, 0), "bottom", (200, 300), "top", None, None, [], None, None)
    assert routing.line_penalty(free[0], free[-1], other) > 0


# ---------------------------------------------------------------- Pfeile umhängen, lose Enden, Schnellmenü
def test_arrow_end_can_be_moved_to_another_block(scene, view, qapp):
    a, b, c = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300), add(scene, T.PROCESS, 300, 300)
    conn = connect(scene, a, "bottom", b, "top")
    conn.set_label("los")
    scene.select_items([conn])
    drag(view, b.port_scene_pos("top"), c.pos())
    qapp.processEvents()
    moved = conn_between(scene, a, c)
    assert moved is not None and conn_between(scene, a, b) is None and moved.data.label == "los"
    assert moved.warning is None, "der alte Pfeil zählt beim Umhängen nicht mehr als zweiter Ausgang"
    scene.undo_stack.undo()
    assert conn_between(scene, a, b) is not None and conn_between(scene, a, c) is None


def test_arrow_start_can_be_moved_to_another_block(scene, view, qapp):
    a, b, c = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300), add(scene, T.PROCESS, 300, 0)
    conn = connect(scene, a, "bottom", b, "top")
    scene.select_items([conn])
    drag(view, a.port_scene_pos("bottom"), c.pos())
    qapp.processEvents()
    assert conn_between(scene, c, b) is not None and conn_between(scene, a, b) is None


def test_drag_into_empty_space_cancels_when_both_switches_are_off(scene, view, qapp):
    a = add(scene, T.PROCESS, 0, 0)
    drag(view, a.port_scene_pos("bottom"), QPointF(0, 200))
    assert scene.connections() == [] and scene._temp_connection is None


def test_quick_menu_creates_the_block_at_the_arrow_end(scene, view, qapp, monkeypatch):
    preferences.set_enabled(preferences.QUICK_MENU, True)
    shown = []
    monkeypatch.setattr(view, "show_quick_menu", shown.append)
    a = add(scene, T.PROCESS, 0, 0)
    drag(view, a.port_scene_pos("bottom"), QPointF(0, 200))
    assert len(shown) == 1 and scene._temp_connection is not None
    scene.finish_quick_menu(T.OUTPUT)
    assert scene._temp_connection is None
    new = next(item for item in scene.elements() if item.element_type is T.OUTPUT)
    assert conn_between(scene, a, new) is not None and new.pos().y() > 200 - 1
    scene.undo_stack.undo()
    assert len(scene.elements()) == 1 and scene.connections() == []


def test_quick_menu_can_be_dismissed(scene, view, qapp, monkeypatch):
    preferences.set_enabled(preferences.QUICK_MENU, True)
    monkeypatch.setattr(view, "show_quick_menu", lambda _pos: None)
    a = add(scene, T.PROCESS, 0, 0)
    drag(view, a.port_scene_pos("bottom"), QPointF(0, 200))
    scene.handle_escape()
    assert scene.connections() == [] and scene._temp_connection is None and len(scene.elements()) == 1


def test_a_click_on_a_port_is_no_drag(scene, view, qapp, monkeypatch):
    preferences.set_enabled(preferences.QUICK_MENU, True)
    shown = []
    monkeypatch.setattr(view, "show_quick_menu", shown.append)
    a = add(scene, T.PROCESS, 0, 0)
    drag(view, a.port_scene_pos("bottom"), a.port_scene_pos("bottom") + QPointF(2, 2))
    assert shown == []


def loose_end(scene, view, block, end_at):
    preferences.set_enabled(preferences.LOOSE_ENDS, True)
    drag(view, block.port_scene_pos("bottom"), end_at)
    return next(item for item in scene.elements() if item.data.properties.get(LOOSE_END_KEY))


def test_loose_end_stays_and_is_red(scene, view, qapp):
    a = add(scene, T.PROCESS, 0, 0)
    end = loose_end(scene, view, a, QPointF(0, 200))
    conn = conn_between(scene, a, end)
    assert conn.warning and conn.warning_level == rules.ERROR
    scene.undo_stack.undo()
    assert scene.connections() == [] and len(scene.elements()) == 1


def test_loose_end_can_be_moved_and_connected(scene, view, qapp):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 300, 300)
    end = loose_end(scene, view, a, QPointF(0, 200))
    preferences.set_enabled(preferences.LOOSE_ENDS, False)  # ein loses Ende bleibt trotzdem beweglich
    drag(view, end.pos(), QPointF(100, 240))
    assert end.pos() == QPointF(100, 240) and end.scene() is scene
    drag(view, end.pos(), b.pos())
    qapp.processEvents()
    conn = conn_between(scene, a, b)
    assert conn is not None and conn.warning is None
    assert not [item for item in scene.elements() if item.is_junction]


def test_deleting_the_arrow_takes_its_loose_end_along(scene, view, qapp):
    a = add(scene, T.PROCESS, 0, 0)
    end = loose_end(scene, view, a, QPointF(0, 200))
    scene.select_items([conn_between(scene, a, end)])
    scene.delete_selection()
    assert scene.elements() == [a]


def test_moving_the_fixed_side_keeps_the_loose_end_and_the_arrow(scene, view, qapp):
    a, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 300, 0)
    end = loose_end(scene, view, a, QPointF(0, 200))
    conn = conn_between(scene, a, end)
    scene.select_items([conn])
    drag(view, a.port_scene_pos("bottom"), b.pos())
    qapp.processEvents()
    moved = conn_between(scene, b, end)
    assert moved is not None and end.scene() is scene
    scene.undo_stack.undo()
    assert conn_between(scene, a, end) is not None and conn_between(scene, b, end) is None
    scene.undo_stack.redo()
    assert conn_between(scene, b, end) is not None


def test_moving_a_trunk_part_may_heal_the_arrow_without_crashing(scene, view, qapp):
    a, b, c = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 0, 300), add(scene, T.PROCESS, 300, 300)
    host = connect(scene, a, "bottom", b, "top")
    junction = scene.element(scene.insert_junction(host, QPointF(0, 150)))
    second = conn_between(scene, junction, b)
    scene.select_items([second])
    drag(view, b.port_scene_pos("top"), c.pos())
    qapp.processEvents()
    assert conn_between(scene, a, c) is not None or conn_between(scene, junction, c) is not None
    assert conn_between(scene, junction, b) is None and conn_between(scene, a, b) is None


def test_loose_end_survives_saving_and_does_not_disturb_analysis(document, view, tmp_path, qapp):
    scene = document.scene
    a = add(scene, T.PROCESS, 0, 0)
    end = loose_end(scene, view, a, QPointF(0, 200))
    path = tmp_path / "lose.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == []
    assert [item for item in reopened.scene.elements() if item.data.properties.get(LOOSE_END_KEY)]
    assert reopened.scene.connection_warnings() == scene.connection_warnings() != {}
    assert not any("Sackgasse" in issue.message and end.element_id in issue.element_ids for issue in run_checks(document))


# ---------------------------------------------------------------- Start und Ende
def test_new_project_starts_with_start_and_end(window):
    preferences.set_enabled(preferences.START_END, True)
    window.new_document()
    document = window.current_document()
    types = sorted(item.element_type.value for item in document.scene.elements())
    assert types == ["end", "start"] and len(document.scene.connections()) == 1
    assert not document.is_modified and document.is_blank()
    # neue Bausteine kommen dazwischen, auch ganz ohne Auswahl
    window.insert_element(T.PROCESS)
    window.insert_element(T.OUTPUT)
    assert not document.scene.connection_warnings() and not document.is_blank() and document.is_modified
    outs = {c.source.element_type: c.target.element_type for c in document.scene.connections()}
    assert outs == {T.START: T.PROCESS, T.PROCESS: T.OUTPUT, T.OUTPUT: T.END}


def test_start_and_end_can_be_switched_off_and_deleted(window):
    window.actions[preferences.action_name(preferences.START_END)].setChecked(True)
    window.actions[preferences.action_name(preferences.START_END)].trigger()
    assert not preferences.enabled(preferences.START_END)
    window.new_document()
    assert window.current_document().scene.elements() == []
    preferences.set_enabled(preferences.START_END, True)
    window.new_document()
    scene = window.current_scene()
    scene.select_all()
    scene.delete_selection()
    assert scene.elements() == []


def test_opening_a_file_replaces_the_untouched_new_project(window, tmp_path):
    preferences.set_enabled(preferences.START_END, True)
    other = DiagramDocument()
    add(other.scene, T.PROCESS, 0, 0)
    path = tmp_path / "datei.pap"
    other.save(str(path))
    window.new_document()
    assert window.open_file(str(path))
    assert window.tabs.count() == 1


# ---------------------------------------------------------------- Tasten
def test_digits_insert_blocks_in_palette_order(window, qapp):
    window.show()
    window.new_document()
    view = window.current_view()
    view.setFocus()
    qapp.processEvents()
    QTest.keyClick(view, Qt.Key.Key_3)
    QTest.keyClick(view, Qt.Key.Key_5)
    QTest.keyClick(view, Qt.Key.Key_1, Qt.KeyboardModifier.KeypadModifier)  # auch auf dem Ziffernblock
    qapp.processEvents()
    assert [item.element_type for item in view.document.scene.elements()] == [T.PROCESS, T.DECISION, T.INPUT]


def test_digit_in_the_text_editor_stays_text(window, qapp):
    window.show()
    window.new_document()
    view = window.current_view()
    view.setFocus()
    scene = view.document.scene
    window.insert_element(T.PROCESS)
    item = scene.elements()[0]
    scene.begin_element_edit(item, select_all=True)
    qapp.processEvents()
    QTest.keyClick(view.viewport(), Qt.Key.Key_3)
    QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
    qapp.processEvents()
    assert len(scene.elements()) == 1 and item.data.text == "3"


def test_function_can_lie_on_two_keys_and_a_taken_key_moves(window):
    actions = window.actions
    save = [QKeySequence("Ctrl+S"), QKeySequence("F3")]
    assert actions.assign("save", save) == []
    assert [s.toString() for s in actions["save"].shortcuts()] == ["Ctrl+S", "F3"]
    moved = actions.assign("open", [QKeySequence("F3")])
    assert moved == [(QKeySequence("F3"), "save")]
    assert [s.toString() for s in actions["save"].shortcuts()] == ["Ctrl+S"]
    custom = actions.custom_shortcuts()
    assert custom["open"] == ["F3"] and "new" not in custom
    actions.reset_shortcuts()
    assert actions.custom_shortcuts() == {}


def test_own_keys_survive_a_restart(qapp, window):
    window.actions.assign("save", [QKeySequence("F3"), QKeySequence("F4")])
    window._on_shortcuts_changed()
    second = MainWindow()
    try:
        assert [s.toString() for s in second.actions["save"].shortcuts()] == ["F3", "F4"]
    finally:
        second.close()


def test_palette_shows_the_current_key(window):
    entry = next(e for e in window.palette.entries if e.element_type is T.PROCESS)
    assert entry.key_hint == "3"
    window.actions.assign(insert_action_name(T.PROCESS), [QKeySequence("V")])
    window._on_shortcuts_changed()
    assert entry.key_hint == "V"


def test_settings_table_search_and_assign(window):
    dialog = SettingsDialog(window.actions, window, show_shortcuts=True)
    table = dialog.shortcut_table
    table.search.setText("speichern")
    shown = [table.names[row] for row in range(table.table.rowCount()) if not table.table.isRowHidden(row)]
    assert "save" in shown and "open" not in shown
    table.search.clear()
    edit = table.edits["save"][1]
    edit.setKeySequence(QKeySequence("F7"))
    table._assign("save")
    assert QKeySequence("F7") in window.actions["save"].shortcuts()
    table._reset_all()
    assert QKeySequence("F7") not in window.actions["save"].shortcuts()


def test_settings_switch_changes_the_program(window):
    dialog = SettingsDialog(window.actions, window)
    name = preferences.action_name(preferences.LOOSE_ENDS)
    box = dialog.switches[name]
    assert not box.isChecked()
    box.click()
    assert preferences.enabled(preferences.LOOSE_ENDS) and window.actions[name].isChecked()
    assert window.settings_store.preference(preferences.LOOSE_ENDS) is True


def test_help_list_can_be_searched_and_shows_real_keys(window):
    window.actions.assign("save", [QKeySequence("F3")])
    dialog = ShortcutsDialog(window, window.actions)
    keys = [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())]
    assert "F3" in keys
    dialog.search.setText("zoom")
    visible = [row for row in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(row)]
    assert visible and all("oom" in dialog.table.item(row, 1).text() or not dialog.table.item(row, 1).text()
                           for row in visible)


# ---------------------------------------------------------------- Zwischenablage belegt
def test_cut_keeps_the_blocks_if_the_clipboard_is_busy(window, monkeypatch):
    from app import clipboard

    window.new_document()
    scene = window.current_scene()
    block = add(scene, T.PROCESS, 0, 0)
    scene.select_items([block])
    errors = []
    monkeypatch.setattr(clipboard, "set_clipboard", lambda *args, **kwargs: False)
    monkeypatch.setattr(window, "_error", lambda title, text: errors.append(text))
    window.cut()
    assert block.scene() is scene and len(errors) == 1
    window.copy()
    assert len(errors) == 2


# ---------------------------------------------------------------- Suche
def test_search_ignores_case_and_umlauts():
    for query in ("prüf", "PRUEF", "pruf"):
        assert matches(query, "Prüfung")
    assert matches("start ende", "Mit Start und Ende beginnen")
    assert not matches("start ende", "Mit Start beginnen")
    assert score("sp", "Speichern") < score("sp", "Bausteine", "Speichern")


def test_search_finds_functions_settings_and_blocks(window):
    window.new_document()
    scene = window.current_scene()
    block = add(scene, T.PROCESS, 0, 0)
    block.set_text("Mehrwertsteuer berechnen")
    bar = window.search_bar
    bar.setText("mehrwert")
    assert [entry.title for entry in bar.entries] == ["Mehrwertsteuer berechnen"]
    bar.run_current()
    assert block.isSelected() and bar.text() == ""
    bar.setText("schnellmenü")
    assert bar.entries[0].title == "Schnellmenü im Leeren" and bar.entries[0].detail.startswith(("ein", "aus"))
    bar.setText("zoom")
    assert any("100" in entry.title for entry in bar.entries)
    bar.setText("gibtesnicht")
    assert bar.entries == [] and bar.results.count() == 1


def test_search_runs_a_function(window):
    window.new_document()
    bar = window.search_bar
    bar.setText("raster anzeigen")
    before = window.actions["toggle_grid"].isChecked()
    bar.run_current()
    assert window.actions["toggle_grid"].isChecked() is not before


# ---------------------------------------------------------------- Automatisch anordnen
def crossing_lines(scene):
    blocks = [i for i in scene.elements() if not i.is_junction and not i.is_comment]
    found = 0
    for conn in scene.connections():
        for item in blocks:
            if item in (conn.source, conn.target):
                continue
            r = item.scene_rect()
            rect = routing.Rect(r.left(), r.top(), r.right(), r.bottom())
            found += any(routing.segment_crosses_rect(a, b, rect) for a, b in zip(conn.points()[:-1], conn.points()[1:]))
    return found


def test_layout_of_nested_decisions_is_clean_and_keeps_the_flow(qapp):
    document = DiagramDocument.open_file("assets/examples/Lernbeispiel_2_Verzweigungen.pap")
    scene = document.scene
    before = document.flow_graph().collapse_junctions()
    edges = sorted((e.source, e.target) for e in before.edges)
    assert apply_layout(scene, plan_auto_layout(scene))
    assert crossing_lines(scene) == 0
    after = document.flow_graph().collapse_junctions()
    assert sorted((e.source, e.target) for e in after.edges) == edges
    for junction in (i for i in scene.elements() if i.is_junction):
        assert not any(b.scene_rect().contains(junction.pos()) for b in scene.elements() if not b.is_junction)
    while scene.undo_stack.canUndo():
        scene.undo_stack.undo()
    assert sorted((e.source, e.target) for e in document.flow_graph().collapse_junctions().edges) == edges


def test_layout_removes_plain_corners_and_keeps_labels(scene):
    d, a, e = add(scene, T.DECISION, 0, 0), add(scene, T.PROCESS, 0, 300), add(scene, T.END, 0, 600)
    corner = add(scene, T.JUNCTION, 300, 0)
    corner2 = add(scene, T.JUNCTION, 300, 450)
    connect(scene, d, "bottom", a, "top").set_label("ja")
    connect(scene, d, "right", corner, "left").set_label("nein")
    connect(scene, corner, "bottom", corner2, "top")
    connect(scene, a, "bottom", e, "top")
    connect(scene, corner2, "bottom", e, "right")
    assert apply_layout(scene, plan_auto_layout(scene))
    assert not [item for item in scene.elements() if item.is_junction]
    assert conn_between(scene, d, e).data.label == "nein"


def test_layout_keeps_a_loop_back_through_a_corner(document, tmp_path):
    scene = document.scene
    s, d, e = add(scene, T.START, 0, 0), add(scene, T.DECISION, 0, 200), add(scene, T.END, 0, 500)
    corner = add(scene, T.JUNCTION, 300, 200)
    connect(scene, s, "bottom", d, "top")
    connect(scene, d, "bottom", corner, "left").set_label("ja")
    connect(scene, corner, "top", d, "right")
    connect(scene, d, "left", e, "top").set_label("nein")
    apply_layout(scene, plan_auto_layout(scene))
    loop = conn_between(scene, d, d)
    assert loop is not None and loop.data.label == "ja" and loop.data.source_port != loop.data.target_port
    path = tmp_path / "schleife.pap"
    document.save(str(path))
    again = DiagramDocument.open_file(str(path))
    assert len(again.scene.connections()) == len(scene.connections())


def test_corner_loop_on_the_same_port_stays_a_real_line(document, tmp_path):
    scene = document.scene
    s, d, e = add(scene, T.START, 0, 0), add(scene, T.DECISION, 0, 200), add(scene, T.END, 300, 500)
    corner = add(scene, T.JUNCTION, 0, 400)
    connect(scene, s, "bottom", d, "top")
    connect(scene, d, "bottom", corner, "top").set_label("ja")
    connect(scene, corner, "left", d, "bottom")
    connect(scene, d, "right", e, "top").set_label("nein")
    apply_layout(scene, plan_auto_layout(scene))
    path = tmp_path / "gleich.pap"
    document.save(str(path))
    again = DiagramDocument.open_file(str(path))
    assert again.load_warnings == [] and len(again.scene.connections()) == len(scene.connections())
    assert any(c.source is c.target and c.data.label == "ja" for c in again.scene.connections())


def test_layout_keeps_the_order_of_exits(scene):
    s, j, a, b = add(scene, T.START, 0, 0), add(scene, T.JUNCTION, 0, 200), add(scene, T.PROCESS, 400, 400), \
        add(scene, T.PROCESS, 0, 400)
    connect(scene, s, "bottom", j, "top")
    connect(scene, j, "bottom", a, "top")
    connect(scene, j, "right", b, "top")
    from app.analysis.graph import FlowGraph
    before = FlowGraph.from_scene(scene).successors(j.element_id)
    apply_layout(scene, plan_auto_layout(scene))
    assert FlowGraph.from_scene(scene).successors(j.element_id) == before


def test_layout_repairs_trunk_references(scene):
    a, c, b = add(scene, T.PROCESS, 0, 0), add(scene, T.PROCESS, 300, 0), add(scene, T.PROCESS, 0, 400)
    s = add(scene, T.START, 0, -200)
    connect(scene, s, "bottom", a, "top")
    host = connect(scene, a, "bottom", b, "top")
    junction = scene.element(scene.insert_junction(host, QPointF(0, 200)))
    trunk_in = conn_between(scene, a, junction)
    corner = scene.element(scene.insert_junction(trunk_in, QPointF(0, 100)))
    connect(scene, c, "bottom", junction, "right")
    apply_layout(scene, plan_auto_layout(scene))
    assert corner.scene() is None
    kept = conn_between(scene, a, junction)
    assert junction.data.properties["trunk_in"] == kept.connection_id
    scene.undo_stack.undo()
    assert corner.scene() is scene and junction.data.properties["trunk_in"] == conn_between(scene, corner, junction).connection_id


def test_comment_without_line_moves_with_the_nearest_block(scene):
    s, a, e = add(scene, T.START, 0, 0), add(scene, T.PROCESS, 500, 100), add(scene, T.END, 0, 500)
    connect(scene, s, "bottom", a, "top")
    connect(scene, a, "bottom", e, "top")
    note = add(scene, T.COMMENT, 700, 100)
    apply_layout(scene, plan_auto_layout(scene))
    assert abs((note.pos().x() - a.pos().x()) - 200) < 1 and note.pos().y() == a.pos().y()
    assert not note.scene_rect().intersects(a.scene_rect())
