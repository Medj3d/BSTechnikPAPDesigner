"""Tests für die Linux-Version: Ordner, Vorgaben des Administrators, Dateizuordnung, AppImage-Update.

Die meisten Tests laufen auf jedem System (das Betriebssystem wird dafür vorgetäuscht); was nur unter Linux
geht (Dateirechte, echtes Ausführen), ist entsprechend markiert.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys

import pytest

from app import config, file_association, file_association_linux as linux, platforms, policy, resources, restart, updater

ON_LINUX = sys.platform.startswith("linux")
ELF = b"\x7fELF" + b"\0" * 60 + b"neues AppImage"


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


@pytest.fixture
def as_linux(monkeypatch):
    monkeypatch.setattr(platforms, "current", lambda: platforms.LINUX)


@pytest.fixture
def appimage(tmp_path, monkeypatch, as_linux):
    """Das Programm läuft als AppImage aus ``tmp_path/apps``."""
    folder = tmp_path / "apps"
    folder.mkdir()
    path = folder / "BSTechnikPAPDesigner-x86_64.AppImage"
    path.write_bytes(b"\x7fELF altes AppImage")
    real_base = resources.base_directory()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(resources, "base_directory", lambda: real_base)  # Symbole usw. weiter aus dem Projekt
    monkeypatch.setenv("APPIMAGE", str(path))
    return path


# ------------------------------------------------------------------ Plattform
def test_current_platform_is_detected():
    expected = "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"
    assert platforms.current() == expected
    assert [platforms.is_windows(), platforms.is_linux(), platforms.is_macos()].count(True) == 1


def test_release_files_are_separate_per_system():
    # Installierte Windows-Programme lesen weiter version.json – die Linux-Version hat eigene Dateien
    assert config.WINDOWS_MANIFEST_NAME == "version.json"
    assert config.WINDOWS_PACKAGE_NAME == "BSTechnikPAPDesigner.zip"
    assert config.LINUX_MANIFEST_NAME != config.WINDOWS_MANIFEST_NAME
    assert config.LINUX_PACKAGE_NAME.endswith(".AppImage")
    if platforms.is_windows():
        assert config.UPDATE_MANIFEST_NAME == "version.json" and config.EXECUTABLE_NAME.endswith(".exe")
        assert config.DOWNLOAD_FILE_NAME == config.SETUP_FILE_NAME
    elif platforms.is_linux():
        assert config.UPDATE_MANIFEST_NAME == config.LINUX_MANIFEST_NAME
        assert config.UPDATE_PACKAGE_NAME == config.LINUX_PACKAGE_NAME
        assert config.EXECUTABLE_NAME == "BSTechnikPAPDesigner"
        assert config.DOWNLOAD_FILE_NAME == config.LINUX_PACKAGE_NAME


def test_linux_data_folder_follows_xdg(as_linux, monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "_generic_data_location", lambda: str(tmp_path / "share"))
    assert platforms.user_data_directory() == os.path.join(str(tmp_path / "share"), "BSTechnik", config.SETTINGS_APP_NAME)
    from app import autosave, errors
    assert errors.log_directory() == os.path.join(platforms.user_data_directory(), "logs")
    assert autosave.default_directory() == os.path.join(platforms.user_data_directory(), "autosave")
    assert os.path.dirname(updater.user_update_root()) == platforms.user_data_directory()


def test_windows_data_folder_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "current", lambda: platforms.WINDOWS)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert platforms.user_data_directory() == os.path.join(str(tmp_path), "BSTechnik", config.SETTINGS_APP_NAME)


@pytest.mark.skipif(not ON_LINUX, reason="QStandardPaths liest XDG_DATA_HOME nur unter Linux")
def test_generic_data_location_reads_xdg_data_home(monkeypatch, tmp_path):
    from PySide6.QtCore import QStandardPaths
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    assert os.path.realpath(location) == os.path.realpath(str(tmp_path))


def test_documents_folder_exists():
    assert os.path.isdir(platforms.documents_directory())


def test_appimage_is_what_gets_restarted(appimage, monkeypatch):
    assert platforms.appimage_path() == str(appimage)
    assert platforms.launch_executable() == str(appimage)
    monkeypatch.setattr(restart.resources, "is_frozen", lambda: True)
    assert restart.command(["a.pap"], pid=7)[0] == str(appimage)
    # ohne AppImage (oder unter Windows) bleibt es die Programmdatei selbst
    monkeypatch.delenv("APPIMAGE")
    assert platforms.appimage_path() is None and platforms.launch_executable() == sys.executable


def test_appimage_only_counts_in_the_finished_program(as_linux, monkeypatch, tmp_path):
    path = tmp_path / "x.AppImage"
    path.write_bytes(b"x")
    monkeypatch.setenv("APPIMAGE", str(path))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert platforms.appimage_path() is None  # aus dem Quelltext: kein AppImage, auch wenn die Variable gesetzt ist


def test_host_programs_get_the_original_library_path(as_linux, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    env = platforms.host_environment({"LD_LIBRARY_PATH": "/tmp/_MEIxyz", "LD_LIBRARY_PATH_ORIG": "/opt/lib",
                                      "QT_PLUGIN_PATH": "/tmp/_MEIxyz/plugins", "PATH": "/usr/bin"})
    assert env == {"LD_LIBRARY_PATH": "/opt/lib", "PATH": "/usr/bin"}
    env = platforms.host_environment({"LD_LIBRARY_PATH": "/tmp/_MEIxyz", "PATH": "/usr/bin"})
    assert env == {"PATH": "/usr/bin"}
    # aus dem Quelltext bleibt alles, wie es ist
    monkeypatch.delattr(sys, "frozen")
    assert platforms.host_environment({"LD_LIBRARY_PATH": "/x"}) == {"LD_LIBRARY_PATH": "/x"}


# ------------------------------------------------------------------ Vorgaben
def test_policy_file_in_etc_disables_updates_for_everyone(as_linux, monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_registry_value", lambda name: None)
    etc = tmp_path / "etc-bstechnik-pap"
    etc.mkdir()
    monkeypatch.setattr(platforms, "LINUX_POLICY_DIRECTORY", str(etc))
    monkeypatch.setattr(policy, "program_directory", lambda: None)
    monkeypatch.delenv(policy.INSTALLATION_ENV, raising=False)
    assert str(etc) in policy.policy_directories()
    assert not policy.updates_disabled()
    (etc / policy.POLICY_FILE_NAME).write_text("[Updates]\nDisabled=1\n", encoding="utf-8")
    assert policy.updates_disabled()


def test_default_linux_policy_folder():
    assert platforms.LINUX_POLICY_DIRECTORY == "/etc/bstechnik-pap"


def test_policy_file_next_to_the_appimage(appimage, monkeypatch):
    monkeypatch.setattr(policy, "_registry_value", lambda name: None)
    assert policy.program_directory() == str(appimage.parent)
    (appimage.parent / policy.POLICY_FILE_NAME).write_text("[Updates]\nDisabled=ja\n", encoding="utf-8")
    assert policy.updates_disabled()


def test_windows_has_no_policy_folder(monkeypatch):
    monkeypatch.setattr(platforms, "current", lambda: platforms.WINDOWS)
    assert platforms.system_policy_directories() == []


# ------------------------------------------------------------ Dateizuordnung
@pytest.mark.parametrize("argument, expected", [
    ("/opt/apps/PAP.AppImage", "/opt/apps/PAP.AppImage"),
    ("/home/anna/Mein Programm/PAP.AppImage", '"/home/anna/Mein Programm/PAP.AppImage"'),
    ("/home/a/100%.AppImage", "/home/a/100%%.AppImage"),
    ('/x/"$`\\.AppImage', '"/x/\\\\"\\\\$\\\\`\\\\\\\\.AppImage"'),
])
def test_exec_arguments_are_quoted_for_desktop_files(argument, expected):
    assert linux.exec_argument(argument) == expected


def test_desktop_entry_starts_the_appimage_with_files():
    entry = linux.desktop_entry(["/home/anna/Mein Programm/PAP.AppImage"])
    lines = entry.splitlines()
    assert lines[0] == "[Desktop Entry]"
    assert 'Exec="/home/anna/Mein Programm/PAP.AppImage" %F' in lines
    assert f"MimeType={config.LINUX_MIME_TYPE};" in lines and f"Icon={config.LINUX_DESKTOP_ID}" in lines
    assert f"Name={config.APP_NAME}" in lines and "Terminal=false" in lines
    assert entry.endswith("\n") and "\n\n" not in entry


def test_mime_definition_maps_pap_files():
    from xml.dom import minidom
    text = linux.mime_definition()
    assert f'type="{config.LINUX_MIME_TYPE}"' in text and 'pattern="*.pap"' in text
    assert minidom.parseString(text.encode("utf-8")).documentElement.tagName == "mime-info"


def test_register_writes_desktop_entry_mime_type_icons_and_default(tmp_path):
    data, conf = tmp_path / "share", tmp_path / "config"
    conf.mkdir()
    (conf / "mimeapps.list").write_text("[Default Applications]\ntext/plain=gedit.desktop;\n\n"
                                        "[Added Associations]\nimage/png=gimp.desktop;\n", encoding="utf-8")
    program = ["/opt/PAP.AppImage"]
    assert linux.register(program, str(data), str(conf), run_tools=False)
    where = linux.paths(str(data), str(conf))
    for key in ("desktop", "mime", "app_icon", "mime_icon"):
        assert os.path.isfile(where[key]), key
    assert where["desktop"].endswith(os.path.join("applications", "bstechnik-papdesigner.desktop"))
    assert where["mime_icon"].endswith(os.path.join("mimetypes", "application-x-bstechnik-pap.png"))
    mimeapps = (conf / "mimeapps.list").read_text(encoding="utf-8")
    assert mimeapps == ("[Default Applications]\napplication/x-bstechnik-pap=bstechnik-papdesigner.desktop;\n"
                        "text/plain=gedit.desktop;\n\n[Added Associations]\nimage/png=gimp.desktop;\n")
    assert not linux.needs_installation(program, str(data))
    # ein zweites Mal ändert nichts
    assert not linux.register(program, str(data), str(conf), run_tools=False)
    assert (conf / "mimeapps.list").read_text(encoding="utf-8") == mimeapps
    # nach dem Verschieben des AppImage zeigt die Verknüpfung auf die alte Stelle: neu einrichten
    assert linux.needs_installation(["/anderswo/PAP.AppImage"], str(data))
    # Entfernen räumt alles weg, die fremden Einträge bleiben
    linux.unregister(str(data), str(conf), run_tools=False)
    assert not any(os.path.exists(where[key]) for key in ("desktop", "mime", "app_icon", "mime_icon"))
    assert (conf / "mimeapps.list").read_text(encoding="utf-8") == (
        "[Default Applications]\ntext/plain=gedit.desktop;\n\n[Added Associations]\nimage/png=gimp.desktop;\n")


def test_default_application_replaces_another_program(tmp_path):
    mimeapps = tmp_path / "mimeapps.list"
    mimeapps.write_text("[Default Applications]\napplication/x-bstechnik-pap=anderes.desktop;\n", encoding="utf-8")
    linux.set_default_application(str(mimeapps))
    assert mimeapps.read_text(encoding="utf-8") == (
        "[Default Applications]\napplication/x-bstechnik-pap=bstechnik-papdesigner.desktop;\n")
    # ohne Datei: wird angelegt
    fresh = tmp_path / "neu" / "mimeapps.list"
    linux.set_default_application(str(fresh))
    assert fresh.read_text(encoding="utf-8") == (
        "[Default Applications]\napplication/x-bstechnik-pap=bstechnik-papdesigner.desktop;\n")
    # Entfernen ohne Abschnitt ändert nichts
    other = tmp_path / "andere.list"
    other.write_text("[Added Associations]\n", encoding="utf-8")
    linux.set_default_application(str(other), remove=True)
    assert other.read_text(encoding="utf-8") == "[Added Associations]\n"


def test_register_dispatches_by_system(as_linux, monkeypatch):
    calls = []
    monkeypatch.setattr(linux, "register", lambda: calls.append("linux"))
    monkeypatch.setattr(file_association, "register_windows", lambda: calls.append("windows"))
    assert file_association.is_supported()
    file_association.register()
    monkeypatch.setattr(platforms, "current", lambda: platforms.WINDOWS)
    file_association.register()
    assert calls == ["linux", "windows"]
    monkeypatch.setattr(platforms, "current", lambda: platforms.MACOS)
    assert not file_association.is_supported() and file_association.ensure_installed() is False


def test_appimage_sets_up_the_association_once_on_start(appimage, monkeypatch, tmp_path):
    monkeypatch.setattr(linux, "_refresh", lambda where: None)
    assert file_association.ensure_installed() is True
    import threading
    for thread in threading.enumerate():
        if thread.name == "desktop-integration":
            thread.join(10)
    desktop = linux.paths()["desktop"]
    assert os.path.isfile(desktop)
    assert linux.exec_argument(str(appimage)) in open(desktop, encoding="utf-8").read()
    assert file_association.ensure_installed() is False  # schon eingerichtet: nichts zu tun


def test_without_appimage_nothing_is_set_up_on_start(as_linux):
    assert file_association.ensure_installed() is False


def test_missing_system_tools_are_skipped(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda name, path=None: None)
    linux._run_tool("update-mime-database", "/nirgends")  # kein Fehler


# ------------------------------------------------------------------ Updates
def test_linux_manifest_points_to_the_appimage():
    data = {"version": "9.9.9", "tag": "v9.9.9", "file": config.LINUX_PACKAGE_NAME, "sha256": "ab" * 32}
    info = updater.parse_manifest(json.dumps(data).encode(), "schule/pap")
    assert info.package_url.endswith("/v9.9.9/" + config.LINUX_PACKAGE_NAME)
    for bad in ("programm.exe", "x.AppImage.sh", "../x.AppImage", "x.appimage.zip.exe"):
        with pytest.raises(updater.UpdateError):
            updater.parse_manifest(json.dumps(dict(data, file=bad)).encode(), "schule/pap")


def test_update_check_reads_the_manifest_of_this_system(monkeypatch):
    urls = []
    monkeypatch.setattr(config, "UPDATE_REPOSITORY", "schule/pap")
    data = {"version": "9.9.9", "file": config.UPDATE_PACKAGE_NAME, "sha256": "ab" * 32}
    updater.fetch_update_info(opener=lambda url, timeout: urls.append(url) or FakeResponse(json.dumps(data).encode()))
    assert urls == [f"https://github.com/schule/pap/releases/latest/download/{config.UPDATE_MANIFEST_NAME}"]


def test_update_mode_for_the_appimage(appimage, monkeypatch):
    monkeypatch.setattr(updater, "application_directory", lambda: "/tmp/.mount_xyz")
    assert updater.update_mode() == "appimage"
    monkeypatch.setattr(updater, "can_write", lambda directory: False)
    assert updater.update_mode() == "blocked"  # Ordner des AppImage schreibgeschützt: nur ein Hinweis
    monkeypatch.delenv("APPIMAGE")
    monkeypatch.setattr(updater, "can_write", lambda directory: True)
    assert updater.update_mode() == "blocked"  # entpackter Programmordner ohne AppImage: kein Selbst-Update


def test_new_appimage_is_downloaded_checked_and_swapped_in(appimage):
    info = updater.UpdateInfo("9.9.9", "https://github.com/a/b/releases/download/v9.9.9/x.AppImage",
                              hashlib.sha256(ELF).hexdigest(), size=len(ELF))
    progress = []
    new_file = updater.download_appimage(info, str(appimage), progress=lambda d, t: progress.append((d, t)),
                                         opener=lambda url, timeout: FakeResponse(ELF))
    assert new_file == updater.appimage_download_path(str(appimage))
    assert os.path.dirname(new_file) == str(appimage.parent) and os.path.basename(new_file).startswith(".")
    assert progress[-1] == (len(ELF), len(ELF))
    assert appimage.read_bytes() == b"\x7fELF altes AppImage"  # noch nichts ersetzt
    updater.replace_appimage(new_file, str(appimage))
    assert appimage.read_bytes() == ELF and not os.path.exists(new_file)
    if ON_LINUX:
        assert os.stat(appimage).st_mode & stat.S_IXUSR


def test_broken_appimage_download_changes_nothing(appimage):
    good = updater.UpdateInfo("9.9.9", "https://x/y.AppImage", hashlib.sha256(ELF).hexdigest())
    with pytest.raises(updater.UpdateError):  # Prüfsumme stimmt nicht
        updater.download_appimage(good, str(appimage), opener=lambda url, timeout: FakeResponse(ELF + b"!"))
    not_elf = b"<html>Fehlerseite</html>"
    with pytest.raises(updater.UpdateError):  # kein Programm
        updater.download_appimage(updater.UpdateInfo("9.9.9", "https://x/y.AppImage",
                                                     hashlib.sha256(not_elf).hexdigest()),
                                  str(appimage), opener=lambda url, timeout: FakeResponse(not_elf))
    with pytest.raises(updater.UpdateCancelled):
        updater.download_appimage(good, str(appimage), cancelled=lambda: True,
                                  opener=lambda url, timeout: FakeResponse(ELF))
    assert sorted(os.listdir(appimage.parent)) == [appimage.name]
    assert appimage.read_bytes() == b"\x7fELF altes AppImage"


def test_failed_swap_keeps_the_old_appimage(appimage, monkeypatch, tmp_path):
    new_file = updater.appimage_download_path(str(appimage))
    with open(new_file, "wb") as handle:
        handle.write(ELF)

    def failing(source, target):
        raise PermissionError("schreibgeschützt")

    monkeypatch.setattr(updater.os, "replace", failing)
    with pytest.raises(updater.UpdateError):
        updater.replace_appimage(new_file, str(appimage))
    assert appimage.read_bytes() == b"\x7fELF altes AppImage" and not os.path.exists(new_file)


def test_leftover_download_is_cleaned_up(appimage):
    leftover = updater.appimage_download_path(str(appimage))
    open(leftover, "wb").close()
    updater.cleanup_appimage_download()
    assert not os.path.exists(leftover)


def test_new_appimage_starts_with_the_original_environment(appimage, monkeypatch):
    started = []
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    monkeypatch.setattr(updater.subprocess, "Popen", lambda command, **kwargs: started.append((command, kwargs)))
    updater.launch_appimage(str(appimage), wait_pid=4711)
    (command, kwargs), = started
    assert command == [str(appimage), config.WAIT_FOR_FLAG, "4711"]
    assert kwargs["env"]["LD_LIBRARY_PATH"] == "/usr/local/lib" and kwargs["start_new_session"]


@pytest.fixture
def window(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=False)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


def test_update_dialog_replaces_the_appimage_and_restarts(window, qapp, appimage, monkeypatch):
    import time
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QMessageBox
    from app import update_dialogs

    shown, closed, launched = [], [], []
    monkeypatch.setattr(update_dialogs, "QProgressDialog", lambda *a, **k: MagicMock())
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: shown.append(text))
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(updater.resources, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "application_directory", lambda: "/tmp/.mount_xyz")
    controller = window.updates
    monkeypatch.setattr(controller, "_launch_appimage_after_quit", lambda path: launched.append(path))
    info = updater.UpdateInfo("99.0.0", "https://github.com/a/b/releases/download/v99.0.0/x.AppImage",
                              hashlib.sha256(ELF).hexdigest())
    real_download = updater.download_appimage
    monkeypatch.setattr(updater, "download_appimage", lambda info, path, **kw: real_download(
        info, path, opener=lambda url, timeout: FakeResponse(ELF), **kw))
    controller.install(info)
    deadline = time.monotonic() + 5
    while not (launched and closed) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert shown == [] and launched == [str(appimage)] and closed == [True]
    assert appimage.read_bytes() == ELF  # die AppImage-Datei ist ersetzt
