"""Vorgaben des Administrators für den Schulbetrieb.

Damit in einem Schulnetz alle Rechner dieselbe Version behalten (etwa während
einer Prüfungsphase) und das Programm nicht bei jedem Start bei GitHub
nachfragt, lassen sich die Updates zentral abschalten – auf einem dieser Wege:

* Registry (Gruppenrichtlinie, Softwareverteilung oder Setup mit
  ``/NOUPDATES``): ``HKEY_LOCAL_MACHINE\\Software\\Policies\\BSTechnik\\PAPDesigner``
  (oder dasselbe unter ``HKEY_CURRENT_USER``), DWORD ``DisableUpdates`` = 1
* Datei ``policy.ini`` im Programmordner (neben ``BSTechnikPAPDesigner.exe``)::

      [Updates]
      Disabled=1

Abgeschaltet heißt: keine Prüfung beim Start, „Nach Updates suchen“ und der
Schalter dafür sind gesperrt, und das Programm gibt beim Start auch nicht an
eine schon früher in den Benutzerordner geladene neuere Version ab.
Benutzer selbst können die Prüfung beim Start nur für sich abschalten
(Hilfe → „Beim Start nach Updates suchen“).
"""

from __future__ import annotations

import configparser
import os
import sys

POLICY_KEY = r"Software\Policies\BSTechnik\PAPDesigner"
DISABLE_UPDATES_VALUE = "DisableUpdates"
POLICY_FILE_NAME = "policy.ini"
# Ordner der installierten Version: gibt sie beim Start an eine neuere Kopie im Benutzerordner ab
# (app/updater.py), erfährt die Kopie darüber, wo die policy.ini des Administrators liegt.
INSTALLATION_ENV = "BSTECHNIK_PAP_INSTALLATION"


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "ja", "on")


def _registry_value(name: str):
    """Wert der Richtlinie (zuerst für den Rechner, dann für den Benutzer) – oder ``None``."""
    if not sys.platform.startswith("win"):
        return None
    import winreg

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, POLICY_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, name)
                return value
        except OSError:
            continue
    return None


def _policy_file(directory: str | None) -> configparser.ConfigParser | None:
    if not directory:
        return None
    path = os.path.join(directory, POLICY_FILE_NAME)
    if not os.path.isfile(path):
        return None
    parser = configparser.ConfigParser()
    try:
        # utf-8-sig: auch mit dem Windows-Editor gespeicherte Dateien (mit Kennung am Anfang)
        parser.read(path, encoding="utf-8-sig")
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None
    return parser


def program_directory() -> str | None:
    """Ordner des fertigen Programms (dort liegt ``policy.ini``); ``None`` beim Start aus dem Quelltext."""
    return os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else None


def policy_directories() -> list[str]:
    """Ordner, in denen eine ``policy.ini`` gilt: der eigene Programmordner und – bei einer Kopie im
    Benutzerordner – der Ordner der installierten Version, die an sie abgegeben hat."""
    folders = [program_directory(), os.environ.get(INSTALLATION_ENV)]
    return list(dict.fromkeys(folder for folder in folders if folder))


def updates_disabled(directory: str | None = None) -> bool:
    """Hat der Administrator die Updates abgeschaltet?

    ``directory``: Ordner mit ``policy.ini`` (ohne Angabe die Ordner aus ``policy_directories``).
    """
    value = _registry_value(DISABLE_UPDATES_VALUE)
    if value is not None and _truthy(value):
        return True
    for folder in ([directory] if directory else policy_directories()):
        parser = _policy_file(folder)
        if parser is not None and _truthy(parser.get("Updates", "Disabled", fallback="0")):
            return True
    return False
