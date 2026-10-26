"""Befehle für die Seiten eines Projekts (Unterprogramme anlegen, löschen, umbenennen)."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from app.i18n import tr


class AddPageCommand(QUndoCommand):
    """Fügt eine Unterprogramm-Seite hinzu und zeigt sie an.

    Die Seite (mit ihrer Szene) wird vorher erzeugt und bleibt erhalten, damit
    weitere Befehle desselben Schritts (z. B. Start und Ende einfügen) sie
    über ihre Szene erreichen.
    """

    def __init__(self, document, page, index: int | None = None, text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Unterprogramm anlegen"), parent)
        self._document = document
        self.page = page
        self._index = len(document.pages) if index is None else index

    def redo(self) -> None:
        self._document.insert_page(self._index, self.page)

    def undo(self) -> None:
        self._document.remove_page(self.page)


class RemovePageCommand(QUndoCommand):
    """Entfernt eine Unterprogramm-Seite samt Inhalt; Rückgängig stellt sie an derselben Stelle wieder her."""

    def __init__(self, document, page, text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Unterprogramm löschen"), parent)
        self._document = document
        self.page = page
        self._index = document.page_index(page)

    def redo(self) -> None:
        index = self._document.remove_page(self.page)
        if index > 0:
            self._index = index

    def undo(self) -> None:
        self._document.insert_page(self._index, self.page)


class RenamePageCommand(QUndoCommand):
    """Ändert den gespeicherten Namen einer Seite (die Texte von Start und Aufrufen ändern eigene Befehle)."""

    def __init__(self, document, page, old_name: str, new_name: str, text: str | None = None, parent=None):
        super().__init__(text if text is not None else tr("Unterprogramm umbenennen"), parent)
        self._document = document
        self.page = page
        self._old = old_name
        self._new = new_name

    def _apply(self, name: str) -> None:
        self.page.name = name
        self._document.pages_changed.emit()

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)
