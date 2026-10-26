"""Grafikunabhängiges Datenmodell eines Programmablaufplans.

Die Klassen in diesem Modul enthalten ausschließlich Daten und kennen weder Qt
noch die grafische Darstellung. Die Szene erzeugt aus diesen Daten grafische
Objekte und schreibt Änderungen (Position, Text, ...) in die Daten zurück.
Identität wird immer über eindeutige IDs hergestellt, niemals über Positionen
oder Reihenfolgen.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app import config
from app.model.element_types import ElementType, spec_for


def new_id() -> str:
    """Erzeugt eine neue, weltweit eindeutige ID."""
    return uuid.uuid4().hex


def now_iso() -> str:
    """Aktueller Zeitpunkt als ISO-8601-Zeichenkette mit Zeitzone."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class ProjectMeta:
    name: str = config.DEFAULT_PROJECT_NAME
    author: str = ""
    description: str = ""
    created: str = field(default_factory=now_iso)
    modified: str = field(default_factory=now_iso)

    def copy(self) -> "ProjectMeta":
        return copy.deepcopy(self)


@dataclass
class DiagramSettings:
    grid_size: int = config.DEFAULT_GRID_SIZE
    grid_visible: bool = config.DEFAULT_GRID_VISIBLE
    snap_to_grid: bool = config.DEFAULT_SNAP_TO_GRID
    zoom: float = 1.0
    view_center_x: float = 0.0
    view_center_y: float = 0.0

    def copy(self) -> "DiagramSettings":
        return copy.deepcopy(self)


@dataclass
class ElementData:
    id: str
    type: ElementType
    x: float
    y: float
    width: float
    height: float
    text: str = ""
    z: float = 0.0
    properties: dict = field(default_factory=dict)

    @property
    def ports(self) -> tuple:
        return spec_for(self.type).ports

    def copy(self) -> "ElementData":
        return copy.deepcopy(self)


@dataclass
class ConnectionData:
    id: str
    source_id: str
    target_id: str
    source_port: str
    target_port: str
    label: str = ""
    # {"mode": "auto"} oder {"mode": "manual", "axis": "x"|"y", "value": float}
    routing: dict = field(default_factory=lambda: {"mode": "auto"})
    # Angezeigter Linienverlauf [(x, y), …] zum Zeitpunkt des Speicherns. Er wird
    # beim Öffnen übernommen, damit eine Linie genau so verläuft wie zuvor; die
    # Szene berechnet ihn bei jeder Änderung selbst neu (None = neu berechnen).
    path: list | None = None

    def copy(self) -> "ConnectionData":
        return copy.deepcopy(self)


@dataclass
class SubprogramPage:
    """Eine eigene Seite für ein Unterprogramm (im PapDesigner: ein weiteres Diagramm des Projekts).

    Aufgerufen wird ein Unterprogramm über den Text seines Start-Elements; ``name`` ist die
    Beschriftung der Seite, solange sie kein Start-Element hat. Zoom und Bildmitte gehören zur Seite.
    """
    name: str = ""
    elements: list = field(default_factory=list)
    connections: list = field(default_factory=list)
    zoom: float = 1.0
    view_center_x: float = 0.0
    view_center_y: float = 0.0

    def copy(self) -> "SubprogramPage":
        return copy.deepcopy(self)


@dataclass
class Diagram:
    meta: ProjectMeta = field(default_factory=ProjectMeta)
    settings: DiagramSettings = field(default_factory=DiagramSettings)
    # Bausteine und Verbindungen des Hauptprogramms (erste Seite)
    elements: list = field(default_factory=list)
    connections: list = field(default_factory=list)
    # weitere Seiten: je eine für ein Unterprogramm
    subprograms: list = field(default_factory=list)

    @property
    def comments(self) -> list:
        """Kommentare sind Elemente vom Typ ``comment``."""
        return [e for e in self.elements if e.type is ElementType.COMMENT]

    def all_elements(self) -> list:
        """Bausteine aller Seiten (Hauptprogramm zuerst)."""
        return list(self.elements) + [e for page in self.subprograms for e in page.elements]

    def all_connections(self) -> list:
        return list(self.connections) + [c for page in self.subprograms for c in page.connections]

    def element_by_id(self, element_id: str) -> ElementData | None:
        for element in self.all_elements():
            if element.id == element_id:
                return element
        return None
