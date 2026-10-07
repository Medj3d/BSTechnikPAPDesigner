"""Deutung der frei geschriebenen Bausteintexte.

PAP-Texte sind Freitext („Anzahl n einlesen“, „summe = summe + x“,
„n > 0 ?“, „Für i = 1 bis n“). Diese Funktionen erkennen darin übliche
Muster; was nicht erkannt wird, bleibt Freitext (Aufrufer entscheiden, wie
sie damit umgehen). Gemeinsam genutzt von Code-Erzeugung und
Schreibtischtest.
"""

from __future__ import annotations

import ast
import keyword
import re
from dataclasses import dataclass

_LETTER = "A-Za-z_ÄÖÜäöüß"
IDENT = re.compile(rf"[{_LETTER}][{_LETTER}0-9]*")
IDENT_PATTERN = rf"[{_LETTER}][{_LETTER}0-9]*"

INPUT_STOPWORDS = {
    "eingabe", "eingaben", "einlesen", "eingeben", "lies", "lese", "lesen", "ein", "wert", "werte",
    "anzahl", "zahl", "zahlen", "von", "der", "die", "das", "den", "dem", "des", "und", "bitte",
    "benutzer", "tastatur", "nach", "in", "variable", "variablen", "eine", "einen", "einer", "neue",
    "neuen", "neuer", "abfragen", "abfrage", "input", "read", "erfassen", "vom", "mit",
    "gib", "gebe", "geben", "sowie", "oder",
}
OUTPUT_STOPWORDS = {
    "ausgabe", "ausgeben", "gib", "gebe", "aus", "zeige", "zeigen", "anzeigen", "drucke", "drucken",
    "schreibe", "schreiben", "print", "melde", "melden", "der", "die", "das", "den", "dem", "des",
    "und", "von", "am", "auf", "bildschirm", "ergebnis", "wert", "werte", "an",
}

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def slug(text: str, default: str = "unterprogramm") -> str:
    """Bezeichner aus Freitext: „Summe berechnen“ → „summe_berechnen“."""
    words = re.findall(r"[A-Za-z0-9]+", text.translate(_UMLAUTS))
    name = "_".join(w.lower() for w in words)
    if not name:
        return default
    if name[0].isdigit():
        name = "_" + name
    return name


def camel(text: str, default: str = "Programm") -> str:
    words = re.findall(r"[A-Za-z0-9]+", text.translate(_UMLAUTS))
    name = "".join(w[:1].upper() + w[1:] for w in words)
    if not name or name[0].isdigit():
        return default
    return name


def lower_camel(text: str, default: str = "unterprogramm") -> str:
    name = camel(text, "")
    return (name[:1].lower() + name[1:]) if name else default


def is_identifier(name: str) -> bool:
    """Gültiger Variablenname (auch mit Umlauten, z. B. „Länge“), kein Schlüsselwort."""
    return bool(re.fullmatch(IDENT_PATTERN, name)) and not keyword.iskeyword(name)


# ----------------------------------------------------------------- Ausdrücke
_QUOTES = [("„", '"'), ("“", '"'), ("”", '"'), ("’", "'"), ("‘", "'")]
_OPERATORS = [("≠", "!="), ("<>", "!="), ("≤", "<="), ("≥", ">="), ("×", "*"), ("·", "*"), ("÷", "/"),
              ("²", "**2"), ("³", "**3"), ("^", "**"), ("&&", " and "), ("||", " or ")]
_STRING_LITERAL = re.compile(r"(\"[^\"]*\"|'[^']*')")
_NOT_CALLS = {"and", "or", "not", "in", "if", "else", "is"}

# Funktionen, die Schreibtischtest und Code-Erzeugung kennen: Name → erlaubte Anzahl
# Argumente (None = mindestens zwei). Alles andere gilt als nicht auswertbar.
FUNCTIONS: dict[str, tuple | None] = {
    "abs": (1,), "sqrt": (1,), "wurzel": (1,), "floor": (1,), "ceil": (1,), "sin": (1,), "cos": (1,),
    "tan": (1,), "exp": (1,), "log": (1,), "int": (1,), "ganzzahl": (1,), "float": (1,), "str": (1,),
    "len": (1,), "round": (1, 2), "runden": (1, 2), "pow": (2,), "min": None, "max": None,
}
CONSTANTS = {"pi"}
# Funktionen mit genau einem Argument: darin ist „6,25“ ein Dezimalkomma
_SINGLE_ARGUMENT = {name for name, arity in FUNCTIONS.items() if arity == (1,)}

