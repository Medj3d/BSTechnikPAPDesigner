"""Lernbeispiele: mitgelieferte Projekte zum Ausprobieren (wie die Tutorials des PapDesigners).

Sie liegen in ``assets/examples`` und werden mit ``tools/make_examples.py`` erzeugt. Geöffnet wird
immer eine unbenannte Kopie – „Speichern“ fragt nach dem Ort, das Beispiel selbst bleibt unverändert.
"""

from __future__ import annotations

import os

from app.i18n import N_
from app.resources import asset_path

# Datei → Titel im Menü (deutscher Quelltext, übersetzt beim Anzeigen)
EXAMPLES = (
    ("Lernbeispiel_1_Ablaufplan.pap", N_("&1 Ablaufplan: Eingabe, Verarbeitung, Ausgabe")),
    ("Lernbeispiel_2_Verzweigungen.pap", N_("&2 Verzweigungen")),
    ("Lernbeispiel_3_Schleifen.pap", N_("&3 Schleifen mit Kopf- und Fußbedingung")),
    ("Lernbeispiel_4_Unterprogramme.pap", N_("&4 Unterprogramme")),
    ("Lernbeispiel_5_Programmierung.pap", N_("&5 Programmierung: Primzahlen")),
)


def example_files() -> list[tuple[str, str]]:
    """(Pfad, Titel-Quelltext) aller vorhandenen Lernbeispiele."""
    found = []
    for file_name, title in EXAMPLES:
        path = asset_path(os.path.join("examples", file_name))
        if os.path.isfile(path):
            found.append((path, title))
    return found
