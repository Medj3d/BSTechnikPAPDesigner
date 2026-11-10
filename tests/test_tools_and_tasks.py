"""Zusatzknöpfe, Code-Ansicht, Minikarte, Haltepunkte, Aufgaben (Lehrermodus) und Namenszeile im Export."""

from __future__ import annotations

import os

import pytest
from PySide6.QtCore import Qt

from app import export, preferences, task as T
from app.codegen.generators import generate, generate_traced
from app.commands import ProjectPropertiesCommand
from app.fileformat.serializer import load_diagram, save_diagram
from app.simulation import breakpoints

EXAMPLES = os.path.join(os.path.dirname(__file__), os.pardir, "assets", "examples")
EXAMPLE = os.path.join(EXAMPLES, "Lernbeispiel_1_Ablaufplan.pap")


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    from app.main_window import MainWindow
    from app.settings_store import SettingsStore
    store = SettingsStore()
    # Jeder Test beginnt mit der schlichten Werkzeugleiste; gespeicherte Schalter dürfen andere Tests nicht
    # beeinflussen (das Zurücksetzen schreibt z. B. „Mit Start und Ende beginnen“ in die Einstellungen)
    for group in ("preferences", "view", "export"):
        store._settings.remove(group)
    for key in preferences.TOOLS:
        preferences.set_enabled(key, False)
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()
    for group in ("preferences", "view", "export"):
        store._settings.remove(group)


def enable_tools(window, *keys):
    for key in keys:
        action = window.actions[preferences.action_name(key)]
        if not action.isChecked():
            action.trigger()


# ------------------------------------------------------------------ Werkzeugleiste
def test_toolbar_is_simple_by_default(window):
    visible = [action for action in window.toolbar.actions() if action.isVisible() and not action.isSeparator()]
    assert window.actions["delete"] in visible and window.actions["auto_layout"] in visible
    for name in ("toggle_code_view", "toggle_minimap", "toggle_breakpoint", "toggle_task"):
        assert not window.actions[name].isVisible()
    for entries in window._toolbar_groups.values():
        assert not any(entry.isVisible() for entry in entries)


def test_tools_switch_on_buttons_and_reset(window, qapp):
    enable_tools(window, *preferences.TOOLS)
    for name in ("toggle_code_view", "toggle_minimap", "toggle_breakpoint", "toggle_task", "edit_task"):
        assert window.actions[name].isVisible()
    assert all(entry.isVisible() for entries in window._toolbar_groups.values() for entry in entries)
    from app.dialogs.settings import SettingsDialog
    dialog = SettingsDialog(window.actions, window)
    dialog.reset_switches()
    assert not window.actions["toggle_code_view"].isVisible()
    assert window.settings_store.preference(preferences.TOOL_CODE_VIEW) is False


def test_toolbar_proxy_follows_action(window):
    enable_tools(window, preferences.TOOL_GRID)
    proxy = next(entry for entry in window._toolbar_groups[preferences.TOOL_GRID]
                 if entry.property("source") is window.actions["toggle_grid"])
    window.new_document()
    before = window.actions["toggle_grid"].isChecked()
    proxy.trigger()
    assert window.actions["toggle_grid"].isChecked() == (not before) == proxy.isChecked()


# ------------------------------------------------------------------ Code-Ansicht
def test_traced_code_equals_normal_code_and_maps_lines(window):
    window.open_file(EXAMPLE)
    document = window.current_document()
    from app.analysis.structure import structure_diagram
    programs = structure_diagram(document.flow_graph())
    for language in ("pseudo", "python", "java"):
        code, ids = generate_traced(programs, language, document.meta.name)
        assert code == generate(programs, language, document.meta.name)
        assert len(ids) == len(code.split("\n"))
        known = {item.element_id for item in document.scene.elements()}
        assert {eid for eid in ids if eid} and {eid for eid in ids if eid} <= known


def test_code_view_selects_block_and_highlights_lines(window, qapp):
    enable_tools(window, preferences.TOOL_CODE_VIEW)
    window.open_file(EXAMPLE)
    window.actions["toggle_code_view"].trigger()
    qapp.processEvents()
    panel = window.code_panel
    assert panel.code()
    row = next(index for index, eid in enumerate(panel.line_ids) if eid)
    panel.click_row(row)
    qapp.processEvents()
    selected = [item.element_id for item in window.current_document().scene.selected_elements()]
    assert selected == [panel.line_ids[row]]
    assert row in panel.highlighted_rows()