_ALLOWED_BINARY = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_COMPARE = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _normalize_code(code: str, condition: bool, parens: list) -> str:
    """Ersetzungen für einen Abschnitt außerhalb von Zeichenketten."""
    for old, new in _OPERATORS:
        code = code.replace(old, new)
    code = re.sub(r"\bund\b|\bAND\b", " and ", code, flags=re.IGNORECASE)
    code = re.sub(r"\boder\b|\bOR\b", " or ", code, flags=re.IGNORECASE)
    code = re.sub(r"\bnicht\b|\bNOT\b", " not ", code, flags=re.IGNORECASE)
    code = re.sub(r"\bwahr\b", "True", code, flags=re.IGNORECASE)
    code = re.sub(r"\bfalsch\b", "False", code, flags=re.IGNORECASE)
    code = re.sub(r"\bmod\b", "%", code, flags=re.IGNORECASE)
    code = re.sub(r"\bdiv\b", "//", code, flags=re.IGNORECASE)
    code = _decimal_commas(code, parens)
    if condition:
        # einzelnes „=“ in einer Bedingung ist ein Vergleich
        code = re.sub(r"(?<![<>=!:])=(?!=)", "==", code)
    return re.sub(r" {2,}", " ", code)


def _decimal_commas(code: str, parens: list) -> str:
    """Deutsches Dezimalkomma „2,5“ → „2.5“ – nicht zwischen Funktionsargumenten („max(3,4)“).

    ``parens`` merkt sich je offener Klammer: ``None`` (Rechenklammer) oder den
    Funktionsnamen. In Funktionen mit genau einem Argument („wurzel(6,25)“) ist
    das Komma ebenfalls ein Dezimalkomma.
    """
    out = []
    for i, ch in enumerate(code):
        if ch == "(":
            before = re.search(rf"({IDENT_PATTERN})\s*$", code[:i])
            parens.append(before.group(1) if before and before.group(1) not in _NOT_CALLS else None)
        elif ch == ")":
            if parens:
                parens.pop()
        elif ch == "," and 0 < i < len(code) - 1 and code[i - 1].isdigit() and code[i + 1].isdigit() \
                and (not parens or parens[-1] is None or parens[-1] in _SINGLE_ARGUMENT):
            out.append(".")
            continue
        out.append(ch)
    return "".join(out)


def normalize_expression(text: str, condition: bool = False) -> str:
    """PAP-Schreibweise → Python-Schreibweise (Operatoren, deutsche Wörter).

    Zeichenketten in Anführungszeichen bleiben unverändert.
    """
    expr = " ".join(text.replace("\n", " ").split())
    if condition:
        expr = expr.rstrip("?").strip()
    for old, new in _QUOTES:
        expr = expr.replace(old, new)
    parens: list = []
    parts = _STRING_LITERAL.split(expr)
    result = [part if index % 2 else _normalize_code(part, condition, parens)
              for index, part in enumerate(parts)]
    return "".join(result).strip()


