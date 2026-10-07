"""Update des fertigen Programms über die Veröffentlichungen des GitHub-Projekts.

Ablauf:

1. Beim Start lädt das Programm im Hintergrund die kleine Datei
   ``version.json`` der neuesten Veröffentlichung.
2. Nennt sie eine höhere Version als die eigene, fragt das Programm nach.
3. Das Paket (ZIP des Programmordners) wird geladen, anhand seiner Prüfsumme
   (SHA-256) geprüft und entpackt – nach ``<Programmordner>\\_update``, wenn
   der Programmordner beschreibbar ist, sonst in den Benutzerordner.
4. Zwei Wege, je nach Programmordner (siehe ``update_mode``):

   * **Programmordner beschreibbar** („nur für mich“ installiert): Die neue
     Programmdatei wird mit ``--apply-update`` gestartet. Sie wartet, bis das
     alte Programm beendet ist, ersetzt den Programmordner und startet das
     Programm neu. Schlägt das Ersetzen fehl, wird der alte Stand
     wiederhergestellt.
   * **Programmordner nicht beschreibbar** (z. B. für alle Benutzer unter
     ``C:\\Programme``): Die neue Version kommt nach
     ``%LOCALAPPDATA%\\BSTechnik\\PAPDesigner\\update\\<Version>`` und wird
     sofort gestartet. Künftig gibt das installierte Programm beim Start von
     selbst an diese neuere Kopie ab (``redirect_to_user_program``). Lässt
     der Rechner den Start aus dem Benutzerordner nicht zu, läuft das
     installierte Programm einfach weiter und es wird nicht erneut versucht.

Es werden keine fremden Hilfsprogramme (cmd, PowerShell) benötigt, und eigene
Dateien des Benutzers im Programmordner bleiben unberührt: Ersetzt wird nur,
was die neue Version selbst mitbringt.

Dieses Modul enthält nur die Abläufe ohne Oberfläche; die Dialoge stehen in
``app.update_dialogs``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass

from app import config, resources

log = logging.getLogger(__name__)

APPLY_FLAG = config.UPDATE_APPLY_FLAG
STAGING_DIRECTORY = "_update"
USER_UPDATE_DIRECTORY = "update"
COMPLETE_MARKER = "fertig.txt"
BLOCKED_MARKER = "gesperrt.txt"
# Umgebungsvariable: Dieses Programm wurde vom installierten Programm aus dem Benutzerordner gestartet
# (verhindert, dass es von dort noch einmal weiterverweist)
STARTED_FROM_UPDATE_ENV = "BSTECHNIK_PAP_STARTED_FROM_UPDATE"
BACKUP_SUFFIX = ".alt"
MANIFEST_MAX_BYTES = 64 * 1024
PACKAGE_MAX_BYTES = 600 * 1024 * 1024
UNPACKED_MAX_BYTES = 2 * 1024 * 1024 * 1024
CHUNK_SIZE = 256 * 1024


class UpdateError(Exception):
    """Fehler beim Prüfen oder Installieren eines Updates mit verständlicher Meldung."""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.message = message
        self.details = details


class UpdateCancelled(Exception):
    """Der Benutzer hat das Herunterladen abgebrochen."""


@dataclass
class UpdateInfo:
    version: str
    package_url: str
    sha256: str
    size: int = 0
    notes: str = ""
    released: str = ""


# ---------------------------------------------------------------- Versionen
def parse_version(text) -> tuple:
    """„v1.2.3“ → (1, 2, 3). Unlesbares ergibt ein leeres Tupel."""
    match = re.fullmatch(r"\s*[vV]?(\d+(?:\.\d+){0,3})\s*", str(text))
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def is_newer(candidate, current) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    if not new:
        return False
    length = max(len(new), len(old))
    return new + (0,) * (length - len(new)) > old + (0,) * (length - len(old))


# ------------------------------------------------------------------ Quelle
def repository() -> str:
    """Das eingetragene GitHub-Projekt („Besitzer/Name“) oder „“."""
    value = str(config.UPDATE_REPOSITORY or "").strip()
    return value if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) else ""


def releases_page(repo: str | None = None) -> str:
    repo = repo or repository()
    return f"https://github.com/{repo}/releases/latest" if repo else ""


def _open(url: str, timeout: float):
    if not url.lower().startswith("https://"):
        raise UpdateError("Updates werden nur über eine gesicherte Verbindung geladen.")
    request = urllib.request.Request(url, headers={
        "User-Agent": f"{config.EXECUTABLE_NAME}/{config.APP_VERSION}", "Accept": "*/*"})
    return urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context())


def parse_manifest(raw: bytes, repo: str) -> UpdateInfo:
    """Liest ``version.json`` einer Veröffentlichung. Wirft ``UpdateError``."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError("Die Angaben zur neuesten Version sind unlesbar.", str(exc)) from exc
    if not isinstance(data, dict):
        raise UpdateError("Die Angaben zur neuesten Version sind unlesbar.")
    version = str(data.get("version", "")).strip()
    file_name = str(data.get("file") or config.UPDATE_PACKAGE_NAME).strip()
    checksum = str(data.get("sha256", "")).strip().lower()
    tag = str(data.get("tag") or f"v{version}").strip()
    if not parse_version(version) or not re.fullmatch(r"[0-9a-f]{64}", checksum) \
            or not re.fullmatch(r"[A-Za-z0-9_.-]+\.zip", file_name) or not re.fullmatch(r"[A-Za-z0-9_.-]+", tag):
        raise UpdateError("Die Angaben zur neuesten Version sind unvollständig.")
    try:
        size = max(0, int(data.get("size") or 0))
    except (TypeError, ValueError):
        size = 0
    return UpdateInfo(version=version,
                      package_url=f"https://github.com/{repo}/releases/download/{tag}/{file_name}",
                      sha256=checksum, size=size, notes=str(data.get("notes") or "").strip(),
                      released=str(data.get("released") or "").strip())


