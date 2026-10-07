"""Umschalten des Farbschemas (dunkel/hell) zur Laufzeit."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app import config, icons, styles

SETTINGS_KEY = "ui/theme"
DEFAULT_THEME = "dark"


def saved_theme_name() -> str:
    value = QSettings(config.ORGANIZATION_NAME, config.SETTINGS_APP_NAME).value(SETTINGS_KEY, DEFAULT_THEME)
    return value if value in styles.UI_THEMES else DEFAULT_THEME


def save_theme_name(name: str) -> None:
    QSettings(config.ORGANIZATION_NAME, config.SETTINGS_APP_NAME).setValue(SETTINGS_KEY, name)


def theme_name_of(theme) -> str:
    for name, candidate in styles.UI_THEMES.items():
        if candidate is theme:
            return name
    return DEFAULT_THEME


def apply_ui_theme(app: QApplication, name: str):
    """Setzt Farbschema, Palette und Stylesheet; Icons werden neu gezeichnet.

    Offene Szenen, Ansichten und Aktionen aktualisiert das Hauptfenster.
    """
    theme = styles.UI_THEMES.get(name, styles.DARK)
    styles.set_current_theme(theme)
    styles.apply_application_style(app, theme)
    icons.clear_cache()
    return theme