def _supported_node(node, any_call: bool = False) -> bool:
    """Nur was der Schreibtischtest auswerten kann – sonst rechnen die erzeugten
    Programme etwas anderes (z. B. „x^2“ als XOR) oder stürzen ab."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float, str, bool))
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.UnaryOp):
        return isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)) and _supported_node(node.operand)
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, _ALLOWED_BINARY) and _supported_node(node.left) and _supported_node(node.right)
    if isinstance(node, ast.BoolOp):
        return all(_supported_node(value) for value in node.values)
    if isinstance(node, ast.Compare):
        return all(isinstance(op, _ALLOWED_COMPARE) for op in node.ops) \
            and all(_supported_node(n) for n in [node.left] + node.comparators)
    if isinstance(node, ast.IfExp):
        return all(_supported_node(n) for n in (node.test, node.body, node.orelse))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            return False
        if not all(_supported_node(arg) for arg in node.args):
            return False
        if any_call:
            return True
        if node.func.id not in FUNCTIONS:
            return False
        arity = FUNCTIONS[node.func.id]
        return len(node.args) >= 2 if arity is None else len(node.args) in arity
    return False


def parse_expression(expr: str):
    """Syntaxbaum eines auswertbaren Ausdrucks oder ``None``."""
    if not expr:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        return None
    return tree.body if _supported_node(tree.body) else None


def is_python_expression(expr: str) -> bool:
    """Ist der Text ein Ausdruck, den Schreibtischtest und Code-Erzeugung verstehen?"""
    return parse_expression(expr) is not None


def call_parts(text: str) -> tuple[str, list[str]] | None:
    """Unterprogramm-Text, der schon ein Aufruf ist: „berechne(x, y)“ → („berechne“, [„x“, „y“])."""
    try:
        body = ast.parse(normalize_expression(text), mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        return None
    if not isinstance(body, ast.Call) or not isinstance(body.func, ast.Name) or body.keywords             or not all(_supported_node(arg) for arg in body.args):
        return None
    return body.func.id, [ast.unparse(arg) for arg in body.args]


def condition_expression(text: str) -> str | None:
    """Bedingung als Python-Ausdruck oder ``None``, wenn sie nicht erkannt wird."""
    expr = normalize_expression(text, condition=True)
    return expr if is_python_expression(expr) else None


_COMPARISON_PREFIX = re.compile(r"^\s*(<=|>=|<>|!=|==|=|<|>|≠|≤|≥)")


def branch_condition(decision_text: str, label: str) -> str | None:
    """Bedingung eines Ausgangs einer Mehrfachverzweigung.

    Verzweigung „wahl“ mit Ausgang „2“ → „wahl = 2“; Verzweigung „x ?“ mit
    Ausgang „< 0“ → „x < 0“; Ausgang „rot“ → „farbe = "rot"“ (Text). Ohne
    Beschriftung ``None``.
    """
    label = " ".join((label or "").split())
    if not label:
        return None
    subject = " ".join(decision_text.split()).rstrip("?").strip()
    if _COMPARISON_PREFIX.match(label):
        return f"{subject} {label}"
    # Wörter sind Text („rot“, „sehr gut“) – außer wahr/falsch und fertigen Ausdrücken
    value = normalize_expression(label)
    is_word = bool(re.fullmatch(IDENT_PATTERN, label)) and value not in ("True", "False")
    if (is_word or not is_python_expression(value)) and '"' not in label:
        return f'{subject} = "{label}"'
    return f"{subject} = {label}"


def is_choice(decision_text: str, labels: list[str]) -> bool:
    """Wählen zwei Ausgänge über Werte statt über ja/nein („1“/„2“, „< 10“/„>= 10“, „rot“/„blau“)?

    Nur wenn die Verzweigung selbst keine Bedingung ist (sondern z. B. nur „x“
    oder „x ?“) und beide Ausgänge beschriftet sind. Ob die Beschriftungen
    ja/nein bedeuten, prüft der Aufrufer.
    """
    if not all(" ".join((label or "").split()) for label in labels):
        return False
    subject = " ".join(decision_text.split()).rstrip("?").strip()
    tree = parse_expression(normalize_expression(subject))
    if tree is None:
        return False  # Freitext-Frage: ja/nein nach Reihenfolge
    is_condition = isinstance(tree, (ast.Compare, ast.BoolOp)) \
        or (isinstance(tree, ast.UnaryOp) and isinstance(tree.op, ast.Not)) \
        or (isinstance(tree, ast.Constant) and isinstance(tree.value, bool))
    return not is_condition


def names_in(expr: str) -> list[str]:
    """Variablennamen eines Ausdrucks (ohne Funktionsnamen und Konstanten wie wahr/falsch)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return []
    functions = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and id(node) not in functions and node.id not in found \
                and node.id not in {"True", "False", "None"}:
            found.append(node.id)
    return found


def unknown_names(expr: str, known) -> list[str]:
    """Namen, die im Plan nie einen Wert bekommen (weder Variable noch Konstante wie pi)."""
    return [name for name in names_in(expr) if name not in known and name not in CONSTANTS]


