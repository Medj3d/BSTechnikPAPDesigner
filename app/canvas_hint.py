"""Leiser Tipp auf einer (fast) leeren Arbeitsfläche: welche Schreibweisen die Bausteine verstehen.

Der Tipp steht unten in der Arbeitsfläche, solange auf der angezeigten Seite nur Start und Ende liegen (oder noch
gar nichts), und verschwindet mit dem ersten weiteren Baustein; in der Präsentationsansicht bleibt er weg. Er ist ein eigenes kleines Fenster über der
Arbeitsfläche – kein Teil der Szene: Bild, PDF, Druck und „Als Bild kopieren“ zeigen ihn nie. Mausklicks gehen
durch ihn hindurch auf die Arbeitsfläche.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from app import notation, styles
from app.i18n import tr
from app.model.element_types import ElementType

MARGIN = 24          # Abstand zum unteren Rand der Arbeitsfläche (Pixel)
MAX_WIDTH = 560
MIN_AREA = (260, 160)   # in einer sehr kleinen Arbeitsfläche würde der Tipp den Plan verdecken
EMPTY_TYPES = (ElementType.START, ElementType.END)


def hint_text() -> str:
    from app.actions import clean_text   # (Menünamen genau wie im Menü, ohne „&“)

    return tr("Tipp: In Bausteinen lässt sich z. B. {example} schreiben – alle Schreibweisen unter {menu} → {entry}",
              example=notation.HINT_EXAMPLE, menu=clean_text(tr("&Hilfe")),
              entry=clean_text(tr("&Schreibweisen im Plan")))


def is_almost_empty(scene) -> bool:
    """Liegen auf der Seite höchstens Start und Ende?"""
    return all(item.element_type in EMPTY_TYPES for item in scene.elements())


class NotationHint(QWidget):
    def __init__(self, view):
        super().__init__(view)   # nicht im Viewport: Den verschiebt Qt beim Schwenken samt Kindern
        self._view = view
        self._text = hint_text()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(self._text)
        view.viewport().installEventFilter(self)
        self.hide()

    def text(self) -> str:
        return self._text

    def refresh(self) -> None:
        """Zeigt oder versteckt den Tipp passend zur angezeigten Seite."""
        scene = self._view.scene()
        area = self._view.viewport().geometry()
        # nicht in der Präsentationsansicht: Dort sieht die ganze Klasse den Plan am Beamer
        presenting = bool(getattr(self._view.window(), "presenting", False))
        wanted = scene is not None and hasattr(scene, "elements") and is_almost_empty(scene) and not presenting \
            and area.width() >= MIN_AREA[0] and area.height() >= MIN_AREA[1]
        if wanted:
            self.place()
            self.raise_()
        self.setVisible(bool(wanted))

    def place(self) -> None:
        area = self._view.viewport().geometry()
        width = max(1, min(MAX_WIDTH, area.width() - 2 * MARGIN))
        flags = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)
        height = self.fontMetrics().boundingRect(QRect(0, 0, width - 16, 10_000), flags, self._text).height() + 12
        self.setGeometry(area.left() + (area.width() - width) // 2, area.bottom() - MARGIN - height, width, height)

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self.refresh()   # z. B. Minikarte ein/aus: die Arbeitsfläche wird schmaler
        return False

    def paintEvent(self, _event) -> None:
        theme = styles.current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Hintergrund in der Farbe der Arbeitsfläche: Die Rasterpunkte laufen nicht durch die Schrift
        background = QColor(theme.canvas_bg)
        background.setAlphaF(0.92)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()), 6, 6)
        color = QColor(theme.text_muted)
        color.setAlphaF(0.85)   # leise, aber gut lesbar
        painter.setPen(color)
        painter.drawText(QRectF(self.rect()).adjusted(8, 0, -8, 0), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                         self._text)
        painter.end()
