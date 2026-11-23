"""Einstellungen: Schalter, Auswahlfelder, Knöpfe und frei belegbare Tastenkürzel.

Jede Änderung gilt sofort. Jede Funktion kann auf zwei Tasten liegen; ist eine Taste schon vergeben, wechselt sie
zur neuen Funktion, denn Qt führt eine doppelt belegte Taste sonst gar nicht aus.

Was man nur einmal einstellt (Farbschema, Sprache, Speichern, Updates, Dateityp, Werkzeugleiste), steht nur hier und
nicht in den Menüs. Die Schalter kommen aus der Befehlsliste (``ActionRegistry``); Auswahlfelder, Knöpfe und
Schalter, die zum Fenster gehören, beschreibt das Hauptfenster mit ``Choice``, ``Button`` und ``Toggle``
(``MainWindow.settings_options``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGroupBox,
                               QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget, QListWidget,
                               QStackedWidget)

from app import config, preferences
from app.actions import clean_text, sequence_text
from app.i18n import N_, tr
from app.search_text import matches

KEY_SLOTS = 2

# Felder, die das Hauptfenster beschreibt (siehe ``MainWindow.settings_options``)
THEME = "option_theme"
LANGUAGE = "option_language"
REGISTER_FILETYPE = "option_register_filetype"
TOOLBAR = "option_toolbar"


@dataclass
class Choice:
    """Auswahlfeld (z. B. Farbschema, Sprache). Die Texte sind schon übersetzt."""
    key: str
    text: str
    tip: str
    items: Sequence[tuple[str, str]]      # (Wert, Beschriftung)
    current: Callable[[], str]
    choose: Callable[[str], None]
    changed: object = None                # Signal mit dem neuen Wert: hält die Auswahl aktuell


@dataclass
class Button:
    """Knopf, der etwas einmalig erledigt (z. B. den Dateityp registrieren)."""
    key: str
    text: str
    tip: str
    run: Callable[[], None]


@dataclass
class Toggle:
    """Ein/Aus-Schalter, der zum Fenster gehört (z. B. „Werkzeugleiste anzeigen“)."""
    key: str
    text: str
    tip: str
    action: QAction
    default: bool = True


def _layout(sections: dict[str, list[str]]):
    """Bereiche und Gruppen des Fensters: (Bereich, ((Gruppe, (Name, …)), …))."""
    return (
        (N_("Allgemein"), ((N_("Darstellung"), (THEME, LANGUAGE)),
                           (N_("Speichern"), ("auto_save", "backup_on_save")),
                           (N_("Updates"), ("check_updates_on_start",)),
                           (N_("Dateityp"), (REGISTER_FILETYPE,)))),
        (N_("Zeichnen"), ((preferences.SECTION_NEW, sections[preferences.SECTION_NEW]),
                          (preferences.SECTION_ARROWS, sections[preferences.SECTION_ARROWS]))),
        (N_("Prüfung"), ((preferences.SECTION_CHECKS, sections[preferences.SECTION_CHECKS]),)),
        (N_("Werkzeugleiste"), ((N_("Anzeige"), (TOOLBAR,)),
                                (preferences.SECTION_TOOLS, sections[preferences.SECTION_TOOLS]))),
    )


class ChoiceBox(QComboBox):
    """Auswahlfeld eines ``Choice``; folgt Änderungen von außen (z. B. dem Knopf in der Werkzeugleiste)."""

    def __init__(self, option: Choice, parent=None):
        super().__init__(parent)
        self.option = option
        for value, label in option.items:
            self.addItem(label, value)
        self.sync()
        self.activated.connect(self._chosen)   # nur eine Auswahl durch den Benutzer, nicht sync()
        if option.changed is not None:
            option.changed.connect(self.sync)   # Methode eines QObject: beim Löschen trennt Qt die Verbindung

    def value(self) -> str:
        return self.currentData()

    def sync(self, *_args) -> None:
        index = self.findData(self.option.current())
        if index >= 0 and index != self.currentIndex():
            self.blockSignals(True)
            self.setCurrentIndex(index)
            self.blockSignals(False)

    def choose(self, value: str) -> None:
        """Wie eine Auswahl mit der Maus."""
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)
            self._chosen(index)

    def _chosen(self, index: int) -> None:
        self.option.choose(self.itemData(index))
        self.sync()   # z. B. abgelehnt: wieder den tatsächlichen Wert zeigen


class SettingSwitch(QCheckBox):
    """Ein/Aus-Schalter, der einem Befehl folgt (Häkchen und „abgeschaltet“, z. B. Updates von der Schul-IT)."""

    def __init__(self, action: QAction, text: str, parent=None):
        super().__init__(text, parent)
        self.action = action
        self.setObjectName("SettingSwitch")   # fett und etwas größer: die Funktion, darunter gedämpft die Erklärung
        self.setChecked(action.isChecked())
        self.setEnabled(action.isEnabled())
        # Methoden eines QObject: Qt trennt die Verbindungen, wenn das Fenster gelöscht wird
        action.changed.connect(self._follow)
        action.toggled.connect(self.setChecked)
        # „trigger“ löst wie ein Klick im Menü alles aus, was an der Einstellung hängt
        self.clicked.connect(self._trigger)

    def _follow(self) -> None:
        self.setEnabled(self.action.isEnabled())

    def _trigger(self, _checked: bool = False) -> None:
        self.action.trigger()


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
    """Einstellungen: links die Bereiche, rechts ihre Felder; oben ein Suchfeld über alles (auch Tastenkürzel)."""

    shortcuts_changed = Signal()

    def __init__(self, actions, parent=None, show_shortcuts: bool = False, options: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.resize(760, 600)
        self.actions = actions
        if options is None:
            provider = getattr(parent, "settings_options", None)
            options = provider() if callable(provider) else {}
        self.options: dict = dict(options)   # Name → Choice, Button oder Toggle
        title = QLabel(tr("Einstellungen"))
        title.setObjectName("DialogTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Einstellungen und Tastenkürzel durchsuchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.switches: dict[str, QCheckBox] = {}   # Schalter aus der Befehlsliste
        self.toggles: dict[str, QCheckBox] = {}    # Schalter des Fensters (Toggle)
        self.choices: dict[str, ChoiceBox] = {}
        self.buttons: dict[str, QPushButton] = {}
        self._choice_labels: dict[str, QLabel] = {}
        self._holders: dict[str, QWidget] = {}
        self._groups: list[tuple[QGroupBox, list[str]]] = []
        self.pages = QStackedWidget()
        self.sections = QListWidget()
        self.sections.setObjectName("SettingsSections")
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        self._page_fields: list[list[str]] = []   # je Bereich die Namen seiner Felder (für die Suche)
        sections: dict[str, list[str]] = {}
        for preference in preferences.PREFERENCES:
            sections.setdefault(preference.section, []).append(preferences.action_name(preference.name))
        for page_title, groups in _layout(sections):
            self._add_page(tr(page_title), groups)
        self.shortcut_table = ShortcutTable(actions)
        self.shortcut_table.changed.connect(self.shortcuts_changed)
        self.shortcut_table.search.hide()   # gesucht wird oben, für alle Bereiche zugleich
        self.pages.addWidget(self.shortcut_table)
        self.sections.addItem(tr("Tastenkürzel"))
        self._page_titles = [self.sections.item(row).text() for row in range(self.sections.count())]
        self._fit_sections()
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
        reset.setToolTip(tr("Alle Schalter wieder auf den Standard stellen (Farbschema, Sprache und Tastenkürzel "
                            "bleiben)"))
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
        # Kein Knopf ist Standardknopf: Enter im Suchfeld löst sonst den ersten Knopf aus (z. B. „Dateityp
        # registrieren“ oder „Alle zurücksetzen“ bei den Tastenkürzeln)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        QTimer.singleShot(0, self.search.setFocus)

    # ------------------------------------------------------------ Aufbau
    def _fit_sections(self) -> None:
        """Bereichsliste so breit, dass auch „Werkzeugleiste (12)“ ohne Bildlaufleiste hineinpasst."""
        self.sections.ensurePolished()   # Schrift und Abstände aus dem Stylesheet
        metrics = self.sections.fontMetrics()
        widest = max(metrics.horizontalAdvance(f"{title} (99)") for title in self._page_titles)
        self.sections.setFixedWidth(max(170, widest + 44))   # Abstände der Einträge, der Liste und Rahmen
        self.sections.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sections.setTextElideMode(Qt.TextElideMode.ElideRight)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Nach einem Wechsel des Farbschemas rechnet Qt die Lage der Einträge sonst mit den alten Höhen: Sie stünden
        # übereinander, die Markierung verdeckte den Nachbarn
        self.sections.doItemsLayout()

    def _available(self, name: str) -> bool:
        """Felder des Fensters nur, wenn es sie beschreibt (z. B. Dateityp nur, wo das geht)."""
        if name in self.options:
            return True
        return not name.startswith("option_") and self.actions.get(name) is not None

    def _add_page(self, page_title: str, groups) -> None:
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(10)
        names_on_page = []
        for heading, names in groups:
            names = [name for name in names if self._available(name)]
            if not names:
                continue
            box = QGroupBox(tr(heading))
            inner = QVBoxLayout(box)
            inner.setSpacing(6)
            for name in names:
                inner.addWidget(self._field(name))
            self._align_labels(names)
            column.addWidget(box)
            self._groups.append((box, names))
            names_on_page += names
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages.addWidget(scroll)
        self.sections.addItem(page_title)
        self._page_fields.append(names_on_page)

    def _field(self, name: str) -> QWidget:
        """Ein Feld mit seiner Erklärung darunter."""
        option = self.options.get(name)
        if isinstance(option, Choice):
            return self._holder(name, self._choice(option), option.tip, indent=False)
        if isinstance(option, Button):
            return self._holder(name, self._button(option), option.tip, indent=False)
        if isinstance(option, Toggle):
            box = self._check_box(option.action, option.text)
            self.toggles[name] = box
            return self._holder(name, box, option.tip, indent=True)
        action = self.actions[name]
        box = self._check_box(action, clean_text(action.text()))
        self.switches[name] = box
        return self._holder(name, box, action.statusTip(), indent=True)

    def _holder(self, name: str, widget: QWidget, tip_text: str, indent: bool) -> QWidget:
        tip = QLabel(tip_text)
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        tip.setContentsMargins(26 if indent else 0, 0, 0, 4)
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        column.addWidget(widget)
        column.addWidget(tip)
        self._holders[name] = holder
        return holder

    @staticmethod
    def _check_box(action: QAction, text: str) -> QCheckBox:
        return SettingSwitch(action, text)

    def _choice(self, option: Choice) -> QWidget:
        label = QLabel(option.text)
        label.setObjectName("SettingLabel")
        box = ChoiceBox(option)
        box.setAccessibleName(option.text)
        label.setBuddy(box)
        self.choices[option.key] = box
        self._choice_labels[option.key] = label
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(label)
        line.addWidget(box)
        line.addStretch(1)
        return row

    def _align_labels(self, names: list[str]) -> None:
        """Auswahlfelder einer Gruppe beginnen alle an derselben Stelle (Beschriftungen gleich breit)."""
        labels = [self._choice_labels[name] for name in names if name in self._choice_labels]
        if len(labels) < 2:
            return
        for label in labels:
            label.ensurePolished()   # erst dann gilt die fette Schrift aus dem Stylesheet
        width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(width)

    def _button(self, option: Button) -> QWidget:
        button = QPushButton(option.text)
        button.clicked.connect(lambda _checked=False: option.run())
        self.buttons[option.key] = button
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(button)
        line.addStretch(1)
        return row

    def _texts(self, name: str) -> tuple:
        """Wonach ein Feld gefunden wird: Beschriftung, Erklärung und bei Auswahlfeldern alle Werte."""
        option = self.options.get(name)
        if option is None:
            action = self.actions[name]
            return clean_text(action.text()), action.statusTip()
        texts = (clean_text(option.text), option.tip)
        if isinstance(option, Choice):
            texts += tuple(label for _value, label in option.items)
        return texts

    # ------------------------------------------------------------ Suche
    def _filter(self, text: str) -> None:
        """Blendet nicht Passendes aus; Bereiche zeigen die Zahl der Treffer, der erste mit Treffern wird gewählt."""
        query = text.strip()
        counts = []
        for names in self._page_fields:
            shown = 0
            for name in names:
                visible = not query or matches(query, *self._texts(name))
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
        """Alle Ein/Aus-Schalter (auch „Werkzeugleiste anzeigen“) auf den Standard.

        Farbschema und Sprache sind Auswahlfelder und bleiben, wie sie sind – ein Sprachwechsel bräuchte außerdem
        einen Neustart. Die Tastenkürzel bleiben ebenso.
        """
        defaults = {preferences.action_name(p.name): p.default for p in preferences.PREFERENCES}
        defaults.update({"auto_save": config.AUTO_SAVE_DEFAULT, "backup_on_save": config.BACKUP_ON_SAVE_DEFAULT,
                         "check_updates_on_start": True})
        for name, default in defaults.items():
            action = self.actions.get(name)
            if action is not None and action.isChecked() != default:
                action.trigger()   # wie ein Klick: alles, was an der Einstellung hängt, folgt
        for option in self.options.values():
            if isinstance(option, Toggle) and option.action.isChecked() != option.default:
                option.action.trigger()
