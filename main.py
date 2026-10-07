"""Startpunkt des BS Technik PAP Designers.

Aufruf:
    python main.py [Projektdatei.pap ...]
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


def _create_application():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from app import config, icons, theme

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORGANIZATION_NAME)
    app.setOrganizationDomain(config.ORGANIZATION_DOMAIN)
    app.setWindowIcon(icons.app_icon())
    theme.apply_ui_theme(app, theme.saved_theme_name())
    return app


def _install_update(arguments: list[str]) -> int:
    """Installationsmodus: Diese (neue) Programmdatei ersetzt den Programmordner und startet neu.

    Aufruf durch das laufende Programm: ``--apply-update <Programmordner> <Prozessnummer>``.
    """
    from PySide6.QtWidgets import QMessageBox

    from app import config, updater
    from app.splash import SplashScreen

    try:
        app_dir, pid = arguments[0], int(arguments[1])
    except (IndexError, ValueError):
        return 2
    app = _create_application()
    splash = SplashScreen("Update wird installiert …")
    splash.show()
    app.processEvents()
    updater.wait_for_exit(pid)
    try:
        updater.apply_update(os.path.dirname(os.path.abspath(sys.executable)), app_dir)
    except updater.UpdateError as exc:
        splash.close()
        QMessageBox.warning(None, config.APP_NAME, exc.message)
    splash.close()
    updater.launch_program(app_dir)
    return 0


def main() -> int:
    # Im gebündelten Programm (PyInstaller) liegt das Paket neben der EXE
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from app import config, errors, resources, updater

    errors.setup_logging()
    errors.install_exception_hook()
    _set_windows_app_id()

    if updater.APPLY_FLAG in sys.argv[1:] and resources.is_frozen():
        return _install_update(sys.argv[sys.argv.index(updater.APPLY_FLAG) + 1:])

    from PySide6.QtCore import QEventLoop, QTimer

    from app.main_window import MainWindow
    from app.splash import SplashScreen

    app = _create_application()

    # Ladebildschirm, während das Hauptfenster aufgebaut wird
    started = time.monotonic()
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    window = MainWindow(enable_autosave=True)

    remaining = config.SPLASH_MIN_DURATION_MS - int((time.monotonic() - started) * 1000)
    if remaining > 0:
        loop = QEventLoop()
        QTimer.singleShot(remaining, loop.quit)
        loop.exec()
    window.show()
    splash.finish(window)

    files = [arg for arg in sys.argv[1:] if not arg.startswith("-") and os.path.isfile(arg)]
    opened = window.offer_recovery() > 0
    for path in files:
        opened = window.open_file(path) or opened
    if not opened:
        window.new_document()

    if resources.is_frozen():
        # Reste eines früheren Updates entfernen und nach einer neuen Version sehen
        QTimer.singleShot(3000, window.updates.cleanup_leftovers)
        window.updates.check()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
