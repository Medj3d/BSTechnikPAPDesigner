"""Erzeugt die Lernbeispiele (``assets/examples/*.pap``) – wie die Tutorials des PapDesigners.

Fünf Projekte, die aufeinander aufbauen: Ablaufplan, Verzweigungen, Schleifen, Unterprogramme und
Programmierung. Jedes erklärt in Kommentaren, was es zeigt, und läuft im Schreibtischtest durch.

Aufruf (aus dem Projektordner)::

    python tools/make_examples.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from app.fileformat.serializer import save_diagram  # noqa: E402
from app.items.factory import new_element_data  # noqa: E402
from app.model.diagram import ConnectionData, Diagram, SubprogramPage, new_id  # noqa: E402
from app.model.element_types import LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, ElementType as T  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "assets", "examples")
AUTHOR = "BS Technik"
# Abstand der Zeilen und der Spalten
ROW = 100
COLUMN = 260


class Plan:
    """Bausteine und Pfeile einer Seite."""

    def __init__(self):
        self.elements = []
        self.connections = []

    def add(self, element_type: T, column: float, row: float, text: str | None = None, part: str | None = None):
        properties = {LOOP_PART_KEY: part} if part else None
        element = new_element_data(element_type, column * COLUMN, row * ROW, text=text, properties=properties)
        self.elements.append(element)
        return element

    def comment(self, column: float, row: float, text: str, attach=None, port: str = "left"):
        note = self.add(T.COMMENT, column, row, text)
        lines = text.count("\n") + 1
        note.width, note.height = 300.0, max(60.0, 20.0 * lines + 20)
        if attach is not None:
            self.link(note, attach, "left" if port == "right" else "right", port)
        return note

    def link(self, source, target, source_port: str = "bottom", target_port: str = "top", label: str = ""):
        self.connections.append(ConnectionData(new_id(), source.id, target.id, source_port, target_port, label))

    def chain(self, *elements):
        for upper, lower in zip(elements, elements[1:]):
            self.link(upper, lower)


def project(name: str, description: str, main: Plan, pages: dict[str, Plan] | None = None) -> Diagram:
    diagram = Diagram(elements=main.elements, connections=main.connections)
    diagram.meta.name = name
    diagram.meta.author = AUTHOR
    diagram.meta.description = description
    for page_name, page in (pages or {}).items():
        bottom = max(element.y for element in page.elements)
        diagram.subprograms.append(SubprogramPage(page_name, page.elements, page.connections,
                                                  view_center_y=bottom / 2))
    return diagram


# ------------------------------------------------------------------ 1 Ablaufplan
def example_flow() -> Diagram:
    p = Plan()
    start = p.add(T.START, 0, 0, "Start")
    read = p.add(T.INPUT, 0, 1, "Radius r einlesen")
    area = p.add(T.PROCESS, 0, 2, "fläche = runden(pi * r ^ 2, 2)")
    show = p.add(T.OUTPUT, 0, 3, "„Fläche:“ fläche")
    end = p.add(T.END, 0, 4, "Ende")
    p.chain(start, read, area, show, end)
    p.comment(-1.4, 0, "Jeder Ablauf beginnt mit Start\nund endet mit Ende.", start)
    p.comment(-1.4, 1, "Eingabe (Parallelogramm):\nDer Wert landet in der Variablen r.", read)
    p.comment(-1.4, 2, "Verarbeitung (Rechteck): links die\nVariable, rechts die Rechnung –\n"
                       "hier auf 2 Stellen gerundet.", area)
    p.comment(-1.4, 3, "Ausgabe: Text in „…“, danach\ndie Variable, deren Wert erscheint.", show)
    p.comment(1.4, 1.5, "Ausprobieren: F9 öffnet den Schreibtischtest,\nF5 lässt den Plan laufen. Mit F10 geht es\n"
                        "Schritt für Schritt, mit Strg+F10 zurück.")
    return project("Lernbeispiel 1 – Ablaufplan", "Kreisfläche: Eingabe, Verarbeitung, Ausgabe.", p)


# ------------------------------------------------------------------ 2 Verzweigungen
def example_branches() -> Diagram:
    p = Plan()
    start = p.add(T.START, 0, 0, "Start")
    read = p.add(T.INPUT, 0, 1, "Punkte p einlesen")
    passed = p.add(T.DECISION, 0, 2.3, "p >= 50 ?")
    top = p.add(T.DECISION, 0, 3.9, "p >= 90 ?")
    very_good = p.add(T.OUTPUT, 0, 5.3, "„sehr gut“ ausgeben")
    good = p.add(T.OUTPUT, 1, 5.3, "„bestanden“ ausgeben")
    failed = p.add(T.OUTPUT, 2, 3.9, "„nicht bestanden“ ausgeben")
    inner = p.add(T.JUNCTION, 0, 6.3)
    outer = p.add(T.JUNCTION, 0, 7.1)
    end = p.add(T.END, 0, 8, "Ende")
    p.chain(start, read, passed)
    p.link(passed, top, "bottom", "top", "ja")
    p.link(passed, failed, "right", "top", "nein")
    p.link(top, very_good, "bottom", "top", "ja")
    p.link(top, good, "right", "top", "nein")
    p.link(very_good, inner)
    p.link(good, inner, "bottom", "right")
    p.link(inner, outer)
    p.link(failed, outer, "bottom", "right")
    p.link(outer, end)
    p.comment(-1.5, 2.3, "Verzweigung (Raute): Die Bedingung\nentscheidet, welcher Pfeil gilt –\n"
                         "beschriftet mit „ja“ und „nein“.", passed)
    p.comment(-1.5, 3.9, "Verzweigungen lassen sich\nverschachteln.", top)
    p.comment(-1.5, 6.7, "Verbindungspunkte führen die Wege\nwieder zusammen (Rechtsklick auf\n"
                         "einen Pfeil → Verbindungspunkt).", inner)
    return project("Lernbeispiel 2 – Verzweigungen", "Notenrechner mit verschachtelter Verzweigung.", p)


# ------------------------------------------------------------------ 3 Schleifen
def example_loops() -> Diagram:
    p = Plan()
    start = p.add(T.START, 0, 0, "Start")
    repeat = p.add(T.LOOP, 0, 1, "wiederhole", LOOP_BEGIN)
    read = p.add(T.INPUT, 0, 2, "Zahl n einlesen")
    until = p.add(T.LOOP, 0, 3, "bis n > 0", LOOP_END)
    init = p.add(T.PROCESS, 0, 4, "summe = 0\ni = 1")
    loop = p.add(T.LOOP, 0, 5, "solange i <= n", LOOP_BEGIN)
    add = p.add(T.PROCESS, 0, 6, "summe = summe + i")
    step = p.add(T.PROCESS, 0, 7, "i = i + 1")
    loop_end = p.add(T.LOOP, 0, 8, "Schleifenende", LOOP_END)
    show = p.add(T.OUTPUT, 0, 9, "„Summe:“ summe")
    end = p.add(T.END, 0, 10, "Ende")
    p.chain(start, repeat, read, until, init, loop, add, step, loop_end, show, end)
    p.comment(-1.5, 2, "Schleife mit Fußbedingung: Der Inhalt\nläuft mindestens einmal; geprüft wird\n"
                       "am Ende („bis …“). Hier: so lange\nfragen, bis n positiv ist.", until)
    p.comment(-1.5, 6, "Schleife mit Kopfbedingung: geprüft\nwird vorher („solange …“) – ist sie\n"
                       "falsch, läuft der Inhalt gar nicht.", loop)
    p.comment(1.4, 4, "Mehrere Zuweisungen in einem\nBaustein: je Zeile eine\n(Zeilenumbruch mit Strg+Enter).", init,
              "right")
    p.comment(1.4, 7.5, "Einfügen → Schleife mit Kopf- bzw.\nFußbedingung legt beide Teile an.\n"
                        "Eine Schleife geht auch mit einer\nVerzweigung und einem Pfeil zurück.")
    return project("Lernbeispiel 3 – Schleifen", "Summe 1 + 2 + … + n mit Fuß- und Kopfbedingung.", p)


# ------------------------------------------------------------------ 4 Unterprogramme
def example_subprograms() -> Diagram:
    main = Plan()
    start = main.add(T.START, 0, 0, "Start")
    hello = main.add(T.SUBPROGRAM, 0, 1, "Begrüßung")
    read_a = main.add(T.INPUT, 0, 2, "Zahl a einlesen")
    read_b = main.add(T.INPUT, 0, 3, "Zahl b einlesen")
    gcd = main.add(T.SUBPROGRAM, 0, 4, "ggT")
    show = main.add(T.OUTPUT, 0, 5, "„größter gemeinsamer Teiler:“ a")
    end = main.add(T.END, 0, 6, "Ende")
    main.chain(start, hello, read_a, read_b, gcd, show, end)
    main.comment(-1.5, 1, "Ein Unterprogramm-Baustein ruft den\nAblauf auf, dessen Start so heißt.\n"
                          "Jedes Unterprogramm hat eine eigene\nSeite (Reiter unten).", hello)
    main.comment(-1.5, 4, "Strg+Doppelklick öffnet das\nUnterprogramm, Alt+← führt zurück.", gcd)
    main.comment(1.4, 2.5, "Mehrfach Benötigtes gehört in ein\nUnterprogramm: markieren, dann\n"
                           "Bearbeiten → Auswahl in Unterprogramm\nauslagern (Strg+Alt+U).")

    greeting = Plan()
    g_start = greeting.add(T.START, 0, 0, "Begrüßung")
    g_show = greeting.add(T.OUTPUT, 0, 1, "„Willkommen beim ggT-Rechner!“ ausgeben")
    g_end = greeting.add(T.END, 0, 2, "Ende")
    greeting.chain(g_start, g_show, g_end)

    euclid = Plan()
    e_start = euclid.add(T.START, 0, 0, "ggT")
    e_loop = euclid.add(T.LOOP, 0, 1, "solange b ≠ 0", LOOP_BEGIN)
    e_rest = euclid.add(T.PROCESS, 0, 2, "r = a mod b")
    e_swap = euclid.add(T.PROCESS, 0, 3, "a = b\nb = r")
    e_loop_end = euclid.add(T.LOOP, 0, 4, "Schleifenende", LOOP_END)
    e_end = euclid.add(T.END, 0, 5, "Ende")
    euclid.chain(e_start, e_loop, e_rest, e_swap, e_loop_end, e_end)
    euclid.comment(-1.5, 0, "Euklidischer Algorithmus: Am Ende\nsteht der ggT in a. Unterprogramme\n"
                            "arbeiten mit denselben Variablen\nwie das Hauptprogramm.", e_start)
    euclid.comment(1.4, 2, "„mod“ ist der Rest der Division;\n„≠“ gibt es unter Bearbeiten →\nSonderzeichen.", e_rest,
                   "right")
    return project("Lernbeispiel 4 – Unterprogramme", "ggT mit dem euklidischen Algorithmus als Unterprogramm.",
                   main, {"Begrüßung": greeting, "ggT": euclid})


# ------------------------------------------------------------------ 5 Programmierung
def example_programming() -> Diagram:
    main = Plan()
    start = main.add(T.START, 0, 0, "Start")
    read = main.add(T.INPUT, 0, 1, "Obergrenze n einlesen")
    init = main.add(T.PROCESS, 0, 2, "z = 2")
    loop = main.add(T.LOOP, 0, 3, "solange z <= n", LOOP_BEGIN)
    check = main.add(T.SUBPROGRAM, 0, 4, "prüfePrim")
    prime = main.add(T.DECISION, 0, 5.3, "prim ?")
    show = main.add(T.OUTPUT, 0, 6.7, "z ausgeben")
    join = main.add(T.JUNCTION, 0, 7.6)
    step = main.add(T.PROCESS, 0, 8.4, "z = z + 1")
    loop_end = main.add(T.LOOP, 0, 9.4, "Schleifenende", LOOP_END)
    end = main.add(T.END, 0, 10.4, "Ende")
    main.chain(start, read, init, loop, check, prime)
    main.link(prime, show, "bottom", "top", "ja")
    main.link(prime, join, "right", "right", "nein")
    main.chain(show, join, step, loop_end, end)
    main.comment(-1.5, 1, "Gibt alle Primzahlen von 2 bis n aus.", start)
    main.comment(-1.5, 5.3, "„prim“ ist wahr oder falsch –\ngesetzt im Unterprogramm.", prime)
    main.comment(1.4, 2, "Extras → Code erzeugen macht aus dem\nPlan Pseudocode, Python oder Java;\n"
                         "Extras → Struktogramm zeigt ihn als\nNassi-Shneiderman-Diagramm.")

    test = Plan()
    t_start = test.add(T.START, 0, 0, "prüfePrim")
    t_init = test.add(T.PROCESS, 0, 1, "prim = wahr\nt = 2")
    t_loop = test.add(T.LOOP, 0, 2, "solange t * t <= z und prim", LOOP_BEGIN)
    t_divides = test.add(T.DECISION, 0, 3.3, "z mod t = 0 ?")
    t_no = test.add(T.PROCESS, 0, 4.7, "prim = falsch")
    t_join = test.add(T.JUNCTION, 0, 5.6)
    t_step = test.add(T.PROCESS, 0, 6.4, "t = t + 1")
    t_loop_end = test.add(T.LOOP, 0, 7.4, "Schleifenende", LOOP_END)
    t_end = test.add(T.END, 0, 8.4, "Ende")
    test.chain(t_start, t_init, t_loop, t_divides)
    test.link(t_divides, t_no, "bottom", "top", "ja")
    test.link(t_divides, t_join, "right", "right", "nein")
    test.chain(t_no, t_join, t_step, t_loop_end, t_end)
    test.comment(-1.5, 2, "Teiler bis zur Wurzel von z prüfen;\nder erste Teiler beendet die Suche.", t_loop)
    return project("Lernbeispiel 5 – Programmierung", "Primzahlen bis n – mit Unterprogramm, Schleifen und "
                   "Verzweigung, bereit für die Code-Erzeugung.", main, {"prüfePrim": test})


EXAMPLES = {
    "Lernbeispiel_1_Ablaufplan.pap": example_flow,
    "Lernbeispiel_2_Verzweigungen.pap": example_branches,
    "Lernbeispiel_3_Schleifen.pap": example_loops,
    "Lernbeispiel_4_Unterprogramme.pap": example_subprograms,
    "Lernbeispiel_5_Programmierung.pap": example_programming,
}


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for file_name, build in EXAMPLES.items():
        path = os.path.abspath(os.path.join(OUTPUT_DIR, file_name))
        save_diagram(build(), path)
        print("geschrieben:", path)


if __name__ == "__main__":
    main()
