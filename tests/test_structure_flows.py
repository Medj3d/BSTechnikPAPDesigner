"""Ablaufformen, die die Struktur-Erkennung richtig deuten muss.

Jeder Plan läuft durch Schreibtischtest, erzeugtes Python und (mit JDK)
erzeugtes Java; alle drei müssen dieselbe Ausgabe liefern. Die Fälle
stammen aus einer systematischen Prüfung mit einem echten Java-Compiler –
vorher entstanden hier u. a. Endlosschleifen im erzeugten Programm.
"""

import pytest

from app.analysis.ast import Break, Continue, DoWhileLoop, If, LimitLoop, Loop, Unstructured, WhileLoop
from app.analysis.structure import structure_diagram
from app.analysis.variables import walk
from app.codegen.generators import generate
from app.model.element_types import LOOP_BEGIN, LOOP_END
from app.model.element_types import ElementType as T
from tests.test_review_fixes_3 import Plan, linear
from tests.test_three_way import I, O, P, three_way

D = T.DECISION


def flow(nodes: dict, edges: list):
    """Plan aus {id: (Typ, Text)} und Kanten (von, nach[, Beschriftung]); „s“ = Start, „e“ = Ende."""
    plan = Plan()
    plan.node("s", T.START, "Start")
    for nid, (kind, text) in nodes.items():
        if kind in (LOOP_BEGIN, LOOP_END):
            plan.node(nid, T.LOOP, text, part=kind)
        else:
            plan.node(nid, kind, text)
    plan.node("e", T.END, "Ende")
    for edge in edges:
        plan.edge(*edge)
    return plan.graph()


def kinds(graph) -> list[str]:
    program = structure_diagram(graph)[0]
    return [type(stmt).__name__ for stmt in walk(program.body)]


def no_jumps(graph) -> bool:
    return not any(isinstance(stmt, Unstructured) for stmt in walk(structure_diagram(graph)[0].body))


# ------------------------------------------------------- Schleifen aus Verzweigungen
def test_branch_straight_back_to_loop_head_is_an_if(tmp_path):
    # Summe der geraden Zahlen 1..6: „nein“ führt direkt zurück zum Schleifenkopf
    graph = flow({"a": (P, "i = 0"), "b": (P, "g = 0"), "w": (D, "i < 6"), "c": (P, "i = i + 1"),
                  "d": (D, "i mod 2 = 0"), "f": (P, "g = g + i"), "o": (O, "g ausgeben")},
                 [("s", "a"), ("a", "b"), ("b", "w"), ("w", "c", "ja"), ("w", "o", "nein"), ("c", "d"),
                  ("d", "f", "ja"), ("d", "w", "nein"), ("f", "w"), ("o", "e")])
    assert kinds(graph).count("WhileLoop") == 1 and "If" in kinds(graph) and no_jumps(graph)
    three_way(graph, tmp_path, expected=["12"])


def test_nested_while_loops_with_direct_return(tmp_path):
    graph = flow({"a": (P, "i = 0"), "b": (P, "k = 0"), "w": (D, "i < 3"), "c": (P, "i = i + 1"), "j": (P, "j = 1"),
                  "v": (D, "j <= i"), "f": (P, "k = k + 1"), "g": (P, "j = j + 1"), "o": (O, "k ausgeben")},
                 [("s", "a"), ("a", "b"), ("b", "w"), ("w", "c", "ja"), ("w", "o", "nein"), ("c", "j"), ("j", "v"),
                  ("v", "f", "ja"), ("v", "w", "nein"), ("f", "g"), ("g", "v"), ("o", "e")])
    assert kinds(graph).count("WhileLoop") == 2 and no_jumps(graph)
    three_way(graph, tmp_path, expected=["6"])


def test_do_while_with_skip_to_the_test(tmp_path):
    graph = flow({"a": (P, "i = 0"), "b": (P, "g = 0"), "c": (P, "i = i + 1"), "d": (D, "i mod 2 = 0"),
                  "f": (P, "g = g + i"), "t": (D, "i < 6"), "o": (O, "g ausgeben")},
                 [("s", "a"), ("a", "b"), ("b", "c"), ("c", "d"), ("d", "f", "ja"), ("d", "t", "nein"), ("f", "t"),
                  ("t", "c", "ja"), ("t", "o", "nein"), ("o", "e")])
    assert "DoWhileLoop" in kinds(graph) and no_jumps(graph)
    three_way(graph, tmp_path, expected=["12"])


