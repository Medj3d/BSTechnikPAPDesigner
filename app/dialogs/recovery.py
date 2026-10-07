"""Dialog: ungespeicherte Projekte nach einem Absturz wiederherstellen."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem,
                               QVBoxLayout)


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return value or "–"


class RecoveryDialog(QDialog):
    """Ergebnis: ``Accepted`` (ausgewählte wiederherstellen), ``DISCARD_ALL`` (bewusst
    verwerfen) oder ``Rejected`` (Esc/Schließen – Sicherungen bleiben erhalten)."""

    DISCARD_ALL = 2

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Projekte wiederherstellen")
        self.setMinimumWidth(520)
        self._entries = list(entries)

        title = QLabel("Projekte wiederherstellen")
        title.setObjectName("DialogTitle")
        text = QLabel("Das Programm wurde nicht ordnungsgemäß beendet. Folgende ungespeicherte "
                      "Projekte können wiederhergestellt werden:")
        text.setWordWrap(True)

        self.list = QListWidget()
        for entry in self._entries:
            location = entry.original_path or "(noch nicht gespeichert)"
            item = QListWidgetItem(f"{entry.display_name}\n{location} · gesichert {_format_time(entry.saved_at)}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list.addItem(item)

        hint = QLabel("Nicht ausgewählte Sicherungen werden verworfen.")
        hint.setObjectName("Muted")

        buttons = QDialogButtonBox()
        restore = buttons.addButton("Wiederherstellen", QDialogButtonBox.ButtonRole.AcceptRole)
        restore.setDefault(True)
        discard = buttons.addButton("Alle verwerfen", QDialogButtonBox.ButtonRole.DestructiveRole)
        discard.clicked.connect(lambda: self.done(self.DISCARD_ALL))
        later = buttons.addButton("Später", QDialogButtonBox.ButtonRole.RejectRole)
        later.setToolTip("Nichts wiederherstellen; beim nächsten Start erneut anbieten")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(text)
        layout.addWidget(self.list, 1)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def selected_entries(self) -> list:
        return [entry for index, entry in enumerate(self._entries)
                if self.list.item(index).checkState() == Qt.CheckState.Checked]
