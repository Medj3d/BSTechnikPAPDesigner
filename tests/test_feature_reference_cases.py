"""Referenzfälle: kleine, typische Programmablaufpläne laufen mit denselben Eingaben durch

* den Schreibtischtest (``app/simulation/engine.py``),
* das erzeugte Python (ausgeführt mit ersetztem ``input()``),
* das erzeugte Java (übersetzt mit ``javac`` und ausgeführt – nur wenn ein JDK da ist),
* den erzeugten PIC16F887-Assembler: Er muss für die Fälle mit ganzen Zahlen ohne ``TODO`` entstehen. Sind ``gpasm`` und
  ``gpsim`` (gputils) installiert – im Linux-Workflow der Fall –, laufen die Fälle ohne Eingabe zusätzlich im
  Simulator, und die Variablen müssen am Ende dieselben Werte haben (8 Bit: modulo 256). Mit der Umgebungsvariablen
  ``PAP_TEST_GPUTILS_PREFIX`` (z. B. ``wsl -e``) lassen sich gputils auch über einen Befehlsvorsatz aufrufen.
* Pseudocode muss nur entstehen.

Verglichen werden die Ausgaben und – wo es geht – die Werte der Variablen am Ende des Ablaufs.
"""

from __future__ import annotations

import builtins
import contextlib
import functools
import io
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

import pytest

from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import generate, java_name
from app.codegen.pic_asm import PicAsmGenerator
from app.model.element_types import LOOP_BEGIN, LOOP_END
from app.model.element_types import ElementType as T
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from tests.test_java_compile import JAVAC
from tests.test_review_fixes_3 import Plan
from tests.test_three_way import YES, normalize

P, I, O, U = T.PROCESS, T.INPUT, T.OUTPUT, T.SUBPROGRAM


# ------------------------------------------------------------------ Baukasten
class Flow:
    """Ablaufpläne aus verschachtelten Listen.

    Schritte: ``(Typ, Text)``, Schleifen als ``(LOOP_BEGIN, Kopf)`` … ``(LOOP_END, Fuß)``,
    ``("wenn", Bedingung, [ja…], [nein…])``, ``("solange", Bedingung, [Rumpf…])`` (Verzweigung mit Rücksprung,
    kopfgesteuert) und ``("wiederhole", [Rumpf…], Bedingung)`` (Verzweigung am Ende: „ja“ springt zurück).
    """

    def __init__(self):
        self.plan = Plan()
        self._count = 0

    def program(self, name: str, steps, end: str = "Ende", x: int = 0) -> "Flow":
        start = self._add(T.START, name, x)
        pending = self._sequence(steps, [(start, "")], x)
        self._connect(pending, self._add(T.END, end, x))
        return self

    def graph(self) -> FlowGraph:
        return self.plan.graph()

    def _add(self, kind, text: str, x: int) -> str:
        nid = f"n{self._count:03d}"
        self._count += 1
        if not isinstance(kind, T) and kind in (LOOP_BEGIN, LOOP_END):   # T.END ist gleich dem Text „end“
            self.plan.node(nid, T.LOOP, text, part=kind, x=x)
        else:
            self.plan.node(nid, kind, text, x=x)
        return nid

    def _connect(self, pending, target: str) -> None:
        for source, label in pending:
            self.plan.edge(source, target, label)

    def _sequence(self, steps, pending, x: int):
        for step in steps:
            if step[0] == "wenn":
                _, condition, then, otherwise = step
                decision = self._add(T.DECISION, condition, x)
                self._connect(pending, decision)
                pending = (self._sequence(then, [(decision, "ja")], x)
                           + self._sequence(otherwise, [(decision, "nein")], x + 300))
            elif step[0] == "solange":
                _, condition, body = step
                decision = self._add(T.DECISION, condition, x)
                self._connect(pending, decision)
                self._connect(self._sequence(body, [(decision, "ja")], x), decision)
                pending = [(decision, "nein")]
            elif step[0] == "wiederhole":
                _, body, condition = step
                marker = self._add(T.JUNCTION, "", x) if not body else None
                if marker:
                    self._connect(pending, marker)
                    pending = [(marker, "")]
                before = self._count
                pending = self._sequence(body, pending, x)
                head = marker or f"n{before:03d}"
                decision = self._add(T.DECISION, condition, x)
                self._connect(pending, decision)
                self.plan.edge(decision, head, "ja")
                pending = [(decision, "nein")]
            else:
                nid = self._add(step[0], step[1], x)
                self._connect(pending, nid)
                pending = [(nid, "")]
        return pending


