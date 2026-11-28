"""Nacharbeiten aus Review und Probeläufen der neuen Funktionen (Teile A bis E).

Aufgabendateien (nie versehentlich ersetzt), Anzeige „Auto-Speichern“, „Alle Änderungen verwerfen“, Tipp und
Schreibweisen-Dialog, Bausteinliste und „Verbinden mit …“, Zugriffstasten in allen Sprachen, Exportordner.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QMessageBox, QStyleOptionViewItem

from app import block_list, export, i18n, notation, styles
from app import task as T
from app.block_list import BlockListPanel, ConnectDialog
from app.document import DiagramDocument
from app.fileformat.project import ProjectFileError
from app.model.element_types import ElementType
from tests.conftest import add, connect

PASSWORD = "geheim"


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    from app.settings_store import SettingsStore

    store = SettingsStore()
    store.clear_recent_files()
    for group in ("window", "last_export_directory"):
        store._settings.remove(group)
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(1200, 800)
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
    store._settings.remove("last_export_directory")


def make_task_file(path, locked: bool = True) -> str:
    document = DiagramDocument()
    document.scene.insert_element(ElementType.PROCESS, QPointF(0, 0))
    lock = T.make_lock(PASSWORD) if locked else ""
    solution = T.encrypt("Musterlösung", PASSWORD) if locked else ""
    T.apply_task(document.meta, T.Task("Aufgabe 3", "Zeichne den Ablauf", solution, lock))
    document.save(str(path))
    document.deleteLater()
    return str(path)


def save_dialog(monkeypatch, *answers):
    asked = []
    queue = list(answers)

    def answer(_parent, _title, suggestion, *_args, **_kwargs):
        asked.append(suggestion)
        return (str(queue.pop(0)) if queue else "", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", answer)
    return asked


def no_save_dialog(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: pytest.fail("hier darf kein Speichern-unter-Dialog kommen"))


def change(document, y: float = 200) -> None:
    document.scene.insert_element(ElementType.OUTPUT, QPointF(0, y))
    assert document.is_modified


def task_dialog(monkeypatch, accepted: bool, task: T.Task | None = None) -> None:
    code = QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
    monkeypatch.setattr("app.main_window.TaskDialog.exec", lambda self: code)
    if task is not None:
        monkeypatch.setattr("app.main_window.TaskDialog.result_task", lambda self: task)


def errors(monkeypatch) -> list:
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: shown.append(a[2]))
    return shown


# ================================================================== Aufgabendateien
def test_viewing_the_solution_and_cancelling_changes_nothing(window, monkeypatch, tmp_path):
    """Review B‑1: Passwort eingeben, um die Musterlösung anzusehen, und abbrechen – die Schülerarbeit bleibt eine
    Kopie und kommt nie (auch nicht automatisch) in die Aufgabendatei."""
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    before = open(original, "rb").read()
    assert window.open_file(original)
    copy = window.current_document()
    change(copy)
    monkeypatch.setattr("app.main_window.ask_password", lambda *_a: PASSWORD)
    task_dialog(monkeypatch, accepted=False)
    window.edit_task()
    assert copy.file_path is None and copy.task_source == os.path.abspath(original)
    assert copy.meta.task_copy == "1" and not copy.task_unlocked
    assert not window._auto_save_applies(copy)
    window._schedule_auto_save(copy)
    window._run_auto_save()
    asked = save_dialog(monkeypatch, original)       # auch bewusst gewählt: die Aufgabe wird nicht ersetzt
    shown = errors(monkeypatch)
    assert not window.save_document(copy)
    assert os.path.basename(asked[0]) == "Aufgabe3 – Lösung.pap"
    assert shown and "wird nicht überschrieben" in shown[0]
    assert open(original, "rb").read() == before


def test_a_new_task_made_from_a_copy_is_saved_as_a_task(window, monkeypatch, tmp_path):
    """Review B‑2: Die Lehrkraft macht aus einer alten Aufgabe eine neue – gespeichert ist es eine Aufgabe (keine
    Schülerlösung), und Schüler öffnen sie wieder als Kopie."""
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    assert window.open_file(original)
    document = window.current_document()
    monkeypatch.setattr("app.main_window.ask_password", lambda *_a: PASSWORD)
    task_dialog(monkeypatch, True, T.Task("Aufgabe 4", "Neu", "", T.make_lock("anders")))
    window.edit_task()
    target = tmp_path / "Aufgabe4.pap"
    save_dialog(monkeypatch, target)
    assert window.save_document(document)
    saved = DiagramDocument.open_file(str(target))
    assert saved.meta.task_copy == "" and saved.meta.task_title == "Aufgabe 4"
    saved.deleteLater()
    assert window.close_tab(window.tabs.indexOf(window.current_view()))   # die Lehrkraft ist fertig
    window.new_document()
    assert window.open_file(str(target))
    reopened = window.current_document()
    assert reopened.file_path is None and reopened.task_source == os.path.abspath(target)   # wieder als Kopie


def test_undoing_the_new_task_makes_it_a_solution_again(window, monkeypatch, tmp_path):
    original = make_task_file(tmp_path / "Aufgabe3.pap")
    assert window.open_file(original)
    document = window.current_document()
    monkeypatch.setattr("app.main_window.ask_password", lambda *_a: PASSWORD)
    task_dialog(monkeypatch, True, T.Task("Aufgabe 3b", "", "", T.make_lock(PASSWORD)))
    window.edit_task()
    assert document.meta.task_copy == ""
    document.undo_stack.undo()
    assert document.meta.task_copy == "1"
    asked = save_dialog(monkeypatch, original)
    shown = errors(monkeypatch)
    assert not window.save_document(document)        # als Lösung darf sie die Aufgabe nicht ersetzen
    assert os.path.basename(asked[0]) == "Aufgabe3 – Lösung.pap" and shown


def test_a_new_project_can_not_replace_a_task_file(window, monkeypatch, tmp_path):
    """Review B‑3 / Probelauf 3: „Speichern unter“ eines ganz anderen Projekts auf eine Aufgabendatei."""
    original = make_task_file(tmp_path / "Aufgabe3.pap", locked=False)
    before = open(original, "rb").read()
    window.new_document()
    document = window.current_document()
    change(document)
    save_dialog(monkeypatch, original)
    shown = errors(monkeypatch)
    assert not window.save_document(document)
    assert shown and open(original, "rb").read() == before and document.file_path is None
    # eine gewöhnliche Datei darf man weiterhin ersetzen (der Dialog hat danach gefragt)
    plain = tmp_path / "plan.pap"
    other = DiagramDocument()
    other.save(str(plain))
    other.deleteLater()
    save_dialog(monkeypatch, plain)
    assert window.save_document(document) and document.file_path == str(plain)


def test_teacher_saves_into_her_file_right_after_setting_the_task(window, monkeypatch, tmp_path):
    """Probelauf 2: Projekt gespeichert, dann Extras → Aufgabe stellen mit Passwort – Strg+S schreibt in dieselbe
    Datei (und das automatische Speichern läuft weiter)."""
    path = tmp_path / "Lehrer.pap"
    window.new_document()
    document = window.current_document()
    change(document)
    save_dialog(monkeypatch, path)
    assert window.save_document(document)
    monkeypatch.setattr("app.main_window.ask_password", lambda *_a: pytest.fail("noch kein Passwort vergeben"))
    task_dialog(monkeypatch, True, T.Task("Aufgabe 1", "Zeichne", "", T.make_lock(PASSWORD)))
    window.edit_task()
    no_save_dialog(monkeypatch)
    assert window.save_document(document)
    assert document.file_path == str(path) and window._auto_save_applies(document)
    assert window.save_state_button.property("save_state") == "auto"
    saved = DiagramDocument.open_file(str(path))
    assert saved.meta.task_title == "Aufgabe 1" and saved.meta.task_lock and saved.meta.task_copy == ""
    saved.deleteLater()


def test_recovered_task_the_teacher_was_editing_returns_to_its_file(window, monkeypatch, tmp_path):
    """Review B‑4: Absturz während Datei → Aufgabe bearbeiten – die Sicherung kommt wieder in die Aufgabendatei
    (gespeichert wird wie nach jeder Wiederherstellung erst bewusst)."""
    from app.autosave import AutosaveManager
    from app.dialogs.recovery import RecoveryDialog

    original = make_task_file(tmp_path / "offen.pap", locked=False)
    crashed = AutosaveManager(window.autosave.directory, interval_ms=3600000)
    teacher = DiagramDocument.open_file(original)
    teacher.task_unlocked = True                            # wie nach Datei → Aufgabe bearbeiten
    change(teacher)
    crashed.register(teacher)
    assert crashed.save_now() == 1
    crashed._timer.stop()
    window.autosave._pid_alive = lambda pid: False
    entries = window.autosave.find_orphans()
    assert len(entries) == 1 and entries[0].task_unlocked
    monkeypatch.setattr(RecoveryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(RecoveryDialog, "selected_entries", lambda self: list(entries))
    assert window.offer_recovery() == 1
    restored = window.current_document()
    assert restored.file_path == os.path.abspath(original) and not restored.task_source
    assert restored.task_unlocked and not window._auto_save_applies(restored)   # erst nach bewusstem Speichern
    no_save_dialog(monkeypatch)
    assert window.save_document(restored)
    assert len(DiagramDocument.open_file(original).scene.elements()) == 2
    teacher.undo_stack.setClean()
    teacher.deleteLater()


# ================================================================== Alle schließen / Beenden
class Answers:
    def __init__(self, monkeypatch, *texts):
        self.texts = list(texts)
        self.shown: list[list[str]] = []
        monkeypatch.setattr(QMessageBox, "exec", lambda box, *_args: self._exec(box))

    def _exec(self, box):
        self.shown.append([button.text() for button in box.buttons()])
        wanted = self.texts.pop(0)
        next(button for button in box.buttons() if button.text() == wanted).click()
        return 0


def test_discard_all_is_only_offered_when_another_project_would_ask(window, monkeypatch, tmp_path):
    """Review B‑6: Ein automatisch gespeichertes Projekt fragt nicht – also gibt es auch kein „alle“."""
    path = tmp_path / "auto.pap"
    plain = DiagramDocument()
    plain.save(str(path))
    plain.deleteLater()
    window.new_document()
    untitled = window.current_document()
    change(untitled)
    assert window.open_file(str(path))
    named = window.current_document()
    change(named)
    answers = Answers(monkeypatch, "Verwerfen")
    assert window.close_all() and window.tabs.count() == 0
    assert len(answers.shown) == 1 and "Alle Änderungen verwerfen" not in answers.shown[0]
    assert len(DiagramDocument.open_file(str(path)).scene.elements()) == 1   # still gespeichert


def test_quitting_offers_discard_all_too(window, monkeypatch):
    """Review B‑6 (nebenbei): Auch beim Beenden gibt es „Alle Änderungen verwerfen“."""
    for y in (0, 100):
        window.new_document()
        change(window.current_document(), y)
    answers = Answers(monkeypatch, "Alle Änderungen verwerfen")
    assert window.close()
    assert len(answers.shown) == 1 and "Alle Änderungen verwerfen" in answers.shown[0]


# ================================================================== Anzeige „Auto-Speichern“
def test_failed_autosave_shows_paused(window, monkeypatch, tmp_path):
    """Review B‑7: Ein Schreibfehler beim automatischen Speichern zeigt „pausiert“ – bis es wieder klappt."""
    path = tmp_path / "plan.pap"
    window.new_document()
    document = window.current_document()
    change(document)
    save_dialog(monkeypatch, path)
    assert window.save_document(document)
    change(document, 400)

    def refuse(*_args, **_kwargs):
        raise ProjectFileError("Die Datei ist schreibgeschützt.", "readonly")

    monkeypatch.setattr(document, "save", refuse)
    assert not window._save_to(document, document.file_path, automatic=True)
    button = window.save_state_button
    assert button.property("save_state") == "paused" and button.text() == "Auto-Speichern pausiert"
    assert "fehlgeschlagen" in button.toolTip()
    monkeypatch.undo()
    assert window._save_to(document, document.file_path, automatic=True)
    assert button.property("save_state") == "auto"


def test_status_button_is_compact_in_a_narrow_window(window, qapp):
    """Probelauf 1: Im schmalen Fenster nur das Symbol – Meldungen links behalten ihren Platz."""
    from app.main_window import SAVE_STATE_COMPACT_WIDTH

    window.new_document()
    button = window.save_state_button
    window.resize(SAVE_STATE_COMPACT_WIDTH - 200, 700)
    qapp.processEvents()
    window._update_save_state()
    if window.width() < SAVE_STATE_COMPACT_WIDTH:
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert button.toolTip().startswith("Nicht gespeichert") and button.accessibleName() == "Nicht gespeichert"
    window.resize(SAVE_STATE_COMPACT_WIDTH + 200, 900)
    qapp.processEvents()
    window._update_save_state()
    if window.width() >= SAVE_STATE_COMPACT_WIDTH:
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    assert not button.icon().isNull() and len(button.text()) <= 25
    assert window.selection_label.isHidden()           # leere Felder nehmen keinen Platz weg


# ================================================================== Schreibweisen und Tipp
def test_notation_dialog_is_deleted_after_closing(window, monkeypatch, qapp):
    """Review A‑1."""
    from app.dialogs.notation import NotationDialog

    monkeypatch.setattr(NotationDialog, "exec", lambda dialog: 0)
    window.show_notation_help()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not window.findChildren(NotationDialog)


def test_hint_stays_away_in_the_presentation_view(window, qapp):
    """Review A‑2 / Probelauf: am Beamer kein Tipp."""
    window.new_document()
    view = window.current_view()
    qapp.processEvents()
    view.notation_hint.refresh()
    shown_before = view.notation_hint.isVisible()
    window.set_presentation(True)
    qapp.processEvents()
    assert not view.notation_hint.isVisible()
    window.set_presentation(False)
    qapp.processEvents()
    view.notation_hint.refresh()
    assert view.notation_hint.isVisible() == shown_before


def test_hint_uses_neither_du_nor_sie():
    """Review A‑3: Die Kurzinfos siezen, der Tipp duzte – jetzt ist er neutral."""
    from app.canvas_hint import hint_text

    words = set(re.findall(r"\w+", hint_text().lower()))
    assert not words & {"du", "kannst", "sie", "können"}


def test_arabic_explanations_keep_notations_left_to_right():
    """Probelauf 4: „:=“ wird zwischen arabischen Wörtern nicht zu „=:“."""
    entry = next(e for e in notation.all_notations() if e.example == "zahl = 5")
    try:
        i18n.set_language("ar")
        assert "⁦:=⁩" in entry.meaning_text()
    finally:
        i18n.set_language("de")
    assert "⁦" not in entry.meaning_text()


def test_examples_are_drawn_left_to_right_but_copied_unchanged(qapp):
    from app.dialogs.notation import LeftToRightDelegate, NotationDialog

    dialog = NotationDialog()
    delegate = dialog.table.itemDelegateForColumn(1)
    assert isinstance(delegate, LeftToRightDelegate)
    option = QStyleOptionViewItem()
    option.direction = Qt.LayoutDirection.RightToLeft
    delegate.initStyleOption(option, dialog.table.model().index(1, 1))
    assert option.direction == Qt.LayoutDirection.LeftToRight
    assert all("⁦" not in dialog.table.item(row, 1).text() for row in range(dialog.table.rowCount()))
    assert "padding" in dialog.table.styleSheet()        # Spalten stoßen nicht aneinander
    dialog.deleteLater()


def test_lists_use_the_program_font_from_the_start(qapp):
    """Probelauf (Optik): Listen und Tabellen haben gleich die Programmschrift, nicht erst nach dem Farbwechsel."""
    styles.apply_application_style(qapp, styles.current_theme())
    assert QApplication.font("QAbstractItemView").family() == styles.ui_font().family()


# ================================================================== Bausteinliste und „Verbinden mit …“
def test_hidden_block_list_does_not_compute(qapp, monkeypatch):
    """Review E‑1: verborgen wird nichts gerechnet; sichtbar werden Zeilen an Ort und Stelle geändert."""
    calls = []
    original = block_list.flow_order
    monkeypatch.setattr(block_list, "flow_order", lambda scene: calls.append(1) or original(scene))
    document = DiagramDocument()
    a = add(document.scene, ElementType.START, 0, 0)
    panel = BlockListPanel()
    panel.set_document(document)
    panel.schedule_refresh()
    assert calls == []
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.show()
    assert calls and panel.element_ids() == [a.element_id]
    first = panel.list.item(0)
    b = add(document.scene, ElementType.PROCESS, 0, 200)
    panel.refresh()
    assert panel.list.item(0) is first and panel.element_ids() == [a.element_id, b.element_id]
    panel.list.setCurrentRow(1)
    connect(document.scene, a, "bottom", b, "top")
    panel.refresh()
    assert panel.list.currentRow() == 1 and panel.list.item(0) is first
    assert "→ Vorgang" in first.text()
    panel.close()
    panel.deleteLater()
    document.scene.clear_diagram()
    document.deleteLater()


def test_already_connected_through_a_junction(scene):
    """Review E‑2."""
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 400)
    host = connect(scene, a, "bottom", b, "top")
    scene.insert_junction(host, QPointF(0, 200))
    dialog = ConnectDialog(a, block_list.connect_targets(scene, a))
    texts = [dialog.list.item(row).text() for row in range(dialog.list.count())]
    assert texts == ["Vorgang „Vorgang“ – schon verbunden"]
    dialog.deleteLater()


def test_decision_marks_a_label_that_is_already_used(scene):
    """Probelauf 5: „ja“ ist schon vergeben – das steht in der Auswahl, vorgeschlagen wird „nein“."""
    decision = add(scene, ElementType.DECISION, 0, 0)
    yes = add(scene, ElementType.PROCESS, 0, 250)
    other = add(scene, ElementType.PROCESS, 300, 250)
    scene.connect_blocks(decision, yes)
    dialog = ConnectDialog(decision, block_list.connect_targets(scene, decision))
    combo = dialog.label_combo
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert texts == ["ja – schon vergeben", "nein", "ohne Beschriftung"]
    assert combo.itemData(0) == "ja" and dialog.label() == "nein"
    assert other in block_list.connect_targets(scene, decision)
    dialog.deleteLater()


# ================================================================== Zugriffstasten
NEW_ACTIONS = ("save_all", "close_all", "edit_task_file", "export_jpg", "connect_to", "jump_to_source",
               "jump_to_target", "toggle_block_list", "toggle_palette", "notation_help")


def _mnemonic(text: str) -> str | None:
    found = re.search(r"&([^&])", text)
    return found.group(1).lower() if found else None


def _clashes(actions, new_texts) -> list:
    seen = defaultdict(list)
    for action in actions:
        if action.text() and action.isVisible() and not action.isSeparator():
            seen[_mnemonic(action.text())].append(action.text())
    return [texts for key, texts in seen.items() if key and len(texts) > 1 and set(texts) & new_texts]


@pytest.mark.parametrize("code", ["de", "en", "fr", "es", "pt", "ru", "ar", "ja", "zh"])
def test_new_entries_have_their_own_access_key(qapp, monkeypatch, tmp_path, code):
    """Review A/C/E‑4: Kein neuer Menüeintrag teilt seinen unterstrichenen Buchstaben mit einem anderen – in den
    Menüs und in den Kontextmenüs von Pfeil und Baustein, in jeder Sprache."""
    from app import main_window as main_window_module
    from app.main_window import MainWindow

    i18n.set_language(code)
    win = MainWindow(enable_autosave=False, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    try:
        if win.current_document() is None:
            win.new_document()
        new_texts = {win.actions[name].text() for name in NEW_ACTIONS}
        problems = []
        for top in win.menuBar().actions():
            if top.menu() is not None:
                problems += _clashes(top.menu().actions(), new_texts)
        captured = []

        class CapturingMenu(QMenu):
            def exec(self, *_args):
                captured.append(list(self.actions()))

        monkeypatch.setattr(main_window_module, "QMenu", CapturingMenu)
        scene = win.current_scene()
        a = add(scene, ElementType.PROCESS, 0, 0)
        b = add(scene, ElementType.PROCESS, 0, 300)
        line = connect(scene, a, "bottom", b, "top")
        start, end = line.points()[0], line.points()[1]
        win.show_context_menu(QPointF((start[0] + end[0]) / 2, (start[1] + end[1]) / 2), QPoint(0, 0))
        win.show_context_menu(a.scene_rect().center(), QPoint(0, 0))
        assert len(captured) == 2
        for actions in captured:
            problems += _clashes(actions, new_texts)
        assert not problems, problems
    finally:
        for view in win.views():
            view.document.undo_stack.setClean()
        win.close()
        win.deleteLater()
        i18n.set_language("de")


# ================================================================== Exportordner
def test_export_remembers_the_last_folder(window, monkeypatch, tmp_path):
    """Probelauf (Optik): Auch ein unbenanntes Projekt schlägt beim nächsten Export den zuletzt benutzten Ordner vor."""
    window.new_document()
    add(window.current_scene(), ElementType.PROCESS, 0, 0)
    monkeypatch.setattr(window, "_export_options", lambda _fmt: export.ExportOptions(scale=1.0))
    folder = tmp_path / "Bilder"
    folder.mkdir()
    asked = []

    def save_name(_parent, _title, suggestion, filters):
        asked.append(suggestion)
        return str(folder / f"bild{len(asked)}"), filters

    monkeypatch.setattr(QFileDialog, "getSaveFileName", save_name)
    window.actions["export_png"].trigger()
    window.actions["export_jpg"].trigger()
    assert (folder / "bild1.png").exists() and (folder / "bild2.jpg").exists()
    assert os.path.dirname(asked[1]) == str(folder)
    window.new_document()                                  # auch ein anderes, unbenanntes Projekt
    add(window.current_scene(), ElementType.PROCESS, 0, 0)
    window.actions["export_svg"].trigger()
    assert os.path.dirname(asked[2]) == str(folder)
