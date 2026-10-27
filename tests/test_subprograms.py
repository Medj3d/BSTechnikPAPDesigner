"""Unterprogramme auf eigenen Seiten: anlegen, aufrufen, umbenennen, löschen, speichern und ausführen."""

import os
import shutil

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from app import export, subprograms
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.diagnostics.checks import INFO, WARNING, run_checks
from app.dialogs.subprogram_name import SubprogramNameDialog
from app.document import DiagramDocument
from app.fileformat.project import CURRENT_FORMAT_VERSION, EXTENSION_NAMESPACE
from app.fileformat.serializer import diagram_to_xml, load_diagram, save_diagram
from app.model.diagram import ConnectionData, Diagram, ElementData, SubprogramPage
from app.model.element_types import ElementType as T
from app.simulation.engine import NEEDS_INPUT, Simulator
from tests.conftest import add, connect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAP_SAMPLE = os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap")
BST = f"{{{EXTENSION_NAMESPACE}}}"


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


def chain(scene, *steps, x=0):
    """Legt Start → Schritte → Ende an und verbindet alles. ``steps``: (Typ, Text)."""
    items = []
    for index, (etype, text) in enumerate(steps):
        item = add(scene, etype, x, index * 120)
        scene.element(item.element_id).set_text(text)
        items.append(item)
    for source, target in zip(items, items[1:]):
        assert connect(scene, source, "bottom", target, "top") is not None
    return items


def main_program(window):
    """Hauptprogramm: Start → Eingabe n → Unterprogramm „Verdoppeln“ → Ausgabe n → Ende."""
    window.new_document()
    document = window.current_document()
    items = chain(document.scene, (T.START, "Start"), (T.INPUT, "n einlesen"), (T.SUBPROGRAM, "Verdoppeln"),
                  (T.OUTPUT, "n ausgeben"), (T.END, "Ende"))
    return document, items


def fill_subprogram(page):
    """Füllt die neue Seite: Start → n = n * 2 → Ende."""
    start, end = page.start_items()[0], [i for i in page.scene.elements() if i.element_type is T.END][0]
    link = [c for c in page.scene.connections()][0]
    page.scene.insert_element(T.PROCESS, QPointF(0, 60), into_connection=link)
    process = [i for i in page.scene.elements() if i.element_type is T.PROCESS][0]
    process.set_text("n = n * 2")
    return start, process, end


def run(document, inputs):
    simulator = Simulator(document.flow_graph())
    inputs = iter(inputs)
    for _ in range(1000):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input(next(inputs))
        if simulator.finished:
            break
    assert simulator.finished
    return simulator


# ------------------------------------------------------------------ Anlegen und Aufrufen
def test_new_subprogram_creates_own_page_with_start_and_end(window):
    document, _items = main_program(window)
    assert window.new_subprogram("Verdoppeln")
    assert len(document.pages) == 2 and document.current_page_index == 1
    page = document.pages[1]
    assert page.display_name == "Verdoppeln" and page.flow_name == "verdoppeln"
    types = sorted(item.element_type.value for item in page.scene.elements())
    assert types == ["end", "start"] and len(page.scene.connections()) == 1
    assert page.start_items()[0].data.text == "Verdoppeln"
    # die Hauptseite bleibt unverändert, die Ansicht zeigt die neue Seite
    assert len(document.main_scene.elements()) == 5
    assert window.current_view().scene() is page.scene
    assert window.page_bar.tabs.count() == 2 and window.page_bar.tabs.tabText(1) == "Verdoppeln"
    # ein Rückgängig-Schritt entfernt die ganze Seite, Wiederholen bringt sie zurück
    window._undo()
    assert len(document.pages) == 1 and window.current_view().scene() is document.main_scene
    assert window.page_bar.tabs.count() == 1
    window._redo()
    assert len(document.pages) == 2 and document.pages[1] is page and len(page.scene.elements()) == 2


def test_subprogram_on_other_page_runs_in_desk_check_and_code(window, monkeypatch, capsys):
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    fill_subprogram(document.pages[1])
    simulator = run(document, ["5"])
    assert simulator.outputs == ["10"]
    programs = structure_diagram(document.flow_graph())
    assert [p.name for p in programs] == ["Start", "Verdoppeln"]
    code = generate(programs, "python")
    assert "def verdoppeln():" in code and "verdoppeln()" in code
    monkeypatch.setattr("builtins.input", lambda *_a: "5")
    exec(compile(code, "plan.py", "exec"), {"__name__": "__main__"})
    assert capsys.readouterr().out.strip().splitlines()[-1] == "10"


