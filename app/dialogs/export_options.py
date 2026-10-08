"""Dialog: Optionen für Export und Druck."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QVBoxLayout)

from app.export import ExportOptions
from app.i18n import N_, tr

# Die Beschriftungen sind deutscher Quelltext (mit N_ markiert); angezeigt werden sie mit tr(). „3×“ besteht nur
# aus Zahl und Symbol und bleibt unverändert.
THEME_CHOICES = [("light", N_("Hell (für Dokumente und Druck)")), ("dark", N_("Dunkel (wie im Editor)"))]
SCALE_CHOICES = [(1.0, N_("1× (Bildschirmauflösung)")), (2.0, N_("2× (empfohlen)")), (3.0, "3×"),
                 (4.0, N_("4× (sehr hoch)"))]


class ExportOptionsDialog(QDialog):
    def __init__(self, format_name: str, options: ExportOptions, parent=None):
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

    def options(self) -> ExportOptions:
        result = ExportOptions(theme_name=self.theme_combo.currentData())
        if self.scale_combo is not None:
            result.scale = float(self.scale_combo.currentData())
        if self.transparent_check is not None:
            result.transparent = self.transparent_check.isChecked()
        return result
