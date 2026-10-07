# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Konfiguration für den BS Technik PAP Designer.
#
# Erzeugen der EXE (im Projektordner):
#     python -m pip install -r requirements-dev.txt
#     python -m PyInstaller --noconfirm BSTechnikPAPDesigner.spec
#
# Ergebnis: dist\BSTechnikPAPDesigner\BSTechnikPAPDesigner.exe

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPrintSupport"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtPositioning",
        "PySide6.QtSql", "PySide6.QtNetwork", "PySide6.QtTest",
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
    icon="assets/app_icon.ico",
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
