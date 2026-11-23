"""Targeted regression cases for simulation, generated code and structograms.

Known findings use strict xfail so an unexpected pass prompts a review.
Run with --runxfail to make the current discrepancies fail the run.
"""

import pytest

from app import styles, subprograms
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.model.element_types import LOOP_BEGIN, LOOP_END
from app.model.element_types import ElementType as T
from app.nsd.renderer import render_image
from app.simulation.engine import Simulator
from tests.test_review_fixes_3 import Plan, linear, simulate
from tests.test_three_way import JAVAC, run_java, run_python


@pytest.fixture
def string_repeat_plan():
    return linear((T.PROCESS, 'x = "abc" * 1,5'), (T.OUTPUT, "x ausgeben"))


def test_fractional_repeat_reference_behavior(string_repeat_plan):
    assert simulate(string_repeat_plan).outputs == ["abc"]


def test_python_fractional_string_repeat_matches_simulation(string_repeat_plan):
    code = generate(structure_diagram(string_repeat_plan), "python")
    assert run_python(code, ()) == simulate(string_repeat_plan).outputs


def test_escaped_quote_inside_output_text():
    graph = linear((T.OUTPUT, r'Ausgabe "A\"B"'))
    assert simulate(graph).outputs == ['A"B']


def test_escaped_quote_and_semicolon_inside_assignment():
    graph = linear((T.PROCESS, r'x = "A\";B"'), (T.OUTPUT, "x ausgeben"))
    assert simulate(graph).outputs == ['A";B']


@pytest.mark.skipif(JAVAC is None, reason="Java toolchain unavailable")
def test_java_emoji_length_matches_simulation(tmp_path):
    graph = linear((T.PROCESS, 'x = len("😀")'), (T.OUTPUT, "x ausgeben"))
    code = generate(structure_diagram(graph), "java")
    assert run_java(code, (), tmp_path) == simulate(graph).outputs


def test_python_division_by_zero_agrees_with_simulation():
    graph = linear((T.PROCESS, "x = 1 / 0"), (T.OUTPUT, '"weiter"'))
    code = generate(structure_diagram(graph), "python")
    # beide brechen an derselben Stelle ab: kein „weiter“
    with pytest.raises(ZeroDivisionError):
        run_python(code, ())
    assert simulate(graph).outputs == []


def test_subprogram_signature_and_call_return_value():
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("init", T.PROCESS, "x = 10; y = 0; n = 2"),
               plan.node("call", T.SUBPROGRAM, "y := doppelt(x)"), plan.node("out", T.OUTPUT, "y ausgeben"),
               plan.node("end", T.END, "Ende"))
    plan.chain(plan.node("sub", T.START, "int doppelt(int n)"),
               plan.node("return", T.PROCESS, "return n * 2"), plan.node("subend", T.END, "Ende"))

    assert simulate(plan.graph()).outputs == ["20"]


def test_explicit_choices_do_not_match_an_unlisted_value():
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("assign", T.PROCESS, "x = 9"),
               plan.node("choice", T.DECISION, "x"))
    for number in range(1, 4):
        plan.edge("choice", plan.node(f"out{number}", T.OUTPUT, f'"Fall {number}"'), str(number))
        plan.edge(f"out{number}", plan.node(f"end{number}", T.END, "Ende"))

    simulator = Simulator(plan.graph())
    for _ in range(10):
        result = simulator.step()
        if result.finished or result.needs:
            break
    assert simulator.outputs == []


def test_generated_python_guards_zero_counting_step():
    graph = linear((LOOP_BEGIN, "Für i = 1 bis 3 Schritt 0"), (T.PROCESS, "x = x + 1"),
                   (LOOP_END, "Schleifenende"), (T.OUTPUT, "x ausgeben"))
    code = generate(structure_diagram(graph), "python")

    # The reused Python runner breaks after a bounded number of traced lines.
    # der erzeugte Code hält mit klarer Meldung an, statt endlos zu laufen
    with pytest.raises(SystemExit) as stopped:
        run_python(code, ())
    assert "0" in str(stopped.value)


def test_japanese_subprogram_name_can_be_entered(document):
    assert subprograms.name_error(document, "補助") is None


def test_structogram_bitmap_includes_distinguishing_title_suffix(qapp):
    prefix = "Langer Titel " * 16
    first = linear((T.PROCESS, "x = 1"), name=prefix + "Apfel")
    second = linear((T.PROCESS, "x = 1"), name=prefix + "Birne")

    first_image = render_image(structure_diagram(first), styles.LIGHT, scale=1)
    second_image = render_image(structure_diagram(second), styles.LIGHT, scale=1)
    assert not first_image.isNull() and not second_image.isNull()
    assert first_image != second_image
