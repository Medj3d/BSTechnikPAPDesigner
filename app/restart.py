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

from app import config, platforms, resources

log = logging.getLogger(__name__)

MAIN_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))


def command(files: list[str] | tuple[str, ...] = (), pid: int | None = None, language: str | None = None) -> list[str]:
    """Die Befehlszeile für den Neustart: dieselbe Programmdatei (beim AppImage die AppImage-Datei) bzw.
    ``main.py``, wartet auf ``pid``."""
    program = [platforms.launch_executable()] if resources.is_frozen() else [sys.executable, MAIN_SCRIPT]
    arguments = [config.WAIT_FOR_FLAG, str(pid if pid is not None else os.getpid())]
    if language:
        arguments += [config.LANGUAGE_FLAG, language]
    return program + arguments + [str(path) for path in files]


def launch_now(files: list[str] | tuple[str, ...] = ()) -> None:
    """Startet das Programm sofort neu; der neue Start wartet, bis dieses beendet ist."""
    try:
        subprocess.Popen(command(files), close_fds=True, env=platforms.host_environment())
    except OSError:
        log.exception("Das Programm konnte nicht neu gestartet werden")


def launch_after_quit(application, files: list[str] | tuple[str, ...] = ()) -> None:
    """Startet das Programm neu, sobald dieses beendet ist.

    Auch Dateien, die ein weiterer Programmstart übergeben hat und die noch nicht geöffnet sind, öffnet der
    Neustart (siehe ``app.single_instance.take_pending``)."""
    from app import single_instance

    single_instance.plan_restart()

    def start() -> None:
        pending = [path for path in single_instance.take_pending() if path not in files]
        launch_now(list(files) + pending)

    application.aboutToQuit.connect(start)