# ----------------------------------------------------------------- Zuweisung
ASSIGN = re.compile(rf"^\s*({IDENT_PATTERN})\s*(?::=|←|<-|=(?!=))\s*(.+?)\s*;?\s*$")


def parse_assignments(text: str) -> list[tuple[str, str]] | None:
    """„x = x + 1“, „summe := 0“, „i ← i + 1“ (mehrere Zeilen oder durch ; getrennt).

    Gibt ``None`` zurück, wenn nicht alle Teile als Zuweisung erkannt werden.
    """
    parts = [p.strip() for p in re.split(r"[\n;]", text) if p.strip()]
    if not parts:
        return None
    result = []
    for part in parts:
        match = ASSIGN.match(part)
        if not match:
            return None
        name, expr = match.group(1), normalize_expression(match.group(2))
        if not is_identifier(name) or not is_python_expression(expr):
            return None
        result.append((name, expr))
    return result


# ------------------------------------------------------------ Ein-/Ausgabe
_QUOTED = re.compile(r'("[^"]*"|„[^“”"]*[“”"]|“[^“”"]*[”"])')
_CHOICE_HINT = re.compile(r"\([^()]*/[^()]*\)")       # „(ja/nein)“, „(j/n)“
# Substantive aus den Füllwörtern, die selbst der Variablenname sein können
_INPUT_NOUNS = {"zahl", "zahlen", "wert", "werte", "anzahl"}
_SEPARATOR = r"\s*(?:,|;|&|\bund\b|\bsowie\b)\s*"


def input_variables(text: str) -> list[str]:
    """Variablennamen aus einem Eingabetext („Anzahl n einlesen“ → [n]).

    Text in Anführungszeichen ist die Aufforderung an den Benutzer
    („"Wie alt bist du?" alter“ → [alter]), ebenso Hinweise wie „(ja/nein)“.
    """
    cleaned = _CHOICE_HINT.sub(" ", _QUOTED.sub(" ", text))
    return _input_variables(cleaned) or _input_variables(text)


def _input_variables(text: str) -> list[str]:
    tokens = [(m.group(0), m.start(), m.end()) for m in IDENT.finditer(text)
              if m.group(0).lower() not in ("und", "sowie", "oder")]
    names = []
    for index, (token, start, end) in enumerate(tokens):
        lower = token.lower()
        if not is_identifier(token):
            continue
        if lower not in INPUT_STOPWORDS:
            names.append(token)
        elif lower in _INPUT_NOUNS and _enumerated(text, tokens, index):
            names.append(token)  # „summe und anzahl einlesen“: anzahl ist hier ein Name
    candidates = list(dict.fromkeys(names))
    if not candidates:
        # „Zahl einlesen“, „Gib eine Zahl ein“, „Anzahl der Werte einlesen“: das Substantiv ist der Name
        nouns = [token for token, _, _ in tokens if token.lower() in _INPUT_NOUNS]
        return nouns[:1]
    # Substantive (Großschreibung, länger als 3 Zeichen, ohne Ziffer) sind meist
    # Beschreibung: „Anzahl n einlesen“, „Radius r eingeben“. „Zahl1“ ist ein Name.
    short = [t for t in candidates if not (t[0].isupper() and len(t) > 3 and not any(c.isdigit() for c in t))]
    if short:
        return short
    # Aufzählung: „Länge und Breite einlesen“, „Eingabe: Name, Alter“
    if len(candidates) > 1 and _is_enumeration(text, candidates):
        return candidates
    return candidates[-1:]


def _enumerated(text: str, tokens: list, index: int) -> bool:
    """Steht das Wort in einer Aufzählung mit einem Namen („summe und anzahl“) – und
    nicht als Beschreibung vor einem Namen („Zahl a und Zahl b“)?"""
    token, start, end = tokens[index]

    def is_name(other: int) -> bool:
        return 0 <= other < len(tokens) and tokens[other][0].lower() not in INPUT_STOPWORDS

    if index + 1 < len(tokens) and is_name(index + 1) and not text[end:tokens[index + 1][1]].strip():
        return False  # „zahl b“: Beschreibung
    before = index > 0 and is_name(index - 1) and \
        re.fullmatch(_SEPARATOR, text[tokens[index - 1][2]:start], flags=re.IGNORECASE) is not None
    after = is_name(index + 1) and \
        re.fullmatch(_SEPARATOR, text[end:tokens[index + 1][1]], flags=re.IGNORECASE) is not None
    return bool(before or after)


