"""Inline-Texteditor direkt auf der Arbeitsfläche.

Der Editor liegt exakt an der Stelle, an der der Text später im Baustein
dargestellt wird (gleiche Schrift, gleiche Umbruchbreite, gleiche
Ausrichtung). Der Baustein passt während der Eingabe live seine Größe an.

Tastenbelegung (verbindlich):

* Enter           → Text bestätigen und Editor schließen
* Shift + Enter   → Zeilenumbruch innerhalb des Bausteins (auch Strg + Enter wie im PapDesigner)
* Rechtsklick     → Ausschneiden, Kopieren, Einfügen und Sonderzeichen (≤ ≥ ≠ ² √ π …)
* „~“             → bedingter Trennstrich (sichtbar nur, wenn das Wort dort umbrochen wird)
* Esc             → Bearbeitung abbrechen
* Klick daneben   → Text bestätigen
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QTextCursor, QTextOption
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QMenu, QStyle, QStyleOptionGraphicsItem

from app import styles
from app.fileformat.serializer import storable_text
from app.i18n import N_, tr
from app.items.base_item import LAYER_OVERLAY

# Sonderzeichen für Formeln und Bedingungen (Zeichen, Beschreibung); Schreibtischtest und Code verstehen
# ≤ ≥ ≠ × · ÷ ² ³ und „←“ als Zuweisung
SPECIAL_CHARACTERS = (
    ("≤", N_("kleiner oder gleich")), ("≥", N_("größer oder gleich")), ("≠", N_("ungleich")),
    ("≈", N_("ungefähr gleich")), ("←", N_("Zuweisung")), ("→", N_("Pfeil")),
    ("×", N_("mal")), ("·", N_("mal (Punkt)")), ("÷", N_("geteilt durch")), ("±", N_("plus/minus")),
    ("²", N_("hoch 2")), ("³", N_("hoch 3")), ("√", N_("Wurzel")), ("π", N_("Pi")), ("∞", N_("unendlich")),
    ("∑", N_("Summe")), ("∧", N_("und")), ("∨", N_("oder")), ("¬", N_("nicht")), ("°", N_("Grad")),
    ("„“", N_("Anführungszeichen")), ("…", N_("Auslassungspunkte")), ("~", N_("bedingter Trennstrich")),
)

_EDITOR_KEYS_WITH_CTRL = {
    Qt.Key.Key_A, Qt.Key.Key_C, Qt.Key.Key_X, Qt.Key.Key_V, Qt.Key.Key_Z, Qt.Key.Key_Y,
    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home,
    Qt.Key.Key_End, Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Return, Qt.Key.Key_Enter,
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
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
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

    def insert_text(self, text: str) -> None:
        """Fügt Text an der Schreibmarke ein (z. B. ein Sonderzeichen); Anführungszeichen umschließen die Auswahl."""
        cursor = self.textCursor()
        if text == "„“":
            selected = cursor.selectedText()
            cursor.insertText(f"„{selected}“")
            if not selected:
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
        else:
            cursor.insertText(text)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu()
        cursor = self.textCursor()
        for label, shortcut, slot, enabled in (
                (tr("&Ausschneiden"), QKeySequence.StandardKey.Cut, self._cut, cursor.hasSelection()),
                (tr("&Kopieren"), QKeySequence.StandardKey.Copy, self._copy, cursor.hasSelection()),
                (tr("&Einfügen"), QKeySequence.StandardKey.Paste, self._paste, True),
                (tr("Alles au&swählen"), QKeySequence.StandardKey.SelectAll, self._select_all, True)):
            action = menu.addAction(label)
            action.setShortcut(QKeySequence(shortcut))
            action.setEnabled(enabled)
            action.triggered.connect(slot)
        menu.addSeparator()
        add_special_characters(menu.addMenu(tr("Sonderzeichen")), self.insert_text)
        menu.exec(event.screenPos())
        event.accept()

    def _copy(self) -> None:
        self._key(QKeySequence.StandardKey.Copy)

    def _cut(self) -> None:
        self._key(QKeySequence.StandardKey.Cut)

    def _paste(self) -> None:
        self._key(QKeySequence.StandardKey.Paste)

    def _select_all(self) -> None:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)

    def _key(self, sequence) -> None:
        """Löst die Standard-Bearbeitung des Textfelds aus (wie das passende Tastenkürzel)."""
        from PySide6.QtGui import QClipboard, QGuiApplication

        cursor = self.textCursor()
        board = QGuiApplication.clipboard()
        if sequence in (QKeySequence.StandardKey.Copy, QKeySequence.StandardKey.Cut) and cursor.hasSelection():
            board.setText(cursor.selectedText().replace("\u2029", "\n"), QClipboard.Mode.Clipboard)
            if sequence == QKeySequence.StandardKey.Cut:
                cursor.removeSelectedText()
        elif sequence == QKeySequence.StandardKey.Paste:
            cursor.insertText(normalize_text(board.text()) if board.text() else "")
        self.setFocus(Qt.FocusReason.OtherFocusReason)

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


def add_special_characters(menu: QMenu, insert) -> None:
    """Füllt ein Menü mit den Sonderzeichen; ``insert(text)`` fügt das gewählte ein."""
    for char, description in SPECIAL_CHARACTERS:
        shown = "„…“" if char == "„“" else char
        action = menu.addAction(f"{shown}\t{tr(description)}")
        action.triggered.connect(lambda _=False, c=char: insert(c))
