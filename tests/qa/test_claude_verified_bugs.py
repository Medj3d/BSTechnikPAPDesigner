"""QA (Claude): nachgestellte Fehler aus QA-BERICHT-CLAUDE.md als Tests.

Jeder Test ist ``xfail(strict=True)`` mit der Bug-Nummer: Ist der Fehler behoben, meldet sich der Test (XPASS) und die
Markierung kann weg.
"""

from __future__ import annotations

import os
import random
import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from app.document import DiagramDocument
from app.model.element_types import ElementType
from tests.qa.claude_qa_helpers import EXAMPLE, DialogStub, close_window, make_window, trap_errors

WINDOWS = sys.platform.startswith("win")


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    DialogStub(monkeypatch, random.Random(7), tmp_path, accept_rate=0.0)
    created = make_window(qapp)
    yield created
    close_window(created, qapp)


def test_closing_a_saved_tab_with_auto_save_raises_nothing(window, qapp, monkeypatch, tmp_path):
    trap = trap_errors(monkeypatch)
    window.set_auto_save(True)
    document = window.current_document()
    assert window._save_to(document, str(tmp_path / "tab.pap"))
    document.scene.insert_element(ElementType.PROCESS, QPointF(0, 0))
    document.undo_stack.setClean()   # wie nach dem automatischen Speichern
    window.close_tab(window.tabs.indexOf(window.current_view()))
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        qapp.processEvents()
    assert not trap.errors, trap.report()


def test_damaged_container_is_not_opened_as_an_empty_project(qapp, tmp_path):
    from app.fileformat.project import ProjectFileError

    with open(EXAMPLE, encoding="utf-8") as handle:
        broken = handle.read().replace("<DIAGRAMS>", "<DIAGRMAS>").replace("</DIAGRAMS>", "</DIAGRMAS>")
    path = tmp_path / "kaputt.pap"
    path.write_text(broken, encoding="utf-8")
    try:
        document = DiagramDocument.open_file(str(path))
    except ProjectFileError:
        return
    try:
        assert document.load_warnings, "leer geöffnet, aber ohne jeden Hinweis"
    finally:
        document.scene.clear_diagram()
        document.deleteLater()


def test_paste_after_undone_cut_is_offset(window, qapp):
    scene = window.current_scene()
    item = scene.element(scene.insert_element(ElementType.PROCESS, QPointF(0, 0)))
    scene.select_items([item])
    window.cut()
    window.current_document().undo_stack.undo()
    scene.select_items([])
    window.paste()
    positions = sorted((round(e.pos().x()), round(e.pos().y())) for e in scene.elements()
                       if e.element_type is ElementType.PROCESS)
    assert len(positions) == 2 and positions[0] != positions[1], positions


def test_undo_properties_after_save_keeps_the_file_name(window, qapp, monkeypatch, tmp_path):
    from app.dialogs.project_properties import ProjectPropertiesDialog

    def accept(dialog, *args):
        for name in ("author_edit", "author", "author_field"):
            field = getattr(dialog, name, None)
            if field is not None and hasattr(field, "setText"):
                field.setText("Max")
                break
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ProjectPropertiesDialog, "exec", accept)
    document = window.current_document()
    window.edit_properties()
    assert window._save_to(document, str(tmp_path / "Kreis.pap"))
    document.undo_stack.undo()
    document.undo_stack.redo()
    assert document.meta.name == "Kreis"


def test_tab_selects_the_next_block(window, qapp):
    scene = window.current_scene()
    scene.insert_element(ElementType.PROCESS, QPointF(0, 0))
    scene.insert_element(ElementType.OUTPUT, QPointF(0, 160))
    scene.clearSelection()
    window.activateWindow()
    QTest.qWait(30)
    if QApplication.activeWindow() is not window:
        pytest.skip("Fenster wird hier nicht aktiv")
    view = window.current_view()
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Tab)
    QTest.qWait(30)
    assert scene.selected_elements()


