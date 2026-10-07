"""Erzeugten Java-Code wirklich übersetzen und ausführen.

Die Tests laufen nur, wenn ein JDK (``javac``) gefunden wird – sonst werden
sie übersprungen. Verglichen wird die Ausgabe des Java-Programms mit der des
Schreibtischtests.
"""

import glob
import os
import re
import shutil
import subprocess

import pytest

from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.document import DiagramDocument
from app.model.element_types import LOOP_BEGIN, LOOP_END
from app.model.element_types import ElementType as T
from tests.test_review_fixes_3 import ROOT, Plan, linear, multi_branch, simulate, subprogram_plan

EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")
PAP_SAMPLE = os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap")


def find_javac() -> str | None:
    """javac im PATH, unter JAVA_HOME oder in den üblichen Installationsordnern."""
    found = shutil.which("javac")
    if found:
        return found
    candidates = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(os.path.join(os.environ["JAVA_HOME"], "bin", "javac.exe"))
    for pattern in (r"C:\Program Files\Eclipse Adoptium\jdk-*\bin\javac.exe",
                    r"C:\Program Files\Java\jdk*\bin\javac.exe",
                    r"C:\Program Files\Microsoft\jdk-*\bin\javac.exe",
                    r"C:\Program Files\Zulu\zulu*\bin\javac.exe",
                    r"C:\Program Files\Amazon Corretto\jdk*\bin\javac.exe",
                    r"C:\Program Files\BellSoft\LibericaJDK-*\bin\javac.exe"):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    return next((c for c in candidates if os.path.isfile(c)), None)


JAVAC = find_javac()
pytestmark = pytest.mark.skipif(JAVAC is None, reason="kein JDK (javac) gefunden")


def java_run(code: str, tmp_path, stdin: str = "") -> str:
    """Übersetzt den Code (Klassenname aus „public class …“) und führt ihn aus."""
    class_name = re.search(r"public class (\w+)", code).group(1)
    source = tmp_path / f"{class_name}.java"
    source.write_text(code, encoding="utf-8")
    compiled = subprocess.run([JAVAC, "-encoding", "UTF-8", "-Xlint:none", str(source)], cwd=tmp_path,
                              capture_output=True, text=True, timeout=120)
    assert compiled.returncode == 0, f"javac:\n{compiled.stderr}\n--- Code ---\n{code}"
    java = os.path.join(os.path.dirname(JAVAC), "java")
    ran = subprocess.run([java, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-cp", str(tmp_path),
                          class_name], input=stdin, capture_output=True, text=True, encoding="utf-8",
                         timeout=60)
    assert ran.returncode == 0, f"java:\n{ran.stderr}\n--- Code ---\n{code}"
    return ran.stdout


def normalize(lines: list[str]) -> list[str]:
    """Zahlen vergleichbar machen: „6.0“/„6“, „2,5“/„2.5“."""
    def number(match):
        value = float(match.group(0).replace(",", "."))
        return str(int(value)) if value.is_integer() else repr(value)
    return [re.sub(r"-?\d+(?:[.,]\d+)?", number, line.strip()) for line in lines if line.strip()]


def input_names(graph: FlowGraph) -> list[str]:
    from app.analysis.text import input_variables
    return [name for node in graph.nodes.values() if node.type is T.INPUT for name in input_variables(node.text)]


def java_outputs(stdout: str, prompts=()) -> list[str]:
    """Ausgabezeilen ohne die Eingabeaufforderungen („n: “, „… (j/n) “), die ohne
    Zeilenumbruch vor der nächsten Ausgabe stehen."""
    cleaned = re.sub(r"[^\n]*?\(j/n\) ", "", stdout)
    if prompts:
        pattern = re.compile(r"^(?:(?:" + "|".join(re.escape(p) for p in prompts) + r"): )+", re.MULTILINE)
        cleaned = pattern.sub("", cleaned)
    return normalize(cleaned.splitlines())


def check(graph: FlowGraph, tmp_path, inputs=(), decisions=()):
    code = generate(structure_diagram(graph), "java")
    expected = normalize(simulate(graph, inputs=inputs, decisions=decisions).outputs)
    stdin = "\n".join(list(inputs) + ["j" if d else "n" for d in decisions]) + "\n"
    stdout = java_run(code, tmp_path, stdin)
    return expected, java_outputs(stdout, input_names(graph))


# ----------------------------------------------------------------- Szenarien
def test_java_example_compiles_and_runs(qapp, tmp_path):
    document = DiagramDocument.open_file(EXAMPLE)
    graph = FlowGraph.from_scene(document.scene)
    code = generate(structure_diagram(graph), "java", document.meta.name)
    stdout = java_run(code, tmp_path, "3\n1\n2\n3\n")
    assert "Mittelwert" in stdout and "2" in stdout
    document.scene.clear_diagram()


