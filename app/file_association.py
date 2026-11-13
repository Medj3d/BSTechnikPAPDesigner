"""Registrierung der Dateiendung ``.pap`` (Doppelklick öffnet das Programm).

**Windows**: Die Zuordnung wird ausschließlich für den aktuellen Benutzer
(``HKEY_CURRENT_USER\\Software\\Classes``) eingetragen und erfordert daher
keine Administratorrechte. Sie wird nur auf ausdrücklichen Wunsch des
Benutzers (Menü „Hilfe“) vorgenommen. Für eine Installation über ein
Setup-Programm siehe ``installer/BSTechnikPAPDesigner.iss``.

**Linux**: ``.desktop``-Datei, Dateityp und Symbole im Benutzerordner – siehe ``app/file_association_linux.py``.
Das AppImage richtet das beim Start von selbst ein (``ensure_installed``).

Eine spätere macOS-Version bekommt hier einen weiteren Zweig (dort meldet das Programmpaket den Dateityp
selbst in seiner ``Info.plist`` an).
"""

from __future__ import annotations

import os
import sys

from app import config, platforms, resources
from app.i18n import tr


def is_supported() -> bool:
    return platforms.is_windows() or platforms.is_linux()


def register() -> None:
    """Trägt die Dateizuordnung ein. Wirft ``OSError`` bei Fehlern."""
    if platforms.is_linux():
        from app import file_association_linux

        file_association_linux.register()
        return
    register_windows()


def unregister() -> None:
    if platforms.is_linux():
        from app import file_association_linux

        file_association_linux.unregister()
        return
    unregister_windows()


def ensure_installed() -> bool:
    """Beim Programmstart: Unter Linux (nur im AppImage) Verknüpfung und Dateityp einrichten, wenn sie fehlen
    oder veraltet sind. Unter Windows geschieht nichts (dort richtet das Setup die Zuordnung ein)."""
    if platforms.is_linux():
        from app import file_association_linux

        return file_association_linux.ensure_installed()
    return False


# ==================================================================== Windows
def _stable_program() -> tuple[str, str] | None:
    """(Programmdatei, Ordner), die eingetragen werden – beim fertigen Programm sonst ``None``.

    Läuft eine Kopie aus dem Benutzerordner (Update ohne Schreibrechte), wird die installierte Version eingetragen:
    Den Ordner der Kopie löscht das nächste Update, die installierte Version gibt beim Öffnen selbst an die neueste
    Kopie ab."""
    if not getattr(sys, "frozen", False):
        return None
    from app import updater

    folder = updater.installation_directory() or os.path.dirname(os.path.abspath(sys.executable))
    return os.path.join(folder, os.path.basename(sys.executable)), folder


def open_command() -> str:
    """Befehlszeile, mit der Windows eine Projektdatei öffnet."""
    program = _stable_program()
    if program is not None:
        return f'"{program[0]}" "%1"'
    main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    return f'"{python}" "{main_script}" "%1"'


def icon_location() -> str:
    icon_path = resources.asset_path("file_icon.ico")
    program = _stable_program()
    if program is not None:
        # dieselbe Datei im eingetragenen Programmordner (bei einer Kopie: in der installierten Version)
        running = os.path.dirname(os.path.abspath(sys.executable))
        stable = os.path.join(program[1], os.path.relpath(icon_path, running))
        if os.path.exists(stable):
            return f'"{stable}"'
        return f'"{program[0]}",0'
    if os.path.exists(icon_path):
        return f'"{icon_path}"'
    return ""


def register_windows() -> None:
    """Trägt die Dateizuordnung in die Registry ein. Wirft ``OSError`` bei Fehlern."""
    if not platforms.is_windows():
        raise OSError(tr("Die Dateizuordnung ist nur unter Windows verfügbar."))
    import winreg

    base = r"Software\Classes"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\{config.FILE_EXTENSION}") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, config.FILE_PROG_ID)
        winreg.SetValueEx(key, "Content Type", 0, winreg.REG_SZ, "application/xml")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\{config.FILE_PROG_ID}") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, config.file_type_description())
    icon = icon_location()
    if icon:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\{config.FILE_PROG_ID}\DefaultIcon") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"{base}\{config.FILE_PROG_ID}\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, open_command())
    _notify_shell()


def unregister_windows() -> None:
    if not platforms.is_windows():
        raise OSError(tr("Die Dateizuordnung ist nur unter Windows verfügbar."))
    import winreg

    base = r"Software\Classes"
    for sub in (rf"{config.FILE_PROG_ID}\shell\open\command", rf"{config.FILE_PROG_ID}\shell\open",
                rf"{config.FILE_PROG_ID}\shell", rf"{config.FILE_PROG_ID}\DefaultIcon",
                config.FILE_PROG_ID):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{base}\{sub}")
        except FileNotFoundError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{base}\{config.FILE_EXTENSION}", 0,
                            winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "")
        if value == config.FILE_PROG_ID:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{base}\{config.FILE_EXTENSION}")
    except (FileNotFoundError, OSError):
        pass
    _notify_shell()


def _notify_shell() -> None:
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass
