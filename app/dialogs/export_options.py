"""Dialog: Optionen für Export und Druck."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QDate, QLocale
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QVBoxLayout)

from app.export import ExportOptions, stamp_text
from app.i18n import N_, tr

# Die Beschriftungen sind deutscher Quelltext (mit N_ markiert); angezeigt werden sie mit tr(). „3×“ besteht nur
# aus Zahl und Symbol und bleibt unverändert.
THEME_CHOICES = [("light", N_("Hell (für Dokumente und Druck)")), ("dark", N_("Dunkel (wie im Editor)"))]
SCALE_CHOICES = [(1.0, N_("1× (Bildschirmauflösung)")), (2.0, N_("2× (empfohlen)")), (3.0, "3×"),
                 (4.0, N_("4× (sehr hoch)"))]


@dataclass
class StampSettings:
    """Name, Klasse und Datum auf dem Plan (gemerkt für das nächste Mal)."""
    enabled: bool = False
    name: str = ""
    school_class: str = ""

    def text(self) -> str:
        if not self.enabled:
            return ""
        return stamp_text(self.name, self.school_class, today_text())


def today_text() -> str:
    return QLocale().toString(QDate.currentDate(), QLocale.FormatType.ShortFormat)


class ExportOptionsDialog(QDialog):
    def __init__(self, format_name: str, options: ExportOptions, parent=None, stamp: StampSettings | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("{format} – Optionen", format=format_name))
        self.setMinimumWidth(400)
        self._format = format_name.upper()
        title = QLabel(f"{format_name}")
        title.setObjectName("DialogTitle")

        self.theme_combo = QComboBox()
        for key, label in THEME_CHOICES:
            self.theme_combo.addItem(tr(label), key)
        keys = [key for key, _ in THEME_CHOICES]
        self.theme_combo.setCurrentIndex(keys.index(options.theme_name) if options.theme_name in keys else 0)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.addRow(tr("Farbschema"), self.theme_combo)

        self.scale_combo = None
        self.transparent_check = None
        if self._format == "PNG":
            self.scale_combo = QComboBox()
            for value, label in SCALE_CHOICES:
                self.scale_combo.addItem(tr(label), value)
            index = next((i for i, (v, _) in enumerate(SCALE_CHOICES) if abs(v - options.scale) < 1e-6), 1)
            self.scale_combo.setCurrentIndex(index)
            form.addRow(tr("Auflösung"), self.scale_combo)
        if self._format in ("PNG", "SVG"):
            self.transparent_check = QCheckBox(tr("Transparenter Hintergrund"))
            self.transparent_check.setChecked(options.transparent)
            form.addRow("", self.transparent_check)

        # Name, Klasse und Datum klein unten rechts auf dem Plan (z. B. für die Abgabe)
        stamp = stamp or StampSettings()
        self.stamp_check = QCheckBox(tr("Name, Klasse und Datum auf den Plan schreiben"))
        self.stamp_check.setChecked(stamp.enabled)
        self.name_edit = QLineEdit(stamp.name)
        self.name_edit.setPlaceholderText(tr("Vor- und Nachname"))
        self.class_edit = QLineEdit(stamp.school_class)
        self.class_edit.setPlaceholderText(tr("z. B. 10b"))
        self.date_label = QLabel(today_text())
        self.date_label.setObjectName("Muted")
        form.addRow("", self.stamp_check)
        form.addRow(tr("Name"), self.name_edit)
        form.addRow(tr("Klasse"), self.class_edit)
        form.addRow(tr("Datum"), self.date_label)
        self.stamp_check.toggled.connect(self._update_stamp_fields)
        self._update_stamp_fields()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Weiter"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _update_stamp_fields(self) -> None:
        enabled = self.stamp_check.isChecked()
        for widget in (self.name_edit, self.class_edit, self.date_label):
            widget.setEnabled(enabled)

    def stamp_settings(self) -> StampSettings:
        return StampSettings(self.stamp_check.isChecked(), self.name_edit.text().strip(),
                             self.class_edit.text().strip())

    def options(self) -> ExportOptions:
        result = ExportOptions(theme_name=self.theme_combo.currentData(), stamp=self.stamp_settings().text())
        if self.scale_combo is not None:
            result.scale = float(self.scale_combo.currentData())
        if self.transparent_check is not None:
            result.transparent = self.transparent_check.isChecked()
        return result
