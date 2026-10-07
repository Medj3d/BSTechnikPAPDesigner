"""Oberfläche der Update-Funktion: Prüfen im Hintergrund, Nachfrage, Laden mit Fortschritt."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from app import config, updater

log = logging.getLogger(__name__)


class UpdateController(QObject):
    """Verbindet die Abläufe aus ``app.updater`` mit dem Hauptfenster.

    Netzwerkzugriffe laufen in einem eigenen Thread; die Ergebnisse kommen als
    Signal im Thread der Oberfläche an.
    """

    _checked = Signal(object, object, bool)   # UpdateInfo | None, UpdateError | None, von Hand ausgelöst
    _progress = Signal(int, int)
    _downloaded = Signal(object, object)      # Ordner der neuen Version | None, Fehler | None

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._checking = False
        self._cancel = threading.Event()
        self._dialog: QProgressDialog | None = None
        self._checked.connect(self._on_checked)
        self._progress.connect(self._on_progress)
        self._downloaded.connect(self._on_downloaded)

    def cleanup_leftovers(self) -> None:
        """Entfernt Reste eines früheren Updates (nicht, während gerade eines geladen wird)."""
        app_dir = updater.application_directory()
        if app_dir is not None and self._dialog is None:
            updater.cleanup_staging(app_dir)

    # ------------------------------------------------------------- Prüfen
    def check(self, manual: bool = False) -> None:
        """Prüft im Hintergrund auf eine neue Version. ``manual``: über das Menü ausgelöst."""
        if self._checking:
            return
        self._checking = True

        def work():
            info, error = None, None
            try:
                info = updater.fetch_update_info()
            except updater.UpdateError as exc:
                error = exc
            except Exception as exc:  # pragma: no cover - Absicherung
                error = updater.UpdateError("Die Update-Prüfung ist fehlgeschlagen.", repr(exc))
            self._checked.emit(info, error, manual)

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _on_checked(self, info, error, manual: bool) -> None:
        self._checking = False
        if error is not None:
            log.info("Update-Prüfung: %s (%s)", error.message, error.details)
            if manual:
                QMessageBox.warning(self._window, "Nach Updates suchen", error.message)
            return
        if info is None:
            if manual:
                QMessageBox.information(self._window, "Nach Updates suchen",
                                        "Für dieses Programm ist noch keine Update-Quelle eingerichtet.")
            return
        if not updater.is_newer(info.version, config.APP_VERSION):
            if manual:
                QMessageBox.information(self._window, "Nach Updates suchen",
                                        f"Das Programm ist auf dem neuesten Stand (Version {config.APP_VERSION}).")
            return
        if self.ask_install(info):
            self.install(info)

    def ask_install(self, info: updater.UpdateInfo) -> bool:
        box = QMessageBox(self._window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Update verfügbar")
        released = f" ({info.released})" if info.released else ""
        box.setText(f"Version {info.version}{released} ist verfügbar – installiert ist Version {config.APP_VERSION}.")
        details = "Das Programm wird dazu kurz beendet und startet danach neu."
        if info.notes:
            details = f"Neu in dieser Version:\n{info.notes}\n\n{details}"
        box.setInformativeText(details)
        install = box.addButton("Jetzt aktualisieren", QMessageBox.ButtonRole.AcceptRole)
        later = box.addButton("Später", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(install)
        box.setEscapeButton(later)
        box.exec()
        return box.clickedButton() is install

    # -------------------------------------------------------- Installieren
    def install(self, info: updater.UpdateInfo) -> None:
        app_dir = updater.application_directory()
        if app_dir is None:
            QMessageBox.information(self._window, "Update",
                                    "Updates werden nur im fertigen Programm (exe) installiert – "
                                    "dieses Programm läuft gerade aus dem Quelltext.")
            return
        if not updater.can_write(app_dir):
            QMessageBox.warning(self._window, "Update nicht möglich",
                                "Im Programmordner fehlen die Schreibrechte, deshalb kann sich das Programm "
                                "nicht selbst aktualisieren.\n\nDie neue Version gibt es hier:\n"
                                f"{updater.releases_page()}")
            return
        # erst alle Projekte sichern bzw. nachfragen – danach wird das Programm beendet
        for view in self._window.views():
            if not self._window.maybe_save(view.document):
                return
        self._cancel.clear()
        dialog = QProgressDialog("Update wird heruntergeladen …", "Abbrechen", 0, 0, self._window)
        dialog.setWindowTitle("Update")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.canceled.connect(self._cancel.set)
        self._dialog = dialog
        dialog.show()

        def work():
            try:
                new_dir = updater.download_package(info, app_dir, progress=self._progress.emit,
                                                   cancelled=self._cancel.is_set)
                self._downloaded.emit(new_dir, None)
            except updater.UpdateCancelled:
                self._downloaded.emit(None, None)
            except updater.UpdateError as exc:
                self._downloaded.emit(None, exc)
            except Exception as exc:  # pragma: no cover - Absicherung
                self._downloaded.emit(None, updater.UpdateError("Das Update ist fehlgeschlagen.", repr(exc)))

        threading.Thread(target=work, name="update-download", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        if self._dialog is None:
            return
        if total > 0:
            self._dialog.setMaximum(100)
            self._dialog.setValue(min(100, int(done * 100 / total)))
            self._dialog.setLabelText(f"Update wird heruntergeladen … {done // (1024 * 1024)} von "
                                      f"{max(1, total // (1024 * 1024))} MB")

    def _on_downloaded(self, new_dir, error) -> None:
        if self._dialog is not None:
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None
        app_dir = updater.application_directory()
        if error is not None:
            log.warning("Update fehlgeschlagen: %s (%s)", error.message, error.details)
            QMessageBox.warning(self._window, "Update nicht möglich", error.message)
            return
        if new_dir is None or app_dir is None:
            return  # abgebrochen
        try:
            updater.start_installer(new_dir, app_dir)
        except updater.UpdateError as exc:
            QMessageBox.warning(self._window, "Update nicht möglich", exc.message)
            return
        # Das Programm beenden; die neue Version wartet darauf und ersetzt dann den Programmordner
        QTimer.singleShot(0, self._window.close)