@pytest.mark.skipif(not WINDOWS, reason="8.3-Kurznamen gibt es nur unter Windows")
def test_same_file_via_short_and_long_path_opens_once(window, qapp, tmp_path):
    import ctypes

    folder = os.path.join(os.environ.get("USERPROFILE", str(tmp_path)), "AppData", "Local", "Temp",
                          f"pap qa kurz lang {os.getpid()}")
    os.makedirs(folder, exist_ok=True)
    path_long = os.path.join(folder, "gleich.pap")
    document = window.current_document()
    assert window._save_to(document, path_long)
    buffer = ctypes.create_unicode_buffer(600)
    ctypes.windll.kernel32.GetShortPathNameW(path_long, buffer, 600)
    path_short = buffer.value
    try:
        if not path_short or path_short.lower() == path_long.lower():
            pytest.skip("Kurznamen sind auf diesem Laufwerk abgeschaltet")
        window.open_file(path_short)
        opened = [v for v in window.views() if v.document.file_path
                  and os.path.basename(v.document.file_path).lower() == "gleich.pap"]
        assert len(opened) == 1, [v.document.file_path for v in opened]
    finally:
        for view in window.views():
            view.document.undo_stack.setClean()
        try:
            os.remove(path_long)
            os.rmdir(folder)
        except OSError:
            pass


def test_task_text_with_comparisons_is_shown_as_plain_text(qapp):
    from app.task_panel import TaskPanel

    panel = TaskPanel()
    document = DiagramDocument()
    document.meta.task_title = "Prüfe, ob a<b und b>c gilt"
    document.meta.task_text = "Aufgabe"
    try:
        panel.set_document(document)
        panel.refresh()
        labels = [label for label in panel.findChildren(QLabel) if "Prüfe" in label.text()]
        if not labels:
            pytest.skip("Titelfeld nicht gefunden – Test an das Aufgabenfeld anpassen")
        assert all(label.textFormat() == Qt.TextFormat.PlainText for label in labels), \
            [(label.text(), label.textFormat()) for label in labels]
    finally:
        panel.deleteLater()
        document.deleteLater()


def test_policy_file_written_by_powershell_disables_updates(tmp_path):
    from app import policy

    (tmp_path / "policy.ini").write_bytes("[Updates]\r\nDisabled=1\r\n".encode("utf-16"))
    assert policy.updates_disabled(str(tmp_path))


def test_teacher_task_file_is_never_overwritten_silently(window, qapp, monkeypatch, tmp_path):
    """QA-B15 (behoben): Aufgabe mit Passwort – automatisches Speichern und „Speichern“ lassen das Original in Ruhe."""
    from app import task as T

    teacher = DiagramDocument()
    T.apply_task(teacher.meta, T.Task("Aufgabe 3", "Zeichne …", T.encrypt("Lösung", "geheim"), T.make_lock("geheim")))
    original = tmp_path / "Aufgabe3.pap"
    teacher.save(str(original))
    teacher.deleteLater()
    before = original.read_bytes()

    window.set_auto_save(True)
    assert window.open_file(str(original))
    student = window.current_document()
    student.scene.insert_element(ElementType.PROCESS, QPointF(0, 0))
    window._run_auto_save()                             # automatisches Speichern hätte jetzt geschrieben
    assert original.read_bytes() == before

    copy = tmp_path / "Aufgabe3 Lösung.pap"
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getSaveFileName", lambda *a, **k: (str(copy), ""))
    assert window.save_document(student)               # „Speichern“ → eigene Datei
    assert original.read_bytes() == before and copy.exists()
    assert student.file_path == str(copy) and student.meta.task_copy == "1"

    student.scene.insert_element(ElementType.OUTPUT, QPointF(0, 200))
    assert window._auto_save_applies(student)           # die eigene Lösung wird wieder automatisch gespeichert
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getSaveFileName",
                        lambda *a, **k: pytest.fail("eigene Lösung soll ohne Dialog gespeichert werden"))
    assert window.save_document(student)
    reopened = DiagramDocument.open_file(str(copy))
    assert len(reopened.scene.elements()) == 2 and reopened.meta.task_lock
    reopened.deleteLater()
