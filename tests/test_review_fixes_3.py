"""Regressionstests zu den Befunden der Prüfung von Code-Erzeugung,
Schreibtischtest und Bedienoberfläche."""

import os

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from app.analysis import text as TX
from app.analysis.graph import Edge, FlowGraph, Node
from app.analysis.structure import structure_diagram
from app.codegen.generators import _java_expr, generate
from app.document import DiagramDocument
from app.model.element_types import LOOP_BEGIN, LOOP_END, LOOP_PART_KEY
from app.model.element_types import ElementType as T
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from app.simulation.evaluator import EvaluationError, evaluate, format_value
from tests.conftest import add

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


# ------------------------------------------------------------------ Hilfen
class Plan:
    """Kleiner Baukasten für Ablaufgraphen ohne Szene."""

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._y = 0

    def node(self, nid, etype, text="", part=None, x=0):
        props = {LOOP_PART_KEY: part} if part else {}
        self._y += 100
        self.nodes[nid] = Node(nid, etype, text, props, x, self._y)
        return nid

    def edge(self, source, target, label=""):
        self.edges.append(Edge(f"e{len(self.edges):03d}", source, target, label))

    def chain(self, *ids):
        for a, b in zip(ids, ids[1:]):
            self.edge(a, b)

    def graph(self) -> FlowGraph:
        return FlowGraph(self.nodes, self.edges)


def linear(*steps, name="Start") -> FlowGraph:
    """Start → Schritte → Ende. Schritte: (Typ, Text) oder („begin“/„end“, Text) für Schleifen."""
    plan = Plan()
    ids = [plan.node("s", T.START, name)]
    for index, (kind, text) in enumerate(steps):
        nid = f"n{index}"
        if kind in (LOOP_BEGIN, LOOP_END):
            plan.node(nid, T.LOOP, text, part=kind)
        else:
            plan.node(nid, kind, text)
        ids.append(nid)
    ids.append(plan.node("e", T.END, "Ende"))
    plan.chain(*ids)
    return plan.graph()


def simulate(graph: FlowGraph, inputs=(), decisions=()):
    simulator = Simulator(graph)
    inputs, decisions = iter(inputs), iter(decisions)
    for _ in range(20000):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input(next(inputs))
        elif result.needs == NEEDS_DECISION:
            simulator.provide_decision(next(decisions))
        if simulator.finished:
            break
    assert simulator.finished
    return simulator


def run_python(graph: FlowGraph, monkeypatch, capsys, inputs=()) -> list[str]:
    code = generate(structure_diagram(graph), "python")
    answers = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    exec(compile(code, "generated.py", "exec"), {"__name__": "__main__"})
    return capsys.readouterr().out.split("\n")[:-1]


# ============================================================ Unterprogramme
def subprogram_plan() -> FlowGraph:
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("i", T.INPUT, "n einlesen"),
               plan.node("u", T.SUBPROGRAM, "Verdoppeln"), plan.node("o", T.OUTPUT, "n ausgeben"),
               plan.node("e", T.END, "Ende"))
    plan.chain(plan.node("s2", T.START, "Verdoppeln", x=400), plan.node("p", T.PROCESS, "n = n * 2", x=400),
               plan.node("g", T.OUTPUT, '"verdoppelt"', x=400), plan.node("e2", T.END, "Zurück", x=400))
    return plan.graph()


def test_simulator_runs_subprogram_and_returns():
    simulator = simulate(subprogram_plan(), inputs=["5"])
    assert simulator.outputs == ["verdoppelt", "10"]


def test_python_subprogram_shares_variables(monkeypatch, capsys):
    assert run_python(subprogram_plan(), monkeypatch, capsys, ["5"]) == ["verdoppelt", "10"]


def test_java_uses_static_fields_for_shared_variables():
    java = generate(structure_diagram(subprogram_plan()), "java")
    assert "    static double n = 0;" in java
    assert "        double n" not in java  # keine lokale Kopie je Methode
    assert "verdoppeln();" in java and java.count("{") == java.count("}")


# ================================================================ Eingaben
@pytest.mark.parametrize("text, expected", [
    ("Gib x ein", ["x"]),
    ("Gib den Radius r ein", ["r"]),
    ("Zahl1 und Zahl2 einlesen", ["Zahl1", "Zahl2"]),
    ("Eingabe: Länge und Breite", ["Länge", "Breite"]),
    ("Name, Alter eingeben", ["Name", "Alter"]),
    ("Anzahl n einlesen", ["n"]),
    ("Zahl a und Zahl b eingeben", ["a", "b"]),
    ("Bitte Temperatur in Celsius eingeben", ["Celsius"]),
])
def test_input_variables(text, expected):
    assert TX.input_variables(text) == expected


