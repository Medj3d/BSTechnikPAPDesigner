"""Viele komplexe Pläne im Dateiformat des PapDesigners: Jeder öffnet sich ohne Hinweise und ohne Verluste,
wird genau so ausgeführt, wie er gemeint ist, übersteht Speichern und Wiederöffnen und ergibt Code.

Die Pläne erzeugt ``tests/papdesigner_corpus.py`` (reproduzierbar aus einer Nummer); was jeder Plan ausgeben
muss, rechnet der Generator selbst aus.
"""

import re

import pytest

from app.analysis.structure import structure_diagram
from app.codegen.generators import generate as generate_code
from app.diagnostics.checks import INFO, run_checks
from app.document import DiagramDocument
from app.model.element_types import ElementType as T
from app.simulation import engine
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from tests.papdesigner_corpus import generate

SEEDS = range(60)
# so viele Schritte darf ein Plan im Schreibtischtest brauchen
STEP_LIMIT = 400_000


@pytest.fixture(autouse=True)
def _application(qapp, monkeypatch):
    # manche Pläne brauchen mehr als die 10 000 Schritte, nach denen der Schreibtischtest sonst anhält
    monkeypatch.setattr(engine, "MAX_STEPS", STEP_LIMIT)
    yield


def simulate(document, inputs):
    simulator = Simulator(document.flow_graph())
    values = iter(inputs)
    for _ in range(STEP_LIMIT):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input(next(values))
        elif result.needs == NEEDS_DECISION:
            simulator.provide_decision(True)
        if simulator.finished:
            return simulator
    raise AssertionError("Der Schreibtischtest kommt nicht ans Ende")


def normalized(lines):
    return [" ".join(str(line).split()) for line in lines]


def figures(xml, subtype=None):
    pattern = r'SUBTYPE="(\w+)"'
    found = re.findall(pattern, xml)
    return [f for f in found if subtype is None or f == subtype]


def open_project(tmp_path, seed):
    project = generate(seed)
    path = tmp_path / f"korpus_{seed:03d}.pap"
    path.write_text(project.to_xml(), encoding="utf-8")
    return project, path, DiagramDocument.open_file(str(path))


@pytest.mark.parametrize("seed", SEEDS)
def test_papdesigner_plan_opens_without_loss(tmp_path, seed):
    project, path, document = open_project(tmp_path, seed)
    assert document.load_warnings == []
    assert not document.native_file
    # ein Diagramm je Seite, mit dem Namen des Diagramms
    assert len(document.pages) == len(project.routines)
    for page, routine in zip(document.pages[1:], project.routines[1:]):
        assert page.display_name == routine.name
    # nichts geht verloren: alle Bausteine und Verbindungen jedes Diagramms
    xml = path.read_text(encoding="utf-8-sig")
    diagrams = xml.split("<DIAGRAM ")[1:]
    for index, (page, part) in enumerate(zip(document.pages, diagrams)):
        expected = len(figures(part)) - (0 if index == 0 else 1)  # Titel der Unterprogramme = Seitenname
        assert len(page.scene.elements()) == expected, f"Diagramm {index}"
        assert len(page.scene.connections()) == part.count("<CONNECTION "), f"Diagramm {index}"
    # keine Verbindung ist rot markiert, jede Schleife hat ihr Gegenstück
    for page in document.pages:
        assert not [c for c in page.scene.connections() if c.warning], page.display_name


@pytest.mark.parametrize("seed", SEEDS)
def test_papdesigner_plan_runs_as_meant(tmp_path, seed):
    project, _path, document = open_project(tmp_path, seed)
    # jeder Aufruf eines eigenen Diagramms findet sein Unterprogramm
    for page in document.pages:
        for item in page.scene.elements():
            if item.element_type is T.SUBPROGRAM and not any(word in item.data.text for word in
                                                              ("Bibliothek", "LED_", "log.")):
                assert document.flow_start(item.data.text) is not None, item.data.text
    outputs = simulate(document, project.inputs).outputs
    assert normalized(outputs) == project.expected_outputs


@pytest.mark.parametrize("seed", SEEDS)
def test_papdesigner_plan_survives_saving_and_gives_code(tmp_path, seed):
    project, _path, document = open_project(tmp_path, seed)
    saved = tmp_path / "gespeichert.pap"
    document.save(str(saved))
    reopened = DiagramDocument.open_file(str(saved))
    assert reopened.load_warnings == [] and reopened.native_file
    assert [p.display_name for p in reopened.pages] == [p.display_name for p in document.pages]
    for before, after in zip(document.pages, reopened.pages):
        assert len(after.scene.elements()) == len(before.scene.elements())
        assert len(after.scene.connections()) == len(before.scene.connections())
    assert normalized(simulate(reopened, project.inputs).outputs) == project.expected_outputs
    # Hinweisliste, Struktur, Python und Java
    issues = run_checks(reopened)
    assert all(issue.severity in (INFO, "warning") for issue in issues)
    programs = structure_diagram(reopened.flow_graph())
    code = generate_code(programs, "python", reopened.meta.name)
    compile(code, f"korpus_{seed}", "exec")
    assert generate_code(programs, "java", reopened.meta.name)
