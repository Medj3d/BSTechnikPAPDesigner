"""Dialog: Code aus dem Programmablaufplan erzeugen."""

from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import LANGUAGES, generate, language_name
from app.i18n import N_, tr

# Endung und Name des Dateityps (deutscher Quelltext; angezeigt wird er mit ``tr(..., pattern=...)``)
EXTENSIONS = {"pseudo": (".txt", N_("Textdatei ({pattern})")), "python": (".py", N_("Python-Datei ({pattern})")),
              "java": (".java", N_("Java-Datei ({pattern})"))}


def monospace_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setFamilies(["Cascadia Mono", "Consolas", font.family()])
    font.setPointSizeF(10.0)
    return font


class CodeDialog(QDialog):
    def __init__(self, document, parent=None, language: str = "pseudo"):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle(tr("Code erzeugen"))
        self.resize(780, 640)
        try:
            self.programs = structure_diagram(FlowGraph.from_scene(document.scene))
        except Exception:  # Analyse darf den Dialog nie verhindern
            self.programs = []

        title = QLabel(tr("Code erzeugen"))
        title.setObjectName("DialogTitle")
        self.language = QComboBox()
        for key in LANGUAGES:
            self.language.addItem(language_name(key), key)
        self.language.setCurrentIndex(max(0, list(LANGUAGES).index(language) if language in LANGUAGES else 0))
        self.language.currentIndexChanged.connect(self.update_code)
        top = QHBoxLayout()
        top.addWidget(title, 1)
        top.addWidget(QLabel(tr("Sprache")))
        top.addWidget(self.language)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        # Programmtext wird immer von links nach rechts gelesen – auch in einer Oberfläche von rechts nach links
        self.editor.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.editor.setFont(monospace_font())
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.notes = QLabel("")
        self.notes.setObjectName("Muted")
        self.notes.setWordWrap(True)

        copy = QPushButton(tr("Kopieren"))
        copy.clicked.connect(self.copy_code)
        save = QPushButton(tr("Speichern …"))
        save.clicked.connect(self.save_code)
        close = QPushButton(tr("Schließen"))
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
            self.notes.setText(tr("Der Plan enthält kein Start-Element. Fügen Sie ein Start-Element hinzu und "
                                  "verbinden Sie es mit dem Ablauf."))
            return
        try:
            code = generate(self.programs, self.current_language, self.document.meta.name)
        except Exception as exc:  # pragma: no cover - Absicherung
            code = ""
            self.notes.setText(tr("Der Code konnte nicht erzeugt werden ({error}).", error=type(exc).__name__))
            self.editor.setPlainText(code)
            return
        self.editor.setPlainText(code)
        warnings = [w for program in self.programs for w in program.warnings]
        note = tr("Nicht erkannte Texte sind im Code als TODO markiert; nicht auswertbare Bedingungen "
                  "werden zur Laufzeit als Frage gestellt.")
        if warnings:
            note = tr("Hinweise: {warnings}", warnings=" ".join(dict.fromkeys(warnings))) + "\n" + note
        self.notes.setText(note)

    def copy_code(self) -> None:
        QApplication.clipboard().setText(self.code())

    def save_code(self) -> None:
        extension, filter_source = EXTENSIONS[self.current_language]
        file_filter = tr(filter_source, pattern=f"*{extension}")
        base = self.document.display_name
        if self.current_language == "java":
            match = re.search(r"public class (\w+)", self.code())
            base = match.group(1) if match else base
        directory = os.path.dirname(self.document.file_path) if self.document.file_path else ""
        path, _ = QFileDialog.getSaveFileName(self, tr("Code speichern"), os.path.join(directory, base + extension),
                                              file_filter)
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self.code())
        except OSError as exc:
            QMessageBox.warning(self, tr("Speichern nicht möglich"),
                                tr("Die Datei konnte nicht gespeichert werden:\n{error}", error=exc))