def fetch_update_info(timeout: float = 8.0, opener=_open) -> UpdateInfo | None:
    """Die neueste veröffentlichte Version; ``None`` ohne eingetragene Update-Quelle.

    Wirft ``UpdateError`` (keine Verbindung, noch keine Veröffentlichung, unlesbare Angaben).
    """
    repo = repository()
    if not repo:
        return None
    url = f"https://github.com/{repo}/releases/latest/download/{config.UPDATE_MANIFEST_NAME}"
    try:
        with opener(url, timeout) as response:
            raw = response.read(MANIFEST_MAX_BYTES + 1)
    except UpdateError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Es wurde noch keine Version veröffentlicht.", str(exc)) from exc
        raise UpdateError("Der Update-Server hat die Anfrage abgelehnt.", str(exc)) from exc
    except Exception as exc:  # keine Verbindung, Zeitüberschreitung, Zertifikat, …
        raise UpdateError("Es konnte keine Verbindung zum Update-Server hergestellt werden.", str(exc)) from exc
    if len(raw) > MANIFEST_MAX_BYTES:
        raise UpdateError("Die Angaben zur neuesten Version sind unlesbar.")
    return parse_manifest(raw, repo)


# ------------------------------------------------------------ Programmordner
def application_directory() -> str | None:
    """Ordner des fertigen Programms; ``None`` beim Start aus dem Quelltext."""
    return os.path.dirname(os.path.abspath(sys.executable)) if resources.is_frozen() else None


def can_write(directory: str) -> bool:
    probe = os.path.join(directory, f".schreibtest-{os.getpid()}")
    try:
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


# ------------------------------------------------ Update im Benutzerordner
# Ist der Programmordner nicht beschreibbar (z. B. für alle Benutzer unter
# C:\Programme installiert), kommt die neue Version in einen Ordner im
# Benutzerprofil: %LOCALAPPDATA%\BSTechnik\PAPDesigner\update\<Version>.
# Beim Start gibt das installierte Programm dann an die neuere Kopie ab.
def user_update_root() -> str:
    from app import errors

    return os.path.join(os.path.dirname(errors.log_directory()), USER_UPDATE_DIRECTORY)


def _is_inside(path: str, folder: str) -> bool:
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # z. B. verschiedene Laufwerke
        return False


def running_from_user_copy() -> bool:
    """Läuft dieses Programm aus dem Benutzerordner (also nicht aus dem installierten Ordner)?"""
    app_dir = application_directory()
    return app_dir is not None and _is_inside(app_dir, user_update_root())


def user_updates_blocked() -> bool:
    """Wurde auf diesem Rechner schon erlebt, dass Programme aus dem Benutzerordner gesperrt sind?"""
    return os.path.isfile(os.path.join(user_update_root(), BLOCKED_MARKER))


