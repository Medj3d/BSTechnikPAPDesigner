"""Code-Erzeugung: Assembler für den Mikrocontroller PIC16F887 (MPASM/gpasm), im Aufbau der Schulvorlage.

Aufbau wie ``start.asm`` aus dem Unterricht: Kopfkommentar (Projekt, Prozessor 16F887 / 4 MHz, Beschaltung der Ports,
Datum, Bearbeiter), ``list``/``#include``/``__CONFIG``, Variablen ab 0x20 (Bank 0), ``org 0x00``,
Hardwarekonfiguration, Hauptprogramm, Unterprogramme, ``end``. Befehle in Großbuchstaben, Zahlen als ``d'5'``.

Der PIC rechnet mit 8 Bit ohne Vorzeichen (0 bis 255). Übersetzt werden:

* Zuweisungen mit ``+ - * / mod``, ``& | ^`` und ``<< >>`` (Multiplikation und Division als Unterprogramme),
  ``x = x + 1`` als ``INCF``, ``x = 0`` als ``CLRF``. ``^`` ist hier – wie beim Mikrocontroller üblich – das
  bitweise XOR, keine Potenz.
* Register außerhalb von Bank 0 (``TRISB``, ``OPTION_REG``, ``ANSEL`` …) bekommen ein ``BANKSEL`` davor und danach
  ``BANKSEL PORTA`` (zurück zu Bank 0)
* Bedingungen ``= ≠ < > ≤ ≥`` (über ``SUBWF``/``SUBLW`` und STATUS-Bits C und Z), ``und``/``oder``/``nicht``
* Bits von Ports und Registern: ``PORTD.0 = 1`` → ``BSF PORTD, 0``; Bedingung ``PORTA.0 = 1`` → ``BTFSS PORTA, 0``;
  Bitmasken in Bedingungen (``(PORTB & 3) = 1``)
* Eingabe liest einen Port (Standard PORTB, „Eingabe x von PORTA“ wählt einen anderen), Ausgabe schreibt einen Port
  (Standard PORTD)
* ``warte 100 ms`` / ``warte 2 s`` als Warteschleife (4 MHz)
* Verzweigungen, Schleifen (Kopf-, Fuß-, Zählschleifen, „n-mal“, Endlosschleife), Unterprogramme (``CALL``/``RETURN``).
  Zählschleifen prüfen vor jedem Schritt, ob der Endwert erreicht ist – so enden auch „bis 0“, „bis 255“ und
  Schrittweiten, die über 0 oder 255 hinausspringen würden (8 Bit laufen sonst über).
* Die Hardwarekonfiguration stellt jeden benutzten Port passend ein: ``TRISx`` = 0 für Ausgänge (auch einzelne Bits
  wie ``PORTC.2 = 1``), 1 für Eingänge.

Was sich nicht übersetzen lässt (Text, Kommazahlen, Funktionen), steht als ``; TODO`` im Code. Eine Bedingung, die
nur aus Worten besteht („Taster gedrückt?“), wird zu einem Bit-Test an PORTB mit Hinweis, ihn anzupassen.
"""

from __future__ import annotations

import ast
import re

from app.analysis import text as T
from app.analysis.ast import (Action, Block, Break, Continue, DoWhileLoop, EndStmt, If, LimitLoop, Loop, Program,
                              Unstructured, WhileLoop)
from app.analysis.graph import resolve_routine, routine_label, routine_name
from app.analysis.variables import STRING, Variables
from app.i18n import tr_code

INDENT = "\t"
INPUT_PORT = "PORTB"
OUTPUT_PORT = "PORTD"
# Register des PIC16F887, die im Plan direkt vorkommen dürfen (keine Variablen)
REGISTERS = {
    "PORTA", "PORTB", "PORTC", "PORTD", "PORTE", "TRISA", "TRISB", "TRISC", "TRISD", "TRISE", "STATUS", "INTCON",
    "OPTION_REG", "TMR0", "TMR1L", "TMR1H", "TMR2", "PR2", "FSR", "INDF", "PCL", "PCLATH", "ADRESH", "ADRESL", "ADCON0",
    "ADCON1", "ANSEL", "ANSELH", "WPUB", "IOCB", "PIR1", "PIR2", "PIE1", "PIE2", "T1CON", "T2CON", "CCPR1L", "CCP1CON",
    "TXREG", "RCREG", "SPBRG", "TXSTA", "RCSTA", "EEDATA", "EEADR",
}
# Namen, die MPASM selbst belegt (Befehle, Direktiven, Kurzformen) – Variablen bekommen dann ein „v_“ davor
_RESERVED = {
    "ADDLW", "ADDWF", "ANDLW", "ANDWF", "BCF", "BSF", "BTFSC", "BTFSS", "CALL", "CLRF", "CLRW", "CLRWDT", "COMF",
    "DECF", "DECFSZ", "GOTO", "INCF", "INCFSZ", "IORLW", "IORWF", "MOVF", "MOVLW", "MOVWF", "NOP", "RETFIE", "RETLW",
    "RETURN", "RLF", "RRF", "SLEEP", "SUBLW", "SUBWF", "SWAPF", "XORLW", "XORWF", "W", "F", "C", "Z", "DC", "END",
    "ORG", "LIST", "CBLOCK", "ENDC", "EQU", "SET", "BANKSEL", "INCLUDE", "CONFIG", "ERRORLEVEL", "HIGH", "LOW", "RP0",
    "RP1", "IRP", "TO", "PD",
} | REGISTERS
_PORT_WORD = re.compile(r"\s*\b(?:an|auf|von|ueber|über|aus|nach|to|from)?\s*\b(PORT[A-E])\b", re.IGNORECASE)
_BIT_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[.,]\s*([0-7])\s*(?:=|:=|←|<-)\s*([01])\s*;?\s*$")
_BIT_TEST = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[.,]\s*([0-7])\s*(?:(==|=|!=|<>|≠)\s*([01]))?\s*\??\s*$")
_WAIT = re.compile(r"^\s*(?:warte|warten|pause|wait|delay)\s*:?\s*(\d+)\s*(ms|millisekunden?|s|sek(?:unden?)?|sec)\b",
                   re.IGNORECASE)
