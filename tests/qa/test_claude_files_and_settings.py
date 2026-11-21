"""QA (Claude): Speichern an schwierigen Orten, Nachfrage beim Schließen, Einstellungen über einen Neustart.

Windows-Fälle (schreibgeschützt, von einem anderen Programm gesperrt) laufen nur unter Windows.
"""

from __future__ import annotations

import os
import random
import stat
import sys

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMessageBox

from app import preferences, theme
from app.document import DiagramDocument
from app.fileformat.project import ProjectFileError
from app.model.element_types import ElementType
from tests.qa.claude_qa_helpers import DialogStub, close_window, make_window, snapshot_document, trap_errors

WINDOWS = sys.platform.startswith("win")


def _plan(document):
    scene = document.scene
    a = scene.element(scene.insert_element(ElementType.PROCESS, QPointF(0, 0)))
    b = scene.element(scene.insert_element(ElementType.OUTPUT, QPointF(0, 160)))
    scene.create_connection(a, "bottom", b, "top")
    scene.begin_element_edit(a, select_all=True)
    scene._editor.setPlainText("Ä ö ü ß – 😀 „Zitat“ <&> x ≠ 1")
    scene.commit_edit()
    return a


@pytest.mark.parametrize("name", ["Übung Nr. 1 (Kopie) 😀.pap", "a" * 120 + ".pap", "Plan mit  zwei Leerzeichen.pap",
                                  "ordner mit ümläuten/und leerzeichen/Plan.pap"])
def test_tricky_paths_roundtrip(qapp, tmp_path, name):
    document = DiagramDocument()
    _plan(document)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == []
    assert snapshot_document(reopened) == snapshot_document(document)
    for doc in (document, reopened):
        doc.scene.clear_diagram()
        doc.deleteLater()


@pytest.mark.skipif(not WINDOWS, reason="Schreibschutz-Attribut gibt es so nur unter Windows")
def test_read_only_file_gives_clear_message_and_stays_unchanged(qapp, tmp_path):
    document = DiagramDocument()
    _plan(document)
    path = tmp_path / "schreibgeschützt.pap"
    document.save(str(path))
    before = path.read_bytes()
    os.chmod(path, stat.S_IREAD)
    try:
        document.scene.insert_element(ElementType.PROCESS, QPointF(300, 0))
        with pytest.raises(ProjectFileError) as caught:
            document.save(str(path))
        assert "Schreibberechtigung" in str(caught.value)
        assert path.read_bytes() == before
        assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")], "Zwischendatei bleibt liegen"
    finally:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        document.scene.clear_diagram()
        document.deleteLater()


@pytest.mark.skipif(not WINDOWS, reason="Sperren durch ein anderes Programm wird unter Windows geprüft")
def test_file_locked_by_another_program_gives_clear_message(qapp, tmp_path):
    import ctypes
    from ctypes import wintypes

    document = DiagramDocument()
    _plan(document)
    path = tmp_path / "gesperrt.pap"
    document.save(str(path))
    create = ctypes.windll.kernel32.CreateFileW
    create.restype = wintypes.HANDLE
    # wie Word/Excel: geöffnet ohne Freigabe für andere (share mode 0)
    handle = create(str(path), 0x80000000, 0, None, 3, 0x80, None)
    assert handle not in (None, wintypes.HANDLE(-1).value)
    try:
        with pytest.raises(ProjectFileError) as caught:
            document.save(str(path))
        assert "anderen Programm" in str(caught.value) or "Schreibberechtigung" in str(caught.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    document.save(str(path))   # danach geht es wieder
    document.scene.clear_diagram()
    document.deleteLater()


def test_missing_folder_gives_clear_message(qapp, tmp_path):
    document = DiagramDocument()
    _plan(document)
    with pytest.raises(ProjectFileError) as caught:
        document.save(str(tmp_path / "gibt es nicht" / "plan.pap"))
    assert "existiert nicht" in str(caught.value)
    document.scene.clear_diagram()
    document.deleteLater()


# ----------------------------------------------------------------- Schließen mit ungespeicherten Änderungen
@pytest.mark.parametrize("answer, closes", [("Abbrechen", False), ("Verwerfen", True), ("Speichern", True)])
def test_closing_with_unsaved_changes_asks_and_obeys(qapp, monkeypatch, tmp_path, answer, closes):
    trap = trap_errors(monkeypatch)
    DialogStub(monkeypatch, random.Random(0), tmp_path)
    asked = []

    def fake_exec(box, *args):
        asked.append(box.text())
        next(b for b in box.buttons() if b.text() == answer).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    window = make_window(qapp)
    saved_to = []
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getSaveFileName",
                        lambda *a, **k: (saved_to.append(str(tmp_path / "neu.pap")) or str(tmp_path / "neu.pap"), ""))
    try:
        _plan(window.current_document())
        window.close()
        qapp.processEvents()
        assert asked and "geändert" in asked[0]
        assert window.isVisible() is not closes
        if answer == "Speichern":
            assert os.path.exists(tmp_path / "neu.pap")
            reopened = DiagramDocument.open_file(str(tmp_path / "neu.pap"))
            assert len(reopened.scene.elements()) == 2
            reopened.scene.clear_diagram()
        assert not trap.errors, trap.report()
    finally:
        if window.isVisible():
            close_window(window, qapp)
        else:
            from tests.qa.claude_qa_helpers import clear_test_settings
            clear_test_settings()


# ----------------------------------------------------------------- Einstellungen über einen Neustart
def test_settings_survive_a_restart(qapp, monkeypatch, tmp_path):
    DialogStub(monkeypatch, random.Random(0), tmp_path)
    first = make_window(qapp)
    try:
        first.actions[preferences.action_name(preferences.EXTENDED_CHECKS)].trigger()        # an
        first.actions[preferences.action_name(preferences.TOOL_MINIMAP)].trigger()           # Knopf an
        first.actions["toggle_minimap"].trigger()                                             # Minikarte aus
        first.actions["theme_dark"].trigger()
        first.actions.assign("structogram", [QKeySequence("Ctrl+Alt+S")])
        first._on_shortcuts_changed()
        first.actions["auto_save"].trigger()
        for view in first.views():
            view.document.undo_stack.setClean()
        first.close()
        preferences.reset()
        second = make_window(qapp)
        try:
            assert preferences.enabled(preferences.EXTENDED_CHECKS) is True
            assert second.actions[preferences.action_name(preferences.TOOL_MINIMAP)].isChecked()
            assert second.actions["toggle_minimap"].isChecked() is False
            assert theme.saved_theme_name() == "dark"
            assert second.actions["structogram"].shortcuts()[0] == QKeySequence("Ctrl+Alt+S")
            assert second.actions["auto_save"].isChecked()
        finally:
            close_window(second, qapp)
    finally:
        first.deleteLater()
        preferences.reset()