def mark_user_updates_blocked() -> None:
    try:
        os.makedirs(user_update_root(), exist_ok=True)
        with open(os.path.join(user_update_root(), BLOCKED_MARKER), "w", encoding="utf-8") as handle:
            handle.write("Der Start von Programmen aus diesem Ordner war nicht möglich.\n")
    except OSError:
        log.warning("Sperre für Updates im Benutzerordner konnte nicht vermerkt werden")


def user_update_root_usable() -> bool:
    root = user_update_root()
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        return False
    return can_write(root)


def update_mode() -> str:
    """Wie sich dieses Programm aktualisieren kann.

    * ``"in_place"``  – der Programmordner wird ersetzt (beschreibbar, z. B. „nur für mich“ installiert)
    * ``"user_copy"`` – die neue Version kommt in den Benutzerordner und wird von dort gestartet
    * ``"blocked"``   – weder noch (kein Zugriff, oder Programme aus dem Benutzerordner sind gesperrt)
    * ``"source"``    – das Programm läuft aus dem Quelltext
    """
    app_dir = application_directory()
    if app_dir is None:
        return "source"
    if not running_from_user_copy() and can_write(app_dir):
        return "in_place"
    if user_updates_blocked() or not user_update_root_usable():
        return "blocked"
    return "user_copy"


def _version_folder_name(version: str) -> str:
    return ".".join(str(part) for part in parse_version(version))


def user_programs() -> list[tuple[tuple, str, str]]:
    """Fertige Programmkopien im Benutzerordner als (Version, Name, Ordner), die neueste zuerst."""
    root = user_update_root()
    try:
        names = os.listdir(root)
    except OSError:
        return []
    found = []
    for name in names:
        version = parse_version(name)
        folder = os.path.join(root, name)
        if version and os.path.isfile(os.path.join(folder, COMPLETE_MARKER)) \
                and os.path.isfile(os.path.join(folder, config.EXECUTABLE_NAME)):
            found.append((version, name, folder))
    return sorted(found, reverse=True)


def newer_user_program() -> tuple[str, str] | None:
    """(Version, Ordner) der neuesten fertigen Kopie – wenn sie neuer ist als dieses Programm."""
    for _version, name, folder in user_programs():
        return (name, folder) if is_newer(name, config.APP_VERSION) else None
    return None


def redirect_to_user_program(arguments: list[str]) -> bool:
    """Startet eine neuere Kopie aus dem Benutzerordner anstelle dieses Programms.

    ``True``: Die Kopie läuft, dieses Programm soll sich sofort beenden. ``False``:
    normal weiterstarten (nichts Neueres da, bereits von der Kopie gestartet, oder der
    Start war nicht möglich – dann wird das vermerkt und nicht erneut versucht).
    """
    if not resources.is_frozen() or os.environ.get(STARTED_FROM_UPDATE_ENV) or user_updates_blocked():
        return False
    found = newer_user_program()
    if found is None:
        return False
    version, folder = found
    try:
        subprocess.Popen([os.path.join(folder, config.EXECUTABLE_NAME), *arguments], cwd=folder, close_fds=True,
                         env=dict(os.environ, **{STARTED_FROM_UPDATE_ENV: version}))
    except OSError as exc:
        log.warning("Neuere Version aus dem Benutzerordner konnte nicht gestartet werden: %s", exc)
        mark_user_updates_blocked()
        return False
    return True


def install_user_program(new_dir: str, version: str) -> str:
    """Legt die entpackte neue Version im Benutzerordner ab. Gibt deren Ordner zurück."""
    name = _version_folder_name(version)
    if not name:
        raise UpdateError("Die Versionsnummer des Updates ist ungültig.")
    target = os.path.join(user_update_root(), name)
    try:
        os.makedirs(user_update_root(), exist_ok=True)
        _remove(target)
        shutil.move(new_dir, target)
        # die Markierung kommt zuletzt: erst damit gilt die Kopie als vollständig
        with open(os.path.join(target, COMPLETE_MARKER), "w", encoding="utf-8") as handle:
            handle.write(name)
    except OSError as exc:
        _remove(target)
        raise UpdateError("Die neue Version konnte nicht abgelegt werden.", str(exc)) from exc
    return target


def _remove_if_unused(path: str) -> None:
    """Entfernt einen Ordner nur, wenn ihn kein laufendes Programm benutzt (Windows lässt ihn dann nicht umbenennen)."""
    aside = path + ".weg"
    try:
        _remove(aside)
        os.rename(path, aside)
    except OSError:
        return
    _remove(aside)


