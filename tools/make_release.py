"""Macht aus dem gebauten Programm eine Veröffentlichung und lädt sie bei GitHub hoch.

Voraussetzung: ``build_exe.bat`` ist gelaufen (``dist\\BSTechnikPAPDesigner``),
die Versionsnummer in ``app/config.py`` wurde erhöht und dort ist unter
``UPDATE_REPOSITORY`` das GitHub-Projekt eingetragen.

Erzeugt in ``dist``:

* ``BSTechnikPAPDesigner-Setup.exe`` – die Setup-Datei zum Weitergeben
  (braucht Inno Setup 6 auf diesem Rechner; fehlt es, wird sie ausgelassen)
* ``BSTechnikPAPDesigner.zip``       – der Programmordner als Paket; daraus
  aktualisieren sich bereits installierte Programme
* ``version.json``                   – Version und Prüfsumme; daran erkennt
  das Programm auf anderen Rechnern, dass es ein Update gibt

und veröffentlicht alles mit der GitHub-Befehlszeile (``gh``) als Version
``v<Versionsnummer>``. Aufruf über ``release.bat`` oder::

    python tools\\make_release.py ["Was ist neu"] [--ohne-upload]
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
INSTALLER_SCRIPT = os.path.join(ROOT, "installer", "BSTechnikPAPDesigner.iss")
NO_UPLOAD_FLAG = "--ohne-upload"


def release_notes() -> str:
    """Der Text „Was ist neu“ von der Befehlszeile (oder leer)."""
    return next((arg for arg in sys.argv[1:] if not arg.startswith("--")), "")


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
    manifest = os.path.join(DIST, config.UPDATE_MANIFEST_NAME)
    data = updater.write_manifest(manifest, package, release_notes())
    print(f"Paket:   {package} ({data['size'] // (1024 * 1024)} MB)")
    print(f"Angaben: {manifest} (Version {data['version']}, {data['released']})")
    return package, manifest


def find_inno_setup() -> str | None:
    """Der Übersetzer von Inno Setup (ISCC.exe) oder ``None``, wenn es nicht installiert ist."""
    candidates = [shutil.which("ISCC")]
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            candidates.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def build_setup() -> str | None:
    """Erzeugt die Setup-Datei. ``None``, wenn Inno Setup fehlt (dann geht es ohne weiter)."""
    compiler = find_inno_setup()
    if compiler is None:
        print("\nInno Setup 6 ist nicht installiert – die Setup-Datei wird ausgelassen.")
        print("Download: https://jrsoftware.org/isdl.php")
        return None
    command = [compiler, "/Qp", f"/DAppVersion={config.APP_VERSION}", f"/DSourceDir={PROGRAM}",
               f"/DOutputDir={DIST}", INSTALLER_SCRIPT]
    if subprocess.run(command, cwd=ROOT).returncode != 0:
        raise SystemExit("Die Setup-Datei konnte nicht erstellt werden (Meldung von Inno Setup siehe oben).")
    setup = os.path.join(DIST, config.SETUP_FILE_NAME)
    print(f"Setup:   {setup} ({os.path.getsize(setup) // (1024 * 1024)} MB)")
    return setup


def publish(package: str, manifest: str, setup: str | None = None) -> int:
    repo = updater.repository()
    tag = f"v{config.APP_VERSION}"
    if not repo:
        print("\nIn app/config.py ist unter UPDATE_REPOSITORY noch kein GitHub-Projekt eingetragen.")
        print("Die Dateien wurden erzeugt, aber nicht hochgeladen.")
        return 1
    if shutil.which("gh") is None:
        print("\nDie GitHub-Befehlszeile (gh) ist nicht installiert. Bitte die Dateien von Hand als")
        print(f"Veröffentlichung „{tag}“ hochladen: https://github.com/{repo}/releases/new")
        return 1
    notes = release_notes() or f"Version {config.APP_VERSION} ({config.APP_RELEASE_DATE})"
    files = [package, manifest] + ([setup] if setup else [])
    command = ["gh", "release", "create", tag, *files, "--repo", repo,
               "--title", f"Version {config.APP_VERSION}", "--notes", notes, "--latest"]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"\nDas Hochladen ist fehlgeschlagen. Gibt es die Version {tag} schon? Dann zuerst die")
        print("Versionsnummer in app/config.py erhöhen. Angemeldet? Sonst einmal „gh auth login“ ausführen.")
        return result.returncode
    print(f"\nVeröffentlicht: https://github.com/{repo}/releases/tag/{tag}")
    if setup:
        print(f"Zum Weitergeben: https://github.com/{repo}/releases/latest/download/{config.SETUP_FILE_NAME}")
    print("Bereits installierte Programme bieten das Update beim nächsten Start an.")
    return 0


def main() -> int:
    package, manifest = build_package()
    setup = build_setup()
    if NO_UPLOAD_FLAG in sys.argv[1:]:
        print("\nNicht hochgeladen (--ohne-upload).")
        return 0
    return publish(package, manifest, setup)


if __name__ == "__main__":
    sys.exit(main())
