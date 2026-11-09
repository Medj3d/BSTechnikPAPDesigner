"""Unterschiede zwischen den Betriebssystemen an einer Stelle.

Alles, was unter Windows, Linux (und später macOS) verschieden ist – Ordner für Protokolle und Sicherungen, wie
sich das Programm selbst neu startet, wo der Administrator Vorgaben ablegt –, fragen die übrigen Module hier ab.
Eine neue Plattform braucht dann nur hier und in den Modulen mit eigenem Ablauf (Dateizuordnung, Updater) einen
weiteren Zweig.

* **Windows**: Daten unter ``%LOCALAPPDATA%\\BSTechnik\\PAPDesigner``, Einstellungen in der Registry.
* **Linux**: Daten unter ``~/.local/share/BSTechnik/PAPDesigner`` (``$XDG_DATA_HOME``), Einstellungen in
  ``~/.config/BS Technik/PAPDesigner.conf``. Das fertige Programm ist ein AppImage: eine einzige Datei
  (``$APPIMAGE``), die beim Start eingehängt wird – neu starten, verknüpfen und ersetzen muss man deshalb diese
  Datei und nicht ``sys.executable`` (das liegt im eingehängten, nur vorübergehend vorhandenen Ordner).
* **macOS** (noch nicht gebaut): Daten unter ``~/Library/Application Support/BSTechnik/PAPDesigner``.
"""

from __future__ import annotations

import os
import sys

WINDOWS = "windows"
LINUX = "linux"
MACOS = "macos"

# Hier legt der Administrator unter Linux eine ``policy.ini`` für alle Benutzer ab (siehe ``app/policy.py``)
LINUX_POLICY_DIRECTORY = "/etc/bstechnik-pap"
MACOS_POLICY_DIRECTORY = "/Library/Application Support/BSTechnik/PAPDesigner"


def current() -> str:
    """Das Betriebssystem, auf dem das Programm läuft: ``windows``, ``linux`` oder ``macos``."""
    if sys.platform.startswith("win"):
        return WINDOWS
    if sys.platform == "darwin":
        return MACOS
    return LINUX


def is_windows() -> bool:
    return current() == WINDOWS


def is_linux() -> bool:
    return current() == LINUX


def is_macos() -> bool:
    return current() == MACOS


# ---------------------------------------------------------------- Ordner
def _folder_name() -> str:
    from app import config

    return os.path.join(config.ORGANIZATION_NAME.replace(" ", ""), config.SETTINGS_APP_NAME)


def _generic_data_location() -> str:
    """``~/.local/share`` (bzw. ``$XDG_DATA_HOME``) unter Linux, ``~/Library/Application Support`` unter macOS."""
    try:
        from PySide6.QtCore import QStandardPaths

        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
        if location:
            return location
    except ImportError:  # pragma: no cover - Qt fehlt nie, nur Absicherung
        pass
    if is_macos():
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def user_data_directory() -> str:
    """Eigener Ordner des Programms für Protokolle, Sicherungskopien und Updates (nicht die Einstellungen)."""
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, _folder_name())
    return os.path.join(_generic_data_location(), _folder_name())


def documents_directory() -> str:
    """Der Ordner „Dokumente“ des Benutzers (unter Linux z. B. ``~/Dokumente``); sonst der Benutzerordner."""
    home = os.path.expanduser("~")
    if not is_windows():
        try:
            from PySide6.QtCore import QStandardPaths

            location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            if location and os.path.isdir(location):
                return location
        except ImportError:  # pragma: no cover
            pass
    documents = os.path.join(home, "Documents")
    return documents if os.path.isdir(documents) else home


def system_policy_directories() -> list[str]:
    """Ordner mit Vorgaben des Administrators für alle Benutzer (unter Windows steht das in der Registry)."""
    if is_linux():
        return [LINUX_POLICY_DIRECTORY]
    if is_macos():
        return [MACOS_POLICY_DIRECTORY]
    return []


# ---------------------------------------------------------------- AppImage
def appimage_path() -> str | None:
    """Pfad der laufenden AppImage-Datei – oder ``None``, wenn das Programm nicht als AppImage läuft."""
    if not is_linux() or not getattr(sys, "frozen", False):
        return None
    path = os.environ.get("APPIMAGE")
    return os.path.abspath(path) if path and os.path.isfile(path) else None


# ---------------------------------------------------------------- Programm starten
def launch_executable() -> str:
    """Die Datei, mit der man dieses Programm erneut startet.

    Im AppImage die AppImage-Datei selbst: ``sys.executable`` liegt dort im eingehängten Ordner, der mit dem
    Programm verschwindet. Sonst ``sys.executable`` (die exe bzw. beim Quelltext der Python-Interpreter).
    """
    return appimage_path() or sys.executable


def host_environment(environment: dict | None = None) -> dict:
    """Umgebung für Programme des Systems (``xdg-mime``, ein neu gestartetes AppImage …).

    Das gebündelte Programm (PyInstaller) setzt unter Linux ``LD_LIBRARY_PATH`` auf seine eigenen Bibliotheken;
    fremde Programme würden damit die falschen laden. Der ursprüngliche Wert steht in ``…_ORIG``.
    """
    env = dict(os.environ if environment is None else environment)
    if is_windows() or not getattr(sys, "frozen", False):
        return env
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        original = env.pop(name + "_ORIG", None)
        if original is not None:
            env[name] = original
        else:
            env.pop(name, None)
    return env
