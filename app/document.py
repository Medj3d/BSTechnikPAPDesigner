"""Ein geöffnetes Projekt (entspricht einem Tab).

Das Dokument verbindet Projektmetadaten, Diagrammeinstellungen, die Seiten
des Projekts und den Undo-Stapel. Ob ungespeicherte Änderungen vorliegen,
ergibt sich aus dem „clean“-Zustand des Undo-Stapels.

Ein Projekt besteht aus Seiten: Die erste ist das Hauptprogramm, jede weitere
ein Unterprogramm (wie die Diagramme eines PapDesigner-Projekts). Jede Seite
hat ihre eigene Szene und Ansicht; alle Seiten teilen sich Raster und den
Undo-Stapel. ``scene`` ist immer die Szene der gerade angezeigten Seite.
"""

from __future__ import annotations

import logging
import os
import shutil
import weakref
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from app import config
from app.analysis.graph import FlowGraph, flow_name
from app.fileformat.serializer import load_diagram, save_diagram
from app.i18n import tr
from app.model.diagram import Diagram, ProjectMeta, SubprogramPage, now_iso
from app.model.element_types import ElementType
from app.scene import DiagramScene

log = logging.getLogger(__name__)


# so viele zuletzt angezeigte Seiten merkt sich „Zurück“
HISTORY_LIMIT = 50


def display_name_for_path(path: str) -> str:
    name = os.path.basename(path)
    for extension in (config.FILE_EXTENSION, config.BACKUP_EXTENSION):
        if name.lower().endswith(extension.lower()):
            name = name[: -len(extension)]
            break
    return name or path


class DiagramPage:
    """Eine Seite des Projekts: das Hauptprogramm oder ein Unterprogramm.

    ``name`` gilt für Unterprogramm-Seiten ohne Start-Element; sonst heißt die
    Seite wie ihr Start-Element – unter diesem Namen wird sie aufgerufen.
    """

    def __init__(self, document: "DiagramDocument", scene: DiagramScene, name: str = "",
                 view: tuple[float, float, float] = (1.0, 0.0, 0.0), fit_on_show: bool = False):
        self.document = document
        self.scene = scene
        self.name = name
        self._view = tuple(float(v) for v in view)
        # True: Die Anordnung stammt aus dem Raster einer fremden Datei – beim ersten Anzeigen einpassen
        self.fit_on_show = fit_on_show

    @property
    def is_main(self) -> bool:
        return bool(self.document.pages) and self.document.pages[0] is self

    @property
    def view_state(self) -> tuple[float, float, float]:
        """(Zoom, Bildmitte x, Bildmitte y) – beim Hauptprogramm in den Diagrammeinstellungen."""
        if self.is_main:
            settings = self.document.settings
            return settings.zoom, settings.view_center_x, settings.view_center_y
        return self._view

    @view_state.setter
    def view_state(self, value: tuple[float, float, float]) -> None:
        zoom, cx, cy = (float(v) for v in value)
        if self.is_main:
            settings = self.document.settings
            settings.zoom, settings.view_center_x, settings.view_center_y = zoom, cx, cy
        else:
            self._view = (zoom, cx, cy)

    def start_items(self) -> list:
        """Start-Elemente der Seite, von oben nach unten."""
        starts = [item for item in self.scene.elements() if item.element_type is ElementType.START]
        return sorted(starts, key=lambda item: (item.data.y, item.data.x, item.element_id))

    @property
    def display_name(self) -> str:
        """Name der Seite – unter ihm wird das Unterprogramm aufgerufen (wie ein Diagramm im PapDesigner).

        Ohne gespeicherten Namen gilt der Text des ersten Start-Elements.
        """
        if self.is_main:
            return tr("Hauptprogramm")
        name = " ".join(self.name.split())
        if name:
            return name
        for item in self.start_items():
            text = " ".join(item.data.text.split())
            if text:
                return text
        return tr("Unterprogramm")

    @property
    def flow_name(self) -> str:
        """Bezeichner, unter dem die Seite aufgerufen wird (leer für das Hauptprogramm)."""
        return "" if self.is_main else flow_name(self.display_name)


