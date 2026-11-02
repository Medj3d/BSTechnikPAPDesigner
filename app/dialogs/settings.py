"""Einstellungen: Ein/Aus-Schalter und frei belegbare Tastenkürzel.

Jede Änderung gilt sofort. Jede Funktion kann auf zwei Tasten liegen; ist eine Taste schon vergeben, wechselt sie
zur neuen Funktion, denn Qt führt eine doppelt belegte Taste sonst gar nicht aus.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QKeySequenceEdit, QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from app import preferences
from app.actions import clean_text, sequence_text
from app.i18n import N_, tr
from app.search_text import matches

KEY_SLOTS = 2
# Schalter, die es schon vor diesem Fenster als Menüeintrag gab
_GENERAL = (N_("Speichern"), ("auto_save", "backup_on_save"))
_UPDATES = (N_("Updates"), ("check_updates_on_start",))


class KeyEdit(QKeySequenceEdit):
    """Eingabefeld für genau eine Taste (mit Umschalt, Strg, Alt)."""

    def __init__(self, sequence: QKeySequence | None = None, parent=None):
        super().__init__(sequence or QKeySequence(), parent)
        self.setMaximumSequenceLength(1)
        self.setClearButtonEnabled(True)
        field = self.findChild(QLineEdit)
        if field is not None:
            field.setPlaceholderText(tr("Taste drücken"))


class ShortcutTable(QWidget):
    """Liste aller Funktionen mit ihren beiden Tasten, durchsuchbar."""

    changed = Signal()

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.names = actions.bindable()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Funktion oder Taste suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.table = QTableWidget(len(self.names), KEY_SLOTS + 2)
        self.table.setHorizontalHeaderLabels([tr("Funktion"), tr("Taste 1"), tr("Taste 2"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, KEY_SLOTS + 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, 150)
        header.setSectionResizeMode(KEY_SLOTS + 1, QHeaderView.ResizeMode.ResizeToContents)
        self.edits: dict[str, list[KeyEdit]] = {}
        for row, name in enumerate(self.names):
            self.table.setItem(row, 0, QTableWidgetItem(clean_text(actions[name].text())))
            edits = [KeyEdit() for _ in range(KEY_SLOTS)]
            self.edits[name] = edits
            for slot, edit in enumerate(edits):
                self.table.setCellWidget(row, slot + 1, edit)
                edit.editingFinished.connect(lambda n=name: self._assign(n))
                edit.keySequenceChanged.connect(lambda _sequence, e=edit, n=name: self._on_cleared(e, n))
            reset = QToolButton()
            reset.setText("↺")
            reset.setToolTip(tr("Standard dieser Funktion wiederherstellen"))
            reset.clicked.connect(lambda _=False, n=name: self._reset_one(n))
            self.table.setCellWidget(row, KEY_SLOTS + 1, reset)
        self.notice = QLabel()
        self.notice.setObjectName("Muted")
        self.notice.setWordWrap(True)
        reset_all = QPushButton(tr("Alle zurücksetzen"))
        reset_all.clicked.connect(self._reset_all)
        bottom = QHBoxLayout()
        bottom.addWidget(self.notice, 1)
        bottom.addWidget(reset_all)
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self) -> None:
        for name, edits in self.edits.items():
            sequences = self.actions[name].shortcuts()
            for slot, edit in enumerate(edits):
                edit.blockSignals(True)
                edit.setKeySequence(sequences[slot] if slot < len(sequences) else QKeySequence())
                edit.blockSignals(False)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        for row, name in enumerate(self.names):
            keys = " ".join(sequence_text(sequence) for sequence in self.actions[name].shortcuts())
            self.table.setRowHidden(row, not matches(text, self.table.item(row, 0).text(), keys))

    def _on_cleared(self, edit: KeyEdit, name: str) -> None:
        if edit.keySequence().isEmpty():
            self._assign(name)

    def _assign(self, name: str) -> None:
        sequences = [edit.keySequence() for edit in self.edits[name] if not edit.keySequence().isEmpty()]
        moved = self.actions.assign(name, sequences)
        if moved:
            self.notice.setText(tr("„{key}“ lag auf „{name}“ und wurde dort entfernt.", key=sequence_text(moved[0][0]),
                                   name=clean_text(self.actions[moved[0][1]].text())))
        else:
            self.notice.clear()
        self.refresh()
        self.changed.emit()

    def _reset_one(self, name: str) -> None:
        self.actions.assign(name, self.actions.default_shortcuts(name))
        self.notice.clear()
        self.refresh()
        self.changed.emit()

    def _reset_all(self) -> None:
        self.actions.reset_shortcuts()
        self.notice.clear()
        self.refresh()
        self.changed.emit()


class SettingsDialog(QDialog):
    shortcuts_changed = Signal()

    def __init__(self, actions, parent=None, show_shortcuts: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.resize(680, 640)
        self.actions = actions
        title = QLabel(tr("Einstellungen"))
        title.setObjectName("DialogTitle")
        self.tabs = QTabWidget()
        self.tabs.addTab(self._switches_page(), tr("Schalter"))
        self.shortcut_table = ShortcutTable(actions)
        self.shortcut_table.changed.connect(self.shortcuts_changed)
        self.tabs.addTab(self.shortcut_table, tr("Tastenkürzel"))
        if show_shortcuts:
            self.tabs.setCurrentWidget(self.shortcut_table)
            QTimer.singleShot(0, self.shortcut_table.search.setFocus)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Schließen"))
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

    def _switches_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        sections: dict[str, list[str]] = {}
        for preference in preferences.PREFERENCES:
            sections.setdefault(preference.section, []).append(preferences.action_name(preference.name))
        groups = [*sections.items(), _GENERAL, _UPDATES]
        self.switches: dict[str, QCheckBox] = {}
        for heading, names in groups:
            box = QGroupBox(tr(heading))
            inner = QVBoxLayout(box)
            for name in names:
                inner.addWidget(self._switch(name))
            layout.addWidget(box)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _switch(self, name: str) -> QWidget:
        action = self.actions[name]
        box = QCheckBox(clean_text(action.text()))
        box.setChecked(action.isChecked())
        # „trigger“ löst wie ein Klick im Menü alles aus, was an der Einstellung hängt
        box.clicked.connect(lambda _checked=False: action.trigger())
        action.toggled.connect(box.setChecked)
        self.switches[name] = box
        tip = QLabel(action.statusTip())
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        tip.setContentsMargins(24, 0, 0, 6)
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        column.addWidget(box)
        column.addWidget(tip)
        return holder
