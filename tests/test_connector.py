"""Übergangsstelle (Konnektor nach DIN 66001): Kreis mit Marke, Paare mit gleicher Marke gehören zusammen."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF

from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.diagnostics.checks import run_checks
from app.document import DiagramDocument
from app.model.element_types import ElementType as T
from app.model.element_types import display_name_for
from app.simulation.engine import Simulator
from tests.test_menu_reorg import menus_of, window  # noqa: F401  (Fixture des Hauptfensters)


def _add(scene, element_type, x, y, text=None):
    item = scene.element(scene.insert_element(element_type, QPointF(x, y)))
    if text is not None:
        item.set_text(text)
    return item


def _con(scene, a, a_port, b, b_port):
    return scene.connection(scene.create_connection(a, a_port, b, b_port))


def _loop_with_connectors(scene, exit_mark="A", entry_mark="A"):
    """i := 0 → (A) → [i >= 3?] –nein→ i := i + 1 → (A) …; ja → Ausgabe i → Ende."""
    start = _add(scene, T.START, 0, 0)
    init = _add(scene, T.PROCESS, 0, 100, "i := 0")
    entry = _add(scene, T.CONNECTOR, 0, 180, entry_mark)
    decision = _add(scene, T.DECISION, 0, 280, "i >= 3")
    step = _add(scene, T.PROCESS, 260, 280, "i := i + 1")
    exit_ = _add(scene, T.CONNECTOR, 260, 380, exit_mark)
    output = _add(scene, T.OUTPUT, 0, 420, "i")
    end = _add(scene, T.END, 0, 520)
    _con(scene, start, "bottom", init, "top")
    _con(scene, init, "bottom", entry, "top")
    _con(scene, entry, "bottom", decision, "top")
    yes = _con(scene, decision, "bottom", output, "top")
    no = _con(scene, decision, "right", step, "left")
    yes.set_label("ja")
    no.set_label("nein")
    _con(scene, step, "bottom", exit_, "top")
    _con(scene, output, "bottom", end, "top")
    return entry, exit_


def _simulate(graph):
    sim = Simulator(graph)
    for _ in range(500):
        sim.step()
        if sim.finished:
            break
    return sim


def test_connector_pair_runs_like_a_loop(qapp):
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene)
    graph = FlowGraph.from_scene(doc.scene)
    sim = _simulate(graph)
    assert sim.finished
    assert sim.variables["i"] == 3
    code = generate(structure_diagram(graph), "python")
    assert "while" in code and "i = i + 1" in code
    assert "connector" not in code and "junction" not in code


def test_connector_is_a_labelled_circle(qapp):
    doc = DiagramDocument()
    item = _add(doc.scene, T.CONNECTOR, 0, 0)
    assert item.data.text == "A"
    assert item.data.width == item.data.height
    item.set_text("Schleife 1")
    assert item.data.width == item.data.height >= 40
    assert display_name_for(T.CONNECTOR) == "Übergangsstelle"


def test_correct_pair_gives_no_connector_hint(qapp):
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene)
    messages = [issue.message for issue in run_checks(doc)]
    assert not [m for m in messages if "Übergangsstelle" in m or "Sackgasse" in m or "nie erreicht" in m], messages


def test_missing_partner_is_reported(qapp):
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene, exit_mark="B")
    messages = [issue.message for issue in run_checks(doc)]
    assert any("keine zweite Übergangsstelle „B“" in m for m in messages), messages
    assert not [m for m in messages if "Sackgasse" in m or "keinen Nachfolger" in m], messages


def test_target_nobody_jumps_to_is_reported(qapp):
    doc = DiagramDocument()
    lonely = _add(doc.scene, T.CONNECTOR, 0, 0, "C")
    end = _add(doc.scene, T.END, 0, 100)
    _con(doc.scene, lonely, "bottom", end, "top")
    messages = [issue.message for issue in run_checks(doc)]
    assert any("Keine Übergangsstelle „C“ führt hierher" in m for m in messages), messages


def test_mark_ignores_case_and_spaces(qapp):
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene, exit_mark=" a ")
    assert _simulate(FlowGraph.from_scene(doc.scene)).finished


def test_two_exits_with_same_mark_are_reported(qapp):
    doc = DiagramDocument()
    entry, _exit = _loop_with_connectors(doc.scene)
    other = _add(doc.scene, T.CONNECTOR, -200, 180, "A")
    target = _add(doc.scene, T.PROCESS, -200, 280, "x := 1")
    _con(doc.scene, other, "bottom", target, "top")
    messages = [issue.message for issue in run_checks(doc)]
    assert any("an 2 Stellen weiter" in m for m in messages), messages


def test_connector_survives_save_and_load(qapp, tmp_path):
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene)
    path = tmp_path / "konnektor.pap"
    doc.save(str(path))
    loaded = DiagramDocument.open_file(str(path))
    connectors = [item for item in loaded.scene.elements() if item.element_type is T.CONNECTOR]
    assert sorted(item.data.text for item in connectors) == ["A", "A"]
    assert _simulate(FlowGraph.from_scene(loaded.scene)).variables["i"] == 3


def test_connector_is_in_palette_and_insert_menu(window):
    from app.actions import insert_action_name
    from app.palette import PaletteEntry
    action = window.actions[insert_action_name(T.CONNECTOR)]
    assert action in menus_of(window)["Einfügen"]
    assert any(entry.element_type is T.CONNECTOR for entry in window.palette.findChildren(PaletteEntry))
    action.trigger()
    assert [item for item in window.current_view().document.scene.elements() if item.element_type is T.CONNECTOR]


def test_auto_layout_does_not_pull_pairs_together(qapp):
    graph = FlowGraph.from_scene
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene)
    assert not [e for e in graph(doc.scene, link_connectors=False).edges if e.id.startswith("connector-link:")]
    assert [e for e in graph(doc.scene).edges if e.id.startswith("connector-link:")]


@pytest.mark.parametrize("language", ["python", "java", "pseudo"])
def test_code_for_all_languages(qapp, language):
    doc = DiagramDocument()
    _loop_with_connectors(doc.scene)
    code = generate(structure_diagram(FlowGraph.from_scene(doc.scene)), language)
    assert "Übergangsstelle" not in code
