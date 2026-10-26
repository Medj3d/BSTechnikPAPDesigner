"""Dialog: Name eines neuen oder umbenannten Unterprogramms (mit Prüfung beim Tippen)."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from app.fileformat.serializer import storable_text
from app.i18n import tr
from app.subprograms import clean_name, name_error


class SubprogramNameDialog(QDialog):
    def __init__(self, document, title: str, initial: str = "", page=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self._document = document
        self._page = page

        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        hint = QLabel(tr("Unter diesem Namen rufen Unterprogramm-Bausteine das Unterprogramm auf. "
                         "Seine Seite beginnt mit einem Start-Element dieses Namens."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.name_edit = QLineEdit(initial)
        self.name_edit.setPlaceholderText(tr("z. B. Mittelwert berechnen"))
        self.name_edit.selectAll()
        self.name_edit.textChanged.connect(self._validate)
        self.error_label = QLabel("")
        self.error_label.setObjectName("Muted")
        self.error_label.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("OK"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)
        self._validate()

    def name(self) -> str:
        return clean_name(storable_text(self.name_edit.text()))

    def _validate(self, *_args) -> None:
        error = name_error(self._document, self.name(), self._page)
        unchanged = self._page is not None and self.name() == self._page.display_name
        self.error_label.setText(error if error and not unchanged else "")
        self.error_label.setVisible(bool(error) and not unchanged)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(error is None or unchanged)

    def accept(self) -> None:
        if self.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled():
            super().accept()
