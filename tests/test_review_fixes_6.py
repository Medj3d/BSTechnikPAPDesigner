"""Regressionstests zur zweiten Prüfrunde (Version 1.15.2): Schreibtischtest, Schleifen, Unterprogramm-Namen,
Code-Ansicht, Hinweise, Assembler, Wiederherstellen, Lehrermodus und Tastatursteuerung."""

import os

import pytest
from PySide6.QtCore import QPointF

from app.analysis import text as T
from app.analysis.ast import Action, Block, If, LimitLoop, Program
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.connections.endpoints import ConnectionEndpoint
from app.diagnostics.checks import run_checks
from app.document import DiagramDocument
from app.model.element_types import ElementType as E
from app.simulation.engine import Simulator
from tests.conftest import add, connect
from tests.test_pic_asm import act, asm, program
from tests.test_subprograms import chain, window  # noqa: F401 (Fixture)


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


def run(document):
    simulator = Simulator(document.flow_graph())
    for _ in range(200):
        if simulator.finished or simulator.pending is not None:
            break
        simulator.step()
    return simulator


# 8 – ein Vorgang mit einer unbekannten Zeile führt die übrigen trotzdem aus
def test_process_with_one_unknown_line_runs_the_others(scene, document):
    chain(scene, (E.START, "Start"), (E.PROCESS, "x = 1\nZähler erhöhen\ny = x + 1"), (E.END, "Ende"))
    assert T.assignment_items("x = 1; Zähler erhöhen; y = 2") == [("x", "1"), "Zähler erhöhen", ("y", "2")]
    assert run(document).variables == {"x": 1, "y": 2}
    python = generate(structure_diagram(document.flow_graph()), "python")
    assert "x = 1" in python and "# TODO: Zähler erhöhen" in python and "y = x + 1" in python


# 9 – Abdeckung: Unterprogramme zählen von Anfang an mit
def test_coverage_includes_called_subprograms_from_the_start(window):
    from app import subprograms

    window.new_document()
    document = window.current_document()
    chain(document.scene, (E.START, "Start"), (E.SUBPROGRAM, "hilfe"), (E.END, "Ende"))
    page = subprograms.create_subprogram(document, "hilfe")
    document.show_page(document.pages[0])
    start = page.start_items()[0]
    end = [i for i in page.scene.elements() if i.element_type is E.END][0]
    assert end is not None
    panel = window.simulation_panel
    panel.set_document(document)
    panel.restart()
    _done, total = panel.coverage()
    panel.step()
    assert panel.coverage()[1] == total >= 5
    panel.stop(silent=True)
    assert start is not None


# Freitext-Fuß: Die Schleife ist fußgesteuert und fragt am Ende – ein erkannter Kopf behält aber Vorrang
def test_free_text_footer_asks_but_never_overrides_a_real_header():
    asked = Program(name="T", start_id="s", end_id="x", end_text="Ende", body=Block([
        LimitLoop(header="Wiederhole", footer="bis Taster gedrückt", begin_id="b", end_id="e",
                  body=Block([act("x = 1")]))]))
    python = generate([asked], "python")
    assert 'if frage("bis Taster gedrückt"):' in python and "while frage" not in python
    headed = Program(name="T", start_id="s", end_id="x", end_text="Ende", body=Block([
        LimitLoop(header="solange x < 10", footer="solange Durchlauf aktiv", begin_id="b", end_id="e",
                  body=Block([act("x = x + 1")]))]))
    assert T.loop_footer("solange x < 10", "solange Durchlauf aktiv") is None
    assert "while x < 10:" in generate([headed], "python")
    assert "while (x < 10)" in generate([headed], "java")


# 10 – nach „Wiederholen“ die Seite des letzten Teilschritts
def test_redo_shows_the_page_where_the_step_ended(window):
    from app import subprograms

    window.new_document()
    document = window.current_document()
    page = subprograms.create_subprogram(document, "teil")
    command = document.undo_stack.command(document.undo_stack.index() - 1)
    assert document.command_page(command, last=True) is page


