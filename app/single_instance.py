"""Ein Programmfenster für alles: Weitere Programmstarts übergeben ihre Dateien an das laufende Programm.

Öffnet man im Explorer mehrere ``.pap``-Dateien oder doppelklickt sie nacheinander, startet Windows das Programm
jedes Mal neu. Statt vieler Fenster übernimmt das schon laufende Programm die Dateien und öffnet sie – wie im
Programm selbst – als Reiter im selben Fenster.

Ablauf (``acquire``):

1. Der neue Programmstart fragt über eine lokale Pipe (``QLocalServer``, nur für den eigenen Benutzer und die
   eigene Windows-Sitzung): Läuft schon ein Programm? Dann schickt er die Dateien (als absolute Pfade), wartet auf
   die Bestätigung und beendet sich. Das laufende Programm öffnet die Dateien und holt sein Fenster nach vorn.
2. Läuft keins, wird dieses Programm das erste und lauscht auf weitere Starts. Dateien, die schon während des
   Starts (Ladebildschirm) eintreffen, werden gemerkt und geöffnet, sobald das Fenster bereit ist.
3. Wer das „erste“ Programm ist, entscheidet eine Sperre (benannter Windows-Mutex, sonst eine Sperrdatei): Sie
   lässt sich nur einmal erwerben und verschwindet mit dem Programm, auch nach einem Absturz. Qt allein reicht
   dafür nicht – mehrere Prozesse können dieselbe Pipe anlegen. Starten mehrere Programme gleichzeitig, gewinnt
   eines die Sperre; die anderen versuchen es kurz darauf als Absender noch einmal.

Läuft ein Programm, antwortet aber nicht (hängt), startet der neue Programmstart nach einer Wartezeit als
eigenes, unabhängiges Fenster – niemand wartet ewig. Mit ``--neues-fenster`` lässt sich das Weiterreichen
ausdrücklich abschalten.

Nachrichten: 4 Byte Länge (Big Endian) + UTF-8-JSON. Es werden nur Dateipfade übertragen; das Programm öffnet
sie über seinen gewohnten Öffnen-Weg, der nur ``.pap``-Dateien annimmt und alles prüft.
"""

from __future__ import annotations

import ctypes
import getpass
import json
import logging
import os
import re
import sys
import time
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

PROTOCOL = 1
HEADER_BYTES = 4
MAX_MESSAGE_BYTES = 1 << 20
MAX_FILES = 64
MAX_PATH_CHARS = 4096
CONNECT_TIMEOUT_MS = 1500
# Das erste Programm baut beim Start sein Fenster auf (rund 1–2 s ohne Ereignisschleife) – so lange darf die
# Bestätigung dauern. Ein hängendes Programm hält niemanden länger auf.
REPLY_TIMEOUT_MS = 8000
# So lange darf eine Verbindung brauchen, um ihre Nachricht vollständig zu liefern (Schutz vor Hängern)
RECEIVE_TIMEOUT_MS = 3000
# Verzögerung zwischen Bestätigung und Öffnen: Der Absender erlaubt dem laufenden Programm in dieser Zeit,
# sich in den Vordergrund zu holen (Windows verweigert das sonst Programmen im Hintergrund).
ACTIVATE_DELAY_MS = 150

SENT = "sent"             # Dateien übergeben – dieser Programmstart soll sich beenden
NO_SERVER = "no_server"   # es läuft kein anderes Programm
NO_REPLY = "no_reply"     # es läuft eins, antwortet aber nicht


def _session_id() -> int:
    """Windows-Sitzung (z. B. bei mehreren angemeldeten Benutzern an einem Rechner)."""
    if sys.platform.startswith("win"):
        try:
            session = ctypes.c_ulong()
            if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
                return int(session.value)
        except Exception:  # pragma: no cover - Absicherung
            pass
    return 0


def server_name() -> str:
    """Name der Pipe: je Benutzer und Sitzung eigen, damit sich fremde Programme nie begegnen."""
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - Absicherung
        user = "benutzer"
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", user)[:60] or "benutzer"
    return f"BSTechnikPAPDesigner.{user}.{_session_id()}"


def allow_foreground(pid) -> None:
    """Erlaubt dem Prozess ``pid``, sich in den Vordergrund zu holen (nur Windows)."""
    if sys.platform.startswith("win") and isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(pid)
        except Exception:  # pragma: no cover - Absicherung
            pass