def main(*steps, name: str = "Start") -> Flow:
    return Flow().program(name, list(steps))


def init(text: str):
    return P, text


# ------------------------------------------------------------------ Fälle
@dataclass
class Case:
    name: str
    flow: Flow
    answers: tuple = ()
    expected: tuple = ()
    # PIC: None (Text, Kommazahlen …), "generate" (muss ohne TODO entstehen), "run" (zusätzlich im Simulator)
    pic: str | None = None
    # Variablen, die nur der Schreibtischtest kennt bzw. die sich nicht vergleichen lassen
    skip_vars: frozenset = field(default_factory=frozenset)

    def __str__(self):
        return self.name


def _comparisons(a: int, b: int) -> Case:
    steps = [init(f"a = {a}"), init(f"b = {b}"), init("r = 0")]
    for weight, op in zip((1, 2, 4, 8, 16, 32), (">", "<", "≥", "≤", "=", "≠")):
        steps.append(("wenn", f"a {op} b", [(P, f"r = r + {weight}")], []))
    steps.append((O, "r ausgeben"))
    expected = sum(w for w, ok in zip((1, 2, 4, 8, 16, 32), (a > b, a < b, a >= b, a <= b, a == b, a != b)) if ok)
    return Case(f"vergleiche_{a}_{b}", main(*steps), expected=(str(expected),), pic="run")


def _subprogram_flow() -> Flow:
    flow = main(init("a = 3"), init("b = 4"), (U, "c := quadratsumme(a, b)"), (O, '"Summe der Quadrate:" c'),
                (U, "m := maximum(a, b)"), (O, '"Maximum:" m'),
                (LOOP_BEGIN, "Für i = 1 bis 4"), (U, "q := quadrat(i)"), (O, "q ausgeben"), (LOOP_END, ""))
    flow.program("int quadratsumme(int x, int y)", [(P, "return x * x + y * y")], x=500)
    flow.program("int maximum(int p, int k)", [("wenn", "p > k", [(P, "return p")], [(P, "return k")])], x=900)
    flow.program("int quadrat(int z)", [], end="return z * z", x=1300)
    return flow


def _boolean_function_flow() -> Flow:
    flow = main((I, "n einlesen"), (U, "ok := istGerade(n)"), (O, '"gerade:" ok'),
                ("wenn", "ok", [(O, '"durch 2 teilbar"')], [(O, '"Rest 1"')]))
    flow.program("bool istGerade(int zahl)", [(P, "return zahl mod 2 = 0")], x=500)
    return flow


def _procedure_flow() -> Flow:
    flow = main((I, "breite einlesen"), (U, "rahmen(breite)"), (U, "rahmen(breite + 2)"), (O, '"fertig"'))
    flow.program("rahmen(int n)", [(P, 'linie = "#" * n'), (O, "linie ausgeben")], x=500)
    return flow


