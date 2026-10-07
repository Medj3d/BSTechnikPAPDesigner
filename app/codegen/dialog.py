"""Dialog: Code aus dem Programmablaufplan erzeugen."""

from __future__ import annotations

import os
import re

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import LANGUAGES, generate

EXTENSIONS = {"pseudo": (".txt", "Textdatei (*.txt)"), "python": (".py", "Python-Datei (*.py)"),
              "java": (".java", "Java-Datei (*.java)")}


def monospace_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setFamilies(["Cascadia Mono", "Consolas", font.family()])
    font.setPointSizeF(10.0)
    return font


class CodeDialog(QDialog):
    def __init__(self, document, parent=None, language: str = "pseudo"):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Code erzeugen")
        self.resize(780, 640)
        try:
            self.programs = structure_diagram(FlowGraph.from_scene(document.scene))
        except Exception:  # Analyse darf den Dialog nie verhindern
            self.programs = []

        title = QLabel("Code erzeugen")
        title.setObjectName("DialogTitle")
        self.language = QComboBox()
        for key, label in LANGUAGES.items():
            self.language.addItem(label, key)
        self.language.setCurrentIndex(max(0, list(LANGUAGES).index(language) if language in LANGUAGES else 0))
        self.language.currentIndexChanged.connect(self.update_code)
        top = QHBoxLayout()
        top.addWidget(title, 1)
        top.addWidget(QLabel("Sprache"))
        top.addWidget(self.language)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setFont(monospace_font())
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.notes = QLabel("")
        self.notes.setObjectName("Muted")
        self.notes.setWordWrap(True)

        copy = QPushButton("Kopieren")
        copy.clicked.connect(self.copy_code)
        save = QPushButton("Speichern …")
        save.clicked.connect(self.save_code)
        close = QPushButton("Schließen")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(copy)
        buttons.addWidget(save)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.notes)
        layout.addLayout(buttons)
        self.update_code()

    @property
    def current_language(self) -> str:
        return self.language.currentData()

    def code(self) -> str:
        return self.editor.toPlainText()

    def update_code(self) -> None:
        if not self.programs:
            self.editor.setPlainText("")
            self.notes.setText("Der Plan enthält kein Start-Element. Fügen Sie ein Start-Element hinzu und "
                               "verbinden Sie es mit dem Ablauf.")
            return
        try:
            code = generate(self.programs, self.current_language, self.document.meta.name)
        except Exception as exc:  # pragma: no cover - Absicherung
            code = ""
            self.notes.setText(f"Der Code konnte nicht erzeugt werden ({type(exc).__name__}).")
            self.editor.setPlainText(code)
            return
        self.editor.setPlainText(code)
        warnings = [w for program in self.programs for w in program.warnings]
        note = "Nicht erkannte Texte sind im Code als TODO markiert; nicht auswertbare Bedingungen " \
               "werden zur Laufzeit als Frage gestellt."
        if warnings:
            note = "Hinweise: " + " ".join(dict.fromkeys(warnings)) + "\n" + note
        self.notes.setText(note)

    def copy_code(self) -> None:
        QApplication.clipboard().setText(self.code())

    def save_code(self) -> None:
        extension, file_filter = EXTENSIONS[self.current_language]
        base = self.document.display_name
        if self.current_language == "java":
            match = re.search(r"public class (\w+)", self.code())
            base = match.group(1) if match else base
        directory = os.path.dirname(self.document.file_path) if self.document.file_path else ""
        path, _ = QFileDialog.getSaveFileName(self, "Code speichern", os.path.join(directory, base + extension),
                                              file_filter)
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self.code())
        except OSError as exc:
            QMessageBox.warning(self, "Speichern nicht möglich", f"Die Datei konnte nicht gespeichert werden:\n{exc}")
