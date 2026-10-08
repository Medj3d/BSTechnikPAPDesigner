"""Prüft die Übersetzungen in ``assets/translations/<Sprache>.json`` gegen den Quelltext.

    python tools\\check_translations.py             # alle Sprachen
    python tools\\check_translations.py fr ja       # nur diese
    python tools\\check_translations.py --warnings  # auch Hinweise anzeigen

**Fehler** (die Tests schlagen fehl): fehlender Text, leere Übersetzung, andere Platzhalter als im Quelltext,
anderer Tastenkürzel-Buchstabe (``&``), andere Zahl von Zeilenumbrüchen, andere Leerzeichen am Rand, kein Text in
der Schrift der Sprache, übrig gebliebene deutsche Umlaute, nicht ausgelesene („veraltete“) Schlüssel.
**Hinweise**: fehlende Auslassungspunkte, auffällige Länge, Übersetzung gleich dem Deutschen.

Texte, die nur in erzeugten Programmen stehen (``tr_code``), braucht nur das Englische.
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from app import i18n  # noqa: E402
from tools.extract_strings import collect, is_required  # noqa: E402

# Schrift, in der (fast) jede Übersetzung Buchstaben haben muss
SCRIPTS = {
    "ru": re.compile("[Ѐ-ӿ]"),
    "ar": re.compile("[؀-ۿݐ-ݿ]"),
    "zh": re.compile("[一-鿿]"),
    "ja": re.compile("[぀-ヿ一-鿿]"),
}
# Wörter, die in jeder Sprache gleich bleiben dürfen (Eigennamen, Dateiformate, Programmiersprachen)
SAME_EVERYWHERE = {"png", "svg", "pdf", "python", "java", "code", "ok", "pap", "ctrl", "shift", "alt", "esc", "f1",
                   "f2", "f5", "f9", "f10", "html", "json", "xml", "zip", "gif", "ico", "px", "pseudocode",
                   "nassi", "shneiderman", "bs", "technik", "pap-designer", "designer", "qt", "pyside6", "version",
                   "info", "a4", "dpi", "x", "y", "strg", "enter", "tab", "del", "entf", "umschalt", "pfeiltasten",
                   "zoom", "todo", "nan", "mod", "mb", "exe", "windows", "papdesigner", "update", "updates",
                   "setup", "start", "text", "name", "id", "format", "administrator"}
# Deutsche Buchstaben, die in einer Übersetzung nichts verloren haben (ü gibt es auch im Spanischen/Französischen)
GERMAN_LETTERS = {code: re.compile(r"[äöÄÖß]" if code in ("es", "fr", "pt") else r"[äöüÄÖÜß]")
                  for code in i18n.LANGUAGES}
NAMES_WITH_UMLAUTS = ("Schäfer",)  # Eigennamen der Urheber dürfen bleiben
PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def mnemonics(text: str) -> int:
    """Zahl der Tastenkürzel-Buchstaben (``&X``); ``&&`` ist ein echtes „&“."""
    return len(re.findall(r"(?<!&)&(?!&)", text))


def words_of(text: str) -> list[str]:
    stripped = PLACEHOLDER.sub(" ", text)
    return re.findall(r"[A-Za-zÄÖÜäöüßÀ-ÿ]{2,}", stripped)


def meaningful_words(source: str) -> list[str]:
    return [w for w in words_of(source) if w.lower() not in SAME_EVERYWHERE]


def _edge_spaces(text: str) -> tuple[int, int]:
    return len(text) - len(text.lstrip()), len(text) - len(text.rstrip())


def check_entry(code: str, key: str, source: str, target) -> tuple[list[str], list[str]]:
    """Fehler und Hinweise für eine einzelne Übersetzung (``source`` = deutscher Text)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(target, str) or not target.strip():
        return [f"{code}: leer: {key!r}"], []
    if i18n.placeholders(source) != i18n.placeholders(target):
        errors.append(f"{code}: Platzhalter {i18n.placeholders(source)} ≠ {i18n.placeholders(target)}: "
                      f"{key!r} → {target!r}")
    if mnemonics(source) != mnemonics(target):
        errors.append(f"{code}: Tastenkürzel (&) {mnemonics(source)} ≠ {mnemonics(target)}: {key!r} → {target!r}")
    if source.count("&&") != target.count("&&"):
        errors.append(f"{code}: „&&“ nicht übernommen: {key!r} → {target!r}")
    if source.count("\n") != target.count("\n"):
        errors.append(f"{code}: Zeilenumbrüche {source.count(chr(10))} ≠ {target.count(chr(10))}: "
                      f"{key!r} → {target!r}")
    if _edge_spaces(source) != _edge_spaces(target):
        errors.append(f"{code}: Leerzeichen am Rand anders: {key!r} → {target!r}")
    letters = GERMAN_LETTERS.get(code)
    if letters is not None and letters.search(target) and not any(name in target for name in NAMES_WITH_UMLAUTS):
        errors.append(f"{code}: deutsche Umlaute in der Übersetzung: {key!r} → {target!r}")
    meaningful = meaningful_words(source)
    script = SCRIPTS.get(code)
    if script is not None and meaningful and not script.search(target):
        errors.append(f"{code}: kein Text in der Schrift der Sprache: {key!r} → {target!r}")
    if target == source and len(meaningful) >= 2:
        warnings.append(f"{code}: Übersetzung gleich dem Deutschen: {key!r}")
    if source.rstrip().endswith("…") and not re.search(r"(…|\.\.\.)\s*$", target):
        warnings.append(f"{code}: Auslassungspunkte fehlen: {key!r} → {target!r}")
    if len(source) > 25:
        low = 0.12 if code in ("zh", "ja") else 0.25
        ratio = len(target) / len(source)
        if ratio > 3.5 or ratio < low:
            warnings.append(f"{code}: auffällige Länge ({ratio:.1f}×): {key!r} → {target!r}")
    return errors, warnings


