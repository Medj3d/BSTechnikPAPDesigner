"""Dreifach-Vergleich: Schreibtischtest, erzeugtes Python und erzeugtes Java
(übersetzt mit javac) müssen für denselben Plan dieselbe Ausgabe liefern.

Die Fälle stammen aus einer systematischen Prüfung der Code-Erzeugung mit
einem echten Java-Compiler. Ohne JDK wird nur Schreibtischtest gegen Python
verglichen.
"""

import builtins
import contextlib
import io
import re
import sys

import pytest

from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate
from app.model.element_types import LOOP_BEGIN, LOOP_END
from app.model.element_types import ElementType as T
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from tests.test_java_compile import JAVAC, java_run
from tests.test_review_fixes_3 import Plan, linear

P, I, O, U = T.PROCESS, T.INPUT, T.OUTPUT, T.SUBPROGRAM
NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?")
YES = ("j", "ja")


def normalize(lines) -> list[str]:
    """Zahlen vergleichbar machen: „6.0“ = „6“, „2,5“ = „2.5“, „3.1536E10“ = „31536000000“."""
    def number(match):
        value = float(match.group(0).replace(",", "."))
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else f"{value:.8g}"
    result = []
    for line in lines:
        for part in str(line).split("\n"):
            if part.strip():
                result.append(NUMBER.sub(number, part.strip()))
    return result


def run_simulator(graph: FlowGraph, answers) -> list[str]:
    simulator = Simulator(graph)
    answers = iter(answers)
    for _ in range(20000):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            # das erzeugte Programm fragt jede Variable einzeln ab
            simulator.provide_input({name: next(answers) for name in result.variables})
        elif result.needs == NEEDS_DECISION:
            simulator.provide_decision(str(next(answers)).lower() in YES)
        if simulator.finished:
            break
    assert simulator.finished
    return normalize(simulator.outputs)


def run_python(code: str, answers) -> list[str]:
    answers = iter(answers)
    original = builtins.input
    builtins.input = lambda _prompt="": str(next(answers))
    buffer = io.StringIO()
    lines = 0

    def brake(frame, event, arg):
        # eine Endlosschleife im erzeugten Programm soll den Testlauf nicht aufhängen
        nonlocal lines
        lines += 1
        if lines > 500_000:
            raise RuntimeError("Endlosschleife im erzeugten Python-Programm")
        return brake

    previous = sys.gettrace()
    try:
        with contextlib.redirect_stdout(buffer):
            sys.settrace(brake)
            try:
                exec(compile(code, "generated.py", "exec"), {"__name__": "__main__"})
            finally:
                sys.settrace(previous)
    finally:
        builtins.input = original
    return normalize(buffer.getvalue().splitlines())


def run_java(code: str, answers, tmp_path) -> list[str]:
    stdout = java_run(code, tmp_path, "".join(f"{answer}\n" for answer in answers))
    # Eingabeaufforderungen stehen ohne Zeilenumbruch vor der nächsten Ausgabe
    prompts = set()
    for function, text in re.findall(r'\b(eingabe|eingabeText|frage)\("((?:[^"\\]|\\.)*)"\)', code):
        text = text.replace('\\"', '"').replace("\\\\", "\\")
        prompts.add(text + " (j/n) " if function == "frage" else text)
    prompts = sorted(prompts, key=len, reverse=True)
    lines = []
    for line in stdout.splitlines():
        stripped = True
        while stripped:
            stripped = False
            for prompt in prompts:
                if prompt and line.startswith(prompt):
                    line, stripped = line[len(prompt):], True
                    break
        lines.append(line)
    return normalize(lines)


def three_way(graph: FlowGraph, tmp_path, answers=(), expected=None) -> list[str]:
    programs = structure_diagram(graph)
    simulated = run_simulator(graph, answers)
    python = run_python(generate(programs, "python"), answers)
    assert python == simulated, f"Python {python} != Schreibtischtest {simulated}"
    if JAVAC is not None:
        java = run_java(generate(programs, "java"), answers, tmp_path)
        assert java == simulated, f"Java {java} != Schreibtischtest {simulated}\n{generate(programs, 'java')}"
    if expected is not None:
        assert simulated == normalize(expected)
    return simulated


