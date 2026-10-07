"""Tests für Code-Erzeugung, Struktogramm, Schreibtischtest, Layout, Hinweise,
automatisches Sichern, Farbschema und Dateien aus dem PapDesigner."""

import os

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QMessageBox

from app import icons, styles
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.document import DiagramDocument
from app.model.element_types import ElementType as T
from tests.conftest import add, connect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")
PAP_SAMPLE = os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap")


@pytest.fixture(autouse=True)
def _application(qapp):
    """Alle Tests dieser Datei benötigen eine laufende Qt-Anwendung."""
    yield


def programs_of(scene):
    return structure_diagram(FlowGraph.from_scene(scene))


def build_loop_program(scene):
    s = add(scene, T.START, 0, 0)
    i = add(scene, T.INPUT, 0, 120)
    i.set_text("n einlesen")
    p = add(scene, T.PROCESS, 0, 240)
    p.set_text("k = 0")
    d = add(scene, T.DECISION, 0, 380)
    d.set_text("k < n ?")
    b = add(scene, T.PROCESS, 0, 540)
    b.set_text("k = k + 1")
    o = add(scene, T.OUTPUT, 300, 540)
    o.set_text("k ausgeben")
    e = add(scene, T.END, 300, 700)
    connect(scene, s, "bottom", i, "top")
    connect(scene, i, "bottom", p, "top")
    connect(scene, p, "bottom", d, "top")
    connect(scene, d, "bottom", b, "top")
    connect(scene, d, "right", o, "top")
    connect(scene, b, "left", d, "left")
    connect(scene, o, "bottom", e, "top")
    return s, d


# ================================================================= Codegen
def test_codegen_example_all_languages():
    from app.codegen.generators import generate
    document = DiagramDocument.open_file(EXAMPLE)
    programs = programs_of(document.scene)
    python = generate(programs, "python", document.meta.name)
    compile(python, "generated.py", "exec")
    assert "i = 1\n    while i <= n:" in python and "i += 1" in python
    assert "print(\"Keine Werte\")" in python
    java = generate(programs, "java", document.meta.name)
    assert java.count("{") == java.count("}")
    assert "public class BeispielMittelwert" in java
    pseudo = generate(programs, "pseudo", document.meta.name)
    assert "WENN n > 0 ? DANN" in pseudo and "FÜR i = 1 bis n" in pseudo
    document.scene.clear_diagram()


def test_codegen_while_loop_and_unknown_condition(scene):
    from app.codegen.generators import generate
    build_loop_program(scene)
    python = generate(programs_of(scene), "python")
    compile(python, "generated.py", "exec")
    assert "while k < n:" in python and "k = k + 1" in python
    d = [e for e in scene.elements() if e.element_type is T.DECISION][0]
    d.set_text("Kunde zufrieden?")
    python = generate(programs_of(scene), "python")
    compile(python, "generated.py", "exec")
    assert 'while frage("Kunde zufrieden?")' in python and "def frage(text):" in python


