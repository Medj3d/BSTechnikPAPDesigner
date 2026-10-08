"""Tests für „ein Fenster für alles“: Weitere Programmstarts übergeben ihre Dateien an das laufende Programm."""

import json
import os
import shutil
import subprocess
import sys
import time
import uuid

import pytest
from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QMessageBox

from app import config, single_instance, updater
from app.single_instance import NO_REPLY, NO_SERVER, SENT, InstanceServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


@pytest.fixture
def name():
    """Ein eigener Pipe-Name je Test – nie der des echten Programms."""
    return f"test.pap.{uuid.uuid4().hex}"


@pytest.fixture
def server(name):
    instance = InstanceServer(name)
    assert instance.start()
    yield instance
    instance.close()


def pump(qapp, condition, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    return condition()


# Der Absender läuft – wie beim Doppelklick im Explorer – als eigener Prozess. (Ein Thread ohne Qt-Ereignisschleife
# verhält sich bei blockierenden Socket-Aufrufen anders und wäre kein aussagekräftiger Test.)
SENDER_CODE = """
import json, sys, time
sys.path.insert(0, __ROOT__)
from PySide6.QtCore import QCoreApplication
app = QCoreApplication(sys.argv[:1])
from app import single_instance as si
mode, name, files, seconds = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), float(sys.argv[4])
if mode == "send":
    print(si.send_to_running(files, name))
else:
    handed, server = si.acquire(files, name, attempts=40)
    print("HANDED" if handed else ("SERVER" if server else "ALONE"), flush=True)
    if server:
        received = []
        server.set_handler(received.append)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)
        print("RECEIVED " + json.dumps(received))
        server.close()
""".replace("__ROOT__", repr(ROOT))


def start_sender(mode: str, name: str, files: list[str], seconds: float = 0.0, cwd=None) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", SENDER_CODE, mode, name, json.dumps(files), str(seconds)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)


def finish(qapp, process: subprocess.Popen, seconds: float = 30.0) -> str:
    """Wartet auf den Absender (der Server hier arbeitet währenddessen) und liefert seine Ausgabe."""
    pump(qapp, lambda: process.poll() is not None, seconds)
    out, err = process.communicate(timeout=5)
    assert process.returncode == 0, err[-600:]
    return out.strip()


def send(qapp, files: list[str], name: str, cwd=None) -> str:
    """Ein zweiter Programmstart gibt seine Dateien weiter; liefert ``SENT``, ``NO_SERVER`` oder ``NO_REPLY``."""
    return finish(qapp, start_sender("send", name, files, cwd=cwd))


class Receiver:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, files):
        self.calls.append(files)


# --------------------------------------------------------------- Grundlagen
def test_server_name_is_per_user_and_session_and_safe():
    name = single_instance.server_name()
    assert name.startswith("BSTechnikPAPDesigner.") and name == single_instance.server_name()
    assert all(c.isalnum() or c in "._-" for c in name) and len(name) < 120
    assert name.rsplit(".", 1)[1].isdigit()  # Sitzungsnummer


@pytest.mark.parametrize("payload, expected", [
    (b'{"action": "open", "files": ["C:\\\\a.pap", "b.pap"]}', ["C:\\a.pap", "b.pap"]),
    (b'{"action": "open", "files": []}', []),
    (b'{"action": "open", "files": ["\xc3\xa4\xc3\xb6\xc3\xbc \xe2\x82\xac.pap"]}', ["äöü €.pap"]),
    (b"", None), (b"kein json", None), (b"[]", None), (b"42", None), (b"null", None),
    (b'{"files": []}', None), (b'{"action": "zerstoeren", "files": []}', None),
    (b'{"action": "open"}', None), (b'{"action": "open", "files": "a.pap"}', None),
    (b'{"action": "open", "files": [1, 2]}', None), (b'{"action": "open", "files": [""]}', None),
    (b'{"action": "open", "files": ["a\\u0000b.pap"]}', None), (b'{"action": "open", "files": [null]}', None),
    (b"\xff\xfe\x00garbage", None), (b'{"action": "open", "files": ["' + b"x" * 5000 + b'"]}', None),
    (b'{"action": "open", "files": [' + b",".join([b'"a.pap"'] * 65) + b"]}", None),
    (b"[" * 5000, None),
])
def test_requests_are_validated(payload, expected):
    assert single_instance.parse_request(payload) == expected


