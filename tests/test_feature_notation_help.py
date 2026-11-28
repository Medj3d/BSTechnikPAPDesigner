"""Hilfe „Schreibweisen im Plan“: Jedes Beispiel der Hilfe wird wirklich ausgeführt.

Für jedes Beispiel (und jede in der Erklärung genannte andere Schreibweise) entsteht ein kleiner Plan, der im
Schreibtischtest, im erzeugten Python-Programm und – wenn ein JDK da ist – im erzeugten Java-Programm laufen und
dasselbe ausgeben muss (``tests/test_three_way.py``). Kommt ein Beispiel in die Hilfe, ohne dass es hier geprüft
wird, schlägt ``test_every_example_of_the_help_is_checked`` fehl: Die Hilfe kann nichts versprechen, was das
Programm nicht kann.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt

from app import notation
from app.analysis import text as T
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.inline_editor import SPECIAL_CHARACTERS
from app.model.element_types import LOOP_BEGIN as LB
from app.model.element_types import LOOP_END as LE
from app.model.element_types import ElementType as ET
from tests.test_review_fixes_3 import Plan, linear
from tests.test_three_way import three_way

P, I, O, D, U = ET.PROCESS, ET.INPUT, ET.OUTPUT, ET.DECISION, ET.SUBPROGRAM


def decision(condition: str, *before) -> FlowGraph:
    """Start → before… → Verzweigung → „JA“ / „NEIN“ → Ende."""
    plan = Plan()
    ids = [plan.node("s", ET.START, "Start")]
    for index, (kind, text) in enumerate(before):
        ids.append(plan.node(f"b{index}", kind, text))
    ids.append(plan.node("d", D, condition))
    plan.chain(*ids)
    plan.node("y", O, '"JA"')
    plan.node("n", O, '"NEIN"', x=300)
    plan.node("e", ET.END, "Ende")
    plan.edge("d", "y", "ja")
    plan.edge("d", "n", "nein")
    plan.edge("y", "e")
    plan.edge("n", "e")
    return plan.graph()


def choice(subject: str, labels) -> FlowGraph:
    """Start → „wahl einlesen“ → Mehrfachverzweigung mit den Ausgängen ``labels`` → Ausgabe des Ausgangs."""
    plan = Plan()
    plan.chain(plan.node("s", ET.START, "Start"), plan.node("i", I, f"{subject} einlesen"),
               plan.node("d", D, subject))
    plan.node("e", ET.END, "Ende")
    for index, label in enumerate(labels):
        plan.node(f"o{index}", O, f'"{label}"', x=200 * index)
        plan.edge("d", f"o{index}", label)
        plan.edge(f"o{index}", "e")
    return plan.graph()


def with_subprogram(main_steps, sub_start: str, sub_steps, sub_end: str = "Ende") -> FlowGraph:
    """Hauptprogramm und ein Unterprogramm (eigener Start) im selben Ablaufgraphen."""
    plan = Plan()
    ids = [plan.node("s", ET.START, "Start")]
    for index, (kind, text) in enumerate(main_steps):
        ids.append(plan.node(f"m{index}", kind, text))
    ids.append(plan.node("e", ET.END, "Ende"))
    plan.chain(*ids)
    sub = [plan.node("s2", ET.START, sub_start, x=400)]
    for index, (kind, text) in enumerate(sub_steps):
        sub.append(plan.node(f"u{index}", kind, text, x=400))
    sub.append(plan.node("e2", ET.END, sub_end, x=400))
    plan.chain(*sub)
    return plan.graph()


def loop(*steps) -> FlowGraph:
    return linear(*steps)


# Beispiel der Hilfe → Fälle: (Plan, Eingaben/Antworten, erwartete Ausgabe). Jeder Fall muss das Beispiel (oder eine
# der in der Erklärung genannten Schreibweisen) als Bausteintext enthalten.
CASES = {
    "x := x + 1": [(linear((P, "x := 4"), (P, "x := x + 1"), (O, "x ausgeben")), [], ["5"])],
    "zahl = 5": [(linear((P, f"zahl {sign} 5"), (O, "zahl ausgeben")), [], ["5"]) for sign in ("=", ":=", "←")],
    "a = 1; b = 2": [(linear((P, "a = 1; b = 2"), (O, "Ausgabe: a + b")), [], ["3"]),
                     (linear((P, "a = 1\nb = 2"), (O, "Ausgabe: a + b")), [], ["3"])],
    'name = "Anna"': [(linear((P, 'name = "Anna"'), (O, "name ausgeben")), [], ["Anna"])],
    'gruss = "Hallo " + name': [
        (linear((P, 'name = "Anna"'), (P, 'gruss = "Hallo " + name'), (O, "gruss ausgeben")), [], ["Hallo Anna"]),
        (linear((P, 'gruss = "Note " + 2'), (O, "gruss ausgeben")), [], ["Note 2"])],
    "fertig = wahr": [(decision("fertig", (P, "fertig = wahr")), [], ["JA"]),
                      (decision("fertig", (P, "fertig = falsch")), [], ["NEIN"])],
    "mittel = (a + b) / 2": [(linear((P, "a = 3; b = 4"), (P, "mittel = (a + b) / 2"), (O, "mittel ausgeben")),
                              [], ["3.5"])] + [
        (linear((P, f"y = 6 {op} 2"), (O, "y ausgeben")), [], [result])
        for op, result in (("+", "8"), ("-", "4"), ("*", "12"), ("/", "3"))],
    "preis = 2,5 * 4": [(linear((P, "preis = 2,5 * 4"), (O, "preis ausgeben")), [], ["10"]),
                        (linear((P, "preis = 2.5 * 4"), (O, "preis ausgeben")), [], ["10"])],
    "rest = 17 mod 5": [(linear((P, f"rest = 17 {op} 5"), (O, "rest ausgeben")), [], ["2"]) for op in ("mod", "%")],
    "ganz = 17 div 5": [(linear((P, f"ganz = 17 {op} 5"), (O, "ganz ausgeben")), [], ["3"]) for op in ("div", "//")],
    "q = x^2": [(linear((P, "x = 3"), (P, f"q = {power}"), (O, "q ausgeben")), [], ["9"])
                for power in ("x^2", "x**2", "x²")],
    "w = wurzel(16)": [(linear((P, f"w = {call}"), (O, "w ausgeben")), [], [result]) for call, result in (
        ("wurzel(16)", "4"), ("abs(-3)", "3"), ("min(4, 7)", "4"), ("max(4, 7)", "7"), ("ganzzahl(7,8)", "7"),
        ("sin(0)", "0"), ("cos(0)", "1"), ("runden(pi, 2)", "3.14"))],
    "r = runden(x, 2)": [(linear((P, f"x = {value}"), (P, "r = runden(x, 2)"), (O, "r ausgeben")), [], [result])
                         for value, result in (("2,345", "2.35"), ("2,344", "2.34"), ("1,005", "1.01"))],
    "n einlesen": [(linear((I, "n einlesen"), (O, "n ausgeben")), ["5"], ["5"])],
    "Eingabe: a, b": [(linear((I, "Eingabe: a, b"), (O, "Ausgabe: a + b")), ["2", "3"], ["5"])],
    '"Wie alt bist du?" alter': [(linear((I, '"Wie alt bist du?" alter'), (O, "alter ausgeben")), ["15"], ["15"])],
    "summe ausgeben": [(linear((P, "summe = 6"), (O, "summe ausgeben")), [], ["6"])],
    '"Summe: " summe': [(linear((P, "summe = 6"), (O, '"Summe: " summe')), [], ["Summe: 6"])],
    "Ausgabe: x * 2": [(linear((P, "x = 4"), (O, "Ausgabe: x * 2")), [], ["8"])],
    '"Fertig!"': [(linear((O, '"Fertig!"')), [], ["Fertig!"])],
    "x > 0 ?": [(decision(condition, (P, f"x = {x}")), [], [result]) for condition, x, result in (
        ("x > 0 ?", 5, "JA"), ("x > 0 ?", -1, "NEIN"), ("x < 0", 0, "NEIN"), ("x <= 0", 0, "JA"),
        ("x >= 0", 0, "JA"), ("x > 0", 0, "NEIN"))],
    "x = 0": [(decision(condition, (P, f"x = {x}")), [], [result]) for condition, x, result in (
        ("x = 0", 0, "JA"), ("x = 0", 1, "NEIN"), ("x == 0", 0, "JA"))],
    "x ≠ 0": [(decision(f"x {sign} 0", (P, f"x = {x}")), [], [result])
              for sign in ("≠", "<>", "!=") for x, result in ((1, "JA"), (0, "NEIN"))],
    "x ≥ 1 und x ≤ 6": [(decision(condition, (P, f"x = {x}")), [], [result]) for condition, x, result in (
        ("x ≥ 1 und x ≤ 6", 3, "JA"), ("x ≥ 1 und x ≤ 6", 7, "NEIN"), ("x < 1 oder x > 6", 7, "JA"),
        ("nicht x > 6", 7, "NEIN"), ("nicht x > 6", 2, "JA"))],
    'antwort = "ja"': [(decision('antwort = "ja"', (I, "antwort einlesen")), [answer], [result])
                       for answer, result in (("ja", "JA"), ("nein", "NEIN"))],
    "wahl": [(choice("wahl", ("1", "2", "sonst")), [answer], [result])
             for answer, result in (("1", "1"), ("2", "2"), ("7", "sonst"))],
    "solange i < 10": [(loop((P, "i = 0"), (LB, "solange i < 10"), (P, "i = i + 3"), (LE, ""), (O, "i ausgeben")),
                        [], ["12"]),
                       (loop((P, "i = 20"), (LB, "solange i < 10"), (P, "i = i + 3"), (LE, ""), (O, "i ausgeben")),
                        [], ["20"])],   # Kopfbedingung: kein Durchlauf
    "bis i >= 10": [(loop((P, "i = 0"), (LB, "wiederhole"), (P, "i = i + 3"), (LE, "bis i >= 10"),
                          (O, "i ausgeben")), [], ["12"]),
                    (loop((P, "i = 20"), (LB, "wiederhole"), (P, "i = i + 3"), (LE, "bis i >= 10"),
                          (O, "i ausgeben")), [], ["23"])],   # Fußbedingung: mindestens ein Durchlauf
    "für i = 1 bis 10": [(loop((P, "s = 0"), (LB, "für i = 1 bis 10"), (P, "s = s + i"), (LE, ""),
                               (O, "s ausgeben")), [], ["55"])],
    "für i = 10 bis 0 schritt -2": [(loop((P, "s = 0"), (LB, "für i = 10 bis 0 schritt -2"), (P, "s = s + i"),
                                          (LE, ""), (O, "s ausgeben")), [], ["30"])],
    "3-mal": [(loop((P, "n = 4"), (P, "k = 0"), (LB, head), (P, "k = k + 1"), (LE, ""), (O, "k ausgeben")),
               [], [result]) for head, result in (("3-mal", "3"), ("wiederhole n mal", "4"))],
    "Summe berechnen": [(with_subprogram([(P, "a = 2"), (U, "Summe berechnen"), (O, "s ausgeben")],
                                         "Summe berechnen", [(P, "s = a + 1")]), [], ["3"])],
    "doppelt(n)": [(with_subprogram([(P, "x = 21"), (U, "y := doppelt(x)"), (O, "y ausgeben")],
                                    "doppelt(n)", [(P, "return n * 2")]), [], ["42"])],
    "y := doppelt(x)": [(with_subprogram([(P, "x = 5"), (U, "y := doppelt(x)"), (O, "y ausgeben")],
                                         "doppelt(n)", [(P, "return n * 2")]), [], ["10"])],
    "return n * 2": [(with_subprogram([(P, "x = 3"), (U, "y := doppelt(x)"), (O, "y ausgeben")],
                                      "doppelt(n)", steps, end), [], ["6"])
                     for steps, end in (([(P, "return n * 2")], "Ende"), ([(P, "Rückgabe: n * 2")], "Ende"),
                                        ([], "return n * 2"))],
}


def test_every_example_of_the_help_is_checked():
    examples = [entry.example for entry in notation.all_notations()]
    assert len(examples) == len(set(examples)), "ein Beispiel steht doppelt in der Hilfe"
    assert set(examples) == set(CASES), (set(examples) ^ set(CASES))


def test_the_hint_example_is_part_of_the_help():
    assert notation.HINT_EXAMPLE in CASES


def _case_ids():
    return [f"{example}#{index}" for example, cases in CASES.items() for index in range(len(cases))]


@pytest.mark.parametrize("case", _case_ids())
def test_example_runs_in_simulator_python_and_java(case, tmp_path):
    example, index = case.rsplit("#", 1)
    graph, answers, expected = CASES[example][int(index)]
    texts = {node.text for node in graph.nodes.values()} | {edge.label for edge in graph.edges}
    if int(index) == 0:
        # der erste Fall benutzt das Beispiel genau so, wie es in der Hilfe steht
        assert example in texts, (example, texts)
    programs = structure_diagram(graph)
    # nichts davon wird zum Kommentar „TODO: …“ (= nicht verstanden) – in keiner Sprache
    for language, marker in (("python", "# TODO"), ("java", "// TODO"), ("pseudo", "TODO:")):
        assert marker not in generate(programs, language), (language, generate(programs, language))
    three_way(graph, tmp_path, answers, expected=expected)


def test_alternatives_named_in_the_explanations_are_checked():
    """Was eine Erklärung als andere Schreibweise nennt, kommt in einem geprüften Fall vor."""
    texts = set()
    for cases in CASES.values():
        for graph, _answers, _expected in cases:
            texts |= {node.text for node in graph.nodes.values()} | {edge.label for edge in graph.edges}
    joined = "\n".join(texts)
    tokens = {
        ":=", "=", "←", ";", "+", "wahr", "falsch", "-", "*", "/", "%", "//", "x**2", "x²", "wurzel", "abs", "min",
        "max", "ganzzahl", "sin", "cos", "pi", "<", ">", "<=", ">=", "==", "≠", "≤", "≥", "<>", "!=", "und", "oder", "nicht",
        "1", "2", "sonst", "wiederhole", "wiederhole n mal", "Rückgabe: n * 2", "Summe berechnen"}
    named = set()
    for entry in notation.all_notations():
        for _name, value in entry.values:
            parts = [value] if value in tokens else [part for part in value.replace(",", " ").split() if part]
            named |= set(parts)
    assert named <= tokens, named - tokens
    for token in named:
        assert token in joined, token


def test_special_characters_named_in_the_help_are_in_the_menu():
    menu = {char for char, _description in SPECIAL_CHARACTERS}
    assert {"≤", "≥", "≠"} <= menu


def test_parsers_read_the_examples_as_described():
    """Gegenprobe direkt an den Deutungsfunktionen (unabhängig vom Ablauf)."""
    assert T.parse_assignments("x := x + 1") == [("x", "x + 1")]
    assert T.parse_assignments("a = 1; b = 2") == [("a", "1"), ("b", "2")]
    assert T.input_variables("n einlesen") == ["n"]
    assert T.input_variables("Eingabe: a, b") == ["a", "b"]
    assert T.input_variables('"Wie alt bist du?" alter') == ["alter"]
    assert T.parse_loop_header("solange i < 10").kind == "while"
    assert T.parse_loop_header("für i = 1 bis 10").kind == "for"
    assert T.parse_loop_header("für i = 10 bis 0 schritt -2").step == "-2"
    assert T.parse_loop_header("3-mal").kind == "times"
    assert T.parse_loop_footer("bis i >= 10") == ("until", "i >= 10")
    assert T.routine_parameters("doppelt(n)") == ["n"]
    assert T.call_spec("y := doppelt(x)") == ("y", ["x"])
    assert T.return_statement("return n * 2") == "n * 2"
    assert T.return_statement("Rückgabe: n * 2") == "n * 2"


# ------------------------------------------------------------------ Dialog
def test_dialog_lists_every_example_and_filters(qapp):
    from app.dialogs.notation import NotationDialog

    dialog = NotationDialog()
    shown = [dialog.table.item(row, 1).text() for row in range(dialog.table.rowCount())]
    for entry in notation.all_notations():
        assert entry.example in shown
    dialog.search.setText("Schleife")
    visible = [row for row in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(row)]
    assert visible and len(visible) < dialog.table.rowCount()
    dialog.search.setText("")
    assert not any(dialog.table.isRowHidden(row) for row in range(dialog.table.rowCount()))
    dialog.deleteLater()


@pytest.mark.parametrize("code", ["en", "es", "fr", "pt", "ru", "ar", "zh", "ja"])
def test_dialog_explanations_are_translated_and_examples_are_not(qapp, code):
    from app import i18n
    from app.dialogs.notation import NotationDialog

    i18n.set_language(code)
    dialog = NotationDialog()
    shown = [dialog.table.item(row, 1).text() for row in range(dialog.table.rowCount())]
    meanings = [dialog.table.item(row, 2).text() for row in range(dialog.table.rowCount())]
    assert {entry.example for entry in notation.all_notations()} <= set(shown)
    assert "Text steht in Anführungszeichen" not in meanings
    assert all("{" not in text for text in meanings)
    dialog.deleteLater()


@pytest.mark.parametrize("code", ["de", "en", "ru", "ar", "zh", "ja"])
def test_hint_names_the_menu_like_the_menu_itself(qapp, code):
    from app import i18n
    from app.actions import clean_text
    from app.canvas_hint import hint_text
    from app.i18n import tr

    i18n.set_language(code)
    text = hint_text()
    assert notation.HINT_EXAMPLE in text
    assert clean_text(tr("&Hilfe")) in text and clean_text(tr("&Schreibweisen im Plan")) in text
    assert "{" not in text


def test_example_can_be_copied_with_ctrl_c(qapp):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from app.dialogs.notation import NotationDialog

    dialog = NotationDialog()
    row = next(row for row in range(dialog.table.rowCount()) if dialog.table.item(row, 1).text() == "3-mal")
    dialog.table.setCurrentCell(row, 1)
    QTest.keyClick(dialog.table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "3-mal"
    dialog.deleteLater()


# ------------------------------------------------------------- Tipp auf der Arbeitsfläche
def _hint(view):
    return view.notation_hint


def test_hint_shows_on_a_plan_with_only_start_and_end(view, qapp):
    from tests.conftest import add

    scene = view.document.scene
    add(scene, ET.START, 0, -100)
    add(scene, ET.END, 0, 100)
    qapp.processEvents()
    hint = _hint(view)
    assert hint.isVisible()
    assert notation.HINT_EXAMPLE in hint.text()
    assert "Schreibweisen im Plan" in hint.text()
    block = add(scene, ET.PROCESS, 0, 0)
    qapp.processEvents()
    assert not hint.isVisible()
    scene.select_items([block])
    scene.delete_selection()
    qapp.processEvents()
    assert hint.isVisible()
    view.document.undo_stack.undo()   # Baustein wieder da
    qapp.processEvents()
    assert not hint.isVisible()


def test_hint_does_not_cover_the_plan_and_lets_clicks_through(view, qapp):
    hint = _hint(view)
    assert hint.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert view.viewport().geometry().contains(hint.geometry())
    assert hint.parent() is view   # nicht im Viewport: sonst verschiebt ihn das Schwenken mit


def test_hint_is_not_exported(view, qapp, tmp_path):
    """Der Tipp ist ein Fenster über der Arbeitsfläche, kein Teil der Szene: Bild, PDF und Druck zeigen ihn nicht."""
    from app import export

    hint = _hint(view)
    scene = view.document.scene
    assert hint.isVisible()
    assert all(item.toolTip() != hint.text() for item in scene.items())
    path = tmp_path / "leer.svg"
    from tests.conftest import add
    add(scene, ET.START, 0, 0)
    export.export_svg(scene, str(path), export.ExportOptions())
    assert notation.HINT_EXAMPLE not in path.read_text(encoding="utf-8")
    assert "Schreibweisen" not in path.read_text(encoding="utf-8")


def test_hint_follows_the_shown_page(qapp, tmp_path):
    from app.canvas import DiagramView
    from app.document import DiagramDocument
    from tests.conftest import add

    document = DiagramDocument()
    view = DiagramView(document)
    view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    view.resize(900, 600)
    view.show()
    qapp.processEvents()
    add(document.scene, ET.PROCESS, 0, 0)
    qapp.processEvents()
    assert not view.notation_hint.isVisible()
    document.insert_page(1, document.new_page("Teil"))   # neue, leere Unterprogramm-Seite wird angezeigt
    qapp.processEvents()
    assert document.current_page_index == 1
    assert view.notation_hint.isVisible()
    document.set_current_page(0)
    qapp.processEvents()
    assert not view.notation_hint.isVisible()
    view.close()
    document.scene.clear_diagram()
    view.deleteLater()
    document.deleteLater()
