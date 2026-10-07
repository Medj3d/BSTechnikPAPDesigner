"""Zugriff auf mitgelieferte Dateien (Ordner ``assets``).

Im fertigen Programm (PyInstaller) liegen sie im entpackten Programmordner,
beim Start aus dem Quelltext im Projektordner.
"""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    """Läuft das fertige Programm (exe) und nicht der Quelltext?"""
    return bool(getattr(sys, "frozen", False))


def base_directory() -> str:
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def asset_path(name: str) -> str:
    return os.path.join(base_directory(), "assets", name)
