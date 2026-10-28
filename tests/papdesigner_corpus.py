"""Komplexe Programmablaufpläne im Dateiformat des PapDesigners 2.2 – so, wie das Original sie schreibt.

Jeder Plan entsteht zufällig, aber reproduzierbar aus einer Nummer (``seed``): verschachtelte und mehrfache
Verzweigungen (mit Verbindungspunkten zusammengeführt, „ja“ mal nach unten, mal zur Seite), Schleifen mit
Kopf- und Fußbedingung, Zähl- und „n mal“-Schleifen, Schleifen aus einer Verzweigung mit Pfeil zurück,
vorzeitiges Ende, Unterprogramme auf eigenen Diagrammen (mit Parametern, Rückgabetyp und Zuweisung im Aufruf,
Namen mit Leerzeichen), Aufrufe fremder Module, Kommentare, Sonderzeichen, „~“ und mehrzeilige Texte.

Zu jedem Plan gehört, was er bei bestimmten Eingaben ausgeben muss: Der Generator führt den Ablauf selbst
in Python aus (``Project.expected_outputs``). So prüft der Test nicht nur, dass sich die Datei öffnen lässt,
sondern dass der Plan genau so verstanden wird, wie er gemeint ist.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

GUID = "2FB25471-B62C-4EE6-BD43-F819C095ACF8"
# Beschriftungen der Ausgänge einer Verzweigung, wie sie in echten Dateien vorkommen
LABELS = [("ja", "nein"), ("yes", "no"), ("true", "false"), ("Ja", "Nein"), ("wahr", "falsch"), ("j", "n"),
          ("Y", "N")]
INPUT_VARIABLES = ["a", "b", "c", "d"]
WORK_VARIABLES = ["x", "y", "z", "s", "p", "q"]
MAX_STEPS = 200_000


# ------------------------------------------------------------------ Bausteine des Ablaufs
@dataclass
class Expr:
    """Ein Ausdruck, einmal als Python, einmal als Text im Plan."""
    py: str
    pap: str


@dataclass
class Act:
    assignments: list           # [(Ziel, Expr)]


@dataclass
class Inp:
    var: str
    text: str


@dataclass
class Out:
    label: str                  # erwartete Ausgabe: label + Wert
    expr: Expr | None
    text: str


@dataclass
class If:
    cond: Expr
    then: list
    other: list | None
    yes_down: bool = True


@dataclass
class Loop:
    kind: str                   # while, repeat_until, repeat_while, for, times
    head: str                   # Text im Schleifenbeginn
    foot: str                   # Text im Schleifenende
    body: list
    cond: Expr | None = None    # while/until-Bedingung
    var: str = ""
    start: int = 0
    end: int = 0


@dataclass
class DLoop:
    """Schleife aus Verbindungspunkt, Verzweigung und Pfeil zurück."""
    cond: Expr                  # solange diese Bedingung gilt, läuft der Körper
    body: list
    exit_on_yes: bool = False   # die Verzweigung fragt nach der Abbruchbedingung


@dataclass
class Call:
    routine: "Routine | None"   # None: fremdes Modul ohne eigenes Diagramm
    text: str


@dataclass
class Stop:
    """Ausgabe und sofort zum Ende des Ablaufs (Hauptprogramm: Programmende, Unterprogramm: zurück)."""
    out: Out


@dataclass
class Note:
    text: str


@dataclass
class Prose:
    """Nicht auswertbarer Text (wie in vielen echten Plänen) – ändert keine Variable."""
    subtype: str
    text: str


@dataclass
class Routine:
    name: str                   # Name des Diagramms (Titel)
    label: str                  # Name, unter dem es aufgerufen wird
    body: list = field(default_factory=list)
    start_text: str = "Start"
    end_text: str = "Ende"
    title_column: int = 0
    params: list = field(default_factory=list)


@dataclass
class Project:
    seed: int
    name: str
    author: str
    yes: str
    no: str
    routines: list              # [0] = Hauptprogramm
    inputs: list

    @property
    def expected_outputs(self) -> list[str]:
        return Interpreter(self).run()

    def to_xml(self) -> str:
        return Writer(self).xml()


# ------------------------------------------------------------------ Erzeugen
class Generator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.seed = seed
        self.counters = 0

    # -------------------------------------------------- Texte
    def pick(self, *options):
        return self.rng.choice(options)

    def value(self, variables) -> Expr:
        if self.rng.random() < 0.3:
            k = str(self.rng.randint(1, 9))
            return Expr(k, k)
        v = self.rng.choice(variables)
        return Expr(v, v)

    def expression(self, variables) -> Expr:
        v = self.rng.choice(variables)
        w = self.rng.choice(variables)
        k = self.rng.randint(1, 9)
        m = self.rng.randint(2, 7)
        choice = self.rng.randrange(9)
        if choice == 0:
            return Expr(f"{v} + {k}", f"{v} + {k}")
        if choice == 1:
            return Expr(f"{v} * {k}", self.pick(f"{v} * {k}", f"{v} · {k}", f"{v} × {k}"))
        if choice == 2:
            return Expr(f"{v} - {w}", f"{v} - {w}")
        if choice == 3:
            return Expr(f"({v} + {w}) % {m}", self.pick(f"({v} + {w}) mod {m}", f"({v} + {w}) MOD {m}"))
        if choice == 4:
            return Expr(f"{v} // {m}", f"{v} div {m}")
        if choice == 5:
            return Expr(f"abs({v} - {w})", f"abs({v} - {w})")
        if choice == 6:
            return Expr(f"max({v}, {w})", f"max({v}, {w})")
        if choice == 7:
            return Expr(f"min({v}, {k})", f"min({v}, {k})")
        return Expr(f"{v} + {w} * {k}", f"{v} + {w} * {k}")

    def comparison(self, variables) -> Expr:
        v = self.rng.choice(variables)
        k = self.rng.randint(0, 12)
        op = self.rng.choice(["<", ">", "<=", ">=", "==", "!=", "even"])
        if op == "even":
            m = self.rng.randint(2, 4)
            return Expr(f"{v} % {m} == 0", self.pick(f"{v} mod {m} = 0", f"{v} mod {m} == 0"))
        pap_op = {"<=": self.pick("<=", "≤"), ">=": self.pick(">=", "≥"), "==": self.pick("=", "=="),
                  "!=": self.pick("!=", "≠", "<>")}.get(op, op)
        return Expr(f"{v} {op} {k}", f"{v} {pap_op} {k}")

    def condition(self, variables) -> Expr:
        first = self.comparison(variables)
        if self.rng.random() < 0.25:
            second = self.comparison(variables)
            py_op, pap_op = self.pick(("and", self.pick("und", "and", "&&")), ("or", self.pick("oder", "or", "||")))
            return Expr(f"({first.py}) {py_op} ({second.py})", f"{first.pap} {pap_op} {second.pap}")
        return first

    def output(self, variables, label: str | None = None) -> Out:
        var = self.rng.choice(variables)
        label = label or self.pick(f"{var} =", "Ergebnis:", f"Wert von {var}:", "→")
        expr = Expr(var, var)
        text = self.pick(f'"{label}" {var}', f'„{label}“ {var}', f'Ausgabe "{label}" {var}',
                         f'Ausgabe von "{label}" {var}')
        return Out(label, expr, text)

    def message(self, text: str) -> Out:
        return Out(text, None, self.pick(f'"{text}"', f'„{text}“', f'Ausgabe "{text}"'))

    def counter(self) -> str:
        self.counters += 1
        return f"i{self.counters}"

    # -------------------------------------------------- Abläufe
    def block(self, variables, depth: int, routines, size: int | None = None) -> list:
        size = size if size is not None else self.rng.randint(2, 5)
        statements = []
        for _ in range(size):
            statements.extend(self.statement(variables, depth, routines))
        return statements

    def statement(self, variables, depth: int, routines) -> list:
        r = self.rng.random()
        if depth >= 4 or r < 0.25:
            return [self.simple(variables, routines)]
        kind = self.rng.choice(["if", "if", "if_chain", "while", "repeat", "for", "times", "dloop", "call",
                                "stop", "note"])
        if kind == "if":
            other = self.block(variables, depth + 1, routines, self.rng.randint(1, 3)) \
                if self.rng.random() < 0.7 else None
            return [If(self.condition(variables), self.block(variables, depth + 1, routines, self.rng.randint(1, 3)),
                       other, self.rng.random() < 0.7)]
        if kind == "if_chain":
            # mehrfache Verzweigung: wenn … sonst wenn … sonst …
            count = self.rng.randint(2, 4)
            tail = self.block(variables, depth + 2, routines, 1)
            for _ in range(count):
                tail = [If(self.comparison(variables), self.block(variables, depth + 2, routines, 1), tail,
                           self.rng.random() < 0.5)]
            return tail
        if kind in ("while", "repeat", "dloop"):
            i = self.counter()
            limit = self.rng.randint(1, 4)
            body = self.block(variables, depth + 1, routines, self.rng.randint(1, 3))
            body.append(Act([(i, Expr(f"{i} + 1", f"{i} + 1"))]))
            init = Act([(i, Expr("0", "0"))])
            if kind == "while":
                cond = Expr(f"{i} < {limit}", self.pick(f"{i} < {limit}", f"{i} <= {limit - 1}"))
                head = self.pick(f"solange {cond.pap}", f"while {cond.pap}", f"Solange {cond.pap}")
                return [init, Loop("while", head, self.pick("", "", "Schleifenende"), body, cond)]
            if kind == "repeat":
                if self.rng.random() < 0.6:
                    cond = Expr(f"{i} >= {limit}", self.pick(f"{i} >= {limit}", f"{i} ≥ {limit}"))
                    foot = self.pick(f"bis {cond.pap}", f"until {cond.pap}", f"Bis {cond.pap}")
                    return [init, Loop("repeat_until", self.pick("wiederhole", "repeat", "Wiederhole", ""), foot,
                                       body, cond)]
                cond = Expr(f"{i} < {limit}", f"{i} < {limit}")
                foot = self.pick(f"solange {cond.pap}", f"while ({cond.pap})")
                return [init, Loop("repeat_while", self.pick("wiederhole", "do", ""), foot, body, cond)]
            exit_on_yes = self.rng.random() < 0.5
            cond = Expr(f"{i} < {limit}", f"{i} < {limit}")
            return [init, DLoop(cond if not exit_on_yes else Expr(f"{i} >= {limit}", f"{i} >= {limit}"), body,
                                exit_on_yes)]
        if kind == "for":
            var = self.counter()
            start, end = self.rng.randint(0, 2), self.rng.randint(2, 4)
            head = self.pick(f"für {var} = {start} bis {end}", f"for {var} = {start} to {end}",
                             f"Für {var} von {start} bis {end}", f"zähle {var} von {start} bis {end}")
            body = self.block(variables, depth + 1, routines, self.rng.randint(1, 3))
            return [Loop("for", head, self.pick("", f"nächstes {var}", f"next {var}"), body, var=var, start=start,
                         end=end)]
        if kind == "times":
            n = self.rng.randint(1, 3)
            body = self.block(variables, depth + 1, routines, self.rng.randint(1, 2))
            return [Loop("times", self.pick(f"{n} mal", f"wiederhole {n}-mal", f"{n}-mal"), "", body, end=n)]
        if kind == "call" and routines:
            return [self.call(self.rng.choice(routines))]
        if kind == "stop":
            out = self.message(self.pick("Abbruch", "Fehler: Wert zu groß", "fertig <früh>", "Stop & Ende"))
            v = self.rng.choice(variables)
            k = self.rng.choice([self.rng.randint(5, 12), self.rng.randint(40, 200), self.rng.randint(40, 200)])
            cond = Expr(f"{v} > {k}", f"{v} > {k}")
            return [If(cond, [Stop(out)], None, self.rng.random() < 0.5)]
        if kind == "note":
            return [Note(self.pick("Hinweis: Hier wird gerechnet.", "TODO: später optimieren\n(siehe Seite 2)",
                                   "Achtung: x < 0 & y > 0 möglich", "Mehrzeiliger\nKommentar\nmit „Zeichen“ <>",
                                   "Ab~lauf~steuerung")),
                    self.simple(variables, routines)]
        return [self.simple(variables, routines)]

    def simple(self, variables, routines):
        r = self.rng.random()
        if r < 0.45:
            target = self.rng.choice(WORK_VARIABLES)
            assignments = [(target, self.expression(variables))]
            if self.rng.random() < 0.2:
                second = self.rng.choice(WORK_VARIABLES)
                assignments.append((second, self.expression(variables)))
            return Act(assignments)
        if r < 0.7:
            return self.output(variables)
        if r < 0.8 and routines:
            return self.call(self.rng.choice(routines))
        if r < 0.85:
            return Call(None, self.pick("Bibliothek initialisieren", "LED_blinken()", "log.schreiben(x)"))
        if r < 0.92:
            return Prose("PapActivity", self.pick("Daten sichern", "Puffer leeren", "Anzeige aktualisieren",
                                                  "Zeitstempel merken"))
        # ein Kommentar steht immer neben einem Baustein (sonst entstünde ein leerer Zweig)
        return Prose("PapActivity", self.pick("Wert merken", "Siehe Spezifikation 3.2", "Ergebnis~speicher füllen"))

    def call(self, routine: Routine) -> Call:
        label = routine.label
        if routine.params:
            args = ", ".join(self.rng.choice(INPUT_VARIABLES + WORK_VARIABLES) for _ in routine.params)
            target = self.rng.choice(WORK_VARIABLES)
            text = self.pick(f"{label}({args})", f"{target} := {label}({args})", f"int {target} = {label}({args})",
                             f"{label} ({args})")
        else:
            text = self.pick(label, label, f"{label}()") if " " not in label else label
        return Call(routine, text)

    def routine_name(self, index: int) -> Routine:
        style = self.rng.randrange(5)
        base = self.pick("berechne", "pruefe", "zaehle", "verarbeite", "summiere", "teste", "rechne", "mische")
        base = f"{base}{index}"
        if style == 0:
            routine = Routine(base, base)
        elif style == 1:
            params = [self.pick("int", "float", "") for _ in range(self.rng.randint(1, 3))]
            names = ["n", "m", "k"][:len(params)]
            signature = ", ".join(f"{t} {n}".strip() for t, n in zip(params, names))
            routine = Routine(f"{self.pick('int', 'void', 'bool', 'double')} {base}({signature})", base)
            routine.params = names
        elif style == 2:
            words = self.pick("Werte prüfen", "Summe bilden", "Daten aufbereiten", "Ergebnis melden")
            routine = Routine(f"{words} {index}", f"{words} {index}")
        elif style == 3:
            routine = Routine(f"{base}(a, b)", base)
            routine.params = ["a", "b"]
        else:
            routine = Routine(f"{base}()", base)
        routine.start_text = self.pick("Start", "Start", "Start", routine.label)
        routine.end_text = self.pick("Ende", "End", "Ende", "Return")
        return routine

    def project(self) -> Project:
        rng = self.rng
        yes, no = rng.choice(LABELS)
        count = rng.choice([0, 1, 2, 3, 4, 5, 8, 12]) if self.seed % 7 else rng.randint(10, 14)
        variables = INPUT_VARIABLES + WORK_VARIABLES
        routines: list[Routine] = []
        for index in range(count, 0, -1):
            routine = self.routine_name(index)
            # Unterprogramme rufen nur später angelegte auf: keine Rekursion
            routine.body = self.block(variables, 2, routines[:], rng.randint(2, 4))
            routine.title_column = rng.choice([0, 0, 1])
            routines.append(routine)
        routines.reverse()
        main = Routine(self.pick("Hauptprogramm", "main()", "PAP-Test", "Steuerung"), "")
        main.title_column = rng.choice([0, 0, 1, 2])
        inputs = INPUT_VARIABLES[:rng.randint(1, 4)]
        prelude = [Inp(v, self.pick(f"{v} einlesen", f"Eingabe {v}", f"Eingabe von {v}", f"Zahl {v} einlesen",
                                    f"Wert {v} eingeben", f"read {v}")) for v in inputs]
        unread = [v for v in INPUT_VARIABLES if v not in inputs]
        init = [Act([(v, Expr(str(k), str(k))) for v in unread + WORK_VARIABLES for k in [rng.randint(0, 5)]])]
        body = self.block(variables, 0, routines, rng.randint(5, 10))
        main.body = prelude + init + body + [self.output(variables, "Schluss:")]
        name = f"Korpus {self.seed:03d}"
        values = [str(rng.randint(0, 12)) for _ in inputs]
        return Project(self.seed, name, self.pick("BS Technik", "Testlauf", "Ä. Öztürk"), yes, no,
                       [main] + routines, values)


def generate(seed: int) -> Project:
    return Generator(seed).project()


# ------------------------------------------------------------------ selbst ausführen
class _Stop(Exception):
    pass


class Interpreter:
    def __init__(self, project: Project):
        self.project = project
        self.env: dict = {}
        self.outputs: list[str] = []
        self.inputs = iter(project.inputs)
        self.steps = 0

    def run(self) -> list[str]:
        try:
            self.block(self.project.routines[0].body)
        except _Stop:
            pass
        return self.outputs

    def eval(self, expr: Expr):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise RuntimeError("Plan läuft zu lange")
        return eval(expr.py, {"__builtins__": {}, "abs": abs, "max": max, "min": min}, self.env)

    def block(self, statements):
        for statement in statements:
            self.statement(statement)

    def emit(self, out: Out):
        text = out.label if out.expr is None else f"{out.label} {self.eval(out.expr)}"
        self.outputs.append(" ".join(text.split()))

    def statement(self, s):
        if isinstance(s, Act):
            for target, expr in s.assignments:
                self.env[target] = self.eval(expr)
        elif isinstance(s, Inp):
            self.env[s.var] = int(next(self.inputs))
        elif isinstance(s, Out):
            self.emit(s)
        elif isinstance(s, If):
            branch = s.then if self.eval(s.cond) else (s.other or [])
            self.block(branch)
        elif isinstance(s, Loop):
            self.loop(s)
        elif isinstance(s, DLoop):
            while bool(self.eval(s.cond)) != s.exit_on_yes:
                self.block(s.body)
        elif isinstance(s, Call):
            if s.routine is not None:
                try:
                    self.block(s.routine.body)
                except _Stop:
                    pass
        elif isinstance(s, Stop):
            self.emit(s.out)
            raise _Stop()

    def loop(self, s: Loop):
        if s.kind == "while":
            while self.eval(s.cond):
                self.block(s.body)
        elif s.kind == "repeat_until":
            while True:
                self.block(s.body)
                if self.eval(s.cond):
                    break
        elif s.kind == "repeat_while":
            while True:
                self.block(s.body)
                if not self.eval(s.cond):
                    break
        elif s.kind == "for":
            for value in range(s.start, s.end + 1):
                self.env[s.var] = value
                self.block(s.body)
        elif s.kind == "times":
            for _ in range(s.end):
                self.block(s.body)


# ------------------------------------------------------------------ als .pap schreiben
@dataclass
class _Figure:
    id: int
    subtype: str
    column: int
    row: int
    text: str
    associate: int | None = None


class _Diagram:
    def __init__(self, project: Project, routine: Routine, rng: random.Random):
        self.project = project
        self.routine = routine
        self.rng = rng
        self.figures: list[_Figure] = []
        self.connections: list[tuple[int, int, int, str]] = []
        self.next_id = 0
        self.to_end: list[tuple[int, str]] = []
        self.notes: list[tuple[int, str]] = []

    def new_id(self) -> int:
        number = self.next_id
        self.next_id += 1
        return number

    def figure(self, subtype: str, column: int, row: int, text: str = "") -> _Figure:
        figure = _Figure(self.new_id(), subtype, column, row, text)
        self.figures.append(figure)
        return figure

    def connect(self, exits, target: int) -> None:
        for source, label in exits:
            self.connections.append((self.new_id(), source, target, label))

    def build(self) -> None:
        title = self.figure("PapTitle", self.routine.title_column, 0, self.routine.name)
        start = self.figure("PapStart", 0, 1, self.routine.start_text)
        end = _Figure(self.new_id(), "PapEnd", 0, 0, self.routine.end_text)  # Zeile folgt
        entry, exits, _width, height = self.sequence(self.routine.body, 0, 2)
        if entry is None:
            self.connect([(start.id, "")], end.id)
        else:
            self.connect([(start.id, "")], entry)
            self.connect(exits, end.id)
        self.connect(self.to_end, end.id)
        end.row = 2 + height
        self.figures.append(end)
        del title
        # Kommentare in einer eigenen Spalte rechts daneben
        column = max(f.column for f in self.figures) + 1
        used = set()
        for row, text in self.notes:
            while row in used:
                row += 1
            used.add(row)
            self.figure("PapComment", column, row, text)
        self.orthogonalize()

    def orthogonalize(self) -> None:
        """Wie der PapDesigner selbst: jede Verbindung waagerecht oder senkrecht, jede Ecke ein Verbindungspunkt.

        (Schräge Ausgänge einer Verzweigung nimmt das Original gar nicht an, andere zeichnet es schief.)
        """
        cells = {f.id: (f.column, f.row) for f in self.figures}
        subtype = {f.id: f.subtype for f in self.figures}
        taken = set(cells.values())
        straight = []
        for number, source, target, label in self.connections:
            (cs, rs), (ct, rt) = cells[source], cells[target]
            decision = subtype[source] == "PapCondition"
            if (cs == ct or rs == rt) and not (decision and rt < rs):
                straight.append((number, source, target, label))
                continue
            options = [(ct, rs), (cs, rt)]
            corner = next((cell for cell in options if cell not in taken and not (decision and cell[1] < rs)), None)
            if corner is not None:
                path = [corner]
            else:  # zwei Ecken in einer freien Spalte rechts von allem
                lane = max(column for column, _row in taken) + 1
                path = [(lane, rs), (lane, rt)]
            hops = [source]
            for cell in path:
                hub = self.figure("PapConnector", *cell)
                taken.add(cell)
                hops.append(hub.id)
            hops.append(target)
            for index, (start, end) in enumerate(zip(hops, hops[1:])):
                straight.append((number if index == 0 else self.new_id(), start, end, label if index == 0 else ""))
        self.connections = straight

    # -------------------------------------------------- Anordnung im Raster (wie der PapDesigner)
    def sequence(self, statements, column: int, row: int):
        entry, exits, width, height = None, [], 1, 0
        for statement in statements:
            if isinstance(statement, Note):
                self.notes.append((row + height, statement.text))
                continue
            first, out, w, h = self.layout(statement, column, row + height)
            if entry is None:
                entry = first
            else:
                self.connect(exits, first)
            exits = out
            width = max(width, w)
            height += h
            if not exits:  # vorzeitiges Ende: Was folgt, wäre nie erreichbar
                break
        return entry, exits, width, height

    def layout(self, s, column: int, row: int):
        p = self.project
        if isinstance(s, Act):
            f = self.figure("PapActivity", column, row, "\n".join(_assign_text(self.rng, t, e)
                                                                   for t, e in s.assignments))
            return f.id, [(f.id, "")], 1, 1
        if isinstance(s, Inp):
            f = self.figure("PapInput", column, row, s.text)
            return f.id, [(f.id, "")], 1, 1
        if isinstance(s, Out):
            f = self.figure("PapOutput", column, row, s.text)
            return f.id, [(f.id, "")], 1, 1
        if isinstance(s, Prose):
            f = self.figure(s.subtype, column, row, s.text)
            return f.id, [(f.id, "")], 1, 1
        if isinstance(s, Call):
            f = self.figure("PapModule", column, row, s.text)
            return f.id, [(f.id, "")], 1, 1
        if isinstance(s, Stop):
            f = self.figure("PapOutput", column, row, s.out.text)
            self.to_end.append((f.id, ""))
            return f.id, [], 1, 1
        if isinstance(s, If):
            decision = self.figure("PapCondition", column, row, _question_text(self.rng, s.cond))
            yes_label, no_label = p.yes, p.no
            down, side = (s.then, s.other) if s.yes_down else (s.other, s.then)
            down_label, side_label = (yes_label, no_label) if s.yes_down else (no_label, yes_label)
            exits = []
            entry, out, down_width, down_height = self.sequence(down or [], column, row + 1)
            if entry is not None:
                self.connect([(decision.id, down_label)], entry)
                exits += out
            else:  # leerer Zweig (oder nur Kommentare): direkt zum Verbindungspunkt
                exits.append((decision.id, down_label))
            entry, out, side_width, side_height = self.sequence(side or [], column + down_width, row + 1)
            if entry is not None:
                self.connect([(decision.id, side_label)], entry)
                exits += out
            else:
                exits.append((decision.id, side_label))
                side_width = 0
            height = 1 + max(down_height, side_height)
            if not exits:
                return decision.id, [], down_width + side_width, height
            join = self.figure("PapConnector", column, row + height)
            self.connect(exits, join.id)
            return decision.id, [(join.id, "")], max(1, down_width + side_width), height + 1
        if isinstance(s, Loop):
            begin = self.figure("PapLoopStart", column, row, s.head)
            entry, out, width, height = self.sequence(s.body, column, row + 1)
            finish = self.figure("PapLoopEnd", column, row + 1 + height, s.foot)
            begin.associate, finish.associate = finish.id, begin.id
            if entry is None:  # Körper nur aus Kommentaren
                out = [(begin.id, "")]
            else:
                self.connect([(begin.id, "")], entry)
            self.connect(out, finish.id)
            return begin.id, [(finish.id, "")], width, height + 2
        if isinstance(s, DLoop):
            join = self.figure("PapConnector", column, row)
            decision = self.figure("PapCondition", column, row + 1, _question_text(self.rng, s.cond))
            body_label, exit_label = (p.no, p.yes) if s.exit_on_yes else (p.yes, p.no)
            entry, out, width, height = self.sequence(s.body, column, row + 2)
            self.connect([(join.id, "")], decision.id)
            self.connect([(decision.id, body_label)], entry)
            self.connect(out, join.id)
            return join.id, [(decision.id, exit_label)], width, height + 2
        raise TypeError(s)

    def xml(self, index: int) -> list[str]:
        routine = self.routine
        figures = sorted(self.figures, key=lambda f: (f.column, f.row))
        columns = max(f.column for f in figures) + 1
        rows = max(f.row for f in figures) + 1
        stamp = "2026.10.28 10:00:00"
        out = [f'      <DIAGRAM FORMAT="1.00" ID="{index}" NAME={quoteattr(routine.name)} CREATED="{stamp}" '
               f'MODIFIED="{stamp}">',
               f'        <LAYOUT FORMAT="1.00" COLUMNS="{columns}" ROWS="{rows}">',
               "          <ENTRIES>"]
        for f in figures:
            anchor = ' ANCHOR="True"' if f.subtype == "PapTitle" else ""
            associate = f' ASSOCIATE="{f.associate}"' if f.associate is not None else ""
            out += [f'            <ENTRY COLUMN="{f.column}" ROW="{f.row}"{anchor}>',
                    f'              <FIGURE SUBTYPE="{f.subtype}" FORMAT="1.00" ID="{f.id}"{associate}>',
                    f"                <TEXT><![CDATA[{f.text}]]></TEXT>",
                    "              </FIGURE>",
                    "            </ENTRY>"]
        out += ["          </ENTRIES>", "        </LAYOUT>", "        <CONNECTIONS>"]
        connections = list(self.connections)
        self.rng.shuffle(connections)  # wie im Original: in der Reihenfolge des Zeichnens, nicht des Ablaufs
        for number, source, target, label in connections:
            out.append(f'          <CONNECTION FORMAT="1.00" ID="{number}" FROM="{source}" TO="{target}" '
                       f'TEXT={quoteattr(label)} />')
        out += ["        </CONNECTIONS>", "      </DIAGRAM>"]
        return out


def _assign_text(rng: random.Random, target: str, expr: Expr) -> str:
    return f"{target}{rng.choice([' = ', ' := ', ' ← ', ' = '])}{expr.pap}"


def _question_text(rng: random.Random, cond: Expr) -> str:
    return cond.pap + rng.choice(["", "?", " ?", ""])



class Writer:
    def __init__(self, project: Project):
        self.project = project

    def diagrams(self) -> list[_Diagram]:
        rng = random.Random(self.project.seed * 7919 + 1)
        built = []
        for routine in self.project.routines:
            diagram = _Diagram(self.project, routine, rng)
            diagram.build()
            built.append(diagram)
        return built

    def xml(self) -> str:
        p = self.project
        stamp = "2026.10.28 10:00:00"
        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 f'<FRAME GUID="{GUID}" FORMAT="0000" APP_VERSION="2.2.0.8" CHECKSUM="0000000000000000">',
                 f'  <PROJECT FORMAT="1.00" NAME={quoteattr(p.name)} AUTHOR={quoteattr(p.author)} '
                 f'CREATED="{stamp}" MODIFIED="{stamp}">',
                 "    <DIAGRAMS>"]
        for index, diagram in enumerate(self.diagrams()):
            lines += diagram.xml(index)
        lines += ["    </DIAGRAMS>", "  </PROJECT>", "</FRAME>"]
        return "﻿" + "\n".join(lines)
