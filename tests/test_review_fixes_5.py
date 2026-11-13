"""Regressionstests zur Prüfung des Gemini-Berichts (Version 1.15.1): Schreibtischtest-Panel, Sicherung,
Runden, Dateiversion mit Aufgabe, Dateizuordnung und Umgebung nach einem Update."""

import os
import sys
import time
import xml.etree.ElementTree as ET

import pytest
from PySide6.QtCore import QPointF

from app import config, policy, updater
from app.document import DiagramDocument
from app.fileformat.project import EXTENSION_NAMESPACE, TASK_FORMAT_VERSION
from app.fileformat.serializer import load_diagram, save_diagram
from app.model.element_types import ElementType as T

BST = "{" + EXTENSION_NAMESPACE + "}"


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


# 1 – Auswahl der Abläufe im Schreibtischtest: nicht bei jeder einzelnen Änderung neu berechnen
def test_simulation_panel_does_not_recompute_on_every_change_while_hidden():
    from app.simulation.panel import SimulationPanel

    document = DiagramDocument()
    panel = SimulationPanel()
    panel.set_document(document)
    calls = []
    original = document.flow_graph
    document.flow_graph = lambda: calls.append(1) or original()
    document.scene.insert_element(T.START, QPointF(0, 0))
    for index in range(30):
        document.scene.insert_element(T.PROCESS, QPointF(0, 100 + 80 * index))
    assert calls == []          # verborgen: gar nicht gerechnet
    panel.restart()             # vor dem Start wird nachgeholt
    assert panel.program_combo.count() == 1 and calls
    panel.stop(silent=True)
    panel.set_document(None)
    panel.deleteLater()
    document.scene.clear_diagram()


# 2 – Sicherung vergleicht den Inhalt, nicht die Stelle im Rückgängig-Verlauf
def test_autosave_notices_new_change_after_undo(tmp_path):
    from app.autosave import AutosaveManager

    manager = AutosaveManager(str(tmp_path), interval_ms=3600000)
    document = DiagramDocument()
    document.scene.insert_element(T.PROCESS, QPointF(0, 0))
    manager.register(document)
    assert manager.save_now() == 1
    document.undo_stack.undo()
    document.scene.insert_element(T.OUTPUT, QPointF(0, 0))   # gleiche Stelle im Verlauf, anderer Inhalt
    assert manager.save_now() == 1
    saved = load_diagram(manager._backup_path(document)).diagram
    assert [e.type for e in saved.elements] == [T.OUTPUT]
    assert manager.save_now() == 0
    manager.shutdown()
    document.scene.clear_diagram()


# 3 – Wiederherstellen: alte Sicherung bleibt, bis die neue geschrieben ist
def test_restored_backup_survives_until_new_backup(tmp_path, monkeypatch):
    from app import autosave as autosave_module
    from app.autosave import AutosaveManager

    crashed = AutosaveManager(str(tmp_path), interval_ms=3600000)
    document = DiagramDocument()
    document.scene.insert_element(T.PROCESS, QPointF(0, 0))
    crashed.register(document)
    crashed.save_now()
    crashed._timer.stop()
    survivor = AutosaveManager(str(tmp_path), interval_ms=3600000, pid_alive_func=lambda pid: False)
    entry = survivor.find_orphans()[0]
    restored = survivor.restore(entry)
    # Schreiben schlägt fehl (z. B. Datenträger voll): die alte Sicherung darf nicht verschwinden
    monkeypatch.setattr(autosave_module, "save_diagram", lambda *_a: (_ for _ in ()).throw(OSError("voll")))
    survivor.adopt(restored, entry)
    assert os.path.exists(entry.backup_path)
    monkeypatch.undo()
    survivor.adopt(restored, entry)
    assert not os.path.exists(entry.backup_path)
    survivor.shutdown()
    document.scene.clear_diagram()
    restored.scene.clear_diagram()


# 4 – runden mit riesiger Stellenzahl friert nicht ein
def test_rounding_with_huge_number_of_digits_returns_immediately():
    from app.codegen.generators import generate
    from app.simulation.evaluator import runden
    from tests.test_pic_asm import act, program

    started = time.perf_counter()
    assert runden(1.25, 100000000) == 1.25 and runden(2.5) == 3 and runden(1.25, 1) == 1.3
    assert time.perf_counter() - started < 1
    python = generate([program(act("x = runden(1.25, 100000000)"))], "python")
    namespace = {}
    exec(python.split("def main")[0], namespace)
    assert namespace["runden"](1.25, 100000000) == 1.25 and namespace["runden"](2.5) == 3
    assert "if (stellen > 15) return x;" in generate([program(act("x = runden(1.25, 3)"))], "java")


# 5 – Projekte mit Aufgabe bekommen Dateiversion 4, damit ältere Versionen sie nicht still verlieren
def test_task_raises_the_file_version(tmp_path):
    document = DiagramDocument()
    document.scene.insert_element(T.PROCESS, QPointF(0, 0))
    plain = document.to_diagram()
    path = tmp_path / "ohne.pap"
    save_diagram(plain, str(path))
    assert ET.parse(path).getroot().get(BST + "VERSION") == "1"
    with_task = document.to_diagram()
    with_task.meta.task_title = "Aufgabe 1"
    path = tmp_path / "mit.pap"
    save_diagram(with_task, str(path))
    assert ET.parse(path).getroot().get(BST + "VERSION") == str(TASK_FORMAT_VERSION) == "4"
    assert load_diagram(str(path)).diagram.meta.task_title == "Aufgabe 1"
    document.scene.clear_diagram()


# 6 und 7 – aus einer Update-Kopie: Dateizuordnung auf die installierte Version, Umgebung beim Neustart
@pytest.fixture
def user_copy(tmp_path, monkeypatch):
    installed = tmp_path / "Programme" / "PAP"
    installed.mkdir(parents=True)
    (installed / config.EXECUTABLE_NAME).write_bytes(b"")
    copy = os.path.join(updater.user_update_root(), "9.9.9")
    os.makedirs(copy)
    open(os.path.join(copy, config.EXECUTABLE_NAME), "wb").close()
    monkeypatch.setattr(updater.resources, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join(copy, config.EXECUTABLE_NAME))
    monkeypatch.setenv(policy.INSTALLATION_ENV, str(installed))
    return str(installed), copy


def test_file_association_from_user_copy_points_to_installed_program(user_copy):
    from app import file_association

    installed, copy = user_copy
    assert updater.installation_directory() == installed
    command = file_association.open_command()
    assert command == f'"{os.path.join(installed, config.EXECUTABLE_NAME)}" "%1"' and copy not in command
    assert copy not in file_association.icon_location()


def test_launch_program_passes_the_installation_to_a_user_copy(user_copy, monkeypatch):
    installed, copy = user_copy
    seen = {}
    monkeypatch.setattr(updater.subprocess, "Popen", lambda command, **kwargs: seen.update(kwargs))
    monkeypatch.delenv(policy.INSTALLATION_ENV)
    monkeypatch.setattr(updater, "installation_directory", lambda: installed)
    updater.launch_program(copy, wait_pid=123)
    assert seen["env"][policy.INSTALLATION_ENV] == installed