CASES = [
    # Folge (Sequenz)
    Case("sequenz_rechnen",
         main((I, "a einlesen"), (I, "b einlesen"), (P, "summe = a + b"), (P, "differenz = a - b"),
              (P, "produkt = a * b"), (O, '"Summe:" summe'), (O, '"Differenz:" differenz'),
              (O, '"Produkt:" produkt')),
         ("7", "3"), ("Summe: 10", "Differenz: 4", "Produkt: 21"), pic="generate"),
    Case("sequenz_tauschen",
         main(init("a = 7"), init("b = 3"), (P, "h = a"), (P, "a = b"), (P, "b = h"), (O, "a ausgeben"),
              (O, "b ausgeben")),
         expected=("3", "7"), pic="run"),
    # Verzweigung (wenn – sonst)
    *[Case(f"verzweigung_noten_{points}",
           main((I, "punkte einlesen"),
                ("wenn", "punkte >= 90", [(O, '"sehr gut"')],
                 [("wenn", "punkte >= 50", [(O, '"bestanden"')], [(O, '"nicht bestanden"')])]),
                (O, '"Punkte:" punkte')),
           (str(points),), (text, f"Punkte: {points}"))
      for points, text in ((95, "sehr gut"), (90, "sehr gut"), (50, "bestanden"), (49, "nicht bestanden"))],
    Case("verzweigung_maximum",
         main(init("a = 9"), init("b = 14"), ("wenn", "a > b", [(P, "groesser = a")], [(P, "groesser = b")]),
              (O, "groesser ausgeben")),
         expected=("14",), pic="run"),
    # Kopfgesteuerte Schleife
    *[Case(f"kopfschleife_summe_{n}",
           main((I, "n einlesen"), init("s = 0"), init("i = 1"), (LOOP_BEGIN, "solange i <= n"), (P, "s = s + i"),
                (P, "i = i + 1"), (LOOP_END, ""), (O, '"Summe:" s')),
           (str(n),), (f"Summe: {n * (n + 1) // 2}",), pic="generate")
      for n in (5, 0)],
    Case("kopfschleife_zweierpotenz",
         main(init("p = 1"), init("k = 0"), (LOOP_BEGIN, "solange p < 100"), (P, "p = p * 2"), (P, "k = k + 1"),
              (LOOP_END, ""), (O, "k ausgeben")),
         expected=("7",), pic="run"),
    Case("kopfschleife_ggt_mit_verzweigung",
         main(init("a = 48"), init("b = 18"), ("solange", "b ≠ 0", [(P, "r = a mod b"), (P, "a = b"), (P, "b = r")]),
              (O, '"ggT:" a')),
         expected=("ggT: 6",), pic="run"),
    # Fußgesteuerte Schleife
    *[Case(f"fussschleife_verdoppeln_{start}",
           main((I, "start einlesen"), (P, "x = start"), (LOOP_BEGIN, ""), (P, "x = x * 2"), (LOOP_END, "bis x > 50"),
                (O, "x ausgeben")),
           (str(start),), (str(result),), pic="generate")
      for start, result in ((3, 96), (100, 200))],
    Case("fussschleife_quersumme",
         main(init("zahl = 247"), init("quersumme = 0"), (LOOP_BEGIN, ""), (P, "quersumme = quersumme + zahl mod 10"),
              (P, "zahl = zahl div 10"), (LOOP_END, "solange zahl > 0"), (O, '"Quersumme:" quersumme')),
         expected=("Quersumme: 13",), pic="run"),
    Case("fussschleife_eingabe_bis_positiv",
         main(init("versuche = 0"), (LOOP_BEGIN, ""), (I, "zahl einlesen"), (P, "versuche = versuche + 1"),
              (LOOP_END, "bis zahl > 0"), (O, '"Zahl:" zahl'), (O, '"Versuche:" versuche')),
         ("-3", "0", "4"), ("Zahl: 4", "Versuche: 3")),
    Case("fussschleife_eingabe_pruefen",
         main(("wiederhole", [(I, "zahl einlesen")], "zahl < 1 oder zahl > 10"), (O, '"Gültig:" zahl')),
         ("0", "11", "5"), ("Gültig: 5",), pic="generate"),
    # Zählschleife
    Case("zaehlschleife_fakultaet",
         main(init("fak = 1"), (LOOP_BEGIN, "Für i = 1 bis 5"), (P, "fak = fak * i"), (LOOP_END, ""),
              (O, "fak ausgeben"), (O, "i ausgeben")),
         expected=("120", "6"), pic="run"),
    Case("zaehlschleife_rueckwaerts",
         main((LOOP_BEGIN, "Für k = 10 bis 1 Schritt -3"), (O, "k ausgeben"), (LOOP_END, "")),
         expected=("10", "7", "4", "1"), pic="run"),
    Case("zaehlschleife_schritt_drei",
         main(init("s = 0"), (LOOP_BEGIN, "Für i = 2 bis 12 Schritt 3"), (P, "s = s + i"), (LOOP_END, ""),
              (O, "s ausgeben"), (O, "i ausgeben")),
         expected=("26", "14"), pic="run"),
    Case("zaehlschleife_n_mal",
         main(init("z = 0"), (LOOP_BEGIN, "wiederhole 3 mal"), (P, "z = z + 2"), (LOOP_END, ""), (O, "z ausgeben")),
         expected=("6",), pic="run"),
    Case("zaehlschleife_quadrate",
         main((I, "n einlesen"), (LOOP_BEGIN, "Für i = 1 bis n"), (O, "i * i ausgeben"), (LOOP_END, "")),
         ("4",), ("1", "4", "9", "16"), pic="generate"),
    # Verschachtelte Schleifen
    Case("verschachtelt_dreieck",
         main(init("z = 0"), (LOOP_BEGIN, "Für i = 1 bis 3"), (LOOP_BEGIN, "Für j = 1 bis i"), (P, "z = z + 1"),
              (LOOP_END, ""), (LOOP_END, ""), (O, "z ausgeben")),
         expected=("6",), pic="run"),
    Case("verschachtelt_einmaleins",
         main((LOOP_BEGIN, "Für i = 1 bis 3"), (LOOP_BEGIN, "Für j = 1 bis 3"), (O, "i * j ausgeben"), (LOOP_END, ""),
              (LOOP_END, "")),
         expected=("1", "2", "3", "2", "4", "6", "3", "6", "9"), pic="run"),
    Case("verschachtelt_solange_in_zaehlschleife",
         main(init("s = 0"), (LOOP_BEGIN, "Für i = 1 bis 3"), (P, "k = i"), (LOOP_BEGIN, "solange k > 0"),
              (P, "s = s + 1"), (P, "k = k - 1"), (LOOP_END, ""), (LOOP_END, ""), (O, "s ausgeben")),
         expected=("6",), pic="run"),
    # Unterprogramme mit Parametern und Rückgabewert
    Case("unterprogramm_rueckgabe", _subprogram_flow(),
         expected=("Summe der Quadrate: 25", "Maximum: 4", "1", "4", "9", "16"), pic="run"),
    Case("unterprogramm_mit_parameter", _procedure_flow(), ("3",), ("###", "#####", "fertig")),
    *[Case(f"unterprogramm_wahrheitswert_{n}", _boolean_function_flow(), (str(n),), expected)
      for n, expected in ((8, ("gerade: wahr", "durch 2 teilbar")), (7, ("gerade: falsch", "Rest 1")))],
    # Text
    Case("text_ausgabe",
         main((I, "name einlesen"), (P, 'gruss = "Hallo " + name + "!"'), (O, "gruss ausgeben"), (O, '"Name:" name'),
              (P, "n = len(name)"), (O, '"Länge:" n'), (P, 'linie = "=" * n'), (O, "linie ausgeben"),
              (P, 'info = name + " hat " + n + " Buchstaben"'), (O, "info ausgeben")),
         ("Anna",), ("Hallo Anna!", "Name: Anna", "Länge: 4", "====", "Anna hat 4 Buchstaben")),
    Case("text_vergleich",
         main((I, "wort einlesen"), ("wenn", 'wort = "Apfel"', [(O, '"gleich"')], [(O, '"anders"')]),
              ("wenn", 'wort < "Birne"', [(O, '"davor"')], [(O, '"danach"')])),
         ("Apfel",), ("gleich", "davor")),
    # Ganzzahlige Division und Rest
    Case("ganzzahl_div_mod",
         main(init("a = 17"), init("b = 5"), (P, "q = a div b"), (P, "r = a mod b"), (O, '"Quotient:" q'),
              (O, '"Rest:" r')),
         expected=("Quotient: 3", "Rest: 2"), pic="run"),
    *[Case(f"ganzzahl_negativ_{x}",
           main((I, "x einlesen"), (P, "q = x div 4"), (P, "r = x mod 4"), (P, "g = x // 4"), (P, "t = ganzzahl(x / 4)"),
                (P, "d = x / 4"), (O, "q ausgeben"), (O, "r ausgeben"), (O, "g ausgeben"), (O, "t ausgeben"),
                (O, "d ausgeben")),
           (str(x),), expected)
      for x, expected in ((17, ("4", "1", "4", "4", "4.25")), (-17, ("-5", "3", "-5", "-4", "-4.25")))],
    # Vergleiche
    _comparisons(7, 5), _comparisons(5, 5), _comparisons(3, 8),
    Case("vergleich_als_wert",
         main(init("a = 7"), init("b = 5"), (P, "groesser = a > b"), (P, "gleich = (a == b)"), (O, "groesser ausgeben"),
              (O, "gleich ausgeben"), (P, 'text = "Ergebnis: " + str(groesser)'), (O, "text ausgeben")),
         expected=("wahr", "falsch", "Ergebnis: wahr")),
    # und / oder / nicht
    *[Case(f"logik_alter_{age}",
           main((I, "alter einlesen"), (P, "kind = alter < 14"), (P, "senior = alter >= 65"),
                ("wenn", "kind oder senior", [(O, '"ermäßigt"')], [(O, '"voller Preis"')]),
                ("wenn", "alter >= 14 und alter < 18", [(O, '"Jugendlich"')], []),
                ("wenn", "NICHT (alter = 30)", [], [(O, '"genau 30"')]),
                ("wenn", "alter > 20 && alter < 40", [(O, '"zwischen 20 und 40"')], []),
                ("wenn", "alter < 5 || alter > 60", [(O, '"sehr jung oder älter"')], [])),
           (str(age),), expected)
      for age, expected in ((10, ("ermäßigt",)), (15, ("voller Preis", "Jugendlich")),
                            (30, ("voller Preis", "genau 30", "zwischen 20 und 40")),
                            (70, ("ermäßigt", "sehr jung oder älter")))],
    *[Case(f"logik_eingabe_wahrheitswert_{answer}",
           main((I, "alter einlesen"), (I, "mitglied einlesen"),
                ("wenn", "alter < 18 und mitglied", [(O, '"Jugendrabatt"')], [(O, '"kein Rabatt"')]),
                (O, '"Mitglied:" mitglied')),
           ("15", answer), expected)
      for answer, expected in (("j", ("Jugendrabatt", "Mitglied: wahr")), ("n", ("kein Rabatt", "Mitglied: falsch")))],
    Case("logik_zahlen",
         main(init("a = 7"), init("b = 5"), init("r = 0"),
              ("wenn", "a > 3 und b < 6", [(P, "r = r + 1")], []),
              ("wenn", "a < 3 oder b = 5", [(P, "r = r + 2")], []),
              ("wenn", "nicht (a = 7)", [(P, "r = r + 4")], []),
              ("wenn", "a > 3 und b > 9", [(P, "r = r + 8")], []),
              ("wenn", "a < 3 oder b > 9", [(P, "r = r + 16")], []),
              (O, "r ausgeben")),
         expected=("3",), pic="run"),
    # Eingaben
    *[Case(f"eingabe_zwei_werte_{index}",
           main((I, "Eingabe: breite, hoehe"), (P, "flaeche = breite * hoehe"), (O, '"Fläche:" flaeche')),
           answers, expected)
      for index, (answers, expected) in enumerate(((("4", "2,5"), ("Fläche: 10",)), (("3", "7"), ("Fläche: 21",))))],
    Case("eingabe_text_und_zahl",
         main((I, "name einlesen"), (I, "alter einlesen"), (P, "naechstes = alter + 1"),
              (O, '"Hallo" name'), (O, '"Nächstes Jahr:" naechstes')),
         ("Max", "16"), ("Hallo Max", "Nächstes Jahr: 17")),
    Case("eingabe_kommazahl",
         main((I, "preis einlesen"), (P, "brutto = preis * 1,19"), (P, "brutto = round(brutto, 2)"), (O, '"Brutto:" brutto')),
         ("10",), ("Brutto: 11.9",)),
    Case("eingabe_mittelwert",
         main((I, "n einlesen"), init("summe = 0"), (LOOP_BEGIN, "Für i = 1 bis n"), (I, "x einlesen"),
              (P, "summe = summe + x"), (LOOP_END, ""), (P, "mittel = summe / n"), (O, '"Mittelwert:" mittel')),
         ("3", "4", "5", "9"), ("Mittelwert: 6",), pic="generate"),
]
BY_NAME = {case.name: case for case in CASES}
assert len(BY_NAME) == len(CASES), "doppelte Namen"


