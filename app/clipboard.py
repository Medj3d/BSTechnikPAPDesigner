"""Kopieren, Ausschneiden, Einfügen und Duplizieren.

Kopiert werden echte Diagrammelemente. Beim Einfügen erhält jedes Element
eine neue eindeutige ID. Verbindungen werden nur übernommen, wenn Quelle
UND Ziel mitkopiert wurden (A → B → C, Kopie von A + B ergibt A' → B'; die
Verbindung zu C wird nicht übernommen).

In der Zwischenablage liegt die Auswahl als ``.pap``-Inhalt – dieselbe
Darstellung wie in einer Projektdatei.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPointF, QRectF
from PySide6.QtWidgets import QApplication

from app.commands import AddElementsCommand, DeleteCommand
from app.fileformat.project import ProjectFileError
from app.fileformat.serializer import diagram_from_xml, diagram_to_xml
from app.i18n import tr
from app.model.diagram import Diagram, new_id
from app.model.element_types import TRUNK_IN_KEY, TRUNK_OUT_KEY

MIME_TYPE = "application/x-bstechnik-pap+xml"


def selection_payload(scene) -> Diagram | None:
    """Die Auswahl als eigenständiges Diagramm (Kopien der Modelldaten)."""
    items = scene.selected_elements()
    if not items:
        return None
    ids = {item.element_id for item in items}
    connections = [conn for conn in scene.connections()
                   if conn.data.source_id in ids and conn.data.target_id in ids]
    return Diagram(elements=[item.data.copy() for item in items],
                   connections=[conn.data.copy() for conn in connections])


def copy_selection(scene) -> bool:
    scene.prepare_for_command()
    payload = selection_payload(scene)
    if payload is None:
        return False
    mime = QMimeData()
    mime.setData(MIME_TYPE, diagram_to_xml(payload).encode("utf-8"))
    mime.setText("\n\n".join(element.text for element in payload.elements if element.text))
    QApplication.clipboard().setMimeData(mime)
    return True


def cut_selection(scene) -> bool:
    if not copy_selection(scene):
        return False
    element_ids = [item.element_id for item in scene.selected_elements()]
    connection_ids = [conn.connection_id for conn in scene.selected_connections()]
    scene.undo_stack.push(DeleteCommand(scene, element_ids, connection_ids, text=tr("Ausschneiden")))
    return True


def clipboard_payload() -> Diagram | None:
    mime = QApplication.clipboard().mimeData()
    if mime is None or not mime.hasFormat(MIME_TYPE):
        return None
    try:
        return diagram_from_xml(bytes(mime.data(MIME_TYPE))).diagram
    except ProjectFileError:
        return None


def can_paste() -> bool:
    mime = QApplication.clipboard().mimeData()
    return mime is not None and mime.hasFormat(MIME_TYPE)


def payload_bounds(payload: Diagram) -> QRectF:
    rect = QRectF()
    for e in payload.elements:
        rect = rect.united(QRectF(e.x - e.width / 2, e.y - e.height / 2, e.width, e.height))
    return rect


def paste_payload(scene, payload: Diagram, target_center: QPointF | None = None,
                  offset: QPointF | None = None, text: str | None = None) -> list[str]:
    """Fügt den Inhalt als neue Elemente ein. Gibt die neuen IDs zurück.

    ``text``: Beschriftung des Undo-Schritts (schon übersetzt); ohne Angabe „Einfügen“.
    """
    if text is None:
        text = tr("Einfügen")
    scene.prepare_for_command()
    elements = []
    id_map: dict[str, str] = {}
    for source in payload.elements:
        element = source.copy()
        element.id = new_id()
        id_map[source.id] = element.id
        elements.append(element)
    if not elements:
        return []

    bounds = payload_bounds(payload)
    if target_center is not None:
        delta = scene.snap_point(QPointF(target_center.x() - bounds.center().x(),
                                         target_center.y() - bounds.center().y()))
    else:
        # Versatz auf das Raster runden, damit Kopien auch bei Rastergrößen
        # wie 25 oder 30 auf Rasterpunkten landen.
        delta = scene.snap_point(offset or QPointF(0, 0))
    for element in elements:
        point = scene.clamp_point(QPointF(element.x + delta.x(), element.y + delta.y()))
        element.x, element.y = point.x(), point.y()

    connections = []
    connection_map: dict[str, str] = {}
    for source in payload.connections:
        if source.source_id not in id_map or source.target_id not in id_map:
            continue
        conn = source.copy()
        conn.id = new_id()
        conn.path = None  # an der neuen Stelle wird die Linie neu geführt
        connection_map[source.id] = conn.id
        conn.source_id = id_map[conn.source_id]
        conn.target_id = id_map[conn.target_id]
        if conn.routing.get("mode") == "manual":
            # manuelle Mittelachse gemeinsam mit den Bausteinen versetzen
            shift = delta.x() if conn.routing.get("axis") == "x" else delta.y()
            conn.routing = dict(conn.routing, value=float(conn.routing.get("value", 0.0)) + shift)
        connections.append(conn)

    # Verbindungsknoten: Verweise auf ihren Stamm auf die neuen IDs umstellen
    for element in elements:
        for key in (TRUNK_IN_KEY, TRUNK_OUT_KEY):
            if key in element.properties:
                if element.properties[key] in connection_map:
                    element.properties[key] = connection_map[element.properties[key]]
                else:
                    element.properties.pop(key)

    scene.undo_stack.push(AddElementsCommand(scene, elements, connections, text=text))
    return [e.id for e in elements]


def _signature(payload: Diagram) -> tuple:
    return tuple((e.id, e.x, e.y) for e in payload.elements)


class PasteTracker:
    """Merkt sich, wie oft derselbe Inhalt eingefügt wurde (für versetztes Einfügen)."""

    def __init__(self):
        self._signature = None
        self._count = 0

    def next_offset(self, payload: Diagram, step: float) -> QPointF:
        signature = _signature(payload)
        if signature == self._signature:
            self._count += 1
        else:
            self._signature = signature
            self._count = 1
        return QPointF(step * self._count, step * self._count)

    def prime_after_cut(self, payload: Diagram) -> None:
        """Nach dem Ausschneiden wird beim ersten Einfügen an der Originalposition eingefügt."""
        self._signature = _signature(payload)
        self._count = -1

    def reset(self) -> None:
        self._signature = None
        self._count = 0