def bring_to_front(window) -> None:
    """Holt das Fenster nach vorn, auch wenn es minimiert ist; sonst blinkt es in der Taskleiste."""
    state = window.windowState()
    if state & Qt.WindowState.WindowMinimized:
        window.setWindowState((state & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()
    QApplication.alert(window, 0)  # Windows verweigert den Vordergrund manchmal: dann wenigstens blinken


class _Guard:
    """Die Sperre „ich bin das erste Programm“: lässt sich nur einmal erwerben, bis sie freigegeben wird.

    Unter Windows ein benannter Mutex in der Sitzung (``Local\\…``): atomar, und Windows gibt ihn frei, sobald das
    Programm endet – auch bei einem Absturz. Auf anderen Systemen eine Sperrdatei (``QLockFile``).
    """

    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name: str):
        self._name = name
        self._handle = None
        self._lock = None

    def try_acquire(self) -> bool:
        if self._handle is not None or self._lock is not None:
            return True
        if sys.platform.startswith("win"):
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            ctypes.set_last_error(0)
            handle = kernel32.CreateMutexW(None, False, "Local\\" + self._name)
            error = ctypes.get_last_error()
            if not handle:
                return False  # nicht anlegbar (z. B. Zugriff verweigert): jemand anderes hat ihn
            if error == self.ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)  # nicht festhalten: sonst bliebe der Name nach dem Ende des ersten bestehen
                return False
            self._handle = handle
            return True
        from PySide6.QtCore import QDir, QLockFile

        lock = QLockFile(os.path.join(QDir.tempPath(), self._name + ".lock"))
        lock.setStaleLockTime(0)  # nie „nach Alter“ verfallen: nur wenn der Besitzer nicht mehr läuft
        if lock.tryLock(0):
            self._lock = lock
            return True
        return False

    def release(self) -> None:
        if self._handle is not None:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = None
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None


def _frame(message: dict) -> bytes:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    return len(payload).to_bytes(HEADER_BYTES, "big") + payload


def parse_request(payload: bytes) -> list[str] | None:
    """Die Dateipfade einer Nachricht – oder ``None``, wenn sie ungültig ist."""
    try:
        message = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(message, dict) or message.get("action") != "open":
        return None
    files = message.get("files")
    if not isinstance(files, list) or len(files) > MAX_FILES:
        return None
    if not all(isinstance(f, str) and 0 < len(f) <= MAX_PATH_CHARS and "\x00" not in f for f in files):
        return None
    return list(files)


