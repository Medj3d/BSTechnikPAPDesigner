"""Gegenprobe im Original-PapDesigner: Öffnet er diese Dateien?

Startet für jede Datei den installierten PapDesigner 2.2 mit der Datei, liest Fenstertitel und Meldungen aus
und beendet ihn wieder (``tools/papdesigner_gegenprobe.ps1``; es werden keine Tasten oder Klicks gesendet).
Lehnt der PapDesigner eine Datei ab, zeigt er statt ihrer nur sein Tutorial – das erkennt das Werkzeug am
Fenstertitel. Ein laufender PapDesigner wird dabei beendet.

    python tools\\papdesigner_gegenprobe.py Datei.pap [weitere.pap …]
    python tools\\papdesigner_gegenprobe.py --unser examples\\*.pap   # erst mit diesem Programm neu speichern

Mit ``--unser`` werden die Dateien zuvor mit diesem Programm geöffnet und neu gespeichert (in einen
Temp-Ordner) – so prüft man, ob das Original Dateien aus diesem Programm annimmt.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papdesigner_gegenprobe.ps1")
ORIGINAL = r"C:\Program Files (x86)\PapDesigner\PapDesigner.exe"


def check(paths: list[str], folder: str, wait: int = 8) -> dict[str, tuple[bool, list[str]]]:
    """{Datei: (geöffnet?, Fenstertitel)}."""
    listing = os.path.join(folder, "liste.txt")
    with open(listing, "w", encoding="utf-8") as handle:
        handle.write("\n".join(os.path.abspath(p) for p in paths) + "\n")
    out = os.path.join(folder, "ergebnis")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT, "-ListFile", listing,
                    "-OutDir", out, "-WaitSeconds", str(wait)], check=True, capture_output=True)
    with open(os.path.join(out, "bericht.json"), encoding="utf-8-sig") as handle:
        report = json.load(handle)
    report = [report] if isinstance(report, dict) else report
    result = {}
    for path, entry in zip(paths, report):
        titles = [w["title"] for w in (entry.get("windows") or [])]
        result[path] = (any(t.endswith(os.path.basename(path)) for t in titles), titles)
    return result


def main(arguments: list[str]) -> int:
    if not os.path.isfile(ORIGINAL):
        print(f"Der PapDesigner ist nicht installiert ({ORIGINAL}).")
        return 2
    resave = "--unser" in arguments
    paths = [p for pattern in arguments if pattern != "--unser" for p in sorted(glob.glob(pattern))]
    if not paths:
        print(__doc__)
        return 2
    folder = tempfile.mkdtemp(prefix="pap-gegenprobe-")
    if resave:
        from app.fileformat.serializer import load_diagram, save_diagram

        copies = []
        for path in paths:
            copy = os.path.join(folder, os.path.basename(path))
            save_diagram(load_diagram(path).diagram, copy)
            copies.append(copy)
        paths = copies
    result = check(paths, folder)
    refused = [path for path, (opened, _titles) in result.items() if not opened]
    for path in refused:
        print("abgelehnt:", path)
    print(f"Der PapDesigner öffnet {len(paths) - len(refused)} von {len(paths)} Dateien. (Bilder: {folder})")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
