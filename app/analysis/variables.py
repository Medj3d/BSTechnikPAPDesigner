"""Variablen eines Plans und ihre Typen.

Ein PAP kennt keine Typen. Damit Schreibtischtest, erzeugtes Python und
erzeugtes Java trotzdem dasselbe tun, wird für jede Variable einmal
ermittelt, wofür der Plan sie benutzt:

* **Zahl** (``double``)   – es wird mit ihr gerechnet, sie wird mit Zahlen
  verglichen oder dient als Schleifengrenze
* **Text** (``String``)   – sie bekommt Text zugewiesen, wird mit Text
  verglichen – oder ist eine Eingabe ohne jeden Hinweis (dann wird sie so
  ausgegeben, wie sie eingetippt wurde)
* **Wahrheitswert** (``boolean``) – sie bekommt wahr/falsch oder das Ergebnis
  eines Vergleichs

„Wechselnde“ Eingaben (``dynamic``) werden mit Text verglichen *und* zum
Rechnen benutzt (z. B. „solange x ≠ "ende"“ und „summe = summe + x“): Sie
sind Zahl, wenn die Eingabe wie eine Zahl aussieht, sonst Text.
"""

from __future__ import annotations

import ast

from app.analysis import text as T
from app.analysis.ast import Action, Block, DoWhileLoop, If, LimitLoop, Loop, Program, WhileLoop

DOUBLE, STRING, BOOLEAN = "double", "String", "boolean"
DEFAULTS = {DOUBLE: 0, STRING: "", BOOLEAN: False}
_NUM, _TXT, _BOOL = "num", "txt", "bool"

NUMERIC_FUNCTIONS = {"abs", "sqrt", "wurzel", "floor", "ceil", "sin", "cos", "tan", "exp", "log", "int",
                     "ganzzahl", "round", "runden", "pow", "min", "max"}
