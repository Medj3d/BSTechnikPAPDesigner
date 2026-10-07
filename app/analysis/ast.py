"""Strukturbaum eines Programmablaufplans.

Der Strukturbaum ist die gemeinsame Grundlage für Code-Erzeugung,
Struktogramm (Nassi-Shneiderman) und automatisches Layout. Er wird von
``app.analysis.structure.structure_program`` aus einem ``FlowGraph``
erzeugt.

Ein Programm ist eine Folge von Anweisungen (``Block``):

* ``Action``          – Eingabe, Ausgabe, Vorgang, Unterprogramm-Aufruf
* ``If``              – Verzweigung mit Ja- und Nein-Zweig
* ``WhileLoop``       – kopfgesteuerte Schleife (Bedingung vor dem Rumpf)
* ``DoWhileLoop``     – fußgesteuerte Schleife (Bedingung nach dem Rumpf)
* ``LimitLoop``       – Schleifenbegrenzung (Schleifenbeginn … Schleifenende)
* ``Loop``            – Schleife ohne eigene Bedingung („wiederhole“); sie wird über
                        ``Break`` oder ein Ende verlassen, ``Continue`` beginnt den
                        nächsten Durchlauf
* ``Break``           – Sprung aus der innersten Schleife heraus hinter ihr Ende
* ``Unstructured``    – Teil, der sich nicht strukturiert darstellen lässt
                        (Sprünge); enthält die betroffenen Element-IDs

Alle Knoten tragen die ID des zugehörigen Diagrammelements, damit z. B.
das Layout Positionen zurückschreiben oder die Simulation Elemente
hervorheben kann.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stmt:
    # True: Wiederholung von Bausteinen, die im Plan nur einmal vorkommen (z. B. der
    # Teil vor der Prüfung einer Schleife mit Abbruch in der Mitte, oder ein Baustein,
    # in den mehrere Zweige münden). Das Layout überspringt solche Kopien.
    repeated: bool = field(default=False, kw_only=True)


@dataclass
class Block:
    statements: list = field(default_factory=list)

    def __iter__(self):
        return iter(self.statements)

    def __len__(self) -> int:
        return len(self.statements)


@dataclass
class Action(Stmt):
    kind: str            # "input" | "output" | "process" | "subprogram" | "junction"
    text: str
    element_id: str
    comments: list = field(default_factory=list)   # zugeordnete Kommentartexte


@dataclass
class If(Stmt):
    condition: str
    element_id: str
    then_block: Block    # Zweig bei „ja“ (bzw. erster Ausgang)
    else_block: Block    # Zweig bei „nein“ (kann leer sein)
    then_label: str = "ja"
    else_label: str = "nein"
    comments: list = field(default_factory=list)


@dataclass
class WhileLoop(Stmt):
    """Kopfgesteuert: solange ``condition`` (bzw. nicht, wenn ``negate``) → Rumpf."""
    condition: str
    element_id: str      # die Verzweigung, die die Schleife steuert
    body: Block
    negate: bool = False  # True: Rumpf läuft, solange die Bedingung NICHT erfüllt ist
    comments: list = field(default_factory=list)


@dataclass
class DoWhileLoop(Stmt):
    """Fußgesteuert: Rumpf, dann wiederholen solange ``condition`` (bzw. nicht, wenn ``negate``)."""
    condition: str
    element_id: str
    body: Block
    negate: bool = False
    comments: list = field(default_factory=list)


@dataclass
class LimitLoop(Stmt):
    """Schleifenbegrenzung nach DIN 66001 (Schleifenbeginn … Schleifenende)."""
    header: str          # Text des Schleifenbeginns, z. B. „Für i = 1 bis n“
    footer: str          # Text des Schleifenendes, z. B. „solange x < 10“ (kann leer sein)
    begin_id: str
    end_id: str | None
    body: Block
    comments: list = field(default_factory=list)


@dataclass
class Loop(Stmt):
    """Schleife ohne eigene Bedingung, z. B. ein Menü: Eingabe → Auswahl → zurück zur Eingabe."""
    body: Block
    element_id: str      # erster Baustein der Schleife (Ziel der Rücksprünge)


@dataclass
class Continue(Stmt):
    """Springt zum Anfang der innersten ``Loop`` (nächster Durchlauf)."""
    element_id: str


@dataclass
class Break(Stmt):
    """Verlässt die innerste Schleife (der Ablauf springt hinter ihr Ende)."""
    element_id: str      # Baustein, zu dem gesprungen wird


@dataclass
class EndStmt(Stmt):
    """Ende-Element erreicht (Programmende; innerhalb eines Zweigs = vorzeitiges Ende)."""
    text: str
    element_id: str


@dataclass
class Unstructured(Stmt):
    """Nicht strukturierbarer Rest (z. B. Sprünge in Zweige hinein)."""
    note: str
    element_ids: list = field(default_factory=list)
    fatal: bool = False  # True: Hier geht ein Sprung verloren – der Code kann den Ablauf nicht fortsetzen


@dataclass
class Program:
    name: str            # Text des Start-Elements
    start_id: str
    end_id: str | None   # erreichtes Ende-Element (erstes)
    end_text: str
    body: Block
    warnings: list = field(default_factory=list)   # Hinweise der Strukturierung
