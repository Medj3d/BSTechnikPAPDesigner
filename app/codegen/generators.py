"""Code-Erzeugung aus dem Strukturbaum: Pseudocode, Python und Java.

Bausteintexte sind Freitext. Was als Anweisung, Bedingung oder
Schleifenkopf erkannt wird (siehe ``app.analysis.text``), wird übersetzt;
alles andere wird als Kommentar („TODO“) übernommen. Nicht auswertbare
Bedingungen werden in Python/Java als Rückfrage an den Benutzer
(``frage(...)``) umgesetzt, damit das erzeugte Programm lauffähig bleibt.

Maßstab ist der Schreibtischtest: Die erzeugten Programme sollen dieselben
Werte liefern (echte Division, „mod“ mit dem Vorzeichen des Teilers,
kaufmännisches Runden, Text bleibt Text).
"""

from __future__ import annotations

import ast
import math
import re

from app.analysis import text as T
from app.analysis.ast import (Action, Block, Break, Continue, DoWhileLoop, EndStmt, If, LimitLoop, Loop,
                              Program, Unstructured, WhileLoop)
from app.analysis.variables import BOOLEAN, DEFAULTS, DOUBLE, STRING, Variables, static_type

LANGUAGES = {"pseudo": "Pseudocode", "python": "Python", "java": "Java"}
INDENT = "    "


def generate(programs: list[Program], language: str, title: str | None = None) -> str:
    programs = with_title(programs, title)
    if language == "python":
        return PythonGenerator(programs).generate()
    if language == "java":
        return JavaGenerator(programs).generate()
    return PseudoGenerator(programs).generate()


def _one_line(text: str) -> str:
    return " ".join((text or "").split())


def _int_expr(expr: str) -> str:
    """Für ``range()``: ganzzahlige Literale bleiben, alles andere wird mit int() umschlossen."""
    return expr if re.fullmatch(r"-?\d+", expr.strip()) else f"int({expr})"


def _numeric_literal(expr: str) -> float | None:
    try:
        return float(expr) if re.fullmatch(r"-?\d+(?:\.\d+)?", expr.strip()) else None
    except ValueError:
        return None


GENERIC_START_NAMES = {"start", "beginn", "anfang", ""}


def with_title(programs: list[Program], title: str | None) -> list[Program]:
    """Heißt das erste Start-Element nur „Start“, wird der Projektname verwendet."""
    if not programs or not title or programs[0].name.strip().lower() not in GENERIC_START_NAMES:
        return programs
    first = programs[0]
    renamed = Program(title, first.start_id, first.end_id, first.end_text, first.body, first.warnings)
    return [renamed] + list(programs[1:])


def _escape(text: str) -> str:
    return _one_line(text).replace("\\", "\\\\").replace('"', '\\"')


UNSTRUCTURED_MESSAGE = "Dieser Sprung im Plan lässt sich nicht als strukturiertes Programm darstellen"


def _has_break(block: Block) -> bool:
    """Verlässt der Block die umgebende Schleife (verschachtelte Schleifen zählen nicht)?"""
    for stmt in block:
        if isinstance(stmt, Break):
            return True
        if isinstance(stmt, If) and (_has_break(stmt.then_block) or _has_break(stmt.else_block)):
            return True
    return False


def _completes(stmt) -> bool:
    """Kann der Ablauf nach dieser Anweisung weitergehen? (Java lehnt unerreichbaren Code ab.)"""
    if isinstance(stmt, (EndStmt, Break, Continue)):
        return False
    if isinstance(stmt, Unstructured):
        return not stmt.fatal
    if isinstance(stmt, Loop) or _always_repeats(stmt):
        return _has_break(stmt.body)  # „while (true)“ endet nur über break
    if isinstance(stmt, If):
        return _block_completes(stmt.then_block) or _block_completes(stmt.else_block)
    if isinstance(stmt, DoWhileLoop) or (isinstance(stmt, LimitLoop) and stmt.footer
                                         and T.parse_loop_footer(stmt.footer) is not None
                                         and T.parse_loop_header(stmt.header).kind != "for"):
        return _block_completes(stmt.body) or _has_break(stmt.body)
    return True


def _constant(expr: str | None) -> bool | None:
    """Wert einer Bedingung ohne Variablen („wahr“, „1 = 1“) – sonst ``None``."""
    tree = T.parse_expression(expr) if expr else None
    if tree is None or any(isinstance(node, (ast.Name, ast.Call)) for node in ast.walk(tree)):
        return None
    from app.simulation.evaluator import EvaluationError, evaluate
    try:
        return bool(evaluate(expr, {}))
    except EvaluationError:  # z. B. Division durch null
        return None


def _always_repeats(stmt) -> bool:
    """Schleife, deren Bedingung immer erfüllt ist: Für Java ist alles dahinter unerreichbar."""
    if isinstance(stmt, WhileLoop):
        value = _constant(T.condition_expression(stmt.condition))
        return value is not None and value != stmt.negate
    if isinstance(stmt, DoWhileLoop):
        value = _constant(T.condition_expression(stmt.condition))
        return value is not None and value != stmt.negate
    if isinstance(stmt, LimitLoop):
        footer = T.parse_loop_footer(stmt.footer) if stmt.footer else None
        header = T.parse_loop_header(stmt.header)
        if footer is not None and header.kind != "for":
            value = _constant(footer[1])
            return value is not None and value == (footer[0] == "while")
        if footer is None and header.kind == "while":
            return _constant(header.condition) is True
    return False


def _never_runs(stmt) -> bool:
    """Kopfgesteuerte Schleife, deren Bedingung nie erfüllt ist (Java: Rumpf unerreichbar)."""
    if isinstance(stmt, WhileLoop):
        value = _constant(T.condition_expression(stmt.condition))
        return value is not None and value == stmt.negate
    if isinstance(stmt, LimitLoop) and not stmt.footer:
        header = T.parse_loop_header(stmt.header)
        return header.kind == "while" and _constant(header.condition) is False
    return False


def _block_completes(block: Block) -> bool:
    return all(_completes(stmt) for stmt in block)


def _free_name(name: str, taken) -> str:
    """Hängt „_“ an, bis der Name frei ist."""
    while name in taken:
        name += "_"
    return name


def collect_all_variables(programs: list[Program]) -> dict[str, str]:
    """Variablen aller Abläufe → Typ („double“, „String“ oder „boolean“)."""
    return Variables(programs).types


# ====================================================================== Pseudo
class PseudoGenerator:
    def __init__(self, programs: list[Program]):
        self.programs = programs
        self.lines: list[str] = []

    def generate(self) -> str:
        if not self.programs:
            return "// Der Plan enthält kein Start-Element."
        for index, program in enumerate(self.programs):
            if index:
                self.lines.append("")
            self.lines.append(f"PROGRAMM {_one_line(program.name)}")
            self.block(program.body, 1, top_level=True)
            self.lines.append(f"ENDE {_one_line(program.name)}".rstrip())
        return "\n".join(self.lines) + "\n"

    def emit(self, depth: int, text: str) -> None:
        self.lines.append(INDENT * depth + text)

    def comments(self, depth: int, comments: list[str]) -> None:
        for comment in comments:
            self.emit(depth, f"// {_one_line(comment)}")

    def block(self, block: Block, depth: int, top_level: bool = False) -> None:
        statements = list(block)
        if top_level and statements and isinstance(statements[-1], EndStmt):
            statements = statements[:-1]
        for stmt in statements:
            self.stmt(stmt, depth)

    def stmt(self, stmt, depth: int) -> None:
        if isinstance(stmt, Action):
            self.comments(depth, stmt.comments)
            prefix = {"input": "EINGABE: ", "output": "AUSGABE: ", "subprogram": "AUFRUF: "}.get(stmt.kind, "")
            lines = [line for line in stmt.text.splitlines() if line.strip()] or [""]
            for line in lines:
                if stmt.kind == "junction":
                    continue
                self.emit(depth, prefix + line.strip())
        elif isinstance(stmt, If):
            self.comments(depth, stmt.comments)
            self.emit(depth, f"WENN {_one_line(stmt.condition)} DANN")
            self.block(stmt.then_block, depth + 1)
            if len(stmt.else_block):
                self.emit(depth, "SONST")
                self.block(stmt.else_block, depth + 1)
            self.emit(depth, "ENDE WENN")
        elif isinstance(stmt, WhileLoop):
            self.comments(depth, stmt.comments)
            cond = _one_line(stmt.condition)
            self.emit(depth, f"SOLANGE {'NICHT (' + cond + ')' if stmt.negate else cond} WIEDERHOLE")
            self.block(stmt.body, depth + 1)
            self.emit(depth, "ENDE SOLANGE")
        elif isinstance(stmt, DoWhileLoop):
            self.comments(depth, stmt.comments)
            self.emit(depth, "WIEDERHOLE")
            self.block(stmt.body, depth + 1)
            cond = _one_line(stmt.condition)
            self.emit(depth, f"BIS {cond}" if stmt.negate else f"SOLANGE {cond}")
        elif isinstance(stmt, LimitLoop):
            self.comments(depth, stmt.comments)
            header = T.parse_loop_header(stmt.header)
            keyword = "FÜR" if header.kind == "for" else "SCHLEIFE"
            text = _one_line(stmt.header)
            if header.kind == "for" and text.lower().startswith(("für", "fuer", "for")):
                text = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else text
            self.emit(depth, f"{keyword} {text}")
            self.block(stmt.body, depth + 1)
            footer = _one_line(stmt.footer)
            self.emit(depth, f"ENDE {keyword}" + (f" ({footer})" if footer else ""))
        elif isinstance(stmt, Loop):
            self.emit(depth, "WIEDERHOLE")
            self.block(stmt.body, depth + 1)
            self.emit(depth, "ENDE WIEDERHOLE")
        elif isinstance(stmt, Continue):
            self.emit(depth, "NÄCHSTER DURCHLAUF")
        elif isinstance(stmt, Break):
            self.emit(depth, "SCHLEIFE VERLASSEN")
        elif isinstance(stmt, EndStmt):
            self.emit(depth, "ENDE (Programm beenden)")
        elif isinstance(stmt, Unstructured):
            self.emit(depth, f"// Hinweis: nicht strukturierbar – {_one_line(stmt.note)}")


