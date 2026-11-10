"""Haltepunkte für den Schreibtischtest.

Ein Haltepunkt liegt auf einem Baustein. „Ausführen“ (F5) und „Abspielen“ (F6) halten an, bevor ein Baustein mit
Haltepunkt ausgeführt wird. Haltepunkte gehören zur laufenden Sitzung (``document.breakpoints``) und werden
nicht in der Projektdatei gespeichert. Auf dem Baustein zeigt ein roter Punkt oben links den Haltepunkt; in Bildern,
PDF und Ausdruck erscheint er nicht.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

BREAKPOINT_COLOR = "#e05252"
RADIUS = 6.0


class BreakpointMarker(QGraphicsItem):
    """Roter Punkt an der oberen linken Ecke eines Bausteins (Kind des Bausteins, wandert mit)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity, True)
        self.setZValue(1000)
        self.place()

    def place(self) -> None:
        rect = self.parentItem().local_rect()
        self.setPos(rect.left() + 2, rect.top() + 2)

    def boundingRect(self) -> QRectF:
        return QRectF(-RADIUS - 1.5, -RADIUS - 1.5, 2 * RADIUS + 3, 2 * RADIUS + 3)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        scene = self.scene()
        if scene is not None and getattr(scene, "exporting", False):
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.setBrush(QColor(BREAKPOINT_COLOR))
        painter.drawEllipse(QRectF(-RADIUS, -RADIUS, 2 * RADIUS, 2 * RADIUS))


def _marker(item) -> BreakpointMarker | None:
    return next((child for child in item.childItems() if isinstance(child, BreakpointMarker)), None)


def breakpoints_of(document) -> set:
    if not hasattr(document, "breakpoints"):
        document.breakpoints = set()
    return document.breakpoints


def has_breakpoint(document, element_id: str) -> bool:
    return element_id in breakpoints_of(document)


def toggle(document, element_ids) -> bool:
    """Schaltet die Haltepunkte der Bausteine um: Haben alle schon einen, werden sie entfernt, sonst gesetzt.

    Gibt zurück, ob die Bausteine danach einen Haltepunkt haben.
    """
    points = breakpoints_of(document)
    ids = [eid for eid in element_ids if eid]
    if not ids:
        return False
    switch_on = not all(eid in points for eid in ids)
    for eid in ids:
        if switch_on:
            points.add(eid)
        else:
            points.discard(eid)
    refresh_markers(document)
    return switch_on


def clear(document) -> None:
    breakpoints_of(document).clear()
    refresh_markers(document)


def refresh_markers(document) -> None:
    """Bringt die roten Punkte in Einklang mit ``document.breakpoints`` (z. B. nach Rückgängig)."""
    points = breakpoints_of(document)
    for page in document.pages:
        for item in page.scene.elements():
            marker = _marker(item)
            if item.element_id in points:
                if marker is None:
                    BreakpointMarker(item)
                else:
                    marker.place()
            elif marker is not None:
                marker.setParentItem(None)
                if marker.scene() is not None:
                    marker.scene().removeItem(marker)
    # Gelöschte Bausteine bleiben in ``points``: nach „Rückgängig“ ist ihr Haltepunkt wieder da
