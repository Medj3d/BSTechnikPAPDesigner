"""Unterprogramme mit Werten: „y := doppelt(x)“ und „int doppelt(int n)“ mit „return n * 2“ (Codex QA-07).

Die Werte in Klammern gehen nach Position an die Parameter (gemeinsame Variablen), „return …“ bzw. „Rückgabe …“
liefert das Ergebnis für die Variable vor „:=“ – gleich im Schreibtischtest, in Python, Java und im PIC-Assembler.
"""

from app.analysis import text as T
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.model.element_types import ElementType as E
from tests.test_review_fixes_3 import Plan, simulate
from tests.test_three_way import three_way


def _plan(call: str, header: str, *sub_steps, init: str = "x = 10; y = 0; n = 2", outputs=("y ausgeben",),
          sub_end: str = "Ende") -> Plan:
    plan = Plan()
    main = [plan.node("s", E.START, "Start"), plan.node("init", E.PROCESS, init),
            plan.node("call", E.SUBPROGRAM, call)]
    main += [plan.node(f"out{i}", E.OUTPUT, text) for i, text in enumerate(outputs)]
    plan.chain(*main, plan.node("end", E.END, "Ende"))
    sub = [plan.node("sub", E.START, header)]
    sub += [plan.node(f"sub{i}", E.PROCESS, text) for i, text in enumerate(sub_steps)]
    plan.chain(*sub, plan.node("subend", E.END, sub_end))
    return plan


def test_text_helpers():
    assert T.call_spec("y := doppelt(x)") == ("y", ["x"])
    assert T.call_spec("int y = doppelt(x, 2 * z)") == ("y", ["x", "2 * z"])
    assert T.call_spec("doppelt (a, b)") == (None, ["a", "b"])
    assert T.call_spec("doppelt") is None
    assert T.routine_parameters("int doppelt(int n)") == ["n"]
    assert T.routine_parameters("double f(double a, String b, boolean c)") == ["a", "b", "c"]
    assert T.routine_parameters("Teil (2)") == []
    assert T.routine_parameters("doppelt") == []
    assert T.return_statement("return n * 2") == "n * 2"
    assert T.return_statement("Rückgabe: n * 2") == "n * 2"
    assert T.return_statement("Return") == ""
    assert T.return_statement("rückgabe = 5") is None   # Zuweisung an eine Variable
    assert T.return_statement("x = 1") is None


def test_return_value_three_ways(tmp_path):
    plan = _plan("y := doppelt(x)", "int doppelt(int n)", "return n * 2")
    assert three_way(plan.graph(), tmp_path, expected=["20"]) == ["20"]


def test_german_return_and_parameter_types(tmp_path):
    plan = _plan("int y = summe(x, 5)", "double summe(double a, int b)", "Rückgabe a + b",
                 init="x = 10; y = 0")
    assert three_way(plan.graph(), tmp_path, expected=["15"]) == ["15"]


def test_return_in_end_element(tmp_path):
    plan = _plan("y := doppelt(x)", "int doppelt(int n)", "n = n + 1", sub_end="return n * 2")
    assert three_way(plan.graph(), tmp_path, expected=["22"]) == ["22"]


def test_arguments_are_evaluated_before_they_are_assigned(tmp_path):
    plan = _plan("d := differenz(b, a)", "int differenz(int a, int b)", "return a - b",
                 init="a = 1; b = 5; d = 0", outputs=("d ausgeben", "a ausgeben", "b ausgeben"))
    assert three_way(plan.graph(), tmp_path, expected=["4", "5", "1"]) == ["4", "5", "1"]


def test_early_return_from_a_branch(tmp_path):
    plan = Plan()
    plan.chain(plan.node("s", E.START, "Start"), plan.node("init", E.PROCESS, "x = 3; y = 0"),
               plan.node("call", E.SUBPROGRAM, "y := betrag(x - 7)"), plan.node("out", E.OUTPUT, "y ausgeben"),
               plan.node("end", E.END, "Ende"))
    plan.chain(plan.node("sub", E.START, "int betrag(int v)"), plan.node("d", E.DECISION, "v < 0"))
    plan.edge("d", plan.node("neg", E.PROCESS, "return -v"), "ja")
    plan.edge("d", plan.node("pos", E.PROCESS, "return v"), "nein")
    plan.edge("neg", plan.node("e1", E.END, "Ende"))
    plan.edge("pos", plan.node("e2", E.END, "Ende"))
    assert three_way(plan.graph(), tmp_path, expected=["4"]) == ["4"]


def test_calls_without_brackets_still_share_variables(tmp_path):
    plan = _plan("Verdoppeln", "Verdoppeln", "y = x * 2", init="x = 4; y = 0")
    assert three_way(plan.graph(), tmp_path, expected=["8"]) == ["8"]


def test_values_without_parameters_are_reported_not_passed():
    plan = _plan("y := verdoppeln(x)", "verdoppeln", "y = x * 2", init="x = 4; y = 0")
    simulator_outputs = simulate(plan.graph()).outputs
    assert simulator_outputs == ["8"]
    code = generate(structure_diagram(plan.graph()), "python")
    assert "keine Parameter" in code and "keinen Wert zurück" in code
    assert "Werte in Klammern und das Ergebnis werden nicht übergeben" not in code


def test_old_hint_is_gone_when_values_are_passed():
    plan = _plan("y := doppelt(x)", "int doppelt(int n)", "return n * 2")
    for language in ("python", "java", "asm"):
        code = generate(structure_diagram(plan.graph()), language)
        assert "nicht übergeben" not in code, language
    java = generate(structure_diagram(plan.graph()), "java")
    assert "static double doppelt()" in java and "return n * 2;" in java and "y = doppelt();" in java


def test_pic_passes_parameters_and_result_in_w():
    plan = _plan("y := doppelt(x)", "int doppelt(int n)", "return n + 2")
    code = generate(structure_diagram(plan.graph()), "asm")
    lines = [line.strip() for line in code.splitlines()]
    call = lines.index("CALL\tdoppelt")
    assert lines[call - 2:call] == ["MOVF\tx, W", "MOVWF\tn"]
    assert lines[call + 1] == "MOVWF\ty"
    assert any(line.startswith("RETURN") and "W" in line for line in lines)
