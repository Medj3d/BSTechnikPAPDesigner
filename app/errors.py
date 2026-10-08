"""Fehlerbehandlung und Protokollierung.

Unerwartete Fehler werden in eine Logdatei geschrieben und dem Benutzer als
verständliche Meldung angezeigt – nie als Traceback in der normalen
Oberfläche. Technische Details sind nur über „Details anzeigen“ sichtbar.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from app import config
from app.i18n import tr

_log_path: str | None = None
_shown_messages: set[str] = set()
_in_handler = False


def log_directory() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, config.ORGANIZATION_NAME.replace(" ", ""), config.SETTINGS_APP_NAME, "logs")


def setup_logging() -> str | None:
    global _log_path
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    try:
        directory = log_directory()
        os.makedirs(directory, exist_ok=True)
        _log_path = os.path.join(directory, "pap_designer.log")
        handler = RotatingFileHandler(_log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    except OSError:
        _log_path = None
    return _log_path


def log_path() -> str | None:
    return _log_path


def install_exception_hook() -> None:
    sys.excepthook = _handle_exception


def _handle_exception(exc_type, exc_value, exc_tb) -> None:
    global _in_handler
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.getLogger("app").error("Unerwarteter Fehler:\n%s", details)
    if _in_handler:
        return
    key = f"{exc_type.__name__}:{exc_value}"
    if key in _shown_messages:
        return
    _shown_messages.add(key)
    _in_handler = True
    try:
        show_unexpected_error(details)
    finally:
        _in_handler = False


def show_unexpected_error(details: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return
    if QApplication.instance() is None:
        return
    box = QMessageBox(QApplication.activeWindow())
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(config.APP_NAME)
    box.setText(tr("Es ist ein unerwarteter Fehler aufgetreten."))
    info = tr("Die letzte Aktion konnte möglicherweise nicht vollständig ausgeführt werden. "
              "Bitte speichern Sie Ihre Arbeit gegebenenfalls unter einem neuen Namen.")
    if _log_path:
        info += "\n\n" + tr("Ein Fehlerprotokoll wurde gespeichert:\n{path}", path=_log_path)
    box.setInformativeText(info)
    box.setDetailedText(details)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()