# ====================================================================== Python
_PY_MATH = ("sqrt", "sin", "cos", "tan", "floor", "ceil", "exp", "log")
_PY_RESERVED_FUNCTIONS = {"main", "print", "input", "int", "float", "str", "len", "abs", "min", "max", "pow",
                          "round", "range", "wurzel", "ganzzahl", "pi", *_PY_MATH}
_CODE_ROUND = re.compile(r"\b(?:round|runden)\s*\(")
# Namen, die das erzeugte Programm selbst als Funktion braucht – eine gleichnamige
# Variable würde sie verdecken („print = 3“ … „print(...)“)
_PY_RESERVED_VARIABLES = {"main", "print", "input", "int", "float", "str", "len", "abs", "min", "max", "pow",
                          "range", "round", "wurzel", "ganzzahl", *_PY_MATH}


class _TextConcat(ast.NodeTransformer):
    """„"Du bist " + alter“: In Python muss die Zahl erst mit str() zu Text werden."""

    def __init__(self, types: dict, dynamic: set):
        self.types, self.dynamic = types, dynamic
        self.changed = False

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Add) and static_type(node, self.types, self.dynamic) == STRING:
            for side in ("left", "right"):
                operand = getattr(node, side)
                if static_type(operand, self.types, self.dynamic) != STRING:
                    setattr(node, side, ast.Call(func=ast.Name(id="str", ctx=ast.Load()), args=[operand], keywords=[]))
                    self.changed = True
        return node


