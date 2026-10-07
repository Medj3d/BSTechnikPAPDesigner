"""Sichere Auswertung einfacher Ausdrücke für den Schreibtischtest.

Ausgewertet wird über den Syntaxbaum von Python mit einer strengen
Positivliste: Zahlen, Zeichenketten, Variablen, Rechen- und
Vergleichsoperatoren, und/oder/nicht sowie wenige Funktionen. Attribute,
Importe, Lambdas usw. werden abgelehnt. Es wird nie ``eval`` auf Freitext
angewendet.
"""

from __future__ import annotations

import ast
import math
import operator

from app.analysis import text as T

MAX_POWER = 10_000
MAX_STRING = 100_000
MAX_INT_BITS = 10_000  # ca. 3000 Dezimalstellen


class EvaluationError(Exception):
    pass


def _limited(value):
    """Begrenzt Zwischenergebnisse, damit Schleifen wie x = x * x nicht ausufern."""
    if isinstance(value, int) and not isinstance(value, bool) and value.bit_length() > MAX_INT_BITS:
        raise EvaluationError("Die Zahl ist zu groß.")
    if isinstance(value, str) and len(value) > MAX_STRING:
        raise EvaluationError("Die Zeichenkette ist zu lang.")
    return value


_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_COMPARE = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}


def runden(x, stellen=0):
    """Kaufmännisch runden: ab 5 wird aufgerundet (2,5 → 3; -2,5 → -3)."""
    faktor = 10 ** int(stellen)
    wert = math.floor(abs(x) * faktor + 0.5) / faktor
    wert = wert if x >= 0 else -wert
    return int(wert) if int(stellen) <= 0 else wert


def _power(base, exponent):
    """pow(a, b) mit denselben Grenzen wie der Operator **."""
    if isinstance(exponent, (int, float)) and abs(exponent) > MAX_POWER:
        raise ValueError("Der Exponent ist zu groß.")
    if isinstance(base, int) and isinstance(exponent, int) and exponent > 0             and max(abs(base), 2).bit_length() * exponent > MAX_INT_BITS * 2:
        raise OverflowError("Die Zahl ist zu groß.")
    return base ** exponent


_FUNCTIONS = {
    "abs": abs, "min": min, "max": max, "round": runden, "runden": runden, "int": int, "float": float,
    "str": lambda value: text_of(value), "len": len, "sqrt": math.sqrt, "wurzel": math.sqrt, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "floor": math.floor, "ceil": math.ceil, "ganzzahl": int, "exp": math.exp,
    "log": math.log, "pow": _power,
}
assert set(_FUNCTIONS) == set(T.FUNCTIONS), "Funktionstabellen von Text-Deutung und Auswertung weichen ab"
_CONSTANTS = {"pi": math.pi, "True": True, "False": False}


class Scope:
    """Variablen für eine Auswertung.

    Variablen des Plans, die noch keinen Wert haben, liefern den Startwert
    ihres Typs (0, leerer Text, falsch) – wie in den erzeugten Programmen.
    ``missing`` sammelt ihre Namen, damit der Schreibtischtest darauf hinweist.
    """

    def __init__(self, values: dict, defaults: dict | None = None, missing: list | None = None):
        self.values = values
        self.defaults = defaults or {}
        self.missing = missing if missing is not None else []

    def __contains__(self, name) -> bool:
        return name in self.values or name in self.defaults

    def __getitem__(self, name):
        if name in self.values:
            return self.values[name]
        if name not in self.missing:
            self.missing.append(name)
        return self.defaults[name]


def text_of(value) -> str:
    """Zahl oder Wahrheitswert als Text – für str() und für „Text + Zahl“ (7 statt 7.0)."""
    if isinstance(value, bool):
        return "wahr" if value else "falsch"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return safe_str(value)