def decision(condition: str, *before, yes='"JA"', no='"NEIN"') -> FlowGraph:
    """Start → before… → Verzweigung → Ausgabe ja / Ausgabe nein → Ende."""
    plan = Plan()
    ids = [plan.node("s", T.START, "Start")]
    for index, (kind, text) in enumerate(before):
        ids.append(plan.node(f"b{index}", kind, text))
    ids.append(plan.node("d", T.DECISION, condition))
    plan.chain(*ids)
    plan.node("y", O, yes)
    plan.node("n", O, no, x=300)
    plan.node("e", T.END, "Ende")
    plan.edge("d", "y", "ja")
    plan.edge("d", "n", "nein")
    plan.edge("y", "e")
    plan.edge("n", "e")
    return plan.graph()


# ------------------------------------------------------------------ Rechnen
@pytest.mark.parametrize("steps, expected", [
    ([(P, "x = 7,36"), (P, "y = round(x * 10) / 10")], "7.4"),          # Runden auf eine Stelle
    ([(P, "preis = 12,3456"), (P, "y = round(preis * 100) / 100")], "12.35"),
    ([(P, "y = (1 + 2) / 2")], "1.5"),
    ([(P, "y = -7 / 2")], "-3.5"),
    ([(P, "y = 3 * 7 / 2")], "10.5"),
    ([(P, "x = 7"), (P, "y = int(x) / 2")], "3.5"),
    ([(P, "y = -7 // 2")], "-4"),
    ([(P, "y = 7 div 2")], "3"),
    ([(P, "y = abs(-7) / 2")], "3.5"),
    ([(P, "y = max(3, 5) / 2")], "2.5"),
    ([(P, "y = 365 * 24 * 3600 * 1000")], "31536000000"),               # kein int-Überlauf
    ([(P, "y = 3000000000")], "3000000000"),
    ([(P, "y = wurzel(16)")], "4"),
    ([(P, "y = sqrt(16) + 1")], "5"),
    ([(P, "y = ganzzahl(7 / 2)")], "3"),
    ([(P, "y = floor(7 / 2) + ceil(7 / 2)")], "7"),
    ([(P, "y = sin(0) + cos(0)")], "1"),
    ([(P, "r = 2"), (P, "y = round(pi * r ** 2, 2)")], "12.57"),
    ([(P, "pi = 3,14"), (P, "r = 2"), (P, "y = 2 * pi * r")], "12.56"),  # eigene Variable pi
    ([(P, "x = 7"), (P, "y = round(x / 3, 2)")], "2.33"),
    ([(P, "y = wurzel(6,25)")], "2.5"),                                  # Dezimalkomma in der Funktion
    ([(P, "y = abs(-2,5)")], "2.5"),
    ([(P, "x = 7"), (P, "y = x^2")], "49"),
    ([(P, "x = 2,5"), (P, "y = x²")], "6.25"),
    ([(P, "y = -7 mod 3")], "2"),
    ([(P, "y = 7 mod -3")], "-2"),
    ([(P, "x = 2,5"), (P, "y = round(x)")], "3"),                        # kaufmännisch
    ([(P, "y = round(0.5)")], "1"),
    ([(P, "y = round(-2.5)")], "-3"),
    ([(P, "y = 1 if 3 > 2 else 0")], "1"),
])
def test_arithmetic(steps, expected, tmp_path):
    three_way(linear(*steps, (O, "y ausgeben")), tmp_path, expected=[expected])


def test_unsupported_formula_becomes_todo_everywhere(tmp_path):
    graph = linear((P, "x = 7"), (P, "y = 2(x + 1)"), (O, '"fertig"'))
    assert "TODO" in generate(structure_diagram(graph), "python")
    three_way(graph, tmp_path, expected=["fertig"])


