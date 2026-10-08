"""Ein geöffnetes Projekt (entspricht einem Tab).

Das Dokument verbindet Projektmetadaten, Diagrammeinstellungen, die Szene
und den Undo-Stapel. Ob ungespeicherte Änderungen vorliegen, ergibt sich aus
dem „clean“-Zustand des Undo-Stapels.
"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from app import config
from app.fileformat.serializer import load_diagram, save_diagram
from app.i18n import tr
from app.model.diagram import Diagram, ProjectMeta, now_iso
from app.scene import DiagramScene


def display_name_for_path(path: str) -> str:
    name = os.path.basename(path)
    if name.lower().endswith(config.FILE_EXTENSION.lower()):
        name = name[: -len(config.FILE_EXTENSION)]
    return name or path


class DiagramDocument(QObject):
    title_changed = Signal()
    modified_changed = Signal(bool)
    settings_changed = Signal()

    _untitled_counter = 0

    def __init__(self, diagram: Diagram | None = None, file_path: str | None = None, parent=None):
        super().__init__(parent)
        self._name_is_default = diagram is None
        if diagram is None:
            DiagramDocument._untitled_counter += 1
            diagram = Diagram()
            diagram.meta.name = tr("Unbenannt {number}", number=DiagramDocument._untitled_counter)
        self.meta: ProjectMeta = diagram.meta
        self.settings = diagram.settings
        self.file_path = file_path
        # False: Die geöffnete Datei enthielt keine gespeicherte Anordnung
        # (z. B. direkt aus dem PapDesigner) – sie wurde aus dem Raster abgeleitet.
        self.native_file = True
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(0)
        self.scene = DiagramScene(self.settings, self.undo_stack, self)
        self.load_warnings: list[str] = self.scene.load_content(diagram.elements, diagram.connections)
        self.undo_stack.setClean()
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        # liefert (zoom, center_x, center_y) der Ansicht für das Speichern
        self.view_state_provider: Callable[[], tuple] | None = None

    # ---------------------------------------------------------------- Status
    @property
    def is_modified(self) -> bool:
        return not self.undo_stack.isClean()

    @property
    def display_name(self) -> str:
        if self.file_path:
            return display_name_for_path(self.file_path)
        return self.meta.name

    def _on_clean_changed(self, clean: bool) -> None:
        self.modified_changed.emit(not clean)
        self.title_changed.emit()

    # ---------------------------------------------------------- Laden/Speichern
    @classmethod
    def open_file(cls, path: str, parent=None) -> "DiagramDocument":
        """Öffnet eine Projektdatei. Wirft ``ProjectFileError``."""
        result = load_diagram(path)
        document = cls(result.diagram, os.path.abspath(path), parent)
        document.load_warnings = result.warnings + document.load_warnings
        document.native_file = result.native
        return document

    def to_diagram(self) -> Diagram:
        if self.view_state_provider is not None:
            try:
                zoom, cx, cy = self.view_state_provider()
                self.settings.zoom = float(zoom)
                self.settings.view_center_x = float(cx)
                self.settings.view_center_y = float(cy)
            except Exception:
                pass
        return Diagram(meta=self.meta.copy(), settings=self.settings.copy(),
                       elements=self.scene.element_data(), connections=self.scene.connection_data())

    def save(self, path: str) -> None:
        """Speichert das Projekt. Wirft ``ProjectFileError``."""
        self.scene.commit_edit()
        path = os.path.abspath(path)
        old_modified, old_name = self.meta.modified, self.meta.name
        self.meta.modified = now_iso()
        if self._name_is_default:
            self.meta.name = display_name_for_path(path)
        try:
            save_diagram(self.to_diagram(), path)
        except Exception:
            self.meta.modified, self.meta.name = old_modified, old_name
            raise
        self._name_is_default = False
        self.file_path = path
        self.native_file = True
        self.undo_stack.setClean()
        self.title_changed.emit()

    # -------------------------------------------------------- Eigenschaften
    def apply_properties(self, meta: ProjectMeta, grid_size: int) -> None:
        if meta.name != self.meta.name:
            self._name_is_default = False
        self.meta = meta
        self.settings.grid_size = int(grid_size)
        self.settings_changed.emit()
        self.title_changed.emit()

    def set_grid_visible(self, visible: bool) -> None:
        self.settings.grid_visible = bool(visible)
        self.settings_changed.emit()

    def set_snap_to_grid(self, enabled: bool) -> None:
        self.settings.snap_to_grid = bool(enabled)
        self.settings_changed.emit()