def test_two_inputs_then_sum(monkeypatch, capsys):
    graph = linear((T.INPUT, "Zahl1 und Zahl2 einlesen"), (T.PROCESS, "summe = Zahl1 + Zahl2"),
                   (T.OUTPUT, "summe ausgeben"))
    assert simulate(graph, inputs=["2 3"]).outputs == ["5"]
    assert run_python(graph, monkeypatch, capsys, ["2", "3"]) == ["5"]


# ============================================================= Zählschleifen
@pytest.mark.parametrize("steps, inputs, variable, expected", [
    ([(T.PROCESS, "s = 0"), (LOOP_BEGIN, "Für x = 0 bis 1 Schritt 0,25"), (T.PROCESS, "s = s + x"),
      (LOOP_END, "")], [], "s", 2.5),
    ([(T.INPUT, "Schritt st einlesen"), (T.PROCESS, "s = 0"), (LOOP_BEGIN, "Für i = 5 bis 1 Schritt st"),
      (T.PROCESS, "s = s + i"), (LOOP_END, "")], ["-1"], "s", 15),
    ([(LOOP_BEGIN, "Für i = 1 bis 3"), (T.PROCESS, "k = i"), (LOOP_END, "")], [], "i", 4),
    ([(T.PROCESS, "n = 6 / 2"), (T.PROCESS, "k = 0"), (LOOP_BEGIN, "wiederhole n mal"),
      (T.PROCESS, "k = k + 1"), (LOOP_END, "")], [], "k", 3),
    ([(T.PROCESS, "s = 0"), (LOOP_BEGIN, "Für i = 10 bis 1 Schritt -3"), (T.PROCESS, "s = s + i"),
      (LOOP_END, "")], [], "s", 22),
])
def test_counting_loops_match_simulator(steps, inputs, variable, expected, monkeypatch, capsys):
    graph = linear(*steps, (T.OUTPUT, f"{variable} ausgeben"))
    simulator = simulate(graph, inputs=inputs)
    assert simulator.variables[variable] == expected
    printed = run_python(graph, monkeypatch, capsys, inputs)
    assert float(printed[-1].split(":")[-1]) == expected
    java = generate(structure_diagram(graph), "java")
    assert java.count("{") == java.count("}")


def test_java_counting_loop_with_variable_step():
    graph = linear((T.INPUT, "st einlesen"), (LOOP_BEGIN, "Für i = 5 bis 1 Schritt st"),
                   (T.PROCESS, "k = i"), (LOOP_END, ""))
    java = generate(structure_diagram(graph), "java")
    assert "for (i = 5; (st) >= 0 ? i <= 1 : i >= 1; i += st) {" in java


# ======================================================= Mehrfachverzweigung
def multi_branch(decision_text, labels, texts, input_text="wahl einlesen"):
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("i", T.INPUT, input_text),
               plan.node("d", T.DECISION, decision_text))
    plan.node("e", T.END, "Ende")
    for index, (label, text) in enumerate(zip(labels, texts)):
        nid = plan.node(f"o{index}", T.OUTPUT, f'"{text}"', x=index * 200)
        plan.edge("d", nid, label)
        plan.edge(nid, "e")
    return plan.graph()


@pytest.mark.parametrize("decision, labels, cases", [
    ("wahl", ["1", "2", "3"], [("1", "eins"), ("2", "zwei"), ("3", "drei")]),
    ("wahl ?", ["< 0", "= 0", "> 0"], [("-3", "eins"), ("0", "zwei"), ("3", "drei")]),
    ("wahl", ["1", "2", "sonst"], [("1", "eins"), ("2", "zwei"), ("7", "drei")]),
])
def test_multi_branch_simulator_and_python(decision, labels, cases, monkeypatch, capsys):
    graph = multi_branch(decision, labels, ["eins", "zwei", "drei"])
    code = generate(structure_diagram(graph), "python")
    assert "frage(" not in code
    for value, expected in cases:
        assert simulate(graph, inputs=[value]).outputs == [expected]
        assert run_python(graph, monkeypatch, capsys, [value]) == [expected]


def test_multi_branch_unknown_condition_asks_for_exit():
    graph = multi_branch("Farbe wählen", ["rot", "grün", "blau"], ["R", "G", "B"], input_text="nichts")
    simulator = Simulator(graph)
    while True:
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input("x")
        elif result.needs == NEEDS_DECISION:
            break
    assert result.options == ["rot", "grün", "blau"]
    simulator.provide_decision(2)
    while not simulator.finished:
        simulator.step()
    assert simulator.outputs == ["B"]