def cleanup_user_programs() -> None:
    """Räumt den Benutzerordner auf: veraltete oder unvollständige Kopien und Zwischenreste.

    Das laufende Programm und neuere Kopien bleiben stehen; ebenso die Sperrmarkierung.
    """
    root = user_update_root()
    running = application_directory()
    try:
        names = os.listdir(root)
    except OSError:
        return
    complete = {name for _version, name, _folder in user_programs()}
    for name in names:
        path = os.path.join(root, name)
        if name == BLOCKED_MARKER or (running is not None and _is_inside(running, path)):
            continue
        if name in complete and is_newer(name, config.APP_VERSION):
            continue  # eine neuere Kopie wartet auf den nächsten Start
        if os.path.isdir(path) and not os.path.islink(path):
            _remove_if_unused(path)
        else:
            _remove(path)


def _remove(path: str) -> None:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        elif os.path.lexists(path):
            os.remove(path)
    except OSError:
        log.warning("Konnte nicht entfernt werden: %s", path)


def cleanup_staging(app_dir: str) -> None:
    """Entfernt Reste eines Updates (Zwischenordner, Sicherungen des alten Stands)."""
    _remove(os.path.join(app_dir, STAGING_DIRECTORY))
    try:
        names = os.listdir(app_dir)
    except OSError:
        return
    for name in names:
        if name.endswith(BACKUP_SUFFIX) and os.path.lexists(os.path.join(app_dir, name[: -len(BACKUP_SUFFIX)])):
            _remove(os.path.join(app_dir, name))


# ------------------------------------------------------- Laden und Entpacken
def extract_package(archive: str, target: str) -> None:
    """Entpackt das Paket nach ``target``. Wirft ``UpdateError`` bei unzulässigem Inhalt."""
    target = os.path.abspath(target)
    try:
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
            if sum(member.file_size for member in members) > UNPACKED_MAX_BYTES:
                raise UpdateError("Das Update-Paket ist unerwartet groß.")
            for member in members:
                destination = os.path.abspath(os.path.join(target, member.filename))
                if os.path.commonpath([target, destination]) != target:
                    raise UpdateError("Das Update-Paket enthält unzulässige Pfade.")
            package.extractall(target)
    except UpdateError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise UpdateError("Das Update-Paket konnte nicht entpackt werden.", str(exc)) from exc


def locate_program(directory: str) -> str:
    """Der Ordner innerhalb des entpackten Pakets, der die Programmdatei enthält."""
    candidates = [directory] + [os.path.join(directory, name) for name in sorted(os.listdir(directory))]
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, config.EXECUTABLE_NAME)):
            return candidate
    raise UpdateError("Das Update-Paket enthält das Programm nicht.")


def download_package(info: UpdateInfo, app_dir: str, progress=None, cancelled=None, opener=_open) -> str:
    """Lädt, prüft und entpackt das Paket. Gibt den Ordner mit der neuen Version zurück.

    ``progress(geladen, gesamt)`` und ``cancelled() -> bool`` sind optional.
    Wirft ``UpdateError`` oder ``UpdateCancelled``.
    """
    staging = os.path.join(app_dir, STAGING_DIRECTORY)
    _remove(staging)
    archive = os.path.join(staging, "paket.zip")
    digest = hashlib.sha256()
    try:
        os.makedirs(staging)
        with opener(info.package_url, 30.0) as response, open(archive, "wb") as handle:
            try:
                total = int(response.headers.get("Content-Length") or info.size or 0)
            except (TypeError, ValueError):
                total = info.size
            done = 0
            while True:
                if cancelled is not None and cancelled():
                    raise UpdateCancelled()
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                done += len(chunk)
                if done > PACKAGE_MAX_BYTES:
                    raise UpdateError("Das Update-Paket ist unerwartet groß.")
                digest.update(chunk)
                handle.write(chunk)
                if progress is not None:
                    progress(done, total)
        if digest.hexdigest() != info.sha256:
            raise UpdateError("Das Update-Paket ist beschädigt (Prüfsumme stimmt nicht). "
                              "Es wurde nichts verändert.")
        unpacked = os.path.join(staging, "neu")
        extract_package(archive, unpacked)
        os.remove(archive)
        return locate_program(unpacked)
    except (UpdateError, UpdateCancelled):
        _remove(staging)
        raise
    except Exception as exc:
        _remove(staging)
        raise UpdateError("Das Update konnte nicht heruntergeladen werden.", str(exc)) from exc