# ------------------------------------------------------------------ Ausführen
def _comparable(value):
    """Werte vergleichbar machen: Wahrheitswerte bleiben, Zahlen als float, Text bleibt."""
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return None


@functools.lru_cache(maxsize=None)
def simulated(name: str) -> tuple[list[str], dict]:
    case = BY_NAME[name]
    simulator = Simulator(case.flow.graph())
    answers = iter(case.answers)
    for _ in range(20000):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input({variable: next(answers) for variable in result.variables})
        elif result.needs == NEEDS_DECISION:
            simulator.provide_decision(str(next(answers)).lower() in YES)
        if simulator.finished:
            break
    assert simulator.finished, f"{name}: der Schreibtischtest endet nicht"
    assert next(answers, None) is None, f"{name}: nicht alle Eingaben verbraucht"
    return normalize(simulator.outputs), dict(simulator.variables)


def programs(name: str):
    return structure_diagram(BY_NAME[name].flow.graph())


def run_python(code: str, answers) -> tuple[list[str], dict]:
    """Führt das erzeugte Python aus; Ergebnis: Ausgaben und Variablen (global und aus ``main``)."""
    answers = iter(answers)
    original = builtins.input
    builtins.input = lambda _prompt="": str(next(answers))
    namespace = {"__name__": "__main__"}
    local_values = {}
    buffer = io.StringIO()
    lines = 0

    def tracer(frame, event, arg):
        nonlocal lines
        lines += 1
        if lines > 500_000:
            raise RuntimeError("Endlosschleife im erzeugten Python-Programm")
        if event == "return" and frame.f_code.co_name == "main" and frame.f_globals is namespace:
            local_values.update(frame.f_locals)
        return tracer

    previous = sys.gettrace()
    try:
        with contextlib.redirect_stdout(buffer):
            sys.settrace(tracer)
            try:
                exec(compile(code, "generated.py", "exec"), namespace)
            finally:
                sys.settrace(previous)
    finally:
        builtins.input = original
    values = {key: value for key, value in {**namespace, **local_values}.items()
              if not key.startswith("__") and _comparable(value) is not None}
    return normalize(buffer.getvalue().splitlines()), values