def test_branch_condition():
    assert TX.branch_condition("wahl ?", "2") == "wahl = 2"
    assert TX.branch_condition("x", "< 0") == "x < 0"
    assert TX.branch_condition("x", "") is None


# ======================================================================= Java
@pytest.mark.parametrize("expr, expected", [
    ("0 < x < 10", "(0 < x) && (x < 10)"),
    ("not x > 5", "!(x > 5)"),
    ("round(x / 3)", "runden(x / 3)"),                 # kaufmännisch, eigene Hilfsmethode
    ("int(x / 2)", "(double) (long) (x / 2)"),         # abschneiden, aber Kommazahl bleiben
    ("1 / 2", "1 / 2.0"),                              # keine Ganzzahldivision
    ("(1 + 2) / 2", "(1 + 2.0) / 2"),
    ("365 * 24 * 3600 * 1000", "365 * 24.0 * 3600 * 1000"),  # kein int-Überlauf
    ("3000000000", "3000000000.0"),
    ("x ** 2", "Math.pow(x, 2)"),
    ("x % 2", "mod(x, 2)"),                            # Vorzeichen des Teilers wie im Schreibtischtest
    ("max(a, b, c)", "Math.max(Math.max(a, b), c)"),
    ('name == "Max"', '"Max".equals(name)'),
    ("a + b * c", "a + b * c"),
    ("a - (b - c)", "a - (b - c)"),
    ("(a + b) * c", "(a + b) * c"),
    ("-(-x)", "-(-x)"),
    ("True", "true"),
    ("new + 1", "new_ + 1"),                           # Java-Schlüsselwort als Variablenname
])
def test_java_expressions(expr, expected):
    assert _java_expr(expr) == expected


def test_java_expressions_use_variable_types():
    types = {"a": "boolean", "b": "boolean", "c": "boolean", "s": "String", "t": "String", "x": "double"}
    assert _java_expr("a and (b or c)", types) == "a && (b || c)"
    assert _java_expr("not a", types) == "!a"
    assert _java_expr("x and a", types) == "x != 0 && a"       # Zahl als Bedingung: ungleich 0
    assert _java_expr("not x", types) == "x == 0"
    assert _java_expr("s == t", types) == "s.equals(t)"
    assert _java_expr("s != t", types) == "!s.equals(t)"
    assert _java_expr('s + "!"', types) == 's + "!"'
    assert _java_expr('"-" * x', types) == '"-".repeat(Math.max(0, (int) (x)))'
    assert _java_expr("len(s)", types) == "(double) s.length()"
    assert _java_expr("str(x)", types) == "text(x)"                   # 5 statt 5.0
    assert _java_expr("s < t", types) == "s.compareTo(t) < 0"
    assert _java_expr("x + s", types) == "text(x) + s"
    assert _java_expr("x + a", types) == "x + (a ? 1 : 0)"             # wahr zählt wie 1
    assert _java_expr("int(s) + 1", types) == "(double) (long) zahl(s) + 1"
    # Eingabe, die Zahl oder Text sein kann (z. B. mit "ende" verglichen und aufsummiert)
    assert _java_expr("x + s", types, dynamic={"s"}) == "x + zahl(s)"
    assert _java_expr("s == 1", types, dynamic={"s"}) == "zahl(s) == 1"
    assert _java_expr('s == "ende"', types, dynamic={"s"}) == '"ende".equals(s)'
    assert _java_expr("pi * x", types, known={"x"}) == "Math.PI * x"
    assert _java_expr("pi * x", types, known={"x", "pi"}) == "pi * x"   # eigene Variable pi
    assert _java_expr("y + 1", types, known={"x"}) is None            # y erhält nie einen Wert


@pytest.mark.parametrize("expr", ["len(x)", "x in y", "[1, 2]", "f(x=1)", "a.b", "x | 1", "x ^ 2", "foo(1)",
                                  "round(1, 2, 3)", "wurzel(1, 2)"])
def test_java_expression_unsupported(expr):
    assert _java_expr(expr) is None


def test_java_nested_times_loops_have_unique_counters():
    graph = linear((LOOP_BEGIN, "wiederhole 2 mal"), (LOOP_BEGIN, "wiederhole 3 mal"), (T.PROCESS, "k = k + 1"),
                   (LOOP_END, ""), (LOOP_END, ""))
    java = generate(structure_diagram(graph), "java")
    assert "int durchlauf = 0" in java and "int durchlauf2 = 0" in java
    assert java.count("{") == java.count("}")