# ---------------------------------------------------- Übergabe an das erste Programm
def test_second_start_hands_its_files_to_the_running_program(qapp, server, tmp_path):
    receiver = Receiver()
    server.set_handler(receiver)
    first, second = tmp_path / "eins.pap", tmp_path / "zwei mit Leerzeichen.pap"
    assert send(qapp, [str(first), str(second)], server.name) == SENT
    assert pump(qapp, lambda: receiver.calls)
    assert receiver.calls == [[str(first), str(second)]]


def test_relative_paths_become_absolute(qapp, server, tmp_path):
    receiver = Receiver()
    server.set_handler(receiver)
    assert send(qapp, ["plan.pap", os.path.join("unter", "x.pap")], server.name, cwd=tmp_path) == SENT
    assert pump(qapp, lambda: receiver.calls)
    assert receiver.calls == [[str(tmp_path / "plan.pap"), str(tmp_path / "unter" / "x.pap")]]


def test_start_without_files_just_brings_the_window_forward(qapp, server):
    receiver = Receiver()
    server.set_handler(receiver)
    assert send(qapp, [], server.name) == SENT
    assert pump(qapp, lambda: receiver.calls) and receiver.calls == [[]]


def test_the_reply_names_the_running_program_so_it_may_take_the_foreground(qapp, server):
    server.set_handler(Receiver())
    reply = raw_exchange(qapp, server.name, frame(b'{"action": "open", "files": []}'), expect_reply=True)
    message = json.loads(reply[4:].decode("utf-8"))
    assert message == {"ok": True, "pid": os.getpid(), "protocol": single_instance.PROTOCOL}


def test_many_starts_in_a_row_arrive_in_order(qapp, server, tmp_path):
    receiver = Receiver()
    server.set_handler(receiver)
    paths = [str(tmp_path / f"datei{i}.pap") for i in range(5)]
    for path in paths:
        assert send(qapp, [path], server.name) == SENT
    assert pump(qapp, lambda: len(receiver.calls) == 5)
    assert [call[0] for call in receiver.calls] == paths


def test_files_arriving_before_the_window_is_ready_are_kept(qapp, server, tmp_path):
    """Während des Ladebildschirms ist noch niemand zuständig: die Dateien werden gemerkt und danach geöffnet."""
    one, two = str(tmp_path / "a.pap"), str(tmp_path / "b.pap")
    assert send(qapp, [one], server.name) == SENT
    assert send(qapp, [two], server.name) == SENT
    pump(qapp, lambda: False, 0.4)  # abwarten: es ist noch keiner zuständig
    receiver = Receiver()
    server.set_handler(receiver)
    assert pump(qapp, lambda: len(receiver.calls) == 2)
    assert receiver.calls == [[one], [two]]


def test_nobody_running_means_no_server(name):
    started = time.monotonic()
    assert single_instance.send_to_running(["a.pap"], name, connect_timeout=300) == NO_SERVER
    assert time.monotonic() - started < 2.0


def test_the_guard_allows_only_one_first_program(name):
    first, second = single_instance._Guard(name), single_instance._Guard(name)
    try:
        assert first.try_acquire() and first.try_acquire()  # derselbe Besitzer darf nachfragen
        assert not second.try_acquire()
        first.release()
        assert second.try_acquire()  # frei, sobald das erste Programm weg ist
        assert not first.try_acquire()
    finally:
        first.release()
        second.release()


GUARD_HOLDER = """
import sys, time
sys.path.insert(0, __ROOT__)
from app import single_instance as si
guard = si._Guard(sys.argv[1])
print('HELD' if guard.try_acquire() else 'BUSY', flush=True)
time.sleep(float(sys.argv[2]))
""".replace("__ROOT__", repr(ROOT))


