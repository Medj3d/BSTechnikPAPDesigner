"""Dialog: Struktogramm anzeigen und exportieren."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout)

from app import icons, styles
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.codegen.generators import with_title
from app.export import ExportError
from app.i18n import tr
from app.nsd.renderer import export_nsd, render_image

FORMATS = ("PNG", "SVG", "PDF")


def export_filters() -> dict[str, str]:
    """Dateitypen des Speichern-Dialogs in der eingestellten Sprache: Format → Filtertext."""
    return {"PNG": tr("PNG-Bild ({pattern})", pattern="*.png"),
            "SVG": tr("SVG-Grafik ({pattern})", pattern="*.svg"),
            "PDF": tr("PDF-Dokument ({pattern})", pattern="*.pdf")}


class StructogramDialog(QDialog):
    ZOOMS = (0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0)

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle(tr("Struktogramm"))
        self.resize(900, 720)
        try:
            programs = structure_diagram(FlowGraph.from_scene(document.scene))
        except Exception:
            programs = []
        self.programs = with_title(programs, document.meta.name)
        self._zoom_index = self.ZOOMS.index(1.0)

        title = QLabel(tr("Struktogramm (Nassi-Shneiderman)"))
        title.setObjectName("DialogTitle")
        zoom_out = QToolButton()
        zoom_out.setIcon(icons.icon("zoom_out"))
        zoom_out.setToolTip(tr("Verkleinern"))
        zoom_out.clicked.connect(lambda: self.set_zoom_index(self._zoom_index - 1))
        zoom_in = QToolButton()
        zoom_in.setIcon(icons.icon("zoom_in"))
        zoom_in.setToolTip(tr("Vergrößern"))
        zoom_in.clicked.connect(lambda: self.set_zoom_index(self._zoom_index + 1))
        self.zoom_label = QLabel("100 %")
        top = QHBoxLayout()
        top.addWidget(title, 1)
        top.addWidget(zoom_out)
        top.addWidget(self.zoom_label)
        top.addWidget(zoom_in)

        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {styles.current_theme().canvas_bg}; border: none; }}")
        # Strg+Mausrad über dem Struktogramm zoomt (sonst blättert die Bildlaufleiste)
        self.scroll.viewport().installEventFilter(self)

        self.notes = QLabel("")
        self.notes.setObjectName("Muted")
        self.notes.setWordWrap(True)

        export = QPushButton(tr("Exportieren …"))
        export.clicked.connect(self.export)
        export.setEnabled(bool(self.programs))
        close = QPushButton(tr("Schließen"))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.notes, 1)
        buttons.addWidget(export)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(self.scroll, 1)
        layout.addLayout(buttons)

        warnings = [w for program in self.programs for w in program.warnings]
        if not self.programs:
            self.notes.setText(tr("Der Plan enthält kein Start-Element – es gibt kein Struktogramm."))
        elif warnings:
            self.notes.setText(tr("Hinweise: {warnings}", warnings=" ".join(dict.fromkeys(warnings))))
        else:
            self.notes.setText(tr("Nicht strukturierte Teile des Plans werden gestrichelt dargestellt."))
        self.render()

    def set_zoom_index(self, index: int) -> None:
        self._zoom_index = max(0, min(len(self.ZOOMS) - 1, index))
        self.render()

    def _wheel_zoom(self, event) -> bool:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier or not event.angleDelta().y():
            return False
        self.set_zoom_index(self._zoom_index + (1 if event.angleDelta().y() > 0 else -1))
        event.accept()
        return True

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel and watched is self.scroll.viewport() and self._wheel_zoom(event):
            return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event) -> None:
        if not self._wheel_zoom(event):
            super().wheelEvent(event)

    def render(self) -> None:
        zoom = self.ZOOMS[self._zoom_index]
        self.zoom_label.setText(f"{round(zoom * 100)} %")
        if not self.programs:
            self.canvas.clear()
            return
        dpr = self.devicePixelRatioF()
        image = render_image(self.programs, styles.current_theme(), zoom * dpr)
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        self.canvas.setPixmap(pixmap)

    def export(self) -> None:
        base_dir = os.path.dirname(self.document.file_path) if self.document.file_path else ""
        suggestion = os.path.join(base_dir, tr("{name} – Struktogramm", name=self.document.display_name) + ".png")
        filters = export_filters()
        path, selected = QFileDialog.getSaveFileName(self, tr("Struktogramm exportieren"), suggestion,
                                                     ";;".join(filters.values()))
        if not path:
            return
        fmt = next((key for key, value in filters.items() if value == selected), None)
        extension = os.path.splitext(path)[1].lower().lstrip(".").upper()
        if extension in FORMATS:
            fmt = extension
        fmt = fmt or "PNG"
        if not path.lower().endswith("." + fmt.lower()):
            path += "." + fmt.lower()
        try:
            export_nsd(self.programs, path, fmt, styles.LIGHT)
        except ExportError as exc:
            QMessageBox.warning(self, tr("Export nicht möglich"), str(exc))
        except Exception:
            QMessageBox.warning(self, tr("Export nicht möglich"),
                                tr("Beim Export ist ein unerwarteter Fehler aufgetreten."))
