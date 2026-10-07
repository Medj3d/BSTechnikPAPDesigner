"""Startpunkt des BS Technik PAP Designers.

Aufruf:
    python main.py [Projektdatei.pap ...]

Der Ladebildschirm erscheint als Erstes: Alles, was Zeit kostet (Farbschema,
die Programmteile, das Hauptfenster), wird erst danach geladen.
"""

from __future__ import annotations

import os
import sys
import time


def _set_windows_app_id() -> None:
    """Eigenes Taskleisten-Symbol unter Windows (statt des Python-Symbols)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            from app import config

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(config.WINDOWS_APP_ID)
        except Exception:
            pass


def _create_application(arguments: list[str] | tuple[str, ...] = ()):
    """Die Qt-Anwendung – noch ohne Farbschema, damit der Ladebildschirm sofort erscheinen kann.

    Stellt auch die Sprache ein: ``--sprache <Code>`` (nur für diesen Start) oder die gespeicherte Auswahl.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from app import config

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORGANIZATION_NAME)
    app.setOrganizationDomain(config.ORGANIZATION_DOMAIN)

    from app import i18n
    from app.settings_store import SettingsStore

    preference = _flag_value(list(arguments), config.LANGUAGE_FLAG) or SettingsStore().language()
    code = preference if preference == i18n.PSEUDO_LANGUAGE else i18n.resolve(preference)
    i18n.set_language(code)
    i18n.apply_to_application(app, code)
    return app


def _show_splash(app, message: str = ""):
    """Zeigt den Ladebildschirm: zuerst nur das Logo (sofort), gleich darauf mit Schrift."""
    from app.splash import SplashScreen

    splash = SplashScreen(message)
    splash.show()
    app.processEvents()
    splash.complete()
    app.processEvents()
    return splash


def _apply_look(app) -> None:
    """Programmsymbol und Farbschema (nach dem Ladebildschirm, weil es Zeit kostet)."""
    from app import icons, theme

    app.setWindowIcon(icons.app_icon())
    theme.apply_ui_theme(app, theme.saved_theme_name())


def _install_update(arguments: list[str]) -> int:
    """Installationsmodus: Diese (neue) Programmdatei ersetzt den Programmordner und startet neu.

    Aufruf durch das laufende Programm: ``--apply-update <Programmordner> <Prozessnummer>``.
    """
    try:
        app_dir, pid = arguments[0], int(arguments[1])
    except (IndexError, ValueError):
        return 2
    app = _create_application()

    from app.i18n import tr

    splash = _show_splash(app, tr("Update wird installiert …"))

    from PySide6.QtWidgets import QMessageBox

    from app import config, updater

    _apply_look(app)
    updater.wait_for_exit(pid)
    try:
        updater.apply_update(os.path.dirname(os.path.abspath(sys.executable)), app_dir)
    except updater.UpdateError as exc:
        splash.close()
        QMessageBox.warning(None, config.APP_NAME, exc.message)
    splash.close()
    updater.launch_program(app_dir)
    return 0


def _files_from(arguments: list[str]) -> list[str]:
    """Die Projektdateien unter den Startargumenten (als absolute Pfade); Schalter und ihre Werte zählen nicht."""
    from app import config

    files, skip = [], False
    for argument in arguments:
        if skip:
            skip = False
        elif argument in (config.WAIT_FOR_FLAG, config.LANGUAGE_FLAG):
            skip = True  # der nächste Wert gehört zum Schalter (Prozessnummer bzw. Sprachcode)
        elif not argument.startswith("-") and os.path.isfile(argument):
            files.append(os.path.abspath(argument))
    return files


def _flag_value(arguments: list[str], flag: str) -> str | None:
    if flag in arguments and arguments.index(flag) + 1 < len(arguments):
        return arguments[arguments.index(flag) + 1]
    return None


def _open_in_window(window, files: list[str]) -> None:
    """Öffnet Dateien, die ein weiterer Programmstart übergeben hat, als Reiter in diesem Fenster."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    def run() -> None:
        if QApplication.activeModalWidget() is not None:  # z. B. offene Speichern-Nachfrage: danach erst öffnen
            QTimer.singleShot(400, run)
            return
        window.open_external_files(files)

    QTimer.singleShot(0, run)


def main() -> int:
    # Im gebündelten Programm (PyInstaller) liegt das Paket neben der EXE
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from app import config, errors, resources

    errors.setup_logging()
    errors.install_exception_hook()
    _set_windows_app_id()

    arguments = sys.argv[1:]
    if config.UPDATE_APPLY_FLAG in arguments and resources.is_frozen():
        return _install_update(arguments[arguments.index(config.UPDATE_APPLY_FLAG) + 1:])

    from app import updater

    # Neustart (nach Update oder Sprachwechsel): erst warten, bis sich das alte Programm geschlossen hat –
    # sonst übergäbe dieser Start seine Dateien noch an das sich schließende Fenster.
    waiting_for = _flag_value(arguments, config.WAIT_FOR_FLAG)
    if waiting_for is not None and waiting_for.isdigit():
        updater.wait_for_exit(int(waiting_for), 30.0)

    # Liegt im Benutzerordner eine neuere Kopie (Update ohne Schreibrechte im Programmordner),
    # gibt dieses Programm sofort an sie ab – noch vor Qt und Ladebildschirm.
    if updater.redirect_to_user_program(arguments):
        return 0

    files = _files_from(arguments)
    app = _create_application(arguments)

    # Läuft schon ein Programmfenster? Dann übernimmt es die Dateien (als Reiter) und dieser Start endet sofort,
    # ohne Ladebildschirm. Sonst wird dieser Start das erste Programm und lauscht auf weitere Starts.
    instance_server = None
    if config.NEW_WINDOW_FLAG not in arguments:
        from app import single_instance

        handed_over, instance_server = single_instance.acquire(files)
        if handed_over:
            return 0

    started = time.monotonic()
    splash = _show_splash(app)

    # Erst jetzt alles Übrige laden – der Ladebildschirm ist schon zu sehen
    from PySide6.QtCore import QEventLoop, QTimer

    _apply_look(app)
    from app.main_window import MainWindow

    window = MainWindow(enable_autosave=True)

    remaining = config.SPLASH_MIN_DURATION_MS - int((time.monotonic() - started) * 1000)
    if remaining > 0:
        loop = QEventLoop()
        QTimer.singleShot(remaining, loop.quit)
        loop.exec()
    window.show()
    splash.finish(window)

    opened = window.offer_recovery() > 0
    for path in files:
        opened = window.open_file(path) or opened
    if not opened:
        window.new_document()

    if instance_server is not None:
        # Ab jetzt öffnen weitere Programmstarts ihre Dateien hier; was während des Starts eintraf, folgt sofort
        window.instance_server = instance_server
        app.aboutToQuit.connect(instance_server.close)
        instance_server.set_handler(lambda received: _open_in_window(window, received))

    if resources.is_frozen():
        # Reste eines früheren Updates entfernen und nach einer neuen Version sehen
        QTimer.singleShot(3000, window.updates.cleanup_leftovers)
        window.updates.check()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