def test_the_guard_works_across_processes_and_is_freed_when_the_owner_dies(name):
    holder = subprocess.Popen([sys.executable, "-c", GUARD_HOLDER, name, "30"], stdout=subprocess.PIPE, text=True)
    guard = single_instance._Guard(name)
    try:
        assert holder.stdout.readline().strip() == "HELD"
        assert not guard.try_acquire()  # ein anderes Programm ist das erste
        holder.kill()  # Absturz: kein Aufräumen durch das Programm selbst
        holder.wait(10)
        deadline = time.monotonic() + 5
        while not guard.try_acquire() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert guard.try_acquire()  # Windows hat die Sperre freigegeben: das nächste Programm wird das erste
    finally:
        guard.release()
        holder.kill()


def test_qt_alone_would_not_keep_two_servers_apart(name):
    """Warum es die Sperre gibt: Mehrere lauschende Server mit demselben Namen sind möglich."""
    first, second = InstanceServer(name), InstanceServer(name)
    try:
        assert first.start() and second.start()  # kein Fehler – deshalb darf die Pipe nicht über „erstes Programm“ entscheiden
    finally:
        first.close()
        second.close()


def test_closing_the_server_frees_the_guard(name):
    handed_over, first = single_instance.acquire([], name)
    assert not handed_over and first is not None
    other = single_instance._Guard(name)
    try:
        assert not other.try_acquire()
        first.close()
        assert other.try_acquire()
    finally:
        first.close()
        other.release()


# ---------------------------------------------------------------- acquire
def test_acquire_makes_the_first_program_the_server_and_hands_over_the_second(qapp, name, tmp_path):
    handed_over, first = single_instance.acquire([], name)
    assert handed_over is False and first is not None and first.listening
    try:
        receiver = Receiver()
        first.set_handler(receiver)
        target = str(tmp_path / "x.pap")
        assert finish(qapp, start_sender("acquire", name, [target])) == "HANDED"  # dieser Start beendet sich
        assert pump(qapp, lambda: receiver.calls) and receiver.calls == [[target]]
    finally:
        first.close()


def test_programs_starting_at_the_same_moment_end_up_as_one_window(name, tmp_path):
    """Doppelklick auf mehrere Dateien: alle Starts laufen gleichzeitig los, nur einer darf lauschen."""
    paths = [str(tmp_path / f"p{i}.pap") for i in range(4)]
    processes = [start_sender("acquire", name, [path], seconds=6.0) for path in paths]
    outputs = []
    for process in processes:
        out, err = process.communicate(timeout=60)
        assert process.returncode == 0, err[-600:]
        outputs.append(out.strip().splitlines())
    firsts = [lines[0] for lines in outputs]
    assert sorted(firsts) == ["HANDED", "HANDED", "HANDED", "SERVER"], firsts
    (server_lines,) = [lines for lines in outputs if lines[0] == "SERVER"]
    received = json.loads(server_lines[1].removeprefix("RECEIVED "))
    delivered = sorted(call[0] for call in received)
    own = paths[firsts.index("SERVER")]
    # die drei übrigen Dateien kamen beim ersten Programm an; die eigene öffnet es selbst
    assert delivered == sorted(set(paths) - {own})


def test_unresponsive_program_does_not_block_the_new_start_forever(name):
    """Es läuft eins, antwortet aber nicht (hängt): der neue Start wartet nur kurz und startet allein."""
    guard = single_instance._Guard(name)
    assert guard.try_acquire()  # dieses „Programm“ ist das erste …
    hung = InstanceServer(name, guard=guard)
    assert hung.start()  # … und lauscht, aber hier läuft keine Ereignisschleife: es liest nie
    try:
        started = time.monotonic()
        assert single_instance.send_to_running(["a.pap"], name, reply_timeout=300) == NO_REPLY
        assert single_instance.acquire(["a.pap"], name, reply_timeout=300) == (False, None)
        assert time.monotonic() - started < 6.0
    finally:
        hung.close()


