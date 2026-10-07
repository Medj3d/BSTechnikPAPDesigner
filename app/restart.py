"""Das Programm neu starten (z. B. nach einem Sprachwechsel), ohne dass Dateien oder Fenster verloren gehen.

Der neue Start wartet mit ``--warte-auf``, bis sich das alte Programm beendet hat, und öffnet die übergebenen
Projektdateien wieder. Gestartet wird erst, wenn das Programm wirklich endet (``aboutToQuit``) – bricht der
Benutzer das Schließen ab, bleibt alles wie es ist.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from app import config, resources

log = logging.getLogger(__name__)

MAIN_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))


def command(files: list[str] | tuple[str, ...] = (), pid: int | None = None, language: str | None = None) -> list[str]:
    """Die Befehlszeile für den Neustart: dieselbe Programmdatei bzw. ``main.py``, wartet auf ``pid``."""
    program = [sys.executable] if resources.is_frozen() else [sys.executable, MAIN_SCRIPT]
    arguments = [config.WAIT_FOR_FLAG, str(pid if pid is not None else os.getpid())]
    if language:
        arguments += [config.LANGUAGE_FLAG, language]
    return program + arguments + [str(path) for path in files]


def launch_after_quit(application, files: list[str] | tuple[str, ...] = ()) -> None:
    """Startet das Programm neu, sobald dieses beendet ist."""
    def start() -> None:
        try:
            subprocess.Popen(command(files), close_fds=True)
        except OSError:
            log.exception("Das Programm konnte nicht neu gestartet werden")

    application.aboutToQuit.connect(start)
