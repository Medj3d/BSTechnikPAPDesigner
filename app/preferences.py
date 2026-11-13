"""Ein/Aus-Einstellungen des Programms.

Jede Einstellung ist hier einmal beschrieben (Name, Standard, Text, Abschnitt des Einstellungsfensters).
``ActionRegistry`` macht aus jeder einen Schalter (QAction), damit sie im Einstellungsfenster, in der Suche und
per Tastenkürzel gleich funktioniert. Szene und Verbindungen lesen den aktuellen Wert mit ``enabled``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.i18n import N_

# Abschnitte des Einstellungsfensters
SECTION_NEW = N_("Neue Projekte")
SECTION_ARROWS = N_("Pfeile")
SECTION_CHECKS = N_("Prüfung")
SECTION_TOOLS = N_("Knöpfe in der Werkzeugleiste")

START_END = "start_end"
LOOSE_ENDS = "loose_ends"
QUICK_MENU = "quick_menu"
ROUNDED_LINES = "rounded_lines"
WARNING_MARKS = "warning_marks"
EXTENDED_CHECKS = "extended_checks"
# Zusatzknöpfe: Standard ist eine schlichte Werkzeugleiste; wer mehr braucht, schaltet es hier zu
TOOL_FILE = "tool_file"
TOOL_UNDO = "tool_undo"
TOOL_DELETE = "tool_delete"
TOOL_ZOOM = "tool_zoom"
TOOL_LAYOUT = "tool_layout"
TOOL_SIMULATION = "tool_simulation"
TOOL_GENERATE_CODE = "tool_generate_code"
TOOL_STRUCTOGRAM = "tool_structogram"
TOOL_PDF = "tool_pdf"
TOOL_PRINT = "tool_print"
TOOL_CLIPBOARD = "tool_clipboard"
TOOL_GRID = "tool_grid"
TOOL_ALIGN = "tool_align"
TOOL_CODE_VIEW = "tool_code_view"
TOOL_MINIMAP = "tool_minimap"
TOOL_BREAKPOINTS = "tool_breakpoints"
TOOL_TEACHER = "tool_teacher"


@dataclass(frozen=True)
class Preference:
    name: str
    default: bool
    text: str
    tip: str
    section: str


PREFERENCES = (
    Preference(START_END, True, N_("Mit Start und Ende beginnen"),
               N_("Neue Projekte enthalten gleich Start → Ende; neue Bausteine kommen dazwischen"), SECTION_NEW),
    Preference(LOOSE_ENDS, False, N_("Pfeil bleibt im Leeren stehen"),
               N_("Ein ins Leere gezogener Pfeil bleibt mit losem Ende stehen und ist rot, bis er angeschlossen ist"),
               SECTION_ARROWS),
    Preference(QUICK_MENU, True, N_("Schnellmenü im Leeren"),
               N_("Beim Ziehen eines Pfeils ins Leere fragen, welcher Baustein dort entstehen soll"), SECTION_ARROWS),
    Preference(ROUNDED_LINES, True, N_("Abgerundete Ecken"),
               N_("Pfeile knicken mit kleinem Bogen statt mit harter Ecke"), SECTION_ARROWS),
    Preference(WARNING_MARKS, True, N_("Warnzeichen auf Pfeilen"),
               N_("Auf roten und gelben Pfeilen ein Zeichen zeigen; der Grund erscheint beim Überfahren"),
               SECTION_CHECKS),
    Preference(EXTENDED_CHECKS, False, N_("Erweiterte Prüfung"),
               N_("Auch unbeschriftete Ausgänge, doppelte Beschriftungen und Wege ohne Ende gelb markieren"),
               SECTION_CHECKS),
    # Knöpfe der Werkzeugleiste, in ihrer Reihenfolge; an = gehört zur schlichten Standardleiste
    Preference(TOOL_FILE, True, N_("Neu, Öffnen, Speichern"), N_("Projekte anlegen, öffnen und speichern"),
               SECTION_TOOLS),
    Preference(TOOL_UNDO, True, N_("Rückgängig, Wiederholen"), N_("Die letzten Schritte zurücknehmen oder wiederholen"),
               SECTION_TOOLS),
    Preference(TOOL_CLIPBOARD, False, N_("Ausschneiden, Kopieren, Einfügen"),
               N_("Knöpfe für die Zwischenablage (sonst Strg+X, Strg+C, Strg+V)"), SECTION_TOOLS),
    Preference(TOOL_DELETE, True, N_("Löschen"), N_("Die markierten Bausteine und Pfeile entfernen (sonst Entf)"),
               SECTION_TOOLS),
    Preference(TOOL_ZOOM, True, N_("Zoom"), N_("Verkleinern, 100 %, Vergrößern und ganzen Plan einpassen"),
               SECTION_TOOLS),
    Preference(TOOL_GRID, False, N_("Raster und Einrasten"),
               N_("Knöpfe zum Ein- und Ausschalten von Raster und Einrasten"), SECTION_TOOLS),
    Preference(TOOL_ALIGN, False, N_("Ausrichten und Verteilen"),
               N_("Knöpfe zum Ausrichten mehrerer markierter Bausteine (auch im Menü „Anordnen“)"), SECTION_TOOLS),
    Preference(TOOL_LAYOUT, True, N_("Automatisch anordnen"), N_("Den ganzen Plan übersichtlich neu anordnen"),
               SECTION_TOOLS),
    Preference(TOOL_SIMULATION, True, N_("Schreibtischtest"), N_("Den Plan Schritt für Schritt durchspielen"),
               SECTION_TOOLS),
    Preference(TOOL_GENERATE_CODE, False, N_("Code erzeugen"), N_("Pseudocode, Python oder Java aus dem PAP erzeugen"),
               SECTION_TOOLS),
    Preference(TOOL_STRUCTOGRAM, True, N_("Struktogramm"), N_("Ablauf als Struktogramm (Nassi-Shneiderman)"),
               SECTION_TOOLS),
    Preference(TOOL_CODE_VIEW, False, N_("Code-Ansicht"),
               N_("Zeigt beim Zeichnen sofort den passenden Code; ein Klick auf eine Zeile markiert den Baustein"),
               SECTION_TOOLS),
    Preference(TOOL_MINIMAP, False, N_("Minikarte"),
               N_("Kleine Übersicht des ganzen Plans am rechten Rand – praktisch bei großen Plänen"), SECTION_TOOLS),
    Preference(TOOL_BREAKPOINTS, False, N_("Haltepunkte"),
               N_("Der Schreibtischtest hält vor markierten Bausteinen an; geänderte Variablen sind hervorgehoben"),
               SECTION_TOOLS),
    Preference(TOOL_TEACHER, False, N_("Lehrermodus"),
               N_("Aufgaben stellen: Aufgabenstellung offen, Musterlösung mit Passwort verschlüsselt"),
               SECTION_TOOLS),
    Preference(TOOL_PDF, False, N_("Als PDF exportieren"), N_("Den Plan als PDF speichern, z. B. für die Abgabe (Strg+E)"),
               SECTION_TOOLS),
    Preference(TOOL_PRINT, True, N_("Drucken"), N_("Den Plan drucken"), SECTION_TOOLS),
)

TOOLS = tuple(preference.name for preference in PREFERENCES if preference.section == SECTION_TOOLS)

_values: dict[str, bool] = {}


def action_name(name: str) -> str:
    """Name des Schalters in ``ActionRegistry``."""
    return f"preference_{name}"


def default(name: str) -> bool:
    return next(preference.default for preference in PREFERENCES if preference.name == name)


def enabled(name: str) -> bool:
    return _values.get(name, default(name))


def set_enabled(name: str, value: bool) -> None:
    _values[name] = bool(value)


def reset() -> None:
    """Alle Einstellungen wieder auf ihren Standard (für neue Fenster in Tests)."""
    _values.clear()
