"""Regressionstests zur dritten Prüfrunde (Version 1.15.3): Mehrfachverzweigung, Update, Dateikonflikte, Namen,
PIC-Speicher, Texte, Ausschneiden, Zwischenablage, Hinweise, Sicherungskopie, Minikarte, Sicherung."""

import contextlib
import io
import os
import time

import pytest
from PySide6.QtCore import QPointF

from app import updater
from app.analysis import text as T
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.codegen.pic_asm import FREE_CELLS, PicAsmGenerator
from app.document import DiagramDocument
from app.model.element_types import ElementType as E
from app.simulation.engine import Simulator
from tests.conftest import add, connect
from tests.test_pic_asm import act, program
from tests.test_subprograms import chain, window  # noqa: F401 (Fixture)


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


def outputs(document):
    simulator = Simulator(document.flow_graph())
    result = []
    for _ in range(100):
        if simulator.finished or simulator.pending is not None:
            break
        step = simulator.step()
        if step.output:
            result.append(step.output)
    return result


def python_output(document) -> str:
    code = generate(structure_diagram(document.flow_graph()), "python")
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(code, {"__name__": "__main__"})
    return buffer.getvalue().strip()


# 1 – Bedingungen in der Reihenfolge der Ausgänge, auch wenn zwei zum selben Ziel führen
@pytest.mark.parametrize("ports", [("right", "left", "bottom"), ("bottom", "left", "right"),
                                   ("bottom", "right", "left"), ("left", "right", "bottom")])
def test_overlapping_branch_conditions_run_like_the_desk_check(scene, document, ports):
    start = add(scene, E.START, 0, 0)
    step = add(scene, E.PROCESS, 0, 120)
    step.set_text("x = 2")
    decision = add(scene, E.DECISION, 0, 250)
    decision.set_text("x")
    a = add(scene, E.OUTPUT, -250, 400)
    a.set_text('Ausgabe "A"')
    b = add(scene, E.OUTPUT, 250, 400)
    b.set_text('Ausgabe "B"')
    end = add(scene, E.END, 0, 600)
    connect(scene, start, "bottom", step, "top")
    connect(scene, step, "bottom", decision, "top")
    for port, target, label in zip(ports, (a, b, a), (">= 0", "> 1", "sonst")):
        connect(scene, decision, port, target, "top" if label != "sonst" else "right").set_label(label)
    connect(scene, a, "bottom", end, "top")
    connect(scene, b, "bottom", end, "right")
    assert outputs(document) == [python_output(document)]


# 2 – Update: nach „Verwerfen“ nicht noch einmal fragen; läuft das alte Programm noch, nichts ersetzen
def test_closing_for_an_update_does_not_ask_again(window, monkeypatch):
    window.new_document()
    document = window.current_document()
    add(document.scene, E.PROCESS, 0, 0)
    assert document.is_modified
    window.close_without_asking = {document}
    asked = []
    monkeypatch.setattr(window, "maybe_save", lambda doc: asked.append(doc) or False)
    window.close()
    assert asked == []
    window.close_without_asking = set()


def test_update_is_not_applied_while_the_old_program_runs(monkeypatch):
    import main

    applied = []
    monkeypatch.setattr(updater, "wait_for_exit", lambda pid, seconds=60.0: False)
    monkeypatch.setattr(updater, "apply_update", lambda *a, **k: applied.append(a))
    monkeypatch.setattr(updater, "launch_program", lambda *a, **k: applied.append(a))
    warned = []
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    monkeypatch.setattr(main, "_show_splash", lambda app, text=None: type("S", (), {"close": lambda self: None})())
    monkeypatch.setattr(main, "_apply_look", lambda app: None)
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(main, "_create_application", lambda *a, **k: QApplication.instance())
    assert main._install_update(["C:/irgendwo", "123"]) == 1
    assert applied == [] and warned