@pytest.mark.parametrize("loop, answers, expected", [
    ([(P, "x = 7"), (P, "k = 0"), (LOOP_BEGIN, "wiederhole x / 2 mal"), (P, "k = k + 1"), (LOOP_END, "")], [], "3"),
    ([(P, "k = 0"), (LOOP_BEGIN, "wiederhole 2,5 mal"), (P, "k = k + 1"), (LOOP_END, "")], [], "2"),
    ([(I, "n einlesen"), (P, "k = 0"), (LOOP_BEGIN, "wiederhole n mal"), (P, "k = k + 1"), (LOOP_END, "")],
     ["2,5"], "2"),
    # eigener Zähler namens „durchlauf“ darf nicht vom Schleifenzähler verdeckt werden
    ([(P, "k = 0"), (P, "durchlauf = 0"), (LOOP_BEGIN, "wiederhole 3 mal"), (P, "durchlauf = durchlauf + 1"),
      (P, "k = durchlauf"), (LOOP_END, "")], [], "3"),
    ([(I, "Anzahl einlesen"), (P, "k = 0"), (LOOP_BEGIN, "Für i = 1 bis Anzahl"), (P, "k = k + i"), (LOOP_END, "")],
     ["3"], "6"),
    ([(P, "k = 0"), (LOOP_BEGIN, "solange k < (2 + 3) / 2"), (P, "k = k + 0,5"), (LOOP_END, "")], [], "2.5"),
])
def test_loops(loop, answers, expected, tmp_path):
    three_way(linear(*loop, (O, "k ausgeben")), tmp_path, answers, expected=[expected])


# -------------------------------------------------------------- Bedingungen
@pytest.mark.parametrize("before, condition, answers, expected", [
    ([(P, "fertig = wahr")], "fertig ?", [], "JA"),
    ([(P, "fertig = Falsch")], "NICHT fertig", [], "JA"),
    ([(P, "gefunden = 0")], "NICHT gefunden", [], "JA"),
    ([(P, "x = 7")], "x mod 2", [], "JA"),                       # Zahl als Bedingung: ungleich 0
    ([(P, "x = 7"), (P, "ok = x > 5")], "ok", [], "JA"),
    ([(I, "x einlesen")], "x mod 2 = 1", ["-7"], "JA"),          # ungerade – auch bei negativen Zahlen
    ([(P, "x = 7")], "x^2 > 40", [], "JA"),
    ([(P, "x = 7")], "wurzel(x) > 2", [], "JA"),
    ([(P, "x = 7")], "x > 5 && x < 10", [], "JA"),
    ([(I, "antwort einlesen")], 'antwort = "ja"', ["ja"], "JA"),  # Eingabe bleibt Text
    ([(I, "antwort einlesen")], 'antwort ≠ "nein"', ["nein"], "NEIN"),
    ([(I, "antwort einlesen")], "antwort = ja", ["x", "j"], "JA"),  # „ja“ ist keine Variable → Rückfrage
    ([(P, "k = 1")], "Weiter?", ["n"], "NEIN"),                  # Freitext → Rückfrage
    ([(P, "x = 7")], "x > 5 | x < 10", ["j"], "JA"),             # nicht auswertbar → Rückfrage
    ([(P, 't = ""'), (P, 's = "Hal"'), (P, 't = s + "lo"'), (P, 'u = "Hallo"')], "t = u", [], "JA"),
    ([(P, 'name = "Anna"')], 'name < "Berta"', [], "JA"),
])
def test_conditions(before, condition, answers, expected, tmp_path):
    three_way(decision(condition, *before), tmp_path, answers, expected=[expected])


def test_flag_loop(tmp_path):
    graph = linear((P, "fertig = falsch"), (P, "i = 0"), (LOOP_BEGIN, "solange NICHT fertig"),
                   (P, "i = i + 1"), (P, "fertig = i ≥ 3"), (LOOP_END, ""), (O, "i ausgeben"))
    three_way(graph, tmp_path, expected=["3"])
    assert "static boolean fertig = false;" in generate(structure_diagram(graph), "java")


def test_repeat_question_loop(tmp_path):
    graph = linear((P, 'antwort = "j"'), (P, "k = 0"), (LOOP_BEGIN, 'solange antwort = "j"'), (P, "k = k + 1"),
                   (I, "antwort einlesen"), (LOOP_END, ""), (O, '"Durchläufe:" k'))
    three_way(graph, tmp_path, ["j", "n"], expected=["Durchläufe: 2"])


def test_multi_branch_with_text_labels(tmp_path):
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("p", P, 'farbe = "grün"'),
               plan.node("d", T.DECISION, "farbe"))
    plan.node("e", T.END, "Ende")
    for index, label in enumerate(["rot", "grün", "sonst"]):
        nid = plan.node(f"o{index}", O, f'"Ausgang {label}"', x=index * 200)
        plan.edge("d", nid, label)
        plan.edge(nid, "e")
    three_way(plan.graph(), tmp_path, expected=["Ausgang grün"])


