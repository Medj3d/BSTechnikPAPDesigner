"""Inline-Texteditor direkt auf der Arbeitsfläche.

Der Editor liegt exakt an der Stelle, an der der Text später im Baustein
dargestellt wird (gleiche Schrift, gleiche Umbruchbreite, gleiche
Ausrichtung). Der Baustein passt während der Eingabe live seine Größe an.

Tastenbelegung (verbindlich):

* Enter           → Text bestätigen und Editor schließen
* Shift + Enter   → Zeilenumbruch innerhalb des Bausteins
* Esc             → Bearbeitung abbrechen
* Klick daneben   → Text bestätigen
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor, QTextOption
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyle, QStyleOptionGraphicsItem

from app import styles
from app.fileformat.serializer import storable_text
from app.items.base_item import LAYER_OVERLAY

_EDITOR_KEYS_WITH_CTRL = {
    Qt.Key.Key_A, Qt.Key.Key_C, Qt.Key.Key_X, Qt.Key.Key_V, Qt.Key.Key_Z, Qt.Key.Key_Y,
    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home,
    Qt.Key.Key_End, Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
}


def normalize_text(text: str) -> str:
    """Vereinheitlicht Zeilenumbrüche und entfernt überflüssige Leerzeilen am Rand."""
    text = text.replace(" ", "\n").replace(" ", "\n").replace("\r\n", "\n")
    # Zeichen, die eine Projektdatei nicht aufnehmen kann (Steuerzeichen aus
    # eingefügtem Text), sofort ersetzen bzw. entfernen: Angezeigt wird nur,
    # was auch gespeichert wird.
    text = storable_text(text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip("\n")


class InlineTextEditor(QGraphicsTextItem):
    def __init__(self, font: QFont, layout_width: float, alignment: Qt.AlignmentFlag,
                 on_change: Callable[[str], None], on_finish: Callable[[bool, str], None]):
        super().__init__()
        self._on_change = on_change
        self._on_finish = on_finish
        self._finished = False
        self.setFont(font)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setZValue(LAYER_OVERLAY + 10)
        self.setDefaultTextColor(QColor(styles.current_theme().element_text))
        document = self.document()
        document.setDocumentMargin(0)
        document.setUseDesignMetrics(True)
        option = QTextOption(alignment)
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        option.setUseDesignMetrics(True)
        document.setDefaultTextOption(option)
        self.setTextWidth(layout_width)
        document.contentsChanged.connect(self._contents_changed)

    # -------------------------------------------------------------- Inhalt
    def plain_text(self) -> str:
        return normalize_text(self.toPlainText())

    def set_initial_text(self, text: str, select_all: bool) -> None:
        self.document().blockSignals(True)
        self.setPlainText(text)
        self.document().blockSignals(False)
        cursor = self.textCursor()
        if select_all:
            cursor.select(QTextCursor.SelectionType.Document)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def content_height(self) -> float:
        return self.document().size().height()

    def _contents_changed(self) -> None:
        if not self._finished:
            self._on_change(self.toPlainText())

    def finish(self, commit: bool) -> None:
        if self._finished:
            return
        self._finished = True
        self._on_finish(commit, self.plain_text())

    # -------------------------------------------------------------- Events
    def sceneEvent(self, event) -> bool:
        # Tasten, die der Editor selbst benötigt, dürfen nicht von
        # Menü-Tastenkürzeln (Entf, Strg+A, Strg+Z, Esc, ...) abgefangen werden.
        if event.type() == QEvent.Type.ShortcutOverride:
            mods = event.modifiers()
            ctrl_or_alt = mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
            if not ctrl_or_alt or event.key() in _EDITOR_KEYS_WITH_CTRL:
                event.accept()
                return True
        return super().sceneEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.textCursor().insertText("\n")
            else:
                self.finish(True)
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.finish(False)
            event.accept()
            return
        if key == Qt.Key.Key_Tab:
            self.finish(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if event.reason() in (Qt.FocusReason.PopupFocusReason, Qt.FocusReason.ActiveWindowFocusReason):
            return
        self.finish(True)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = QRectF(QPointF(0, 0), self.document().size()).adjusted(-6, -4, 6, 4)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(styles.current_theme().selection), 1.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        background = QColor(styles.current_theme().canvas_bg)
        background.setAlphaF(0.35)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 3.0, 3.0)
        # Qt würde sonst zusätzlich einen gestrichelten Fokusrahmen zeichnen
        plain = QStyleOptionGraphicsItem(option)
        plain.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus)
        super().paint(painter, plain, widget)

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-8, -6, 8, 6)