def test_desk_check_panel_follows_call_into_subprogram_page(window, qapp):
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    start, process, _end = fill_subprogram(document.pages[1])
    window.show_page(0)
    window.simulation_dock.show()
    panel = window.simulation_panel
    panel.restart()
    for _ in range(3):  # Start, Eingabe (wartet), …
        panel.step()
    panel.input_field.setText("5")
    panel.submit_input()
    # Unterprogramm-Baustein: Sprung auf die Seite des Unterprogramms
    while panel.simulator.current not in (start.element_id, process.element_id):
        panel.step()
    assert document.current_page_index == 1
    assert panel._highlight is not None and panel._highlight.scene() is document.pages[1].scene
    while not panel.simulator.finished:
        panel.step()
    assert panel.simulator.outputs == ["10"] and document.current_page_index == 0


def test_ctrl_double_click_or_context_action_opens_or_creates_subprogram(window, monkeypatch):
    document, items = main_program(window)
    call = items[2]
    asked = []
    monkeypatch.setattr(window, "_ask_subprogram_name",
                        lambda doc, title, initial, page=None: asked.append(initial) or initial)
    # noch keine Seite: wird mit dem Namen aus dem Baustein angelegt
    document.scene.subprogram_requested.emit(call)
    QApplication.processEvents()  # geöffnet wird erst nach dem Doppelklick
    assert asked == ["Verdoppeln"] and len(document.pages) == 2 and document.current_page_index == 1
    # vorhanden: nur hinspringen und den Start auswählen
    window.show_page(0)
    assert window.open_subprogram_for(call)
    assert asked == ["Verdoppeln"] and document.current_page_index == 1
    assert document.scene.selected_elements() == document.pages[1].start_items()


def test_creating_from_block_with_new_name_updates_the_call(window, monkeypatch):
    document, items = main_program(window)
    call = items[2]
    call.set_text("berechne(n, 2)")
    monkeypatch.setattr(window, "_ask_subprogram_name", lambda *a, **k: "Summe")
    assert window.open_subprogram_for(call)
    assert call.data.text == "Summe(n, 2)" and document.pages[1].display_name == "Summe"
    window._undo()  # ein Schritt: Seite und geänderter Aufruf
    assert len(document.pages) == 1 and call.data.text == "berechne(n, 2)"


def test_rename_updates_start_and_all_calls_in_one_step(window):
    document, items = main_program(window)
    window.new_subprogram("Verdoppeln")
    page = document.pages[1]
    # ein weiterer Aufruf auf der Unterprogramm-Seite selbst, mit Argumenten
    extra = add(page.scene, T.SUBPROGRAM, 300, 0)
    extra.set_text("verdoppeln(x)")
    window.show_page(0)
    assert window.rename_subprogram(1, "Mal zwei")
    assert page.display_name == "Mal zwei" and items[2].data.text == "Mal zwei"
    assert extra.data.text == "mal_zwei(x)"
    assert window.page_bar.tabs.tabText(1) == "Mal zwei"
    window._undo()
    assert page.display_name == "Verdoppeln" and items[2].data.text == "Verdoppeln"
    assert extra.data.text == "verdoppeln(x)"


def test_page_keeps_its_name_when_the_start_text_changes(window):
    """Wie im PapDesigner heißt ein Unterprogramm wie seine Seite – der Start darf z. B. einfach „Start“ heißen."""
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    page = document.pages[1]
    fill_subprogram(page)
    page.start_items()[0].set_text("Start")
    assert page.display_name == "Verdoppeln" and page.flow_name == "verdoppeln"
    assert run(document, ["5"]).outputs == ["10"]
    assert [p.name for p in structure_diagram(document.flow_graph())] == ["Start", "Verdoppeln"]


def test_delete_subprogram_and_undo_restores_content(window, monkeypatch):
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    page = document.pages[1]
    before = len(page.scene.elements())
    # Nachfrage: Abbrechen lässt alles stehen
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    assert not window.delete_subprogram(1)
    assert len(document.pages) == 2
    assert window.delete_subprogram(1, confirm=False)
    assert len(document.pages) == 1 and document.current_page_index == 0
    window._undo()
    assert document.pages[1] is page and len(page.scene.elements()) == before
    assert document.current_page_index == 1


def test_main_page_cannot_be_renamed_or_deleted(window):
    document, _items = main_program(window)
    assert not window.rename_subprogram(0, "Anders")
    assert not window.delete_subprogram(0, confirm=False)
    assert len(document.pages) == 1


