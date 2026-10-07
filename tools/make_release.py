"""Macht aus dem gebauten Programm ein Update und lädt es bei GitHub hoch.

Voraussetzung: ``build_exe.bat`` ist gelaufen (``dist\\BSTechnikPAPDesigner``),
die Versionsnummer in ``app/config.py`` wurde erhöht und dort ist unter
``UPDATE_REPOSITORY`` das GitHub-Projekt eingetragen.

Erzeugt in ``dist``:

* ``BSTechnikPAPDesigner.zip`` – der Programmordner als Paket
* ``version.json``             – Version und Prüfsumme; daran erkennt das
  Programm auf anderen Rechnern, dass es ein Update gibt

und veröffentlicht beides mit der GitHub-Befehlszeile (``gh``) als
Version ``v<Versionsnummer>``. Aufruf über ``release.bat`` oder::

    python tools\\make_release.py ["Was ist neu"]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from app import config, updater  # noqa: E402

DIST = os.path.join(ROOT, "dist")
PROGRAM = os.path.join(DIST, os.path.splitext(config.EXECUTABLE_NAME)[0])


def build_package() -> tuple[str, str]:
    """Packt den Programmordner und schreibt ``version.json``. Gibt beide Pfade zurück."""
    if not os.path.isfile(os.path.join(PROGRAM, config.EXECUTABLE_NAME)):
        raise SystemExit(f"Das Programm wurde noch nicht gebaut ({PROGRAM}). Bitte zuerst build_exe.bat ausführen.")
    package = os.path.join(DIST, config.UPDATE_PACKAGE_NAME)
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for folder, _dirs, files in os.walk(PROGRAM):
            for name in files:
                path = os.path.join(folder, name)
                archive.write(path, os.path.relpath(path, PROGRAM))
    notes = sys.argv[1] if len(sys.argv) > 1 else ""
    manifest = os.path.join(DIST, config.UPDATE_MANIFEST_NAME)
    data = updater.write_manifest(manifest, package, notes)
    print(f"Paket:   {package} ({data['size'] // (1024 * 1024)} MB)")
    print(f"Angaben: {manifest} (Version {data['version']}, {data['released']})")
    return package, manifest


def publish(package: str, manifest: str) -> int:
    repo = updater.repository()
    tag = f"v{config.APP_VERSION}"
    if not repo:
        print("\nIn app/config.py ist unter UPDATE_REPOSITORY noch kein GitHub-Projekt eingetragen.")
        print("Die beiden Dateien wurden erzeugt, aber nicht hochgeladen.")
        return 1
    if shutil.which("gh") is None:
        print("\nDie GitHub-Befehlszeile (gh) ist nicht installiert. Bitte die beiden Dateien von Hand als")
        print(f"Veröffentlichung „{tag}“ hochladen: https://github.com/{repo}/releases/new")
        return 1
    notes = sys.argv[1] if len(sys.argv) > 1 else f"Version {config.APP_VERSION} ({config.APP_RELEASE_DATE})"
    command = ["gh", "release", "create", tag, package, manifest, "--repo", repo,
               "--title", f"Version {config.APP_VERSION}", "--notes", notes, "--latest"]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"\nDas Hochladen ist fehlgeschlagen. Gibt es die Version {tag} schon? Dann zuerst die")
        print("Versionsnummer in app/config.py erhöhen. Angemeldet? Sonst einmal „gh auth login“ ausführen.")
        return result.returncode
    print(f"\nVeröffentlicht: https://github.com/{repo}/releases/tag/{tag}")
    print("Programme auf anderen Rechnern bieten das Update beim nächsten Start an.")
    return 0


if __name__ == "__main__":
    sys.exit(publish(*build_package()))