def test_codegen_generated_python_runs(scene, monkeypatch, capsys):
    from app.codegen.generators import generate
    build_loop_program(scene)
    code = generate(programs_of(scene), "python")
    answers = iter(["3"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    namespace = {"__name__": "__main__"}
    exec(compile(code, "generated.py", "exec"), namespace)
    assert capsys.readouterr().out.strip() == "3"  # while k < n: k = k + 1 → Ausgabe von k


def test_codegen_subprogram_links_second_program(scene):
    from app.codegen.generators import generate
    s = add(scene, T.START, 0, 0)
    u = add(scene, T.SUBPROGRAM, 0, 120)
    u.set_text("Summe berechnen")
    e = add(scene, T.END, 0, 240)
    connect(scene, s, "bottom", u, "top")
    connect(scene, u, "bottom", e, "top")
    s2 = add(scene, T.START, 400, 0)
    s2.set_text("Summe berechnen")
    p = add(scene, T.PROCESS, 400, 120)
    p.set_text("summe = 1 + 2")
    e2 = add(scene, T.END, 400, 240)
    connect(scene, s2, "bottom", p, "top")
    connect(scene, p, "bottom", e2, "top")
    python = generate(programs_of(scene), "python")
    compile(python, "generated.py", "exec")
    assert "def summe_berechnen():" in python and python.count("def summe_berechnen") == 1
    assert "    summe_berechnen()" in python


def test_code_dialog_constructs(qapp, monkeypatch):
    from app.codegen.dialog import CodeDialog
    document = DiagramDocument.open_file(EXAMPLE)
    dialog = CodeDialog(document)
    assert "PROGRAMM" in dialog.code()
    dialog.language.setCurrentIndex(1)
    assert "def main" in dialog.code()
    dialog.copy_code()
    dialog.deleteLater()
    empty = DiagramDocument()
    assert CodeDialog(empty).code() == ""
    document.scene.clear_diagram()


# ============================================================ Struktogramm
def test_structogram_render_and_export(qapp, tmp_path):
    from app.nsd.dialog import StructogramDialog
    from app.nsd.renderer import NsdRenderer, export_nsd, render_image
    document = DiagramDocument.open_file(EXAMPLE)
    programs = programs_of(document.scene)
    renderer = NsdRenderer(programs[0], styles.LIGHT)
    size = renderer.size()
    assert size.width() >= 360 and size.height() > 200
    assert not render_image(programs, styles.LIGHT).isNull()
    for fmt in ("PNG", "SVG", "PDF"):
        path = tmp_path / f"nsd.{fmt.lower()}"
        export_nsd(programs, str(path), fmt)
        assert path.stat().st_size > 0
    dialog = StructogramDialog(document)
    assert dialog.canvas.pixmap() is not None and not dialog.canvas.pixmap().isNull()
    dialog.set_zoom_index(0)
    dialog.deleteLater()
    document.scene.clear_diagram()


# ======================================================== Schreibtischtest
def test_evaluator_is_safe():
    from app.simulation.evaluator import EvaluationError, evaluate
    assert evaluate("2 + 3 * 4", {}) == 14
    assert evaluate("x ≥ 3 und nicht y", {"x": 3, "y": False}, condition=True) is True
    assert evaluate("a = 5", {"a": 5}, condition=True) is True
    for bad in ("__import__('os')", "x.__class__", "(lambda: 1)()", "open('x')", "9 ** 99999"):
        with pytest.raises(EvaluationError):
            evaluate(bad, {"x": 1})


def test_simulator_runs_example():
    from app.simulation.engine import NEEDS_INPUT, Simulator
    document = DiagramDocument.open_file(EXAMPLE)
    simulator = Simulator(FlowGraph.from_scene(document.scene))
    values = iter(["3", "1", "2", "3"])
    for _ in range(200):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input(next(values))
        if simulator.finished:
            break
    assert simulator.finished
    assert simulator.outputs == ["Mittelwert: 2"]
    assert simulator.variables["summe"] == 6
    document.scene.clear_diagram()


def test_simulator_asks_for_unknown_condition_and_limits_steps(scene):
    from app.simulation.engine import MAX_STEPS, NEEDS_DECISION, Simulator
    build_loop_program(scene)
    d = [e for e in scene.elements() if e.element_type is T.DECISION][0]
    d.set_text("Kunde zufrieden?")
    simulator = Simulator(FlowGraph.from_scene(scene))
    while True:
        result = simulator.step()
        if result.needs == "input":
            simulator.provide_input("2")
        elif result.needs == NEEDS_DECISION:
            break
    simulator.provide_decision(False)
    for _ in range(10):
        simulator.step()
    assert simulator.finished
    # Endlosschleife wird begrenzt
    d.set_text("1 < 2")
    endless = Simulator(FlowGraph.from_scene(scene))
    for _ in range(MAX_STEPS + 50):
        result = endless.step()
        if result.needs == "input":
            endless.provide_input("1")
        if endless.finished:
            break
    assert endless.finished


def test_simulation_panel_highlights_and_steps(qapp):
    from app.simulation.panel import SimulationPanel
    document = DiagramDocument.open_file(EXAMPLE)
    panel = SimulationPanel()
    panel.set_document(document)
    panel.step()
    assert panel._highlight is not None and panel._highlight.scene() is document.scene
    panel.run()
    assert panel.input_row.isVisibleTo(panel) or panel.simulator.pending is not None
    panel.input_field.setText("2")
    panel.submit_input()
    panel.stop()
    assert panel._highlight is None
    panel.deleteLater()
    document.scene.clear_diagram()


# ================================================================ Layout
def rects_overlap(scene):
    items = [it for it in scene.elements() if not it.is_junction]
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if a.scene_rect().intersects(b.scene_rect()):
                return True
    return False


def test_auto_layout_example_and_undo(scene, document):
    from app.layout.auto_layout import apply_layout, plan_auto_layout
    build_loop_program(scene)
    # durcheinander würfeln
    for index, item in enumerate(scene.elements()):
        item.setPos(QPointF((index * 137) % 500, (index * 91) % 300))
    before = {it.element_id: (it.pos().x(), it.pos().y()) for it in scene.elements()}
    plan = plan_auto_layout(scene)
    assert apply_layout(scene, plan)
    assert not rects_overlap(scene)
    grid = scene.grid_size
    assert all(it.pos().x() % grid == 0 and it.pos().y() % grid == 0 for it in scene.elements())
    start = [e for e in scene.elements() if e.element_type is T.START][0]
    assert (start.pos().x(), start.pos().y()) == before[start.element_id]
    document.undo_stack.undo()
    assert {it.element_id: (it.pos().x(), it.pos().y()) for it in scene.elements()} == before


def test_auto_layout_keeps_sequence_in_one_column(scene):
    from app.layout.auto_layout import apply_layout, plan_auto_layout
    items = [add(scene, t, x, y) for t, x, y in
             ((T.START, 0, 0), (T.INPUT, 200, 300), (T.PROCESS, -300, 100), (T.END, 500, 50))]
    for a, b in zip(items, items[1:]):
        connect(scene, a, "bottom", b, "top")
    apply_layout(scene, plan_auto_layout(scene))
    assert len({it.pos().x() for it in items}) == 1
    ys = [it.pos().y() for it in items]
    assert ys == sorted(ys)
    assert not rects_overlap(scene)


# ============================================================== Hinweise
def test_diagnostics_checks(scene):
    from app.diagnostics.checks import run_checks
    assert run_checks(scene) == []
    p = add(scene, T.PROCESS, 0, 0)
    messages = " | ".join(issue.message for issue in run_checks(scene))
    assert "kein Start-Element" in messages and "kein Ende-Element" in messages
    assert "Standardtext" in messages
    s = add(scene, T.START, 0, -200)
    d = add(scene, T.DECISION, 0, 200)
    e = add(scene, T.END, 0, 400)
    connect(scene, s, "bottom", p, "top")
    connect(scene, p, "bottom", d, "top")
    connect(scene, d, "bottom", e, "top")
    lonely = add(scene, T.OUTPUT, 400, 0)
    issues = run_checks(scene)
    messages = " | ".join(issue.message for issue in issues)
    assert "weniger als zwei Ausgänge" in messages
    assert "nie erreicht" in messages and any(lonely.element_id in i.element_ids for i in issues)
    red = connect(scene, p, "right", lonely, "left")
    assert any(red.connection_id in i.connection_ids for i in run_checks(scene))


def test_diagnostics_panel_navigates(qapp, document):
    from app.diagnostics.panel import DiagnosticsPanel
    add(document.scene, T.PROCESS, 0, 0)
    panel = DiagnosticsPanel()
    panel.set_debounce(0)
    counts = []
    targets = []
    panel.issues_changed.connect(lambda w, i: counts.append((w, i)))
    panel.navigate_requested.connect(lambda e, c: targets.append((e, c)))
    panel.set_document(document)
    assert panel.list.count() >= 2 and counts[-1][0] >= 2
    item = next(panel.list.item(i) for i in range(panel.list.count())
                if panel.issues[panel.list.item(i).data(Qt.ItemDataRole.UserRole)].element_ids)
    panel._on_item_clicked(item)
    assert targets
    panel.set_document(None)
    panel.deleteLater()


# ======================================================= Automatisches Sichern
def test_autosave_backup_and_recovery(qapp, tmp_path):
    from app.autosave import AutosaveManager
    crashed = AutosaveManager(str(tmp_path), interval_ms=3600000)
    document = DiagramDocument()
    add(document.scene, T.PROCESS, 0, 0)
    crashed.register(document)
    assert crashed.save_now() == 1
    assert crashed.save_now() == 0  # unverändert
    backups = [n for n in os.listdir(tmp_path) if n.endswith(".pap")]
    assert len(backups) == 1
    # zweite Sitzung: erste gilt als abgestürzt
    survivor = AutosaveManager(str(tmp_path), interval_ms=3600000,
                               pid_alive_func=lambda pid: False)
    orphans = survivor.find_orphans()
    assert len(orphans) == 1
    restored = survivor.restore(orphans[0])
    assert restored.is_modified and len(restored.scene.elements()) == 1
    assert survivor.find_orphans() == []
    survivor.shutdown()
    crashed._timer.stop()
    document.scene.clear_diagram()
    restored.scene.clear_diagram()


def test_autosave_saved_and_shutdown_remove_files(qapp, tmp_path):
    from app.autosave import AutosaveManager
    manager = AutosaveManager(str(tmp_path), interval_ms=3600000)
    document = DiagramDocument()
    add(document.scene, T.PROCESS, 0, 0)
    manager.register(document)
    manager.save_now()
    document.save(str(tmp_path / "projekt.pap"))
    manager.document_saved(document)
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".json")]
    (tmp_path / "kaputt_abc.pap").write_text("{kein json", encoding="utf-8")
    other = AutosaveManager(str(tmp_path), interval_ms=3600000, pid_alive_func=lambda pid: False)
    for entry in other.find_orphans():  # beschädigte Sicherung: keine Ausnahme
        with pytest.raises(Exception):
            other.restore(entry)
    manager.shutdown()
    other.shutdown()
    assert not os.path.exists(manager._session_path())
    document.scene.clear_diagram()


