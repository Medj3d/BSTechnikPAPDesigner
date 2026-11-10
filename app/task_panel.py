"""Aufgabenfeld über der Arbeitsfläche und Lehrer-Dialog „Aufgabe stellen“ (siehe app/task.py)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout,
                               QWidget)

from app import task as T
from app.i18n import tr


def ask_password(parent, title: str, label: str) -> str | None:
    """Fragt ein Passwort ab (verdeckte Eingabe); ``None`` bei Abbruch."""
    password, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Password)
    return password if ok else None


class TaskDialog(QDialog):
    """Lehrkraft: Aufgabenstellung, optionale Musterlösung und Passwort."""

    def __init__(self, current: T.Task, solution_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Aufgabe stellen"))
        self.setMinimumWidth(560)
        self._current = current
        title = QLabel(tr("Aufgabe stellen"))
        title.setObjectName("DialogTitle")
        intro = QLabel(tr("Die Aufgabe steht beim Öffnen der Datei über dem Plan. Die Musterlösung wird mit dem "
                          "Passwort verschlüsselt und ist nur mit ihm lesbar. Das Passwort schützt die Aufgabe "
                          "auch vor Änderungen."))
        intro.setObjectName("Muted")
        intro.setWordWrap(True)

        self.title_edit = QLineEdit(current.title)
        self.title_edit.setPlaceholderText(tr("z. B. Aufgabe 3: Notendurchschnitt"))
        self.text_edit = QPlainTextEdit(current.text)
        self.text_edit.setPlaceholderText(tr("Was soll der Programmablaufplan leisten?"))
        self.text_edit.setMinimumHeight(140)
        self.solution_edit = QPlainTextEdit(solution_text)
        self.solution_edit.setPlaceholderText(tr("optional – z. B. erwartete Ausgaben oder Lösungsweg"))
        self.solution_edit.setMinimumHeight(100)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat_edit = QLineEdit()
        self.repeat_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if current.locked:
            hint = tr("leer lassen = bisheriges Passwort behalten")
            self.password_edit.setPlaceholderText(hint)
            self.repeat_edit.setPlaceholderText(hint)
        else:
            self.password_edit.setPlaceholderText(tr("nötig, wenn es eine Musterlösung gibt"))

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.addRow(tr("Titel"), self.title_edit)
        form.addRow(tr("Aufgabenstellung"), self.text_edit)
        form.addRow(tr("Musterlösung"), self.solution_edit)
        form.addRow(tr("Passwort"), self.password_edit)
        form.addRow(tr("Wiederholen"), self.repeat_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Übernehmen"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        self.remove_button = buttons.addButton(tr("Aufgabe entfernen"), QDialogButtonBox.ButtonRole.DestructiveRole)
        self.remove_button.setVisible(current.present or current.has_solution)
        self.remove_button.clicked.connect(self._remove)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self._removed = False
        self._previous_password = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def set_previous_password(self, password: str) -> None:
        """Das zum Öffnen eingegebene Passwort (bleibt, wenn kein neues vergeben wird)."""
        self._previous_password = password

    def _remove(self) -> None:
        self._removed = True
        self.accept()

    def _accept(self) -> None:
        password, repeat = self.password_edit.text(), self.repeat_edit.text()
        if password != repeat:
            QMessageBox.warning(self, tr("Aufgabe stellen"), tr("Die beiden Passwörter stimmen nicht überein."))
            return
        if self.solution_edit.toPlainText().strip() and not (password or self._previous_password):
            QMessageBox.warning(self, tr("Aufgabe stellen"),
                                tr("Für eine Musterlösung ist ein Passwort nötig – sonst könnte sie jeder lesen."))
            return
        if not (self.title_edit.text().strip() or self.text_edit.toPlainText().strip()):
            QMessageBox.warning(self, tr("Aufgabe stellen"), tr("Bitte einen Titel oder eine Aufgabenstellung "
                                                                 "eingeben."))
            return
        self.accept()

    def result_task(self) -> T.Task:
        if self._removed:
            return T.Task()
        password = self.password_edit.text() or self._previous_password
        solution = self.solution_edit.toPlainText().strip()
        return T.Task(title=self.title_edit.text().strip(), text=self.text_edit.toPlainText().strip(),
                      solution=T.encrypt(solution, password) if solution else "",
                      lock=T.make_lock(password) if password else "")


class TaskPanel(QWidget):
    """Zeigt die Aufgabe des Projekts; Musterlösung nur mit Passwort."""

    edit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document = None
        self.title = QLabel("")
        self.title.setObjectName("TaskTitle")
        self.title.setWordWrap(True)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(False)
        self.text.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.solution_button = QPushButton(tr("Musterlösung anzeigen …"))
        self.solution_button.clicked.connect(self.show_solution)
        self.edit_button = QPushButton(tr("Aufgabe stellen …"))
        self.edit_button.clicked.connect(self.edit_requested)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self.solution_button)
        buttons.addWidget(self.edit_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        layout.addWidget(self.text, 1)
        layout.addLayout(buttons)
        self.refresh()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(150)
        return hint

    def set_document(self, document) -> None:
        if document is self._document:
            self.refresh()
            return
        if self._document is not None:
            try:
                self._document.settings_changed.disconnect(self.refresh)
            except (RuntimeError, TypeError):
                pass
        self._document = document
        if document is not None:
            document.settings_changed.connect(self.refresh)   # auch nach Rückgängig/Wiederholen
        self.refresh()

    def current_task(self) -> T.Task:
        return T.task_of(self._document.meta) if self._document is not None else T.Task()

    def refresh(self) -> None:
        task = self.current_task()
        if task.present:
            self.title.setText(task.title or tr("Aufgabe"))
            self.text.setPlainText(task.text)
            self.text.show()
            self.edit_button.setText(tr("Aufgabe bearbeiten …"))
        else:
            self.title.setText(tr("Dieses Projekt enthält keine Aufgabe."))
            self.text.setPlainText(tr("Lehrkräfte können mit „Aufgabe stellen“ eine Aufgabenstellung und eine "
                                      "verschlüsselte Musterlösung in die Datei schreiben. Wer die Datei öffnet, sieht "
                                      "die Aufgabe hier."))
            self.edit_button.setText(tr("Aufgabe stellen …"))
        self.solution_button.setVisible(task.has_solution)
        self.edit_button.setEnabled(self._document is not None)

    def show_solution(self) -> None:
        task = self.current_task()
        if not task.has_solution:
            return
        password = ask_password(self, tr("Musterlösung"), tr("Passwort der Lehrkraft:"))
        if password is None:
            return
        try:
            solution = T.decrypt(task.solution, password)
        except T.WrongPassword:
            QMessageBox.warning(self, tr("Musterlösung"), tr("Das Passwort ist falsch."))
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("Musterlösung"))
        box.setText(solution)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()