@pytest.mark.parametrize("answers, expected", [(["3", "4", "0"], ["7"]), (["0"], ["0"])])
def test_loop_with_the_test_in_the_middle(answers, expected, tmp_path):
    # Eingabe → Prüfung → Verarbeitung → zurück zur Eingabe
    graph = flow({"a": (P, "summe = 0"), "i": (I, "x einlesen"), "d": (D, "x = 0"), "p": (P, "summe = summe + x"),
                  "o": (O, "summe ausgeben")},
                 [("s", "a"), ("a", "i"), ("i", "d"), ("d", "o", "ja"), ("d", "p", "nein"), ("p", "i"), ("o", "e")])
    assert no_jumps(graph)
    three_way(graph, tmp_path, answers, expected=expected)


def test_input_validation_loop(tmp_path):
    graph = flow({"i": (I, "n einlesen"), "d": (D, "n > 0"), "f": (O, '"Fehler"'), "o": (O, "n ausgeben")},
                 [("s", "i"), ("i", "d"), ("d", "o", "ja"), ("d", "f", "nein"), ("f", "i"), ("o", "e")])
    assert no_jumps(graph)
    python = generate(structure_diagram(graph), "python")
    assert python.count('eingabe("n: ")') == 2  # vor der Schleife und am Ende des Rumpfs
    three_way(graph, tmp_path, ["-1", "0", "5"], expected=["Fehler", "Fehler", "5"])


def test_two_jumps_back_to_the_same_input(tmp_path):
    graph = flow({"a": (P, "summe = 0"), "i": (I, "x einlesen"), "d": (D, "x < 0"), "p": (P, "summe = summe + x"),
                  "t": (D, "summe < 10"), "o": (O, "summe ausgeben")},
                 [("s", "a"), ("a", "i"), ("i", "d"), ("d", "i", "ja"), ("d", "p", "nein"), ("p", "t"),
                  ("t", "i", "ja"), ("t", "o", "nein"), ("o", "e")])
    assert no_jumps(graph)
    three_way(graph, tmp_path, ["4", "-1", "5", "3"], expected=["12"])


def test_while_loop_left_from_the_middle(tmp_path):
    # zweiter Ausgang der Schleife: springt hinter die Schleife
    graph = flow({"a": (P, "i = 0"), "w": (D, "i < 10"), "c": (P, "i = i + 1"), "d": (D, "i * i > 20"),
                  "o": (O, "i ausgeben")},
                 [("s", "a"), ("a", "w"), ("w", "c", "ja"), ("w", "o", "nein"), ("c", "d"), ("d", "o", "ja"),
                  ("d", "w", "nein"), ("o", "e")])
    program = structure_diagram(graph)[0]
    assert any(isinstance(stmt, Break) for stmt in walk(program.body)) and no_jumps(graph)
    assert "break" in generate([program], "python") and "break;" in generate([program], "java")
    three_way(graph, tmp_path, expected=["5"])


@pytest.mark.parametrize("answers, expected", [(["1", "2", "0"], ["eins", "zwei"]), (["9"], [])])
def test_menu_loop(answers, expected, tmp_path):
    graph = flow({"i": (I, "wahl einlesen"), "d": (D, "wahl"), "a": (O, '"eins"'), "b": (O, '"zwei"')},
                 [("s", "i"), ("i", "d"), ("d", "a", "1"), ("d", "b", "2"), ("d", "e", "sonst"), ("a", "i"),
                  ("b", "i")])
    program = structure_diagram(graph)[0]
    found = [type(stmt) for stmt in walk(program.body)]
    assert Loop in found and Continue in found and Unstructured not in found
    three_way(graph, tmp_path, answers, expected=expected)


# ------------------------------------------------------------ Schleifenbegrenzung
def prime_test():
    return flow({"i": (I, "n einlesen"), "b": (LOOP_BEGIN, "Für t = 2 bis n - 1"), "d": (D, "n mod t = 0"),
                 "k": (O, '"keine Primzahl"'), "x": (LOOP_END, ""), "o": (O, '"Primzahl"')},
                [("s", "i"), ("i", "b"), ("b", "d"), ("d", "k", "ja"), ("d", "x", "nein"), ("k", "e"), ("x", "o"),
                 ("o", "e")])


