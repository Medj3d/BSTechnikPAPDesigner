"""Dialog: Projekteigenschaften (Metadaten und Rastergröße)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QSpinBox, QVBoxLayout)

from app import config
from app.fileformat.project import CURRENT_FORMAT_VERSION
from app.fileformat.serializer import storable_text
from app.i18n import tr
from app.model.diagram import ProjectMeta


def format_timestamp(value: str) -> str:
    if not value:
        return "–"
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


class ProjectPropertiesDialog(QDialog):
    def __init__(self, meta: ProjectMeta, grid_size: int, file_path: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Projekteigenschaften"))
        self.setMinimumWidth(460)
        self._meta = meta.copy()

        title = QLabel(tr("Projekteigenschaften"))
        title.setObjectName("DialogTitle")

        self.name_edit = QLineEdit(meta.name)
        self.name_edit.setPlaceholderText(tr("Projektname"))
        self.author_edit = QLineEdit(meta.author)
        self.author_edit.setPlaceholderText(tr("optional"))
        self.description_edit = QPlainTextEdit(meta.description)
        self.description_edit.setPlaceholderText(tr("optional"))
        self.description_edit.setFixedHeight(90)
        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(config.MIN_GRID_SIZE, config.MAX_GRID_SIZE)
        self.grid_spin.setSingleStep(5)
        self.grid_spin.setSuffix(" px")
        self.grid_spin.setValue(int(grid_size))

        created = QLineEdit(format_timestamp(meta.created))
        created.setReadOnly(True)
        modified = QLineEdit(format_timestamp(meta.modified))
        modified.setReadOnly(True)
        version = QLineEdit(str(CURRENT_FORMAT_VERSION))
        version.setReadOnly(True)
        location = QLineEdit(file_path or tr("(noch nicht gespeichert)"))
        location.setReadOnly(True)
        location.setCursorPosition(0)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.addRow(tr("Projektname"), self.name_edit)
        form.addRow(tr("Autor"), self.author_edit)
        form.addRow(tr("Beschreibung"), self.description_edit)
        form.addRow(tr("Rastergröße"), self.grid_spin)
        form.addRow(tr("Erstellt"), created)
        form.addRow(tr("Geändert"), modified)
        form.addRow(tr("Dateiformat-Version"), version)
        form.addRow(tr("Speicherort"), location)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Übernehmen"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def result_meta(self) -> ProjectMeta:
        meta = self._meta.copy()
        # nur übernehmen, was die Projektdatei unverändert aufnehmen kann
        meta.name = storable_text(self.name_edit.text()).strip() or config.default_project_name()
        meta.author = storable_text(self.author_edit.text()).strip()
        meta.description = storable_text(self.description_edit.toPlainText()).strip()
        return meta

    def result_grid_size(self) -> int:
        return int(self.grid_spin.value())
