"""Automatisches Sichern und Wiederherstellen nach einem Absturz.

Ungespeicherte Änderungen offener Projekte werden regelmäßig als
Sicherungskopie in ``%LOCALAPPDATA%\\BSTechnik\\PAPDesigner\\autosave``
abgelegt. Beim normalen Beenden werden die Kopien gelöscht. Findet das
Programm beim Start Kopien einer Sitzung, die nicht mehr läuft (Absturz,
Stromausfall), bietet es die Wiederherstellung an.

Pro laufender Sitzung gibt es eine Sitzungsdatei mit Prozess-ID und
„Herzschlag“. Kopien laufender Sitzungen (z. B. ein zweites geöffnetes
Programmfenster) werden nie angeboten.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
import weakref
from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer

from app import config, errors
from app.fileformat.serializer import save_diagram
from app.model.diagram import now_iso

log = logging.getLogger(__name__)

BACKUP_SUFFIX = config.FILE_EXTENSION
META_SUFFIX = ".json"
SESSION_SUFFIX = ".session"
STALE_AFTER = timedelta(days=1)


def default_directory() -> str:
    return os.path.join(os.path.dirname(errors.log_directory()), "autosave")


def pid_alive(pid: int) -> bool:
    """Läuft der Prozess noch? (Unter Windows niemals os.kill verwenden!)"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # nur unter Unix: Signal 0 prüft lediglich die Existenz
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass
class RecoveryEntry:
    backup_path: str
    meta_path: str
    display_name: str
    original_path: str | None
    saved_at: str
    session_id: str


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: str, data: dict) -> None:
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    os.replace(temp, path)


def _remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        log.warning("Sicherungsdatei konnte nicht gelöscht werden: %s", path)