def test_java_papdesigner_file_compiles(qapp, tmp_path):
    document = DiagramDocument.open_file(PAP_SAMPLE)
    code = generate(structure_diagram(FlowGraph.from_scene(document.scene)), "java", "Mittelwert")
    java_run(code, tmp_path, "2\n4\n6\n")
    document.scene.clear_diagram()


def test_java_subprogram_shares_variables(tmp_path):
    expected, stdout = check(subprogram_plan(), tmp_path, inputs=["5"])
    assert stdout == expected


@pytest.mark.parametrize("steps, inputs", [
    ([(T.PROCESS, "s = 0"), (LOOP_BEGIN, "Für x = 0 bis 1 Schritt 0,25"), (T.PROCESS, "s = s + x"),
      (LOOP_END, ""), (T.OUTPUT, "s ausgeben")], []),
    ([(T.INPUT, "Schritt st einlesen"), (T.PROCESS, "s = 0"), (LOOP_BEGIN, "Für i = 5 bis 1 Schritt st"),
      (T.PROCESS, "s = s + i"), (LOOP_END, ""), (T.OUTPUT, "s ausgeben")], ["-1"]),
    ([(LOOP_BEGIN, "Für i = 1 bis 3"), (T.PROCESS, "k = i"), (LOOP_END, ""), (T.OUTPUT, "i ausgeben")], []),
    ([(T.PROCESS, "n = 6 / 2"), (T.PROCESS, "k = 0"), (LOOP_BEGIN, "wiederhole n mal"),
      (T.PROCESS, "k = k + 1"), (LOOP_END, ""), (T.OUTPUT, "k ausgeben")], []),
    ([(T.PROCESS, "k = 0"), (LOOP_BEGIN, "wiederhole 2 mal"), (LOOP_BEGIN, "wiederhole 3 mal"),
      (T.PROCESS, "k = k + 1"), (LOOP_END, ""), (LOOP_END, ""), (T.OUTPUT, "k ausgeben")], []),
    ([(T.PROCESS, "x = 1"), (LOOP_BEGIN, ""), (T.PROCESS, "x = x * 2"), (LOOP_END, "bis x > 50"),
      (T.OUTPUT, "x ausgeben")], []),
])
def test_java_loops(steps, inputs, tmp_path):
    expected, stdout = check(linear(*steps), tmp_path, inputs=inputs)
    assert stdout == expected


@pytest.mark.parametrize("decision, labels, value", [
    ("wahl", ["1", "2", "3"], "2"),
    ("wahl ?", ["< 0", "= 0", "> 0"], "-3"),
    ("wahl", ["1", "2", "sonst"], "7"),
])
def test_java_multi_branch(decision, labels, value, tmp_path):
    graph = multi_branch(decision, labels, ["eins", "zwei", "drei"])
    expected, stdout = check(graph, tmp_path, inputs=[value])
    assert stdout == expected


@pytest.mark.parametrize("text", ['"Die Summe ist" summe', 'Ausgabe "Summe:", summe', '"Doppelt:" summe * 2',
                                  '"Plus eins:" summe + 1', "summe ausgeben", "summe * 2 ausgeben"])
def test_java_outputs(text, tmp_path):
    expected, stdout = check(linear((T.PROCESS, "summe = 6"), (T.OUTPUT, text)), tmp_path)
    assert stdout == expected


@pytest.mark.parametrize("assignment, condition", [
    ("x = 5", "0 < x < 10"),
    ("x = 7", "NICHT x > 5"),
    ("x = 7", "x ≥ 3 und x ≠ 4"),
    ("x = 7", "x mod 2 = 1"),
    ('name = "Max"', 'name = "Max"'),
])
def test_java_conditions(assignment, condition, tmp_path):
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("p", T.PROCESS, assignment),
               plan.node("d", T.DECISION, condition))
    plan.node("y", T.OUTPUT, '"wahr"')
    plan.node("n", T.OUTPUT, '"falsch"', x=200)
    plan.node("e", T.END, "Ende")
    plan.edge("d", "y", "ja")
    plan.edge("d", "n", "nein")
    plan.edge("y", "e")
    plan.edge("n", "e")
    expected, stdout = check(plan.graph(), tmp_path)
    assert stdout == expected


@pytest.mark.parametrize("expression", ["round(x / 3)", "int(x / 2)", "x ** 2", "max(x, 3, 9)", "abs(-x)",
                                        "sqrt(16) + x", "1 / 2 + x", "x // 2"])
def test_java_expressions_run(expression, tmp_path):
    expected, stdout = check(linear((T.PROCESS, "x = 7"), (T.PROCESS, f"y = {expression}"),
                                    (T.OUTPUT, "y ausgeben")), tmp_path)
    assert stdout == expected
