"""Registrierung der Dateiendung ``.pap`` unter Windows.

Die Zuordnung wird ausschließlich für den aktuellen Benutzer
(``HKEY_CURRENT_USER\\Software\\Classes``) eingetragen und erfordert daher
keine Administratorrechte. Sie wird nur auf ausdrücklichen Wunsch des
Benutzers (Menü „Hilfe“) vorgenommen. Für eine Installation über ein
Setup-Programm siehe ``installer/BSTechnikPAPDesigner.iss``.
"""

from __future__ import annotations

import os
import sys

from app import config, resources
from app.i18n import tr


def is_supported() -> bool:
    return sys.platform.startswith("win")


def open_command() -> str:
    """Befehlszeile, mit der Windows eine Projektdatei öffnet."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    return f'"{python}" "{main_script}" "%1"'


def icon_location() -> str:
    icon_path = resources.asset_path("file_icon.ico")
    if os.path.exists(icon_path):
        return f'"{icon_path}"'
    return f'"{sys.executable}",0' if getattr(sys, "frozen", False) else ""


def register() -> None:
    """Trägt die Dateizuordnung ein. Wirft ``OSError`` bei Fehlern."""
    if not is_supported():
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


def unregister() -> None:
    if not is_supported():
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
