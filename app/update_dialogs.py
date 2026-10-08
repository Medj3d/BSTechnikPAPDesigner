"""Oberfläche der Update-Funktion: Prüfen im Hintergrund, Nachfrage, Laden mit Fortschritt."""

from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from app import config, updater
from app.i18n import tr

log = logging.getLogger(__name__)


def _available_text(info: updater.UpdateInfo) -> str:
    """„Version X (Datum) ist verfügbar – installiert ist Version Y.“"""
    if info.released:
        return tr("Version {version} ({released}) ist verfügbar – installiert ist Version {installed}.",
                  version=info.version, released=info.released, installed=config.APP_VERSION)
    return tr("Version {version} ist verfügbar – installiert ist Version {installed}.",
              version=info.version, installed=config.APP_VERSION)


class UpdateController(QObject):
    """Verbindet die Abläufe aus ``app.updater`` mit dem Hauptfenster.

    Netzwerkzugriffe laufen in einem eigenen Thread; die Ergebnisse kommen als
    Signal im Thread der Oberfläche an.
    """

    # So lange bleibt der Hinweis „neue Version“ in der Statuszeile (Millisekunden)
    STATUS_NOTE_MS = 20000

    _checked = Signal(object, object, bool)   # UpdateInfo | None, UpdateError | None, von Hand ausgelöst
    _progress = Signal(int, int)
    _downloaded = Signal(object, object)      # Ordner der neuen Version | None, Fehler | None

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._checking = False
        self._cancel = threading.Event()
        self._dialog: QProgressDialog | None = None
        self._mode = "in_place"                              # Weg des gerade laufenden Updates
        self._pending_info: updater.UpdateInfo | None = None  # dessen Version
        self._checked.connect(self._on_checked)
        self._progress.connect(self._on_progress)
        self._downloaded.connect(self._on_downloaded)

    def cleanup_leftovers(self) -> None:
        """Entfernt Reste eines früheren Updates (nicht, während gerade eines geladen wird)."""
        app_dir = updater.application_directory()
        if app_dir is not None and self._dialog is None:
            updater.cleanup_staging(app_dir)
            updater.cleanup_user_programs()

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
                error = updater.UpdateError(tr("Die Update-Prüfung ist fehlgeschlagen."), repr(exc))
            self._checked.emit(info, error, manual)

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _on_checked(self, info, error, manual: bool) -> None:
        self._checking = False
        if error is not None:
            log.info("Update-Prüfung: %s (%s)", error.message, error.details)
            if manual:
                QMessageBox.warning(self._window, tr("Nach Updates suchen"), error.message)
            return
        if info is None:
            if manual:
                QMessageBox.information(self._window, tr("Nach Updates suchen"),
                                        tr("Für dieses Programm ist noch keine Update-Quelle eingerichtet."))
            return
        if not updater.is_newer(info.version, config.APP_VERSION):
            if manual:
                QMessageBox.information(self._window, tr("Nach Updates suchen"),
                                        tr("Das Programm ist auf dem neuesten Stand (Version {version}).",
                                           version=config.APP_VERSION))
            return
        blocker = self.install_blocker()
        if blocker:
            # Hier kann das Programm sich nicht selbst aktualisieren: nicht erst fragen
            self._announce_without_install(info, blocker, manual)
            return
        if self.ask_install(info):
            self.install(info)

    def install_blocker(self) -> str:
        """Warum sich das Programm hier nicht selbst aktualisieren kann.

        ``""`` = es kann (der Programmordner wird ersetzt oder die neue Version
        kommt in den Benutzerordner); ``"rights"`` = weder noch (Programmordner
        nicht beschreibbar und der Start aus dem Benutzerordner nicht möglich);
        ``"source"`` = das Programm läuft aus dem Quelltext statt als exe.
        """
        mode = updater.update_mode()
        return {"source": "source", "blocked": "rights"}.get(mode, "")

    def _announce_without_install(self, info: updater.UpdateInfo, blocker: str, manual: bool) -> None:
        """Weist auf die neue Version hin, ohne eine Frage zu stellen, die sich nicht erfüllen lässt.

        Beim Start nur ein ruhiger Hinweis in der Statuszeile; über das Menü
        eine Auskunft mit dem Link zur neuen Version.
        """
        if not manual:
            if blocker == "rights":
                note = tr("Neue Version {version} verfügbar – das Programm kann sich hier nicht selbst "
                          "aktualisieren, bitte beim Administrator melden.", version=info.version)
            else:
                note = tr("Neue Version {version} verfügbar – dieses Programm läuft aus dem Quelltext und "
                          "aktualisiert sich nicht selbst.", version=info.version)
            self._window.statusBar().showMessage(note, self.STATUS_NOTE_MS)
            return
        paragraphs = [_available_text(info)]
        if blocker == "rights":
            paragraphs.append(tr("Das Programm darf seinen Ordner hier nicht ändern und kann auch keine neue "
                                 "Version im Benutzerordner ablegen oder starten. Bitte beim Administrator "
                                 "melden; er installiert die neue Version mit dem Setup."))
        else:
            paragraphs.append(tr("Dieses Programm läuft aus dem Quelltext und aktualisiert sich nicht selbst."))
        if info.notes:
            paragraphs.append(tr("Neu in dieser Version:\n{notes}", notes=info.notes))
        repo = updater.repository()
        if repo:
            paragraphs.append(tr("Die neue Version gibt es hier:\n{url}",
                                 url=f"https://github.com/{repo}/releases/latest/download/{config.SETUP_FILE_NAME}"))
        QMessageBox.information(self._window, tr("Update verfügbar"), "\n\n".join(paragraphs))

    def ask_install(self, info: updater.UpdateInfo) -> bool:
        box = QMessageBox(self._window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr("Update verfügbar"))
        box.setText(_available_text(info))
        details = tr("Das Programm wird dazu kurz beendet und startet danach neu.")
        if info.notes:
            details = tr("Neu in dieser Version:\n{notes}", notes=info.notes) + "\n\n" + details
        box.setInformativeText(details)
        install = box.addButton(tr("Jetzt aktualisieren"), QMessageBox.ButtonRole.AcceptRole)
        later = box.addButton(tr("Später"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(install)
        box.setEscapeButton(later)
        box.exec()
        return box.clickedButton() is install

    # -------------------------------------------------------- Installieren
    def install(self, info: updater.UpdateInfo) -> None:
        mode = updater.update_mode()
        if mode == "source":
            QMessageBox.information(self._window, tr("Update"),
                                    tr("Updates werden nur im fertigen Programm (exe) installiert – "
                                       "dieses Programm läuft gerade aus dem Quelltext."))
            return
        if mode == "blocked":
            QMessageBox.warning(self._window, tr("Update nicht möglich"),
                                tr("Das Programm darf seinen Ordner hier nicht ändern und kann auch keine neue "
                                   "Version im Benutzerordner starten, deshalb kann es sich nicht selbst "
                                   "aktualisieren.\n\nDie neue Version gibt es hier:\n{url}",
                                   url=updater.releases_page()))
            return
        app_dir = updater.application_directory()
        # beschreibbarer Programmordner: dort wird ersetzt; sonst kommt die Kopie in den Benutzerordner
        staging_parent = app_dir if mode == "in_place" else updater.user_update_root()
        self._mode, self._pending_info = mode, info
        # erst alle Projekte sichern bzw. nachfragen – danach wird das Programm beendet
        for view in self._window.views():
            if not self._window.maybe_save(view.document):
                return
        self._cancel.clear()
        dialog = QProgressDialog(tr("Update wird heruntergeladen …"), tr("Abbrechen"), 0, 0, self._window)
        dialog.setWindowTitle(tr("Update"))
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.canceled.connect(self._cancel.set)
        self._dialog = dialog
        dialog.show()

        def work():
            try:
                new_dir = updater.download_package(info, staging_parent, progress=self._progress.emit,
                                                   cancelled=self._cancel.is_set)
                self._downloaded.emit(new_dir, None)
            except updater.UpdateCancelled:
                self._downloaded.emit(None, None)
            except updater.UpdateError as exc:
                self._downloaded.emit(None, exc)
            except Exception as exc:  # pragma: no cover - Absicherung
                self._downloaded.emit(None, updater.UpdateError(tr("Das Update ist fehlgeschlagen."), repr(exc)))

        threading.Thread(target=work, name="update-download", daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        if self._dialog is None:
            return
        if total > 0:
            self._dialog.setMaximum(100)
            self._dialog.setValue(min(100, int(done * 100 / total)))
            self._dialog.setLabelText(tr("Update wird heruntergeladen … {done} von {total} MB",
                                         done=done // (1024 * 1024), total=max(1, total // (1024 * 1024))))

    def _on_downloaded(self, new_dir, error) -> None:
        if self._dialog is not None:
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None
        app_dir = updater.application_directory()
        if error is not None:
            log.warning("Update fehlgeschlagen: %s (%s)", error.message, error.details)
            QMessageBox.warning(self._window, tr("Update nicht möglich"), error.message)
            return
        if new_dir is None or app_dir is None:
            return  # abgebrochen
        try:
            if self._mode == "in_place":
                updater.start_installer(new_dir, app_dir)
                # Das Programm beenden; die neue Version wartet darauf und ersetzt dann den Programmordner
            else:
                folder = updater.install_user_program(new_dir, self._pending_info.version)
                updater.cleanup_user_programs()  # Zwischenreste und veraltete Kopien entfernen
                self._launch_after_quit(folder)  # die neue Kopie startet, sobald dieses Programm beendet ist
        except updater.UpdateError as exc:
            QMessageBox.warning(self._window, tr("Update nicht möglich"), exc.message)
            return
        QTimer.singleShot(0, self._window.close)

    def _launch_after_quit(self, folder: str) -> None:
        """Startet das Programm aus ``folder``, sobald dieses Programm beendet ist."""
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(lambda: updater.launch_program(folder, wait_pid=os.getpid()))
