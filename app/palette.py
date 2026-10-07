"""Werkzeugpalette mit den PAP-Bausteinen.

Jeder Eintrag zeigt eine Vorschau der echten Bausteinform. Ein Baustein
kann per Drag & Drop auf die Arbeitsfläche gezogen oder per Klick eingefügt
werden (unterhalb des ausgewählten Bausteins bzw. in der Bildmitte).
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app import styles
from app.canvas import ELEMENT_MIME_TYPE
from app.items.shapes import geometry_for, paint_shape, render_shape_pixmap
from app.model.element_types import (FLOW_TERMINALS, LOOP_BEGIN, LOOP_END, LOOP_PART_KEY,
                                     PALETTE_ORDER, ElementType, spec_for)

PREVIEW_WIDTH = 58.0
PREVIEW_HEIGHT = 30.0


class PaletteEntry(QWidget):
    """Ein Eintrag der Palette: Formvorschau + Bezeichnung."""

    activated = Signal(object)

    def __init__(self, element_type: ElementType, parent=None):
        super().__init__(parent)
        self.element_type = ElementType(element_type)
        self.spec = spec_for(self.element_type)
        self._hovered = False
        self._pressed_pos: QPoint | None = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"<b>{self.spec.display_name}</b><br>{self.spec.description}<br><br>"
                        "Auf die Arbeitsfläche ziehen oder klicken zum Einfügen.")
        self.setAccessibleName(self.spec.display_name)

    def sizeHint(self) -> QSize:
        return QSize(170, 44)

    def paintEvent(self, event) -> None:
        theme = styles.current_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(6, 2, -6, -2)
        if self._hovered:
            p.setPen(QPen(QColor(theme.border_strong), 1))
            p.setBrush(QColor(theme.panel_raised))
            p.drawRoundedRect(rect, 6, 6)

        # Formvorschau
        p.save()
        preview_center_x = rect.left() + 12 + PREVIEW_WIDTH / 2
        p.translate(preview_center_x, rect.center().y())
        geometry = geometry_for(self.element_type)
        colors = theme.element_colors(self.element_type)
        w, h = PREVIEW_WIDTH, PREVIEW_HEIGHT
        if self.element_type is ElementType.DECISION:
            w, h = 44.0, 32.0
        elif self.element_type in FLOW_TERMINALS:
            w, h = 52.0, 22.0
        if self.element_type is ElementType.LOOP:
            # Schleifenbeginn und -ende übereinander
            half = 13.0
            p.translate(0, -half / 2 - 1.5)
            paint_shape(p, geometry, w, half, colors, {LOOP_PART_KEY: LOOP_BEGIN}, 1.3)
            p.translate(0, half + 3)
            paint_shape(p, geometry, w, half, colors, {LOOP_PART_KEY: LOOP_END}, 1.3)
        else:
            paint_shape(p, geometry, w, h, colors, None, 1.3)
        p.restore()

        # Bezeichnung
        p.setPen(QColor(theme.text if self.isEnabled() else theme.text_disabled))
        text_rect = rect.adjusted(12 + PREVIEW_WIDTH + 14, 0, -4, 0)
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   self.spec.display_name)
        p.end()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed_pos = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pressed_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._pressed_pos).manhattanLength() < QApplication.startDragDistance():
            return
        self._pressed_pos = None
        self._start_drag()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed_pos is not None:
            self._pressed_pos = None
            if self.rect().contains(event.position().toPoint()):
                self.activated.emit(self.element_type)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        mime = QMimeData()
        mime.setData(ELEMENT_MIME_TYPE, self.element_type.value.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        dpr = self.devicePixelRatioF()
        spec = self.spec
        props = {LOOP_PART_KEY: LOOP_BEGIN} if self.element_type is ElementType.LOOP else None
        pixmap = render_shape_pixmap(self.element_type, spec.default_width, spec.default_height,
                                     styles.current_theme(), dpr, scale=0.6, props=props, opacity=0.8)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(int(pixmap.width() / dpr / 2), int(pixmap.height() / dpr / 2)))
        drag.exec(Qt.DropAction.CopyAction)


class ToolPalette(QWidget):
    """Kompakte Liste aller Bausteine."""

    element_activated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PaletteWidget")
        self.entries: list[PaletteEntry] = []

        content = QWidget()
        content.setObjectName("PaletteWidget")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(0)
        layout.addWidget(self._section("BAUSTEINE"))
        for element_type in PALETTE_ORDER:
            layout.addWidget(self._entry(element_type))
        layout.addWidget(self._section("ABLAUF"))
        for element_type in FLOW_TERMINALS:
            layout.addWidget(self._entry(element_type))
        layout.addStretch(1)
        hint = QLabel("Ziehen oder klicken zum Einfügen.\n"
                      "Verbinden: vom Anschlusspunkt auf Baustein oder Pfeil ziehen.\n"
                      "Rot = möglicherweise falsche Verbindung.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        hint.setContentsMargins(12, 8, 8, 4)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setMinimumWidth(168)

    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("PaletteSection")
        return label

    def _entry(self, element_type: ElementType) -> PaletteEntry:
        entry = PaletteEntry(element_type)
        entry.activated.connect(self.element_activated.emit)
        self.entries.append(entry)
        return entry

    def set_entries_enabled(self, enabled: bool) -> None:
        for entry in self.entries:
            entry.setEnabled(enabled)
