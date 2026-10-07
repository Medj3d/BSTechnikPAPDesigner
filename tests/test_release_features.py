"""Tests für Über-Dialog, Ladebildschirm, automatisches Speichern und Updates."""

import hashlib
import io
import json
import os
import shutil
import time
import urllib.error
import zipfile

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox

from app import config, resources, splash, updater
from app.fileformat.serializer import load_diagram
from app.model.element_types import ElementType as T
from tests.conftest import add

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")
PAP_SAMPLE = os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap")
EXE = config.EXECUTABLE_NAME


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    win.set_auto_save(False)
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


def wait_until(qapp, condition, seconds=3.0):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return condition()


def saved_project(window, tmp_path, monkeypatch, name="plan.pap"):
    """Ein neues Projekt, das einmal gespeichert wurde."""
    window.new_document()
    document = window.current_document()
    add(document.scene, T.PROCESS, 0, 0)
    path = str(tmp_path / name)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))
    assert window.save_document(document)
    return document, path


def blocks_in(path) -> int:
    return len(load_diagram(path).diagram.elements)


# ------------------------------------------------------- Über / Ladebildschirm
def test_about_dialog_names_authors_version_and_month():
    from app.dialogs.about import AboutDialog
    dialog = AboutDialog()
    text = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Are Schäfer" in text and "Linus Twardzik" in text
    assert f"Version {config.APP_VERSION}" in text and config.APP_RELEASE_DATE in text
    assert config.APP_RELEASE_DATE.split()[-1].isdigit()  # „Monat Jahr“
    dialog.deleteLater()