def test_pid_alive_for_current_process():
    from app.autosave import pid_alive
    assert pid_alive(os.getpid())
    assert not pid_alive(0)


def test_recovery_dialog(qapp, tmp_path):
    from app.autosave import RecoveryEntry
    from app.dialogs.recovery import RecoveryDialog
    entries = [RecoveryEntry("a", "a.json", "Projekt A", None, "2026-01-01T10:00:00", "s1"),
               RecoveryEntry("b", "b.json", "Projekt B", "C:/x.pap", "", "s1")]
    dialog = RecoveryDialog(entries)
    dialog.list.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected_entries() == entries[:1]
    dialog.deleteLater()


# ============================================================== Farbschema
def test_light_theme_switch_and_back(qapp):
    from app import theme
    from app.main_window import MainWindow
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    window.new_document()
    dark_pixel = icons.icon("new").pixmap(24, 24).toImage()
    try:
        window.set_theme("light")
        assert styles.current_theme() is styles.LIGHT_UI
        assert window.current_document().scene.theme is styles.LIGHT_UI
        assert window.actions["theme_light"].isChecked()
        light_pixel = icons.icon("new").pixmap(24, 24).toImage()
        assert dark_pixel != light_pixel
        image = window.current_view().grab().toImage()
        background = QColor(image.pixel(5, 5))
        assert background.lightness() > 200
    finally:
        window.set_theme("dark")
        theme.save_theme_name("dark")
    assert styles.current_theme() is styles.DARK
    window.current_document().undo_stack.setClean()
    window.close()