class DiagramDocument(QObject):
    title_changed = Signal()
    modified_changed = Signal(bool)
    settings_changed = Signal()
    # Seiten: hinzugefügt (Seite), entfernt (Seite), umbenannt oder umsortiert; die angezeigte Seite (Index)
    page_added = Signal(object)
    page_removed = Signal(object)
    pages_changed = Signal()
    current_page_changed = Signal(int)
    # der Inhalt irgendeiner Seite hat sich geändert (Baustein/Verbindung hinzugefügt oder entfernt)
    content_changed = Signal()

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
        self.pages: list[DiagramPage] = []
        self._current = 0
        # zuletzt angezeigte Seiten (Zurück/Vorwärts wie im Browser, z. B. vom Unterprogramm zum Aufruf)
        # schwache Verweise: Eine gelöschte Seite hält der Verlauf nicht am Leben
        self._back: list[weakref.ref] = []
        self._forward: list[weakref.ref] = []
        self._navigating = False
        # Dateien, von denen in dieser Sitzung schon eine Sicherungskopie angelegt wurde
        self._backed_up: set[str] = set()
        main = self.new_page()
        self.pages.append(main)
        self.load_warnings: list[str] = main.scene.load_content(diagram.elements, diagram.connections)
        for data in diagram.subprograms:
            page = self.new_page(data.name, (data.zoom, data.view_center_x, data.view_center_y))
            self.pages.append(page)
            self.load_warnings += page.scene.load_content(data.elements, data.connections)
        self.undo_stack.setClean()
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        # liefert (zoom, center_x, center_y) der Ansicht der angezeigten Seite für das Speichern
        self.view_state_provider: Callable[[], tuple] | None = None

    # ---------------------------------------------------------------- Seiten
    def new_page(self, name: str = "", view: tuple = (1.0, 0.0, 0.0)) -> DiagramPage:
        """Erzeugt eine Seite mit leerer Szene (noch nicht im Projekt, siehe ``insert_page``)."""
        scene = DiagramScene(self.settings, self.undo_stack, self)
        scene.content_changed.connect(self.content_changed)
        return DiagramPage(self, scene, name, view)

    @property
    def scene(self) -> DiagramScene:
        """Die Szene der angezeigten Seite."""
        return self.pages[self._current].scene

    @property
    def main_scene(self) -> DiagramScene:
        return self.pages[0].scene

    @property
    def current_page(self) -> DiagramPage:
        return self.pages[self._current]

    @property
    def current_page_index(self) -> int:
        return self._current

    def scenes(self) -> list[DiagramScene]:
        return [page.scene for page in self.pages]

    def page_index(self, page: DiagramPage) -> int:
        return next((i for i, p in enumerate(self.pages) if p is page), -1)

    def page_of_scene(self, scene) -> DiagramPage | None:
        return next((page for page in self.pages if page.scene is scene), None)

    def set_current_page(self, index: int, finish_interaction: bool = True) -> None:
        """Zeigt eine andere Seite an.

        Was auf der bisherigen Seite noch läuft (Texteingabe, Ziehen eines Bausteins), wird vorher regulär
        abgeschlossen und landet als eigener Schritt im Rückgängig-Verlauf. Innerhalb eines Rückgängig-Schritts
        (``finish_interaction=False``) darf kein weiterer entstehen: Dann wird es abgebrochen.
        """
        index = max(0, min(len(self.pages) - 1, int(index)))
        if index == self._current:
            return
        scene = self.scene
        if finish_interaction:
            scene.prepare_for_command()
        else:
            scene.cancel_edit()
            if scene.pointer_interaction_active() or scene.is_connecting:
                scene.end_pointer_interaction(cancel=True)
        if not self._navigating:
            self._back.append(weakref.ref(self.pages[self._current]))
            del self._back[:-HISTORY_LIMIT]
            self._forward.clear()
        self._current = index
        self.current_page_changed.emit(index)

    def _history(self, refs: list[weakref.ref]) -> list[DiagramPage]:
        """Seiten des Verlaufs, die es noch gibt und die nicht gerade angezeigt werden."""
        pages = (ref() for ref in refs)
        return [page for page in pages if page is not None and page is not self.current_page
                and self.page_index(page) >= 0]

    def can_go_back(self) -> bool:
        return bool(self._history(self._back))

    def can_go_forward(self) -> bool:
        return bool(self._history(self._forward))

    def go_back(self) -> bool:
        """Zur zuletzt angezeigten Seite zurück."""
        return self._navigate(self._back, self._forward)

    def go_forward(self) -> bool:
        return self._navigate(self._forward, self._back)

    def _navigate(self, source: list[weakref.ref], other: list[weakref.ref]) -> bool:
        while source:
            page = source.pop()()
            if page is None or page is self.current_page or self.page_index(page) < 0:
                continue
            other.append(weakref.ref(self.current_page))
            self._navigating = True
            try:
                self.show_page(page)
            finally:
                self._navigating = False
            return True
        return False

    def show_page(self, page: DiagramPage) -> None:
        index = self.page_index(page)
        if index >= 0:
            self.set_current_page(index)

    def insert_page(self, index: int, page: DiagramPage) -> None:
        """Nimmt eine Seite auf (für Befehle; die Seite wird danach angezeigt)."""
        index = max(1, min(len(self.pages), index))  # das Hauptprogramm bleibt die erste Seite
        page.scene.setParent(self)
        self.pages.insert(index, page)
        if index <= self._current:
            self._current += 1
        self.page_added.emit(page)
        self.pages_changed.emit()
        self.content_changed.emit()
        self.set_current_page(index, finish_interaction=False)

    def remove_page(self, page: DiagramPage) -> int:
        """Entfernt eine Unterprogramm-Seite (für Befehle). Gibt ihre bisherige Position zurück."""
        index = self.page_index(page)
        if index <= 0:
            return -1
        page.scene.cancel_edit()
        page.scene.clearSelection()
        if index == self._current:
            # zuerst eine andere Seite zeigen, dann entfernen
            self.set_current_page(index - 1, finish_interaction=False)
        self.pages.pop(index)
        if index < self._current:
            self._current -= 1
        # Die Seite lebt nur noch im Rückgängig-Schritt weiter, der sie entfernt hat; wird er verworfen,
        # gibt Python sie samt Szene frei (sonst blieben verworfene Seiten bis zum Schließen im Speicher).
        page.scene.setParent(None)
        self.page_removed.emit(page)
        self.pages_changed.emit()
        self.content_changed.emit()
        return index

    def move_page(self, page: DiagramPage, index: int) -> None:
        """Verschiebt eine Unterprogramm-Seite (für Befehle); die angezeigte Seite bleibt angezeigt."""
        current = self.current_page
        old = self.page_index(page)
        index = max(1, min(len(self.pages) - 1, int(index)))
        if old <= 0 or old == index:
            return
        self.pages.pop(old)
        self.pages.insert(index, page)
        self._current = self.page_index(current)
        self.pages_changed.emit()
        self.current_page_changed.emit(self._current)

    def find_element(self, element_id: str):
        """(Seite, Baustein) zu einer Element-ID – oder ``None``."""
        for page in self.pages:
            item = page.scene.element(element_id)
            if item is not None:
                return page, item
        return None

    def find_connection(self, connection_id: str):
        for page in self.pages:
            conn = page.scene.connection(connection_id)
            if conn is not None:
                return page, conn
        return None

    def main_start_id(self) -> str | None:
        """Start-Element des Hauptprogramms – nach derselben Regel wie Schreibtischtest und Code-Erzeugung
        (in älteren Plänen kann ein Unterprogramm auf derselben Fläche weiter oben liegen)."""
        starts = self.flow_graph().starts()
        return starts[0].id if starts and starts[0].page == 0 else None

    def flow_start(self, call_text: str):
        """(Seite, Start-Element) des Ablaufs, den ein Unterprogramm-Baustein aufruft – oder ``None``.

        Wie im Schreibtischtest: der Ablauf, dessen Start-Text denselben Bezeichner ergibt; das Hauptprogramm
        nur, wenn kein anderer Ablauf so heißt.
        """
        graph = self.flow_graph()
        starts = graph.starts()
        chosen = graph.start_for_call(call_text, exclude=starts[0].id if starts else None)
        return self.find_element(chosen) if chosen else None

    def flow_graph(self) -> FlowGraph:
        """Der Ablaufgraph aller Seiten (für Schreibtischtest, Code, Struktogramm und Hinweise)."""
        names = {index: page.display_name for index, page in enumerate(self.pages) if index > 0}
        return FlowGraph.from_scenes(self.scenes(), names)

    def is_empty(self) -> bool:
        return not any(page.scene.elements() for page in self.pages)

    def command_page(self, command) -> DiagramPage | None:
        """Seite, die ein Undo-Befehl ändert (bei zusammengesetzten Befehlen: die des ersten Teils)."""
        if command is None:
            return None
        if isinstance(getattr(command, "page", None), DiagramPage):
            return command.page
        scene = getattr(command, "_scene", None)
        if scene is not None:
            return self.page_of_scene(scene)
        for i in range(command.childCount()):
            page = self.command_page(command.child(i))
            if page is not None:
                return page
        return None

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
        if not result.native:
            for page in document.pages[1:]:
                page.fit_on_show = True
        return document

    def to_diagram(self) -> Diagram:
        if self.view_state_provider is not None:
            try:
                zoom, cx, cy = self.view_state_provider()
                self.current_page.view_state = (float(zoom), float(cx), float(cy))
            except Exception:
                pass
        subprograms = []
        for page in self.pages[1:]:
            zoom, cx, cy = page.view_state
            subprograms.append(SubprogramPage(name=page.display_name, elements=page.scene.element_data(),
                                              connections=page.scene.connection_data(), zoom=zoom,
                                              view_center_x=cx, view_center_y=cy))
        return Diagram(meta=self.meta.copy(), settings=self.settings.copy(),
                       elements=self.main_scene.element_data(), connections=self.main_scene.connection_data(),
                       subprograms=subprograms)

    def save(self, path: str, backup: bool = False) -> None:
        """Speichert das Projekt. Wirft ``ProjectFileError``."""
        self.scene.commit_edit()
        path = os.path.abspath(path)
        if backup:
            self._backup_once(path)
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

    def _backup_once(self, path: str) -> None:
        """Hebt den Stand einer vorhandenen Datei vor dem ersten Überschreiben in dieser Sitzung auf
        („Projekt.pap-backup“). So bleibt auch beim automatischen Speichern der Stand beim Öffnen erhalten."""
        key = os.path.normcase(path)
        if key in self._backed_up or not os.path.isfile(path):
            return
        self._backed_up.add(key)
        try:
            shutil.copy2(path, config.backup_path_for(path))
        except OSError as exc:  # eine fehlende Sicherungskopie verhindert das Speichern nicht
            log.warning("Sicherungskopie von %s nicht möglich: %s", path, exc)

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
