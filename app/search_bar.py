"""Suchleiste: findet Funktionen, Einstellungen und Bausteine im Plan.

Das Feld steht in der Werkzeugleiste (Strg+K); die Treffer erscheinen in einer Liste darunter. Die Liste ist ein
Kindfenster des Hauptfensters und kein Popup – so bleibt der Fokus beim Tippen im Feld.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from app.i18n import tr
from app.search_text import score

MAX_RESULTS = 14
FIELD_WIDTH = 240
LIST_WIDTH = 420
ROW_HEIGHT = 30


@dataclass
class SearchEntry:
    title: str
    detail: str
    run: Callable[[], None]
    # weiterer Suchtext, der nicht angezeigt wird (z. B. die Beschreibung einer Funktion)
    keywords: str = ""


class SearchBar(QLineEdit):
    def __init__(self, provider: Callable[[], list], window):
        super().__init__(window)
        self.provider = provider
        self.setObjectName("SearchBar")
        self.setPlaceholderText(tr("Suchen …"))
        self.setClearButtonEnabled(True)
        self.setFixedWidth(FIELD_WIDTH)
        self.entries: list[SearchEntry] = []
        self.popup = QFrame(window)
        self.popup.setObjectName("SearchResults")
        self.popup.setFrameShape(QFrame.Shape.StyledPanel)
        self.results = QListWidget(self.popup)
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.results)
        self.popup.hide()
        self.results.itemClicked.connect(lambda _item: self.run_current())
        self.textChanged.connect(self._update_results)
        self.returnPressed.connect(self.run_current)
        window.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Resize and self.popup.isVisible():
            self._place_popup()
        return super().eventFilter(watched, event)

    def open(self) -> None:
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.selectAll()
        self._update_results()

    def close_results(self) -> None:
        self.popup.hide()

    def _update_results(self) -> None:
        query = self.text().strip()
        self.results.clear()
        self.entries = []
        if not query:
            self.popup.hide()
            return
        ranked = []
        for order, entry in enumerate(self.provider()):
            rank = score(query, entry.title, entry.keywords)
            if rank is not None:
                ranked.append((rank, order, entry))
        ranked.sort(key=lambda found: found[:2])
        self.entries = [entry for _rank, _order, entry in ranked[:MAX_RESULTS]]
        for entry in self.entries:
            text = f"{entry.title}    {entry.detail}" if entry.detail else entry.title
            self.results.addItem(QListWidgetItem(text))
        if not self.entries:
            self.results.addItem(QListWidgetItem(tr("Nichts gefunden")))
            self.results.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        else:
            self.results.setCurrentRow(0)
        self._place_popup()
        self.popup.show()
        self.popup.raise_()

    def _place_popup(self) -> None:
        window = self.popup.parentWidget()
        anchor = self.mapTo(window, QPoint(self.width(), self.height() + 2))
        height = min(max(1, self.results.count()), MAX_RESULTS) * ROW_HEIGHT + 6
        left = max(4, anchor.x() - LIST_WIDTH)
        self.popup.setGeometry(left, anchor.y(), LIST_WIDTH, height)

    def run_current(self) -> None:
        row = self.results.currentRow()
        if self.popup.isHidden() or not 0 <= row < len(self.entries):
            return
        entry = self.entries[row]
        self.popup.hide()
        self.clear()
        self.parentWidget().setFocus(Qt.FocusReason.OtherFocusReason)
        entry.run()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.popup.hide()
            self.clear()
            self.parentWidget().setFocus(Qt.FocusReason.OtherFocusReason)
            event.accept()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.entries:
            step = 1 if key == Qt.Key.Key_Down else -1
            self.results.setCurrentRow((self.results.currentRow() + step) % len(self.entries))
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        # Ein Klick in die Trefferliste nimmt dem Feld den Fokus nicht; alles andere schließt die Liste
        self.popup.hide()
        super().focusOutEvent(event)
