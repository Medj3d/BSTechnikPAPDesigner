"""Einstellungen: Ein/Aus-Schalter und frei belegbare Tastenkürzel.

Jede Änderung gilt sofort. Jede Funktion kann auf zwei Tasten liegen; ist eine Taste schon vergeben, wechselt sie
zur neuen Funktion, denn Qt führt eine doppelt belegte Taste sonst gar nicht aus.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QKeySequenceEdit, QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget, QListWidget, QStackedWidget)

from app import config, preferences
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
    """Einstellungen: links die Bereiche, rechts ihre Schalter; oben ein Suchfeld über alles (auch Tastenkürzel)."""

    shortcuts_changed = Signal()

    def __init__(self, actions, parent=None, show_shortcuts: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.resize(760, 600)
        self.actions = actions
        title = QLabel(tr("Einstellungen"))
        title.setObjectName("DialogTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Einstellungen und Tastenkürzel durchsuchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.switches: dict[str, QCheckBox] = {}
        self._holders: dict[str, QWidget] = {}
        self._groups: list[tuple[QGroupBox, list[str]]] = []
        self.pages = QStackedWidget()
        self.sections = QListWidget()
        self.sections.setObjectName("SettingsSections")
        self.sections.setFixedWidth(170)
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        self._page_switches: list[list[str]] = []
        sections: dict[str, list[str]] = {}
        for preference in preferences.PREFERENCES:
            sections.setdefault(preference.section, []).append(preferences.action_name(preference.name))
        for page_title, groups in (
                (N_("Allgemein"), [_GENERAL, _UPDATES]),
                (N_("Zeichnen"), [(preferences.SECTION_NEW, sections[preferences.SECTION_NEW]),
                                  (preferences.SECTION_ARROWS, sections[preferences.SECTION_ARROWS])]),
                (N_("Prüfung"), [(preferences.SECTION_CHECKS, sections[preferences.SECTION_CHECKS])]),
                (N_("Werkzeugleiste"), [(preferences.SECTION_TOOLS, sections[preferences.SECTION_TOOLS])])):
            self._add_switch_page(tr(page_title), groups)
        self.shortcut_table = ShortcutTable(actions)
        self.shortcut_table.changed.connect(self.shortcuts_changed)
        self.shortcut_table.search.hide()   # gesucht wird oben, für alle Bereiche zugleich
        self.pages.addWidget(self.shortcut_table)
        self.sections.addItem(tr("Tastenkürzel"))
        self._page_titles = [self.sections.item(row).text() for row in range(self.sections.count())]
        self.sections.setCurrentRow(self.sections.count() - 1 if show_shortcuts else 0)

        self.empty = QLabel(tr("Nichts gefunden."))
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self.sections)
        right = QVBoxLayout()
        right.addWidget(self.pages, 1)
        right.addWidget(self.empty, 1)
        body.addLayout(right, 1)

        reset = QPushButton(tr("Alle Schalter zurücksetzen"))
        reset.setToolTip(tr("Alle Schalter wieder auf den Standard stellen (Tastenkürzel bleiben)"))
        reset.clicked.connect(self.reset_switches)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Schließen"))
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.search)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)
        QTimer.singleShot(0, self.search.setFocus)

    # ------------------------------------------------------------ Aufbau
    def _add_switch_page(self, page_title: str, groups) -> None:
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(10)
        names_on_page = []
        for heading, names in groups:
            box = QGroupBox(tr(heading))
            inner = QVBoxLayout(box)
            inner.setSpacing(6)
            for name in names:
                inner.addWidget(self._switch(name))
            column.addWidget(box)
            self._groups.append((box, list(names)))
            names_on_page += list(names)
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages.addWidget(scroll)
        self.sections.addItem(page_title)
        self._page_switches.append(names_on_page)

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
        tip.setContentsMargins(26, 0, 0, 4)
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        column.addWidget(box)
        column.addWidget(tip)
        self._holders[name] = holder
        return holder

    # ------------------------------------------------------------ Suche
    def _filter(self, text: str) -> None:
        """Blendet nicht Passendes aus; Bereiche zeigen die Zahl der Treffer, der erste mit Treffern wird gewählt."""
        query = text.strip()
        counts = []
        for names in self._page_switches:
            shown = 0
            for name in names:
                action = self.actions[name]
                visible = not query or matches(query, clean_text(action.text()), action.statusTip())
                self._holders[name].setVisible(visible)
                shown += visible
            counts.append(shown)
        for box, names in self._groups:
            box.setVisible(any(not self._holders[name].isHidden() for name in names))
        self.shortcut_table.search.setText(query)
        table = self.shortcut_table.table
        counts.append(sum(1 for row in range(table.rowCount()) if not table.isRowHidden(row)))
        for row, count in enumerate(counts):
            item = self.sections.item(row)
            item.setText(f"{self._page_titles[row]} ({count})" if query else self._page_titles[row])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled if (count or not query)
                          else item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        found = [row for row, count in enumerate(counts) if count]
        self.empty.setVisible(bool(query) and not found)
        self.pages.setVisible(not (query and not found))
        if query and found and counts[self.sections.currentRow()] == 0:
            self.sections.setCurrentRow(found[0])

    def reset_switches(self) -> None:
        defaults = {preferences.action_name(p.name): p.default for p in preferences.PREFERENCES}
        defaults.update({"auto_save": config.AUTO_SAVE_DEFAULT, "backup_on_save": config.BACKUP_ON_SAVE_DEFAULT,
                         "check_updates_on_start": True})
        for name, default in defaults.items():
            action = self.actions.get(name)
            if action is not None and action.isChecked() != default:
                action.trigger()   # wie ein Klick: alles, was an der Einstellung hängt, folgt