# ------------------------------------------------------------- Ein-/Ausgabe
@pytest.mark.parametrize("steps, answers, expected", [
    ([(I, "name einlesen"), (O, '"Hallo" name')], ["Max"], ["Hallo Max"]),
    ([(I, "Eingabe: Name, Alter"), (O, '"Hallo" Name'), (O, '"Jahre:" Alter')], ["Max", "17"],
     ["Hallo Max", "Jahre: 17"]),
    ([(P, 'name = "Max"'), (P, 'gruss = name + "!"'), (O, "gruss ausgeben")], [], ["Max!"]),
    ([(P, 'a = "Max"'), (P, "b = a"), (O, "b ausgeben")], [], ["Max"]),
    ([(P, "x = 5"), (P, 's = str(x) + " Euro"'), (O, "s ausgeben")], [], ["5 Euro"]),
    ([(P, 's = "-" * 5'), (O, "s ausgeben")], [], ["-----"]),
    ([(P, "x = 3"), (P, "y = 4"), (O, "x und y ausgeben")], [], ["x und y: 3, 4"]),
    ([(P, "x = 3"), (P, "y = 4"), (O, "Ausgabe: x, y")], [], ["x, y: 3, 4"]),
    ([(P, "x = 3"), (P, "y = 4"), (O, "Ausgabe: x, y + 1")], [], ["3 5"]),
    ([(P, "summe = 6"), (P, "anzahl = 3"), (O, "Summe und Anzahl ausgeben")], [], ["Summe und Anzahl: 6, 3"]),
    ([(P, "ergebnis = 12"), (O, "Ergebnis ausgeben")], [], ["Ergebnis: 12"]),
    ([(P, "ergebnis = 12"), (O, "Ergebnis: ergebnis")], [], ["Ergebnis: 12"]),
    ([(I, "Zahl einlesen"), (P, "quadrat = Zahl * Zahl"), (O, "quadrat ausgeben")], ["4"], ["16"]),
    ([(I, "Gib eine Zahl ein"), (O, '"Doppelt:" Zahl * 2')], ["4"], ["Doppelt: 8"]),
    ([(I, "summe und anzahl einlesen"), (P, "mittel = summe / anzahl"), (O, "mittel ausgeben")], ["5", "2"],
     ["2.5"]),
    ([(I, '"Gib dein Alter ein:" alter'), (O, '"Alter:" alter')], ["17"], ["Alter: 17"]),
    ([(I, "„Wie alt bist du?“ alter"), (O, '"Alter:" alter')], ["17"], ["Alter: 17"]),
    ([(I, "Weiter (ja/nein)? antwort einlesen"), (O, '"Antwort:" antwort')], ["nein"], ["Antwort: nein"]),
    ([(O, '"Willkommen"\n"zum Rechner"')], [], ["Willkommen zum Rechner"]),
    ([(P, 's = "Zeile1\\nZeile2"'), (O, "s ausgeben")], [], ["Zeile1", "Zeile2"]),
    ([(P, "Datei c:\\users\\daten.txt öffnen"), (O, '"ok"')], [], ["ok"]),      # \u im Java-Kommentar
    ([(P, "eingabe = 0"), (I, "x einlesen"), (P, "eingabe = eingabe + x"), (O, "eingabe ausgeben")], ["5"], ["5"]),
    ([(P, 'frage = "Wie heißt du?"'), (O, "frage ausgeben")], [], ["Wie heißt du?"]),
    ([(P, "int = 3"), (P, "new = int + 1"), (O, "new ausgeben")], [], ["4"]),   # Java-Schlüsselwörter
])
def test_input_output(steps, answers, expected, tmp_path):
    three_way(linear(*steps), tmp_path, answers, expected=expected)


def test_backslash_u_in_program_name_and_loop_header(tmp_path):
    graph = linear((LOOP_BEGIN, "Für jede Datei in c:\\users"), (P, "k = 1"), (LOOP_END, ""), (O, '"ok"'),
                   name="C:\\users\\Rechner")
    three_way(graph, tmp_path, ["n"], expected=["ok"])


def test_helper_names_do_not_clash_with_variables(tmp_path):
    graph = decision("Ist alles klar?", (P, "frage = 7"), (P, "runden = round(2.5 + frage)"), yes="runden ausgeben")
    python = generate(structure_diagram(graph), "python")
    assert "def frage_(text):" in python and "def runden_(x, stellen=0):" in python
    three_way(graph, tmp_path, ["j"], expected=["10"])