_ARITHMETIC = (ast.Sub, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ORDERING = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def walk(block: Block):
    """Alle Anweisungen eines Blocks, auch die verschachtelten."""
    for stmt in block:
        yield stmt
        if isinstance(stmt, If):
            yield from walk(stmt.then_block)
            yield from walk(stmt.else_block)
        elif isinstance(stmt, (WhileLoop, DoWhileLoop, LimitLoop, Loop)):
            yield from walk(stmt.body)


def static_type(node, types: dict, dynamic=frozenset()) -> str | None:
    """Typ eines Ausdrucks; ``None``, solange er von einer untypisierten Variablen abhängt."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return BOOLEAN
        return STRING if isinstance(node.value, str) else DOUBLE
    if isinstance(node, ast.Name):
        if node.id in types:
            return types[node.id]
        return DOUBLE if node.id in T.CONSTANTS else None
    if isinstance(node, ast.UnaryOp):
        return BOOLEAN if isinstance(node.op, ast.Not) else DOUBLE
    if isinstance(node, (ast.BoolOp, ast.Compare)):
        return BOOLEAN
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Add, ast.Mult)):
            left, right = static_type(node.left, types, dynamic), static_type(node.right, types, dynamic)
            if STRING in (left, right):
                # wechselnde Eingabe + Zahl ist eine Rechnung, keine Verkettung
                left_dynamic, right_dynamic = _is_dynamic(node.left, dynamic), _is_dynamic(node.right, dynamic)
                if (left_dynamic and (right == DOUBLE or right_dynamic)) or (right_dynamic and left == DOUBLE):
                    return DOUBLE
                return STRING
            if isinstance(node.op, ast.Add) and None in (left, right):
                return None
        return DOUBLE
    if isinstance(node, ast.IfExp):
        return static_type(node.body, types, dynamic) or static_type(node.orelse, types, dynamic)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return STRING if node.func.id == "str" else DOUBLE
    return DOUBLE


def _is_dynamic(node, dynamic) -> bool:
    return isinstance(node, ast.Name) and node.id in dynamic


class Variables:
    """Variablen aller Abläufe (Unterprogramme teilen sie mit dem Hauptprogramm) und ihre Typen."""

    def __init__(self, programs: list[Program]):
        self.names: list[str] = []
        self.inputs: set[str] = set()
        self.types: dict[str, str] = {}
        self.dynamic: set[str] = set()
        self._assignments: list[tuple[str, ast.AST]] = []
        self._counters: set[str] = set()          # Zählvariablen: sicher Zahlen
        self._trees: list[ast.AST] = []           # alle gelesenen Ausdrücke
        self._numeric_trees: list[ast.AST] = []   # Schleifengrenzen und Anzahlen
        statements = [stmt for program in programs for stmt in walk(program.body)]
        for stmt in statements:
            self._collect_names(stmt)
        known = set(self.names)
        for stmt in statements:
            self._collect_expressions(stmt, known)
        self._infer()

    # ---------------------------------------------------------- Sammeln
    def _add(self, name: str) -> None:
        if name not in self.names:
            self.names.append(name)

    def _collect_names(self, stmt) -> None:
        if isinstance(stmt, Action):
            if stmt.kind == "input":
                for name in T.input_variables(stmt.text):
                    self._add(name)
                    self.inputs.add(name)
            elif stmt.kind == "process":
                for name, expr in T.parse_assignments(stmt.text) or []:
                    self._add(name)
                    tree = T.parse_expression(expr)
                    if tree is not None:
                        self._assignments.append((name, tree))
        elif isinstance(stmt, LimitLoop):
            header = T.parse_loop_header(stmt.header)
            if header.kind == "for":
                self._add(header.variable)
                self._counters.add(header.variable)

    def _read(self, expr: str | None, numeric: bool = False) -> None:
        tree = T.parse_expression(expr) if expr else None
        if tree is not None:
            (self._numeric_trees if numeric else self._trees).append(tree)

    def _collect_expressions(self, stmt, known: set) -> None:
        if isinstance(stmt, Action) and stmt.kind == "output":
            spec = T.output_spec(stmt.text, known)
            if spec.kind == "expression":
                self._read(spec.value)
            for kind, value in spec.parts:
                if kind == "expression":
                    self._read(value)
        elif isinstance(stmt, (If, WhileLoop, DoWhileLoop)):
            self._read(T.condition_expression(stmt.condition))
        elif isinstance(stmt, LimitLoop):
            header = T.parse_loop_header(stmt.header)
            if header.kind == "for":
                for expr in (header.start, header.end, header.step):
                    self._read(expr, numeric=True)
            elif header.kind == "while":
                self._read(header.condition)
            elif header.kind == "times":
                self._read(header.count, numeric=True)
            footer = T.parse_loop_footer(stmt.footer) if stmt.footer else None
            if footer is not None:
                self._read(footer[1])

    # ------------------------------------------------------------ Typen
    def _infer(self) -> None:
        self._flags: dict[str, set] = {name: set() for name in self.names}
        self._text_assigned: set[str] = set()     # bekommt irgendwo Text zugewiesen
        for name in self._counters:
            self._flags[name].add(_NUM)
        self._links: set[tuple[str, str]] = set()
        trees = self._trees + self._numeric_trees + [tree for _, tree in self._assignments]
        self._fixpoint(trees)
        # Eingaben ohne jeden Hinweis bleiben Text – samt allem, was nur aus ihnen entsteht
        for name in self.names:
            if name in self.inputs and not self._flags[name]:
                self._flags[name].add(_TXT)
        self._fixpoint(trees)
        for name in self.names:
            flags = self._flags[name]
            if name in self._counters:
                kind = DOUBLE
            elif _TXT in flags and _NUM in flags:
                kind = STRING
                if name not in self._text_assigned:
                    self.dynamic.add(name)  # Zahl oder Text – je nach Eingabe
            elif _TXT in flags:
                kind = STRING
            elif _NUM in flags:
                kind = DOUBLE
            elif _BOOL in flags:
                kind = BOOLEAN
            else:
                kind = DOUBLE
            self.types[name] = kind

    def _kind(self, node) -> set:
        """Mögliche Arten eines Ausdrucks nach dem bisherigen Wissen (leer = unbekannt)."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return {_BOOL}
            return {_TXT} if isinstance(node.value, str) else {_NUM}
        if isinstance(node, ast.Name):
            if node.id in self._flags:
                return set(self._flags[node.id])
            return {_NUM} if node.id in T.CONSTANTS else set()
        if isinstance(node, ast.UnaryOp):
            return {_BOOL} if isinstance(node.op, ast.Not) else {_NUM}
        if isinstance(node, (ast.BoolOp, ast.Compare)):
            return {_BOOL}
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, (ast.Add, ast.Mult)):
                if self._is_text(node.left) or self._is_text(node.right):
                    return {_TXT}
                if isinstance(node.op, ast.Add) and not self._kind(node.left) and not self._kind(node.right):
                    return set()
            return {_NUM}
        if isinstance(node, ast.IfExp):
            return self._kind(node.body) | self._kind(node.orelse)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return {_TXT} if node.func.id == "str" else {_NUM}
        return {_NUM}

    def _is_text(self, node) -> bool:
        """Sicher Text? Eine Eingabe, die nur mit Text *verglichen* wird, kann auch eine Zahl sein."""
        if isinstance(node, ast.Name):
            flags = self._flags.get(node.id, set())
            return flags == {_TXT} and (node.id not in self.inputs or node.id in self._text_assigned)
        return self._kind(node) == {_TXT}

    def _mark(self, node, flag: str) -> bool:
        if isinstance(node, ast.Name) and node.id in self._flags and flag not in self._flags[node.id]:
            self._flags[node.id].add(flag)
            return True
        return False

    def _link(self, a, b) -> None:
        if isinstance(a, ast.Name) and isinstance(b, ast.Name) and a.id in self._flags and b.id in self._flags:
            self._links.add((a.id, b.id))

    def _fixpoint(self, trees: list) -> None:
        for _ in range(4 * len(self.names) + 8):
            changed = False
            for tree in self._numeric_trees:
                changed |= self._mark(tree, _NUM)
            for tree in trees:
                for node in ast.walk(tree):
                    changed |= self._evidence(node)
            for name, tree in self._assignments:
                kinds = self._kind(tree)
                if kinds == {_TXT}:
                    self._text_assigned.add(name)
                if not kinds <= self._flags[name]:
                    self._flags[name] |= kinds
                    changed = True
                # Kopien haben denselben Typ – in beide Richtungen („max = a“ und „b > max“)
                self._link(ast.Name(id=name), tree)
                if isinstance(tree, ast.IfExp):
                    self._link(ast.Name(id=name), tree.body)
                    self._link(ast.Name(id=name), tree.orelse)
            for a, b in self._links:
                merged = self._flags[a] | self._flags[b]
                if merged != self._flags[a] or merged != self._flags[b]:
                    self._flags[a], self._flags[b] = set(merged), set(merged)
                    changed = True
            if not changed:
                return

    def _evidence(self, node) -> bool:
        """Hinweise aus einem Teilausdruck: Rechnen → Zahl, Vergleich mit Text → Text."""
        changed = False
        if isinstance(node, ast.BinOp):
            left_text, right_text = self._is_text(node.left), self._is_text(node.right)
            if isinstance(node.op, _ARITHMETIC) or (isinstance(node.op, ast.Add) and not left_text and not right_text):
                changed |= self._mark(node.left, _NUM) | self._mark(node.right, _NUM)
            elif isinstance(node.op, ast.Mult):
                if left_text != right_text:
                    changed |= self._mark(node.right if left_text else node.left, _NUM)  # "-" * n
                elif not left_text:
                    changed |= self._mark(node.left, _NUM) | self._mark(node.right, _NUM)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            changed |= self._mark(node.operand, _NUM)
        elif isinstance(node, ast.Compare):
            operands = [node.left] + node.comparators
            for op, a, b in zip(node.ops, operands, operands[1:]):
                self._link(a, b)
                for name, other in ((a, b), (b, a)):
                    if isinstance(other, ast.Name):
                        continue  # Variable mit Variable: über die Verknüpfung
                    kinds = self._kind(other)
                    if kinds == {_TXT}:
                        changed |= self._mark(name, _TXT)
                    elif _NUM in kinds:
                        changed |= self._mark(name, _NUM)
                if isinstance(op, _ORDERING) and not self._is_text(a) and not self._is_text(b) \
                        and _TXT not in self._kind(a) | self._kind(b):
                    changed |= self._mark(a, _NUM) | self._mark(b, _NUM)  # „a > b“: Zahlen
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in NUMERIC_FUNCTIONS:
                for arg in node.args:
                    if not (node.func.id in ("int", "ganzzahl") and _TXT in self._kind(arg)):
                        changed |= self._mark(arg, _NUM)
            elif node.func.id == "len":
                for arg in node.args:
                    changed |= self._mark(arg, _TXT)
        return changed
