"""Aufgaben als Vorlage, Anzeige „Automatisch speichern“ in der Statusleiste, Datei → Alle speichern / Alle schließen."""

from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from app import task as T
from app.actions import clean_text, sequence_text
from app.document import DiagramDocument
from app.model.element_types import ElementType

PASSWORD = "geheim"


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    from app.settings_store import SettingsStore

    store = SettingsStore()
    store.clear_recent_files()
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    win.set_auto_save(True)
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()
    qapp.processEvents()
    store.clear_recent_files()


def make_task_file(path, locked: bool = True, solution_copy: bool = False) -> str:
    """Aufgabendatei wie nach „Aufgabe stellen“ (Plan leer bis auf einen Baustein)."""
    document = DiagramDocument()
    document.scene.insert_element(ElementType.PROCESS, QPointF(0, 0))
    lock = T.make_lock(PASSWORD) if locked else ""
    solution = T.encrypt("Musterlösung", PASSWORD) if locked else ""
    T.apply_task(document.meta, T.Task("Aufgabe 3", "Zeichne den Ablauf", solution, lock))
    if solution_copy:
        document.meta.task_copy = "1"
    document.save(str(path))
    document.deleteLater()
    return str(path)


def save_dialog(monkeypatch, *answers):
    """Ersetzt „Speichern unter“: gibt nacheinander die Pfade zurück und merkt sich die Vorschläge."""
    asked = []
    queue = list(answers)

    def answer(_parent, _title, suggestion, *_args, **_kwargs):
        asked.append(suggestion)
        return (str(queue.pop(0)) if queue else "", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", answer)
    return asked


def change(document, y: float = 200) -> None:
    document.scene.insert_element(ElementType.OUTPUT, QPointF(0, y))
    assert document.is_modified


def tab_texts(window) -> list[str]:
    return [window.tabs.tabText(i) for i in range(window.tabs.count())]


# ================================================================== Aufgaben als Vorlage
def test_task_file_always_opens_as_an_unnamed_copy(window, monkeypatch, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    before = open(original, "rb").read()
    assert window.open_file(original)
    copy = window.current_document()
    assert copy.file_path is None and copy.task_source == os.path.abspath(original)
    assert copy.display_name == "Aufgabe3 – Kopie" and "Aufgabe3 – Kopie" in tab_texts(window)
    assert copy.meta.task_copy == "1" and copy.meta.task_lock     # die Aufgabe selbst bleibt im Projekt
    assert not window.task_dock.isHidden()
    assert "als Kopie geöffnet" in window.statusBar().currentMessage()
    # zuletzt geöffnet: die Aufgabe – ein Klick darauf öffnet wieder eine Kopie
    assert os.path.abspath(original) in [os.path.abspath(p) for p in window.settings_store.recent_files()]

    change(copy)
    window._schedule_auto_save(copy)
    window._run_auto_save()
    assert not window._auto_save_applies(copy) and open(original, "rb").read() == before

    solution = tmp_path / "Aufgabe3 – Lösung.pap"
    asked = save_dialog(monkeypatch, solution)
    assert window.save_document(copy)                    # Strg+S fragt nach einem neuen Namen
    assert len(asked) == 1 and os.path.basename(asked[0]) == "Aufgabe3 – Lösung.pap"
    assert open(original, "rb").read() == before and solution.exists()
    assert copy.file_path == str(solution) and window._auto_save_applies(copy)
    reopened = DiagramDocument.open_file(str(solution))
    assert reopened.meta.task_copy == "1" and reopened.meta.task_title == "Aufgabe 3"
    reopened.deleteLater()


def test_a_solution_can_not_replace_the_task_file(window, monkeypatch, tmp_path):
    """Auch „Speichern unter“ mit dem Namen der Aufgabe ersetzt sie nicht."""
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    other_task = make_task_file(tmp_path / "Aufgabe4.pap")
    before = open(original, "rb").read()
    assert window.open_file(original)
    copy = window.current_document()
    change(copy)
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: errors.append(a[2]))
    save_dialog(monkeypatch, original, other_task)
    assert not window.save_document(copy)
    assert not window.save_document_as(copy)
    assert len(errors) == 2 and "wird nicht überschrieben" in errors[0]
    assert open(original, "rb").read() == before and copy.file_path is None and copy.is_modified
    # die eigene Lösung darf man natürlich wieder speichern
    solution = tmp_path / "Lösung.pap"
    save_dialog(monkeypatch, solution, solution)
    assert window.save_document(copy) and window.save_document_as(copy)


def test_task_without_password_also_opens_as_copy(window, tmp_path):
    original = make_task_file(tmp_path / "offen.pap", locked=False)
    assert window.open_file(original)
    document = window.current_document()
    assert document.file_path is None and document.task_source and document.display_name == "offen – Kopie"


def test_saved_solution_of_a_student_opens_normally(window, tmp_path):
    solution = make_task_file(tmp_path / "meine Lösung.pap", solution_copy=True)
    assert window.open_file(solution)
    document = window.current_document()
    assert document.file_path == os.path.abspath(solution) and not document.task_source
    assert window._auto_save_applies(document)


def test_opening_the_same_task_again_shows_the_open_copy(window, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    assert window.open_file(original)
    count = window.tabs.count()
    window.new_document()
    assert window.open_file(original)
    assert window.tabs.count() == count + 1               # nur das neue Projekt kam dazu, keine zweite Kopie
    assert window.current_document().task_source == os.path.abspath(original)
    assert "schon als Kopie" in window.statusBar().currentMessage()


def test_untouched_task_copy_is_not_replaced_by_the_next_file(window, tmp_path):
    """Ein unbenanntes, leeres Projekt macht beim Öffnen Platz – die Kopie einer Aufgabe nicht."""
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    other = tmp_path / "anderes.pap"
    plain = DiagramDocument()
    plain.save(str(other))
    plain.deleteLater()
    assert window.open_file(original)
    assert window.open_file(str(other))
    sources = [view.document.task_source for view in window.views()]
    assert os.path.abspath(original) in sources


def test_teacher_changes_the_task_in_a_copy_and_replaces_it_on_purpose(window, monkeypatch, tmp_path):
    """Extras → Aufgabe stellen in der Kopie (mit Passwort, OK): Das Projekt wird wieder eine Aufgabe. Gespeichert
    wird erst nach der Wahl des Namens – vorgeschlagen ist die Aufgabendatei, die man bewusst ersetzt."""
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    assert window.open_file(original)
    document = window.current_document()
    monkeypatch.setattr("app.main_window.ask_password", lambda *_a: PASSWORD)
    monkeypatch.setattr("app.main_window.TaskDialog.exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr("app.main_window.TaskDialog.result_task",
                        lambda self: T.Task("Aufgabe 3b", "Neu", "", T.make_lock(PASSWORD)))
    window.edit_task()
    assert document.file_path is None and document.task_source == os.path.abspath(original)
    assert document.meta.task_copy == "" and document.task_unlocked
    assert "nur ersetzt" in window.statusBar().currentMessage()
    asked = save_dialog(monkeypatch, original)
    assert window.save_document(document)
    assert asked == [os.path.abspath(original)]
    saved = DiagramDocument.open_file(original)
    assert saved.meta.task_title == "Aufgabe 3b" and saved.meta.task_copy == "" and saved.meta.task_lock
    saved.deleteLater()


def test_wrong_password_keeps_the_copy(window, monkeypatch, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    assert window.open_file(original)
    document = window.current_document()
    warnings = []
    monkeypatch.setattr("app.main_window.ask_password", lambda *_a: "falsch")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    window.edit_task()
    assert warnings and document.file_path is None and document.task_source


def test_file_menu_edit_task_opens_the_task_file_itself(window, monkeypatch, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    file_menu = window.menuBar().actions()[0].menu()
    assert window.actions["edit_task_file"] in file_menu.actions()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (original, ""))
    asked = []
    monkeypatch.setattr("app.main_window.ask_password", lambda *a: asked.append(a[1]) or PASSWORD)
    window.actions["edit_task_file"].trigger()
    document = window.current_document()
    assert asked == ["Aufgabe bearbeiten"]
    assert document.file_path == os.path.abspath(original) and document.task_unlocked
    assert window._auto_save_applies(document) and not window._is_task_original(document)
    assert "zum Bearbeiten geöffnet" in window.statusBar().currentMessage()


def test_edit_task_file_needs_the_right_password(window, monkeypatch, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    count = window.tabs.count()
    monkeypatch.setattr("app.main_window.ask_password", lambda *a: None)
    assert not window.edit_task_file(original) and window.tabs.count() == count       # abgebrochen
    warnings = []
    monkeypatch.setattr("app.main_window.ask_password", lambda *a: "falsch")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    assert not window.edit_task_file(original) and window.tabs.count() == count
    assert warnings == ["Das Passwort ist falsch."]


def test_edit_task_file_without_password_and_without_task(window, monkeypatch, tmp_path):
    monkeypatch.setattr("app.main_window.ask_password", lambda *a: pytest.fail("ohne Passwort keine Frage"))
    open_task = make_task_file(tmp_path / "offen.pap", locked=False)
    assert window.edit_task_file(open_task)
    assert window.current_document().file_path == os.path.abspath(open_task)
    plain = DiagramDocument()
    plain.save(str(tmp_path / "plan.pap"))
    plain.deleteLater()
    assert window.edit_task_file(str(tmp_path / "plan.pap"))
    assert "keine Aufgabe" in window.statusBar().currentMessage()


def test_recovered_task_copy_stays_a_copy(qapp, tmp_path):
    from app.autosave import AutosaveManager

    original = make_task_file(tmp_path / "Aufgabe3.pap")
    crashed = AutosaveManager(str(tmp_path / "auto"), interval_ms=3600000)
    document = DiagramDocument.open_file(original)
    document.task_source, document.file_path, document.meta.task_copy = original, None, "1"
    change(document)
    crashed.register(document)
    assert crashed.save_now() == 1
    survivor = AutosaveManager(str(tmp_path / "auto"), interval_ms=3600000, pid_alive_func=lambda pid: False)
    (entry,) = survivor.find_orphans()
    assert entry.task_source == original and entry.original_path is None
    restored = survivor.restore(entry)
    assert restored.file_path is None and restored.task_source == original
    assert restored.display_name == "Aufgabe3 – Kopie" and restored.meta.name == document.meta.name
    for manager in (crashed, survivor):
        manager.shutdown()
    for doc in (document, restored):
        doc.deleteLater()


def test_recovered_task_original_opens_as_copy(window, monkeypatch, tmp_path):
    """Eine Sicherung der Aufgabendatei selbst (Lehrkraft hatte entsperrt) kommt als Kopie zurück."""
    from app.autosave import AutosaveManager
    from app.dialogs.recovery import RecoveryDialog

    original = make_task_file(tmp_path / "Aufgabe3.pap")
    before = open(original, "rb").read()
    crashed = AutosaveManager(window.autosave.directory, interval_ms=3600000)
    teacher = DiagramDocument.open_file(original)
    change(teacher)
    crashed.register(teacher)
    assert crashed.save_now() == 1
    crashed._timer.stop()
    window.autosave._pid_alive = lambda pid: False
    entries = window.autosave.find_orphans()
    assert len(entries) == 1
    monkeypatch.setattr(RecoveryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(RecoveryDialog, "selected_entries", lambda self: list(entries))
    assert window.offer_recovery() == 1
    restored = window.current_document()
    assert restored.file_path is None and restored.task_source == os.path.abspath(original)
    assert restored.is_modified and not window._auto_save_applies(restored)
    assert open(original, "rb").read() == before
    teacher.undo_stack.setClean()
    teacher.deleteLater()


# ================================================================== Anzeige in der Statusleiste
def test_status_shows_untitled_auto_off_and_follows_the_tab(window, monkeypatch, tmp_path):
    button = window.save_state_button
    save_key = sequence_text(window.actions["save"].shortcuts()[0])
    window.new_document()
    assert button.isVisible() and button.property("save_state") == "untitled"
    assert button.text() == "Nicht gespeichert" and save_key in button.toolTip()
    untitled = window.current_document()

    path = tmp_path / "plan.pap"
    save_dialog(monkeypatch, path)
    change(untitled)
    assert window.save_document(untitled)
    assert button.property("save_state") == "auto" and button.text() == "Auto-Speichern an"
    assert str(path) in button.toolTip() and "Allgemein → Speichern" in button.toolTip()

    window.set_auto_save(False)
    assert button.property("save_state") == "off" and button.text() == "Auto-Speichern aus"
    assert str(path) in button.toolTip()
    window.actions["auto_save"].trigger()                   # wie der Schalter in den Einstellungen
    assert button.property("save_state") == "auto"

    window.new_document()                                   # Reiterwechsel
    assert button.property("save_state") == "untitled"
    window.tabs.setCurrentIndex(window.tabs.indexOf(window.views()[0]))
    window.tabs.setCurrentWidget(next(v for v in window.views() if v.document is untitled))
    assert button.property("save_state") == "auto"


def test_status_explains_why_autosave_is_paused(window, tmp_path):
    path = tmp_path / "fremd.pap"
    document = DiagramDocument()
    document.save(str(path))
    document.deleteLater()
    assert window.open_file(str(path))
    opened = window.current_document()
    opened.native_file = False
    window._update_save_state()
    assert window.save_state_button.property("save_state") == "paused"
    assert "anderen Programm" in window.save_state_button.toolTip()
    opened.native_file = True
    os.remove(path)
    window._update_save_state()
    assert window.save_state_button.property("save_state") == "paused"
    assert "gelöscht" in window.save_state_button.toolTip()


def test_status_for_a_task_copy_and_without_project(window, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    assert window.open_file(original)
    assert window.save_state_button.property("save_state") == "untitled"
    assert "Kopie der Aufgabe „Aufgabe3.pap“" in window.save_state_button.toolTip()
    while window.tabs.count():
        window.current_document().undo_stack.setClean()
        assert window.close_tab(window.tabs.currentIndex())
    assert not window.save_state_button.isVisible()


def test_clicking_the_status_opens_the_save_settings(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "show_settings", lambda *a, **k: opened.append(k))
    window.new_document()
    window.save_state_button.click()
    assert opened == [{"focus": "auto_save"}]


def test_settings_focus_the_autosave_switch(window, qapp, monkeypatch):
    from app.dialogs.settings import SettingsDialog

    focused = []

    def fake_exec(dialog):
        dialog.show()
        qapp.processEvents()
        focused.append(dialog.focusWidget() is dialog.switches["auto_save"])
        dialog.close()
        return 0

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window.show_settings(focus="auto_save")
    assert focused == [True]


# ================================================================== Alle speichern / Alle schließen
def test_new_commands_in_the_file_menu_with_free_keys(window):
    file_menu = window.menuBar().actions()[0].menu()
    for name, key in (("save_all", "Ctrl+Alt+S"), ("close_all", "Ctrl+Shift+W")):
        action = window.actions[name]
        assert action in file_menu.actions(), name
        assert action.shortcuts() == [QKeySequence(key)]
        assert action.toolTip().endswith(f"({sequence_text(QKeySequence(key))})")
        owners = [other for other, a in window.actions.all().items() if QKeySequence(key) in a.shortcuts()]
        assert owners == [name], owners
    from app.dialogs.settings import ShortcutTable
    from app.dialogs.shortcuts import ShortcutsDialog

    table = ShortcutTable(window.actions)
    assert {"save_all", "close_all", "edit_task_file"} <= set(table.names)
    table.deleteLater()
    help_dialog = ShortcutsDialog(window, window.actions)
    rows = {help_dialog.table.item(r, 1).text(): help_dialog.table.item(r, 0).text()
            for r in range(help_dialog.table.rowCount())}
    assert rows["Alle geänderten Projekte speichern"] == sequence_text(QKeySequence("Ctrl+Alt+S"))
    assert rows["Alle Projekte schließen (bei Änderungen wird gefragt)"] == \
        sequence_text(QKeySequence("Ctrl+Shift+W"))
    window.new_document()                                  # ohne Projekt sind beide Befehle gesperrt
    titles = {entry.title for entry in window.search_entries()}
    assert {"Alle speichern", "Alle schließen", "Aufgabe bearbeiten"} <= titles
    assert clean_text(window.actions["save_all"].text()) == "Alle speichern"


def test_save_all_saves_every_changed_project(window, monkeypatch, tmp_path):
    saved_path = tmp_path / "schon.pap"
    first = DiagramDocument()
    first.save(str(saved_path))
    first.deleteLater()
    assert window.open_file(str(saved_path))
    window.set_auto_save(False)
    named = window.current_document()
    change(named)
    window.new_document()
    untouched = window.current_document()
    window.new_document()
    untitled_a = window.current_document()
    change(untitled_a)
    window.new_document()
    untitled_b = window.current_document()
    change(untitled_b)
    start = window.current_view()
    asked = save_dialog(monkeypatch, tmp_path / "a.pap", tmp_path / "b.pap")
    window.actions["save_all"].trigger()
    assert len(asked) == 2                                  # nur die zwei unbenannten, geänderten fragen
    assert not any(d.is_modified for d in (named, untitled_a, untitled_b))
    assert untitled_a.file_path == str(tmp_path / "a.pap") and untitled_b.file_path == str(tmp_path / "b.pap")
    assert untouched.file_path is None
    assert window.current_view() is start
    assert "3 Projekt(e) gespeichert" in window.statusBar().currentMessage()


def test_save_all_stops_when_a_name_is_cancelled(window, monkeypatch, tmp_path):
    window.new_document()
    first = window.current_document()
    change(first)
    window.new_document()
    second = window.current_document()
    change(second)
    asked = save_dialog(monkeypatch)                         # Abbrechen
    assert not window.save_all()
    assert len(asked) == 1 and first.is_modified and second.is_modified
    assert "abgebrochen" in window.statusBar().currentMessage()


def test_save_all_with_nothing_to_save(window, monkeypatch):
    window.new_document()
    save_dialog(monkeypatch)
    assert window.save_all()
    assert "schon gespeichert" in window.statusBar().currentMessage()


class Answers:
    """Beantwortet die Frage „wurde geändert“ nacheinander mit den Knopftexten."""

    def __init__(self, monkeypatch, *texts):
        self.texts = list(texts)
        self.shown: list[list[str]] = []
        monkeypatch.setattr(QMessageBox, "exec", lambda box, *_args: self._exec(box))

    def _exec(self, box):
        self.shown.append([button.text() for button in box.buttons()])
        wanted = self.texts.pop(0)
        next(button for button in box.buttons() if button.text() == wanted).click()
        return 0


def three_changed(window) -> list:
    documents = []
    for y in (0, 100, 200):
        window.new_document()
        documents.append(window.current_document())
        change(documents[-1], y)
    return documents


def test_close_all_can_be_cancelled_and_keeps_every_tab(window, monkeypatch):
    window.set_auto_save(False)
    documents = three_changed(window)
    count = window.tabs.count()
    answers = Answers(monkeypatch, "Verwerfen", "Abbrechen")
    assert not window.close_all()
    assert window.tabs.count() == count and all(d.is_modified for d in documents)
    assert "Alle Änderungen verwerfen" in answers.shown[0]


def test_close_all_discard_all_asks_only_once(window, monkeypatch):
    window.set_auto_save(False)
    three_changed(window)
    answers = Answers(monkeypatch, "Alle Änderungen verwerfen")
    window.actions["close_all"].trigger()
    assert len(answers.shown) == 1 and window.tabs.count() == 0
    assert window.stack.currentWidget() is window.empty_state       # wie nach dem Schließen des letzten Reiters
    assert "Alle Projekte geschlossen" in window.statusBar().currentMessage()


def test_close_all_asks_for_each_and_saves_when_wanted(window, monkeypatch, tmp_path):
    window.set_auto_save(False)
    documents = three_changed(window)
    save_dialog(monkeypatch, tmp_path / "behalten.pap")
    answers = Answers(monkeypatch, "Verwerfen", "Speichern", "Verwerfen")
    assert window.close_all()
    assert len(answers.shown) == 3 and window.tabs.count() == 0
    assert "Alle Änderungen verwerfen" not in answers.shown[-1]     # beim letzten gibt es nichts mehr „alle“
    assert (tmp_path / "behalten.pap").exists()
    assert len(documents) == 3


def test_close_all_saves_autosaved_projects_without_asking(window, monkeypatch, tmp_path):
    path = tmp_path / "auto.pap"
    document = DiagramDocument()
    document.save(str(path))
    document.deleteLater()
    assert window.open_file(str(path))
    change(window.current_document())
    Answers(monkeypatch)                                    # jede Frage wäre ein Fehler (leere Antwortliste)
    assert window.close_all() and window.tabs.count() == 0
    assert len(DiagramDocument.open_file(str(path)).scene.elements()) == 1