# ------------------------------------------------- fehlerhafte und feindliche Eingaben
def raw_exchange(qapp, name, data: bytes, wait_ms: int = 600, expect_reply: bool = False) -> bytes:
    """Schickt rohe Bytes an den Server und liefert, was zurückkommt (während hier die Ereignisse laufen).

    ``expect_reply``: auf eine Antwort notfalls länger warten (ein ausgelasteter Rechner antwortet später) und
    zurückkehren, sobald sie vollständig da ist.
    """
    socket = QLocalSocket()
    socket.connectToServer(name)
    assert socket.waitForConnected(1000)
    socket.write(data)
    socket.flush()
    received = bytearray()
    deadline = time.monotonic() + (max(wait_ms, 5000) if expect_reply else wait_ms) / 1000
    last_data = None
    while time.monotonic() < deadline:
        qapp.processEvents()
        chunk = bytes(socket.readAll())
        if chunk:
            received += chunk
            last_data = time.monotonic()
        elif expect_reply and last_data is not None and time.monotonic() - last_data > 0.1:
            break
        time.sleep(0.005)
    socket.abort()
    return bytes(received)


def frame(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


@pytest.mark.parametrize("payload", [b"kein json", b"[]", b'{"action": "open", "files": [1]}', b'{"action":"x"}'])
def test_invalid_messages_are_refused_and_never_opened(qapp, server, payload):
    receiver = Receiver()
    server.set_handler(receiver)
    reply = raw_exchange(qapp, server.name, frame(payload), expect_reply=True)
    assert b'"ok": false' in reply
    pump(qapp, lambda: False, 0.4)
    assert receiver.calls == []
    # der Server arbeitet danach weiter
    assert send(qapp, ["a.pap"], server.name) == SENT


def test_oversized_message_is_dropped(qapp, server):
    receiver = Receiver()
    server.set_handler(receiver)
    assert raw_exchange(qapp, server.name, (single_instance.MAX_MESSAGE_BYTES + 1).to_bytes(4, "big") + b"x" * 64) == b""
    assert receiver.calls == []
    assert send(qapp, [], server.name) == SENT


def test_incomplete_message_is_dropped_after_a_short_wait(qapp, server, monkeypatch):
    monkeypatch.setattr(single_instance, "RECEIVE_TIMEOUT_MS", 150)
    receiver = Receiver()
    server.set_handler(receiver)
    assert raw_exchange(qapp, server.name, (100).to_bytes(4, "big") + b'{"action"', wait_ms=700) == b""
    assert receiver.calls == []
    assert send(qapp, [], server.name) == SENT


def test_garbage_and_silent_clients_do_not_disturb_the_server(qapp, server):
    receiver = Receiver()
    server.set_handler(receiver)
    for data in (b"", b"\x00", b"\xff" * 3, os.urandom(300)):
        raw_exchange(qapp, server.name, data, wait_ms=60)
    assert send(qapp, ["ok.pap"], server.name) == SENT
    assert pump(qapp, lambda: receiver.calls) and len(receiver.calls) == 1


def test_a_failing_handler_does_not_end_the_reception(qapp, server):
    seen = []

    def handler(files):
        seen.append(files)
        if len(seen) == 1:
            raise RuntimeError("Fehler beim Öffnen")

    server.set_handler(handler)
    assert send(qapp, ["a.pap"], server.name) == SENT
    assert send(qapp, ["b.pap"], server.name) == SENT
    assert pump(qapp, lambda: len(seen) == 2)


# ---------------------------------------------------------- Fenster und Programmstart
@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


def test_files_from_another_start_open_as_tabs_in_the_same_window(window, tmp_path):
    first = shutil.copy(EXAMPLE, tmp_path / "eins.pap")
    second = shutil.copy(EXAMPLE, tmp_path / "zwei.pap")
    window.open_external_files([str(first)])
    window.open_external_files([str(second)])
    assert [view.document.file_path for view in window.views()] == [str(first), str(second)]
    assert window.current_document().file_path == str(second)
    window.open_external_files([str(first)])  # schon geöffnet: kein zweiter Reiter, nur nach vorn
    assert len(window.views()) == 2 and window.current_document().file_path == str(first)
    window.open_external_files([])
    assert len(window.views()) == 2


def test_several_files_at_once_and_unusable_ones(window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: shown.append(text))
    good = shutil.copy(EXAMPLE, tmp_path / "gut.pap")
    other = tmp_path / "notizen.txt"
    other.write_text("kein Plan")
    broken = tmp_path / "kaputt.pap"
    broken.write_text("<kaputt")
    window.open_external_files([str(other), str(good), str(broken), str(tmp_path / "fehlt.pap")])
    assert [view.document.file_path for view in window.views()] == [str(good)]
    assert len(shown) == 3  # eine Meldung je unbrauchbarer Datei, die brauchbare wird trotzdem geöffnet


def test_an_empty_new_project_is_replaced_by_the_first_received_file(window, tmp_path):
    window.new_document()
    target = shutil.copy(EXAMPLE, tmp_path / "plan.pap")
    window.open_external_files([str(target)])
    assert [view.document.file_path for view in window.views()] == [str(target)]


def test_bring_to_front_restores_a_minimized_window(window):
    window.setWindowState(Qt.WindowState.WindowMinimized)
    assert window.isMinimized()
    single_instance.bring_to_front(window)
    assert not window.isMinimized()


def test_closing_the_window_stops_listening(window, name):
    window.instance_server = InstanceServer(name)
    assert window.instance_server.start()
    window.close()
    assert not window.instance_server.listening  # weitere Starts werden dann selbst das erste Programm


def test_start_arguments_are_split_into_files_flags_and_values(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pap_main", os.path.join(ROOT, "main.py"))
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    plan = tmp_path / "plan.pap"
    plan.write_text("x")
    other = tmp_path / "zweiter.pap"
    other.write_text("x")
    arguments = [config.WAIT_FOR_FLAG, "4711", str(plan), config.NEW_WINDOW_FLAG, "gibt_es_nicht.pap", str(other), "-x"]
    assert main._files_from(arguments) == [str(plan), str(other)]
    assert main._flag_value(arguments, config.WAIT_FOR_FLAG) == "4711"
    assert main._flag_value(arguments, "--fehlt") is None and main._flag_value(["--warte-auf"], config.WAIT_FOR_FLAG) is None


def test_main_waits_then_hands_over_then_shows_the_splash():
    """Reihenfolge in main.py: warten → an neuere Kopie abgeben → Qt → an laufendes Fenster übergeben → Ladebildschirm."""
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as handle:
        body = handle.read()
    body = body[body.index("def main()"):]
    order = [body.index("updater.wait_for_exit("), body.index("updater.redirect_to_user_program(arguments)"),
             body.index("app = _create_application(arguments)"), body.index("single_instance.acquire(files)"),
             body.index("splash = _show_splash(app)")]
    assert order == sorted(order)
    # der Ladebildschirm erscheint also erst, wenn klar ist, dass dieser Start das erste Programm ist
    assert "if config.NEW_WINDOW_FLAG not in arguments" in body and "if handed_over:" in body


def test_restarts_wait_for_the_old_program(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda command, **kwargs: started.append((command, kwargs)))
    updater.launch_program(str(tmp_path), wait_pid=4711)
    updater.launch_program(str(tmp_path))
    assert started[0][0] == [str(tmp_path / config.EXECUTABLE_NAME), config.WAIT_FOR_FLAG, "4711"]
    assert started[1][0] == [str(tmp_path / config.EXECUTABLE_NAME)]


def test_build_includes_the_network_module_needed_for_the_hand_over():
    with open(os.path.join(ROOT, "BSTechnikPAPDesigner.spec"), encoding="utf-8") as handle:
        spec = handle.read()
    assert "PySide6.QtNetwork" not in spec[spec.index("excludes"):]