@pytest.mark.parametrize("n, expected", [("7", "Primzahl"), ("9", "keine Primzahl"), ("2", "Primzahl")])
def test_early_end_inside_a_counting_loop(n, expected, tmp_path):
    loops = [stmt for stmt in walk(structure_diagram(prime_test())[0].body) if isinstance(stmt, LimitLoop)]
    assert loops and loops[0].end_id == "x"  # das Schleifenende geht nicht verloren
    three_way(prime_test(), tmp_path, [n], expected=[expected])


@pytest.mark.parametrize("answers, expected", [
    (["1", "1234"], ["falsche PIN", "Zugang erlaubt"]),
    (["1", "2", "3"], ["falsche PIN", "falsche PIN", "falsche PIN", "Karte gesperrt"]),
])
def test_pin_check_with_three_tries(answers, expected, tmp_path):
    graph = flow({"b": (LOOP_BEGIN, "wiederhole 3 mal"), "i": (I, "pin einlesen"), "d": (D, "pin = 1234"),
                  "ok": (O, '"Zugang erlaubt"'), "no": (O, '"falsche PIN"'), "x": (LOOP_END, ""),
                  "o": (O, '"Karte gesperrt"')},
                 [("s", "b"), ("b", "i"), ("i", "d"), ("d", "ok", "ja"), ("d", "no", "nein"), ("ok", "e"),
                  ("no", "x"), ("x", "o"), ("o", "e")])
    three_way(graph, tmp_path, answers, expected=expected)


def test_counting_loop_with_extra_condition_at_the_end(tmp_path):
    graph = linear((P, "s = 0"), (LOOP_BEGIN, "Für i = 1 bis 10"), (P, "s = s + i"), (LOOP_END, "bis s > 5"),
                   (O, "s ausgeben"), (O, "i ausgeben"))
    three_way(graph, tmp_path, expected=["6", "3"])


@pytest.mark.parametrize("footer, answers", [("bis fertig", ["n", "n", "j"]), ("bis Eingabe = 0", ["n", "j"]),
                                             ("solange antwort = ja", ["j", "j", "n"])])
def test_loop_end_that_cannot_be_evaluated_asks_everywhere(footer, answers, tmp_path):
    graph = linear((P, "k = 0"), (LOOP_BEGIN, "wiederhole"), (P, "k = k + 1"), (LOOP_END, footer), (O, "k ausgeben"))
    three_way(graph, tmp_path, answers, expected=[str(len(answers))])


def test_counting_loop_bounds_changed_in_the_body(tmp_path):
    graph = linear((P, "n = 3"), (P, "k = 0"), (LOOP_BEGIN, "Für i = 1 bis n"), (P, "n = n - 1"), (P, "k = k + 1"),
                   (LOOP_END, ""), (O, "k ausgeben"))
    three_way(graph, tmp_path)


# ---------------------------------------------------------------- Verzweigungen
def and_pattern():
    return flow({"i": (I, "x einlesen"), "a": (D, "x > 0"), "b": (D, "x < 100"), "g": (O, '"gültig"'),
                 "u": (O, '"ungültig"')},
                [("s", "i"), ("i", "a"), ("a", "b", "ja"), ("a", "u", "nein"), ("b", "g", "ja"), ("b", "u", "nein"),
                 ("g", "e"), ("u", "e")])


@pytest.mark.parametrize("x, expected", [("150", "ungültig"), ("50", "gültig"), ("-3", "ungültig")])
def test_box_shared_by_two_branches_is_repeated(x, expected, tmp_path):
    assert no_jumps(and_pattern())
    assert generate(structure_diagram(and_pattern()), "python").count('print("ungültig")') == 2
    three_way(and_pattern(), tmp_path, [x], expected=[expected])


def two_way(condition, yes_label, no_label, yes_first=True):
    edges = [("d", "y", yes_label), ("d", "n", no_label)]
    return flow({"i": (I, "x einlesen"), "d": (D, condition), "y": (O, '"JA"'), "n": (O, '"NEIN"')},
                [("s", "i"), ("i", "d"), *(edges if yes_first else reversed(edges)), ("y", "e"), ("n", "e")])


@pytest.mark.parametrize("yes_label, no_label", [("ja", "nein"), ("", "nein"), ("ja", ""), ("richtig", "falsch"),
                                                 ("+", "-"), ("w", "f"), ("stimmt", "stimmt nicht"), ("1", "0")])
