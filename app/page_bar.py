"""Seitenleiste unter der Arbeitsfläche: Hauptprogramm und Unterprogramme des Projekts.

Ein Reiter je Seite (wie die Tabellenblätter einer Tabellenkalkulation).
Klick wechselt die Seite, Doppelklick benennt ein Unterprogramm um, Ziehen
sortiert die Unterprogramme um. Das Kontextmenü bietet Umbenennen,
Duplizieren, Kopieren, Ausschneiden, Einfügen, Verschieben und Löschen und
zeigt, wo ein Unterprogramm aufgerufen wird; „+ Unterprogramm“ legt eine
neue Seite an.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QMenu, QTabBar, QToolButton, QWidget

from app import icons, subprograms
from app.i18n import N_, tr
from app.model.element_types import ElementType

# Befehle des Kontextmenüs (Name für ``action_requested``, Text); None = Trennlinie
PAGE_COMMANDS = (
    ("duplicate_page", N_("Duplizieren")),
    ("copy_page", N_("Kopieren")),
    ("cut_page", N_("Ausschneiden")),
    None,
    ("move_page_left", N_("Nach links verschieben")),
    ("move_page_right", N_("Nach rechts verschieben")),
)


class PageBar(QWidget):
    page_selected = Signal(int)
    add_requested = Signal()
    rename_requested = Signal(int)
    delete_requested = Signal(int)
    # (Befehl, Seite): „duplicate_page“, „copy_page“, „cut_page“, „paste_page“, „move_page_left“ …
    action_requested = Signal(str, int)
    # Seite an eine andere Stelle gezogen: (von, nach)
    move_requested = Signal(int, int)
    # ein Aufruf aus „Aufgerufen von“: (Seite, Baustein)
    caller_requested = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._document = None
        self._updating = False

        self.tabs = QTabBar()
        self.tabs.setObjectName("PageTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        # Unterprogramme lassen sich per Ziehen umsortieren (das Hauptprogramm bleibt vorn)
        self.tabs.setMovable(True)
        self.tabs.tabMoved.connect(self._on_tab_moved)
        self.tabs.installEventFilter(self)
        # Ziehen eines Reiters: die gedrückte Seite (Index beim letzten Aufbau) und ob schon etwas verschoben wurde.
        # Jeder Reiter trägt den Index seiner Seite als Daten mit; daran ist nach dem Loslassen die neue Reihenfolge
        # ablesbar, gleich in welcher Folge Qt die Nachbarn beim Ziehen verschoben hat.
        self._pressed: int | None = None
        self._moved = False
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.currentChanged.connect(self._on_current_changed)
        self.tabs.tabBarDoubleClicked.connect(self._on_double_clicked)
        self.tabs.customContextMenuRequested.connect(self._on_context_menu)

        self.add_button = QToolButton()
        self.add_button.setObjectName("PageAddButton")
        self.add_button.setText(tr("+ Unterprogramm"))
        self.add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add_button.setIconSize(QSize(16, 16))
        self.add_button.setIcon(icons.element_icon(ElementType.SUBPROGRAM))
        self.add_button.setToolTip(tr("Neues Unterprogramm auf einer eigenen Seite anlegen (Strg+Umschalt+U)"))
        self.add_button.clicked.connect(self.add_requested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        layout.addWidget(self.tabs, 0)
        layout.addWidget(self.add_button, 0)
        layout.addStretch(1)

    # ------------------------------------------------------------ Dokument
    def set_document(self, document) -> None:
        if document is self._document:
            self.refresh()
            return
        if self._document is not None:
            for signal, slot in self._connections(self._document):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self._document = document
        if document is not None:
            for signal, slot in self._connections(document):
                signal.connect(slot)
        self.refresh()

    def _connections(self, document):
        # Namen folgen dem Start-Element: auch Textänderungen (Rückgängig-Schritte) aktualisieren die Reiter
        return ((document.pages_changed, self.refresh), (document.current_page_changed, self.refresh),
                (document.undo_stack.indexChanged, self.refresh))

    def refresh(self, *_args) -> None:
        document = self._document
        self._updating = True
        try:
            if document is None:
                while self.tabs.count():
                    self.tabs.removeTab(0)
                self.add_button.setEnabled(False)
                return
            self.add_button.setEnabled(True)
            names = [page.display_name for page in document.pages]
            while self.tabs.count() > len(names):
                self.tabs.removeTab(self.tabs.count() - 1)
            while self.tabs.count() < len(names):
                self.tabs.addTab("")
            for index, (page, name) in enumerate(zip(document.pages, names)):
                if self.tabs.tabText(index) != name:
                    self.tabs.setTabText(index, name)
                if page.is_main:
                    tip = tr("Hauptprogramm – hier beginnt der Ablauf")
                    icon = icons.element_icon(ElementType.START)
                else:
                    tip = tr("Unterprogramm „{name}“ – Doppelklick zum Umbenennen, Rechtsklick für weitere "
                             "Befehle", name=name)
                    icon = icons.element_icon(ElementType.SUBPROGRAM)
                self.tabs.setTabToolTip(index, tip)
                self.tabs.setTabData(index, index)
                self.tabs.setTabIcon(index, icon)
            self.tabs.setCurrentIndex(document.current_page_index)
        finally:
            self._updating = False

    def refresh_theme(self) -> None:
        self.add_button.setIcon(icons.element_icon(ElementType.SUBPROGRAM))
        self.refresh()

    # ------------------------------------------------------------ Bedienung
    def _on_current_changed(self, index: int) -> None:
        if not self._updating and not self._moved and index >= 0:
            self.page_selected.emit(index)

    def _on_tab_moved(self, _source: int, _target: int) -> None:
        if not self._updating:
            self._moved = True

    def eventFilter(self, watched, event) -> bool:
        if watched is self.tabs:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                index = self.tabs.tabAt(event.position().toPoint())
                self._pressed = self.tabs.tabData(index) if index >= 0 else None
                self._moved = False
            elif event.type() == QEvent.Type.MouseButtonRelease and self._moved:
                # erst wenn Qt das Loslassen selbst verarbeitet hat, steht die Reihenfolge der Reiter fest
                QTimer.singleShot(0, self._finish_drag)
        return super().eventFilter(watched, event)

    def _finish_drag(self) -> None:
        """Nach dem Ziehen eines Reiters: die Seite an die neue Stelle verschieben (ein Rückgängig-Schritt).
        Das Hauptprogramm bleibt vorn; wer davor abgelegt wird, landet an zweiter Stelle."""
        source, self._pressed, self._moved = self._pressed, None, False
        order = [self.tabs.tabData(index) for index in range(self.tabs.count())]
        if isinstance(source, int) and source > 0 and source in order:
            target = max(1, order.index(source))
            if target != source:
                self.move_requested.emit(source, target)
        self.refresh()

    def _on_double_clicked(self, index: int) -> None:
        if index > 0:
            self.rename_requested.emit(index)

    def _on_context_menu(self, pos) -> None:
        index = self.tabs.tabAt(pos)
        document = self._document
        if document is None:
            return
        menu = QMenu(self)
        if index > 0:
            page = document.pages[index]
            rename = menu.addAction(tr("Umbenennen …"))
            rename.triggered.connect(lambda: self.rename_requested.emit(index))
            for entry in PAGE_COMMANDS:
                if entry is None:
                    menu.addSeparator()
                    continue
                name, label = entry
                action = menu.addAction(tr(label))
                action.setEnabled(name != "move_page_left" or index > 1)
                action.setEnabled(action.isEnabled() and (name != "move_page_right" or index < self.tabs.count() - 1))
                action.triggered.connect(lambda _=False, n=name: self.action_requested.emit(n, index))
            self._add_callers(menu, document, page)
            menu.addSeparator()
            delete = menu.addAction(icons.icon("delete"), tr("Löschen"))
            delete.triggered.connect(lambda: self.delete_requested.emit(index))
            menu.addSeparator()
        elif index == 0:
            copy = menu.addAction(tr("Kopieren"))
            copy.setToolTip(tr("Das Hauptprogramm als Seite kopieren – z. B. um es in einem anderen Projekt als "
                               "Unterprogramm einzufügen"))
            copy.triggered.connect(lambda: self.action_requested.emit("copy_page", 0))
            menu.addSeparator()
        add = menu.addAction(icons.element_icon(ElementType.SUBPROGRAM), tr("Neues Unterprogramm …"))
        add.triggered.connect(self.add_requested)
        paste = menu.addAction(tr("Seite einfügen"))
        paste.setEnabled(subprograms.can_paste_page())
        paste.triggered.connect(lambda: self.action_requested.emit("paste_page", max(index, 0)))
        menu.setToolTipsVisible(True)
        menu.exec(self.tabs.mapToGlobal(pos))

    def _add_callers(self, menu: QMenu, document, page) -> None:
        """Untermenü „Aufgerufen von“: alle Unterprogramm-Bausteine, die diese Seite aufrufen."""
        calls = subprograms.callers(document, page)
        sub = menu.addMenu(tr("Aufgerufen von ({n})", n=len(calls)))
        sub.setEnabled(bool(calls))
        for other, item in calls:
            text = " ".join(item.data.text.split())
            action = sub.addAction(icons.element_icon(ElementType.SUBPROGRAM),
                                   f"{other.display_name}: {text}")
            action.triggered.connect(lambda _=False, p=other, it=item: self.caller_requested.emit(p, it))
