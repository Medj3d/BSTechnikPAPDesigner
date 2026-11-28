"""Neue Standard-Tastenkürzel, einheitlicher Name „Bausteine“ und der Menüeintrag Hilfe → Schreibweisen im Plan."""

from __future__ import annotations

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel, QMenu

from app.actions import clean_text, sequence_text
from app.dialogs.settings import ShortcutTable
from app.dialogs.shortcuts import SHORTCUTS, ShortcutsDialog
from app.palette import ToolPalette

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEW_DEFAULTS = {
    "toggle_code_view": "F12",
    "export_png": "Ctrl+Shift+E",
    "print_preview": "Ctrl+Shift+P",
    "clear_breakpoints": "Ctrl+Shift+F9",
    "toggle_palette": "Ctrl+B",
    "notation_help": "Shift+F1",
}


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    from app.settings_store import SettingsStore

    store = SettingsStore()
    for group in ("preferences", "view", "window", "shortcuts"):
        store._settings.remove(group)
    win = MainWindow(enable_autosave=False, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()
    qapp.processEvents()


def _menu_entries(menu: QMenu) -> list:
    found = []
    for action in menu.actions():
        found.append(action)
        if action.menu() is not None:
            found += _menu_entries(action.menu())
    return found


def _menus(window) -> dict[str, list]:
    return {clean_text(action.text()): _menu_entries(action.menu()) for action in window.menuBar().actions()}


# ------------------------------------------------------------------ Tastenkürzel
@pytest.mark.parametrize("name, key", NEW_DEFAULTS.items())
def test_new_default_shortcut(window, name, key):
    action = window.actions[name]
    assert action.shortcuts()[0] == QKeySequence(key)
    assert window.actions.default_shortcuts(name)[0] == QKeySequence(key)
    # Kurzinfo mit Kürzel wie bei allen anderen Befehlen („Code-Ansicht (F12)“)
    assert action.toolTip().endswith(f"({sequence_text(QKeySequence(key))})"), action.toolTip()


def test_no_two_commands_share_a_default_key(window):
    owners: dict[str, str] = {}
    for name in window.actions.bindable():
        for sequence in window.actions.default_shortcuts(name):
            text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            assert text not in owners, f"{text}: {owners.get(text)} und {name}"
            owners[text] = name
    # die Tasten des Schreibtischtests und der Präsentation bleiben, wie sie sind
    for key, name in (("F5", "simulation_run"), ("F6", "simulation_play"), ("F9", "toggle_breakpoint"),
                      ("F10", "simulation_step"), ("Ctrl+F10", "simulation_back"), ("F11", "presentation"),
                      ("Ctrl+E", "export_pdf"), ("Ctrl+K", "search"), ("F1", "shortcuts")):
        assert owners[key] == name


def test_new_keys_are_in_the_menus_and_the_settings(window):
    menus = _menus(window)
    for name in NEW_DEFAULTS:
        assert any(window.actions[name] in entries for entries in menus.values()), name
    assert "toggle_palette" in window.actions.bindable()
    table = ShortcutTable(window.actions)
    row = table.names.index("toggle_palette")
    assert table.table.item(row, 0).text() == "Bausteine"
    assert table.edits["toggle_code_view"][0].keySequence() == QKeySequence("F12")
    table.deleteLater()


def test_f1_help_lists_the_new_keys_with_the_current_binding(window):
    dialog = ShortcutsDialog(window, window.actions)
    rows = {dialog.table.item(row, 1).text(): dialog.table.item(row, 0).text()
            for row in range(dialog.table.rowCount())}
    shown = set(rows.values())
    for key in NEW_DEFAULTS.values():
        assert sequence_text(QKeySequence(key)) in shown, key
    window.actions.assign("toggle_code_view", [QKeySequence("Ctrl+Alt+F7")])
    dialog = ShortcutsDialog(window, window.actions)
    rows = {dialog.table.item(row, 1).text(): dialog.table.item(row, 0).text()
            for row in range(dialog.table.rowCount())}
    assert rows["Code-Ansicht neben dem Plan ein-/ausblenden"] == sequence_text(QKeySequence("Ctrl+Alt+F7"))


def test_new_shortcuts_trigger_their_commands(window):
    code = window.actions["toggle_code_view"]
    palette = window.actions["toggle_palette"]
    before_code, before_palette = window.code_dock.isVisible(), window.palette_dock.isVisible()
    code.trigger()
    palette.trigger()
    assert window.code_dock.isVisible() is not before_code
    assert window.palette_dock.isVisible() is not before_palette
    code.trigger()
    palette.trigger()
    assert window.code_dock.isVisible() is before_code and window.palette_dock.isVisible() is before_palette


# ------------------------------------------------------------------ Name „Bausteine“
def test_panel_and_menu_entry_have_the_same_name(window):
    assert window.palette_dock.windowTitle() == "Bausteine"
    toggle = window.actions["toggle_palette"]
    assert clean_text(toggle.text()) == "Bausteine"
    assert toggle in _menus(window)["Ansicht"]
    assert toggle.toolTip() == f"Bausteine ({sequence_text(QKeySequence('Ctrl+B'))})"


def test_no_word_werkzeugpalette_left_in_the_interface(window):
    texts = []
    for action in window.findChildren(type(window.actions["new"])):
        texts += [action.text(), action.toolTip(), action.statusTip()]
    texts += [widget.toolTip() for widget in window.findChildren(QLabel)]
    texts += [key + " " + function for key, function in SHORTCUTS]
    assert not [text for text in texts if "palette" in text.lower()], [t for t in texts if "palette" in t.lower()]


def test_panel_has_no_second_heading_but_keeps_the_flow_section_and_hints(qapp):
    palette = ToolPalette()
    sections = [label.text() for label in palette.findChildren(QLabel) if label.objectName() == "PaletteSection"]
    assert sections == ["ABLAUF"]   # „BAUSTEINE“ ist weg, die Trennung „ABLAUF“ (Start/Ende) bleibt
    assert "Ziehen oder klicken zum Einfügen." in palette.hints
    assert "Rot = Fehler" in palette.hints
    content = palette.entries[0].parentWidget()
    assert content.toolTip() == palette.hints
    palette.deleteLater()


def test_dock_title_carries_the_hints(window):
    assert window.palette_dock.toolTip() == window.palette.hints


def test_readme_uses_the_same_name():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    # Versionstabelle (Zeilen „| 1.x | Datum | …“) bleibt, wie sie war
    described = [line for line in lines if not line.startswith("| 1.")]
    assert not [line for line in described if "Werkzeugpalette" in line]
    assert any("Schreibweisen im Plan" in line for line in described)


# ------------------------------------------------------------------ Hilfe → Schreibweisen
def test_help_menu_entry_opens_the_notation_dialog(window, monkeypatch):
    from app.dialogs.notation import NotationDialog

    help_entries = _menus(window)["Hilfe"]
    action = window.actions["notation_help"]
    assert help_entries.index(action) == help_entries.index(window.actions["shortcuts"]) + 1
    opened = []
    monkeypatch.setattr(NotationDialog, "exec", lambda dialog: opened.append(dialog) or 0)
    action.trigger()
    assert len(opened) == 1 and opened[0].windowTitle() == "Schreibweisen im Plan"


def test_f1_dialog_has_a_button_to_the_notation_help(window, monkeypatch):
    from app.dialogs.notation import NotationDialog

    opened = []
    monkeypatch.setattr(NotationDialog, "exec", lambda dialog: opened.append(dialog) or 0)
    dialog = ShortcutsDialog(window, window.actions)
    assert dialog.notation_button.text() == "Schreibweisen im Plan …"
    dialog.notation_button.click()
    assert opened


def test_search_finds_the_notation_help(window):
    entries = window.search_entries()
    found = [entry for entry in entries if entry.title == "Schreibweisen im Plan"]
    assert found and found[0].detail == sequence_text(QKeySequence("Shift+F1"))