# 12 – Aufräumen nach dem Update: nur selbst vermerkte .alt-Dateien
def test_cleanup_only_removes_recorded_backups(tmp_path):
    (tmp_path / "eigene.txt").write_text("x")
    (tmp_path / "eigene.txt.alt").write_text("Daten des Nutzers")
    (tmp_path / "kern.dll").write_text("neu")
    (tmp_path / "kern.dll.alt").write_text("alt")
    (tmp_path / updater.BACKUP_RECORD).write_text("kern.dll.alt\n", encoding="utf-8")
    updater.cleanup_staging(str(tmp_path))
    assert (tmp_path / "eigene.txt.alt").exists() and not (tmp_path / "kern.dll.alt").exists()
    assert not (tmp_path / updater.BACKUP_RECORD).exists()


# 3 – Datei von außen geändert: automatisches Speichern hält an, von Hand wird gefragt
def test_file_changed_outside_is_not_overwritten_silently(window, tmp_path, monkeypatch):
    window.new_document()
    document = window.current_document()
    path = tmp_path / "plan.pap"
    document.save(str(path))
    assert not document.changed_on_disk()
    add(document.scene, E.PROCESS, 0, 300)
    time.sleep(0.02)
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")   # anderes Programm
    os.utime(path, None)
    assert document.changed_on_disk()
    outside = path.read_text(encoding="utf-8")
    assert not window._save_to(document, str(path), automatic=True)
    assert path.read_text(encoding="utf-8") == outside
    asked = []
    monkeypatch.setattr(window, "_ask_disk_conflict", lambda doc: asked.append(doc) or "cancel")
    assert not window.save_document(document)
    assert asked == [document] and path.read_text(encoding="utf-8") == outside
    monkeypatch.setattr(window, "_ask_disk_conflict", lambda doc: "overwrite")
    assert window.save_document(document) and not document.changed_on_disk()


# 4 – eindeutige Namen je Sprache
def test_generated_names_do_not_collide():
    java = generate([program(act("double = 1"), act("double_ = 2"), act("Ausgabe double + double_", "output"))],
                    "java")
    fields = [line.strip() for line in java.splitlines() if line.strip().startswith("static double double")]
    assert len(fields) == len(set(fields)) == 2
    generator = PicAsmGenerator([program(act("ärger = 1"), act("aerger = 2"))])
    code = generator.generate()
    assert generator.var("ärger") != generator.var("aerger")
    assert code.split("cblock\t0x20")[1].split("endc")[0].split() == ["aerger", "aerger_2"]
    python = generate([program(act("sqrt = 4"), act("y = sqrt(9)"))], "python")
    assert "from math import sqrt" in python
    with contextlib.redirect_stdout(io.StringIO()):
        exec(python, {"__name__": "__main__"})


# 5 – zu viele Variablen für den PIC
def test_pic_warns_when_bank_0_is_full():
    many = PicAsmGenerator([program(*[act(f"v{i} = {i}") for i in range(FREE_CELLS + 4)])]).generate()
    assert "; TODO: Zu viele Variablen" in many
    few = PicAsmGenerator([program(act("a = 1"))]).generate()
    assert "Zu viele Variablen" not in few


# 6 – Text in Anführungszeichen: kein Trennen am „;“, Leerzeichen bleiben
def test_text_literals_keep_semicolons_and_spaces(scene, document):
    assert T.split_statements('x = "A;B"; y = 2\nz = 3') == ['x = "A;B"', "y = 2", "z = 3"]
    assert T.parse_assignments('x = "a  b"') == [("x", '"a  b"')]
    chain(scene, (E.START, "Start"), (E.PROCESS, 'x = "A;B"'), (E.OUTPUT, "Ausgabe x"), (E.END, "Ende"))
    assert outputs(document) == ["A;B"] == [python_output(document)]