def test_java_condition_translation_in_code():
    graph = linear((T.INPUT, "x einlesen"), (T.PROCESS, "k = x"))
    plan_code = generate(structure_diagram(graph), "java")
    assert "x = eingabe" in plan_code
    assert TX.condition_expression("NICHT x > 5") == "not x > 5"
    assert _java_expr(TX.condition_expression("NICHT x > 5")) == "!(x > 5)"


# ================================================================= Ausgaben
@pytest.mark.parametrize("text, expected", [
    ('"Die Summe ist" summe', "Die Summe ist 6"),
    ('Ausgabe "Summe:", summe', "Summe: 6"),
    ('"Summe:" summe ausgeben', "Summe: 6"),
    ('"Doppelt:" summe * 2', "Doppelt: 12"),
    ('"Hallo"', "Hallo"),
])
def test_output_string_with_values(text, expected, monkeypatch, capsys):
    graph = linear((T.PROCESS, "summe = 6"), (T.OUTPUT, text))
    assert simulate(graph).outputs == [expected]
    assert run_python(graph, monkeypatch, capsys) == [expected]
    java = generate(structure_diagram(graph), "java")
    if expected != "Hallo":
        assert 'System.out.println("' in java and ' + " " + ' in java
    if "*" in text:
        assert '" + " " + text(summe * 2));' in java


# ============================================================ Große Zahlen
def test_big_numbers_are_limited():
    with pytest.raises(EvaluationError):
        evaluate("10 ** 5000", {})
    with pytest.raises(EvaluationError):
        evaluate("x * x", {"x": 2 ** 6000})
    assert format_value(10 ** 5000) == "(sehr große Zahl)"
    graph = linear((T.PROCESS, "x = 2"), (LOOP_BEGIN, "solange x > 0"), (T.PROCESS, "x = x * x"), (LOOP_END, ""))
    simulator = Simulator(graph)
    for _ in range(200):
        simulator.step()  # darf keine Ausnahme werfen
    assert simulator.variables["x"].bit_length() <= 10_000


# ======================================================== Ausdrücke/Texte
def test_normalize_keeps_string_literals():
    assert TX.parse_assignments('meldung = "Zahl ist nicht gültig und zu groß"') == \
        [("meldung", '"Zahl ist nicht gültig und zu groß"')]
    assert TX.parse_assignments("m = max(3,4)") == [("m", "max(3,4)")]
    assert TX.normalize_expression("2,5 * (1,5 + x)") == "2.5 * (1.5 + x)"
    assert TX.condition_expression("x = 5 und y <> 3?") == "x == 5 and y != 3"
    assert TX.condition_expression('name = "a=b"') == 'name == "a=b"'
    assert evaluate("m", {"m": 1}) == 1
    assert evaluate("max(3,4)", {}) == 4


# =============================================================== Oberfläche
@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
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


def test_simulation_survives_switching_to_hints_tab(window, qapp):
    window.open_file(EXAMPLE)
    window.simulation_dock.show()
    window.simulation_dock.raise_()
    qapp.processEvents()
    window.simulation_panel.run()
    assert window.simulation_panel.simulator is not None
    window._toggle_diagnostics()  # Hinweise nach vorne
    qapp.processEvents()
    assert window.simulation_panel.simulator is not None
    assert not window.diagnostics_dock.isHidden() and window._diagnostics_on_top
    window._toggle_diagnostics()  # liegt vorne → ausblenden
    qapp.processEvents()
    assert window.diagnostics_dock.isHidden()
    window.simulation_dock.close()
    qapp.processEvents()
    assert window.simulation_panel.simulator is None


def test_hints_button_raises_dock_behind_simulation_tab(window, qapp):
    window.new_document()
    window._toggle_diagnostics()
    window.simulation_dock.show()
    window.simulation_dock.raise_()
    qapp.processEvents()
    assert not window._diagnostics_on_top
    window.issues_button.click()
    qapp.processEvents()
    assert not window.diagnostics_dock.isHidden() and window._diagnostics_on_top


