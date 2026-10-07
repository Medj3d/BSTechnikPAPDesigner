"""Dialog: Über das Programm."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from app import config, icons


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Über {config.APP_NAME}")
        self.setMinimumWidth(440)

        logo = QLabel()
        logo.setPixmap(icons.render_app_icon(72))
        logo.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(config.APP_NAME)
        title.setObjectName("DialogTitle")
        # Version und Erscheinungsmonat dieser Version
        version = QLabel(f"Version {config.APP_VERSION} · {config.APP_RELEASE_DATE}")
        version.setObjectName("Muted")
        authors = QLabel(f"Ein Programm von {' und '.join(config.APP_AUTHORS)}\nfür die BS Technik")
        authors.setWordWrap(True)
        description = QLabel(
            "Editor für Programmablaufpläne (PAP) nach klassischer Notation.\n\n"
            "Bausteine: Start, Ende, Eingabe, Ausgabe, Vorgang, Unterprogramm, "
            "Verzweigung, Schleife und Kommentar.\n\n"
            f"Projektdateien: *{config.FILE_EXTENSION}")
        description.setWordWrap(True)
        tech = QLabel(f"Python {platform.python_version()} · PySide6 {PySide6.__version__} · Qt {qVersion()}")
        tech.setObjectName("Muted")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        text_layout.addWidget(title)
        text_layout.addWidget(version)
        text_layout.addSpacing(8)
        text_layout.addWidget(authors)
        text_layout.addSpacing(8)
        text_layout.addWidget(description)
        text_layout.addSpacing(8)
        text_layout.addWidget(tech)

        top = QHBoxLayout()
        top.setSpacing(18)
        top.addWidget(logo)
        top.addLayout(text_layout, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.addLayout(top)
        layout.addSpacing(10)
        layout.addWidget(buttons)