# ================================================== Dateien aus dem PapDesigner
def test_papdesigner_file():
    from app.fileformat.serializer import load_diagram
    result = load_diagram(PAP_SAMPLE)
    diagram = result.diagram
    assert diagram.meta.name == "Mittelwert" and diagram.meta.author == "Testautor"
    types = [e.type for e in diagram.elements]
    assert types.count(T.START) == 2 and T.JUNCTION in types and T.SUBPROGRAM in types
    loops = [e for e in diagram.elements if e.type is T.LOOP]
    assert {e.properties["part"] for e in loops} == {"begin", "end"}
    labels = {c.label for c in diagram.connections}
    assert {"ja", "nein"} <= labels
    document = DiagramDocument(diagram)
    assert document.load_warnings == []
    programs = programs_of(document.scene)
    assert len(programs) == 2
    # Hauptprogramm zuerst, obwohl das Unterprogramm weiter oben liegt
    assert programs[0].name == "Start" and programs[1].name == "Fehlermeldung"
    from app.codegen.generators import generate
    python = generate(programs, "python")
    compile(python, "x.py", "exec")
    assert "def fehlermeldung():" in python and "        fehlermeldung()" in python
    # Anordnen: der Zusammenführungspunkt landet direkt über dem Ende
    from app.layout.auto_layout import apply_layout, plan_auto_layout
    apply_layout(document.scene, plan_auto_layout(document.scene))
    junction = [e for e in document.scene.elements() if e.element_type is T.JUNCTION][0]
    successor = [c.target for c in junction.connections if c.source is junction][0]
    assert junction.pos().x() == successor.pos().x()
    assert 0 < successor.pos().y() - junction.pos().y() <= 80
    document.scene.clear_diagram()


@pytest.mark.parametrize("content", [b"", b"<kaputt", b"<FRAME></FRAME>",
                                     b'<!DOCTYPE x [<!ENTITY a "b">]><FRAME/>', b'{"format": 1}'])
def test_bad_pap_files_are_rejected(tmp_path, content):
    from app.fileformat.project import ProjectFileError
    from app.fileformat.serializer import load_diagram
    path = tmp_path / "bad.pap"
    path.write_bytes(content)
    with pytest.raises(ProjectFileError):
        load_diagram(str(path))


# ================================================================= Fenster
def test_main_window_feature_actions(qapp, monkeypatch, tmp_path):
    import shutil
    from app.main_window import MainWindow
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    assert window.open_file(shutil.copy(PAP_SAMPLE, tmp_path / "mittelwert.pap"))
    for name in ("generate_code", "structogram", "auto_layout"):
        assert window.actions[name].isEnabled()
    window.show_code_dialog()
    window.show_structogram()
    window.auto_layout()
    assert not rects_overlap(window.current_document().scene)
    window.simulation_dock.show()
    window.simulation_panel.step()
    assert window.simulation_panel.simulator is not None
    window.diagnostics_panel.refresh()
    for view in window.views():
        view.document.undo_stack.setClean()
    window.close()