def _is_enumeration(text: str, names: list[str]) -> bool:
    """Stehen die Namen nur durch „und“, „sowie“ oder Kommas getrennt hintereinander?"""
    position = text.find(names[0])
    if position < 0:
        return False
    position += len(names[0])
    for name in names[1:]:
        index = text.find(name, position)
        if index < 0:
            return False
        if not re.fullmatch(r"\s*(?:,|;|&|\bund\b|\bsowie\b)?\s*", text[position:index], flags=re.IGNORECASE):
            return False
        position = index + len(name)
    return True


@dataclass
class OutputSpec:
    kind: str       # "string" | "expression" | "variables" | "mixed" | "text"
    value: str
    variables: tuple = ()
    # „mixed“: Folge aus („string“, Text) und („expression“, Python-Ausdruck)
    parts: tuple = ()


_OUTPUT_PREFIX = re.compile(r"^\s*(ausgabe|gib|zeige|drucke|schreibe)\b\s*:?\s*", re.IGNORECASE)
_OUTPUT_SUFFIX = re.compile(r"\s*\b(ausgeben|aus|anzeigen|drucken)\s*$", re.IGNORECASE)


def _value_list(node) -> list | None:
    """„x, y“ und „x und y“ zählen Werte auf – das ist keine Rechnung."""
    if isinstance(node, ast.Tuple):
        return list(node.elts)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And) \
            and all(isinstance(value, ast.Name) for value in node.values):
        return list(node.values)
    return None


