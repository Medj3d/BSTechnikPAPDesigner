"""Regressionstests zur Gegenprüfung von Struktogramm, Auto-Layout, Hinweisliste und Schreibtischtest-Panel."""

import pytest
from PySide6.QtCore import QPointF

from app import styles
from app.analysis.structure import structure_diagram
from app.diagnostics.checks import run_checks
from app.layout.auto_layout import apply_layout, plan_auto_layout
from app.model.element_types import ElementType as T
from app.nsd.renderer import NsdRenderer, _If, _Text
from tests.test_review_fixes_3 import Plan, linear
from tests.test_three_way import I, O, P


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


def place(scene, kind, x, y, text=None):
    item = scene.element(scene.insert_element(kind, QPointF(x, y)))
    if text is not None:
        item.set_text(text)
    return item


def link(scene, source, source_port, target, target_port, label=None):
    connection = scene.connection(scene.create_connection(source, source_port, target, target_port))
    if label is not None:
        connection.set_label(label)
    return connection


def overlaps(scene) -> list:
    items = [item for item in scene.elements() if not item.is_junction]
    return [(a.data.text, b.data.text) for index, a in enumerate(items) for b in items[index + 1:]
            if a.scene_rect().intersects(b.scene_rect())]


# ------------------------------------------------------------------ Layout
def test_layout_places_all_exits_of_a_multi_way_decision_in_one_row(scene):
    start = place(scene, T.START, 0, 0)
    read = place(scene, T.INPUT, 0, 120, "note einlesen")
    decision = place(scene, T.DECISION, 0, 260, "note")
    done = place(scene, T.OUTPUT, 0, 600, '"fertig"')
    end = place(scene, T.END, 0, 720)
    link(scene, start, "bottom", read, "top")
    link(scene, read, "bottom", decision, "top")
    outputs = []
    for index, label in enumerate(["1", "2", "3", "sonst"]):
        box = place(scene, T.OUTPUT, index * 240, 420 + index * 40, f'"Note {label}"')
        link(scene, decision, "bottom" if index == 0 else "right", box, "top", label)
        link(scene, box, "bottom", done, "top")
        outputs.append(box)
    link(scene, done, "bottom", end, "top")
    assert apply_layout(scene, plan_auto_layout(scene))
    assert len({box.pos().y() for box in outputs}) == 1  # eine Reihe, keine Treppe
    assert not overlaps(scene)


def test_layout_keeps_attached_comment_clear_of_the_other_branch(scene):
    start = place(scene, T.START, 0, 0)
    decision = place(scene, T.DECISION, 0, 160, "x > 5")
    yes = place(scene, T.OUTPUT, 0, 320, '"groß"')
    no = place(scene, T.OUTPUT, 480, 320, '"klein"')
    end = place(scene, T.END, 0, 460)
    comment = place(scene, T.COMMENT, 220, 320, "Ausgabe für große Zahlen")
    link(scene, start, "bottom", decision, "top")
    link(scene, decision, "bottom", yes, "top", "ja")
    link(scene, decision, "right", no, "top", "nein")
    link(scene, yes, "bottom", end, "top")
    link(scene, no, "bottom", end, "right")
    link(scene, yes, "right", comment, "left")
    apply_layout(scene, plan_auto_layout(scene))
    assert not overlaps(scene)


def test_layout_keeps_reachable_loop_end_without_begin_in_the_column(scene):
    start = place(scene, T.START, 0, 0)
    step = place(scene, T.PROCESS, 0, 120, "k = k + 1")
    begin = place(scene, T.LOOP, 400, 240)  # fügt Schleifenbeginn und -ende als Paar ein
    loop_end = next(item for item in scene.elements()
                    if item.element_type is T.LOOP and item.data.properties.get("part") == "end")
    scene.select_items([begin])
    scene.delete_selection()                # übrig bleibt ein Schleifenende ohne Schleifenbeginn
    loop_end.set_text("bis k > 3")
    end = place(scene, T.END, 0, 360)
    link(scene, start, "bottom", step, "top")
    link(scene, step, "bottom", loop_end, "top")
    link(scene, loop_end, "bottom", end, "top")
    apply_layout(scene, plan_auto_layout(scene))
    assert loop_end.pos().x() == step.pos().x()
    assert step.pos().y() < loop_end.pos().y() < end.pos().y()