def test_name_check(window):
    document, _items = main_program(window)
    assert subprograms.name_error(document, "") is not None
    assert subprograms.name_error(document, "  ?!  ") is not None
    assert subprograms.name_error(document, "Start") is not None  # so heißt der Start des Hauptprogramms
    assert subprograms.name_error(document, "Verdoppeln") is None
    window.new_subprogram("Verdoppeln")
    assert subprograms.name_error(document, "verdoppeln") is not None  # gleicher Bezeichner
    assert subprograms.name_error(document, "Verdoppeln", document.pages[1]) is None  # die eigene Seite
    # der Vorschlag ist ein noch fehlender Aufruf, sonst „Unterprogramm 1“
    assert subprograms.suggested_name(document) == "Unterprogramm 1"
    dialog = SubprogramNameDialog(document, "Neu", "Verdoppeln")
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled() and dialog.error_label.text()
    dialog.name_edit.setText("  Mittelwert   berechnen ")
    assert ok.isEnabled() and dialog.name() == "Mittelwert berechnen"
    dialog.deleteLater()


def test_suggested_name_is_a_missing_call(window):
    document, _items = main_program(window)
    assert subprograms.suggested_name(document) == "Verdoppeln"


def test_undo_shows_the_page_it_changes(window):
    document, items = main_program(window)
    window.new_subprogram("Verdoppeln")
    page = document.pages[1]
    add(page.scene, T.PROCESS, 300, 300)
    window.show_page(0)
    window._undo()  # betrifft die Unterprogramm-Seite
    assert document.current_page_index == 1
    window.show_page(1)
    items[1].set_text("x")  # nur zur Sicherheit: direkte Änderungen sind kein Schritt
    window.show_page(0)
    document.scene.select_items([items[3]])
    document.scene.move_selection_by(20, 0)
    window.show_page(1)
    window._undo()
    assert document.current_page_index == 0


def test_page_navigation_actions(window):
    document, _items = main_program(window)
    window.new_subprogram("A")
    window.new_subprogram("B")
    assert document.current_page_index == 2
    assert not window.actions["next_page"].isEnabled() and window.actions["previous_page"].isEnabled()
    window.actions["previous_page"].trigger()
    window.actions["previous_page"].trigger()
    assert document.current_page_index == 0 and not window.actions["previous_page"].isEnabled()
    window.actions["next_page"].trigger()
    assert document.current_page_index == 1


def test_view_state_is_kept_per_page(window):
    document, _items = main_program(window)
    view = window.current_view()
    view.set_zoom(2.0)
    window.new_subprogram("Verdoppeln")
    assert view.zoom == 1.0
    view.set_zoom(0.5)
    window.show_page(0)
    assert view.zoom == 2.0
    window.show_page(1)
    assert view.zoom == 0.5


# ------------------------------------------------------------------ Hinweise
def test_hints_cover_all_pages_and_navigate_there(window):
    document, items = main_program(window)
    # Aufruf ohne Unterprogramm: Hinweis mit Weg zum Anlegen
    hints = [i for i in run_checks(document) if items[2].element_id in i.element_ids]
    assert hints and hints[0].severity == INFO and "Unterprogramm anlegen" in hints[0].message
    window.new_subprogram("Verdoppeln")
    page = document.pages[1]
    assert not [i for i in run_checks(document) if items[2].element_id in i.element_ids]
    # Seite ohne Start: Warnung; ein Klick führt auf die Seite
    lonely = add(page.scene, T.PROCESS, 300, 300)
    for start in page.start_items():
        page.scene.select_items([start])
        page.scene.delete_selection()
    warnings = [i for i in run_checks(document) if i.severity == WARNING and "kein Start-Element" in i.message]
    assert warnings
    window.show_page(0)
    window._navigate_to([lonely.element_id], [])
    assert document.current_page_index == 1 and page.scene.selected_elements() == [lonely]


# ------------------------------------------------------------------ Datei
def sample_with_subprogram() -> Diagram:
    diagram = Diagram()
    diagram.elements = [ElementData("s", T.START, 0, 0, 120, 40, "Start"),
                        ElementData("u", T.SUBPROGRAM, 0, 120, 160, 60, "Verdoppeln"),
                        ElementData("e", T.END, 0, 240, 120, 40, "Ende")]
    diagram.connections = [ConnectionData("c1", "s", "u", "bottom", "top"),
                           ConnectionData("c2", "u", "e", "bottom", "top")]
    diagram.subprograms = [SubprogramPage(
        name="Verdoppeln", zoom=1.5, view_center_x=10.0, view_center_y=-20.0,
        elements=[ElementData("s2", T.START, 0, 0, 120, 40, "Verdoppeln"),
                  ElementData("p2", T.PROCESS, 0, 120, 160, 60, "n = n * 2"),
                  ElementData("e2", T.END, 0, 240, 120, 40, "Ende")],
        connections=[ConnectionData("d1", "s2", "p2", "bottom", "top"),
                     ConnectionData("d2", "p2", "e2", "bottom", "top")])]
    return diagram


