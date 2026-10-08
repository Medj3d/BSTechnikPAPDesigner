"""Dialog: Über das Programm."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from app import config, i18n, icons
from app.i18n import tr
from app.model.element_types import ElementType, display_name_for


def _author_names() -> str:
    """Die Urheber als Aufzählung in der eingestellten Sprache („A und B“, „A, B und C“)."""
    names = list(config.APP_AUTHORS)
    if len(names) < 2:
        return "".join(names)
    return tr("{first} und {last}", first=", ".join(names[:-1]), last=names[-1])


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Über {name}", name=config.APP_NAME))
        self.setMinimumWidth(440)

        logo = QLabel()
        logo.setPixmap(icons.render_app_icon(72))
        logo.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(config.APP_NAME)
        title.setObjectName("DialogTitle")
        # Version und Erscheinungsmonat dieser Version
        version = QLabel(tr("Version {version} · {date}", version=config.APP_VERSION,
                            date=i18n.release_date_text()))
        version.setObjectName("Muted")
        authors = QLabel(tr("Ein Programm von {authors}\nfür die BS Technik", authors=_author_names()))
        authors.setWordWrap(True)
        # Die Bausteinnamen kommen aus der Bausteintabelle: so stimmen sie mit denen der Werkzeugpalette überein
        blocks = tr("Bausteine: {start}, {end}, {input}, {output}, {process}, {subprogram}, {decision}, "
                    "{loop} und {comment}.",
                    start=display_name_for(ElementType.START), end=display_name_for(ElementType.END),
                    input=display_name_for(ElementType.INPUT), output=display_name_for(ElementType.OUTPUT),
                    process=display_name_for(ElementType.PROCESS),
                    subprogram=display_name_for(ElementType.SUBPROGRAM),
                    decision=display_name_for(ElementType.DECISION), loop=display_name_for(ElementType.LOOP),
                    comment=display_name_for(ElementType.COMMENT))
        description = QLabel("\n\n".join([
            tr("Editor für Programmablaufpläne (PAP) nach klassischer Notation."),
            blocks,
            tr("Projektdateien: *{extension}", extension=config.FILE_EXTENSION)]))
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
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Schließen"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.addLayout(top)
        layout.addSpacing(10)
        layout.addWidget(buttons)
