"""Schreibweisen, die Schreibtischtest und Code-Erzeugung in den Bausteintexten verstehen.

Die Beispiele sind aus der echten Deutung der Texte abgeleitet (``app/analysis/text.py``,
``app/simulation/evaluator.py``, ``app/simulation/engine.py``). ``tests/test_feature_notation_help.py`` führt
**jedes** Beispiel im Schreibtischtest und im erzeugten Python- (und Java-)Programm aus – so kann die Hilfe nie
etwas versprechen, was das Programm nicht kann.

Die Beispiele selbst werden nie übersetzt: Genau so muss man sie in den Baustein schreiben. Übersetzt wird nur
die Erklärung; Schreibweisen darin stehen als Platzhalter, damit sie in jeder Sprache gleich bleiben.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.i18n import N_, is_rtl, tr
from app.model.element_types import (LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, ElementType, default_text_for,
                                     display_name_for)

# Kurzes Beispiel für den Tipp auf der leeren Arbeitsfläche (steht auch in der Liste unten)
HINT_EXAMPLE = "x := x + 1"


@dataclass(frozen=True)
class Notation:
    block: ElementType
    example: str                 # so, wie es im Baustein steht (nie übersetzt)
    meaning: str                 # deutscher Quelltext der Erklärung (mit N_ markiert)
    values: tuple = ()           # Platzhalter der Erklärung: ((Name, Schreibweise), …) – nie übersetzt
    part: str | None = None      # Schleife: LOOP_BEGIN oder LOOP_END

    def block_text(self) -> str:
        """Bausteinname in der eingestellten Sprache („Vorgang“, „Schleifenende“ …)."""
        if self.block is ElementType.LOOP and self.part:
            return default_text_for(ElementType.LOOP, {LOOP_PART_KEY: self.part})
        return display_name_for(self.block)

    def meaning_text(self) -> str:
        values = dict(self.values)
        if is_rtl():
            # Zwischen arabischen Wörtern drehte die Schreibrichtung „:=“ sonst zu „=:“: Schreibweisen bleiben in
            # einer eigenen Insel von links nach rechts (LRI … PDI)
            values = {name: f"⁦{value}⁩" for name, value in values.items()}
        return tr(self.meaning, **values)


P, I, O = ElementType.PROCESS, ElementType.INPUT, ElementType.OUTPUT
D, L, U = ElementType.DECISION, ElementType.LOOP, ElementType.SUBPROGRAM
S = ElementType.START

# (Überschrift, Einträge); die Überschrift ist deutscher Quelltext (N_)
SECTIONS: list[tuple[str, list[Notation]]] = [
    (N_("Werte zuweisen"), [
        Notation(P, "x := x + 1", N_("x bekommt einen neuen Wert: den alten Wert plus 1")),
        Notation(P, "zahl = 5", N_("Zuweisen geht mit {a}, {b} oder {c}"), (("a", ":="), ("b", "="), ("c", "←"))),
        Notation(P, "a = 1; b = 2", N_("Mehrere Zuweisungen: mit {sep} trennen oder je eine Zeile"),
                 (("sep", ";"),)),
        Notation(P, 'name = "Anna"', N_("Text steht in Anführungszeichen")),
        Notation(P, 'gruss = "Hallo " + name', N_("Texte (auch mit Zahlen) mit {plus} verbinden"),
                 (("plus", "+"),)),
        Notation(P, "fertig = wahr", N_("Wahrheitswerte: {yes} und {no}"), (("yes", "wahr"), ("no", "falsch"))),
    ]),
    (N_("Rechnen"), [
        Notation(P, "mittel = (a + b) / 2", N_("Grundrechenarten {ops} und Klammern"), (("ops", "+ - * /"),)),
        Notation(P, "preis = 2,5 * 4", N_("Kommazahlen mit Komma oder Punkt")),
        Notation(P, "rest = 17 mod 5", N_("Rest beim Teilen (auch {alt})"), (("alt", "%"),)),
        Notation(P, "ganz = 17 div 5", N_("Ganzzahlig teilen (auch {alt})"), (("alt", "//"),)),
        Notation(P, "q = x^2", N_("Hochzahl (auch {a} oder {b})"), (("a", "x**2"), ("b", "x²"))),
        Notation(P, "w = wurzel(16)", N_("Funktionen: {names}"),
                 (("names", "wurzel, abs, min, max, ganzzahl, sin, cos, pi"),)),
        Notation(P, "r = runden(x, 2)", N_("Auf 2 Stellen runden (ab 5 wird aufgerundet)")),
    ]),
    (N_("Eingabe"), [
        Notation(I, "n einlesen", N_("Liest einen Wert in die Variable n")),
        Notation(I, "Eingabe: a, b", N_("Mehrere Werte nacheinander einlesen")),
        Notation(I, '"Wie alt bist du?" alter', N_("Der Text in Anführungszeichen ist die Frage an den Benutzer")),
    ]),
    (N_("Ausgabe"), [
        Notation(O, "summe ausgeben", N_("Gibt den Wert der Variablen summe aus")),
        Notation(O, '"Summe: " summe', N_("Text und Wert nebeneinander")),
        Notation(O, "Ausgabe: x * 2", N_("Ergebnis einer Rechnung ausgeben")),
        Notation(O, '"Fertig!"', N_("Nur Text ausgeben")),
    ]),
    (N_("Bedingungen (Verzweigung)"), [
        Notation(D, "x > 0 ?", N_("Vergleiche: {ops} – das Fragezeichen am Ende darf stehen"),
                 (("ops", "<  >  <=  >="),)),
        Notation(D, "x = 0", N_("In einer Bedingung vergleicht {a} (auch {b})"), (("a", "="), ("b", "=="))),
        Notation(D, "x ≠ 0", N_("Ungleich: {a}, {b} oder {c}"), (("a", "≠"), ("b", "<>"), ("c", "!="))),
        Notation(D, "x ≥ 1 und x ≤ 6", N_("Verknüpfen mit {words}; {signs} gibt es mit Rechtsklick in der "
                                          "Texteingabe"),
                 (("words", "und, oder, nicht"), ("signs", "≤ ≥ ≠"))),
        Notation(D, 'antwort = "ja"', N_("Text vergleichen (in Anführungszeichen)")),
        Notation(D, "wahl", N_("Mehrfachverzweigung: Ausgänge mit Werten beschriften, z. B. {labels}"),
                 (("labels", "1, 2, sonst"),)),
    ]),
    (N_("Schleifen"), [
        Notation(L, "solange i < 10", N_("Kopfbedingung: wird vor jedem Durchlauf geprüft"), part=LOOP_BEGIN),
        Notation(L, "bis i >= 10", N_("Fußbedingung: wird nach jedem Durchlauf geprüft (Schleifenbeginn: {head})"),
                 (("head", "wiederhole"),), part=LOOP_END),
        Notation(L, "für i = 1 bis 10", N_("Zählschleife: i läuft von 1 bis 10"), part=LOOP_BEGIN),
        Notation(L, "für i = 10 bis 0 schritt -2", N_("Zählschleife mit Schrittweite (auch rückwärts)"),
                 part=LOOP_BEGIN),
        Notation(L, "3-mal", N_("Feste Anzahl von Durchläufen (auch {alt})"), (("alt", "wiederhole n mal"),),
                 part=LOOP_BEGIN),
    ]),
    (N_("Unterprogramme"), [
        Notation(U, "Summe berechnen", N_("Ruft das Unterprogramm „{name}“ auf; die Variablen gelten "
                                          "überall"), (("name", "Summe berechnen"),)),
        Notation(S, "doppelt(n)", N_("Start eines Unterprogramms mit Parameter n")),
        Notation(U, "y := doppelt(x)", N_("Aufruf mit Wert: x geht an n, das Ergebnis an y")),
        Notation(P, "return n * 2", N_("Ergebnis zurückgeben (auch {alt}) – auch im Baustein Ende möglich"),
                 (("alt", "Rückgabe: n * 2"),)),
    ]),
]


def all_notations() -> list[Notation]:
    return [entry for _heading, entries in SECTIONS for entry in entries]