# 11 – Start einer Unterprogramm-Seite umbenennen benennt Seite und Aufrufe mit um; vergebene Namen nicht
def test_renaming_the_start_renames_the_subprogram(window):
    from app import subprograms

    window.new_document()
    document = window.current_document()
    chain(document.scene, (E.START, "Start"), (E.SUBPROGRAM, "alt"), (E.END, "Ende"))
    page = subprograms.create_subprogram(document, "alt")
    other = subprograms.create_subprogram(document, "anders")
    start = page.start_items()[0]
    assert document.rename_from_start(page.scene, start, "neu")
    assert page.display_name == "neu" and start.data.text == "neu"
    calls = [i for i in document.main_scene.elements() if i.element_type is E.SUBPROGRAM]
    assert calls[0].data.text == "neu"
    messages = []
    page.scene.status_message.connect(messages.append)
    assert document.rename_from_start(page.scene, start, "anders")   # vergeben: nichts ändern
    assert page.display_name == "neu" and start.data.text == "neu" and messages
    assert other.display_name == "anders"
    document.undo_stack.undo()
    assert page.display_name == "alt"


# 12 – Code-Ansicht: Markieren wählt nichts aus
def test_code_panel_selecting_text_does_not_select_blocks(document):
    from PySide6.QtGui import QTextCursor

    from app.codegen.live_panel import CodePanel

    chain(document.scene, (E.START, "Start"), (E.PROCESS, "x = 1"), (E.PROCESS, "y = 2"), (E.END, "Ende"))
    panel = CodePanel(language="python")
    panel.set_document(document)
    panel.refresh()
    requested = []
    panel.element_requested.connect(requested.append)
    cursor = panel.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 5)
    panel.editor.setTextCursor(cursor)
    assert requested == []
    panel.set_document(None)
    panel.deleteLater()


# 13 – der Hinweis im Code-Dialog passt zur Sprache
def test_code_dialog_note_matches_the_language(document):
    from app.codegen.dialog import CodeDialog

    chain(document.scene, (E.START, "Start"), (E.PROCESS, "x = 1"), (E.END, "Ende"))
    dialog = CodeDialog(document)
    assert "PORTB" in dialog.notes.text()
    dialog.language.setCurrentIndex(1)
    assert "unverändert" in dialog.notes.text()
    dialog.language.setCurrentIndex(2)
    assert "zur Laufzeit" in dialog.notes.text()
    dialog.deleteLater()


# 14 – Schnellmenü „Schleife“ an einem Pfeil nach oben: Eingang oben am Schleifenbeginn
def test_quick_menu_loop_upwards_uses_the_top_port(scene):
    block = add(scene, E.PROCESS, 0, 400)
    scene._quick_drag = {"source": ConnectionEndpoint(item=block, port="top"), "target": None,
                         "pos": QPointF(0, 300), "source_port": "top", "target_port": None, "error": None,
                         "warning": None, "press": QPointF(0, 300), "replaces": None, "moving": "target"}
    scene.finish_quick_menu(E.LOOP)
    links = [c for c in block.connections if c.source is block]
    assert len(links) == 1 and links[0].data.target_port == "top"
    loop = links[0].target
    assert loop.scene_rect().bottom() < block.scene_rect().top()


# 15 – Hinweise: Hauptprogramm ohne Start; Raute ohne Ausgang nur einmal gemeldet
def test_checks_main_without_start_and_no_duplicate_dead_end(window):
    from app import subprograms

    window.new_document()
    document = window.current_document()
    for item in list(document.main_scene.elements()):
        if item.element_type is E.START:
            document.main_scene.remove_element_item(item)
    add(document.main_scene, E.PROCESS, 0, 0)
    subprograms.create_subprogram(document, "up")
    messages = [issue.message for issue in run_checks(document)]
    assert "Das Hauptprogramm hat kein Start-Element." in messages
    other = DiagramDocument()
    start = add(other.scene, E.START, 0, 0)
    decision = add(other.scene, E.DECISION, 0, 150)
    connect(other.scene, start, "bottom", decision, "top")
    about = [i.message for i in run_checks(other) if decision.element_id in i.element_ids or "Nachfolger" in i.message]
    assert len([m for m in about if "Nachfolger" in m or "Ausgänge" in m]) == 1
    # die Raute ohne Ausgang bleibt im Code eine Verzweigung (keine Zuweisung)
    programs = structure_diagram(other.flow_graph())
    assert isinstance(programs[0].body.statements[0], If)
    other.scene.clear_diagram()