def test_subprogram_pages_are_saved_as_own_diagrams(tmp_path):
    import xml.etree.ElementTree as ET
    diagram = sample_with_subprogram()
    path = str(tmp_path / "plan.pap")
    save_diagram(diagram, path)
    root = ET.parse(path).getroot()
    assert root.get(f"{BST}VERSION") == str(CURRENT_FORMAT_VERSION) == "2"
    diagrams = root.findall("./PROJECT/DIAGRAMS/DIAGRAM")
    assert [d.get("NAME") for d in diagrams][1:] == ["Verdoppeln"]
    # wie im PapDesigner zählen die Nummern in jedem Diagramm neu ab 0 (Titel) und sind darin eindeutig
    for pap_diagram in diagrams:
        figures = list(pap_diagram.iter("FIGURE"))
        numbers = [f.get("ID") for f in figures] + [c.get("ID") for c in pap_diagram.iter("CONNECTION")]
        assert len(numbers) == len(set(numbers))
        assert figures[0].get("SUBTYPE") == "PapTitle" and figures[0].get("ID") == "0"
    result = load_diagram(path)
    assert result.native and result.warnings == [] and result.diagram == diagram


def test_project_without_subprograms_stays_format_version_1():
    assert ' bst:VERSION="1" ' in diagram_to_xml(Diagram())


def test_papdesigner_diagrams_open_as_pages(window, tmp_path):
    path = shutil.copy(PAP_SAMPLE, tmp_path / "mittelwert.pap")
    assert window.open_file(str(path))
    document = window.current_document()
    assert [page.display_name for page in document.pages] == ["Hauptprogramm", "Fehlermeldung"]
    # jede Seite beginnt links oben – nichts liegt mehr nebeneinander
    assert min(item.data.x for item in document.pages[1].scene.elements()) == 0
    assert document.pages[1].fit_on_show
    window.show_page(1)
    assert not document.pages[1].fit_on_show
    assert run(document, ["0"]).outputs == ["Keine Werte"]


def test_pages_survive_saving_and_reopening(window, tmp_path, monkeypatch):
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    fill_subprogram(document.pages[1])
    window.current_view().set_zoom(1.5)
    path = str(tmp_path / "plan.pap")
    assert window._save_to(document, path)
    window.close_tab(window.tabs.currentIndex())
    assert window.open_file(path)
    reopened = window.current_document()
    assert [page.display_name for page in reopened.pages] == ["Hauptprogramm", "Verdoppeln"]
    assert reopened.pages[1].view_state[0] == 1.5
    assert run(reopened, ["4"]).outputs == ["8"]


def test_pdf_and_print_contain_every_page(window, tmp_path):
    from PySide6.QtPdf import QPdfDocument
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    path = str(tmp_path / "plan.pdf")
    from app.main_window import _printable_scenes
    export.export_pdf(_printable_scenes(document), path, export.ExportOptions())
    pdf = QPdfDocument()
    pdf.load(path)
    assert pdf.pageCount() == 2
    # die Seiten sind so groß wie ihr Diagramm: das Hauptprogramm ist länger als das Unterprogramm
    assert pdf.pagePointSize(0).height() > pdf.pagePointSize(1).height()
    pdf.close()


def test_theme_switch_reaches_hidden_pages(window):
    document, _items = main_program(window)
    window.new_subprogram("Verdoppeln")
    window.show_page(0)
    window.set_theme("light")
    try:
        assert all(scene.theme.name == "light_ui" for scene in document.scenes())
    finally:
        window.set_theme("dark")


def test_document_without_window_keeps_old_single_canvas_subprograms():
    """Ältere Pläne mit allen Abläufen auf einer Fläche funktionieren weiter."""
    document = DiagramDocument()
    scene = document.scene
    chain(scene, (T.START, "Start"), (T.SUBPROGRAM, "Verdoppeln"), (T.OUTPUT, "n ausgeben"), (T.END, "Ende"))
    chain(scene, (T.START, "Verdoppeln"), (T.PROCESS, "n = 21 * 2"), (T.END, "Ende"), x=400)
    assert run(document, []).outputs == ["42"]
    found = document.flow_start("Verdoppeln")
    assert found is not None and found[0] is document.pages[0]
    scene.clear_diagram()
    QApplication.processEvents()