# -------------------------------------------------------------- Installieren
def start_installer(new_dir: str, app_dir: str) -> None:
    """Startet die neue Version im Installationsmodus; danach beendet sich das laufende Programm."""
    executable = os.path.join(new_dir, config.EXECUTABLE_NAME)
    try:
        subprocess.Popen([executable, APPLY_FLAG, app_dir, str(os.getpid())], cwd=new_dir, close_fds=True)
    except OSError as exc:
        raise UpdateError("Die neue Version konnte nicht gestartet werden.", str(exc)) from exc


def launch_program(app_dir: str, wait_pid: int | None = None) -> None:
    """Startet das Programm aus ``app_dir``.

    ``wait_pid``: Der neue Start wartet, bis dieser Prozess beendet ist (das laufende Programm, das sich gerade
    schließt) – sonst übergäbe er seine Arbeit noch an dieses (siehe ``app.single_instance``).
    """
    command = [os.path.join(app_dir, config.EXECUTABLE_NAME)]
    if wait_pid:
        command += [config.WAIT_FOR_FLAG, str(wait_pid)]
    try:
        subprocess.Popen(command, cwd=app_dir, close_fds=True)
    except OSError:
        log.exception("Programm konnte nach dem Update nicht gestartet werden")


def wait_for_exit(pid: int, seconds: float = 60.0) -> bool:
    """Wartet, bis der Prozess beendet ist. ``False`` nach Ablauf der Zeit."""
    from app.autosave import pid_alive

    deadline = time.monotonic() + seconds
    while pid_alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)
    return True


def _rename_with_retry(source: str, target: str, seconds: float = 15.0) -> None:
    """Benennt um; wartet kurz, falls Windows die Datei noch festhält (Virenscanner, Explorer)."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            os.rename(source, target)
            return
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.3)


def apply_update(source_dir: str, app_dir: str, retry_seconds: float = 15.0) -> None:
    """Ersetzt im Programmordner alles, was die neue Version mitbringt.

    Der bisherige Stand wird zuerst beiseitegelegt (``….alt``) und bei einem
    Fehler vollständig zurückgeholt; dann wird ``UpdateError`` geworfen.
    Andere Dateien im Programmordner bleiben unberührt.
    """
    source_dir, app_dir = os.path.abspath(source_dir), os.path.abspath(app_dir)
    try:
        names = sorted(os.listdir(source_dir))
    except OSError as exc:
        raise UpdateError("Die neue Version wurde nicht gefunden.", str(exc)) from exc
    if config.EXECUTABLE_NAME not in names or not os.path.isdir(app_dir):
        raise UpdateError("Die neue Version ist unvollständig. Es wurde nichts verändert.")
    backups: list[tuple[str, str]] = []
    created: list[str] = []
    try:
        for name in names:
            target = os.path.join(app_dir, name)
            if os.path.lexists(target):
                backup = target + BACKUP_SUFFIX
                _remove(backup)
                _rename_with_retry(target, backup, retry_seconds)
                backups.append((target, backup))
            created.append(target)
            source = os.path.join(source_dir, name)
            if os.path.isdir(source):
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
    except Exception as exc:
        # alles zurück auf den alten Stand
        for target in created:
            _remove(target)
        for target, backup in reversed(backups):
            try:
                os.rename(backup, target)
            except OSError:
                log.exception("Alter Stand konnte nicht zurückgeholt werden: %s", target)
        raise UpdateError("Das Update konnte nicht installiert werden (fehlen Schreibrechte im "
                          "Programmordner?). Die bisherige Version bleibt erhalten.", str(exc)) from exc
    for _target, backup in backups:
        _remove(backup)


def write_manifest(path: str, package: str, notes: str = "") -> dict:
    """Erzeugt ``version.json`` für ein fertiges Paket (für ``tools/make_release.py``)."""
    digest = hashlib.sha256()
    with open(package, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    manifest = {
        "version": config.APP_VERSION,
        "tag": f"v{config.APP_VERSION}",
        "released": config.APP_RELEASE_DATE,
        "file": os.path.basename(package),
        "size": os.path.getsize(package),
        "sha256": digest.hexdigest(),
        "notes": notes,
    }
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    return manifest