def _read_frame(socket: QLocalSocket, timeout_ms: int) -> dict | None:
    """Liest eine Nachricht (blockierend, mit Zeitgrenze)."""
    deadline = time.monotonic() + timeout_ms / 1000
    buffer = bytearray()
    while True:
        buffer += bytes(socket.readAll())
        if len(buffer) >= HEADER_BYTES:
            length = int.from_bytes(buffer[:HEADER_BYTES], "big")
            if length > MAX_MESSAGE_BYTES:
                return None
            if len(buffer) >= HEADER_BYTES + length:
                try:
                    message = json.loads(bytes(buffer[HEADER_BYTES:HEADER_BYTES + length]).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return None
                return message if isinstance(message, dict) else None
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0 or not socket.waitForReadyRead(remaining):
            return None


def send_to_running(files: list[str], name: str | None = None, connect_timeout: int = CONNECT_TIMEOUT_MS,
                    reply_timeout: int = REPLY_TIMEOUT_MS) -> str:
    """Gibt ``files`` an ein bereits laufendes Programm weiter: ``SENT``, ``NO_SERVER`` oder ``NO_REPLY``."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(connect_timeout):
        return NO_SERVER
    try:
        socket.write(_frame({"protocol": PROTOCOL, "action": "open",
                             "files": [os.path.abspath(f) for f in files][:MAX_FILES]}))
        if not socket.waitForBytesWritten(reply_timeout):
            return NO_REPLY
        reply = _read_frame(socket, reply_timeout)
        if reply is None or reply.get("ok") is not True:
            return NO_REPLY
        # Das laufende Programm darf sich jetzt in den Vordergrund holen (es wartet dafür kurz)
        allow_foreground(reply.get("pid"))
        return SENT
    finally:
        socket.abort()


class _Connection(QObject):
    """Eine eingehende Verbindung: sammelt die Nachricht, bestätigt sie und übergibt die Dateien."""

    def __init__(self, socket: QLocalSocket, server: "InstanceServer"):
        super().__init__(server)
        self._socket = socket
        self._server = server
        self._buffer = bytearray()
        socket.setParent(self)
        socket.readyRead.connect(self._on_ready)
        socket.disconnected.connect(self.deleteLater)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._drop)
        self._timer.start(RECEIVE_TIMEOUT_MS)

    def _drop(self) -> None:
        self._socket.abort()
        self.deleteLater()

    def _on_ready(self) -> None:
        self._buffer += bytes(self._socket.readAll())
        if len(self._buffer) < HEADER_BYTES:
            return
        length = int.from_bytes(self._buffer[:HEADER_BYTES], "big")
        if length > MAX_MESSAGE_BYTES:
            self._drop()
            return
        if len(self._buffer) < HEADER_BYTES + length:
            return
        self._timer.stop()
        files = parse_request(bytes(self._buffer[HEADER_BYTES:HEADER_BYTES + length]))
        self._buffer.clear()
        self._socket.write(_frame({"ok": files is not None, "pid": os.getpid(), "protocol": PROTOCOL}))
        self._socket.flush()
        self._socket.disconnectFromServer()
        if files is not None:
            self._server.deliver(files)


class InstanceServer(QObject):
    """Lauscht auf Dateien, die weitere Programmstarts übergeben."""

    def __init__(self, name: str | None = None, parent: QObject | None = None, guard: _Guard | None = None):
        super().__init__(parent)
        self._name = name or server_name()
        self._guard = guard
        self._server: QLocalServer | None = None
        self._handler: Callable[[list[str]], None] | None = None
        self._backlog: list[list[str]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def listening(self) -> bool:
        return self._server is not None and self._server.isListening()

    def start(self) -> bool:
        """Beginnt zu lauschen. ``False``, wenn schon ein anderes Programm lauscht."""
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)  # nur der eigene Benutzer
        server.newConnection.connect(self._on_new_connection)
        if not server.listen(self._name):
            server.deleteLater()
            return False
        self._server = server
        return True

    def set_handler(self, handler: Callable[[list[str]], None]) -> None:
        """Legt fest, wer die Dateien erhält. Bis dahin Eingetroffenes wird jetzt nachgereicht."""
        self._handler = handler
        backlog, self._backlog = self._backlog, []
        for files in backlog:
            QTimer.singleShot(0, lambda f=files: self._dispatch(f))

    def close(self) -> None:
        """Hört auf zu lauschen (z. B. beim Beenden): Später startende Programme werden dann selbst das erste."""
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None
        if self._guard is not None:
            self._guard.release()  # ein später startendes Programm wird selbst das erste

    def deliver(self, files: list[str]) -> None:
        # kurz warten: der Absender erlaubt dem Programm erst jetzt, sich in den Vordergrund zu holen
        QTimer.singleShot(ACTIVATE_DELAY_MS, lambda: self._dispatch(files))

    def _dispatch(self, files: list[str]) -> None:
        if self._handler is None:
            self._backlog.append(files)  # das Fenster ist noch nicht bereit (Ladebildschirm)
            return
        try:
            self._handler(files)
        except Exception:  # pragma: no cover - Absicherung: ein Fehler darf den Empfang nie beenden
            log.exception("Übergebene Dateien konnten nicht geöffnet werden")

    def _on_new_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            _Connection(self._server.nextPendingConnection(), self)


def acquire(files: list[str], name: str | None = None, attempts: int = 20, pause: float = 0.15,
            reply_timeout: int = REPLY_TIMEOUT_MS) -> tuple[bool, InstanceServer | None]:
    """Übergibt die Dateien an ein laufendes Programm oder wird selbst das erste.

    Gibt ``(True, None)`` zurück, wenn die Dateien übergeben wurden (dieser Programmstart soll sich beenden),
    sonst ``(False, server)`` mit dem lauschenden Server – oder ``(False, None)``, wenn ein Programm läuft,
    aber nicht antwortet (dann startet dieses als eigenes Fenster ohne Server).
    """
    name = name or server_name()
    guard = _Guard(name)
    server = InstanceServer(name, guard=guard)
    for _ in range(max(1, attempts)):
        if guard.try_acquire():  # wer die Sperre bekommt, ist das erste Programm – bei gleichzeitigen Starts genau einer
            if server.start():
                return False, server
            guard.release()
            log.warning("Die lokale Pipe für andere Programmfenster ließ sich nicht anlegen – dieses startet allein.")
            return False, None
        result = send_to_running(files, name, reply_timeout=reply_timeout)
        if result == SENT:
            return True, None
        if result == NO_REPLY:
            log.warning("Ein anderes Programmfenster antwortet nicht – dieses startet als eigenes Fenster.")
            return False, None
        time.sleep(pause)  # das erste Programm lauscht noch nicht (es startet gerade): gleich noch einmal versuchen
    log.warning("Der Austausch mit anderen Programmfenstern ist nicht möglich – dieses startet allein.")
    return False, None