# ------------------------------------------------------------------ Befunde aus dem Review
def test_switching_page_while_dragging_keeps_the_move_undoable(window):
    document, items = main_program(window)
    window.new_subprogram("Verdoppeln")
    window.show_page(0)
    scene = document.scene
    block = items[1]
    scene.select_items([block])
    # Ziehen begonnen: Startposition gemerkt, Baustein schon verschoben
    scene._drag_move_active = True
    scene._move_start = {block.element_id: (block.pos().x(), block.pos().y())}
    block.setPos(block.pos() + QPointF(100, 0))
    index = document.undo_stack.index()
    window.actions["next_page"].trigger()  # Seitenwechsel mitten im Ziehen
    assert document.current_page_index == 1
    assert not scene.pointer_interaction_active()
    assert document.undo_stack.index() == index + 1 and document.is_modified
    window._undo()
    assert document.current_page_index == 0 and block.pos().x() == 0


def test_names_with_parameters_are_matched_by_the_word_before_the_bracket(window):
    document, items = main_program(window)
    assert subprograms.name_error(document, "int verdoppeln(int n)") is None
    window.new_subprogram("int verdoppeln(int n)")
    assert subprograms.name_error(document, "verdoppeln") is not None  # derselbe Name
    fill_subprogram(document.pages[1])
    items[2].set_text("n := verdoppeln(n)")
    assert run(document, ["5"]).outputs == ["10"]


def test_old_plans_with_subprogram_above_main_program(window):
    """Ältere Pläne: Unterprogramm auf derselben Fläche, oberhalb des Hauptprogramms."""
    window.new_document()
    document = window.current_document()
    scene = document.scene
    worker = chain(scene, (T.START, "Worker"), (T.PROCESS, "n = 7"), (T.END, "Ende"), x=400)
    main = chain(scene, (T.START, "Start"), (T.SUBPROGRAM, "Worker"), (T.OUTPUT, "n ausgeben"), (T.END, "Ende"))
    for item in main:
        item.setPos(item.pos() + QPointF(0, 500))
    assert document.main_start_id() == main[0].element_id
    assert document.flow_start("Worker") == (document.pages[0], worker[0])
    assert "Hauptprogramm" in subprograms.name_error(document, "Start")
    assert "Hauptprogramm" not in subprograms.name_error(document, "Worker")
    assert window.open_subprogram_for(main[1])  # öffnet den vorhandenen Ablauf, legt nichts an
    assert len(document.pages) == 1 and scene.selected_elements() == [worker[0]]
    assert run(document, []).outputs == ["7"]


def test_discarded_pages_are_released(window):
    import gc
    import weakref
    document, items = main_program(window)
    window.new_subprogram("Verdoppeln")
    page = weakref.ref(document.pages[1])
    window._undo()
    assert len(document.pages) == 1 and page() is not None  # Wiederholen braucht die Seite noch
    document.scene.select_items([items[1]])
    document.scene.move_selection_by(20, 0)  # neuer Schritt: das Anlegen kann nicht mehr wiederholt werden
    gc.collect()
    assert page() is None
    assert len([child for child in document.children() if child.metaObject().className() == "DiagramScene"
                or type(child).__name__ == "DiagramScene"]) == 1


def test_real_ctrl_double_click_opens_subprogram(window, qapp):
    from PySide6.QtTest import QTest
    document, items = main_program(window)
    window.new_subprogram("Verdoppeln")
    window.show_page(0)
    view = window.current_view()
    call = items[2]
    view.centerOn(call.scene_rect().center())
    qapp.processEvents()
    point = view.mapFromScene(call.scene_rect().center())
    ctrl = Qt.KeyboardModifier.ControlModifier
    before = document.undo_stack.index()
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, ctrl, point)
    qapp.processEvents()
    assert document.current_page_index == 1 and not document.main_scene.is_editing
    assert not document.main_scene.pointer_interaction_active()
    assert document.undo_stack.index() == before  # kein Verschieben, keine Textänderung


def test_block_with_default_text_gets_the_new_name(window, monkeypatch):
    window.new_document()
    document = window.current_document()
    block = add(document.scene, T.SUBPROGRAM, 0, 0)  # trägt noch den Standardtext „Unterprogramm“
    asked = []
    monkeypatch.setattr(window, "_ask_subprogram_name",
                        lambda doc, title, initial, page=None: asked.append(initial) or "Ausgabe")
    assert window.open_subprogram_for(block)
    assert asked == ["Unterprogramm 1"] and block.data.text == "Ausgabe"
    assert document.pages[1].display_name == "Ausgabe"


