"""Die Wörter „ja“ und „nein“ an den Ausgängen einer Verzweigung – in allen Sprachen.

Die Beschriftung einer Verbindung steht in der Projektdatei. Ein Plan, der auf Englisch („yes“/„no“), Französisch
(„oui“/„non“) oder Japanisch („はい“/„いいえ“) angelegt wurde, muss trotzdem als Verzweigung mit Ja-/Nein-Ausgang
erkannt werden (Code erzeugen, Struktogramm, Schreibtischtest, Hinweisliste). Deshalb erkennt ``is_yes`` und
``is_no`` die Wörter **aller** Sprachen, unabhängig davon, in welcher Sprache das Programm gerade läuft.

Neue Verbindungen an einer Verzweigung bekommen die Beschriftung der eingestellten Sprache
(``yes_label``/``no_label``).
"""

from __future__ import annotations

from app import i18n
from app.i18n import N_, tr

# Quelltext der beiden Beschriftungen (Schlüssel der Übersetzung)
YES_SOURCE = N_("ja", ctx="Beschriftung")
NO_SOURCE = N_("nein", ctx="Beschriftung")
ELSE_SOURCE = N_("sonst", ctx="Beschriftung")

# Immer erkannt – auch ohne Übersetzungsdatei und wenn der Plan in einer anderen Sprache angelegt wurde
YES_WORDS = frozenset({
    "ja", "j", "yes", "y", "wahr", "true", "1", "w", "t", "+", "richtig", "stimmt", "ok", "erfüllt",
    "oui", "vrai", "sí", "si", "verdadero", "sim", "verdadeiro", "да", "истина", "نعم", "صحيح", "是", "真", "はい", "真"})
NO_WORDS = frozenset({
    "nein", "n", "no", "falsch", "false", "0", "f", "-", "stimmt nicht", "nicht erfüllt",
    "non", "faux", "falso", "não", "nao", "нет", "ложь", "لا", "خطأ", "否", "假", "いいえ", "偽"})
NO_PREFIXES = ("nicht ", "kein ", "keine ")  # „nicht erfüllt“, „kein Treffer“, …
# Beschriftung des „sonst“-Zweigs (bei Verzweigungen mit mehr als zwei Ausgängen)
ELSE_WORDS = frozenset({
    "sonst", "andernfalls", "ansonsten", "else", "default", "sonstiges", "otherwise", "sinon", "autrement",
    "de lo contrario", "si no", "caso contrário", "caso contrario", "senão", "иначе", "в противном случае",
    "غير ذلك", "وإلا", "否则", "其他", "それ以外", "さもなければ"})


def yes_label() -> str:
    """Beschriftung für den Ja-Ausgang in der eingestellten Sprache."""
    return tr(YES_SOURCE, ctx="Beschriftung")


def no_label() -> str:
    """Beschriftung für den Nein-Ausgang in der eingestellten Sprache."""
    return tr(NO_SOURCE, ctx="Beschriftung")


def yes_words() -> frozenset[str]:
    """Alle Wörter, die als „ja“ gelten (klein geschrieben)."""
    return YES_WORDS | {w.strip().lower() for w in i18n.all_translations(YES_SOURCE, ctx="Beschriftung")}


def no_words() -> frozenset[str]:
    """Alle Wörter, die als „nein“ gelten (klein geschrieben)."""
    return NO_WORDS | {w.strip().lower() for w in i18n.all_translations(NO_SOURCE, ctx="Beschriftung")}


def else_label() -> str:
    """Beschriftung für den „sonst“-Zweig in der eingestellten Sprache."""
    return tr(ELSE_SOURCE, ctx="Beschriftung")


def else_words() -> frozenset[str]:
    return ELSE_WORDS | {w.strip().lower() for w in i18n.all_translations(ELSE_SOURCE, ctx="Beschriftung")}


def normalize(label: str | None) -> str:
    return " ".join((label or "").split()).lower()


def is_yes(label: str | None) -> bool:
    return normalize(label) in yes_words()


def is_no(label: str | None) -> bool:
    label = normalize(label)
    return label in no_words() or label.startswith(NO_PREFIXES)


def is_else(label: str | None) -> bool:
    return normalize(label) in else_words()


# ---------------------------------------------------------------- Programmnamen
# Heißt das Start-Element nur so, trägt das Programm den Projektnamen (Code erzeugen)
GENERIC_PROGRAM_NAMES = frozenset({"start", "beginn", "anfang", "begin", "début", "inicio", "início", "старт",
                                   "начало", "ابدأ", "بداية", "开始", "開始", "スタート", ""})


def generic_program_names() -> frozenset[str]:
    """Namen, die nur „Start“ bedeuten – in allen Sprachen (klein geschrieben)."""
    return GENERIC_PROGRAM_NAMES | {w.strip().lower() for w in i18n.all_translations("Start", ctx="Standardtext")}
