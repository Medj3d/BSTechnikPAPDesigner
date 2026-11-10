"""Dock-Panel „Code“: zeigt beim Zeichnen sofort den passenden Code.

Die Ansicht ist zuschaltbar (Ansicht → Code-Ansicht). Sie aktualisiert sich verzögert nach jeder Änderung,
solange sie sichtbar ist. Ein Klick auf eine Codezeile markiert den Baustein, aus dem sie stammt; umgekehrt
werden die Zeilen der im Plan ausgewählten Bausteine hervorgehoben.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QTextCursor, QTextFormat
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget

from app import styles
from app.codegen.dialog import monospace_font
from app.codegen.generators import LANGUAGES, generate_traced, language_name
from app.i18n import tr


class CodePanel(QWidget):
    element_requested = Signal(str)   # Baustein-ID der angeklickten Zeile

    def __init__(self, parent=None, language: str = "python"):
        super().__init__(parent)
        self._document = None
        self._line_ids: list = []
        self._selected: set = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)

        self.language = QComboBox()
        for key in LANGUAGES:
            self.language.addItem(language_name(key), key)
        keys = list(LANGUAGES)
        self.language.setCurrentIndex(keys.index(language) if language in keys else 0)
        self.language.currentIndexChanged.connect(self.refresh)
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 4, 0)
        header.addWidget(QLabel(tr("Sprache")))
        header.addWidget(self.language, 1)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.editor.setFont(monospace_font())
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.editor.cursorPositionChanged.connect(self._on_cursor_moved)
        self.editor.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.editor.setToolTip(tr("Klick auf eine Zeile markiert den Baustein im Plan"))

        self.note = QLabel("")
        self.note.setObjectName("Muted")
        self.note.setWordWrap(True)
        self.note.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.note)
        self._updating = False

    # ------------------------------------------------------------ Dokument
    @property
    def current_language(self) -> str:
        return self.language.currentData()

    def set_language(self, key: str) -> None:
        keys = list(LANGUAGES)
        if key in keys:
            self.language.setCurrentIndex(keys.index(key))

    def set_document(self, document) -> None:
        if document is self._document:
            return
        if self._document is not None:
            try:
                self._document.content_changed.disconnect(self.schedule_refresh)
                self._document.pages_changed.disconnect(self.schedule_refresh)
                self._document.undo_stack.indexChanged.disconnect(self.schedule_refresh)
            except (RuntimeError, TypeError):
                pass
        self._document = document
        if document is not None:
            document.content_changed.connect(self.schedule_refresh)
            document.pages_changed.connect(self.schedule_refresh)
            document.undo_stack.indexChanged.connect(self.schedule_refresh)
        self.refresh()

    def schedule_refresh(self, *_args) -> None:
        if self.isVisible():
            self._timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()   # während sie verborgen war, wurde nicht mitgerechnet

    def refresh(self) -> None:
        self._timer.stop()
        document = self._document
        if document is None:
            self._set_code("", [], tr("Kein Projekt geöffnet."))
            return
        if not self.isVisible():
            return
        from app.analysis.structure import structure_diagram

        try:
            programs = structure_diagram(document.flow_graph())
        except Exception:  # die Ansicht darf die Bedienung nie stören
            programs = []
        if not programs:
            self._set_code("", [], tr("Der Plan enthält kein Start-Element. Fügen Sie ein Start-Element hinzu "
                                      "und verbinden Sie es mit dem Ablauf."))
            return
        try:
            code, ids = generate_traced(programs, self.current_language, document.meta.name)
        except Exception as exc:  # pragma: no cover - Absicherung
            self._set_code("", [], tr("Der Code konnte nicht erzeugt werden ({error}).", error=type(exc).__name__))
            return
        self._set_code(code, ids, "")

    def _set_code(self, code: str, ids: list, note: str) -> None:
        bar = self.editor.verticalScrollBar()
        position = bar.value()
        self._updating = True
        try:
            if self.editor.toPlainText() != code:
                self.editor.setPlainText(code)
                bar.setValue(position)   # beim Weiterzeichnen nicht jedes Mal nach oben springen
        finally:
            self._updating = False
        self._line_ids = ids
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self._highlight()

    def code(self) -> str:
        return self.editor.toPlainText()

    @property
    def line_ids(self) -> list:
        return list(self._line_ids)

    # ------------------------------------------------------------ Auswahl
    def show_selection(self, element_ids) -> None:
        """Hebt die Zeilen der im Plan ausgewählten Bausteine hervor."""
        self._selected = set(element_ids or ())
        self._highlight()
        rows = [row for row, eid in enumerate(self._line_ids) if eid in self._selected]
        if rows:
            block = self.editor.document().findBlockByNumber(rows[0])
            if block.isValid():
                # nur sichtbar machen, ohne den Textcursor (und damit die Auswahl im Plan) zu verändern
                top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
                if top < 0 or top > self.editor.viewport().height() - 20:
                    bar = self.editor.verticalScrollBar()
                    bar.setValue(max(0, rows[0] - 2))

    def _highlight(self) -> None:
        theme = styles.current_theme()
        color = QColor(theme.accent)
        color.setAlpha(60)
        selections = []
        for row, eid in enumerate(self._line_ids):
            if eid is None or eid not in self._selected:
                continue
            block = self.editor.document().findBlockByNumber(row)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = QTextCursor(block)
            selections.append(selection)
        self.editor.setExtraSelections(selections)

    def highlighted_rows(self) -> list[int]:
        return [selection.cursor.blockNumber() for selection in self.editor.extraSelections()]

    def _on_cursor_moved(self) -> None:
        if self._updating:
            return
        row = self.editor.textCursor().blockNumber()
        if 0 <= row < len(self._line_ids) and self._line_ids[row]:
            self.element_requested.emit(self._line_ids[row])

    def click_row(self, row: int) -> None:
        """Wie ein Klick auf die Zeile ``row`` (für Tests und die Tastatur)."""
        block = self.editor.document().findBlockByNumber(row)
        if block.isValid():
            self.editor.setTextCursor(QTextCursor(block))

    def refresh_theme(self) -> None:
        self._highlight()