PAPDESIGNER_STYLE = """<?xml version="1.0" encoding="utf-8"?>
<FRAME GUID="2FB25471-B62C-4EE6-BD43-F819C095ACF8" FORMAT="0000" APP_VERSION="2.2.0.8" CHECKSUM="0">
  <PROJECT FORMAT="1.00" NAME="Datum" AUTHOR="" CREATED="2021.03.01 08:15:00" MODIFIED="2021.03.01 08:15:00">
    <DIAGRAMS>
      <DIAGRAM FORMAT="1.00" ID="0" NAME="Datum" CREATED="2021.03.01 08:15:00" MODIFIED="2021.03.01 08:15:00">
        <LAYOUT FORMAT="1.00" COLUMNS="1" ROWS="6"><ENTRIES>
          <ENTRY COLUMN="0" ROW="0" ANCHOR="True"><FIGURE SUBTYPE="PapTitle" FORMAT="1.00" ID="0"><TEXT><![CDATA[Datum]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="1"><FIGURE SUBTYPE="PapStart" FORMAT="1.00" ID="1"><TEXT><![CDATA[Start]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="2"><FIGURE SUBTYPE="PapInput" FORMAT="1.00" ID="2"><TEXT><![CDATA[Eingabe: jahr]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="3"><FIGURE SUBTYPE="PapModule" FORMAT="1.00" ID="3"><TEXT><![CDATA[bool schalt := isLeapYear(jahr)]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="4"><FIGURE SUBTYPE="PapOutput" FORMAT="1.00" ID="4"><TEXT><![CDATA[rest]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="5"><FIGURE SUBTYPE="PapEnd" FORMAT="1.00" ID="5"><TEXT><![CDATA[Ende]]></TEXT></FIGURE></ENTRY>
        </ENTRIES></LAYOUT>
        <CONNECTIONS>
          <CONNECTION FORMAT="1.00" ID="6" FROM="1" TO="2" TEXT="" /><CONNECTION FORMAT="1.00" ID="7" FROM="2" TO="3" TEXT="" />
          <CONNECTION FORMAT="1.00" ID="8" FROM="3" TO="4" TEXT="" /><CONNECTION FORMAT="1.00" ID="9" FROM="4" TO="5" TEXT="" />
        </CONNECTIONS>
      </DIAGRAM>
      <DIAGRAM FORMAT="1.00" ID="1" NAME="bool isLeapYear(int year)" CREATED="2021.03.01 08:15:00" MODIFIED="2021.03.01 08:15:00">
        <LAYOUT FORMAT="1.00" COLUMNS="1" ROWS="4"><ENTRIES>
          <ENTRY COLUMN="0" ROW="0" ANCHOR="True"><FIGURE SUBTYPE="PapTitle" FORMAT="1.00" ID="10"><TEXT><![CDATA[bool isLeapYear(int year)]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="1"><FIGURE SUBTYPE="PapStart" FORMAT="1.00" ID="11"><TEXT><![CDATA[Start]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="2"><FIGURE SUBTYPE="PapActivity" FORMAT="1.00" ID="12"><TEXT><![CDATA[rest = jahr mod 4]]></TEXT></FIGURE></ENTRY>
          <ENTRY COLUMN="0" ROW="3"><FIGURE SUBTYPE="PapEnd" FORMAT="1.00" ID="13"><TEXT><![CDATA[Ende]]></TEXT></FIGURE></ENTRY>
        </ENTRIES></LAYOUT>
        <CONNECTIONS>
          <CONNECTION FORMAT="1.00" ID="14" FROM="11" TO="12" TEXT="" /><CONNECTION FORMAT="1.00" ID="15" FROM="12" TO="13" TEXT="" />
        </CONNECTIONS>
      </DIAGRAM>
    </DIAGRAMS>
  </PROJECT>
</FRAME>
"""


