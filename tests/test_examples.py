"""Lernbeispiele (``assets/examples``): Sie öffnen sich ohne Hinweise, sind fehlerfrei, laufen im
Schreibtischtest durch und ergeben übersetzbaren Code."""

import os

import pytest

from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.diagnostics.checks import INFO, run_checks
from app.document import DiagramDocument
from app.examples import example_files
from tests.test_subprograms import run

# Eingaben und die erwartete Ausgabe je Lernbeispiel
CASES = {
    "Lernbeispiel_1_Ablaufplan.pap": (["2"], ["Fläche: 12,57"]),
    "Lernbeispiel_2_Verzweigungen.pap": (["95"], ["sehr gut"]),
    "Lernbeispiel_3_Schleifen.pap": (["0", "-3", "4"], ["Summe: 10"]),
    "Lernbeispiel_4_Unterprogramme.pap": (["84", "36"], ["Willkommen beim ggT-Rechner!",
                                                         "größter gemeinsamer Teiler: 12"]),
    "Lernbeispiel_5_Programmierung.pap": (["20"], ["2", "3", "5", "7", "11", "13", "17", "19"]),
}


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


def test_all_examples_are_bundled():
    assert sorted(os.path.basename(path) for path, _title in example_files()) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_example_opens_cleanly_and_runs(name):
    path = dict((os.path.basename(p), p) for p, _t in example_files())[name]
    document = DiagramDocument.open_file(path)
    assert document.load_warnings == []
    problems = [issue.message for issue in run_checks(document) if issue.severity != INFO]
    assert problems == []
    inputs, expected = CASES[name]
    outputs = run(document, inputs).outputs
    assert [line.strip() for line in outputs] == expected
    # Code-Erzeugung: Python lässt sich übersetzen
    code = generate(structure_diagram(document.flow_graph()), "python", document.meta.name)
    compile(code, name, "exec")
    assert "TODO:" not in code