class AutosaveManager(QObject):
    def __init__(self, directory: str | None = None, interval_ms: int = 60000, parent=None,
                 pid_alive_func=pid_alive):
        super().__init__(parent)
        self.directory = directory or default_directory()
        self.session_id = uuid.uuid4().hex[:12]
        self._pid_alive = pid_alive_func
        self._documents: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._started = now_iso()
        self._active = True
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError:
            log.warning("Autosave-Ordner nicht verfügbar: %s", self.directory)
            self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(max(1000, int(interval_ms)))
        self._timer.timeout.connect(self._tick)
        if self._active:
            self._write_session()
            self._timer.start()

    # ------------------------------------------------------------ Pfade
    def _session_path(self, session_id: str | None = None) -> str:
        return os.path.join(self.directory, (session_id or self.session_id) + SESSION_SUFFIX)

    def _backup_path(self, document) -> str:
        info = self._documents.get(document)
        doc_id = info["id"] if info else uuid.uuid4().hex[:12]
        return os.path.join(self.directory, f"{self.session_id}_{doc_id}{BACKUP_SUFFIX}")

    # ------------------------------------------------------------ Dokumente
    def register(self, document) -> None:
        if document not in self._documents:
            self._documents[document] = {"id": uuid.uuid4().hex[:12], "index": None}

    def unregister(self, document) -> None:
        if document in self._documents:
            self._delete_backup(document)
            del self._documents[document]

    def document_saved(self, document) -> None:
        if document in self._documents:
            self._delete_backup(document)
            self._documents[document]["index"] = None

    def _delete_backup(self, document) -> None:
        path = self._backup_path(document)
        _remove(path)
        _remove(path + META_SUFFIX)

    def save_now(self) -> int:
        """Sichert alle geänderten Projekte. Gibt die Anzahl geschriebener Kopien zurück."""
        if not self._active:
            return 0
        written = 0
        for document, info in list(self._documents.items()):
            try:
                if not document.is_modified:
                    if info["index"] is not None:
                        self._delete_backup(document)
                        info["index"] = None
                    continue
                index = document.undo_stack.index()
                path = self._backup_path(document)
                if info["index"] == index and os.path.exists(path):
                    continue  # seit der letzten Sicherung unverändert
                save_diagram(document.to_diagram(), path)
                _write_json(path + META_SUFFIX, {
                    "original_path": document.file_path,
                    "display_name": document.display_name,
                    "saved_at": now_iso(),
                    "session_id": self.session_id,
                    "pid": os.getpid(),
                })
                info["index"] = index
                written += 1
            except Exception:  # Autosave darf nie stören
                log.exception("Automatisches Sichern fehlgeschlagen")
        return written

    def _write_session(self) -> None:
        try:
            _write_json(self._session_path(), {"pid": os.getpid(), "started": self._started,
                                               "heartbeat": now_iso()})
        except OSError:
            log.warning("Sitzungsdatei konnte nicht geschrieben werden")

    def _tick(self) -> None:
        try:
            self._write_session()
            self.save_now()
        except Exception:
            log.exception("Fehler beim automatischen Sichern")

    def shutdown(self) -> None:
        """Normales Beenden: eigene Sicherungen und Sitzungsdatei entfernen."""
        self._timer.stop()
        for document in list(self._documents.keys()):
            self._delete_backup(document)
        self._documents.clear()
        _remove(self._session_path())

    # ------------------------------------------------------ Wiederherstellen
    def _session_alive(self, session_id: str) -> bool:
        if session_id == self.session_id:
            return True
        data = _read_json(self._session_path(session_id))
        if not data:
            return False
        try:
            heartbeat = datetime.fromisoformat(str(data.get("heartbeat")))
            if datetime.now(heartbeat.tzinfo) - heartbeat > STALE_AFTER:
                return False
        except (TypeError, ValueError):
            return False
        pid = data.get("pid")
        return self._pid_alive(pid) if isinstance(pid, int) else False

    def find_orphans(self) -> list[RecoveryEntry]:
        """Sicherungen aus Sitzungen, die nicht mehr laufen."""
        if not os.path.isdir(self.directory):
            return []
        self._cleanup_dead_sessions()
        entries = []
        alive_cache: dict[str, bool] = {}
        for name in sorted(os.listdir(self.directory)):
            if not name.endswith(BACKUP_SUFFIX) or "_" not in name:
                continue
            session_id = name.split("_", 1)[0]
            if session_id not in alive_cache:
                alive_cache[session_id] = self._session_alive(session_id)
            if alive_cache[session_id]:
                continue
            backup = os.path.join(self.directory, name)
            meta = _read_json(backup + META_SUFFIX)
            original = meta.get("original_path") if isinstance(meta.get("original_path"), str) else None
            entries.append(RecoveryEntry(
                backup_path=backup,
                meta_path=backup + META_SUFFIX,
                display_name=str(meta.get("display_name") or os.path.splitext(name)[0]),
                original_path=original,
                saved_at=str(meta.get("saved_at") or ""),
                session_id=session_id,
            ))
        return entries

    def restore(self, entry: RecoveryEntry):
        """Lädt eine Sicherung als geändertes Projekt. Wirft ``ProjectFileError``."""
        from app.document import DiagramDocument

        document = DiagramDocument.open_file(entry.backup_path)
        document.file_path = entry.original_path or None
        if entry.original_path is None:
            document.meta.name = entry.display_name
        # als ungespeichert markieren, damit der Benutzer bewusst speichert
        document.undo_stack.resetClean()
        document.title_changed.emit()
        self.discard(entry)
        return document

    def discard(self, entry: RecoveryEntry) -> None:
        _remove(entry.backup_path)
        _remove(entry.meta_path)
        self._cleanup_dead_sessions()

    def _cleanup_dead_sessions(self) -> None:
        """Sitzungsdateien beendeter Sitzungen ohne verbliebene Sicherungen löschen."""
        try:
            names = os.listdir(self.directory)
        except OSError:
            return
        backups = {name.split("_", 1)[0] for name in names if name.endswith(BACKUP_SUFFIX) and "_" in name}
        for name in names:
            if name.endswith(SESSION_SUFFIX):
                session_id = name[: -len(SESSION_SUFFIX)]
                if session_id not in backups and not self._session_alive(session_id):
                    _remove(os.path.join(self.directory, name))