@pytest.mark.parametrize("yes_first", [True, False])
def test_yes_no_labels(yes_label, no_label, yes_first, tmp_path):
    graph = two_way("x > 5", yes_label, no_label, yes_first)
    three_way(graph, tmp_path, ["7"], expected=["JA"])
    three_way(graph, tmp_path, ["3"], expected=["NEIN"])


def test_unlabelled_exits_first_is_yes_everywhere_with_hint(tmp_path):
    graph = two_way("x > 5", "", "")
    assert any("nicht mit ja/nein beschriftet" in warning for warning in structure_diagram(graph)[0].warnings)
    three_way(graph, tmp_path, ["7"], expected=["JA"])


@pytest.mark.parametrize("condition, first, second, x, expected", [
    ("x ?", "< 10", ">= 10", "20", "NEIN"),     # zweiter Ausgang
    ("x ?", "< 10", ">= 10", "5", "JA"),
    ("x", "1", "2", "2", "NEIN"),
    ("x", "= 0", "≠ 0", "7", "NEIN"),
    ("x mod 2", "1", "0", "7", "JA"),           # 1/0 als Paar: ja/nein
])
def test_two_exits_selected_by_value(condition, first, second, x, expected, tmp_path):
    three_way(two_way(condition, first, second), tmp_path, [x], expected=[expected])


@pytest.mark.parametrize("tag, expected", [("6", "Wochenende"), ("7", "Wochenende"), ("3", "Arbeitstag")])
def test_two_exits_to_the_same_box(tag, expected, tmp_path):
    graph = flow({"i": (I, "tag einlesen"), "d": (D, "tag"), "w": (O, '"Wochenende"'), "a": (O, '"Arbeitstag"')},
                 [("s", "i"), ("i", "d"), ("d", "w", "6"), ("d", "w", "7"), ("d", "a", "sonst"), ("w", "e"),
                  ("a", "e")])
    assert "tag == 6 or tag == 7" in generate(structure_diagram(graph), "python") and no_jumps(graph)
    three_way(graph, tmp_path, [tag], expected=[expected])


@pytest.mark.parametrize("label, x, expected", [("ja", "7", ["weiter"]), ("ja", "3", []), ("nein", "7", []),
                                                ("nein", "3", ["weiter"])])
def test_decision_with_only_one_exit(label, x, expected, tmp_path):
    graph = flow({"i": (I, "x einlesen"), "d": (D, "x > 5"), "o": (O, '"weiter"')},
                 [("s", "i"), ("i", "d"), ("d", "o", label), ("o", "e")])
    assert any("nur einen Ausgang" in warning for warning in structure_diagram(graph)[0].warnings)
    three_way(graph, tmp_path, [x], expected=expected)


def test_early_exit_to_the_shared_end(tmp_path):
    graph = flow({"i": (I, "x einlesen"), "a": (D, "x > 100"), "b": (D, "x > 0"), "p": (O, '"positiv"'),
                  "n": (O, '"nicht positiv"'), "w": (O, '"weiter"')},
                 [("s", "i"), ("i", "a"), ("a", "e", "ja"), ("a", "b", "nein"), ("b", "p", "ja"), ("b", "n", "nein"),
                  ("p", "w"), ("n", "w"), ("w", "e")])
    three_way(graph, tmp_path, ["-1"], expected=["nicht positiv", "weiter"])
    three_way(graph, tmp_path, ["500"], expected=[])


# ------------------------------------------------------------------ Sprünge
def test_jump_into_another_loop_body(tmp_path):
    # Sprung aus der ersten Schleife mitten in den Rumpf der zweiten: der Baustein wird wiederholt
    graph = flow({"a": (P, "i = 0"), "k": (P, "k = 0"), "w": (D, "i < 3"), "b": (P, "i = i + 1"), "v": (D, "i = 2"),
                  "x": (D, "k < 5"), "y": (P, "k = k + 1"), "o": (O, "k ausgeben")},
                 [("s", "a"), ("a", "k"), ("k", "w"), ("w", "b", "ja"), ("w", "x", "nein"), ("b", "v"),
                  ("v", "y", "ja"), ("v", "w", "nein"), ("x", "y", "ja"), ("x", "o", "nein"), ("y", "x"), ("o", "e")])
    for language in ("python", "java", "pseudo"):
        assert generate(structure_diagram(graph), language)
    three_way(graph, tmp_path, expected=["5"])