# 7 – Ausschneiden wie Löschen: lose Pfeilenden fallen mit weg, Verbindungspunkte werden geheilt
def test_cut_removes_the_same_as_delete(qapp, monkeypatch):
    from app import clipboard
    from app.connections.endpoints import ConnectionEndpoint
    from app.model.element_types import LOOSE_END_KEY

    def plan():
        document = DiagramDocument()
        scene = document.scene
        items = chain(scene, (E.START, "Start"), (E.PROCESS, "x = 1"), (E.END, "Ende"))
        scene._leave_loose(ConnectionEndpoint(item=items[1], port="right"), "right", QPointF(300, 120))
        scene.select_items([items[1]])
        return document, scene

    monkeypatch.setattr(clipboard, "copy_selection", lambda _scene: True)
    cut_doc, cut_scene = plan()
    assert clipboard.cut_selection(cut_scene)
    del_doc, del_scene = plan()
    del_scene.delete_selection()
    assert len(cut_scene.elements()) == len(del_scene.elements()) == 2
    assert not [i for i in cut_scene.elements() if i.data.properties.get(LOOSE_END_KEY)]
    assert len(cut_scene.connections()) == len(del_scene.connections())
    cut_scene.undo_stack.undo()
    assert len(cut_scene.elements()) == 4


# 8 – „Als Bild kopieren“ meldet nur echten Erfolg
def test_copy_image_reports_a_busy_clipboard(scene, monkeypatch):
    from app import clipboard

    chain(scene, (E.START, "Start"), (E.END, "Ende"))
    monkeypatch.setattr(clipboard, "set_clipboard", lambda *a, **k: False)
    assert clipboard.copy_image(scene) is False


# 9 – Hinweisliste: eine abgestürzte Prüfung wird nicht als „keine Auffälligkeiten“ gemeldet
def test_failed_check_is_not_reported_as_clean(document, monkeypatch):
    from app.diagnostics import panel as panel_module

    monkeypatch.setattr(panel_module, "run_checks", lambda _doc: 1 / 0)
    panel = panel_module.DiagnosticsPanel()
    panel.set_document(document)
    assert "nicht geprüft" in panel.summary.text()
    panel.set_document(None)
    panel.deleteLater()


# 10 – Sicherungskopie: erst nach Erfolg vermerkt, nie halb geschrieben
def test_backup_copy_is_retried_after_a_failure(tmp_path, monkeypatch):
    import shutil

    from app import config

    document = DiagramDocument()
    path = tmp_path / "p.pap"
    document.save(str(path))
    real_copy = shutil.copy2
    monkeypatch.setattr(shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("gesperrt")))
    document.save(str(path), backup=True)
    assert not os.path.exists(config.backup_path_for(str(path)))
    monkeypatch.setattr(shutil, "copy2", real_copy)
    document.save(str(path), backup=True)
    assert os.path.exists(config.backup_path_for(str(path)))
    assert not os.path.exists(config.backup_path_for(str(path)) + ".tmp")
    document.scene.clear_diagram()


# 11 – Minikarte: sehr hohe Pläne – Zeichnung und Klick mit derselben Skalierung
def test_minimap_scale_respects_the_pixmap_limit(view):
    from app.minimap import MAX_PIXMAP_HEIGHT, Minimap

    scene = view.document.scene
    for index in range(80):
        add(scene, E.PROCESS, 0, index * 400)
    minimap = Minimap(view)
    minimap.resize(160, 600)
    minimap._watch_scene()
    minimap._render()
    assert minimap._source.height() * minimap.scale() * minimap.devicePixelRatioF() <= MAX_PIXMAP_HEIGHT + 1
    minimap.deleteLater()


# 13 – Sicherung wandelt den Plan nur einmal um
def test_autosave_serializes_once(tmp_path, monkeypatch):
    from app import autosave as autosave_module
    from app.autosave import AutosaveManager

    calls = []
    real = autosave_module.diagram_to_xml
    monkeypatch.setattr(autosave_module, "diagram_to_xml", lambda d: calls.append(1) or real(d))
    manager = AutosaveManager(str(tmp_path), interval_ms=3600000)
    document = DiagramDocument()
    document.scene.insert_element(E.PROCESS, QPointF(0, 0))
    manager.register(document)
    assert manager.save_now() == 1 and len(calls) == 1
    manager.shutdown()
    document.scene.clear_diagram()