# N1 – runden mit sehr vielen Stellen vor dem Komma
def test_rounding_with_hugely_negative_digits():
    from app.simulation.evaluator import evaluate, runden

    assert runden(100, -400) == 0 and runden(1234, -2) == 1200 and runden(1e308, -301) > 1e307
    assert evaluate("runden(100, -400)", {}) == 0


# N3 – Assembler: „;“ trennt Anweisungen, gelesene Ports werden Eingänge
def test_pic_semicolons_and_ports_read_in_expressions():
    code = asm(act("warte 100 ms; PORTD.0 = 1"), act("a = 1; b = a << 2"), act("x = PORTB & 15"))
    assert "\tCALL\twarte_ms" in code and "\tBSF\tPORTD, 0" in code
    assert "\tMOVWF\tb" in code and "; TODO" not in code
    assert "\tMOVLW\tb'11111111'\n\tMOVWF\tTRISB" in code and "; Beschaltung PORTB : Eingabe" in code
    assert "; TODO" in asm(act("warte 100 ms lang"))   # nichts wird still verschluckt


# Wiederherstellen: eine kaputte Sicherung wird beiseitegelegt, nicht gelöscht
def test_unreadable_backup_is_set_aside(tmp_path):
    from app.autosave import AutosaveManager, RecoveryEntry

    backup = tmp_path / "alt_abc.pap"
    backup.write_text("kaputt", encoding="utf-8")
    entry = RecoveryEntry(backup_path=str(backup), meta_path=str(backup) + ".json", display_name="x",
                          original_path=None, saved_at="", session_id="alt")
    manager = AutosaveManager(str(tmp_path), interval_ms=3600000)
    kept = manager.set_aside(entry)
    assert kept and os.path.exists(kept) and not backup.exists()
    assert manager.find_orphans() == []
    manager.shutdown()


# K1.4 – wiederhergestellte Projekte werden nicht still in die Originaldatei geschrieben
def test_restored_document_is_not_auto_saved(window, tmp_path):
    window.new_document()
    document = window.current_document()
    path = tmp_path / "p.pap"
    window._auto_save_enabled = True
    document.save(str(path))
    assert window._auto_save_applies(document)
    document.restored_from_backup = True
    assert not window._auto_save_applies(document)
    document.save(str(path))
    assert window._auto_save_applies(document)


# Lehrermodus: Passwort entfernen
def test_task_password_can_be_removed():
    from app import task as TK
    from app.task_panel import TaskDialog

    locked = TK.Task(title="A", text="B", lock=TK.make_lock("geheim"))
    dialog = TaskDialog(locked)
    dialog.set_previous_password("geheim")
    dialog.remove_password.setChecked(True)
    result = dialog.result_task()
    assert result.title == "A" and not result.lock and not result.locked
    dialog.deleteLater()


# Tastatur: Tab wandert im Ablauf von Baustein zu Baustein
def test_tab_moves_through_the_flow(scene):
    items = chain(scene, (E.START, "Start"), (E.PROCESS, "x = 1"), (E.OUTPUT, "x"))
    scene.select_items([])
    assert scene.select_neighbour() is items[0]           # ohne Auswahl: Start
    assert scene.select_neighbour() is items[1]
    assert scene.select_neighbour() is items[2]
    assert scene.select_neighbour(forward=False) is items[1]


# Schleife ohne Kopf mit Freitext-Fuß: Der Schreibtischtest fragt am Schleifenende
def test_simulator_asks_at_a_free_text_footer(scene, document):
    from app.simulation.engine import NEEDS_DECISION

    start = add(scene, E.START, 0, 0)
    begin = scene.element(scene.insert_element(E.LOOP, QPointF(0, 150)))
    ends = [i for i in scene.elements() if i.element_type is E.LOOP and i is not begin]
    ends[0].set_text("bis Taster gedrückt")
    connect(scene, start, "bottom", begin, "top")
    simulator = Simulator(document.flow_graph())
    for _ in range(20):
        result = simulator.step()
        if simulator.pending is not None:
            break
    assert simulator.pending is not None and simulator.pending.needs == NEEDS_DECISION
    assert simulator.pending.element_id == ends[0].element_id
    assert isinstance(result, object)
    assert Action  # noqa: B018