def test_splash_shows_logo_credit_and_version(monkeypatch):
    assert os.path.isfile(resources.asset_path(splash.LOGO_FILE))
    assert config.SPLASH_CREDIT == "A product for BS Technik from Are Schäfer and Linus Twardzik"
    assert splash.version_text() == f"Version {config.APP_VERSION}"
    pixmap = splash.render_splash(1.0)
    assert (pixmap.width(), pixmap.height()) == (splash.SPLASH_WIDTH, splash.SPLASH_HEIGHT)
    image = pixmap.toImage()
    center = image.pixelColor(splash.SPLASH_WIDTH // 2, 36 + 135)
    assert center.blue() > center.red() + 40  # das Blau des Logos in der Mitte
    assert image.pixelColor(3, 3).lightness() == 0  # schwarzer Hintergrund
    # Schrift unter dem Logo und in der Ecke unten rechts
    assert any(image.pixelColor(x, 338).lightness() > 150 for x in range(60, 500))
    assert any(image.pixelColor(x, y).lightness() > 80 for x in range(470, 545) for y in range(410, 430))
    assert not any(image.pixelColor(x, y).lightness() > 80 for x in range(10, 120) for y in range(410, 430))
    # hohe Bildschirmauflösung: schärferes Bild gleicher Größe
    sharp = splash.render_splash(2.0)
    assert sharp.width() == 2 * splash.SPLASH_WIDTH and sharp.devicePixelRatio() == 2.0
    # fehlt das Logo, erscheint ersatzweise das Programmsymbol statt eines Fehlers
    monkeypatch.setattr(splash, "LOGO_FILE", "gibt_es_nicht.png")
    assert not splash.render_splash(1.0).isNull()


def test_splash_screen_shows_the_logo_at_once_and_the_text_right_after():
    def has_text(pixmap) -> bool:
        image = pixmap.toImage()
        ratio = pixmap.devicePixelRatio()
        return any(image.pixelColor(int(x * ratio), int(338 * ratio)).lightness() > 150 for x in range(60, 500))

    screen = splash.SplashScreen()
    first = screen.pixmap()
    center = first.toImage().pixelColor(first.width() // 2, int((36 + 135) * first.devicePixelRatio()))
    assert center.blue() > center.red() + 40 and not has_text(first)  # nur das Logo – ohne Wartezeit
    screen.complete()
    assert has_text(screen.pixmap())
    screen.deleteLater()
    # der Ladebildschirm bleibt 5 bis 7 Sekunden stehen
    assert 5000 <= config.SPLASH_MIN_DURATION_MS <= 7000


def test_start_shows_the_splash_before_loading_the_program():
    """In main.py steht der Ladebildschirm vor allem, was Zeit kostet."""
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as handle:
        source = handle.read()
    body = source[source.index("def main()"):]
    shown = body.index("_show_splash(app)")
    assert shown < body.index("_apply_look(app)") < body.index("from app.main_window import MainWindow")
    assert "main_window" not in body[:shown] and "updater" not in body[:shown]


# ------------------------------------------------------ Automatisches Speichern
def test_auto_save_writes_a_saved_project_after_a_change(window, qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTO_SAVE_DELAY_MS", 20)
    document, path = saved_project(window, tmp_path, monkeypatch)
    window.set_auto_save(True)
    assert window.actions["auto_save"].isChecked() and blocks_in(path) == 1
    add(document.scene, T.PROCESS, 0, 200)
    assert document.is_modified and blocks_in(path) == 1  # noch nicht – erst kurz nach der Änderung
    assert wait_until(qapp, lambda: not document.is_modified)
    assert blocks_in(path) == 2
    assert "Automatisch gespeichert" in window.statusBar().currentMessage()
    # Rückgängig ist eine Änderung wie jede andere
    document.undo_stack.undo()
    assert wait_until(qapp, lambda: not document.is_modified) and blocks_in(path) == 1


def test_auto_save_leaves_unsaved_and_foreign_projects_alone(window, qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTO_SAVE_DELAY_MS", 10)
    window.set_auto_save(True)
    window.new_document()  # noch nie gespeichert
    fresh = window.current_document()
    add(fresh.scene, T.PROCESS, 0, 0)
    foreign_path = shutil.copy(PAP_SAMPLE, tmp_path / "mittelwert.pap")
    original = open(foreign_path, "rb").read()
    assert window.open_file(str(foreign_path))  # aus einem anderen Programm
    foreign = window.current_document()
    add(foreign.scene, T.PROCESS, 900, 900)
    assert window._auto_save_pending == set()
    wait_until(qapp, lambda: False, 0.15)
    assert fresh.is_modified and foreign.is_modified
    assert open(foreign_path, "rb").read() == original
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == ["mittelwert.pap"]


def test_auto_save_can_be_switched_off(window, qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTO_SAVE_DELAY_MS", 10)
    document, path = saved_project(window, tmp_path, monkeypatch)
    assert not window.actions["auto_save"].isChecked()  # in den Tests aus (siehe conftest)
    add(document.scene, T.PROCESS, 0, 200)
    wait_until(qapp, lambda: False, 0.15)
    assert document.is_modified and blocks_in(path) == 1
    window.set_auto_save(True)  # Einschalten holt offene Änderungen nach
    assert wait_until(qapp, lambda: not document.is_modified) and blocks_in(path) == 2


def test_auto_save_does_not_interrupt_typing(window, qapp, tmp_path, monkeypatch):
    document, path = saved_project(window, tmp_path, monkeypatch)
    window.set_auto_save(True)
    item = document.scene.elements()[0]
    add(document.scene, T.PROCESS, 0, 200)
    document.scene.begin_element_edit(item, select_all=True)
    document.scene._editor.setPlainText("noch nicht fertig")
    window._run_auto_save()
    assert document.scene.is_editing and document.is_modified and blocks_in(path) == 1
    assert document in window._auto_save_pending  # wird nachgeholt
    document.scene.commit_edit()
    window._run_auto_save()
    assert not document.is_modified and blocks_in(path) == 2
    assert load_diagram(path).diagram.elements[0].text == "noch nicht fertig"


def test_auto_save_does_not_wait_forever_while_work_continues(window, tmp_path, monkeypatch):
    document, path = saved_project(window, tmp_path, monkeypatch)
    window.set_auto_save(True)
    add(document.scene, T.PROCESS, 0, 200)
    assert window._auto_save_timer.interval() == config.AUTO_SAVE_DELAY_MS
    window._auto_save_since -= config.AUTO_SAVE_MAX_WAIT_MS / 1000 + 1  # es wird schon lange gearbeitet
    add(document.scene, T.PROCESS, 0, 400)
    assert window._auto_save_timer.isActive() and window._auto_save_timer.interval() == 0


def test_auto_save_failure_is_quiet_and_keeps_the_project_modified(window, tmp_path, monkeypatch):
    folder = tmp_path / "ordner"
    folder.mkdir()
    document, path = saved_project(window, folder, monkeypatch)
    window.set_auto_save(True)
    add(document.scene, T.PROCESS, 0, 200)
    shutil.rmtree(folder)  # z. B. USB-Stick abgezogen
    window._run_auto_save()  # kein Meldungsfenster (die Tests sperren echte Dialoge)
    assert document.is_modified
    assert "Automatisches Speichern nicht möglich" in window.statusBar().currentMessage()


def test_closing_saves_silently_when_auto_save_is_on(window, tmp_path, monkeypatch):
    document, path = saved_project(window, tmp_path, monkeypatch)
    window.set_auto_save(True)
    add(document.scene, T.PROCESS, 0, 200)
    assert document.is_modified
    assert window.close_tab(window.tabs.currentIndex())  # ohne Nachfrage
    assert window.views() == [] and blocks_in(path) == 2


def test_auto_save_choice_is_remembered(window):
    store = window.settings_store
    try:
        window.actions["auto_save"].trigger()
        assert store.auto_save() is True and window._auto_save_enabled
        window.actions["auto_save"].trigger()
        assert store.auto_save() is False and not window._auto_save_enabled
    finally:
        store._settings.remove("auto_save")
    assert store.auto_save() is config.AUTO_SAVE_DEFAULT


def test_menus_offer_auto_save_and_update_check(window):
    menus = {action.text().replace("&", ""): action.menu() for action in window.menuBar().actions()}
    file_entries = [a.text().replace("&", "") for a in menus["Datei"].actions()]
    help_entries = [a.text().replace("&", "") for a in menus["Hilfe"].actions()]
    assert "Automatisch speichern" in file_entries
    assert "Nach Updates suchen …" in help_entries and "Über das Programm" in help_entries


# ------------------------------------------------------------------ Updates
@pytest.mark.parametrize("candidate, current, newer", [
    ("1.0.1", "1.0.0", True), ("v1.1", "1.0.9", True), ("2", "1.9.9", True), ("1.10.0", "1.9.0", True),
    ("1.0.0", "1.0.0", False), ("1.0", "1.0.0", False), ("0.9.9", "1.0.0", False), ("1.0.0", "1.0.1", False),
    ("", "1.0.0", False), ("neu", "1.0.0", False), ("1.0.0-beta", "0.1", False), (None, "1.0.0", False),
])
def test_version_comparison(candidate, current, newer):
    assert updater.is_newer(candidate, current) is newer


def manifest(**changes) -> bytes:
    data = {"version": "9.9.9", "tag": "v9.9.9", "released": "Mai 2030", "file": config.UPDATE_PACKAGE_NAME,
            "size": 10, "sha256": "ab" * 32, "notes": "Neu:\n- alles"}
    data.update(changes)
    return json.dumps(data).encode("utf-8")


def test_manifest_is_read():
    info = updater.parse_manifest(manifest(), "schule/pap")
    assert info.version == "9.9.9" and info.sha256 == "ab" * 32 and info.notes.startswith("Neu")
    assert info.package_url == f"https://github.com/schule/pap/releases/download/v9.9.9/{config.UPDATE_PACKAGE_NAME}"


@pytest.mark.parametrize("raw", [
    b"", b"kein json", b"[]", manifest(version="neu"), manifest(sha256="kurz"), manifest(sha256="zz" * 32),
    manifest(file="../../boese.zip"), manifest(file="programm.exe"), manifest(tag="v1/../../x"),
    manifest(file="https://anderswo.example/x.zip"),
])
def test_bad_manifest_is_rejected(raw):
    with pytest.raises(updater.UpdateError):
        updater.parse_manifest(raw, "schule/pap")


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def test_update_check_reads_the_latest_release(monkeypatch):
    monkeypatch.setattr(config, "UPDATE_REPOSITORY", "schule/pap")
    urls = []
    info = updater.fetch_update_info(opener=lambda url, timeout: urls.append(url) or FakeResponse(manifest()))
    assert urls == ["https://github.com/schule/pap/releases/latest/download/version.json"]
    assert updater.is_newer(info.version, config.APP_VERSION)

    def missing(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    def offline(url, timeout):
        raise OSError("kein Netz")

    for opener, word in ((missing, "noch keine Version"), (offline, "keine Verbindung")):
        with pytest.raises(updater.UpdateError) as failure:
            updater.fetch_update_info(opener=opener)
        assert word in failure.value.message


@pytest.mark.parametrize("value", ["", "   ", "nur-ein-name", "a/b/c", "https://github.com/a/b", "a b/c"])
def test_without_a_valid_source_nothing_is_contacted(monkeypatch, value):
    monkeypatch.setattr(config, "UPDATE_REPOSITORY", value)

    def forbidden(*_args):
        raise AssertionError("darf nicht aufgerufen werden")

    assert updater.repository() == "" and updater.fetch_update_info(opener=forbidden) is None


def test_only_secure_connections_are_used():
    with pytest.raises(updater.UpdateError):
        updater._open("http://github.com/x/y/releases/latest/download/version.json", 1)


def package(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def info_for(data: bytes, **changes) -> updater.UpdateInfo:
    values = {"version": "9.9.9", "package_url": "https://github.com/schule/pap/releases/download/v9.9.9/p.zip",
              "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    values.update(changes)
    return updater.UpdateInfo(**values)


@pytest.mark.parametrize("prefix", ["", "BSTechnikPAPDesigner/"])
def test_package_is_downloaded_checked_and_unpacked(tmp_path, prefix):
    data = package({prefix + EXE: b"neu", prefix + "_internal/lib.dll": b"dll"})
    steps = []
    new_dir = updater.download_package(info_for(data), str(tmp_path), progress=lambda d, t: steps.append((d, t)),
                                       opener=lambda url, timeout: FakeResponse(data))
    assert os.path.dirname(new_dir).startswith(str(tmp_path / updater.STAGING_DIRECTORY))
    assert open(os.path.join(new_dir, EXE), "rb").read() == b"neu"
    assert os.path.isfile(os.path.join(new_dir, "_internal", "lib.dll"))
    assert steps[-1] == (len(data), len(data))
    assert not os.path.exists(tmp_path / updater.STAGING_DIRECTORY / "paket.zip")


def test_damaged_or_dangerous_packages_change_nothing(tmp_path):
    good = package({EXE: b"neu"})
    cases = [
        (good, info_for(good, sha256="00" * 32), "Prüfsumme"),
        (package({"liesmich.txt": b"x"}), None, "enthält das Programm nicht"),
        (package({EXE: b"neu", "../ausbruch.txt": b"x"}), None, "unzulässige Pfade"),
        (b"kein zip", None, "nicht entpackt"),
    ]
    for data, info, word in cases:
        with pytest.raises(updater.UpdateError) as failure:
            updater.download_package(info or info_for(data), str(tmp_path),
                                     opener=lambda url, timeout, d=data: FakeResponse(d))
        assert word in failure.value.message
        assert list(tmp_path.iterdir()) == []  # auch kein Zwischenordner bleibt zurück
    with pytest.raises(updater.UpdateCancelled):
        updater.download_package(info_for(good), str(tmp_path), cancelled=lambda: True,
                                 opener=lambda url, timeout: FakeResponse(good))
    assert list(tmp_path.iterdir()) == [] and not os.path.exists(tmp_path.parent / "ausbruch.txt")


def program_folder(root, version: str, extra: dict | None = None):
    files = {EXE: f"exe {version}", "_internal/kern.dll": f"kern {version}",
             f"_internal/nur_{version}.dll": version}
    files.update(extra or {})
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def tree(root) -> dict:
    return {str(path.relative_to(root)).replace("\\", "/"): path.read_text(encoding="utf-8")
            for path in sorted(root.rglob("*")) if path.is_file()}


def test_update_replaces_the_program_and_keeps_the_users_files(tmp_path):
    app_dir = program_folder(tmp_path / "programm", "alt", {"meine_plaene/plan.pap": "wichtig", "notiz.txt": "x"})
    new_dir = program_folder(app_dir / updater.STAGING_DIRECTORY / "neu", "neu")
    updater.apply_update(str(new_dir), str(app_dir))
    updater.cleanup_staging(str(app_dir))
    assert tree(app_dir) == {EXE: "exe neu", "_internal/kern.dll": "kern neu", "_internal/nur_neu.dll": "neu",
                             "meine_plaene/plan.pap": "wichtig", "notiz.txt": "x"}


def test_failed_update_restores_the_previous_version(tmp_path, monkeypatch):
    app_dir = program_folder(tmp_path / "programm", "alt", {"plan.pap": "wichtig"})
    new_dir = program_folder(tmp_path / "neu", "neu")
    before = tree(app_dir)

    def broken_copy(source, target, *args, **kwargs):
        os.makedirs(target)
        open(os.path.join(target, "halb.dll"), "w").close()
        raise OSError("Datenträger voll")

    monkeypatch.setattr(shutil, "copytree", broken_copy)
    with pytest.raises(updater.UpdateError) as failure:
        updater.apply_update(str(new_dir), str(app_dir))
    assert "bisherige Version bleibt erhalten" in failure.value.message
    assert tree(app_dir) == before
    # ein unvollständiges Paket wird gar nicht erst angefasst
    os.remove(new_dir / EXE)
    with pytest.raises(updater.UpdateError):
        updater.apply_update(str(new_dir), str(app_dir))
    assert tree(app_dir) == before


def test_locked_program_folder_is_left_untouched(tmp_path, monkeypatch):
    """Läuft das alte Programm noch (Dateien gesperrt), bleibt alles beim Alten."""
    app_dir = program_folder(tmp_path / "programm", "alt")
    new_dir = program_folder(tmp_path / "neu", "neu")
    before = tree(app_dir)

    def locked(source, target):
        raise PermissionError("in Benutzung")

    monkeypatch.setattr(os, "rename", locked)
    with pytest.raises(updater.UpdateError):
        updater.apply_update(str(new_dir), str(app_dir), retry_seconds=0.0)
    assert tree(app_dir) == before


def load_make_release():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_release", os.path.join(ROOT, "tools", "make_release.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_file_is_built_and_published_with_the_release(tmp_path, monkeypatch):
    import types
    make_release = load_make_release()
    dist = tmp_path / "dist"
    program_folder(dist / "BSTechnikPAPDesigner", "neu")
    monkeypatch.setattr(make_release, "DIST", str(dist))
    monkeypatch.setattr(make_release, "PROGRAM", str(dist / "BSTechnikPAPDesigner"))
    monkeypatch.setattr(make_release.sys, "argv", ["make_release.py", "--ohne-upload", "Setup dabei"])
    assert make_release.release_notes() == "Setup dabei"
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[0] == "ISCC.exe":
            (dist / config.SETUP_FILE_NAME).write_bytes(b"setup")
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(make_release.subprocess, "run", fake_run)
    # ohne Inno Setup geht es ohne Setup-Datei weiter
    monkeypatch.setattr(make_release, "find_inno_setup", lambda: None)
    assert make_release.build_setup() is None and calls == []
    # mit Inno Setup: Version, Quelle und Ziel werden vorgegeben
    monkeypatch.setattr(make_release, "find_inno_setup", lambda: "ISCC.exe")
    setup = make_release.build_setup()
    assert setup == str(dist / config.SETUP_FILE_NAME)
    assert f"/DAppVersion={config.APP_VERSION}" in calls[0] and f"/DOutputDir={dist}" in calls[0]
    assert os.path.isfile(calls[0][-1]) and calls[0][-1].endswith(".iss")
    # --ohne-upload: alles bauen, nichts hochladen
    assert make_release.main() == 0 and not any(command[0] == "gh" for command in calls)
    # hochgeladen werden Paket, Angaben und Setup-Datei
    monkeypatch.setattr(config, "UPDATE_REPOSITORY", "schule/pap")
    monkeypatch.setattr(make_release.shutil, "which", lambda name: "gh")
    assert make_release.publish("p.zip", "version.json", setup) == 0
    assert calls[-1][:7] == ["gh", "release", "create", f"v{config.APP_VERSION}", "p.zip", "version.json", setup]


def test_installer_script_installs_without_admin_rights_and_takes_its_version_from_the_build():
    path = os.path.join(ROOT, "installer", "BSTechnikPAPDesigner.iss")
    raw = open(path, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf")  # sonst liest Inno Setup die Umlaute falsch
    script = raw.decode("utf-8-sig")
    assert "PrivilegesRequired=lowest" in script  # Benutzerprofil: dort funktionieren die Updates
    assert f"OutputBaseFilename={os.path.splitext(config.SETUP_FILE_NAME)[0]}" in script
    assert f'#define AppExe "{config.EXECUTABLE_NAME}"' in script
    assert config.APP_VERSION not in script and "#ifndef AppVersion" in script  # Version kommt vom Bau
    assert f'#define ProgId "{config.FILE_PROG_ID}"' in script and f"Classes\\{config.FILE_EXTENSION}" in script
    assert os.path.isfile(os.path.join(ROOT, "assets", "file_icon.ico")) and r"_internal\assets\file_icon.ico" in script
    for author in config.APP_AUTHORS:
        assert author in script


def test_release_files_are_built_and_understood(tmp_path, monkeypatch):
    make_release = load_make_release()
    dist = tmp_path / "dist"
    program_folder(dist / "BSTechnikPAPDesigner", "neu")
    monkeypatch.setattr(make_release, "DIST", str(dist))
    monkeypatch.setattr(make_release, "PROGRAM", str(dist / "BSTechnikPAPDesigner"))
    monkeypatch.setattr(make_release.sys, "argv", ["make_release.py", "Fehler behoben"])
    package_path, manifest_path = make_release.build_package()
    data = open(package_path, "rb").read()
    info = updater.parse_manifest(open(manifest_path, "rb").read(), "schule/pap")
    assert info.version == config.APP_VERSION and info.released == config.APP_RELEASE_DATE
    assert info.notes == "Fehler behoben" and info.sha256 == hashlib.sha256(data).hexdigest()
    # genau dieses Paket lässt sich laden und installieren
    app_dir = program_folder(tmp_path / "programm", "alt")
    new_dir = updater.download_package(info, str(app_dir), opener=lambda url, timeout: FakeResponse(data))
    updater.apply_update(new_dir, str(app_dir))
    updater.cleanup_staging(str(app_dir))
    assert tree(app_dir) == tree(dist / "BSTechnikPAPDesigner")
    # ohne eingetragenes GitHub-Projekt wird nichts hochgeladen
    monkeypatch.setattr(config, "UPDATE_REPOSITORY", "")
    assert make_release.publish(package_path, manifest_path) == 1


def test_update_dialogs(window, qapp, monkeypatch):
    shown, asked, installed = [], [], []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, title, text, *a, **k: shown.append(text))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: shown.append(text))
    controller = window.updates
    monkeypatch.setattr(controller, "install_blocker", lambda: "")  # hier darf installiert werden
    monkeypatch.setattr(controller, "ask_install", lambda info: asked.append(info.version) or True)
    monkeypatch.setattr(controller, "install", lambda info: installed.append(info.version))
    newer = updater.UpdateInfo("99.0.0", "https://github.com/a/b/releases/download/v99.0.0/p.zip", "ab" * 32)
    same = updater.UpdateInfo(config.APP_VERSION, newer.package_url, "ab" * 32)
    error = updater.UpdateError("Es konnte keine Verbindung zum Update-Server hergestellt werden.")

    # beim Programmstart: still, solange es nichts Neues gibt
    for info, failure in ((None, None), (same, None), (None, error)):
        controller._on_checked(info, failure, False)
    assert shown == [] and asked == []
    controller._on_checked(newer, None, False)
    assert asked == ["99.0.0"] and installed == ["99.0.0"]

    # über das Menü: immer eine Auskunft
    controller._on_checked(None, None, True)
    controller._on_checked(same, None, True)
    controller._on_checked(None, error, True)
    assert "keine Update-Quelle" in shown[0] and "neuesten Stand" in shown[1] and "keine Verbindung" in shown[2]

    # die Prüfung selbst läuft im Hintergrund und meldet sich in der Oberfläche
    monkeypatch.setattr(updater, "fetch_update_info", lambda: newer)
    controller.check(manual=True)
    assert wait_until(qapp, lambda: len(asked) == 2) and installed == ["99.0.0", "99.0.0"]


def newer_version(**changes) -> updater.UpdateInfo:
    values = {"version": "99.0.0", "package_url": "https://github.com/a/b/releases/download/v99.0.0/p.zip",
              "sha256": "ab" * 32, "released": "Mai 2030", "notes": "Neu: alles"}
    values.update(changes)
    return updater.UpdateInfo(**values)


def test_write_protected_program_folder_gets_a_quiet_hint_instead_of_a_question(window, monkeypatch, tmp_path):
    """Für alle Benutzer installiert (z. B. in der Schule): Der Programmordner ist nicht beschreibbar."""
    monkeypatch.setattr(config, "UPDATE_REPOSITORY", "schule/pap")
    monkeypatch.setattr(updater, "application_directory", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "can_write", lambda directory: False)
    asked, installed, shown = [], [], []
    controller = window.updates
    monkeypatch.setattr(controller, "ask_install", lambda info: asked.append(info.version) or True)
    monkeypatch.setattr(controller, "install", lambda info: installed.append(info.version))
    monkeypatch.setattr(QMessageBox, "information", lambda _p, title, text, *a, **k: shown.append(text))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: shown.append(text))
    assert controller.install_blocker() == "rights"

    # beim Start: keine Frage, kein Fenster – nur ein Hinweis in der Statuszeile
    controller._on_checked(newer_version(), None, False)
    assert asked == [] and installed == [] and shown == []
    message = window.statusBar().currentMessage()
    assert "Neue Version 99.0.0 verfügbar" in message and "Administrator" in message

    # über das Menü: eine Auskunft mit dem Link zur Setup-Datei, ebenfalls ohne Frage
    controller._on_checked(newer_version(), None, True)
    assert asked == [] and installed == [] and len(shown) == 1
    text = shown[0]
    assert "99.0.0" in text and "Mai 2030" in text and config.APP_VERSION in text
    assert "Administrator" in text and "Neu: alles" in text
    assert f"https://github.com/schule/pap/releases/latest/download/{config.SETUP_FILE_NAME}" in text

    # nichts Neues: auch hier weder Hinweis noch Fenster
    window.statusBar().clearMessage()
    controller._on_checked(newer_version(version=config.APP_VERSION), None, False)
    assert window.statusBar().currentMessage() == "" and len(shown) == 1


def test_writable_program_folder_still_asks_before_updating(window, monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "application_directory", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "can_write", lambda directory: True)
    asked, installed = [], []
    controller = window.updates
    monkeypatch.setattr(controller, "ask_install", lambda info: asked.append(info.version) or True)
    monkeypatch.setattr(controller, "install", lambda info: installed.append(info.version))
    assert controller.install_blocker() == ""
    window.statusBar().clearMessage()
    controller._on_checked(newer_version(), None, False)
    assert asked == ["99.0.0"] and installed == ["99.0.0"]
    assert "Administrator" not in window.statusBar().currentMessage()


def test_install_blocker_reflects_the_real_folder(monkeypatch, tmp_path):
    from app.update_dialogs import UpdateController
    controller = UpdateController.__new__(UpdateController)  # ohne Fenster: nur die Prüfung
    assert controller.install_blocker() == "source"  # die Tests laufen aus dem Quelltext
    monkeypatch.setattr(updater, "application_directory", lambda: str(tmp_path))
    assert controller.install_blocker() == ""  # echter, beschreibbarer Ordner
    assert not list(tmp_path.iterdir())  # die Prüfung hinterlässt nichts
    monkeypatch.setattr(updater, "application_directory", lambda: str(tmp_path / "gibt_es_nicht"))
    assert controller.install_blocker() == "rights"  # nicht beschreibbar (hier: nicht vorhanden)


def test_update_is_only_installed_in_the_finished_program(window, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, title, text, *a, **k: shown.append(text))
    assert updater.application_directory() is None  # die Tests laufen aus dem Quelltext
    window.updates.install(updater.UpdateInfo("99.0.0", "https://github.com/a/b/x.zip", "ab" * 32))
    assert len(shown) == 1 and "nur im fertigen Programm" in shown[0]
