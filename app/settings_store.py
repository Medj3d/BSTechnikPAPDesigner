"""Anwendungseinstellungen (zuletzt geöffnete Dateien, Fensterzustand, Ordner)."""

from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, QSettings

from app import config


class SettingsStore:
    def __init__(self):
        self._settings = QSettings(config.ORGANIZATION_NAME, config.SETTINGS_APP_NAME)

    # ---------------------------------------------------------- zuletzt geöffnet
    def recent_files(self) -> list[str]:
        value = self._settings.value("recent_files", [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        # nur Projektdateien (.pap) – andere Einträge lassen sich nicht öffnen
        files = [str(v) for v in value if v and str(v).lower().endswith(config.FILE_EXTENSION.lower())]
        return files[: config.MAX_RECENT_FILES]

    def add_recent_file(self, path: str) -> None:
        path = os.path.abspath(path)
        files = [f for f in self.recent_files() if os.path.normcase(f) != os.path.normcase(path)]
        files.insert(0, path)
        self._settings.setValue("recent_files", files[: config.MAX_RECENT_FILES])

    def remove_recent_file(self, path: str) -> None:
        files = [f for f in self.recent_files() if os.path.normcase(f) != os.path.normcase(path)]
        self._settings.setValue("recent_files", files)

    def clear_recent_files(self) -> None:
        self._settings.setValue("recent_files", [])

    # ---------------------------------------------------------- Speichern
    def auto_save(self) -> bool:
        """Sollen bereits gespeicherte Projekte nach Änderungen von selbst gespeichert werden?"""
        value = self._settings.value("auto_save", None)
        if value is None:
            return bool(config.AUTO_SAVE_DEFAULT)
        return str(value).strip().lower() in ("true", "1")

    def set_auto_save(self, enabled: bool) -> None:
        self._settings.setValue("auto_save", bool(enabled))

    # ---------------------------------------------------------- Ordner
    def last_directory(self) -> str:
        value = self._settings.value("last_directory", "")
        if isinstance(value, str) and value and os.path.isdir(value):
            return value
        documents = os.path.join(os.path.expanduser("~"), "Documents")
        return documents if os.path.isdir(documents) else os.path.expanduser("~")

    def set_last_directory(self, path: str) -> None:
        directory = path if os.path.isdir(path) else os.path.dirname(path)
        if directory:
            self._settings.setValue("last_directory", directory)

    # ---------------------------------------------------------- Fenster
    def window_geometry(self) -> QByteArray | None:
        value = self._settings.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def window_state(self) -> QByteArray | None:
        value = self._settings.value("window/state")
        return value if isinstance(value, QByteArray) else None

    def save_window(self, geometry: QByteArray, state: QByteArray) -> None:
        self._settings.setValue("window/geometry", geometry)
        self._settings.setValue("window/state", state)

    # ---------------------------------------------------------- Export
    def value(self, key: str, default=None):
        return self._settings.value(key, default)

    def set_value(self, key: str, value) -> None:
        self._settings.setValue(key, value)
