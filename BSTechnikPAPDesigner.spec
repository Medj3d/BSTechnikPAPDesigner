# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Konfiguration für den BS Technik PAP Designer (Windows und Linux).
#
# Erzeugen der EXE (im Projektordner):
#     python -m pip install -r requirements-dev.txt
#     python -m PyInstaller --noconfirm BSTechnikPAPDesigner.spec
#
# Ergebnis: dist\BSTechnikPAPDesigner\BSTechnikPAPDesigner.exe
# Unter Linux: dist/BSTechnikPAPDesigner/BSTechnikPAPDesigner – daraus macht tools/build_appimage.sh das AppImage.

import glob
import os
import sys

block_cipher = None
LINUX = sys.platform.startswith("linux")

# Linux: Bibliotheken, die Qt für die Anzeige unter X11/XWayland braucht, die aber nicht auf jedem System
# installiert sind (z. B. fehlt libxcb-cursor0 unter Ubuntu ohne Desktop-Pakete). Sie kommen mit ins Programm.
LINUX_EXTRA_LIBRARIES = [
    "libxcb-cursor.so.0", "libxcb-icccm.so.4", "libxcb-image.so.0", "libxcb-keysyms.so.1",
    "libxcb-render-util.so.0", "libxcb-xkb.so.1", "libxcb-xinerama.so.0", "libxcb-randr.so.0",
    "libxcb-shape.so.0", "libxcb-xfixes.so.0", "libxcb-sync.so.1", "libxcb-shm.so.0",
    "libxkbcommon-x11.so.0", "libxkbcommon.so.0",
]
LIBRARY_FOLDERS = ["/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"]


def linux_libraries():
    found = []
    for name in LINUX_EXTRA_LIBRARIES:
        for folder in LIBRARY_FOLDERS:
            matches = glob.glob(os.path.join(folder, name))
            if matches:
                found.append((os.path.realpath(matches[0]), "."))
                break
        else:
            print(f"Hinweis: {name} nicht gefunden – wird nicht mitgeliefert")
    return found


a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=linux_libraries() if LINUX else [],
    datas=[("assets", "assets")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPrintSupport"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtPositioning",
        "PySide6.QtSql", "PySide6.QtTest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BSTechnikPAPDesigner",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None if LINUX else "assets/app_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="BSTechnikPAPDesigner",
)
