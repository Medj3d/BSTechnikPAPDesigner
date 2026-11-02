"""Textvergleich für die Suchfelder: unabhängig von Groß- und Kleinschreibung und von Umlauten.

„prüf“, „pruef“ und „PRUF“ finden alle „Prüfung“; jedes Wort der Eingabe muss vorkommen.
"""

from __future__ import annotations

import unicodedata

_GERMAN = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _forms(text: str) -> tuple[str, str]:
    """Der Text ohne Akzente und mit ausgeschriebenen Umlauten."""
    folded = str(text or "").casefold().replace("&", "")
    plain = "".join(c for c in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(c))
    return plain, folded.translate(_GERMAN)


def score(query: str, *texts: str) -> int | None:
    """Wie gut ``query`` passt (kleiner = besser), ``None``, wenn nicht. Vorne in ``texts`` zählt mehr."""
    words = str(query or "").split()
    if not words:
        return 0
    forms = [_forms(text) for text in texts]
    total = 0
    for word in words:
        wanted = _forms(word)
        best = None
        for position, (plain, german) in enumerate(forms):
            if any(w and (h.startswith(w) or f" {w}" in h) for w, h in zip(wanted, (plain, german))):
                best = position * 2
                break
            if any(w and w in h for w, h in zip(wanted, (plain, german))):
                best = position * 2 + 1
                break
        if best is None:
            return None
        total += best
    return total


def matches(query: str, *texts: str) -> bool:
    return score(query, *texts) is not None