def test_subprogram_call_with_arguments(tmp_path):
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("p", P, "n = 5"), plan.node("u", U, "verdoppeln(n)"),
               plan.node("v", U, "protokoll(n, 2)"), plan.node("o", O, "n ausgeben"), plan.node("e", T.END, "Ende"))
    plan.chain(plan.node("s2", T.START, "Verdoppeln", x=400), plan.node("q", P, "n = n * 2", x=400),
               plan.node("e2", T.END, "Ende", x=400))
    three_way(plan.graph(), tmp_path, expected=["10"])


def test_nameless_input_is_discarded_everywhere(tmp_path):
    three_way(decision("eingabe = 42", (I, "Eingabe")), tmp_path, ["42", "j"], expected=["JA"])


# ----------------------------------------------------------- Typ-Erkennung
def test_variable_types():
    from app.analysis.variables import Variables

    def types(*steps):
        info = Variables(structure_diagram(linear(*steps)))
        return info.types, info.dynamic

    # eine Kopie der Eingabe wird gerechnet → auch die Eingabe ist eine Zahl
    assert types((I, "a einlesen"), (P, "max = a"), (P, "max = max + 1"))[0] == {"a": "double", "max": "double"}
    # Eingabe ohne jeden Hinweis bleibt Text, ebenso ihre Kopie
    assert types((I, "name einlesen"), (P, "kopie = name"))[0] == {"name": "String", "kopie": "String"}
    # mit Text verglichen und trotzdem aufsummiert: Zahl oder Text, je nach Eingabe
    found, dynamic = types((P, "summe = 0"), (I, "x einlesen"), (LOOP_BEGIN, 'solange x != "ende"'),
                           (P, "summe = summe + x"), (I, "x einlesen"), (LOOP_END, ""))
    assert found == {"summe": "double", "x": "String"} and dynamic == {"x"}
    assert types((P, "fertig = falsch"), (P, "n = 3"), (P, 't = "a"'))[0] == \
        {"fertig": "boolean", "n": "double", "t": "String"}


@pytest.mark.parametrize("steps, answers, expected", [
    # Kopie einer Eingabe, mit der gerechnet wird
    ([(I, "a einlesen"), (I, "b einlesen"), (P, "summe = a"), (P, "summe = summe + b"), (O, "summe ausgeben")],
     ["3", "4"], ["7"]),
    ([(I, "a einlesen"), (I, "b einlesen"), (P, "erg = a"), (P, "erg = erg * b"), (O, "erg ausgeben")],
     ["3", "4"], ["12"]),
    # Text + Zahl wird verkettet
    ([(I, "alter einlesen"), (P, 'text = "Du bist " + alter + " Jahre alt"'), (O, "text ausgeben")], ["17"],
     ["Du bist 17 Jahre alt"]),
    ([(P, "n = 3"), (P, 'text = "Anzahl: " + n'), (O, "text ausgeben")], [], ["Anzahl: 3"]),
    # Zahlen als Text: ohne „.0“
    ([(P, "n = 12345"), (P, "stellen = len(str(n))"), (O, "stellen ausgeben")], [], ["5"]),
    ([(P, 's = ""'), (LOOP_BEGIN, "Für i = 1 bis 3"), (P, "s = s + str(i)"), (LOOP_END, ""), (O, "s ausgeben")],
     [], ["123"]),
    ([(P, 't = "42"'), (P, "z = int(t) + 1"), (O, "z ausgeben")], [], ["43"]),
    # Wahrheitswert in einer Rechnung zählt wie 1
    ([(P, "anzahl = 0"), (LOOP_BEGIN, "Für i = 1 bis 5"), (P, "anzahl = anzahl + (i > 2)"), (LOOP_END, ""),
      (O, "anzahl ausgeben")], [], ["3"]),
    # Text mal negative Anzahl ergibt leeren Text
    ([(I, "n einlesen"), (P, 'linie = "*" * (n - 5) + "!"'), (O, "linie ausgeben")], ["3"], ["!"]),
    # Summe bis zum Wort „ende“
    ([(P, "summe = 0"), (I, "x einlesen"), (LOOP_BEGIN, 'solange x != "ende"'), (P, "summe = summe + x"),
      (I, "x einlesen"), (LOOP_END, ""), (O, '"Summe:" summe')], ["5", "7", "ende"], ["Summe: 12"]),
    # vergessener Startwert: alle drei nehmen 0 an (der Schreibtischtest weist darauf hin)
    ([(LOOP_BEGIN, "Für i = 1 bis 3"), (P, "summe = summe + i"), (LOOP_END, ""), (O, "summe ausgeben")], [], ["6"]),
    # Leerzeichen am Rand eines Textes
    ([(P, "summe = 7"), (O, '"Summe: " summe')], [], ["Summe: 7"]),
    ([(P, "x = 7"), (O, '"Wert " x " Euro"')], [], ["Wert 7 Euro"]),
    # Eingabe für eine Zahl: Tippfehler werden erneut abgefragt (nur Python/Java fragen nach)
    ([(I, "x einlesen"), (P, "y = -x"), (O, '"Ergebnis:" y')], ["0"], ["Ergebnis: 0"]),
])
def test_types_in_all_three(steps, answers, expected, tmp_path):
    three_way(linear(*steps), tmp_path, answers, expected=expected)