# ------------------------------------------------------------ Struktogramm
def test_structogram_never_makes_a_column_narrower_than_its_longest_word():
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("i", I, "monat einlesen"), plan.node("d", T.DECISION, "monat"))
    plan.node("e", T.END, "Ende")
    months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
              "November", "Dezember"]
    for index, month in enumerate(months):
        box = plan.node(f"o{index}", O, f'"{month}"', x=index * 200)
        plan.edge("d", box, str(index + 1))
        plan.edge(box, "e")
    other = plan.node("x", O, '"ungültiger Monat"', x=2600)
    plan.edge("d", other, "sonst")
    plan.edge(other, "e")
    renderer = NsdRenderer(structure_diagram(plan.graph())[0], styles.LIGHT)

    def check(node, width):
        assert width + 0.5 >= node.min_width(renderer.fm)
        if isinstance(node, _If):
            left = node.split(width, renderer.fm)
            check(node.yes, left)
            check(node.no, width - left)
        for child in getattr(node, "children", []):
            check(child, width)

    assert renderer.width > 900  # breiter als die übliche Grenze, weil der Inhalt es braucht
    check(renderer.root, renderer.width)


def test_structogram_header_leaves_room_for_the_condition_between_the_diagonals():
    renderer = NsdRenderer(structure_diagram(linear((P, "x = 1")))[0], styles.LIGHT)
    node = _If("jahresbrutto > beitragsbemessungsgrenze und nicht privatversichert", _Text("a"), _Text("b"), "ja", "nein")
    width, fm = 456.0, renderer.fm
    size, head = node._condition_size(width, fm), node.header_height(width, fm)
    level = (6.0 + size.height()) / head   # Anteil der Kopfhöhe an der Unterkante des Textes
    assert width * (1 - level) >= size.width()  # freie Breite zwischen den Schrägen


# ------------------------------------------------------------ Hinweisliste
def test_hint_list_shows_all_structure_warnings(scene):
    start = place(scene, T.START, 0, 0)
    decision = place(scene, T.DECISION, 0, 160, "x > 5")
    out = place(scene, T.OUTPUT, 0, 320, '"weiter"')
    end = place(scene, T.END, 0, 460)
    link(scene, start, "bottom", decision, "top")
    link(scene, decision, "bottom", out, "top", "ja")
    link(scene, out, "bottom", end, "top")
    messages = " | ".join(issue.message for issue in run_checks(scene))
    assert "nur einen Ausgang" in messages


# -------------------------------------------------------------------- Panel
def test_panel_shows_why_an_input_was_rejected(qapp, document):
    from app.simulation.panel import SimulationPanel
    scene = document.scene
    start = place(scene, T.START, 0, 0)
    read = place(scene, T.INPUT, 0, 120, "a, b einlesen")
    add = place(scene, T.PROCESS, 0, 240, "c = a + b")
    out = place(scene, T.OUTPUT, 0, 360, "c ausgeben")
    end = place(scene, T.END, 0, 480)
    for upper, lower in zip((start, read, add, out), (read, add, out, end)):
        link(scene, upper, "bottom", lower, "top")
    panel = SimulationPanel()
    panel.set_document(document)
    panel.run()
    panel.input_field.setText("3 vier")
    panel.submit_input()
    assert "vier" in panel.status.text() and panel.simulator.pending is not None
    panel.input_field.setText("3,5 4")
    panel.submit_input()
    panel.run()
    assert panel.simulator.outputs == ["7,5"]
    panel.stop()
    panel.deleteLater()
