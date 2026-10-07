"""Liest alle übersetzbaren Texte aus dem Quelltext.

Gesucht werden die Aufrufe ``tr("…")``, ``tr_code("…")`` und ``N_("…")`` (auch als ``i18n.tr`` usw.), deren erstes
Argument ein Textliteral ist. Der Text ist der Schlüssel der Übersetzung; ``ctx="…"`` macht daraus den Schlüssel
``"<ctx>::<Text>"`` (gleiches deutsches Wort, andere Bedeutung).

    python tools\\extract_strings.py                 # Zusammenfassung
    python tools\\extract_strings.py --json out.json  # alle Schlüssel mit Platzhaltern und Fundstellen
    python tools\\extract_strings.py --missing en     # was in assets/translations/en.json noch fehlt

``tr(variable)`` lässt sich nicht auslesen; solche Texte müssen dort, wo sie entstehen, mit ``N_("…")`` markiert
sein. Die Aufrufe werden als „dynamisch“ gemeldet, damit man sie prüfen kann.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass, field

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from app import i18n  # noqa: E402

FUNCTIONS = {"tr", "tr_code", "N_"}
SKIPPED_FOLDERS = {"__pycache__"}


@dataclass
class Entry:
    key: str
    text: str
    ctx: str | None
    kinds: set = field(default_factory=set)
    locations: list = field(default_factory=list)

    @property
    def placeholders(self) -> list[str]:
        return i18n.placeholders(self.text)


@dataclass
class Dynamic:
    path: str
    line: int
    function: str
    source: str


def _function_name(node: ast.Call) -> str | None:
    function = node.func
    if isinstance(function, ast.Name) and function.id in FUNCTIONS:
        return function.id
    if isinstance(function, ast.Attribute) and function.attr in FUNCTIONS \
            and isinstance(function.value, ast.Name) and function.value.id == "i18n":
        return function.attr
    return None


def source_files(root: str = ROOT) -> list[str]:
    files = [os.path.join(root, "main.py")]
    for folder, directories, names in os.walk(os.path.join(root, "app")):
        directories[:] = [d for d in directories if d not in SKIPPED_FOLDERS]
        files += [os.path.join(folder, name) for name in sorted(names) if name.endswith(".py")]
    # app/i18n.py ist die Übersetzungsfunktion selbst (ihre Aufrufe sind Beispiele und Weiterreichungen)
    files = [path for path in files if os.path.relpath(path, root).replace("\\", "/") != "app/i18n.py"]
    return [path for path in sorted(files) if os.path.isfile(path)]


def collect(root: str = ROOT) -> tuple[dict[str, Entry], list[Dynamic]]:
    """Alle Texte (Schlüssel → Eintrag) und die Aufrufe mit nicht auslesbarem Text."""
    entries: dict[str, Entry] = {}
    dynamic: list[Dynamic] = []
    for path in source_files(root):
        relative = os.path.relpath(path, root).replace("\\", "/")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = _function_name(node)
            if function is None:
                continue
            first = node.args[0] if node.args else None
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                if function != "N_":
                    dynamic.append(Dynamic(relative, node.lineno, function, ast.get_source_segment(source, node) or ""))
                continue
            ctx = None
            for keyword in node.keywords:
                if keyword.arg == "ctx":
                    if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        ctx = keyword.value.value
                    else:
                        dynamic.append(Dynamic(relative, node.lineno, function, "ctx ist kein Textliteral"))
            text = first.value
            key = f"{ctx}{i18n.CONTEXT_SEPARATOR}{text}" if ctx else text
            entry = entries.setdefault(key, Entry(key, text, ctx))
            entry.kinds.add(function)
            entry.locations.append((relative, node.lineno))
    return entries, dynamic


def missing(code: str, entries: dict[str, Entry]) -> list[str]:
    catalog = i18n.load_catalog(code)
    return [key for key in entries if key not in catalog]


def main(argv: list[str]) -> int:
    entries, dynamic = collect()
    if "--json" in argv:
        target = argv[argv.index("--json") + 1]
        data = [{"key": e.key, "text": e.text, "ctx": e.ctx, "placeholders": e.placeholders,
                 "locations": [f"{p}:{n}" for p, n in e.locations]} for e in entries.values()]
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        print(f"{len(entries)} Texte nach {target} geschrieben.")
        return 0
    if "--missing" in argv:
        code = argv[argv.index("--missing") + 1]
        left = missing(code, entries)
        print(f"{code}: {len(left)} von {len(entries)} Texten fehlen.")
        for key in left:
            print("  ", repr(key))
        return 1 if left else 0
    placeholders = sum(1 for e in entries.values() if e.placeholders)
    print(f"{len(entries)} verschiedene Texte, davon {placeholders} mit Platzhaltern; "
          f"{len(dynamic)} Aufrufe mit nicht auslesbarem Text.")
    for item in dynamic:
        print(f"  dynamisch: {item.path}:{item.line}  {item.source}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