def _parse_output_values(expr: str, known: dict) -> list | None:
    """Ausdruck(sliste) einer Ausgabe als Syntaxbäume – nur mit bekannten Variablen."""
    try:
        body = ast.parse(expr, mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        return None
    elements = _value_list(body) or [body]
    for element in elements:
        source = ast.unparse(element)
        names = names_in(source)
        if not _supported_node(element) or not names or not all(n in known for n in names):
            return None
    return elements


def _mixed_output(text: str, known: set) -> OutputSpec | None:
    """„"Die Summe ist" summe“, „Ausgabe "Summe:", summe“ → Text und Wert(e)."""
    segments = _QUOTED.split(text)
    parts: list[tuple[str, str]] = []
    for index, segment in enumerate(segments):
        if index % 2:
            parts.append(("string", " ".join(segment[1:-1].split())))  # ohne Rand-Leerzeichen, wie im Code
            continue
        core = segment
        if index == 0:
            core = _OUTPUT_PREFIX.sub("", core)
        if index == len(segments) - 1:
            core = _OUTPUT_SUFFIX.sub("", core)
        core = core.strip().strip(",;+&").strip()
        if not core:
            continue
        elements = _parse_output_values(normalize_expression(core), known)
        if elements is None:
            return None
        parts.extend(("expression", ast.unparse(element)) for element in elements)
    if not any(kind == "expression" for kind, _ in parts):
        # nur Texte („"Willkommen"“ und darunter „"zum Rechner"“): alle ausgeben
        return OutputSpec("string", " ".join(value for _, value in parts))
    return OutputSpec("mixed", text, parts=tuple(parts))


def output_spec(text: str, known_variables: set[str] | None = None) -> OutputSpec:
    """Deutet einen Ausgabetext."""
    exact = set(known_variables or set())   # „Summe“ und „summe“ können zwei Variablen sein
    known = {v.lower(): v for v in sorted(exact, reverse=True)}
    stripped = " ".join(text.split())
    quoted = _QUOTED.search(stripped)
    if quoted:
        mixed = _mixed_output(stripped, exact)
        if mixed is not None:
            return mixed
        return OutputSpec("string", " ".join(quoted.group(0)[1:-1].split()))
    core = _OUTPUT_PREFIX.sub("", stripped)
    core = _OUTPUT_SUFFIX.sub("", core).strip()
    expr = normalize_expression(core)
    elements = _parse_output_values(expr, exact) if core else None
    if elements is not None and len(elements) == 1 and _value_list(ast.parse(expr, mode="eval").body) is None:
        return OutputSpec("expression", expr, tuple(names_in(expr)))
    if elements is not None and not all(isinstance(element, ast.Name) for element in elements):
        # „Ausgabe: x, y + 1“: mehrere Werte nebeneinander
        return OutputSpec("mixed", stripped, parts=tuple(("expression", ast.unparse(e)) for e in elements))
    tokens = IDENT.findall(stripped)

    def variable(token: str) -> str:
        return token if token in exact else known[token.lower()]

    matches = [variable(t) for t in tokens if t.lower() in known and t.lower() not in OUTPUT_STOPWORDS]
    if not matches:
        # Variable heißt wie ein Füllwort: „Ergebnis ausgeben“ mit der Variablen ergebnis
        matches = [variable(t) for t in tokens if t.lower() in known]
    unique = tuple(dict.fromkeys(matches))
    if unique:
        # Beschriftung ohne Verben wie „ausgeben“: „Mittelwert ausgeben“ → „Mittelwert“
        words = [w for w in stripped.replace(":", " ").split()
                 if w.lower().strip(",;") not in OUTPUT_STOPWORDS - {"und"} or w.lower().strip(",;") in known]
        words = [w for i, w in enumerate(words) if i == 0 or w.lower() != words[i - 1].lower()]
        while words and words[0].lower() == "und":
            words.pop(0)
        while words and words[-1].lower() == "und":
            words.pop()
        return OutputSpec("variables", " ".join(words) or stripped, unique)
    return OutputSpec("text", stripped)


# ------------------------------------------------------------- Schleifen
@dataclass
class LoopHeader:
    kind: str                 # "for" | "while" | "times" | "unknown"
    variable: str = ""
    start: str = ""
    end: str = ""
    step: str = "1"
    condition: str = ""       # Python-Ausdruck (while)
    count: str = ""           # Python-Ausdruck (times)


FOR_PATTERN = re.compile(
    rf"^\s*(?:für|fuer|for|zähle|zaehle)\s+({IDENT_PATTERN})\s*(?:=|:=|von|from|←)\s*(.+?)\s+"
    r"(?:bis|to)\s+(.+?)(?:\s+(?:schritt(?:weite)?|step|in schritten von)\s+(.+?))?\s*$",
    re.IGNORECASE)
WHILE_PATTERN = re.compile(r"^\s*(?:solange|while|wiederhole\s+solange)\s+(.+?)\s*$", re.IGNORECASE)
TIMES_PATTERN = re.compile(r"^\s*(?:wiederhole\s+)?(.+?)\s*[- ]?mal\b.*$", re.IGNORECASE)
UNTIL_PATTERN = re.compile(r"^\s*(?:bis|until|wiederhole\s+bis)\s+(.+?)\s*$", re.IGNORECASE)


def parse_loop_header(text: str) -> LoopHeader:
    text = " ".join(text.split()).rstrip(":")
    match = FOR_PATTERN.match(text)
    if match:
        var, start, end, step = match.groups()
        start_e, end_e = normalize_expression(start), normalize_expression(end)
        step_e = normalize_expression(step) if step else "1"
        if is_identifier(var) and all(is_python_expression(e) for e in (start_e, end_e, step_e)):
            return LoopHeader("for", var, start_e, end_e, step_e)
    match = WHILE_PATTERN.match(text)
    if match:
        cond = condition_expression(match.group(1))
        if cond:
            return LoopHeader("while", condition=cond)
    match = TIMES_PATTERN.match(text)
    if match:
        count = normalize_expression(match.group(1))
        if is_python_expression(count):
            return LoopHeader("times", count=count)
    return LoopHeader("unknown")


def parse_loop_footer(text: str) -> tuple[str, str] | None:
    """Fuß einer Schleifenbegrenzung: („until“|„while“, Python-Bedingung) oder ``None``."""
    text = " ".join(text.split())
    match = UNTIL_PATTERN.match(text)
    if match:
        cond = condition_expression(match.group(1))
        if cond:
            return "until", cond
    match = WHILE_PATTERN.match(text)
    if match:
        cond = condition_expression(match.group(1))
        if cond:
            return "while", cond
    return None
