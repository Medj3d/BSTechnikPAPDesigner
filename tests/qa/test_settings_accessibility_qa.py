"""QA für Tastaturwege, Einstellungen und Qt-Accessibility."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtGui import QAccessible, QColor, QKeySequence
from PySide6.QtTest import QTest

from app import preferences, styles
from app.actions import insert_action_name
from app.dialogs.settings import SettingsDialog
from app.main_window import MainWindow
from app.model.element_types import ElementType
from app.update_dialogs import UpdateController


@pytest.fixture
def main_windows(qapp, monkeypatch, tmp_path):
    """Benutzereinstellungen und reale Bildschirmfenster aus dem Test heraushalten."""
    from app import clipboard, settings_store, subprograms

    profile = str(tmp_path / "profile.ini")

    def ini_settings(*_args):
        return QSettings(profile, QSettings.Format.IniFormat)

    monkeypatch.setattr(settings_store, "QSettings", ini_settings)
    monkeypatch.setattr(clipboard, "can_paste", lambda: False)
    monkeypatch.setattr(subprograms, "can_paste_page", lambda: False)
    monkeypatch.setattr(UpdateController, "disabled_by_policy", lambda _self: False)
    preferences.reset()
    windows = []

    def create():
        window = MainWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        window.show()
        windows.append(window)
        qapp.processEvents()
        return window

    yield create

    qapp.processEvents()
    for window in reversed(windows):
        for view in window.views():
            view.document.scene.cancel_edit()
            view.document.undo_stack.setClean()
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def focus_canvas(window, qapp):
    """Getestet werden Qt-Fensterereignisse mit dem Fokus auf der Zeichenfläche."""
    view = window.current_view()
    window.activateWindow()
    qapp.processEvents()
    if not window.isActiveWindow():
        qapp.setActiveWindow(window)
    view.setFocus()
    qapp.processEvents()
    assert qapp.focusWidget() is view
    return view


def set_key(dialog, action_name, slot, sequence):
    edit = dialog.shortcut_table.edits[action_name][slot]
    edit.setKeySequence(QKeySequence(sequence))
    edit.editingFinished.emit()


def test_all_dialog_switches_and_shortcuts_survive_reopen(main_windows):
    first = main_windows()
    dialog = SettingsDialog(first.actions, first)
    dialog.shortcuts_changed.connect(first._on_shortcuts_changed)
    expected = {}
    for name, checkbox in dialog.switches.items():
        assert checkbox.isEnabled()
        expected[name] = not checkbox.isChecked()
        checkbox.click()
        assert first.actions[name].isChecked() == expected[name]
        if name.startswith("preference_tool_"):
            group = first._toolbar_groups[name.removeprefix("preference_")]
            assert all(entry.isVisible() is expected[name] for entry in group)
    assert len(expected) == len(preferences.PREFERENCES) + 3
    set_key(dialog, "save", 0, "F8")
    first.close()
    preferences.reset()
    second = main_windows()
    reopened = SettingsDialog(second.actions, second)
    assert {name: checkbox.isChecked() for name, checkbox in reopened.switches.items()} == expected
    assert second.actions["save"].shortcut() == QKeySequence("F8")

    reopened.reset_switches()
    for preference in preferences.PREFERENCES:
        name = preferences.action_name(preference.name)
        assert reopened.switches[name].isChecked() is preference.default
    assert second.actions["save"].shortcut() == QKeySequence("F8")
    assert second.settings_store.backup_on_save()
    assert second.settings_store.check_updates_on_start()


def test_two_distinct_shortcuts_on_same_command_work(main_windows, qapp):
    window = main_windows()
    window.new_document()
    target = focus_canvas(window, qapp)
    dialog = SettingsDialog(window.actions, window)
    set_key(dialog, "new", 0, "F7")
    set_key(dialog, "new", 1, "F8")
    QTest.keyClick(target, Qt.Key.Key_F7)
    QTest.keyClick(target, Qt.Key.Key_F8)
    assert window.tabs.count() == 3


def test_escape_leaves_presentation_with_no_selection(main_windows, qapp):
    window = main_windows()
    window.new_document()
    target = focus_canvas(window, qapp)
    QTest.keyClick(target, Qt.Key.Key_F11)
    assert window.presenting
    assert not window.current_scene().selectedItems()
    QTest.keyClick(target, Qt.Key.Key_Escape)
    assert not window.presenting


@pytest.mark.skipif(sys.platform != "win32", reason="Gegenprobe mit dem Windows-Qt-Backend.")
def test_tab_in_canvas_selects_first_flow_element(main_windows, qapp):
    window = main_windows()
    window.new_document()
    target = focus_canvas(window, qapp)
    assert {item.element_type for item in window.current_scene().elements()} == {
        ElementType.START, ElementType.END,
    }
    QTest.keyClick(target, Qt.Key.Key_Tab)
    assert [item.element_type for item in window.current_scene().selected_elements()] == [ElementType.START]


def test_same_shortcut_in_both_slots_does_not_disable_action(main_windows, qapp):
    window = main_windows()
    window.new_document()
    target = focus_canvas(window, qapp)
    dialog = SettingsDialog(window.actions, window)
    set_key(dialog, "new", 0, "F7")
    set_key(dialog, "new", 1, "F7")
    QTest.keyClick(target, Qt.Key.Key_F7)
    assert window.tabs.count() == 2


def test_old_edit_text_shortcut_stops_after_reassignment(main_windows, qapp):
    window = main_windows()
    window.new_document()
    target = focus_canvas(window, qapp)
    scene = window.current_scene()
    scene.select_items([next(item for item in scene.elements() if item.element_type is ElementType.START)])
    dialog = SettingsDialog(window.actions, window)
    set_key(dialog, "edit_text", 0, "F7")
    QTest.keyClick(target, Qt.Key.Key_F7)
    assert scene.is_editing
    scene.cancel_edit()
    QTest.keyClick(target, Qt.Key.Key_F2)
    assert not scene.is_editing


def test_page_add_button_tooltip_uses_current_shortcut(main_windows):
    window = main_windows()
    dialog = SettingsDialog(window.actions, window)
    dialog.shortcuts_changed.connect(window._on_shortcuts_changed)
    set_key(dialog, "new_subprogram", 0, "F7")
    assert "F7" in window.page_bar.add_button.toolTip()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="QCheckBox spiegelt die per Richtlinie deaktivierte Aktion nicht.")
def test_updates_switch_is_disabled_under_admin_policy(main_windows, monkeypatch):
    monkeypatch.setattr(UpdateController, "disabled_by_policy", lambda _self: True)
    window = main_windows()
    dialog = SettingsDialog(window.actions, window)
    assert not window.actions["check_updates_on_start"].isEnabled()
    toggle = dialog.switches["check_updates_on_start"]
    toggle.click()
    assert not toggle.isChecked() and not toggle.isEnabled()


def test_explicit_save_persists_project_grid_settings(main_windows, tmp_path):
    window = main_windows()
    window.new_document()
    path = str(tmp_path / "Raster.pap")
    window.current_document().save(path)
    window.actions["toggle_grid"].trigger()
    window.actions["toggle_snap"].trigger()
    assert not window.current_document().settings.grid_visible
    assert not window.current_document().settings.snap_to_grid
    assert window.save_document(window.current_document())
    assert window.close_tab(0)
    assert window.open_file(path)
    assert not window.actions["toggle_grid"].isChecked()
    assert not window.actions["toggle_snap"].isChecked()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Raster und Einrasten setzen beim Umschalten kein Dirty-Flag.")
def test_view_switches_survive_close_and_reopen(main_windows, tmp_path):
    window = main_windows()
    window.new_document()
    path = str(tmp_path / "Raster.pap")
    window.current_document().save(path)
    window.actions["toggle_grid"].trigger()
    window.actions["toggle_snap"].trigger()
    assert window.close_tab(0)
    assert window.open_file(path)
    assert not window.actions["toggle_grid"].isChecked()
    assert not window.actions["toggle_snap"].isChecked()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Paletteneinträge sind weder per Tab fokussierbar noch als Buttons zugänglich.")
def test_palette_entry_exposes_keyboard_and_accessibility_activation(main_windows):
    window = main_windows()
    window.new_document()
    entry = window.palette.entries[0]
    accessible = QAccessible.queryAccessibleInterface(entry)
    assert accessible.text(QAccessible.Text.Name) == entry.label
    assert accessible.state().focusable
    assert accessible.role() == QAccessible.Role.Button
    assert accessible.actionInterface().actionNames()


@pytest.mark.parametrize("tool", ["simulation_run", "diagnostics_refresh"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Das Symbol hat eine Beschreibung, aber keinen Accessible Name.")
def test_icon_buttons_expose_accessible_names(main_windows, tool):
    window = main_windows()
    button = (window.simulation_panel.run_button if tool == "simulation_run"
              else window.diagnostics_panel._refresh_button)
    accessible = QAccessible.queryAccessibleInterface(button)
    assert accessible.role() == QAccessible.Role.Button
    assert accessible.text(QAccessible.Text.Name).strip()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Ein langes Kürzel verdeckt die Bausteinbeschriftung.")
def test_palette_label_remains_visible_with_long_shortcut(main_windows, qapp):
    window = main_windows()
    window.new_document()
    entry = next(entry for entry in window.palette.entries if entry.element_type is ElementType.SUBPROGRAM)
    text_color = QColor(styles.current_theme().text).rgb()

    def text_pixel_count():
        image = entry.grab().toImage()
        return sum(image.pixel(x, y) == text_color
                   for y in range(image.height()) for x in range(image.width()))

    if not text_pixel_count():
        pytest.fail("Die Vergleichsaufnahme enthält vor der Umbelegung keine Textfarbe.")
    dialog = SettingsDialog(window.actions, window)
    dialog.shortcuts_changed.connect(window._on_shortcuts_changed)
    set_key(dialog, insert_action_name(ElementType.SUBPROGRAM), 0, "Ctrl+Alt+Shift+F12")
    qapp.processEvents()
    assert text_pixel_count()


def wcag_contrast(first, second):
    def luminance(color):
        channels = (int(color[offset:offset + 2], 16) / 255 for offset in (1, 3, 5))
        linear = (channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                  for channel in channels)
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("theme", [styles.DARK, styles.LIGHT_UI], ids=["dunkel", "hell"])
def test_normal_canvas_symbol_text_meets_aa(theme):
    for element_type in ElementType:
        colors = theme.element_colors(element_type)
        assert wcag_contrast(colors.text, colors.fill) >= 4.5, element_type


@pytest.mark.parametrize(
    "theme,background",
    [(styles.DARK, "accent"), (styles.DARK, "accent_hover"), (styles.LIGHT_UI, "accent_hover")],
    ids=["dunkel-standard", "dunkel-hover", "hell-hover"],
)
def test_default_button_text_meets_aa(theme, background):
    colors = theme.accent_text, getattr(theme, background)
    ratio = wcag_contrast(*colors)
    assert ratio >= 4.5, f"{colors}: {ratio:.3f}:1"