def test_lost_jump_stops_the_generated_program():
    from app.analysis.ast import Block, Program
    program = Program("Start", "s", None, "", Block([Unstructured("Sprung zu „x“", ["x"], fatal=True)]))
    assert "raise SystemExit" in generate([program], "python")
    assert "throw new IllegalStateException" in generate([program], "java")


def test_statement_kinds_exported():
    assert {DoWhileLoop, If, WhileLoop}  # Strukturbausteine bleiben importierbar


# ------------------------------------------------ mehrere Ausgänge, Schleifen in Schleifen
def test_two_exits_out_of_one_loop(tmp_path):
    # Zahlenraten mit höchstens 5 Versuchen: „richtig“ und „Abbruch mit 0“ verlassen beide die Schleife
    graph = flow({"g": (P, "geheim = 7"), "v": (P, "v = 0"), "w": (D, "v < 5"), "i": (I, "zahl einlesen"),
                  "c": (P, "v = v + 1"), "r": (D, "zahl = geheim"), "z": (D, "zahl = 0"), "m": (O, '"weiter"'),
                  "o": (O, "v ausgeben")},
                 [("s", "g"), ("g", "v"), ("v", "w"), ("w", "i", "ja"), ("w", "o", "nein"), ("i", "c"), ("c", "r"),
                  ("r", "o", "ja"), ("r", "z", "nein"), ("z", "o", "ja"), ("z", "m", "nein"), ("m", "w"), ("o", "e")])
    assert generate(structure_diagram(graph), "python").count("break") == 2 and no_jumps(graph)
    three_way(graph, tmp_path, ["3", "9", "7"], expected=["weiter", "weiter", "3"])
    three_way(graph, tmp_path, ["3", "0"], expected=["weiter", "2"])


def test_counting_loop_with_two_exits(tmp_path):
    graph = flow({"b": (LOOP_BEGIN, "Für i = 1 bis 10"), "a": (D, "i = 7"), "c": (D, "i * i > 20"), "p": (P, "z = i"),
                  "x": (LOOP_END, ""), "o": (O, "i ausgeben")},
                 [("s", "b"), ("b", "a"), ("a", "o", "ja"), ("a", "c", "nein"), ("c", "o", "ja"), ("c", "p", "nein"),
                  ("p", "x"), ("x", "o"), ("o", "e")])
    three_way(graph, tmp_path, expected=["5"])


def test_jump_from_inner_counting_loop_to_outer_loop_end(tmp_path):
    graph = flow({"l0": (LOOP_BEGIN, "Für i = 1 bis 3"), "l1": (LOOP_BEGIN, "Für j = 1 bis 3"), "d": (D, "j > i"),
                  "o": (O, "i * 10 + j ausgeben"), "x1": (LOOP_END, ""), "x0": (LOOP_END, ""), "f": (O, '"fertig"')},
                 [("s", "l0"), ("l0", "l1"), ("l1", "d"), ("d", "x0", "ja"), ("d", "o", "nein"), ("o", "x1"),
                  ("x1", "x0"), ("x0", "f"), ("f", "e")])
    loops = {stmt.begin_id: stmt.end_id for stmt in walk(structure_diagram(graph)[0].body)
             if isinstance(stmt, LimitLoop)}
    assert loops == {"l0": "x0", "l1": "x1"}  # jedes Schleifenende gehört zu genau einem Schleifenbeginn
    three_way(graph, tmp_path, expected=["11", "21", "22", "31", "32", "33", "fertig"])


def test_number_guessing_too_small_too_big(tmp_path):
    graph = flow({"g": (P, "geheim = 7"), "i": (I, "zahl einlesen"), "a": (D, "zahl < geheim"), "k": (O, '"zu klein"'),
                  "b": (D, "zahl > geheim"), "h": (O, '"zu groß"'), "r": (O, '"richtig"')},
                 [("s", "g"), ("g", "i"), ("i", "a"), ("a", "k", "ja"), ("a", "b", "nein"), ("k", "i"),
                  ("b", "h", "ja"), ("b", "r", "nein"), ("h", "i"), ("r", "e")])
    assert no_jumps(graph)
    three_way(graph, tmp_path, ["9", "3", "9", "3", "7"],
              expected=["zu groß", "zu klein", "zu groß", "zu klein", "richtig"])