CHECKER = """
public class Pruefer {
    public static void main(String[] args) throws Exception {
        Class<?> programm = Class.forName("%s");
        programm.getMethod("main", String[].class).invoke(null, (Object) new String[0]);
        System.out.println();
        System.out.println("@@VARIABLEN@@");
        for (java.lang.reflect.Field feld : programm.getDeclaredFields()) {
            if (!java.lang.reflect.Modifier.isStatic(feld.getModifiers()) || feld.getName().equals("SCANNER")) {
                continue;
            }
            feld.setAccessible(true);
            System.out.println(feld.getName() + "=" + feld.get(null));
        }
    }
}
"""


def run_java(code: str, answers, tmp_path) -> tuple[list[str], dict]:
    """Übersetzt das erzeugte Java, führt es aus und liest danach alle statischen Variablen (Reflexion)."""
    class_name = re.search(r"public class (\w+)", code).group(1)
    (tmp_path / f"{class_name}.java").write_text(code, encoding="utf-8")
    (tmp_path / "Pruefer.java").write_text(CHECKER % class_name, encoding="utf-8")
    compiled = subprocess.run([JAVAC, "-encoding", "UTF-8", "-Xlint:none", f"{class_name}.java", "Pruefer.java"],
                              cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert compiled.returncode == 0, f"javac:\n{compiled.stderr}\n--- Code ---\n{code}"
    java = os.path.join(os.path.dirname(JAVAC), "java")
    ran = subprocess.run([java, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-cp", str(tmp_path), "Pruefer"],
                         input="".join(f"{answer}\n" for answer in answers), capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert ran.returncode == 0, f"java:\n{ran.stderr}\n--- Code ---\n{code}"
    stdout, _, dump = ran.stdout.replace("\r\n", "\n").partition("\n@@VARIABLEN@@\n")
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
    values = {}
    for row in dump.splitlines():
        key, _, text = row.partition("=")
        values[key] = text
    return normalize(lines), values


def same_value(expected, actual) -> bool:
    expected = _comparable(expected)
    if isinstance(actual, str) and not isinstance(expected, str):
        # Java liefert Text: „true“, „17.0“
        if isinstance(expected, bool):
            return actual == ("true" if expected else "false")
        try:
            actual = float(actual)
        except ValueError:
            return False
    actual = _comparable(actual)
    if isinstance(expected, bool) or isinstance(actual, bool):
        return isinstance(expected, bool) and isinstance(actual, bool) and expected == actual
    if isinstance(expected, float) and isinstance(actual, float):
        return math.isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-9)
    return expected == actual


def compare_variables(case: Case, expected: dict, actual: dict, rename=lambda name: name, where="") -> None:
    checked = 0
    for name, value in expected.items():
        if name in case.skip_vars:
            continue
        key = rename(name)
        assert key in actual, f"{case}: {where} kennt die Variable „{name}“ nicht ({sorted(actual)})"
        assert same_value(value, actual[key]), f"{case}: {where} {name} = {actual[key]!r}, Schreibtischtest {value!r}"
        checked += 1
    assert checked or not expected


# ------------------------------------------------------------------ Tests
@pytest.mark.parametrize("case", CASES, ids=str)
def test_desk_check_gives_the_expected_outputs(case):
    outputs, _ = simulated(case.name)
    assert outputs == normalize(case.expected)


@pytest.mark.parametrize("case", CASES, ids=str)
def test_python_matches_the_desk_check(case):
    outputs, variables = simulated(case.name)
    code = generate(programs(case.name), "python")
    assert "TODO" not in code.split("\n", 3)[-1], code
    python_outputs, python_variables = run_python(code, case.answers)
    assert python_outputs == outputs, f"Python {python_outputs} != Schreibtischtest {outputs}\n{code}"
    compare_variables(case, variables, python_variables, where="Python")


@pytest.mark.skipif(JAVAC is None, reason="kein JDK (javac) im PATH oder unter JAVA_HOME – Java-Vergleich übersprungen")
@pytest.mark.parametrize("case", CASES, ids=str)
def test_java_matches_the_desk_check(case, tmp_path):
    outputs, variables = simulated(case.name)
    code = generate(programs(case.name), "java")
    java_outputs, java_variables = run_java(code, case.answers, tmp_path)
    assert java_outputs == outputs, f"Java {java_outputs} != Schreibtischtest {outputs}\n{code}"
    compare_variables(case, variables, java_variables, rename=java_name, where="Java")


@pytest.mark.parametrize("case", CASES, ids=str)
def test_pseudocode_is_generated(case):
    code = generate(programs(case.name), "pseudo")
    assert code.startswith("PROGRAMM") and "TODO" not in code, code
    for program in programs(case.name):
        assert " ".join(program.name.split()) in code, (program.name, code)


# ------------------------------------------------------------------ PIC
def gputils_prefix() -> list[str] | None:
    """Befehlsvorsatz für gpasm/gpsim: leer, wenn sie im PATH liegen; aus ``PAP_TEST_GPUTILS_PREFIX`` (z. B.
    „wsl -e“); sonst ``None``."""
    if shutil.which("gpasm") and shutil.which("gpsim"):
        return []
    prefix = os.environ.get("PAP_TEST_GPUTILS_PREFIX", "").strip()
    return shlex.split(prefix) if prefix else None


PIC_CASES = [case for case in CASES if case.pic]


@pytest.mark.parametrize("case", PIC_CASES, ids=str)
def test_pic_assembler_is_generated_without_todo(case):
    code = generate(programs(case.name), "asm")
    todo = [line for line in code.splitlines() if re.search(r";\s*TODO", line)]
    assert not todo, f"{case}: {todo}\n{code}"


@pytest.mark.skipif(gputils_prefix() is None, reason="gputils/gpsim nicht installiert – PIC-Lauf übersprungen")
@pytest.mark.parametrize("case", [case for case in PIC_CASES if case.pic == "run"], ids=str)
def test_pic_assembler_runs_like_the_desk_check(case, tmp_path):
    outputs, variables = simulated(case.name)
    prefix = gputils_prefix()
    generator = PicAsmGenerator(programs(case.name))
    code = generator.generate()
    (tmp_path / "prog.asm").write_text(code, encoding="cp1252")
    (tmp_path / "prog.stc").write_text("break e ende\nrun\ndump\nquit\n")
    assembled = subprocess.run(prefix + ["gpasm", "-o", "prog.hex", "prog.asm"], cwd=tmp_path, capture_output=True,
                               text=True, timeout=120)
    assert assembled.returncode == 0 and "Error" not in assembled.stdout, assembled.stdout
    result = subprocess.run(prefix + ["gpsim", "-i", "-s", "prog.cod", "-c", "prog.stc"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    assert "Hit a Breakpoint" in output, output[-2000:]
    memory = {}
    for row in re.finditer(r"^([0-9a-f]{4}):\s+((?:[0-9a-f-]{2} ){16})", output, re.MULTILINE):
        for offset, cell in enumerate(row.group(2).split()):
            if cell != "--":
                memory[int(row.group(1), 16) + offset] = int(cell, 16)
    block = code.split("cblock\t0x20")[1].split("endc")[0].split()
    expected = {name: int(value) % 256 for name, value in variables.items()
                if name not in case.skip_vars and not isinstance(value, (bool, str)) and float(value).is_integer()}
    assert expected
    for name, want in expected.items():
        address = 0x20 + block.index(generator.var(name))
        assert memory.get(address) == want, (case.name, name, memory.get(address), want)
    # die letzte Ausgabe steht an PORTD
    last = re.findall(r"-?\d+", outputs[-1])
    assert memory.get(0x08) == int(last[-1]) % 256, (case.name, memory.get(0x08), outputs[-1])


# ------------------------------------------------------------------ Korrekturen, die die Fälle gefunden haben
def test_truth_values_are_printed_as_wahr_and_falsch():
    graph = main(init("a = 7"), (P, "ok = a > 5"), (O, "ok ausgeben"), (O, '"Ergebnis:" ok'),
                 (P, 's = "ok: " + str(ok)'), (O, "s ausgeben")).graph()
    python = generate(structure_diagram(graph), "python")
    assert 'print("wahr" if ok else "falsch")' in python and "'wahr' if ok else 'falsch'" in python
    java = generate(structure_diagram(graph), "java")
    assert "System.out.println(text(ok));" in java and 'return x ? "wahr" : "falsch";' in java
    assert "String.valueOf(ok)" not in java


def test_single_equals_in_a_return_is_a_comparison():
    from app.analysis import text as TX
    assert TX.return_statement("return zahl mod 2 = 0") == "zahl % 2 == 0"
    assert TX.return_statement("Rückgabe: a ≠ b") == "a != b"
    assert TX.return_statement("return n * 2") == "n * 2"


def test_input_used_as_a_condition_is_a_yes_no_question():
    from app.analysis.variables import Variables

    def types(*steps):
        return Variables(structure_diagram(main(*steps).graph())).types

    assert types((I, "mitglied einlesen"), ("wenn", "mitglied", [(O, '"ja"')], []))["mitglied"] == "boolean"
    assert types((I, "a einlesen"), (I, "m einlesen"),
                 ("wenn", "a < 18 und m", [(O, '"ja"')], []))["m"] == "boolean"
    assert types((I, "fertig einlesen"), (LOOP_BEGIN, "solange nicht fertig"), (I, "fertig einlesen"),
                 (LOOP_END, ""))["fertig"] == "boolean"
    # andere Hinweise gehen vor: verglichen mit Text bleibt Text, gerechnet wird eine Zahl
    assert types((I, "w einlesen"), ("wenn", 'w = "ja" oder w', [(O, '"x"')], []))["w"] == "String"
    assert types((I, "x einlesen"), ("wenn", "x mod 2", [(O, '"x"')], []))["x"] == "double"


def test_pic_counting_loop_counts_once_more_after_the_last_pass():
    code = generate(programs("zaehlschleife_fakultaet"), "asm")
    lines = [line.strip() for line in code.splitlines()]
    final = lines.index(next(line for line in lines if line.startswith("letzterschritt_")))
    assert lines[final + 1] == "INCF\ti, F" and lines[final + 2].startswith("endeschleife_")
