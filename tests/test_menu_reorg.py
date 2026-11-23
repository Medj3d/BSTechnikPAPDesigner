"""Menüs aufgeräumt: Was man einmal einstellt, steht in den Einstellungen; jeder Befehl in genau einem Menü."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenu, QMessageBox

from app import file_association, i18n, platforms, preferences, styles
from app import theme as theme_module
from app.actions import clean_text
from app.dialogs.settings import LANGUAGE, REGISTER_FILETYPE, THEME, TOOLBAR, SettingsDialog
from app.model.element_types import ElementType


def _clear_store(store) -> None:
    for group in ("preferences", "view", "export", "window", "language"):
        store._settings.remove(group)


def _new_window(qapp, tmp_path):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    return win


def _close(win) -> None:
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


@pytest.fixture
def window(qapp, tmp_path):
    from app.settings_store import SettingsStore
    store = SettingsStore()
    _clear_store(store)
    for key in preferences.TOOLS:
        preferences.set_enabled(key, preferences.default(key))
    win = _new_window(qapp, tmp_path)
    yield win
    if styles.current_theme() is not styles.DARK:
        win.set_theme("dark")
    theme_module.save_theme_name("dark")
    _close(win)
    _clear_store(store)   # auch das Fensterlayout: eine ausgeblendete Werkzeugleiste bliebe sonst gespeichert


def menu_actions(menu: QMenu) -> list:
    """Alle Einträge eines Menüs samt Untermenüs."""
    found = []
    for action in menu.actions():
        if action.menu() is not None:
            found.append(action)
            found += menu_actions(action.menu())
        elif not action.isSeparator():
            found.append(action)
    return found


def menus_of(window) -> dict[str, list]:
    return {clean_text(action.text()): menu_actions(action.menu()) for action in window.menuBar().actions()}


def all_menu_entries(window) -> list:
    return [action for entries in menus_of(window).values() for action in entries]


# ------------------------------------------------------------------ Menüs
MOVED = ("auto_save", "backup_on_save", "check_updates_on_start", "register_filetype", "theme_dark", "theme_light",
         "toggle_toolbar") + tuple(preferences.action_name(key) for key in (
             preferences.LOOSE_ENDS, preferences.QUICK_MENU, preferences.ROUNDED_LINES, preferences.WARNING_MARKS,
             preferences.EXTENDED_CHECKS))


def test_options_set_once_are_not_in_the_menus(window):
    entries = all_menu_entries(window)
    for name in MOVED:
        assert window.actions[name] not in entries, name
    assert window.toolbar.toggleViewAction() not in entries
    titles = {clean_text(action.text()) for action in entries}
    for title in ("Farbschema", "Sprache / Language", "Pfeile", "Prüfung", "Automatisch speichern",
                  "Sicherungskopie anlegen", "Beim Start nach Updates suchen", "Dateityp registrieren", "Werkzeugleiste",
                  "Werkzeugleiste anzeigen", "Dunkel", "Hell"):
        assert title not in titles, title


def test_moved_actions_still_work_by_search_and_shortcut_table(window):
    """Aus dem Menü genommen, aber nicht gelöscht: Strg+K findet sie, und sie lassen sich auf Tasten legen."""
    titles = {entry.title for entry in window.search_entries()}
    for name in ("auto_save", "check_updates_on_start", "theme_light", "toggle_toolbar", "toggle_theme"):
        assert clean_text(window.actions[name].text()) in titles, name
    assert "Sprache / Language" in titles
    assert "toggle_toolbar" in window.actions.bindable() and "toggle_theme" in window.actions.bindable()


@pytest.mark.parametrize("name, menu", [
    ("toggle_simulation", "Ansicht"), ("toggle_diagnostics", "Ansicht"), ("toggle_task", "Ansicht"),
    ("auto_layout", "Anordnen"), ("extract_subprogram", "Bearbeiten"),
])
def test_every_command_is_in_exactly_one_menu(window, name, menu):
    action = window.actions[name]
    places = [title for title, entries in menus_of(window).items() for entry in entries if entry is action]
    assert places == [menu]


def test_extras_keeps_only_tools(window):
    names = [name for name, action in window.actions.all().items() if action in menus_of(window)["Extras"]]
    assert set(names) == {"generate_code", "structogram", "settings", "search", "edit_task", "toggle_breakpoint",
                          "clear_breakpoints"}
    assert not [action for action in window.extras_menu.actions() if action.menu()]   # keine Untermenüs mehr


def test_more_and_context_menus_only_offer_existing_commands(window):
    registered = set(window.actions.all().values())
    entries = menu_actions(window.more_menu)
    assert all(entry in registered for entry in entries if entry.menu() is None)
    for name in MOVED:
        assert window.actions[name] not in entries, name


# ------------------------------------------------------------------ Einstellungen
def test_settings_offer_every_moved_option(window):
    dialog = SettingsDialog(window.actions, window)
    for name in ("auto_save", "backup_on_save", "check_updates_on_start") + MOVED[7:]:
        assert name in dialog.switches, name
    assert set(dialog.choices) == {THEME, LANGUAGE}
    assert TOOLBAR in dialog.toggles
    assert dialog.options[LANGUAGE].text == "Sprache / Language"
    # Darstellung steht ganz oben auf „Allgemein“
    assert dialog.sections.item(0).text() == "Allgemein"
    assert (REGISTER_FILETYPE in dialog.buttons) is file_association.is_supported()
    dialog.close()


@pytest.mark.skipif(not platforms.is_windows(), reason="Dateityp registrieren gibt es unter Windows (und Linux)")
def test_register_file_type_button_runs_the_old_command(window, monkeypatch):
    dialog = SettingsDialog(window.actions, window)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: asked.append(args[1]) or QMessageBox.StandardButton.No)
    dialog.buttons[REGISTER_FILETYPE].click()
    assert asked == ["Dateityp registrieren"]   # gefragt wie früher im Menü, mit „Nein“ nichts eingetragen
    dialog.close()


def test_theme_choice_applies_at_once_and_is_saved(window):
    dialog = SettingsDialog(window.actions, window)
    box = dialog.choices[THEME]
    assert box.value() == "dark"
    box.choose("light")
    assert styles.current_theme() is styles.LIGHT_UI
    assert theme_module.saved_theme_name() == "light"
    assert window.actions["theme_light"].isChecked()
    box.choose("dark")
    assert styles.current_theme() is styles.DARK and theme_module.saved_theme_name() == "dark"
    dialog.close()


def test_theme_button_in_toolbar_toggles_and_dialog_follows(window, qapp):
    action = window.actions["toggle_theme"]
    assert action in window.toolbar.actions() and window.theme_button.isVisible()
    assert "Hell/Dunkel umschalten" in action.toolTip()
    dark_icon = action.icon().pixmap(18, 18).toImage()
    dialog = SettingsDialog(window.actions, window)
    window.theme_button.click()
    qapp.processEvents()
    assert styles.current_theme() is styles.LIGHT_UI and theme_module.saved_theme_name() == "light"
    assert dialog.choices[THEME].value() == "light"           # das offene Fenster folgt
    assert action.icon().pixmap(18, 18).toImage() != dark_icon   # Sonne statt Mond
    window.theme_button.click()
    assert styles.current_theme() is styles.DARK and dialog.choices[THEME].value() == "dark"
    dialog.close()
    window.theme_button.click()   # das geschlossene Fenster stört nicht mehr
    assert styles.current_theme() is styles.LIGHT_UI


def test_language_choice_is_saved_with_restart_hint(window, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)   # „Später“
    restarts = []
    monkeypatch.setattr(window, "restart_program", lambda: restarts.append(True))
    dialog = SettingsDialog(window.actions, window)
    box = dialog.choices[LANGUAGE]
    labels = [box.itemText(index) for index in range(box.count())]
    assert labels[0] == "Automatisch (Systemsprache)" and "English" in labels and "Deutsch" in labels
    box.choose("en")
    assert window.settings_store.language() == "en" and box.value() == "en"
    assert shown == ["Die Sprache wird nach einem Neustart des Programms geändert."] and restarts == []
    box.choose(i18n.AUTOMATIC)
    assert window.settings_store.language() == i18n.AUTOMATIC
    dialog.close()


def test_language_label_stays_bilingual_in_other_languages(window):
    from app.main_window import language_label
    try:
        i18n.set_language("fr")
        assert language_label() == "Langue / Language"
        i18n.set_language("en")
        assert language_label() == "Language"
    finally:
        i18n.set_language("de")
    assert language_label() == "Sprache / Language"


def test_toolbar_switch_in_settings(window, qapp):
    dialog = SettingsDialog(window.actions, window)
    switch = dialog.toggles[TOOLBAR]
    assert switch.text() == "Werkzeugleiste anzeigen" and switch.isChecked()
    switch.click()
    qapp.processEvents()
    assert window.toolbar.isHidden() and not switch.isChecked()
    dialog.reset_switches()   # „Alle Schalter zurücksetzen“ holt sie zurück
    qapp.processEvents()
    assert not window.toolbar.isHidden() and switch.isChecked()
    dialog.close()


def test_reset_keeps_theme_and_language(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    dialog = SettingsDialog(window.actions, window)
    dialog.choices[THEME].choose("light")
    dialog.choices[LANGUAGE].choose("en")
    dialog.reset_switches()
    assert styles.current_theme() is styles.LIGHT_UI and window.settings_store.language() == "en"
    dialog.close()


def test_settings_search_finds_the_new_fields(window, qapp):
    dialog = SettingsDialog(window.actions, window)
    dialog.show()
    for query, key in (("language", LANGUAGE), ("sprache", LANGUAGE), ("english", LANGUAGE), ("farbschema", THEME),
                       ("hell", THEME), ("werkzeugleiste anzeigen", TOOLBAR)):
        dialog.search.setText(query)
        qapp.processEvents()
        assert dialog._holders[key].isVisibleTo(dialog), query
    if file_association.is_supported():
        dialog.search.setText("dateityp")
        qapp.processEvents()
        assert dialog._holders[REGISTER_FILETYPE].isVisibleTo(dialog)
        assert not dialog._holders[THEME].isVisibleTo(dialog)
    dialog.close()


# ------------------------------------------------------------------ Werkzeugleiste
def shown_in_toolbar(window) -> set:
    return {entry.property("source") for entries in window._toolbar_groups.values() for entry in entries
            if entry.isVisible() and entry.property("source") is not None}


def test_toolbar_has_no_pdf_button_and_new_defaults(window):
    assert not hasattr(preferences, "TOOL_PDF") and "tool_pdf" not in preferences.TOOLS
    sources = {entry.property("source") for entries in window._toolbar_groups.values() for entry in entries}
    assert window.actions["export_pdf"] not in sources
    assert preferences.default(preferences.TOOL_GRID) and preferences.default(preferences.TOOL_GENERATE_CODE)
    assert not preferences.default(preferences.TOOL_PRINT)
    shown = shown_in_toolbar(window)
    assert {window.actions[name] for name in ("toggle_grid", "toggle_snap", "generate_code")} <= shown
    assert window.actions["print"] not in shown
    # Tastenkürzel und Menüeinträge bleiben
    assert QKeySequence("Ctrl+E") in window.actions["export_pdf"].shortcuts()
    assert QKeySequence("Ctrl+P") in window.actions["print"].shortcuts()
    file_entries = menus_of(window)["Datei"]
    assert window.actions["export_pdf"] in file_entries and window.actions["print"] in file_entries


def test_stored_toolbar_choice_wins_over_the_new_default(window, qapp, tmp_path):
    store = window.settings_store
    store.set_preference(preferences.TOOL_PRINT, True)
    store.set_preference(preferences.TOOL_GRID, False)
    second = _new_window(qapp, tmp_path / "second")
    try:
        shown = shown_in_toolbar(second)
        assert second.actions["print"] in shown and second.actions["toggle_grid"] not in shown
    finally:
        _close(second)


# ------------------------------------------------------------------ Verbindungspunkt
def test_structure_warning_names_the_junction_in_the_ui_language():
    from app.analysis.graph import FlowGraph
    from app.analysis.structure import structure_diagram
    from app.model.diagram import ConnectionData, ElementData
    elements = [ElementData("s", ElementType.START, 0, 0, 120, 40, "Start", 0, {}),
                ElementData("j", ElementType.JUNCTION, 0, 100, 12, 12, "", 0, {}),
                ElementData("a", ElementType.PROCESS, 0, 200, 160, 60, "a = 1", 0, {}),
                ElementData("b", ElementType.PROCESS, 200, 200, 160, 60, "b = 1", 0, {}),
                ElementData("e", ElementType.END, 0, 300, 120, 40, "Ende", 0, {})]
    connections = [ConnectionData("1", "s", "j", "bottom", "top", ""),
                   ConnectionData("2", "j", "a", "bottom", "top", ""),
                   ConnectionData("3", "j", "b", "right", "top", ""),
                   ConnectionData("4", "a", "e", "bottom", "top", "")]
    (program,) = structure_diagram(FlowGraph.from_diagram(elements, connections))
    text = " ".join(program.warnings)
    assert "„Verbindungspunkt“ hat mehrere Ausgänge" in text and "junction" not in text
    dead_end = [ElementData("s", ElementType.START, 0, 0, 120, 40, "Start", 0, {}),
                ElementData("j", ElementType.JUNCTION, 0, 100, 12, 12, "", 0, {})]
    (program,) = structure_diagram(FlowGraph.from_diagram(dead_end, [ConnectionData("1", "s", "j", "bottom", "top", "")]))
    assert "„Verbindungspunkt“ hat keinen Nachfolger." in program.warnings


def test_palette_tooltip_calls_the_junction_a_merge_point(window):
    entry = next(entry for entry in window.palette.entries if entry.element_type is ElementType.JUNCTION)
    assert "Verbindungspunkt (Zusammenführung)" in entry.toolTip()


def test_hint_list_names_a_dead_end_junction_only_once(scene):
    """Die Strukturanalyse meldet die Sackgasse noch einmal; mit gleichem Namen fällt die zweite Meldung weg."""
    from app.diagnostics.checks import run_checks
    from tests.conftest import add, connect
    start = add(scene, ElementType.START, 0, 0)
    junction = add(scene, ElementType.JUNCTION, 0, 150)
    assert connect(scene, start, "bottom", junction, "top") is not None
    messages = [issue.message for issue in run_checks(scene) if junction.element_id in issue.element_ids
                or not issue.element_ids]
    dead_ends = [message for message in messages if "keinen Nachfolger" in message]
    assert dead_ends == ["Verbindungspunkt hat keinen Nachfolger (Sackgasse)."], messages


# ------------------------------------------------------------------ Nacharbeiten aus Prüfung und Probelauf
def _shown_dialog(window, qapp, **kwargs):
    dialog = SettingsDialog(window.actions, window, **kwargs)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    dialog.show()
    qapp.processEvents()
    return dialog


def test_enter_in_settings_search_presses_no_button(window, qapp, monkeypatch):
    """Enter im Suchfeld darf weder „Dateityp registrieren“ noch „Alle zurücksetzen“ (Tastenkürzel) auslösen."""
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: asked.append(args[1]) or QMessageBox.StandardButton.No)
    window.actions.assign("zoom_fit", [QKeySequence("Ctrl+Alt+9")])
    dialog = _shown_dialog(window, qapp)
    assert not any(button.isDefault() or button.autoDefault() for button in dialog.findChildren(QPushButton))
    for row in (0, dialog.sections.count() - 1):   # Allgemein (Dateityp) und Tastenkürzel
        dialog.sections.setCurrentRow(row)
        QTest.keyClick(dialog.search, Qt.Key.Key_Return)
        qapp.processEvents()
    assert asked == [] and dialog.isVisible()
    assert window.actions["zoom_fit"].shortcuts() == [QKeySequence("Ctrl+Alt+9")]   # nicht zurückgesetzt
    window.actions.reset_shortcuts()
    dialog.close()


def test_theme_button_sits_on_the_right_before_the_search(window):
    actions = window.toolbar.actions()
    theme = actions.index(window.actions["toggle_theme"])
    assert actions[theme + 1] is window._search_action
    assert theme > actions.index(window._toolbar_end)   # hinter dem Platzhalter, also rechts


def test_show_settings_does_not_leave_dialogs_behind(window, qapp, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: 0)
    for _ in range(2):
        window.show_settings()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert window.findChildren(SettingsDialog) == []
    window.theme_button.click()                         # die gelöschten Fenster hängen an keinem Signal mehr
    window.actions["auto_save"].trigger()
    window.actions["auto_save"].trigger()
    assert styles.current_theme() is styles.LIGHT_UI


def test_settings_sections_stay_readable_after_theme_switch(window, qapp):
    """Nach Hell → Dunkel standen die Bereiche übereinander; mit Trefferzahl gab es eine Bildlaufleiste."""
    window.set_theme("light")
    window.set_theme("dark")
    dialog = _shown_dialog(window, qapp)
    rects = [dialog.sections.visualItemRect(dialog.sections.item(row)) for row in range(dialog.sections.count())]
    for above, below in zip(rects, rects[1:]):
        assert below.top() >= above.bottom(), (above, below)
    dialog.search.setText("Pfeil")
    qapp.processEvents()
    assert not dialog.sections.horizontalScrollBar().isVisible()
    dialog.close()


def test_choice_fields_line_up(window, qapp):
    dialog = _shown_dialog(window, qapp)
    left = {dialog.choices[key].mapTo(dialog, dialog.choices[key].rect().topLeft()).x() for key in (THEME, LANGUAGE)}
    assert len(left) == 1
    dialog.close()


def test_f1_headings_named_like_a_menu_only_list_commands_of_that_menu(window):
    """Schüler lesen „Extras“ in der F1-Hilfe als Menüweg."""
    from app.dialogs.shortcuts import _LIVE_KEYS, SHORTCUTS
    menus = menus_of(window)
    heading, checked = None, set()
    for key, function in SHORTCUTS:
        if not function:
            heading = key
            continue
        if heading in menus and key in _LIVE_KEYS:
            for name in _LIVE_KEYS[key]:
                assert window.actions[name] in menus[heading], (heading, key, name)
            checked.add(heading)
    assert {"Datei", "Bearbeiten", "Ansicht", "Anordnen", "Extras"} <= checked