def menu(inner_nodes: dict, inner_edges: list, around=None):
    """Menü „wahl“ mit 1 → innerer Teil, 2 → „zwei“, sonst → raus; ``around``: (Knoten, Kanten davor/danach)."""
    nodes = {"i": (I, "wahl einlesen"), "d": (D, "wahl"), "z": (O, '"zwei"'), **inner_nodes}
    edges = [("i", "d"), ("d", "z", "2"), ("z", "i"), *inner_edges]
    return nodes, edges


def test_menu_with_inner_while_loop(tmp_path):
    nodes, edges = menu({"k": (P, "k = 0"), "w": (D, "k < 2"), "c": (P, "k = k + 1"), "o": (O, "k ausgeben"),
                         "t": (O, '"Tschüss"')},
                        [("d", "k", "1"), ("k", "w"), ("w", "c", "ja"), ("c", "o"), ("o", "w"), ("w", "i", "nein"),
                         ("d", "t", "sonst"), ("t", "e")])
    graph = flow(nodes, [("s", "i"), *edges])
    assert no_jumps(graph)
    three_way(graph, tmp_path, ["1", "2", "1", "0"], expected=["1", "2", "zwei", "1", "2", "Tschüss"])


def test_menu_inside_a_branch_is_left_with_break(tmp_path):
    nodes, edges = menu({"a": (O, '"eins"'), "f": (O, '"fertig"')},
                        [("d", "a", "1"), ("a", "i"), ("d", "f", "sonst"), ("f", "e")])
    nodes = {"x": (I, "x einlesen"), "q": (D, "x > 0"), "n": (O, '"kein Menü"'), **nodes}
    graph = flow(nodes, [("s", "x"), ("x", "q"), ("q", "i", "ja"), ("q", "n", "nein"), ("n", "f"), *edges])
    assert no_jumps(graph)
    three_way(graph, tmp_path, ["1", "1", "2", "0"], expected=["eins", "zwei", "fertig"])
    three_way(graph, tmp_path, ["0"], expected=["kein Menü", "fertig"])


def test_menu_inside_a_counting_loop(tmp_path):
    nodes, edges = menu({"a": (O, '"eins"'), "b": (LOOP_BEGIN, "wiederhole 2 mal"), "x": (LOOP_END, ""),
                         "f": (O, '"fertig"')},
                        [("d", "a", "1"), ("a", "i"), ("d", "x", "sonst"), ("x", "f"), ("f", "e")])
    graph = flow(nodes, [("s", "b"), ("b", "i"), *edges])
    three_way(graph, tmp_path, ["1", "0", "2", "1", "0"], expected=["eins", "zwei", "eins", "fertig"])


def search_loop():
    return flow({"x": (I, "x einlesen"), "q": (D, "x > 0"), "n": (O, '"nix"'), "a": (P, "i = 0"), "w": (D, "i < 5"),
                 "c": (P, "i = i + 1"), "d": (D, "i = x"), "g": (O, '"gefunden"'), "m": (O, '"nicht gefunden"'),
                 "b": (O, '"Suche beendet"'), "f": (O, '"fertig"')},
                [("s", "x"), ("x", "q"), ("q", "a", "ja"), ("q", "n", "nein"), ("n", "f"), ("a", "w"),
                 ("w", "c", "ja"), ("w", "m", "nein"), ("c", "d"), ("d", "g", "ja"), ("d", "w", "nein"), ("g", "b"),
                 ("m", "b"), ("b", "f"), ("f", "e")])


@pytest.mark.parametrize("x, expected", [("9", ["nicht gefunden", "Suche beendet", "fertig"]),
                                         ("3", ["gefunden", "Suche beendet", "fertig"]), ("0", ["nix", "fertig"])])
def test_search_loop_with_found_and_not_found_exit(x, expected, tmp_path):
    assert no_jumps(search_loop())
    three_way(search_loop(), tmp_path, [x], expected=expected)


def test_jump_from_inner_loop_to_outer_loop_test(tmp_path):
    graph = flow({"a": (P, "i = 0"), "c": (P, "n = 0"), "w": (D, "i < 3"), "b": (P, "i = i + 1"), "j": (P, "j = 0"),
                  "v": (D, "j < 3"), "d": (D, "i * 10 + j = 21"), "p": (P, "j = j + 1"), "q": (P, "n = n + 1"),
                  "o": (O, "n ausgeben")},
                 [("s", "a"), ("a", "c"), ("c", "w"), ("w", "b", "ja"), ("w", "o", "nein"), ("b", "j"), ("j", "v"),
                  ("v", "d", "ja"), ("v", "w", "nein"), ("d", "w", "ja"), ("d", "q", "nein"), ("q", "p"), ("p", "v"),
                  ("o", "e")])
    three_way(graph, tmp_path, expected=["7"])


