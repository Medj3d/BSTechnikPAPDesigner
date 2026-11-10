"""Gleichheitstest Windows ↔ Linux: Fingerabdruck jeder Datei auf einem System, dann Vergleich.

Für jede Datei wird festgehalten, was das Programm daraus macht:

* ``geoeffnet``   – Bausteine und Verbindungen jeder Seite nach dem Öffnen (ungerundet), Hinweise beim Laden
* ``gespeichert`` – die gespeicherte ``.pap``-Datei (Zeitstempel fest, zufällige Kennungen durchnummeriert)
* ``angeordnet``  – Lage aller Bausteine und Linien nach „Automatisch anordnen“
* ``schreibtischtest`` – Ausgaben mit festen Eingaben (Korpus-Pläne: die Eingaben des Generators)
* ``pruefung``    – Befunde der Prüfung (Schwere, Text, betroffene Bausteine)

    python tools/plattform_vergleich.py erfassen windows.json Ordner_oder_Dateien … [--korpus 60]
    python tools/plattform_vergleich.py vergleichen windows.json linux.json
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

FIXED_TIME = "2026-01-01T00:00:00"
ID_PATTERN = re.compile(r"\b[0-9a-f]{32}\b")
DEFAULT_INPUTS = ["3", "1", "4", "1", "5", "9", "2", "6"]
STEP_LIMIT = 400_000  # wie tests/test_papdesigner_corpus.py


def _ids(document) -> dict[str, str]:
    """Zufällige Kennungen → „e1“, „c1“ … in der Reihenfolge der Seiten."""
    names: dict[str, str] = {}
    for page in document.pages:
        for data in page.scene.element_data():
            names.setdefault(data.id, f"e{len(names) + 1}")
        for data in page.scene.connection_data():
            names.setdefault(data.id, f"c{len(names) + 1}")
    return names


def _number(value):
    return round(value, 6) if isinstance(value, float) else value


def _deep(value, ids):
    if isinstance(value, str):
        return ids.get(value, value)
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, (list, tuple)):
        return [_deep(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: _deep(v, ids) for k, v in sorted(value.items())}
    if hasattr(value, "__dataclass_fields__"):
        return {k: _deep(getattr(value, k), ids) for k in value.__dataclass_fields__}
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


def _pages(document, ids):
    return [{"seite": page.display_name,
             "bausteine": _deep(page.scene.element_data(), ids),
             "verbindungen": _deep(page.scene.connection_data(), ids)} for page in document.pages]


def _desk_check(document, inputs):
    from app.simulation import engine
    from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator

    engine.MAX_STEPS = STEP_LIMIT
    simulator = Simulator(document.flow_graph())
    values = list(inputs) or DEFAULT_INPUTS
    asked = 0
    for _ in range(STEP_LIMIT):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            value = values[asked % len(values)]
            asked += 1
            simulator.provide_input(" ".join([value] * max(1, len(result.variables))))
        elif result.needs == NEEDS_DECISION:
            # Korpus-Pläne wie im Korpus-Test immer „ja“, sonst abwechselnd
            simulator.provide_decision(True if inputs else asked % 2 == 0)
            asked += 1
        if simulator.finished:
            break
    return {"ausgaben": [" ".join(str(line).split()) for line in simulator.outputs],
            "fertig": bool(simulator.finished), "schritte": simulator.steps}


def fingerprint(path: str, inputs=()) -> dict:
    from app import document as document_module
    from app.diagnostics.checks import run_checks
    from app.document import DiagramDocument
    from app.layout.auto_layout import apply_layout, plan_auto_layout

    document_module.now_iso = lambda: FIXED_TIME
    result: dict = {}
    document = DiagramDocument.open_file(path)
    ids = _ids(document)
    result["geoeffnet"] = {"seiten": _pages(document, ids), "hinweise": [str(w) for w in document.load_warnings],
                           "eigenes_format": bool(document.native_file)}
    result["pruefung"] = [[i.severity, i.message, _deep(i.element_ids, ids), _deep(i.connection_ids, ids)]
                          for i in run_checks(document)]
    result["schreibtischtest"] = _desk_check(document, inputs)
    with tempfile.TemporaryDirectory() as folder:
        target = os.path.join(folder, "gespeichert.pap")
        document.meta.created = document.meta.created or FIXED_TIME
        document.save(target)
        with open(target, "rb") as handle:
            text = handle.read().decode("utf-8")
    order: dict[str, str] = {}
    text = ID_PATTERN.sub(lambda m: order.setdefault(m.group(0), f"id{len(order) + 1:04d}"), text)
    result["gespeichert"] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}
    for page in document.pages:
        apply_layout(page.scene, plan_auto_layout(page.scene))
    result["angeordnet"] = _pages(document, ids)
    result["angeordnet_schreibtischtest"] = _desk_check(document, inputs)
    for page in document.pages:
        page.scene.clear_diagram()
    return result


def collect(output: str, patterns: list[str], corpus: int) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841 - Szenen brauchen eine Anwendung
    from app import config, i18n

    config.AUTO_SAVE_DEFAULT = False
    i18n.set_language("de")
    results = {}
    files = []
    for pattern in patterns:
        files += sorted(glob.glob(os.path.join(pattern, "*.pap"))) if os.path.isdir(pattern) else sorted(glob.glob(pattern))
    for path in files:
        key = f"{os.path.basename(os.path.dirname(os.path.abspath(path)))}/{os.path.basename(path)}"
        try:
            results[key] = fingerprint(path)
        except Exception as exc:  # festhalten, nicht abbrechen
            results[key] = {"fehler": repr(exc)}
    if corpus:
        from tests.papdesigner_corpus import generate

        with tempfile.TemporaryDirectory() as folder:
            for seed in range(corpus):
                project = generate(seed)
                path = os.path.join(folder, f"korpus_{seed:03d}.pap")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(project.to_xml())
                try:
                    results[f"korpus/{seed:03d}"] = fingerprint(path, project.inputs)
                    results[f"korpus/{seed:03d}"]["erwartet"] = project.expected_outputs
                except Exception as exc:
                    results[f"korpus/{seed:03d}"] = {"fehler": repr(exc)}
    with open(output, "w", encoding="utf-8") as handle:
        json.dump({"system": sys.platform, "dateien": results}, handle, ensure_ascii=False, indent=1)
    print(f"{len(results)} Dateien erfasst → {output}")


def _first_difference(a, b, where=""):
    if type(a) is not type(b):
        return where, a, b
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                return _first_difference(a.get(key), b.get(key), f"{where}.{key}")
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{where}[Länge {len(a)}≠{len(b)}]", None, None
        for index, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _first_difference(x, y, f"{where}[{index}]")
    elif a != b:
        return where, a, b
    return where, a, b


def compare(first: str, second: str) -> int:
    with open(first, encoding="utf-8") as handle:
        a = json.load(handle)
    with open(second, encoding="utf-8") as handle:
        b = json.load(handle)
    aspects = ["geoeffnet", "gespeichert", "pruefung", "schreibtischtest", "angeordnet", "angeordnet_schreibtischtest"]
    counts = {aspect: 0 for aspect in aspects}
    differences = []
    files = sorted(set(a["dateien"]) | set(b["dateien"]))
    for name in files:
        x, y = a["dateien"].get(name), b["dateien"].get(name)
        if x is None or y is None or "fehler" in x or "fehler" in y:
            differences.append((name, "fehlt/Fehler", str(x and x.get("fehler")), str(y and y.get("fehler"))))
            continue
        for aspect in aspects:
            if x.get(aspect) == y.get(aspect):
                counts[aspect] += 1
            else:
                where, left, right = _first_difference(x.get(aspect), y.get(aspect), aspect)
                differences.append((name, where, str(left)[:160], str(right)[:160]))
        if "erwartet" in x and x["schreibtischtest"]["ausgaben"] != x["erwartet"]:
            differences.append((name, f"{a['system']}: Schreibtischtest ≠ erwartet", "", ""))
        if "erwartet" in y and y["schreibtischtest"]["ausgaben"] != y["erwartet"]:
            differences.append((name, f"{b['system']}: Schreibtischtest ≠ erwartet", "", ""))
    print(f"{a['system']} ↔ {b['system']}: {len(files)} Dateien")
    for aspect in aspects:
        print(f"  {aspect:30s} gleich bei {counts[aspect]} von {len(files)}")
    for name, where, left, right in differences:
        print(f"ABWEICHUNG {name} {where}\n    {left}\n    {right}")
    return 1 if differences else 0


def main(arguments: list[str]) -> int:
    if len(arguments) >= 3 and arguments[0] == "vergleichen":
        return compare(arguments[1], arguments[2])
    if len(arguments) >= 2 and arguments[0] == "erfassen":
        corpus = 0
        if "--korpus" in arguments:
            index = arguments.index("--korpus")
            corpus = int(arguments[index + 1])
            arguments = arguments[:index] + arguments[index + 2:]
        collect(arguments[1], arguments[2:], corpus)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