class PythonGenerator:
    def __init__(self, programs: list[Program]):
        self.programs = programs
        self.lines: list[str] = []
        self.uses_frage = False
        self.uses_eingabe = False
        self.uses_runden = False
        self.used: set[str] = set()              # gelesene Namen und Funktionen (für Importe)
        self.called: dict[str, str] = {}         # Funktionsname → Beschriftung (noch fehlende Abläufe)
        self.known: set[str] = set()
        self.types: dict[str, str] = {}
        self.dynamic: set[str] = set()
        self.function_names: dict[str, str] = {}  # Programmname (slug) → Funktionsname
        self.functions: list[str] = []
        self.input_fn, self.ask_fn, self.round_fn = "eingabe", "frage", "runden"
        self.renamed: dict[str, str] = {}        # Variable des Plans → Name im Python-Programm
        self._rename_pattern = None
        self._loops = 0                          # Tiefe der gerade erzeugten Schleifen

    def var(self, name: str) -> str:
        """Name einer Plan-Variablen im Python-Programm."""
        return self.renamed.get(name, name)

    def _rename_variables(self) -> None:
        for name in sorted(self.known & _PY_RESERVED_VARIABLES):
            self.renamed[name] = _free_name(name + "_", self.known | set(self.renamed.values()))
        if self.renamed:
            names = "|".join(re.escape(name) for name in sorted(self.renamed, key=len, reverse=True))
            self._rename_pattern = re.compile(rf"(?<![\w.])({names})(?!\w)(?!\s*\()")

    def _name_functions(self, taken: set) -> None:
        """Eindeutige Funktionsnamen, die keine Variable und keine Hilfsfunktion verdecken."""
        used = set(taken) | _PY_RESERVED_FUNCTIONS | {self.input_fn, self.ask_fn, self.round_fn}
        for index, program in enumerate(self.programs):
            if index == 0:
                name = "main"
            else:
                name = T.slug(program.name, f"ablauf_{index + 1}")
                if not T.is_identifier(name) or name in used:
                    name = _free_name(f"{name}_ablauf" if T.is_identifier(name) else f"ablauf_{index + 1}", used)
            used.add(name)
            self.functions.append(name)
            slug = T.slug(program.name)
            # ein Aufruf meint den gleichnamigen Ablauf – nicht das Hauptprogramm selbst
            if slug not in self.function_names or self.function_names[slug] == "main":
                self.function_names[slug] = name

    def generate(self) -> str:
        if not self.programs:
            return "# Der Plan enthält kein Start-Element.\n"
        variables = Variables(self.programs)
        self.known = set(variables.names)
        self.types, self.dynamic = variables.types, variables.dynamic
        # Hilfsfunktionen dürfen nicht wie eine Variable des Plans heißen
        self.input_fn = _free_name("eingabe", self.known)
        self.ask_fn = _free_name("frage", self.known)
        self.round_fn = _free_name("runden", self.known)
        self._rename_variables()
        self._name_functions(self.known | set(self.renamed.values()))
        shared = sorted(self.var(name) for name in self.known) if len(self.programs) > 1 else []
        unset = self._unset_variables()
        body: list[str] = []
        for index, program in enumerate(self.programs):
            self.lines = []
            self.lines.append(f"def {self.functions[index]}():")
            self.lines.append(f'{INDENT}"""{_escape(program.name)}"""')
            if shared:
                # alle Abläufe arbeiten mit denselben Variablen
                self.lines.append(f"{INDENT}global {', '.join(shared)}")
            for warning in program.warnings:
                self.lines.append(f"{INDENT}# Hinweis: {_one_line(warning)}")
            if index == 0 and unset:
                self.lines.append(f"{INDENT}# Startwerte: Diese Variablen bekommen nicht auf jedem Weg einen Wert.")
                for name in unset:
                    self.lines.append(f"{INDENT}{self.var(name)} = {DEFAULTS[self.types[name]]!r}"
                                      .replace("''", '""'))
            self.block(program.body, 1, top_level=True)
            body.extend(self.lines)
            body.append("")
            body.append("")
        stubs = []
        for fname, label in self.called.items():
            stubs += [f"def {fname}(*argumente):", f'{INDENT}"""Unterprogramm „{_escape(label)}“."""',
                      f"{INDENT}pass  # TODO: Unterprogramm ausarbeiten", "", ""]
        header = [f"# Automatisch erzeugt aus dem Programmablaufplan „{_escape(self.programs[0].name)}“",
                  "# (BS Technik PAP Designer). Nicht erkannte Texte sind als TODO markiert.", ""]
        footer = ['if __name__ == "__main__":', f"{INDENT}main()"]
        return "\n".join(header + self._imports() + [""] + self._helpers() + stubs + body + footer) + "\n"

    def _imports(self) -> list[str]:
        used = self.used - self.known
        names = sorted({name for name in _PY_MATH if name in used} | ({"sqrt"} if "wurzel" in used else set())
                       | ({"pi"} if "pi" in used else set()))
        lines = [f"from math import {', '.join(names)}"] if names else []
        if "wurzel" in used:
            lines.append("wurzel = sqrt")
        if "ganzzahl" in used:
            lines.append("ganzzahl = int")
        return lines + [""] if lines else []

    def _helpers(self) -> list[str]:
        one, two, three, four = INDENT, INDENT * 2, INDENT * 3, INDENT * 4
        helpers = []
        if self.uses_eingabe:
            helpers += [f"def {self.input_fn}(text, nur_zahl=True):",
                        f'{one}"""Liest eine Zahl ein (auch mit Komma); fragt bei Tippfehlern erneut."""',
                        f"{one}while True:",
                        f"{two}wert = input(text).strip()",
                        f"{two}for typ in (int, float):",
                        f"{three}try:",
                        f'{four}zahl = typ(wert.replace(",", "."))',
                        f"{three}except ValueError:",
                        f"{four}continue",
                        f'{three}if "_" not in wert and zahl == zahl and abs(zahl) != float("inf"):',
                        f"{four}return zahl",
                        f"{two}if not nur_zahl:",
                        f"{three}return wert  # keine Zahl: Text",
                        f'{two}print("Bitte eine Zahl eingeben.")', "", ""]
        if self.uses_frage:
            helpers += [f"def {self.ask_fn}(text):",
                        f'{one}"""Nicht automatisch auswertbare Bedingung: den Benutzer fragen."""',
                        f'{one}return input(text + " (j/n) ").strip().lower().startswith("j")', "", ""]
        if self.uses_runden:
            helpers += [f"def {self.round_fn}(x, stellen=0):",
                        f'{one}"""Kaufmännisch runden: ab 5 wird aufgerundet (2,5 wird 3)."""',
                        f"{one}faktor = 10 ** int(stellen)",
                        f"{one}wert = int(abs(x) * faktor + 0.5) / faktor",
                        f"{one}wert = wert if x >= 0 else -wert",
                        f"{one}return int(wert) if stellen <= 0 else wert", "", ""]
        return helpers

    # ----------------------------------------------------------- Startwerte
    def _unset_variables(self) -> list[str]:
        """Variablen, die gelesen werden können, bevor sie sicher einen Wert haben.

        Java gibt jeder Variablen einen Startwert; damit das Python-Programm
        dann nicht abstürzt, bekommen genau diese Variablen dort ebenfalls einen.
        """
        needed: list[str] = []
        active: set[int] = set()

        def read(names, assigned) -> None:
            for name in names:
                if name in self.known and name not in assigned and name not in needed:
                    needed.append(name)

        def visit(block: Block, assigned: set) -> set:
            assigned = set(assigned)
            for stmt in block:
                if isinstance(stmt, Action):
                    if stmt.kind == "input":
                        assigned.update(T.input_variables(stmt.text))
                    elif stmt.kind == "process":
                        for name, expr in T.parse_assignments(stmt.text) or []:
                            read(T.names_in(expr), assigned)
                            assigned.add(name)
                    elif stmt.kind == "output":
                        spec = T.output_spec(stmt.text, self.known)
                        read(spec.variables, assigned)
                        for kind, value in spec.parts:
                            if kind == "expression":
                                read(T.names_in(value), assigned)
                    elif stmt.kind == "subprogram":
                        call = T.call_parts(stmt.text)
                        slug = T.slug(call[0] if call else stmt.text)
                        index = next((i for i, p in enumerate(self.programs) if T.slug(p.name) == slug), None)
                        if index is not None and index not in active:
                            active.add(index)
                            visit(self.programs[index].body, assigned)
                            active.discard(index)
                elif isinstance(stmt, If):
                    read(T.names_in(T.condition_expression(stmt.condition) or ""), assigned)
                    then_out, else_out = visit(stmt.then_block, assigned), visit(stmt.else_block, assigned)
                    assigned |= then_out & else_out
                elif isinstance(stmt, WhileLoop):
                    read(T.names_in(T.condition_expression(stmt.condition) or ""), assigned)
                    visit(stmt.body, assigned)
                elif isinstance(stmt, Loop):
                    # Die Bausteine am Anfang des Rumpfs laufen immer; danach kann die Schleife
                    # jederzeit verlassen werden – was dort gesetzt wird, gilt nicht als sicher.
                    statements = list(stmt.body)
                    lead = 0
                    while lead < len(statements) and isinstance(statements[lead], Action):
                        lead += 1
                    assigned = visit(Block(statements[:lead]), assigned)
                    visit(Block(statements[lead:]), assigned)
                elif isinstance(stmt, DoWhileLoop):
                    assigned = visit(stmt.body, assigned)  # läuft mindestens einmal
                    read(T.names_in(T.condition_expression(stmt.condition) or ""), assigned)
                elif isinstance(stmt, LimitLoop):
                    header = T.parse_loop_header(stmt.header)
                    footer = T.parse_loop_footer(stmt.footer) if stmt.footer else None
                    if header.kind == "for":
                        for expr in (header.start, header.end, header.step):
                            read(T.names_in(expr), assigned)
                        if all(self.expr(e) is not None for e in (header.start, header.end, header.step)):
                            assigned.add(header.variable)  # nur dann wird wirklich gezählt
                    elif header.kind == "while":
                        read(T.names_in(header.condition), assigned)
                    elif header.kind == "times":
                        read(T.names_in(header.count), assigned)
                    out = visit(stmt.body, assigned)
                    if footer is not None:
                        if header.kind != "for":
                            assigned = out  # fußgesteuert: läuft mindestens einmal
                        read(T.names_in(footer[1]), out)
            return assigned

        active.add(0)
        visit(self.programs[0].body, set())
        return needed

    # ---------------------------------------------------------------- Helfer
    def emit(self, depth: int, text: str) -> None:
        self.lines.append(INDENT * depth + text)

    def comments(self, depth: int, comments: list[str]) -> None:
        for comment in comments:
            self.emit(depth, f"# {_one_line(comment)}")

    def expr(self, expr: str | None) -> str | None:
        """Ausdruck für das Python-Programm oder ``None``, wenn ein Name nie einen Wert bekommt."""
        if not expr:
            return None
        tree = T.parse_expression(expr)
        if tree is None or T.unknown_names(expr, self.known):
            return None
        self.used.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
        concat = _TextConcat(self.types, self.dynamic)
        tree = concat.visit(tree)
        if concat.changed:
            expr = ast.unparse(ast.fix_missing_locations(tree))
        if self._rename_pattern is not None:
            parts = T._STRING_LITERAL.split(expr)
            expr = "".join(part if index % 2 else self._rename_pattern.sub(lambda m: self.renamed[m.group(1)], part)
                           for index, part in enumerate(parts))
        if _CODE_ROUND.search(expr):
            # Pythons round() rundet „zur geraden Zahl“ (2,5 → 2) – im PAP ist kaufmännisch gemeint
            parts = T._STRING_LITERAL.split(expr)
            if any(_CODE_ROUND.search(part) for part in parts[::2]):
                self.uses_runden = True
            return "".join(part if index % 2 else _CODE_ROUND.sub(f"{self.round_fn}(", part)
                           for index, part in enumerate(parts))
        return expr

    def ask(self, text: str) -> str:
        self.uses_frage = True
        return f'{self.ask_fn}("{_escape(text)}")'

    def condition(self, text: str, negate: bool = False) -> str:
        expr = self.expr(T.condition_expression(text)) or self.ask(text)
        return f"not ({expr})" if negate else expr

    def block(self, block: Block, depth: int, top_level: bool = False) -> None:
        statements = list(block)
        if top_level and statements and isinstance(statements[-1], EndStmt):
            statements = statements[:-1]
        before = len(self.lines)
        for stmt in statements:
            self.stmt(stmt, depth)
        if not any(line.strip() and not line.strip().startswith("#") for line in self.lines[before:]):
            self.emit(depth, "pass")

    def stmt(self, stmt, depth: int) -> None:
        if isinstance(stmt, Action):
            self.comments(depth, stmt.comments)
            getattr(self, f"action_{stmt.kind}", self.action_process)(stmt, depth)
        elif isinstance(stmt, If):
            self.comments(depth, stmt.comments)
            self.emit(depth, f"if {self.condition(stmt.condition)}:")
            self.block(stmt.then_block, depth + 1)
            if len(stmt.else_block):
                self.emit(depth, "else:")
                self.block(stmt.else_block, depth + 1)
        elif isinstance(stmt, WhileLoop):
            self.comments(depth, stmt.comments)
            self.emit(depth, f"while {self.condition(stmt.condition, stmt.negate)}:")
            self.loop_body(stmt.body, depth + 1)
        elif isinstance(stmt, DoWhileLoop):
            self.comments(depth, stmt.comments)
            self.emit(depth, "while True:")
            self.loop_body(stmt.body, depth + 1)
            # weiter, solange die Bedingung gilt (bzw. bis sie gilt, wenn negiert)
            self.emit(depth + 1, f"if {self.condition(stmt.condition, not stmt.negate)}:")
            self.emit(depth + 2, "break")
        elif isinstance(stmt, LimitLoop):
            self.limit_loop(stmt, depth)
        elif isinstance(stmt, Loop):
            self.emit(depth, "while True:")
            self.loop_body(stmt.body, depth + 1)
        elif isinstance(stmt, Continue) and self._loops:
            self.emit(depth, "continue  # nächster Durchlauf")
        elif isinstance(stmt, Break) and self._loops:
            self.emit(depth, "break  # Schleife verlassen")
        elif isinstance(stmt, EndStmt):
            self.emit(depth, "return  # Ende")
        elif isinstance(stmt, (Unstructured, Break, Continue)):
            note = stmt.note if isinstance(stmt, Unstructured) else "Sprung aus einer Schleife"
            self.emit(depth, f"# Hinweis: nicht strukturierbar – {_one_line(note)}")
            if not isinstance(stmt, Unstructured) or stmt.fatal:
                # lieber deutlich anhalten als mit falschem Ablauf weiterlaufen
                self.emit(depth, f'raise SystemExit("{UNSTRUCTURED_MESSAGE}: {_escape(note)}")')

    def loop_body(self, block: Block, depth: int) -> None:
        self._loops += 1
        try:
            self.block(block, depth)
        finally:
            self._loops -= 1

    def limit_loop(self, stmt: LimitLoop, depth: int) -> None:
        self.comments(depth, stmt.comments)
        header = T.parse_loop_header(stmt.header)
        footer = T.parse_loop_footer(stmt.footer) if stmt.footer else None
        start, end, step = (self.expr(e) for e in (header.start, header.end, header.step)) \
            if header.kind == "for" else (None, None, None)
        counting = header.kind == "for" and None not in (start, end, step)
        leave = None
        if footer is not None:
            kind, text = footer
            cond = self.expr(text) or self.ask(stmt.footer)
            leave = cond if kind == "until" else f"not ({cond})"
        if footer is not None and not counting:
            self.emit(depth, f"while True:  # {_one_line(stmt.header)}")
            self.loop_body(stmt.body, depth + 1)
            self.emit(depth + 1, f"if {leave}:")
            self.emit(depth + 2, "break")
            return
        if counting:
            # Zählschleife wie im PAP: auch Kommazahl-Schritte, Schritt aus einer Variablen,
            # und die Zählvariable hat nach der Schleife den ersten Wert „hinter“ dem Ende.
            var = self.var(header.variable)
            self.emit(depth, f"{var} = {start}")
            literal = _numeric_literal(step)
            if literal is not None:
                self.emit(depth, f"while {var} {'>=' if literal < 0 else '<='} {end}:")
            else:
                self.emit(depth, f"while ({var} <= {end}) if ({step}) >= 0 else ({var} >= {end}):")
            self.loop_body(stmt.body, depth + 1)
            if leave is not None:
                # zusätzliche Bedingung am Schleifenende
                self.emit(depth + 1, f"if {leave}:")
                self.emit(depth + 2, "break")
            self.emit(depth + 1, f"{var} -= {step[1:]}" if literal is not None and literal < 0
                      else f"{var} += {step}")
            return
        if header.kind == "while" and self.expr(header.condition):
            self.emit(depth, f"while {self.expr(header.condition)}:")
        elif header.kind == "times" and self.expr(header.count):
            self.emit(depth, f"for _ in range({_int_expr(self.expr(header.count))}):")
        else:
            self.emit(depth, f"while {self.ask(stmt.header)}:")
        self.loop_body(stmt.body, depth + 1)

    # ------------------------------------------------------------ Aktionen
    def action_input(self, stmt: Action, depth: int) -> None:
        names = T.input_variables(stmt.text)
        if not names:
            self.emit(depth, f'input("{_escape(stmt.text)}: ")  # TODO: Variable festlegen')
            return
        for name in names:
            kind, target = self.types.get(name, DOUBLE), self.var(name)
            if name in self.dynamic:
                self.uses_eingabe = True  # Zahl oder Text – je nachdem, was eingetippt wird
                self.emit(depth, f'{target} = {self.input_fn}("{name}: ", nur_zahl=False)')
            elif kind == STRING:
                self.emit(depth, f'{target} = input("{name}: ").strip()')
            elif kind == BOOLEAN:
                self.emit(depth, f"{target} = {self.ask(name + '?')}")
            else:
                self.uses_eingabe = True
                self.emit(depth, f'{target} = {self.input_fn}("{name}: ")')

    def action_output(self, stmt: Action, depth: int) -> None:
        spec = T.output_spec(stmt.text, self.known)
        if spec.kind == "mixed" and all(kind == "string" or self.expr(value) for kind, value in spec.parts):
            args = ", ".join(f'"{_escape(value)}"' if kind == "string" else self.expr(value)
                             for kind, value in spec.parts)
            self.emit(depth, f"print({args})")
        elif spec.kind == "expression" and self.expr(spec.value):
            self.emit(depth, f"print({self.expr(spec.value)})")
        elif spec.kind == "variables" and len(spec.variables) == 1:
            self.emit(depth, f'print("{_escape(spec.value)}:", {self.var(spec.variables[0])})')
        elif spec.kind == "variables":
            values = ", ".join(self.var(name) for name in spec.variables)
            self.emit(depth, f'print("{_escape(spec.value)}:", ", ".join(str(wert) for wert in ({values})))')
        else:
            text = spec.value if spec.kind in ("string", "text") else _one_line(stmt.text)
            self.emit(depth, f'print("{_escape(text)}")')

    def action_process(self, stmt: Action, depth: int) -> None:
        assignments = T.parse_assignments(stmt.text)
        if assignments:
            for name, expr in assignments:
                code = self.expr(expr)
                if code is not None:
                    self.emit(depth, f"{self.var(name)} = {code}")
                else:
                    missing = ", ".join(f"„{n}“" for n in T.unknown_names(expr, self.known))
                    self.emit(depth, f"{self.var(name)} = 0  # TODO: {name} = {expr} – {missing} erhält im Plan "
                                     "keinen Wert")
            return
        for line in [line for line in stmt.text.splitlines() if line.strip()] or ["(leer)"]:
            self.emit(depth, f"# TODO: {line.strip()}")

    def action_subprogram(self, stmt: Action, depth: int) -> None:
        call = T.call_parts(stmt.text)
        slug = T.slug(call[0] if call else stmt.text)
        if slug in self.function_names:
            # Abläufe haben keine Parameter: Sie arbeiten mit den gemeinsamen Variablen
            note = f"  # {_one_line(stmt.text)}" if call and call[1] else ""
            self.emit(depth, f"{self.function_names[slug]}(){note}")
            return
        name = slug if T.is_identifier(slug) else f"unterprogramm_{len(self.called) + 1}"
        name = _free_name(name, (self.known | _PY_RESERVED_FUNCTIONS | set(self.functions)
                                 | {self.input_fn, self.ask_fn, self.round_fn}) - set(self.called))
        self.called.setdefault(name, stmt.text)
        arguments = ", ".join(self.expr(arg) or "None" for arg in call[1]) if call else ""
        self.emit(depth, f"{name}({arguments})")

    def action_junction(self, stmt: Action, depth: int) -> None:
        pass