_SIMPLE = (ast.Name, ast.Constant)
_OUTPUT_WORD = re.compile(r"^\s*(?:ausgabe|gib|zeige|drucke|schreibe)\b\s*:?\s*", re.IGNORECASE)
PORTS = ("PORTA", "PORTB", "PORTC", "PORTD", "PORTE")
# Register, die nicht in Bank 0 liegen (STATUS, INTCON, FSR, PCL, PCLATH gibt es in jeder Bank)
_OTHER_BANK = {"TRISA", "TRISB", "TRISC", "TRISD", "TRISE", "OPTION_REG", "PR2", "ADRESL", "ADCON1", "WPUB", "IOCB",
               "PIE1", "PIE2", "SPBRG", "TXSTA", "EEDATA", "EEADR", "ANSEL", "ANSELH"}
# Marken und Speicherzellen, die der Erzeuger selbst anlegt – Variablen und Unterprogramme dürfen nicht so heißen
_OWN_NAMES = {
    "MAIN", "ENDE", "MUL8", "MUL8_SCHLEIFE", "MUL8_FERTIG", "DIV8", "DIV8_SCHLEIFE", "DIV8_FERTIG", "WARTE_S",
    "WARTE_S_SCHLEIFE", "WARTE_S_VIERTEL", "WARTE_MS", "WARTE_MS_AUSSEN", "WARTE_MS_INNEN", "MUL_A", "MUL_B",
    "MUL_ERG", "DIV_A", "DIV_B", "DIV_Q", "WARTE_ZAEHLER", "WARTE_INNEN", "WARTE_SEK", "WARTE_VIERTEL",
}
_OWN_NUMBERED = re.compile(r"^(?:hilf|zaehler|weiter|sonst|endewenn|solange|endesolange|wiederhole|pruefe"
                           r"|endewiederhole|schleife|endeschleife)_?\d+$", re.IGNORECASE)
# Platzhalter, damit „^“ nicht zur Potenz („**“) wird
_XOR = "\u2295"


def taken_name(name: str) -> bool:
    """Belegt MPASM oder der Erzeuger diesen Namen schon?"""
    return name.upper() in _RESERVED or name.upper() in _OWN_NAMES or bool(_OWN_NUMBERED.match(name))


def normalized(text: str, condition: bool = False) -> str:
    """PAP-Schreibweise → Python-Schreibweise, wobei „^“ (XOR) erhalten bleibt."""
    return T.normalize_expression(text.replace("^", _XOR), condition).replace(_XOR, "^")


class _Unsupported(Exception):
    """Ausdruck lässt sich auf dem 8-Bit-PIC nicht direkt übersetzen."""


def symbol(name: str) -> str:
    """Name einer Variablen oder Marke, den MPASM annimmt (nur Buchstaben, Ziffern, Unterstrich)."""
    text = name.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}))
    text = re.sub(r"[^A-Za-z0-9_]", "_", text).strip("_") or "wert"
    if text[0].isdigit():
        text = "v_" + text
    return text[:30]


# Zeichen, die ältere Assembler-Umgebungen (MPLAB 8, Windows-1252) nicht kennen
_COMMENT_CHARS = str.maketrans({"≠": "<>", "≤": "<=", "≥": ">=", "„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'",
                                "’": "'", "–": "-", "—": "-", "→": "->", "←": "<-", "·": "*", "×": "*", "÷": "/",
                                "…": "...", "▶": ">"})


def ascii_comment(text: str) -> str:
    """Kommentartext, den auch MPLAB 8 (Windows-1252) richtig zeigt: Sonderzeichen werden ersetzt, Umlaute bleiben."""
    return text.translate(_COMMENT_CHARS).encode("cp1252", "replace").decode("cp1252")


def literal(value: int) -> str:
    return f"d'{value}'"


