"""Seitenleiste unter der Arbeitsfläche: Hauptprogramm und Unterprogramme des Projekts.

Ein Reiter je Seite (wie die Tabellenblätter einer Tabellenkalkulation).
Klick wechselt die Seite, Doppelklick benennt ein Unterprogramm um, das
Kontextmenü bietet Umbenennen und Löschen; „+ Unterprogramm“ legt eine neue
Seite an.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QMenu, QTabBar, QToolButton, QWidget

from app import icons
from app.i18n import tr
from app.model.element_types import ElementType


class PageBar(QWidget):
    page_selected = Signal(int)
    add_requested = Signal()
    rename_requested = Signal(int)
    delete_requested = Signal(int)

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
                self.tabs.setTabIcon(index, icon)
            self.tabs.setCurrentIndex(document.current_page_index)
        finally:
            self._updating = False

    def refresh_theme(self) -> None:
        self.add_button.setIcon(icons.element_icon(ElementType.SUBPROGRAM))
        self.refresh()

    # ------------------------------------------------------------ Bedienung
    def _on_current_changed(self, index: int) -> None:
        if not self._updating and index >= 0:
            self.page_selected.emit(index)

    def _on_double_clicked(self, index: int) -> None:
        if index > 0:
            self.rename_requested.emit(index)

    def _on_context_menu(self, pos) -> None:
        index = self.tabs.tabAt(pos)
        menu = QMenu(self)
        if index > 0:
            rename = menu.addAction(tr("Umbenennen …"))
            rename.triggered.connect(lambda: self.rename_requested.emit(index))
            delete = menu.addAction(icons.icon("delete"), tr("Löschen"))
            delete.triggered.connect(lambda: self.delete_requested.emit(index))
            menu.addSeparator()
        add = menu.addAction(icons.element_icon(ElementType.SUBPROGRAM), tr("Neues Unterprogramm …"))
        add.triggered.connect(self.add_requested)
        menu.exec(self.tabs.mapToGlobal(pos))
