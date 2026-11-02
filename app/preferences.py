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

START_END = "start_end"
LOOSE_ENDS = "loose_ends"
QUICK_MENU = "quick_menu"
ROUNDED_LINES = "rounded_lines"
WARNING_MARKS = "warning_marks"
EXTENDED_CHECKS = "extended_checks"


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
)

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