# ------------------------------------------------------------------ Minikarte
def test_minimap_shows_and_moves_view(window, qapp):
    window.open_file(EXAMPLE)
    view = window.current_view()
    assert not view.minimap.isVisible()
    enable_tools(window, preferences.TOOL_MINIMAP)
    qapp.processEvents()
    assert view.minimap.isVisible()
    view.minimap.repaint()
    before = view.visible_center()
    point = view.minimap.scene_point(view.minimap.rect().topLeft() + view.minimap.rect().center() * 0.2)
    view.centerOn(point)
    assert view.visible_center() != before
    window.actions["toggle_minimap"].trigger()
    assert not view.minimap.isVisible()


# ------------------------------------------------------------------ Haltepunkte
def test_breakpoint_stops_run(window, qapp):
    enable_tools(window, preferences.TOOL_BREAKPOINTS)
    window.open_file(EXAMPLE)
    document = window.current_document()
    output = next(item for item in document.scene.elements() if item.element_type.value == "output")
    document.scene.select_items([output])
    window.actions["toggle_breakpoint"].trigger()
    assert breakpoints.has_breakpoint(document, output.element_id)
    assert any(isinstance(child, breakpoints.BreakpointMarker) for child in output.childItems())
    panel = window.simulation_panel
    window.simulation_dock.show()
    panel.run()
    panel.input_field.setText("2")
    panel.submit_input()
    panel.run()
    assert panel.simulator.current == output.element_id and not panel.simulator.finished
    assert "Haltepunkt" in panel.status.text()
    assert "fläche" in panel.changed_variables() or panel.changed_variables()
    panel.run()
    assert panel.simulator.finished
    window.actions["clear_breakpoints"].trigger()
    assert not any(isinstance(child, breakpoints.BreakpointMarker) for child in output.childItems())


# ------------------------------------------------------------------ Aufgaben
def test_encryption_round_trip_and_wrong_password():
    data = T.encrypt("Lösung: a + b ✓", "geheim")
    assert "Lösung" not in data and T.decrypt(data, "geheim") == "Lösung: a + b ✓"
    with pytest.raises(T.WrongPassword):
        T.decrypt(data, "falsch")
    lock = T.make_lock("geheim")
    assert T.check_lock(lock, "geheim") and not T.check_lock(lock, "Geheim")


def test_task_is_saved_and_shown_on_open(window, qapp, tmp_path):
    window.new_document()
    document = window.current_document()
    meta = document.meta.copy()
    T.apply_task(meta, T.Task("Aufgabe 1", "Summe zweier Zahlen", T.encrypt("a+b", "pw"), T.make_lock("pw")))
    grid = document.settings.grid_size
    document.undo_stack.push(ProjectPropertiesCommand(document, document.meta, meta, grid, grid))
    path = str(tmp_path / "aufgabe.pap")
    save_diagram(document.to_diagram(), path)
    loaded = load_diagram(path).diagram.meta
    assert (loaded.task_title, loaded.task_text) == ("Aufgabe 1", "Summe zweier Zahlen")
    assert T.decrypt(loaded.task_solution, "pw") == "a+b"
    window.task_dock.hide()
    window.open_file(path)
    qapp.processEvents()
    assert not window.task_dock.isHidden() and window.actions["toggle_task"].isVisible()
    assert window.task_panel.title.text() == "Aufgabe 1"
    assert window.task_panel.solution_button.isVisibleTo(window.task_panel)


def test_file_without_task_stays_unchanged(tmp_path):
    diagram = load_diagram(EXAMPLE).diagram
    path = str(tmp_path / "ohne.pap")
    save_diagram(diagram, path)
    with open(path, encoding="utf-8") as handle:
        assert "TASK_" not in handle.read()


# ------------------------------------------------------------------ Namenszeile
def test_stamp_is_drawn_bottom_right(window, qapp, tmp_path):
    window.open_file(EXAMPLE)
    scene = window.current_document().scene
    plain = export.render_image(scene, export.ExportOptions(scale=1.0))
    stamped = export.render_image(scene, export.ExportOptions(scale=1.0, stamp="Max Muster · 10b · 10.11.2026"))
    assert stamped.height() >= plain.height()
    corner = [stamped.pixelColor(x, y).lightness() for x in range(stamped.width() - 200, stamped.width() - 10)
              for y in range(stamped.height() - 26, stamped.height() - 4)]
    assert min(corner) < 200   # dort steht Text
    assert export.stamp_text("Max", "", "1.1.2027") == "Max · 1.1.2027"