class PicAsmGenerator:
    def __init__(self, programs: list[Program]):
        self.programs = programs
        self.lines: list[str] = []
        self._labels: set[str] = set()
        self._counter = 0
        self._loops: list[tuple[str, str]] = []   # (Weiter-Marke, Ende-Marke) der innersten Schleifen
        self._program_index = 0
        self._temps = 0          # gerade belegte Zwischenspeicher hilf1, hilf2, …
        self._max_temps = 0
        self._counters = 0       # Zähler für „n-mal“-Schleifen
        self.uses_mul = self.uses_div = self.uses_wait_ms = self.uses_wait_s = False
        # benutzte Bits je Port (0xFF = ganzer Port) – daraus entstehen TRISx und die Beschaltung im Kopf
        self.port_in: dict[str, int] = {}
        self.port_out: dict[str, int] = {}
        self.labels_of: list[str] = []
        self.variable_names: list[str] = []
        self.extra_vars: list[str] = []
        self.called: dict[str, str] = {}

    # ------------------------------------------------------------ Grundlagen
    def emit(self, depth: int, text: str) -> None:
        """Eine Befehlszeile (eingerückt). Marken schreibt ``label``."""
        self.lines.append(INDENT + text)

    def label(self, name: str) -> None:
        self.lines.append(name)

    def note(self, text: str) -> None:
        self.emit(0, f"; {ascii_comment(' '.join(str(text).split()))}")

    def comments(self, comments: list[str]) -> None:
        for comment in comments:
            self.note(comment)

    def new_label(self, base: str) -> str:
        self._counter += 1
        name = f"{base}_{self._counter}"
        self._labels.add(name)
        return name

    def var(self, name: str) -> str:
        if name.upper() in REGISTERS:
            return name.upper()
        sym = symbol(name)
        return "v_" + sym if taken_name(sym) or sym in self.labels_of else sym

    def use_port(self, port: str, output: bool, mask: int = 0xFF) -> None:
        if port in PORTS:
            ports = self.port_out if output else self.port_in
            ports[port] = ports.get(port, 0) | mask

    @staticmethod
    def banked(register: str, lines: list[str]) -> list[str]:
        """Befehle für ein Register außerhalb von Bank 0: Bank wählen, danach zurück zu Bank 0.

        ``BANKSEL`` setzt nur RP0/RP1 – W und die Bits C und Z bleiben erhalten."""
        if register not in _OTHER_BANK:
            return lines
        return [f"BANKSEL\t{register}", *lines, "BANKSEL\tPORTA\t\t; " + tr_code("zurück zu Bank 0")]

    def temp(self) -> str:
        self._temps += 1
        self._max_temps = max(self._max_temps, self._temps)
        return f"hilf{self._temps}"

    def release(self) -> None:
        self._temps -= 1

    # ------------------------------------------------------------ Ausdrücke
    def parse(self, expr: str | None, condition: bool = False):
        if not expr:
            raise _Unsupported()
        expr = normalized(expr, condition)
        tree = T.parse_expression(expr)
        if tree is None:
            tree = self._parse_bit_expression(expr)
        return tree.body if isinstance(tree, ast.Expression) else tree

    @staticmethod
    def _parse_bit_expression(expr: str):
        """Auf dem Mikrocontroller üblich, im PAP sonst nicht erlaubt: ``& | ^ << >> ~`` (Bitmasken, Schieben).

        ``expr`` ist schon in Python-Schreibweise (``normalized``)."""
        allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Name, ast.Constant, ast.Load,
                   ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.BitAnd, ast.BitOr, ast.BitXor,
                   ast.LShift, ast.RShift, ast.Invert, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq,
                   ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
        try:
            tree = ast.parse(expr, mode="eval")
        except (SyntaxError, ValueError, RecursionError):
            raise _Unsupported() from None
        if not all(isinstance(node, allowed) for node in ast.walk(tree)):
            raise _Unsupported()
        return tree

    def constant(self, node) -> int | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return int(node.value)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            if not 0 <= node.value <= 255:
                raise _Unsupported()
            return node.value
        if isinstance(node, ast.Constant):
            raise _Unsupported()   # Kommazahl oder Text
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            value = node.operand.value
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255:
                return (256 - value) % 256   # Zweierkomplement
            raise _Unsupported()
        return None

    def name(self, node) -> str | None:
        if isinstance(node, ast.Name):
            if node.id not in self.known and node.id.upper() not in REGISTERS:
                raise _Unsupported()
            if node.id in self.strings:
                raise _Unsupported()
            return self.var(node.id)
        return None

    def to_w(self, node) -> list[str]:
        """Befehle, die den Wert von ``node`` ins W-Register bringen."""
        value = self.constant(node)
        if value is not None:
            return [f"MOVLW\t{literal(value)}"]
        name = self.name(node)
        if name is not None:
            return self.banked(name, [f"MOVF\t{name}, W"])
        if isinstance(node, ast.BinOp):
            return self.binop(node)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return self.to_w(node.operand) + ["SUBLW\td'0'\t\t; 0 - W (Zweierkomplement)"]
            if isinstance(node.op, ast.Invert):
                return self.to_w(node.operand) + ["XORLW\tb'11111111'"]
            if isinstance(node.op, ast.UAdd):
                return self.to_w(node.operand)
        raise _Unsupported()

    def operand(self, node) -> tuple[str, str] | None:
        """Einfacher Operand als („LW“, Wert) oder („WF“, Register) – sonst ``None``."""
        value = self.constant(node)
        if value is not None:
            return "LW", literal(value)
        name = self.name(node)
        if name is not None and name not in _OTHER_BANK:   # andere Bank: erst ins W-Register holen
            return "WF", name
        return None

    def binop(self, node: ast.BinOp) -> list[str]:
        op = node.op
        commutative = {ast.Add: "ADD", ast.BitAnd: "AND", ast.BitOr: "IOR", ast.BitXor: "XOR"}
        for kind, mnemonic in commutative.items():
            if isinstance(op, kind):
                return self._commutative(mnemonic, node.left, node.right)
        if isinstance(op, ast.Sub):
            return self.difference(node.left, node.right)
        if isinstance(op, ast.Mult):
            self.uses_mul = True
            return self._helper_call(node.left, node.right, "mul_a", "mul_b", "mul8")
        if isinstance(op, (ast.Div, ast.FloorDiv)):
            self.uses_div = True
            return self._helper_call(node.left, node.right, "div_a", "div_b", "div8")
        if isinstance(op, ast.Mod):
            self.uses_div = True
            return self._helper_call(node.left, node.right, "div_a", "div_b", "div8") + ["MOVF\tdiv_a, W\t\t; Rest"]
        if isinstance(op, (ast.LShift, ast.RShift)):
            count = self.constant(node.right)
            if count is None or count > 7:
                raise _Unsupported()
            rotate = "RLF" if isinstance(op, ast.LShift) else "RRF"
            temp = self.temp()
            try:
                lines = self.to_w(node.left) + [f"MOVWF\t{temp}"]
            finally:
                self.release()
            for _ in range(count):
                lines += ["BCF\tSTATUS, C", f"{rotate}\t{temp}, F"]
            return lines + [f"MOVF\t{temp}, W"]
        raise _Unsupported()

    def _commutative(self, mnemonic: str, left, right) -> list[str]:
        simple = self.operand(right)
        if simple is not None:
            return self.to_w(left) + [f"{mnemonic}{simple[0]}\t{simple[1]}" + (", W" if simple[0] == "WF" else "")]
        simple = self.operand(left)
        if simple is not None:
            return self.to_w(right) + [f"{mnemonic}{simple[0]}\t{simple[1]}" + (", W" if simple[0] == "WF" else "")]
        temp = self.temp()
        try:
            lines = self.to_w(right) + [f"MOVWF\t{temp}"] + self.to_w(left) + [f"{mnemonic}WF\t{temp}, W"]
        finally:
            self.release()
        return lines

    def difference(self, left, right) -> list[str]:
        """W = left − right. Der letzte Befehl ist SUBWF/SUBLW: Danach gilt C=1 ⇔ left ≥ right, Z=1 ⇔ gleich."""
        a, b = self.operand(left), self.operand(right)
        if a is not None and a[0] == "LW":
            return self.to_w(right) + [f"SUBLW\t{a[1]}\t\t; {a[1]} - W"]
        if a is not None:
            return self.to_w(right) + [f"SUBWF\t{a[1]}, W\t\t; {a[1]} - W"]
        temp = self.temp()
        try:
            lines = self.to_w(left) + [f"MOVWF\t{temp}"] + self.to_w(right) + [f"SUBWF\t{temp}, W"]
        finally:
            self.release()
        return lines

    def _helper_call(self, left, right, first: str, second: str, routine: str) -> list[str]:
        temp = self.temp()
        try:
            lines = self.to_w(right) + [f"MOVWF\t{temp}"] + self.to_w(left) + [f"MOVWF\t{first}",
                                                                                 f"MOVF\t{temp}, W",
                                                                                 f"MOVWF\t{second}"]
        finally:
            self.release()
        return lines + [f"CALL\t{routine}"]

    # ------------------------------------------------------------ Bedingungen
    def jump_if(self, node, truth: bool, target: str) -> list[str]:
        """Springt nach ``target``, wenn die Bedingung ``truth`` ergibt; sonst geht es dahinter weiter."""
        if isinstance(node, ast.BoolOp):
            conjunction = isinstance(node.op, ast.And)
            if conjunction != truth:
                # „und“ ist falsch, sobald ein Teil falsch ist – „oder“ ist wahr, sobald ein Teil wahr ist
                return [line for value in node.values for line in self.jump_if(value, truth, target)]
            skip = self.new_label("weiter")
            lines = [line for value in node.values[:-1] for line in self.jump_if(value, not truth, skip)]
            return lines + self.jump_if(node.values[-1], truth, target) + [f"@{skip}"]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self.jump_if(node.operand, not truth, target)
        if isinstance(node, ast.Compare):
            if len(node.ops) > 1:   # a < b < c  →  a < b und b < c
                parts = [ast.Compare(left=l, ops=[o], comparators=[r])
                         for l, o, r in zip([node.left, *node.comparators[:-1]], node.ops, node.comparators)]
                return self.jump_if(ast.BoolOp(op=ast.And(), values=parts), truth, target)
            return self.compare(node.left, node.ops[0], node.comparators[0], truth, target)
        value = self.constant(node) if isinstance(node, ast.Constant) else None
        if value is not None:
            return [f"GOTO\t{target}"] if bool(value) == truth else []
        # Zahl als Wahrheitswert: wahr, wenn nicht 0
        lines = self.to_w(node) + ["IORLW\td'0'\t\t; Z=1, wenn 0"]
        return lines + [("BTFSS" if truth else "BTFSC") + "\tSTATUS, Z", f"GOTO\t{target}"]

    def compare(self, left, op, right, truth: bool, target: str) -> list[str]:
        if isinstance(op, (ast.Eq, ast.NotEq)):
            lines = self.difference(left, right)
            equal_jumps = isinstance(op, ast.Eq) == truth
            # Z=1 ⇔ gleich: springen, wenn (gleich und gesucht) – also Befehl überspringen, wenn nicht
            return lines + [("BTFSC" if equal_jumps else "BTFSS") + "\tSTATUS, Z", f"GOTO\t{target}"]
        if isinstance(op, (ast.Lt, ast.GtE)):
            lines = self.difference(left, right)          # C=1 ⇔ left ≥ right
            greater_equal = isinstance(op, ast.GtE)
        elif isinstance(op, (ast.Gt, ast.LtE)):
            lines = self.difference(right, left)          # C=1 ⇔ right ≥ left ⇔ left ≤ right
            greater_equal = isinstance(op, ast.LtE)
        else:
            raise _Unsupported()
        jump_on_carry = greater_equal == truth
        return lines + [("BTFSC" if jump_on_carry else "BTFSS") + "\tSTATUS, C", f"GOTO\t{target}"]

    def condition_jump(self, text: str, truth: bool, target: str, source: str) -> None:
        """Bedingung aus einem Bausteintext; springt nach ``target``, wenn sie ``truth`` ergibt."""
        bit = _BIT_TEST.match(text or "")
        if bit and (bit.group(1).upper() in REGISTERS or bit.group(1) in self.known):
            register, number, operator, value = self.var(bit.group(1)), bit.group(2), bit.group(3), bit.group(4)
            # gesuchter Bitwert, bei dem die Bedingung wahr ist: „PORTA.0“ und „PORTA.0 = 1“ → 1, „≠ 1“ → 0
            wanted = True if operator is None else (value == "1") == (operator in ("==", "="))
            set_jumps = wanted == truth
            self.use_port(register, output=False, mask=1 << int(number))
            tested = register
            if register in _OTHER_BANK:
                # der Sprung verlässt die Stelle – vorher zurück zu Bank 0, das Bit wird in einer Kopie geprüft
                tested = self.temp()
                self.release()
                for line in self.banked(register, [f"MOVF\t{register}, W"]) + [f"MOVWF\t{tested}"]:
                    self.emit(0, line)
            # Springen, wenn das Bit den gesuchten Wert hat: den GOTO überspringen, wenn nicht
            self.emit(0, ("BTFSC" if set_jumps else "BTFSS") + f"\t{tested}, {number}")
            self.emit(0, f"GOTO\t{target}")
            return
        try:
            lines = self.jump_if(self.parse(text, condition=True), truth, target)
        except _Unsupported:
            self.note("TODO: " + tr_code("Bedingung „{text}“ als Bit-Test formulieren, z. B. PORTB.0 = 1",
                                         text=source))
            self.emit(0, ("BTFSC" if truth else "BTFSS") + f"\t{INPUT_PORT}, 0")
            self.emit(0, f"GOTO\t{target}")
            self.use_port(INPUT_PORT, output=False, mask=1)
            return
        for line in lines:
            if line.startswith("@"):
                self.label(line[1:])
            else:
                self.emit(0, line)

    # ------------------------------------------------------------ Programm
    def generate(self) -> str:
        if not self.programs:
            return "; " + tr_code("Der Plan enthält kein Start-Element.") + "\n"
        variables = Variables(self.programs)
        self.known = set(variables.names)
        self.variable_names = list(variables.names)
        # Text ist nur, was irgendwo Text zugewiesen bekommt – eine Eingabe liest am PIC immer eine Zahl vom Port
        text_assigned = getattr(variables, "_text_assigned", set(variables.types))
        self.strings = {name for name, kind in variables.types.items() if kind == STRING and name in text_assigned}
        self.labels_of = []
        taken = set()
        for index, program in enumerate(self.programs):
            base = "main" if index == 0 else symbol(routine_name(program.name) or T.slug(program.name) or "up")
            name = base
            while (index and taken_name(name)) or name in taken:
                name = f"{base}_{len(taken) + 1}"
            taken.add(name)
            self.labels_of.append(name)
        body: list[str] = []
        for index, program in enumerate(self.programs):
            self._program_index = index
            self.lines = []
            if index == 0:
                self._section(tr_code("Hauptprogramm - (loop)"))
            else:
                self.lines.append("")
            self.label(self.labels_of[index])
            self.note(program.name)
            for warning in program.warnings:
                self.note("TODO: " + warning)
            self.block(program.body, top_level=True)
            if index == 0:
                self.label("ende")
                self.emit(0, "GOTO\tende\t\t; " + tr_code("Programmende: hier anhalten"))
            else:
                self.emit(0, "RETURN")
            body.append(self.lines)
        main, routines = body[0], [line for lines in body[1:] for line in lines]
        code = "\n".join(self._header() + self._variables() + self._setup() + main
                         + self._routines_section(routines) + ["", INDENT + "end"]) + "\n"
        return ascii_comment(code)

    def _section(self, title: str) -> None:
        self.lines += [";" + "-" * 97, f"; {title}", ";" + "-" * 97]

    def _header(self) -> list[str]:
        from datetime import date

        name = self.programs[0].name
        line = ";" + "-" * 97
        return [line,
                f"; Projektname\t    : {' '.join(name.split())}",
                "; Prozessor\t    : 16F887 / 4 Mhz",
                *(f"; Beschaltung {port} : {self._wiring(port)}" for port in PORTS),
                f"; Datum\t\t    : {date.today().strftime('%d.%m.%Y')}",
                "; Bearbeiter\t    : ",
                "; letzte Aenderung  : ",
                "; Bearbeiter\t    :",
                "; " + tr_code("Automatisch erzeugt aus dem Programmablaufplan (BS Technik PAP Designer)."),
                "; " + tr_code("Nicht übersetzbare Stellen sind mit TODO markiert."),
                line,
                "\tlist\tp=16F887",
                "\t#include\t<p16f887.inc>",
                "\terrorlevel -302",
                "\terrorlevel -305",
                "\t__CONFIG    _CONFIG1, 0x20E4",
                "\t__CONFIG    _CONFIG2, 0xFFFF"]

    def _wiring(self, port: str) -> str:
        output = self.port_out.get(port, 0)
        reads = self.port_in.get(port, 0) & ~output & 0xFF
        return ", ".join(word for word, used in ((tr_code("Eingabe"), reads), (tr_code("Ausgabe"), output)) if used)

    def _variables(self) -> list[str]:
        names = [self.var(name) for name in self.variable_names
                 if name not in self.strings and name.upper() not in REGISTERS]
        names += [f"hilf{i}" for i in range(1, self._max_temps + 1)]
        names += [f"zaehler{i}" for i in range(1, self._counters + 1)]
        if self.uses_mul:
            names += ["mul_a", "mul_b", "mul_erg"]
        if self.uses_div:
            names += ["div_a", "div_b", "div_q"]
        if self.uses_wait_ms or self.uses_wait_s:
            names += ["warte_zaehler", "warte_innen"]
        if self.uses_wait_s:
            names += ["warte_sek", "warte_viertel"]
        lines = [";" + "-" * 97, "; " + tr_code("Variablen und Definitionen - (ab 0x20 -> freier Speicher auf Bank 0)"),
                 ";" + "-" * 97]
        names = list(dict.fromkeys(names))
        if names:
            lines += ["\tcblock\t0x20"] + [f"\t{name}" for name in names] + ["\tendc"]
        return lines + ["", "\torg\t0x00", ""]

    def _setup(self) -> list[str]:
        lines = [";" + "-" * 97, "; " + tr_code("Hardwarekonfiguration - (setup)"), ";" + "-" * 97,
                 "\tBANKSEL\tANSEL", "\tCLRF\tANSEL\t\t; " + tr_code("alle Pins digital"), "\tCLRF\tANSELH"]
        tris = []
        for port in PORTS:
            if port not in self.port_in and port not in self.port_out:
                continue
            # 1 = Eingang, 0 = Ausgang; ein Bit, das geschrieben wird, ist ein Ausgang (Lesen geht dann trotzdem)
            value = ~self.port_out.get(port, 0) & 0xFF
            register = "TRIS" + port[-1]
            if value == 0:
                tris.append(f"\tCLRF\t{register}\t\t; {port}: {tr_code('Ausgang')}")
            else:
                note = tr_code("Eingang") if value == 0xFF else f"1 = {tr_code('Eingang')}, 0 = {tr_code('Ausgang')}"
                tris += [f"\tMOVLW\tb'{value:08b}'", f"\tMOVWF\t{register}\t\t; {port}: {note}"]
        if tris:
            lines += ["\tBANKSEL\tTRISA"] + tris
        lines += ["\tBANKSEL\tPORTA\t\t; " + tr_code("zurück zu Bank 0")]
        lines += [f"\tCLRF\t{port}" for port in PORTS if self.port_out.get(port)]
        return lines + [""]

    def _routines_section(self, routines: list[str]) -> list[str]:
        lines = ["", ";" + "-" * 97, "; " + tr_code("Unterprogramme - (Funktionen)"), ";" + "-" * 97]
        lines += routines
        for name, text in self.called.items():
            lines += ["", name, f"\t; TODO: {tr_code('Unterprogramm „{label}“ ausarbeiten', label=text)}", "\tRETURN"]
        if self.uses_mul:
            lines += ["", "; " + tr_code("Multiplikation: W = mul_a * mul_b (8 Bit)"), "mul8",
                      "\tCLRF\tmul_erg", "mul8_schleife", "\tMOVF\tmul_b, F", "\tBTFSC\tSTATUS, Z",
                      "\tGOTO\tmul8_fertig", "\tMOVF\tmul_a, W", "\tADDWF\tmul_erg, F", "\tDECF\tmul_b, F",
                      "\tGOTO\tmul8_schleife", "mul8_fertig", "\tMOVF\tmul_erg, W", "\tRETURN"]
        if self.uses_div:
            lines += ["", "; " + tr_code("Division: W = div_a / div_b, Rest in div_a (bei div_b = 0: 0)"), "div8",
                      "\tCLRF\tdiv_q", "\tMOVF\tdiv_b, F", "\tBTFSC\tSTATUS, Z", "\tRETLW\td'0'",
                      "div8_schleife", "\tMOVF\tdiv_b, W", "\tSUBWF\tdiv_a, W\t\t; div_a - div_b",
                      "\tBTFSS\tSTATUS, C\t\t; " + tr_code("passt nicht mehr hinein?"), "\tGOTO\tdiv8_fertig",
                      "\tMOVWF\tdiv_a", "\tINCF\tdiv_q, F", "\tGOTO\tdiv8_schleife", "div8_fertig",
                      "\tMOVF\tdiv_q, W", "\tRETURN"]
        if self.uses_wait_s:
            lines += ["", "; " + tr_code("Warten: W Sekunden (4 MHz)"), "warte_s", "\tMOVWF\twarte_sek",
                      "warte_s_schleife", "\tMOVLW\td'4'", "\tMOVWF\twarte_viertel", "warte_s_viertel",
                      "\tMOVLW\td'250'", "\tCALL\twarte_ms", "\tDECFSZ\twarte_viertel, F", "\tGOTO\twarte_s_viertel",
                      "\tDECFSZ\twarte_sek, F", "\tGOTO\twarte_s_schleife", "\tRETURN"]
        if self.uses_wait_ms or self.uses_wait_s:
            lines += ["", "; " + tr_code("Warten: W Millisekunden (4 MHz, 1 Befehl = 1 µs)"), "warte_ms",
                      "\tMOVWF\twarte_zaehler", "warte_ms_aussen", "\tMOVLW\td'249'", "\tMOVWF\twarte_innen",
                      "warte_ms_innen", "\tNOP", "\tDECFSZ\twarte_innen, F", "\tGOTO\twarte_ms_innen",
                      "\tDECFSZ\twarte_zaehler, F", "\tGOTO\twarte_ms_aussen", "\tRETURN"]
        return lines

    # ------------------------------------------------------------ Anweisungen
    def block(self, block: Block, top_level: bool = False) -> None:
        statements = list(block)
        if top_level and statements and isinstance(statements[-1], EndStmt):
            statements = statements[:-1]
        for stmt in statements:
            self.stmt(stmt, 0)

    def stmt(self, stmt, depth: int) -> None:
        if isinstance(stmt, Action):
            self.comments(stmt.comments)
            getattr(self, f"action_{stmt.kind}", self.action_process)(stmt)
        elif isinstance(stmt, If):
            self.comments(stmt.comments)
            otherwise, done = self.new_label("sonst"), self.new_label("endewenn")
            self.note(tr_code("Wenn {text}", text=stmt.condition))
            self.condition_jump(stmt.condition, False, otherwise if len(stmt.else_block) else done, stmt.condition)
            self.block(stmt.then_block)
            if len(stmt.else_block):
                self.emit(0, f"GOTO\t{done}")
                self.label(otherwise)
                self.block(stmt.else_block)
            self.label(done)
        elif isinstance(stmt, WhileLoop):
            self.comments(stmt.comments)
            head, end = self.new_label("solange"), self.new_label("endesolange")
            self.label(head)
            self.note(tr_code("Solange {text}", text=stmt.condition) if not stmt.negate
                      else tr_code("Bis {text}", text=stmt.condition))
            self.condition_jump(stmt.condition, stmt.negate, end, stmt.condition)
            self.loop_body(stmt.body, head, end)
            self.emit(0, f"GOTO\t{head}")
            self.label(end)
        elif isinstance(stmt, DoWhileLoop):
            self.comments(stmt.comments)
            head, check, end = self.new_label("wiederhole"), self.new_label("pruefe"), self.new_label("endewiederhole")
            self.label(head)
            self.loop_body(stmt.body, check, end)
            self.label(check)
            self.condition_jump(stmt.condition, not stmt.negate, head, stmt.condition)
            self.label(end)
        elif isinstance(stmt, LimitLoop):
            self.limit_loop(stmt)
        elif isinstance(stmt, Loop):
            head, end = self.new_label("schleife"), self.new_label("endeschleife")
            self.label(head)
            self.loop_body(stmt.body, head, end)
            self.emit(0, f"GOTO\t{head}")
            self.label(end)
        elif isinstance(stmt, Continue) and self._loops:
            self.emit(0, f"GOTO\t{self._loops[-1][0]}\t\t; " + tr_code("nächster Durchlauf"))
        elif isinstance(stmt, Break) and self._loops:
            self.emit(0, f"GOTO\t{self._loops[-1][1]}\t\t; " + tr_code("Schleife verlassen"))
        elif isinstance(stmt, EndStmt):
            self.emit(0, "GOTO\tende" if self._program_index == 0 else "RETURN")
        elif isinstance(stmt, Unstructured):
            self.note("TODO: " + stmt.note)
        else:
            self.note("TODO: " + tr_code("Sprung ohne Schleife"))

    def loop_body(self, block: Block, again: str, end: str) -> None:
        self._loops.append((again, end))
        try:
            self.block(block)
        finally:
            self._loops.pop()

    def limit_loop(self, stmt: LimitLoop) -> None:
        self.comments(stmt.comments)
        header = T.parse_loop_header(stmt.header)
        footer = T.parse_loop_footer(stmt.footer) if stmt.footer else None
        head, again, end = self.new_label("schleife"), self.new_label("weiter"), self.new_label("endeschleife")
        self.note(stmt.header)
        if header.kind == "for":
            variable = self.var(header.variable)
            if not self.assign(header.variable, header.start):
                self.note("TODO: " + tr_code("Startwert {expr}", expr=header.start))
            descending = header.step.strip().startswith("-")
            step = header.step.strip().lstrip("-").strip() or "1"
            # Erst prüfen, ob die Schleife überhaupt läuft …
            comparison = f"{header.variable} {'>=' if descending else '<='} ({header.end})"
            self.condition_jump(comparison, False, end, comparison)
            self.label(head)
            self.loop_body(stmt.body, again, end)
            self.label(again)
            if footer is not None:
                self.condition_jump(footer[1], footer[0] == "until", end, stmt.footer)
            # … und vor jedem Schritt, ob der Endwert erreicht ist. Hinter dem Endwert zu prüfen ginge mit 8 Bit
            # nicht: „bis 255“ oder „bis 0 Schritt -1“ liefen über (255 + 1 = 0) und endeten nie.
            if descending:
                last = f"{header.variable} <= ({header.end})"
                rest = f"{header.variable} - ({header.end})"
            else:
                last = f"{header.variable} >= ({header.end})"
                rest = f"({header.end}) - {header.variable}"
            if step != "1":
                last = f"{last} oder {rest} < ({step})"
            self.condition_jump(last, True, end, last)
            if step == "1":
                self.emit(0, f"{'DECF' if descending else 'INCF'}\t{variable}, F")
            else:
                op = "-" if descending else "+"
                if not self.assign(header.variable, f"{header.variable} {op} ({step})"):
                    self.note("TODO: " + tr_code("Schrittweite {expr}", expr=header.step))
            self.emit(0, f"GOTO\t{head}")
            self.label(end)
            return
        if header.kind == "times":
            self._counters += 1
            counter = f"zaehler{self._counters}"
            try:
                lines = self.to_w(self.parse(header.count))
            except _Unsupported:
                lines = None
            if lines is None:
                self.note("TODO: " + tr_code("Anzahl {expr}", expr=header.count))
                lines = ["MOVLW\td'1'"]
            for line in lines + [f"MOVWF\t{counter}", f"IORLW\td'0'", "BTFSC\tSTATUS, Z", f"GOTO\t{end}"]:
                self.emit(0, line)
            self.label(head)
            self.loop_body(stmt.body, again, end)
            self.label(again)
            if footer is not None:
                self.condition_jump(footer[1], footer[0] == "until", end, stmt.footer)
            self.emit(0, f"DECFSZ\t{counter}, F")
            self.emit(0, f"GOTO\t{head}")
            self.label(end)
            return
        self.label(head)
        if header.kind == "while":
            self.condition_jump(header.condition, False, end, stmt.header)
        elif footer is None:
            self.note("TODO: " + tr_code("Schleifenkopf „{text}“ – läuft endlos", text=stmt.header))
        self.loop_body(stmt.body, again, end)
        self.label(again)
        if footer is not None:
            self.condition_jump(footer[1], footer[0] == "until", end, stmt.footer)
        self.emit(0, f"GOTO\t{head}")
        self.label(end)

    # ------------------------------------------------------------ Aktionen
    def _port_in(self, text: str, default: str) -> tuple[str, str]:
        """(Text ohne Port-Angabe, Port) – „Eingabe x von PORTA“ → („Eingabe x“, „PORTA“)."""
        match = _PORT_WORD.search(text)
        if not match:
            return text, default
        return (text[:match.start()] + text[match.end():]).strip(), match.group(1).upper()

    def action_input(self, stmt: Action) -> None:
        text, port = self._port_in(stmt.text, INPUT_PORT)
        self.note(stmt.text)
        names = [name for name in T.input_variables(text) if name.upper() not in REGISTERS]
        self.use_port(port, output=False)
        if not names:
            self.note("TODO: " + tr_code("Variable festlegen"))
            return
        for name in names:
            if name in self.strings:
                self.note("TODO: " + tr_code("Text kann der PIC nicht einlesen: {name}", name=name))
                continue
            self.emit(0, f"MOVF\t{port}, W\t\t; " + tr_code("Wert von {port} lesen", port=port))
            self.emit(0, f"MOVWF\t{self.var(name)}")

    def action_output(self, stmt: Action) -> None:
        text, port = self._port_in(stmt.text, OUTPUT_PORT)
        self.note(stmt.text)
        spec = T.output_spec(text, self.known)
        values = []
        raw = _OUTPUT_WORD.sub("", text, count=1).strip()
        try:
            # Bitausdrücke („PORTB & 15“, „a ^ b“) als Ganzes – die allgemeine Analyse kennt sie nicht
            if raw and not any(mark in raw for mark in "\"„“,'") and self.parse(raw) is not None:
                values = [raw]
        except _Unsupported:
            pass
        if values:
            pass
        elif spec.kind == "mixed":
            values = [value for kind, value in spec.parts if kind != "string"]
        elif spec.kind == "expression":
            values = [spec.value]
        elif spec.kind == "variables":
            values = list(spec.variables)
        written = False
        for value in values:
            try:
                lines = self.to_w(self.parse(value))
            except _Unsupported:
                self.note("TODO: " + tr_code("{expr} lässt sich nicht ausgeben (nur Zahlen 0 bis 255)", expr=value))
                continue
            for line in lines + [f"MOVWF\t{port}\t\t; " + tr_code("an {port} ausgeben", port=port)]:
                self.emit(0, line)
            written = True
        if written or (not values and port == OUTPUT_PORT):
            self.use_port(port, output=True)
        if not values:
            self.note("TODO: " + tr_code("Text „{text}“ ausgeben – der Port zeigt nur Zahlen", text=spec.value))

    def assign(self, name: str, expr: str) -> bool:
        """Zuweisung ``name = expr``; ``False``, wenn sie sich nicht übersetzen lässt."""
        target = self.var(name)
        if name in self.strings:
            return False
        if name not in self.known and name.upper() not in REGISTERS:
            # z. B. „q = a << 2“: Bitausdrücke erkennt die allgemeine Analyse nicht – die Variable braucht trotzdem Platz
            self.known.add(name)
            self.variable_names.append(name)
        try:
            node = self.parse(expr)
            value = self.constant(node)
            if value == 0:
                lines = self.banked(target, [f"CLRF\t{target}"])
            elif (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub))
                    and isinstance(node.left, ast.Name) and node.left.id == name
                    and isinstance(node.right, ast.Constant) and node.right.value == 1):
                lines = self.banked(target, [f"{'INCF' if isinstance(node.op, ast.Add) else 'DECF'}\t{target}, F"])
            else:
                lines = self.to_w(node) + self.banked(target, [f"MOVWF\t{target}"])
        except _Unsupported:
            return False
        if target in PORTS:
            self.use_port(target, output=True)
        for line in lines:
            self.emit(0, line)
        return True

    def action_process(self, stmt: Action) -> None:
        self.note(stmt.text)
        for line in [line.strip() for line in stmt.text.splitlines() if line.strip()]:
            bit = _BIT_ASSIGN.match(line)
            if bit:
                register, command = self.var(bit.group(1)), "BSF" if bit.group(3) == "1" else "BCF"
                self.use_port(register, output=True, mask=1 << int(bit.group(2)))
                for code in self.banked(register, [f"{command}\t{register}, {bit.group(2)}"]):
                    self.emit(0, code)
                continue
            wait = _WAIT.match(line)
            if wait:
                amount, unit = int(wait.group(1)), wait.group(2).lower()
                if not 1 <= amount <= 255:
                    self.note("TODO: " + tr_code("Wartezeit 1 bis 255 angeben"))
                    continue
                seconds = unit.startswith("s")
                self.uses_wait_s |= seconds
                self.uses_wait_ms |= not seconds
                self.emit(0, f"MOVLW\t{literal(amount)}")
                self.emit(0, f"CALL\t{'warte_s' if seconds else 'warte_ms'}")
                continue
            # „^“ ist hier XOR: die allgemeine Analyse machte daraus eine Potenz
            assignments = None if "^" in line else T.parse_assignments(line)
            if not assignments:
                # Bitausdrücke („q = a << 2“, „x = PORTB & 15“) lässt die allgemeine Analyse aus
                match = T.ASSIGN.match(line)
                assignments = [(match.group(1), match.group(2))] if match else None
            if not assignments:
                self.note("TODO: " + line)
                continue
            for name, expr in assignments:
                if not self.assign(name, expr):
                    self.note("TODO: " + tr_code("{name} = {expr} (nur ganze Zahlen 0 bis 255)", name=name,
                                                 expr=expr))

    def action_subprogram(self, stmt: Action) -> None:
        self.note(stmt.text)
        index = resolve_routine(stmt.text, [program.name for program in self.programs], exclude=0)
        if index is not None:
            self.emit(0, f"CALL\t{self.labels_of[index]}")
            return
        name = symbol(routine_name(stmt.text) or T.slug(stmt.text) or "unterprogramm")
        variables = {self.var(variable) for variable in self.variable_names}
        if taken_name(name) or name in self.labels_of or name in variables:
            name = "up_" + name
        self.called.setdefault(name, routine_label(stmt.text) or stmt.text)
        self.emit(0, f"CALL\t{name}")

    def action_junction(self, stmt: Action) -> None:
        pass

    def action_start(self, stmt: Action) -> None:
        pass