def check_language(code: str, entries: dict) -> tuple[list[str], list[str]]:
    """Fehler und Hinweise für eine Sprache."""
    errors: list[str] = []
    warnings: list[str] = []
    catalog = i18n.load_catalog(code)
    if not catalog:
        return [f"{code}: Keine Übersetzungsdatei (assets/translations/{code}.json) oder sie ist leer/unlesbar."], []
    identical = 0
    for key, entry in entries.items():
        if key not in catalog:
            if is_required(code, entry):
                errors.append(f"{code}: fehlt: {key!r}")
            continue
        entry_errors, entry_warnings = check_entry(code, key, entry.text, catalog[key])
        errors += entry_errors
        warnings += entry_warnings
        if catalog[key] == entry.text and meaningful_words(entry.text):
            identical += 1
    for key in catalog:
        if key not in entries:
            errors.append(f"{code}: veralteter Schlüssel (kommt im Quelltext nicht mehr vor): {key!r}")
    total = max(1, len(entries))
    warnings.append(f"{code}: {identical} von {total} Texten gleich dem Deutschen (nur Bedeutsames gezählt)")
    return errors, warnings


def main(argv: list[str]) -> int:
    codes = [a for a in argv if not a.startswith("--")] or [c for c in i18n.LANGUAGES if c != i18n.SOURCE_LANGUAGE]
    entries, _dynamic = collect()
    failed = False
    for code in codes:
        errors, warnings = check_language(code, entries)
        print(f"{code} ({i18n.language_name(code)}): {len(entries)} Texte, {len(errors)} Fehler")
        for line in errors[:60]:
            print("   FEHLER ", line)
        if len(errors) > 60:
            print(f"   … und {len(errors) - 60} weitere Fehler")
        if "--warnings" in argv:
            for line in warnings[:60]:
                print("   hinweis", line)
        failed = failed or bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