def test_stale_simulation_ignores_input_and_removes_highlight(qapp):
    from app.simulation.panel import SimulationPanel
    document = DiagramDocument.open_file(EXAMPLE)
    panel = SimulationPanel()
    panel.set_document(document)
    panel.run()
    assert panel.simulator.pending is not None and panel._highlight is not None
    trace_before = len(panel.simulator.trace)
    add(document.scene, T.PROCESS, 900, 900)  # Plan ändern (Befehl auf dem Undo-Stapel)
    assert panel._stale and panel._highlight is None
    assert not panel.input_row.isVisibleTo(panel)
    panel.input_field.setText("3")
    panel.submit_input()
    assert len(panel.simulator.trace) == trace_before
    assert "neu starten" in panel.status.text()
    panel.stop()
    panel.deleteLater()
    document.scene.clear_diagram()


def test_simulation_toolbar_keeps_buttons_together(qapp):
    from app.simulation.panel import SimulationPanel
    document = DiagramDocument.open_file(EXAMPLE)
    panel = SimulationPanel()
    panel.set_document(document)
    assert not panel.program_combo.isVisibleTo(panel)
    assert panel._toolbar_stretch.isVisibleTo(panel)
    panel.deleteLater()
    document.scene.clear_diagram()


def test_simulation_panel_multi_exit_buttons(qapp):
    from app.simulation.panel import SimulationPanel
    panel = SimulationPanel()
    panel._set_decision_options(["rot", "grün", "blau"])
    assert [b.text() for b in panel._decision_buttons] == ["rot", "grün", "blau"]
    panel._set_decision_options([])
    assert [b.text() for b in panel._decision_buttons] == ["ja", "nein"]
    panel.deleteLater()


def _make_orphan(directory):
    from app.autosave import AutosaveManager
    crashed = AutosaveManager(directory, interval_ms=3600000)
    document = DiagramDocument()
    add(document.scene, T.PROCESS, 0, 0)
    crashed.register(document)
    crashed.save_now()
    crashed._timer.stop()
    os.remove(crashed._session_path())  # Sitzung „abgestürzt“
    return crashed, document


def test_recovery_escape_keeps_backups(window, monkeypatch):
    from app.dialogs.recovery import RecoveryDialog
    crashed, document = _make_orphan(window.autosave.directory)
    monkeypatch.setattr(RecoveryDialog, "exec", lambda self: RecoveryDialog.DialogCode.Rejected)
    assert window.offer_recovery() == 0
    assert len(window.autosave.find_orphans()) == 1  # Esc/X: nichts gelöscht
    monkeypatch.setattr(RecoveryDialog, "exec", lambda self: RecoveryDialog.DISCARD_ALL)
    assert window.offer_recovery() == 0
    assert window.autosave.find_orphans() == []
    document.scene.clear_diagram()


def test_recovery_restore_selected(window, monkeypatch):
    from app.dialogs.recovery import RecoveryDialog
    crashed, document = _make_orphan(window.autosave.directory)
    monkeypatch.setattr(RecoveryDialog, "exec", lambda self: RecoveryDialog.DialogCode.Accepted)
    assert window.offer_recovery() == 1
    assert window.current_document().is_modified
    document.scene.clear_diagram()


def test_export_menu_icon_follows_theme(window):
    from app import theme
    before = window.export_menu.icon().pixmap(16, 16).toImage()
    try:
        window.set_theme("light")
        after = window.export_menu.icon().pixmap(16, 16).toImage()
        assert before != after
    finally:
        window.set_theme("dark")
        theme.save_theme_name("dark")


def test_pap_files_can_be_dropped(window):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap"))])
    event = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    event.setAccepted(False)
    window.dragEnterEvent(event)
    assert event.isAccepted()
    assert window._openable("C:/x/PLAN.PAP") and not window._openable("C:/x/plan.txt")


def test_structogram_ctrl_wheel_over_diagram_zooms(qapp):
    from app.nsd.dialog import StructogramDialog
    document = DiagramDocument.open_file(EXAMPLE)
    dialog = StructogramDialog(document)
    before = dialog._zoom_index
    viewport = dialog.scroll.viewport()
    event = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(0, 0), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(viewport, event)
    assert dialog._zoom_index == before + 1
    dialog.deleteLater()
    document.scene.clear_diagram()


def test_structogram_image_has_no_color_fringes():
    from app import styles
    from app.nsd.renderer import render_image
    document = DiagramDocument.open_file(EXAMPLE)
    image = render_image(structure_diagram(FlowGraph.from_scene(document.scene)), styles.LIGHT, 1.0)
    fringes = 0
    for y in range(0, image.height(), 2):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            channels = (color.red(), color.green(), color.blue())
            if max(channels) - min(channels) > 70:
                fringes += 1
    assert fringes == 0
    document.scene.clear_diagram()