def _eval(node, variables):
    if isinstance(node, ast.Expression):
        return _eval(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)):
            return node.value
        raise EvaluationError("Dieser Wert wird nicht unterstützt.")
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise EvaluationError(f"Die Variable „{node.id}“ hat noch keinen Wert.")
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, variables)
        try:
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return +value
        except TypeError as exc:
            raise EvaluationError(f"Rechnung nicht möglich ({exc}).") from exc
        if isinstance(node.op, ast.Not):
            return not value
        raise EvaluationError("Dieser Operator wird nicht unterstützt.")
    if isinstance(node, ast.BinOp):
        op = _BINARY.get(type(node.op))
        if op is None:
            raise EvaluationError("Dieser Operator wird nicht unterstützt.")
        left, right = _eval(node.left, variables), _eval(node.right, variables)
        if isinstance(node.op, ast.Add) and isinstance(left, str) != isinstance(right, str):
            # Text + Zahl wird verkettet – wie in den erzeugten Programmen
            left, right = (left, text_of(right)) if isinstance(left, str) else (text_of(left), right)
        if isinstance(node.op, ast.Mult) and (isinstance(left, str) or isinstance(right, str)):
            # Text * Kommazahl: die Anzahl wird abgeschnitten
            left = int(left) if isinstance(left, float) and math.isfinite(left) else left
            right = int(right) if isinstance(right, float) and math.isfinite(right) else right
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > MAX_POWER:
            raise EvaluationError("Der Exponent ist zu groß.")
        if isinstance(node.op, ast.Mult) and (isinstance(left, str) or isinstance(right, str)):
            count = right if isinstance(left, str) else left
            if isinstance(count, int) and count * max(len(str(left)), len(str(right))) > MAX_STRING:
                raise EvaluationError("Die Zeichenkette wäre zu lang.")
        if isinstance(node.op, ast.Pow) and isinstance(left, int) and isinstance(right, int) and right > 0 \
                and max(abs(left), 2).bit_length() * right > MAX_INT_BITS * 2:
            raise EvaluationError("Die Zahl ist zu groß.")
        try:
            return _limited(op(left, right))
        except ZeroDivisionError as exc:
            raise EvaluationError("Division durch null.") from exc
        except (TypeError, ValueError, OverflowError) as exc:
            raise EvaluationError(f"Rechnung nicht möglich ({exc}).") from exc
    if isinstance(node, ast.BoolOp):
        values = node.values
        if isinstance(node.op, ast.And):
            result = True
            for value in values:
                result = _eval(value, variables)
                if not result:
                    return result
            return result
        result = False
        for value in values:
            result = _eval(value, variables)
            if result:
                return result
        return result
    if isinstance(node, ast.Compare):
        left = _eval(node.left, variables)
        for op_node, comparator in zip(node.ops, node.comparators):
            op = _COMPARE.get(type(op_node))
            if op is None:
                raise EvaluationError("Dieser Vergleich wird nicht unterstützt.")
            right = _eval(comparator, variables)
            try:
                if not op(left, right):
                    return False
            except TypeError as exc:
                raise EvaluationError("Diese Werte lassen sich nicht vergleichen.") from exc
            left = right
        return True
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS or node.keywords:
            raise EvaluationError("Diese Funktion wird nicht unterstützt.")
        args = [_eval(arg, variables) for arg in node.args]
        try:
            return _limited(_FUNCTIONS[node.func.id](*args))
        except (TypeError, ValueError, OverflowError) as exc:
            raise EvaluationError(f"Funktion „{node.func.id}“: {exc}") from exc
    if isinstance(node, ast.IfExp):
        return _eval(node.body, variables) if _eval(node.test, variables) else _eval(node.orelse, variables)
    raise EvaluationError("Dieser Ausdruck wird nicht unterstützt.")


def evaluate(expression: str, variables, condition: bool = False):
    """Wertet einen Ausdruck in PAP-Schreibweise aus. Wirft ``EvaluationError``."""
    expr = T.normalize_expression(expression, condition=condition)
    if not expr:
        raise EvaluationError("Kein Ausdruck vorhanden.")
    if len(expr) > 2000:
        raise EvaluationError("Der Ausdruck ist zu lang.")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise EvaluationError("Der Text ist kein auswertbarer Ausdruck.") from exc
    return _eval(tree, variables)


def evaluate_condition(text: str, variables) -> bool:
    return bool(evaluate(text, variables, condition=True))


def parse_number(raw: str):
    """Eingabe als Zahl (auch mit Komma) oder ``None``, wenn es keine ist."""
    value = raw.strip()
    if not value or "_" in value:
        return None
    for convert in (int, float):
        try:
            result = convert(value.replace(",", ".") if convert is float else value)
        except ValueError:
            continue
        if isinstance(result, float) and not math.isfinite(result):
            return None  # „inf“ und „nan“ sind Wörter, keine Zahlen
        if isinstance(result, int) and result.bit_length() > MAX_INT_BITS:
            return None
        return result
    return None


def parse_value(raw: str):
    """Eingabewert: Zahl, wenn die Eingabe wie eine Zahl aussieht – sonst Text.

    Wörter wie ja/nein/wahr/falsch bleiben Text, wie in den erzeugten Programmen.
    """
    number = parse_number(raw)
    return raw.strip() if number is None else number


def display(value) -> str:
    """Wert, wie ihn die Ausgabe zeigt (ganze Zahlen ohne „,0“, Dezimalkomma)."""
    if isinstance(value, bool):
        return "wahr" if value else "falsch"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.10g}".replace(".", ",")
    return safe_str(value)


def format_value(value) -> str:
    if isinstance(value, bool):
        return "wahr" if value else "falsch"
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return f"{value:.1f}".replace(".", ",")
        return f"{value:.6g}".replace(".", ",")
    if isinstance(value, str):
        return f"„{value}“"
    return safe_str(value)


def safe_str(value) -> str:
    """``str()`` ohne Absturz bei sehr großen Zahlen."""
    try:
        return str(value)
    except ValueError:  # mehr als 4300 Stellen
        return "(sehr große Zahl)"