# ======================================================================== Java
class _Unsupported(Exception):
    pass


_JAVA_BINARY = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_JAVA_COMPARE = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
_JAVA_MATH = {"abs": "Math.abs", "sqrt": "Math.sqrt", "wurzel": "Math.sqrt", "floor": "Math.floor",
              "ceil": "Math.ceil", "sin": "Math.sin", "cos": "Math.cos", "tan": "Math.tan",
              "pow": "Math.pow", "exp": "Math.exp", "log": "Math.log"}
# Java-Schlüsselwörter und Namen, die im erzeugten Programm schon vergeben sind
_JAVA_RESERVED = {"abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
                  "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
                  "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long",
                  "native", "new", "package", "private", "protected", "public", "return", "short", "static",
                  "strictfp", "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try",
                  "void", "volatile", "while", "null", "true", "false", "var", "record", "yield", "_",
                  "String", "Math", "System", "Scanner", "Object", "Double", "Long", "SCANNER", "args"}
_JAVA_CLASS_NAMES = {"String", "Math", "System", "Scanner", "Object", "Double", "Long", "Integer", "Boolean",
                     "Character", "Number", "Class", "Thread", "Error", "Exception"}
_JAVA_METHODS = {"main", "eingabe", "eingabeText", "frage", "mod", "runden", "text", "zahl"}
_INT_MAX = 2 ** 31 - 1


