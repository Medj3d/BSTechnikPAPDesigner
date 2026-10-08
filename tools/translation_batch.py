"""Übersetzungen portionsweise ergänzen.

    python tools\\translation_batch.py status                       # was fehlt je Sprache?
    python tools\\translation_batch.py next fr --count 100 --out teil.json
                                                                    # die nächsten fehlenden Texte (mit Hinweisen)
    python tools\\translation_batch.py merge fr uebersetzt.json     # {"Schlüssel": "Übersetzung", …} übernehmen
    python tools\\translation_batch.py dump fr --out alles.json     # alle Texte mit vorhandener Übersetzung

``merge`` prüft jede Übersetzung (Platzhalter, ``&``, Zeilenumbrüche, Leerzeichen am Rand, Schrift) und übernimmt
nur die fehlerfreien; der Rest wird mit Grund gemeldet und bleibt offen. Die Übersetzungsdatei
``assets/translations/<Sprache>.json`` bleibt dabei in der Reihenfolge des Quelltexts.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from app import i18n  # noqa: E402
from tools.check_translations import check_entry  # noqa: E402
from tools.extract_strings import collect, is_required  # noqa: E402


def catalog_path(code: str) -> str:
    return os.path.join(i18n.translations_directory(), f"{code}.json")


def read_catalog(code: str) -> dict[str, str]:
    try:
        with open(catalog_path(code), encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def write_catalog(code: str, catalog: dict[str, str], entries: dict) -> None:
    """Schreibt die Datei in der Reihenfolge des Quelltexts (unbekannte Schlüssel ans Ende)."""
    ordered = {key: catalog[key] for key in entries if key in catalog}
    ordered.update({key: value for key, value in catalog.items() if key not in ordered})
    os.makedirs(os.path.dirname(catalog_path(code)), exist_ok=True)
    temporary = catalog_path(code) + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(ordered, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.replace(temporary, catalog_path(code))


def note_for(entry) -> str:
    """Kurzer Hinweis für die Übersetzung: woher der Text kommt und worauf zu achten ist."""
    notes = []
    if entry.kinds == {"tr_code"}:
        notes.append("Text IM ERZEUGTEN PROGRAMM (Pseudocode bzw. Kommentar in Python/Java)")
    elif "tr_code" in entry.kinds:
        notes.append("auch im erzeugten Programm verwendet")
    if entry.ctx:
        notes.append(f"Verwendung: {entry.ctx}")
    if "&" in entry.text.replace("&&", ""):
        notes.append("Menü/Schaltfläche mit Tastenkürzel (&)")
    return "; ".join(notes)


def describe(entry, translation: str | None = None) -> dict:
    data = {"key": entry.key, "de": entry.text}
    note = note_for(entry)
    if note:
        data["note"] = note
    data["where"] = ", ".join(sorted({path for path, _line in entry.locations}))
    if translation is not None:
        data["translation"] = translation
    return data


def _option(argv: list[str], name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def _emit(data, argv: list[str]) -> None:
    target = _option(argv, "--out")
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if target:
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
    else:
        print(text)


def command_status(entries: dict) -> int:
    for code in i18n.LANGUAGES:
        if code == i18n.SOURCE_LANGUAGE:
            continue
        catalog = read_catalog(code)
        needed = [key for key, entry in entries.items() if is_required(code, entry)]
        left = [key for key in needed if key not in catalog]
        print(f"{code}: {len(needed) - len(left)} von {len(needed)} übersetzt, {len(left)} offen")
    return 0


def command_next(code: str, entries: dict, argv: list[str]) -> int:
    catalog = read_catalog(code)
    count = int(_option(argv, "--count", "100"))
    left = [entry for key, entry in entries.items() if key not in catalog and is_required(code, entry)]
    _emit([describe(entry) for entry in left[:count]], argv)
    print(f"{code}: {len(left)} offen, {min(count, len(left))} ausgegeben.", file=sys.stderr)
    return 0


def command_dump(code: str, entries: dict, argv: list[str]) -> int:
    catalog = read_catalog(code)
    _emit([describe(entry, catalog.get(key, "")) for key, entry in entries.items() if is_required(code, entry)], argv)
    return 0


def command_merge(code: str, entries: dict, source: str) -> int:
    with open(source, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if isinstance(data, list):  # auch die Form von „next“/„dump“ mit ausgefülltem "translation"
        data = {item["key"]: item.get("translation", "") for item in data if isinstance(item, dict) and "key" in item}
    if not isinstance(data, dict):
        print("Erwartet wird ein JSON-Objekt {\"Schlüssel\": \"Übersetzung\"}.")
        return 2
    catalog = read_catalog(code)
    accepted = rejected = 0
    for key, target in data.items():
        entry = entries.get(key)
        if entry is None:
            print(f"   ABGELEHNT unbekannter Schlüssel: {key!r}")
            rejected += 1
            continue
        errors, _warnings = check_entry(code, key, entry.text, target)
        if errors:
            for line in errors:
                print("   ABGELEHNT", line)
            rejected += 1
            continue
        catalog[key] = target
        accepted += 1
    write_catalog(code, catalog, entries)
    left = [key for key, entry in entries.items() if key not in catalog and is_required(code, entry)]
    print(f"{code}: {accepted} übernommen, {rejected} abgelehnt, {len(left)} noch offen.")
    return 1 if rejected else 0


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] not in ("status", "next", "merge", "dump"):
        print(__doc__)
        return 2
    entries, _dynamic = collect()
    if argv[0] == "status":
        return command_status(entries)
    code = argv[1]
    if code not in i18n.LANGUAGES or code == i18n.SOURCE_LANGUAGE:
        print(f"Unbekannte Sprache: {code}")
        return 2
    if argv[0] == "next":
        return command_next(code, entries, argv)
    if argv[0] == "dump":
        return command_dump(code, entries, argv)
    return command_merge(code, entries, argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