@pytest.mark.parametrize("header, footer", [("solange wahr", ""), ("solange 1 = 1", ""), ("wiederhole", "bis falsch")])
def test_endless_loop_left_only_by_end_compiles_in_java(header, footer, tmp_path):
    graph = flow({"b": (LOOP_BEGIN, header), "i": (I, "x einlesen"), "d": (D, "x = 0"), "q": (O, '"Schluss"'),
                  "o": (O, "x ausgeben"), "x": (LOOP_END, footer), "n": (O, '"nie erreicht"')},
                 [("s", "b"), ("b", "i"), ("i", "d"), ("d", "q", "ja"), ("d", "o", "nein"), ("q", "e"), ("o", "x"),
                  ("x", "n"), ("n", "e")])
    assert "nie erreicht." in generate(structure_diagram(graph), "java")  # Hinweis statt unerreichbarem Code
    three_way(graph, tmp_path, ["4", "0"], expected=["4", "Schluss"])


def test_dead_end_inside_a_loop_ends_the_program(tmp_path):
    graph = flow({"b": (LOOP_BEGIN, "Für i = 1 bis 3"), "d": (D, "i = 2"), "q": (O, '"Sackgasse"'),
                  "o": (O, "i ausgeben"), "x": (LOOP_END, ""), "f": (O, '"fertig"')},
                 [("s", "b"), ("b", "d"), ("d", "q", "ja"), ("d", "o", "nein"), ("o", "x"), ("x", "f"), ("f", "e")])
    three_way(graph, tmp_path, expected=["1", "Sackgasse"])


def test_many_menu_loops_in_a_row(tmp_path):
    nodes, edges, answers, expected = {}, [], [], []
    for k in range(9):
        nodes.update({f"i{k}": (I, "wahl einlesen"), f"d{k}": (D, "wahl"), f"o{k}": (O, f'"M{k}"')})
        edges += [(f"i{k}", f"d{k}"), (f"d{k}", f"o{k}", "1"), (f"o{k}", f"i{k}"),
                  (f"d{k}", f"i{k + 1}" if k < 8 else "e", "sonst")]
        answers += ["1", "1", "0"]
        expected += [f"M{k}", f"M{k}"]
    graph = flow(nodes, [("s", "i0"), *edges])
    assert no_jumps(graph)
    three_way(graph, tmp_path, answers, expected=expected)


def test_variable_first_used_inside_a_menu_loop_gets_a_start_value(tmp_path):
    graph = flow({"i": (I, "wahl einlesen"), "d": (D, "wahl"), "p": (P, "zaehler = zaehler + 1"),
                  "o": (O, "zaehler ausgeben")},
                 [("s", "i"), ("i", "d"), ("d", "p", "1"), ("p", "i"), ("d", "o", "2"), ("o", "i"),
                  ("d", "e", "sonst")])
    assert "zaehler = 0" in generate(structure_diagram(graph), "python")
    three_way(graph, tmp_path, ["1", "1", "2", "0"], expected=["2"])


@pytest.mark.parametrize("edges", [
    [("s", "a"), ("a", "b"), ("b", "p"), ("p", "b")],                           # Rückpfeil zum Schleifenbeginn
    [("s", "a"), ("a", "b"), ("b", "p"), ("p", "a")],                           # Rückpfeil vor den Schleifenbeginn
    [("s", "a"), ("a", "b"), ("b", "p"), ("p", "b"), ("x", "e")],               # Schleifenende nicht angeschlossen
])
def test_loop_begin_on_a_cycle_without_loop_end_does_not_hang(edges):
    import threading
    graph = flow({"a": (P, "k = 0"), "b": (LOOP_BEGIN, "solange k < 5"), "p": (P, "k = k + 1"), "x": (LOOP_END, "")},
                 edges)
    done = []
    worker = threading.Thread(target=lambda: done.append(structure_diagram(graph)), daemon=True)
    worker.start()
    worker.join(5)
    assert done, "Die Struktur-Analyse kommt nicht zurück"
    for language in ("python", "java", "pseudo"):
        assert generate(done[0], language)