def _java_string_literal(value: str) -> str:
    named = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}
    out = []
    for ch in value:
        if ch in named:
            out.append(named[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\%03o" % ord(ch))  # oktal: \\uXXXX würde vor dem Einlesen ersetzt
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _java_comment(text: str) -> str:
    """Kommentartext: javac wertet „\\uXXXX“ auch in Kommentaren aus – Backslashes verdoppeln."""
    return _one_line(text).replace("\\", "\\\\")


def java_name(name: str) -> str:
    """Variablenname für Java: Schlüsselwörter wie „int“ oder „new“ bekommen einen Unterstrich."""
    return name + "_" if name in _JAVA_RESERVED else name


class _JavaExpr:
    """Übersetzt einen Python-Ausdruck über den Syntaxbaum nach Java.

    ``types`` sind die Typen der Variablen, ``dynamic`` die Eingaben, die Zahl
    oder Text sein können; ``known`` die Variablen des Plans (``None`` = jeden
    Namen annehmen). ``helpers`` sammelt benötigte Hilfsmethoden.
    """

    def __init__(self, types: dict | None = None, known=None, helpers: set | None = None, dynamic=frozenset()):
        self.types = types or {}
        self.known = known
        self.dynamic = dynamic
        self.helpers = helpers if helpers is not None else set()

    # ------------------------------------------------------------- Typen
    def type_of(self, node) -> str:
        if isinstance(node, ast.IfExp):
            return self.type_of(node.body)
        return static_type(node, self.types, self.dynamic) or DOUBLE

    def is_dynamic(self, node) -> bool:
        return isinstance(node, ast.Name) and node.id in self.dynamic

    def integral(self, node) -> bool:
        """Ergibt der Java-Ausdruck einen int? Dann drohen Ganzzahldivision und Überlauf."""
        if isinstance(node, ast.Constant):
            return type(node.value) is int and abs(node.value) <= _INT_MAX
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return self.integral(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("abs", "min", "max"):
            return all(self.integral(arg) for arg in node.args)
        if isinstance(node, ast.IfExp):
            return self.integral(node.body) and self.integral(node.orelse)
        return False

    def as_double(self, node) -> str:
        if isinstance(node, ast.Constant):
            return f"{node.value}.0"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return f"-{node.operand.value}.0"
        return f"(double) {self.operand(node, 3)}"

    # ---------------------------------------------------------- Umsetzung
    def convert(self, node) -> str:
        method = getattr(self, f"_{type(node).__name__}", None)
        if method is None:
            raise _Unsupported(type(node).__name__)
        return method(node)

    def _precedence(self, node) -> int:
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, (ast.Add, ast.Sub)):
                return 1
            if isinstance(node.op, ast.Div):
                return 2
            if isinstance(node.op, ast.Mult):
                return 9 if self.type_of(node) == STRING else 2
            return 9  # Math.pow(…), Math.floor(…), mod(…)
        if isinstance(node, ast.UnaryOp):
            return 0 if isinstance(node.op, ast.Not) else 3
        if isinstance(node, (ast.Compare, ast.BoolOp, ast.IfExp)):
            return 0
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("int", "ganzzahl", "len"):
            return 3  # Typumwandlung „(double) …“
        return 9

    def operand(self, node, level: int = 9) -> str:
        """Teilausdruck; geklammert, wenn er schwächer bindet als ``level``."""
        text = self.convert(node)
        return f"({text})" if self._precedence(node) < level else text

    def number(self, node, level: int = 1) -> str:
        """Operand einer Rechnung oder eines Zahlenvergleichs."""
        kind = self.type_of(node)
        if kind == BOOLEAN:
            return f"({self.convert(node)} ? 1 : 0)"  # wahr zählt wie 1
        if kind == STRING:
            if not self.is_dynamic(node):
                raise _Unsupported("Text in einer Rechnung")
            self.helpers.add("zahl")  # Eingabe, die Zahl oder Text sein kann
            return f"zahl({self.convert(node)})"
        return self.operand(node, level)

    def as_text(self, node, level: int = 9) -> str:
        """Operand einer Textverkettung: Zahlen wie im Schreibtischtest (7 statt 7.0)."""
        if self.type_of(node) == DOUBLE:
            self.helpers.add("text")
            return f"text({self.convert(node)})"
        return self.operand(node, level)

    def truthy(self, node) -> str:
        """Ausdruck als Bedingung: Zahlen gelten als wahr, wenn sie nicht 0 sind (wie im Schreibtischtest)."""
        kind = self.type_of(node)
        if kind == BOOLEAN:
            return self.convert(node)
        if kind == STRING:
            return f"!{self.operand(node, 9)}.isEmpty()"
        return f"{self.operand(node, 1)} != 0"

    def _Constant(self, node) -> str:
        value = node.value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return repr(value) if abs(value) <= _INT_MAX else f"{value}.0"
        if isinstance(value, float):
            if not math.isfinite(value):
                raise _Unsupported("Zahl")
            return repr(value)
        if isinstance(value, str):
            return _java_string_literal(value)
        raise _Unsupported("Konstante")

    def _Name(self, node) -> str:
        if self.known is None or node.id in self.known:
            if node.id == "pi" and (self.known is None or "pi" not in self.known):
                return "Math.PI"
            return java_name(node.id)
        if node.id == "pi":
            return "Math.PI"
        raise _Unsupported(node.id)  # erhält im Plan nie einen Wert

    def _BinOp(self, node) -> str:
        left_type, right_type = self.type_of(node.left), self.type_of(node.right)
        kind = self.type_of(node)
        if isinstance(node.op, ast.Add) and kind == STRING:
            return f"{self.as_text(node.left, 1)} + {self.as_text(node.right, 2)}"
        if isinstance(node.op, ast.Mult) and kind == STRING:
            if left_type == right_type:
                raise _Unsupported("Text * Text")
            text, count = (node.left, node.right) if left_type == STRING else (node.right, node.left)
            # wie im Schreibtischtest: eine Anzahl unter 0 ergibt leeren Text
            return f"{self.operand(text, 9)}.repeat(Math.max(0, (int) ({self.number(count)})))"
        if isinstance(node.op, ast.Pow):
            return f"Math.pow({self.number(node.left, 0)}, {self.number(node.right, 0)})"
        if isinstance(node.op, ast.Mod):
            self.helpers.add("mod")  # Javas % nimmt das Vorzeichen der linken Zahl
            return f"mod({self.number(node.left, 0)}, {self.number(node.right, 0)})"
        level = 1 if isinstance(node.op, (ast.Add, ast.Sub)) else 2
        left = self.number(node.left, level)
        if self.integral(node.left) and self.integral(node.right):
            right = self.as_double(node.right)  # 7 / 2 wäre in Java 3, 365 * 24 * 3600 * 1000 liefe über
        else:
            right = self.number(node.right, level + 1)
        if isinstance(node.op, ast.FloorDiv):
            return f"Math.floor({left} / {right})"
        op = _JAVA_BINARY.get(type(node.op))
        if op is None:
            raise _Unsupported("Operator")
        return f"{left} {op} {right}"

    def _UnaryOp(self, node) -> str:
        if isinstance(node.op, ast.Not):
            kind = self.type_of(node.operand)
            if kind == DOUBLE:
                return f"{self.operand(node.operand, 1)} == 0"
            if kind == STRING:
                return f"{self.operand(node.operand, 9)}.isEmpty()"
            inner = self.convert(node.operand)
            return f"!{inner}" if isinstance(node.operand, (ast.Name, ast.Constant)) else f"!({inner})"
        operand = self.number(node.operand, 3)
        if isinstance(node.op, ast.USub):
            return f"-({operand})" if operand.startswith("-") else f"-{operand}"  # nicht „--“
        if isinstance(node.op, ast.UAdd):
            return operand
        raise _Unsupported("Operator")

    def _BoolOp(self, node) -> str:
        op = " && " if isinstance(node.op, ast.And) else " || "
        parts = []
        for value in node.values:
            text = self.truthy(value)
            parts.append(f"({text})" if isinstance(value, (ast.BoolOp, ast.IfExp)) else text)
        return op.join(parts)

    def _compare(self, left, op_node, right) -> str:
        op = _JAVA_COMPARE.get(type(op_node))
        if op is None:
            raise _Unsupported("Vergleich")
        left_type, right_type = self.type_of(left), self.type_of(right)
        left_dynamic, right_dynamic = self.is_dynamic(left), self.is_dynamic(right)
        # Eingabe, die Zahl oder Text sein kann: mit Zahlen wird als Zahl verglichen
        numeric_dynamic = (left_dynamic and right_type == DOUBLE) or (right_dynamic and left_type == DOUBLE) \
            or (left_dynamic and right_dynamic and op not in ("==", "!="))
        if STRING in (left_type, right_type) and not numeric_dynamic:
            if op in ("==", "!="):
                # Text wird mit equals verglichen; ein Literal steht vorn
                if isinstance(right, ast.Constant) and right_type == STRING or left_type != STRING:
                    text = f"{self.operand(right, 9)}.equals({self.convert(left)})"
                else:
                    text = f"{self.operand(left, 9)}.equals({self.convert(right)})"
                return text if op == "==" else f"!{text}"
            if left_type != right_type:
                raise _Unsupported("Text mit Zahl verglichen")
            return f"{self.operand(left, 9)}.compareTo({self.convert(right)}) {op} 0"
        if left_type == right_type == BOOLEAN and op in ("==", "!="):
            return f"{self.operand(left, 1)} {op} {self.operand(right, 1)}"
        return f"{self.number(left)} {op} {self.number(right)}"

    def _Compare(self, node) -> str:
        # a < b < c  →  a < b && b < c
        operands = [node.left] + node.comparators
        parts = [self._compare(a, op, b) for a, op, b in zip(operands, node.ops, operands[1:])]
        return parts[0] if len(parts) == 1 else " && ".join(f"({p})" for p in parts)

    def _Call(self, node) -> str:
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise _Unsupported("Aufruf")
        name = node.func.id
        kinds = [self.type_of(arg) for arg in node.args]
        count = len(node.args)
        if name == "str" and count == 1:
            if kinds[0] == STRING:
                return self.convert(node.args[0])
            if kinds[0] == DOUBLE:
                self.helpers.add("text")  # 5 statt 5.0
                return f"text({self.convert(node.args[0])})"
            return f"String.valueOf({self.convert(node.args[0])})"
        if name == "len" and count == 1 and kinds[0] == STRING:
            return f"(double) {self.operand(node.args[0], 9)}.length()"
        if name in ("float", "int", "ganzzahl") and count == 1 and kinds[0] == STRING:
            self.helpers.add("zahl")  # Text in eine Zahl umwandeln (auch mit Komma)
            parsed = f"zahl({self.convert(node.args[0])})"
            return parsed if name == "float" else f"(double) (long) {parsed}"
        args = [self.number(arg, 0) for arg in node.args]
        if name == "float" and count == 1:
            return self.number(node.args[0], 9)
        if name in ("min", "max") and count >= 2:
            result = args[0]
            for arg in args[1:]:
                result = f"Math.{name}({result}, {arg})"
            return result
        if name in ("int", "ganzzahl") and count == 1:
            return f"(double) (long) ({args[0]})"  # schneidet ab wie int(), bleibt aber eine Kommazahl
        if name in ("round", "runden") and count in (1, 2):
            self.helpers.add("runden")  # kaufmännisch, auch auf Nachkommastellen
            return f"runden({', '.join(args)})"
        arity = 2 if name == "pow" else 1
        if name in _JAVA_MATH and count == arity:
            return f"{_JAVA_MATH[name]}({', '.join(args)})"
        raise _Unsupported(name)

    def _IfExp(self, node) -> str:
        if self.type_of(node.body) != self.type_of(node.orelse):
            raise _Unsupported("unterschiedliche Typen")
        test = self.truthy(node.test)
        return f"{test} ? {self.operand(node.body, 1)} : {self.operand(node.orelse, 1)}"


def _java_expr(expr: str, types: dict | None = None, known=None, dynamic=frozenset()) -> str | None:
    """Python-Ausdruck → Java, sonst ``None`` (dann TODO bzw. Rückfrage)."""
    tree = T.parse_expression(expr)
    if tree is None:
        return None
    try:
        return _JavaExpr(types, known, dynamic=dynamic).convert(tree)
    except (_Unsupported, RecursionError):
        return None


class JavaGenerator:
    def __init__(self, programs: list[Program]):
        self.programs = programs
        self.lines: list[str] = []
        self.uses_frage = False
        self.uses_eingabe = False
        self.uses_eingabe_text = False
        self.helpers: set[str] = set()
        self.called: dict[str, str] = {}         # Methodenname → Beschriftung (noch fehlende Abläufe)
        self.known: set[str] = set()
        self.types: dict[str, str] = {}
        self.dynamic: set[str] = set()
        self.methods: list[str] = []
        self.method_names: dict[str, int] = {}   # Programmname (slug) → Index
        self._times_depth = 0
        self._loops = 0                          # Tiefe der gerade erzeugten Schleifen

    # -------------------------------------------------------------- Namen
    def _name_methods(self) -> None:
        used = set(_JAVA_METHODS) | _JAVA_RESERVED
        for index, program in enumerate(self.programs):
            if index == 0:
                name = "main"
            else:
                name = T.lower_camel(program.name, f"ablauf{index + 1}")
                name = _free_name(name if name not in used else f"{name}Ablauf", used)
            used.add(name)
            self.methods.append(name)
            slug = T.slug(program.name)
            # ein Aufruf meint den gleichnamigen Ablauf – nicht das Hauptprogramm selbst
            if self.method_names.get(slug, 0) == 0:
                self.method_names[slug] = index

    def _class_name(self) -> str:
        first = self.programs[0].name
        name = T.camel(first if first.strip().lower() not in GENERIC_START_NAMES else "Programm")[:60]
        return name + "Programm" if name in _JAVA_CLASS_NAMES or name in _JAVA_RESERVED else name

    # ---------------------------------------------------------- Ausdrücke
    def _translate(self, expr: str | None, how):
        """Wendet ``how(Übersetzer, Baum)`` an; ``None``, wenn der Ausdruck nicht übersetzbar ist."""
        tree = T.parse_expression(expr) if expr else None
        if tree is None:
            return None
        helpers = set(self.helpers)
        translator = _JavaExpr(self.types, self.known, self.helpers, self.dynamic)
        try:
            return how(translator, tree)
        except (_Unsupported, RecursionError):
            self.helpers.clear()
            self.helpers.update(helpers)
            return None

    def typed(self, expr: str | None) -> tuple[str, str] | None:
        """(Java-Code, Typ) eines Ausdrucks oder ``None``."""
        return self._translate(expr, lambda t, tree: (t.convert(tree), t.type_of(tree)))

    def number(self, expr: str | None) -> str | None:
        """Ausdruck, der eine Zahl sein muss (Schleifengrenzen)."""
        return self._translate(expr, lambda t, tree: t.number(tree, 0))

    def truth(self, expr: str | None) -> str | None:
        """Ausdruck als Bedingung für if/while."""
        return self._translate(expr, lambda t, tree: t.truthy(tree))

    def printable(self, expr: str | None) -> str | None:
        """Ausdruck für die Ausgabe: Zahlen ohne „.0“."""
        return self._translate(expr, lambda t, tree: t.as_text(tree, 0))

    def ask(self, text: str) -> str:
        self.uses_frage = True
        return f'frage("{_escape(text)}")'

    def condition(self, text: str, negate: bool = False) -> str:
        java = self.truth(T.condition_expression(text)) or self.ask(text)
        return f"!({java})" if negate else java

    def variable_text(self, name: str) -> str:
        """Variable in einer Textausgabe."""
        if self.types.get(name) == DOUBLE:
            self.helpers.add("text")
            return f"text({java_name(name)})"
        return java_name(name)

    # ------------------------------------------------------------ Programm
    def generate(self) -> str:
        if not self.programs:
            return "// Der Plan enthält kein Start-Element.\n"
        variables = Variables(self.programs)
        self.known = set(variables.names)
        self.types, self.dynamic = variables.types, variables.dynamic
        self._name_methods()
        methods: list[str] = []
        for index, program in enumerate(self.programs):
            self.lines = []
            self._times_depth = 0
            signature = "public static void main(String[] args)" if index == 0 else \
                f"static void {self.methods[index]}()"
            self.lines.append(f"{INDENT}// {_java_comment(program.name)}")
            for warning in program.warnings:
                self.lines.append(f"{INDENT}// Hinweis: {_java_comment(warning)}")
            self.lines.append(f"{INDENT}{signature} {{")
            self.block(program.body, 2, top_level=True)
            self.lines.append(f"{INDENT}}}")
            methods.extend(self.lines)
            methods.append("")
        # Variablen als Klassenfelder: Unterprogramme arbeiten mit denselben Werten
        defaults = {DOUBLE: "0", STRING: '""', BOOLEAN: "false"}
        fields = [f"{INDENT}static {self.types[name]} {java_name(name)} = {defaults[self.types[name]]};"
                  for name in variables.names]
        if fields:
            fields.append("")
        stubs = []
        for name, label in self.called.items():
            stubs += [f"{INDENT}// Unterprogramm „{_java_comment(label)}“",
                      f"{INDENT}static void {name}(Object... argumente) {{",
                      f"{INDENT}{INDENT}// TODO: Unterprogramm ausarbeiten", f"{INDENT}}}", ""]
        uses_scanner = self.uses_eingabe or self.uses_eingabe_text or self.uses_frage
        head = [f"// Automatisch erzeugt aus dem Programmablaufplan „{_java_comment(self.programs[0].name)}“",
                "// (BS Technik PAP Designer). Nicht erkannte Texte sind als TODO markiert.", ""]
        if uses_scanner:
            head += ["import java.util.Scanner;", ""]
        head.append(f"public class {self._class_name()} {{")
        if uses_scanner:
            head += [f"{INDENT}static final Scanner SCANNER = new Scanner(System.in);", ""]
        body = head + fields + methods + stubs + self._helper_methods()
        while body and body[-1] == "":
            body.pop()
        return "\n".join(body + ["}"]) + "\n"

    def _helper_methods(self) -> list[str]:
        one, two, three = INDENT, INDENT * 2, INDENT * 3
        helpers = []
        if self.uses_eingabe:
            helpers += [f"{one}// Liest eine Zahl ein (auch mit Komma); fragt bei Tippfehlern erneut.",
                        f"{one}static double eingabe(String text) {{",
                        f"{two}while (true) {{",
                        f"{three}System.out.print(text);",
                        f"{three}String zeile = SCANNER.nextLine().trim().replace(',', '.');",
                        f"{three}try {{",
                        f"{three}{one}double wert = Double.parseDouble(zeile);",
                        f"{three}{one}if (!Double.isNaN(wert) && !Double.isInfinite(wert)) {{",
                        f"{three}{two}return wert;",
                        f"{three}{one}}}",
                        f"{three}}} catch (NumberFormatException fehler) {{",
                        f"{three}{one}// keine Zahl: noch einmal fragen",
                        f"{three}}}",
                        f'{three}System.out.println("Bitte eine Zahl eingeben.");',
                        f"{two}}}",
                        f"{one}}}", ""]
        if self.uses_eingabe_text:
            helpers += [f"{one}// Liest einen Text ein.",
                        f"{one}static String eingabeText(String text) {{",
                        f"{two}System.out.print(text);",
                        f"{two}return SCANNER.nextLine().trim();",
                        f"{one}}}", ""]
        if self.uses_frage:
            helpers += [f"{one}static boolean frage(String text) {{",
                        f'{two}System.out.print(text + " (j/n) ");',
                        f'{two}return SCANNER.nextLine().trim().toLowerCase().startsWith("j");',
                        f"{one}}}", ""]
        if "text" in self.helpers:
            helpers += [f"{one}// Zahl als Text: 7 statt 7.0 – wie im Schreibtischtest.",
                        f"{one}static String text(double x) {{",
                        f"{two}if (x == Math.rint(x) && Math.abs(x) < 1e15) {{",
                        f"{three}return String.valueOf((long) x);",
                        f"{two}}}",
                        f"{two}return String.valueOf(x);",
                        f"{one}}}", ""]
        if "zahl" in self.helpers:
            helpers += [f"{one}// Text als Zahl (auch mit Komma). Ist der Text keine Zahl, kommt NaN heraus.",
                        f"{one}static double zahl(String text) {{",
                        f"{two}try {{",
                        f"{three}return Double.parseDouble(text.trim().replace(',', '.'));",
                        f"{two}}} catch (NumberFormatException fehler) {{",
                        f"{three}return Double.NaN;",
                        f"{two}}}",
                        f"{one}}}", ""]
        if "mod" in self.helpers:
            helpers += [f"{one}// Rest der Division; das Ergebnis hat das Vorzeichen des Teilers (-7 mod 3 = 2).",
                        f"{one}static double mod(double a, double b) {{",
                        f"{two}return a - b * Math.floor(a / b);",
                        f"{one}}}", ""]
        if "runden" in self.helpers:
            helpers += [f"{one}// Kaufmännisch runden: ab 5 wird aufgerundet (2,5 wird 3).",
                        f"{one}static double runden(double x) {{",
                        f"{two}return runden(x, 0);",
                        f"{one}}}", "",
                        f"{one}static double runden(double x, double stellen) {{",
                        f"{two}double faktor = Math.pow(10, (long) stellen);",
                        f"{two}return Math.signum(x) * Math.floor(Math.abs(x) * faktor + 0.5) / faktor + 0.0;",
                        f"{one}}}", ""]
        return helpers

    # ---------------------------------------------------------------- Helfer
    def emit(self, depth: int, text: str) -> None:
        self.lines.append(INDENT * depth + text)

    def comments(self, depth: int, comments: list[str]) -> None:
        for comment in comments:
            self.emit(depth, f"// {_java_comment(comment)}")

    def block(self, block: Block, depth: int, top_level: bool = False) -> None:
        statements = list(block)
        if top_level and statements and isinstance(statements[-1], EndStmt):
            statements = statements[:-1]
        for index, stmt in enumerate(statements):
            if _never_runs(stmt):
                # „while (false)“ lässt javac nicht zu: der Rumpf wäre unerreichbar
                text = stmt.condition if isinstance(stmt, WhileLoop) else stmt.header
                self.emit(depth, f"// Hinweis: Die Schleife „{_java_comment(text)}“ wird nie durchlaufen.")
                continue
            self.stmt(stmt, depth)
            if not _completes(stmt) and index < len(statements) - 1:
                # Java lehnt Anweisungen ab, die nie erreicht werden
                self.emit(depth, "// Hinweis: Die folgenden Bausteine des Plans werden nie erreicht.")
                break

    def loop_body(self, block: Block, depth: int) -> None:
        self._loops += 1
        try:
            self.block(block, depth)
        finally:
            self._loops -= 1

    def stmt(self, stmt, depth: int) -> None:
        if isinstance(stmt, Action):
            self.comments(depth, stmt.comments)
            getattr(self, f"action_{stmt.kind}", self.action_process)(stmt, depth)
        elif isinstance(stmt, If):
            self.comments(depth, stmt.comments)
            self.emit(depth, f"if ({self.condition(stmt.condition)}) {{")
            self.block(stmt.then_block, depth + 1)
            if len(stmt.else_block):
                self.emit(depth, "} else {")
                self.block(stmt.else_block, depth + 1)
            self.emit(depth, "}")
        elif isinstance(stmt, WhileLoop):
            self.comments(depth, stmt.comments)
            self.emit(depth, f"while ({self.condition(stmt.condition, stmt.negate)}) {{")
            self.loop_body(stmt.body, depth + 1)
            self.emit(depth, "}")
        elif isinstance(stmt, DoWhileLoop):
            self.comments(depth, stmt.comments)
            self.emit(depth, "do {")
            self.loop_body(stmt.body, depth + 1)
            self.emit(depth, f"}} while ({self.condition(stmt.condition, stmt.negate)});")
        elif isinstance(stmt, LimitLoop):
            self.limit_loop(stmt, depth)
        elif isinstance(stmt, Loop):
            self.emit(depth, "while (true) {")
            self.loop_body(stmt.body, depth + 1)
            self.emit(depth, "}")
        elif isinstance(stmt, Continue) and self._loops:
            self.emit(depth, "continue; // nächster Durchlauf")
        elif isinstance(stmt, Break) and self._loops:
            self.emit(depth, "break; // Schleife verlassen")
        elif isinstance(stmt, EndStmt):
            self.emit(depth, "return; // Ende")
        elif isinstance(stmt, (Unstructured, Break, Continue)):
            note = stmt.note if isinstance(stmt, Unstructured) else "Sprung aus einer Schleife"
            self.emit(depth, f"// Hinweis: nicht strukturierbar – {_java_comment(note)}")
            if not isinstance(stmt, Unstructured) or stmt.fatal:
                # lieber deutlich anhalten als mit falschem Ablauf weiterlaufen
                self.emit(depth, f'throw new IllegalStateException("{UNSTRUCTURED_MESSAGE}: {_escape(note)}");')

    def limit_loop(self, stmt: LimitLoop, depth: int) -> None:
        self.comments(depth, stmt.comments)
        header = T.parse_loop_header(stmt.header)
        footer = T.parse_loop_footer(stmt.footer) if stmt.footer else None
        self.emit(depth, f"// {_java_comment(stmt.header)}")
        start = end = step = None
        if header.kind == "for" and self.types.get(header.variable) == DOUBLE:
            start, end, step = (self.number(header.start), self.number(header.end), self.number(header.step))
        counting = None not in (start, end, step)
        repeat = leave = None
        if footer is not None:
            kind, cond = footer
            java = self.truth(cond) or self.ask(stmt.footer)
            repeat, leave = (f"!({java})", java) if kind == "until" else (java, f"!({java})")
        if footer is not None and not counting:
            self.emit(depth, "do {")
            self.loop_body(stmt.body, depth + 1)
            self.emit(depth, f"}} while ({repeat});")
            return
        if counting:
            var = java_name(header.variable)
            literal = _numeric_literal(header.step)
            if literal is not None:
                comparison = f"{var} {'>=' if literal < 0 else '<='} {end}"
            else:
                comparison = f"({step}) >= 0 ? {var} <= {end} : {var} >= {end}"
            self.emit(depth, f"for ({var} = {start}; {comparison}; {var} += {step}) {{")
            self.loop_body(stmt.body, depth + 1)
            if leave is not None and _block_completes(stmt.body):
                # zusätzliche Bedingung am Schleifenende
                self.emit(depth + 1, f"if ({leave}) {{")
                self.emit(depth + 2, "break;")
                self.emit(depth + 1, "}")
            self.emit(depth, "}")
            return
        counter = None
        if header.kind == "while" and self.truth(header.condition):
            self.emit(depth, f"while ({self.truth(header.condition)}) {{")
        elif header.kind == "times" and self.number(header.count):
            # eigener Zähler je Verschachtelungstiefe, der keine Variable des Plans verdeckt
            self._times_depth += 1
            base = "durchlauf" if self._times_depth == 1 else f"durchlauf{self._times_depth}"
            counter = _free_name(base, self.known | _JAVA_RESERVED)
            count = self.number(header.count)
            if re.fullmatch(r"\d+", count):
                self.emit(depth, f"for (int {counter} = 0; {counter} < {count}; {counter}++) {{")
            else:
                # Anzahl einmal bestimmen und abschneiden – wie im Schreibtischtest
                limit = _free_name(f"{counter}Ende", self.known | _JAVA_RESERVED)
                self.emit(depth, f"for (int {counter} = 0, {limit} = (int) ({count}); "
                                 f"{counter} < {limit}; {counter}++) {{")
        else:
            self.emit(depth, f"while ({self.ask(stmt.header)}) {{")
        self.loop_body(stmt.body, depth + 1)
        self.emit(depth, "}")
        if counter is not None:
            self._times_depth -= 1

    # ------------------------------------------------------------ Aktionen
    def action_input(self, stmt: Action, depth: int) -> None:
        names = T.input_variables(stmt.text)
        if not names:
            self.uses_eingabe_text = True
            self.emit(depth, f'eingabeText("{_escape(stmt.text)}: "); // TODO: Variable festlegen')
            return
        for name in names:
            kind = self.types.get(name, DOUBLE)
            if kind == STRING:
                self.uses_eingabe_text = True
                self.emit(depth, f'{java_name(name)} = eingabeText("{name}: ");')
            elif kind == BOOLEAN:
                self.emit(depth, f"{java_name(name)} = {self.ask(name + '?')};")
            else:
                self.uses_eingabe = True
                self.emit(depth, f'{java_name(name)} = eingabe("{name}: ");')

    def action_output(self, stmt: Action, depth: int) -> None:
        spec = T.output_spec(stmt.text, self.known)
        if spec.kind == "mixed":
            parts = []
            for kind, value in spec.parts:
                code = f'"{_escape(value)}"' if kind == "string" else self.printable(value)
                if code is None:
                    break
                # Rechnungen klammern, sonst verkettet Java „"x" + summe + 1“ als Text
                parts.append(code if kind == "string" or re.fullmatch(r"[\w.]+(\(.*\))?", code) else f"({code})")
            else:
                separator = ' + " " + '
                self.emit(depth, f"System.out.println({separator.join(parts)});")
                return
            strings = " ".join(value for kind, value in spec.parts if kind == "string") or _one_line(stmt.text)
            self.emit(depth, f'System.out.println("{_escape(strings)}"); // TODO: Werte ausgeben')
        elif spec.kind == "expression":
            code = self.printable(spec.value)
            if code is not None:
                self.emit(depth, f"System.out.println({code});")
            else:
                self.emit(depth, f'System.out.println("{_escape(stmt.text)}"); // TODO: Ausdruck übersetzen')
        elif spec.kind == "variables":
            parts = " + \", \" + ".join(self.variable_text(name) for name in spec.variables)
            self.emit(depth, f'System.out.println("{_escape(spec.value)}: " + {parts});')
        else:
            self.emit(depth, f'System.out.println("{_escape(spec.value)}");')

    def action_process(self, stmt: Action, depth: int) -> None:
        assignments = T.parse_assignments(stmt.text)
        if not assignments:
            for line in [line for line in stmt.text.splitlines() if line.strip()] or ["(leer)"]:
                self.emit(depth, f"// TODO: {_java_comment(line)}")
            return
        for name, expr in assignments:
            target, wanted = java_name(name), self.types.get(name, DOUBLE)
            result = self.typed(expr)
            code = None
            if result is not None:
                code, found = result
                if wanted == found:
                    pass
                elif wanted == DOUBLE and found == BOOLEAN:
                    code = f"({code}) ? 1 : 0"
                elif wanted == DOUBLE:
                    code = self.number(expr)  # wechselnde Eingabe als Zahl; reiner Text: nicht übersetzbar
                elif wanted == BOOLEAN and found == DOUBLE:
                    code = self.truth(expr)
                elif wanted == STRING and found == DOUBLE:
                    code = self.printable(expr)
                elif wanted == STRING:
                    code = f"String.valueOf({code})"
                else:
                    code = None
            if code is None:
                missing = T.unknown_names(expr, self.known)
                reason = f" – {', '.join(f'„{n}“' for n in missing)} erhält im Plan keinen Wert" if missing else ""
                self.emit(depth, f"// TODO: {_java_comment(f'{name} = {expr}')}{_java_comment(reason)}")
            else:
                self.emit(depth, f"{target} = {code};")

    def action_subprogram(self, stmt: Action, depth: int) -> None:
        call = T.call_parts(stmt.text)
        slug = T.slug(call[0] if call else stmt.text)
        if slug in self.method_names:
            # Abläufe haben keine Parameter: Sie arbeiten mit den gemeinsamen Variablen
            index = self.method_names[slug]
            note = f" // {_java_comment(stmt.text)}" if call and call[1] else ""
            self.emit(depth, (f"{self.methods[index]}();" if index else "main(new String[0]);") + note)
            return
        label = call[0] if call else stmt.text
        name = _free_name(T.lower_camel(label, f"unterprogramm{len(self.called) + 1}"),
                          (set(self.methods) | _JAVA_METHODS | _JAVA_RESERVED) - set(self.called))
        self.called.setdefault(name, stmt.text)
        arguments = [self.typed(arg) for arg in call[1]] if call else []
        if None in arguments:
            self.emit(depth, f"{name}(); // TODO: {_java_comment(stmt.text)}")
        else:
            self.emit(depth, f"{name}({', '.join(code for code, _ in arguments)});")

    def action_junction(self, stmt: Action, depth: int) -> None:
        pass