def test_papdesigner_subprograms_named_by_their_diagram(window, tmp_path):
    """Echte PapDesigner-Dateien: Unterprogramme beginnen mit „Start“, ihr Name steht nur am Diagramm
    (oft mit Rückgabetyp und Parametern); aufgerufen wird z. B. mit „bool schalt := isLeapYear(jahr)“."""
    path = tmp_path / "datum.pap"
    path.write_text(PAPDESIGNER_STYLE, encoding="utf-8")
    assert window.open_file(str(path))
    document = window.current_document()
    assert [page.display_name for page in document.pages] == ["Hauptprogramm", "bool isLeapYear(int year)"]
    assert window.page_bar.tabs.tabText(1) == "bool isLeapYear(int year)"
    # Schreibtischtest, Code, Hinweise und Öffnen finden das Unterprogramm über den Namen der Seite
    assert run(document, ["2023"]).outputs == ["3"]
    programs = structure_diagram(document.flow_graph())
    assert [p.name for p in programs] == ["Start", "bool isLeapYear(int year)"]
    code = generate(programs, "python")
    assert "def isleapyear():" in code and "isleapyear()  # bool schalt := isLeapYear(jahr)" in code
    java = generate(programs, "java")
    assert "static void isLeapYear()" in java and "isLeapYear(); // bool schalt := isLeapYear(jahr)" in java
    assert not [i for i in run_checks(document) if "noch nicht gibt" in i.message]
    call = [item for item in document.main_scene.elements() if item.element_type is T.SUBPROGRAM][0]
    window.show_page(0)
    assert window.open_subprogram_for(call) and document.current_page_index == 1
    assert [window.simulation_panel.program_combo.itemText(i)
            for i in range(window.simulation_panel.program_combo.count())] == ["Start", "bool isLeapYear(int year)"]
    # Umbenennen lässt den Start „Start“ in Ruhe und passt den Aufruf an
    assert window.rename_subprogram(1, "bool istSchaltjahr(int year)")
    assert document.pages[1].start_items()[0].data.text == "Start"
    assert call.data.text == "bool schalt := istSchaltjahr(jahr)"  # nur der Name vor der Klammer ist neu
    assert run(document, ["2021"]).outputs == ["1"]



# ------------------------------------------------------------------ PapDesigner-Bedienung
def test_ctrl_drag_copies_instead_of_moving(window, qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    window.new_document()
    document = window.current_document()
    scene = document.scene
    a = add(scene, T.PROCESS, 0, 0)
    b = add(scene, T.PROCESS, 0, 160)
    connect(scene, a, "bottom", b, "top")
    scene.select_items([a, b])
    view = window.current_view()
    view.centerOn(QPointF(100, 80))
    qapp.processEvents()
    start = view.mapFromScene(a.scene_rect().center())
    ctrl = Qt.KeyboardModifier.ControlModifier
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, ctrl, start)
    for step in range(1, 11):
        QTest.mouseMove(view.viewport(), start + QPoint(30 * step, 0))
        qapp.processEvents()
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, ctrl, start + QPoint(300, 0))
    qapp.processEvents()
    assert len(scene.elements()) == 4 and len(scene.connections()) == 2
    assert a.pos().x() == 0 and b.pos().x() == 0  # die Originale bleiben stehen
    assert all(item.pos().x() > 200 for item in scene.selected_elements())
    window._undo()
    assert len(scene.elements()) == 2


def test_change_element_type_keeps_text_and_connections(scene):
    start = add(scene, T.START, 0, 0)
    block = add(scene, T.PROCESS, 0, 120)
    block.set_text("Eingabe: n")
    end = add(scene, T.END, 0, 240)
    first = connect(scene, start, "bottom", block, "top")
    second = connect(scene, block, "bottom", end, "top")
    second.set_label("weiter")
    assert scene.change_element_type(block, T.INPUT)
    new = scene.element(block.element_id)
    assert new.element_type is T.INPUT and new.data.text == "Eingabe: n"
    assert {c.connection_id for c in new.connections} == {first.connection_id, second.connection_id}
    assert scene.connection(second.connection_id).data.label == "weiter"
    # Standardtext wird mit umgewandelt
    other = add(scene, T.PROCESS, 300, 0)
    scene.change_element_type(other, T.OUTPUT)
    assert scene.element(other.element_id).data.text == "Ausgabe"
    for _ in range(3):  # Umwandeln, Einfügen von „other“, Umwandeln
        scene.undo_stack.undo()
    assert scene.element(block.element_id).element_type is T.PROCESS
    assert len(scene.element(block.element_id).connections) == 2


def test_change_to_end_moves_a_missing_port(scene):
    block = add(scene, T.PROCESS, 0, 0)
    after = add(scene, T.PROCESS, 0, 160)
    link = connect(scene, block, "bottom", after, "top")
    assert scene.change_element_type(block, T.END)
    # Ende hat unten keinen Anschluss: die Verbindung bleibt (rot markiert) und geht von rechts ab
    data = scene.connection(link.connection_id).data
    assert data.source_port == "right" and scene.connection(link.connection_id).warning