@pytest.mark.parametrize("before, condition, answers, expected", [
    ([(I, "a einlesen"), (I, "b einlesen"), (P, "max = a")], "b > max", ["3", "7"], "JA"),
    ([(I, "x einlesen"), (I, "y einlesen"), (P, "s = x + 1")], "x = y", ["5", "5"], "JA"),
    ([(I, "pw einlesen")], "len(pw) < 8", ["12345678"], "NEIN"),      # Ziffern bleiben hier Text
    ([(I, "pin einlesen")], 'pin = "1234"', ["1234"], "JA"),
    ([(I, "fach einlesen")], 'fach = "Inf"', ["Inf"], "JA"),          # „Inf“ ist keine Zahl
    ([(P, "n = 5")], 'str(n) = "5"', [], "JA"),
])
def test_types_in_conditions(before, condition, answers, expected, tmp_path):
    three_way(decision(condition, *before), tmp_path, answers, expected=[expected])


def test_menu_with_numbers_and_letters(tmp_path):
    def menu():
        plan = Plan()
        plan.chain(plan.node("s", T.START, "Start"), plan.node("i", I, "wahl einlesen"),
                   plan.node("d", T.DECISION, "wahl"))
        plan.node("e", T.END, "Ende")
        for index, (label, text) in enumerate([("1", "eins"), ("2", "zwei"), ("q", "ende"), ("sonst", "anders")]):
            nid = plan.node(f"o{index}", O, f'"{text}"', x=index * 200)
            plan.edge("d", nid, label)
            plan.edge(nid, "e")
        return plan.graph()
    for answer, expected in (("1", "eins"), ("2", "zwei"), ("q", "ende"), ("x", "anders")):
        three_way(menu(), tmp_path, [answer], expected=[expected])


def test_variable_set_in_one_branch_only(tmp_path):
    plan = Plan()
    plan.chain(plan.node("s", T.START, "Start"), plan.node("i", I, "x einlesen"), plan.node("d", T.DECISION, "x > 0"))
    plan.node("p", P, 'art = "positiv"')
    plan.node("o", O, '"Art:" art')
    plan.node("e", T.END, "Ende")
    plan.edge("d", "p", "ja")
    plan.edge("d", "o", "nein")
    plan.edge("p", "o")
    plan.edge("o", "e")
    graph = plan.graph()
    assert 'art = ""' in generate(structure_diagram(graph), "python")   # Startwert wie in Java
    three_way(graph, tmp_path, ["-5"], expected=["Art:"])
    three_way(graph, tmp_path, ["5"], expected=["Art: positiv"])


def test_simulator_hints_at_missing_start_value():
    simulator = Simulator(linear((P, "summe = summe + 1"), (O, "summe ausgeben")))
    messages = []
    while not simulator.finished:
        messages.append(simulator.step().message)
    assert simulator.outputs == ["1"]
    assert any("hatte noch keinen Wert" in message for message in messages)


def test_simulator_asks_again_for_a_number():
    simulator = Simulator(linear((I, "x einlesen"), (O, "x * 2 ausgeben")))
    simulator.step()
    result = simulator.step()
    assert result.needs == NEEDS_INPUT
    retry = simulator.provide_input("abc")
    assert retry.needs == NEEDS_INPUT and "Zahl" in retry.message and simulator.pending is not None
    simulator.provide_input("2,5")
    while not simulator.finished:
        simulator.step()
    assert simulator.outputs == ["5"]