def test_counterpart_label_like_papdesigner(scene):
    from app import labels
    assert labels.opposite_label("ja") == "nein" and labels.opposite_label("Wahr") == "Falsch"
    assert labels.opposite_label("true") == "false" and labels.opposite_label("sonst") is None
    decision = add(scene, T.DECISION, 0, 0)
    a = add(scene, T.PROCESS, 0, 200)
    b = add(scene, T.PROCESS, 300, 0)
    first = connect(scene, decision, "bottom", a, "top")
    second = connect(scene, decision, "right", b, "left")
    assert (first.data.label, second.data.label) == ("ja", "nein")
    scene._commit_label(first, "ja", "nein")
    assert (first.data.label, second.data.label) == ("nein", "ja")
    scene._commit_label(second, "ja", "falsch")
    assert (first.data.label, second.data.label) == ("wahr", "falsch")  # „nein“ hieße dasselbe wie „falsch“
    scene.undo_stack.undo()
    scene.undo_stack.undo()
    assert (first.data.label, second.data.label) == ("ja", "nein")


def test_call_picker_sets_the_call(window):
    document, items = main_program(window)
    window.new_subprogram("bool istGerade(int n)")
    call = items[2]
    window._set_call(call, document.pages[1])
    assert call.data.text == "istGerade"
    call.set_text("x := verdoppeln(n)")
    window._set_call(call, document.pages[1])
    assert call.data.text == "x := istGerade(n)"
    assert document.flow_start(call.data.text)[0] is document.pages[1]


def test_spaces_and_hyphens_do_not_matter_for_calls(window):
    document, items = main_program(window)
    window.new_subprogram("Summe berechnen")
    items[2].set_text("Summe-berechnen")
    assert document.flow_start(items[2].data.text)[0] is document.pages[1]
    items[2].set_text("Summeberechnen")
    assert document.flow_start(items[2].data.text)[0] is document.pages[1]


def test_papdesigner_subpage_title_is_not_a_comment(tmp_path):
    path = tmp_path / "datum.pap"
    path.write_text(PAPDESIGNER_STYLE, encoding="utf-8")
    diagram = load_diagram(str(path)).diagram
    assert not [e for e in diagram.subprograms[0].elements if e.type is T.COMMENT]
    assert diagram.subprograms[0].name == "bool isLeapYear(int year)"


# ------------------------------------------------------------------ Befunde aus dem zweiten Review (ChatGPT)
def test_exact_names_win_over_the_tolerant_match():
    from app.analysis.graph import resolve_routine
    names = ["Start", "ab_c", "a_bc"]
    assert resolve_routine("a_bc", names, exclude=0) == 2 and resolve_routine("ab_c", names, exclude=0) == 1
    assert resolve_routine("abc", names, exclude=0) == 1  # tolerant: der erste passende
    assert resolve_routine("Summe-berechnen", ["Start", "Summe berechnen"], exclude=0) == 1
    assert resolve_routine("gibt es nicht", names, exclude=0) is None


def test_python_variable_analysis_uses_the_same_target_as_the_call(monkeypatch, capsys):
    """Hauptprogramm „a_bc“ ruft „ab_c“; das Unterprogramm liest x vor dem Setzen."""
    from tests.test_review_fixes_3 import Plan
    plan = Plan()
    plan.chain(plan.node("s", T.START, "a_bc"), plan.node("u", T.SUBPROGRAM, "ab_c"), plan.node("e", T.END, "Ende"))
    plan.chain(plan.node("s2", T.START, "ab_c", x=400), plan.node("o", T.OUTPUT, "x", x=400),
               plan.node("p", T.PROCESS, "x = 1", x=400), plan.node("e2", T.END, "Ende", x=400))
    code = generate(structure_diagram(plan.graph()), "python")
    assert "ab_c()" in code
    exec(compile(code, "plan.py", "exec"), {"__name__": "__main__"})  # kein NameError
    assert capsys.readouterr().out.strip() == "0"


def test_change_type_keeps_a_self_connection(scene):
    block = add(scene, T.PROCESS, 0, 0)
    loop = scene.connection(scene.create_connection(block, "left", block, "top"))
    assert loop is not None
    assert scene.change_element_type(block, T.START)  # Start hat oben keinen Anschluss
    data = scene.connection(loop.connection_id).data
    assert data.source_port != data.target_port and data.target_port in ("left", "right", "bottom")


def test_change_type_keeps_the_line_when_ports_stay(scene):
    a = add(scene, T.PROCESS, 0, 0)
    b = add(scene, T.PROCESS, 400, 300)
    link = connect(scene, a, "right", b, "top")
    link.data.routing = {"mode": "manual", "axis": "x", "value": 300.0}
    scene.reset_routing(link)  # nur damit der Verlauf neu berechnet ist
    before = link.points()
    # gleiche Form (Rechteck), gleiche Anschlüsse: der Linienverlauf bleibt genau erhalten
    assert scene.change_element_type(a, T.SUBPROGRAM)
    assert scene.connection(link.connection_id).points() == before
