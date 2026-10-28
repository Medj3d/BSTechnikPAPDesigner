"""Kopieren, Ausschneiden, Einfügen und Duplizieren.

Kopiert werden echte Diagrammelemente. Beim Einfügen erhält jedes Element
eine neue eindeutige ID. Verbindungen werden nur übernommen, wenn Quelle
UND Ziel mitkopiert wurden (A → B → C, Kopie von A + B ergibt A' → B'; die
Verbindung zu C wird nicht übernommen).

In der Zwischenablage liegt die Auswahl als ``.pap``-Inhalt – dieselbe
Darstellung wie in einer Projektdatei – und zusätzlich als Bild, damit sie
sich direkt in Word, OneNote oder PowerPoint einfügen lässt. „Als Bild
kopieren“ legt nur das Bild ab.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPointF, QRectF, QThread
from PySide6.QtWidgets import QApplication

from app.commands import AddElementsCommand, DeleteCommand
from app.fileformat.project import ProjectFileError
from app.fileformat.serializer import diagram_from_xml, diagram_to_xml
from app.i18n import tr
from app.model.diagram import Diagram, new_id
from app.model.element_types import TRUNK_IN_KEY, TRUNK_OUT_KEY

MIME_TYPE = "application/x-bstechnik-pap+xml"
# Bild in der Zwischenablage: doppelte Auflösung (scharf in Word & Co.), schmaler Rand
IMAGE_SCALE = 2.0
IMAGE_MARGIN = 12.0


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
    """Kopiert die Auswahl: als ``.pap``-Inhalt (zum Einfügen hier), als Text und als Bild (für Word & Co.)."""
    scene.prepare_for_command()
    payload = selection_payload(scene)
    if payload is None:
        return False
    content = diagram_to_xml(payload).encode("utf-8")
    text = "\n\n".join(element.text for element in payload.elements if element.text)
    image = _image_of(scene, [element.id for element in payload.elements])

    def mime_data() -> QMimeData:
        mime = QMimeData()
        mime.setData(MIME_TYPE, content)
        mime.setText(text)
        if image is not None:
            mime.setImageData(image)
        return mime

    set_clipboard(mime_data, lambda data: data is not None and data.hasFormat(MIME_TYPE))
    return True


def set_clipboard(make_mime, arrived, attempts: int = 10) -> bool:
    """Legt Daten in die Zwischenablage und prüft, ob sie angekommen sind.

    Unter Windows hält manchmal ein anderes Programm (z. B. der Zwischenablage-Verlauf, der ein großes Bild
    einliest) die Zwischenablage kurz fest; dann ginge das Kopieren still verloren. Deshalb wird es kurz darauf
    noch einmal versucht.
    """
    board = QApplication.clipboard()
    for attempt in range(attempts):
        board.setMimeData(make_mime())
        if arrived(board.mimeData()):
            return True
        QThread.msleep(20 * (attempt + 1))
    return False


def _image_of(scene, element_ids=None):
    """Bild der Bausteine (bzw. der ganzen Seite) wie beim PNG-Export: hell, ohne Raster – oder ``None``."""
    from app.export import ExportError, ExportOptions, render_image

    try:
        return render_image(scene, ExportOptions(theme_name="light", scale=IMAGE_SCALE, margin=IMAGE_MARGIN),
                            element_ids)
    except ExportError:
        return None


def copy_image(scene) -> bool:
    """„Als Bild kopieren“: nur ein Bild der Auswahl bzw. – ohne Auswahl – der ganzen Seite.

    Ohne Text und ohne ``.pap``-Inhalt, damit Word, OneNote oder PowerPoint sicher ein Bild einfügen.
    """
    scene.prepare_for_command()
    ids = [item.element_id for item in scene.selected_elements()]
    image = _image_of(scene, ids or None)
    if image is None:
        return False

    def mime_data() -> QMimeData:
        mime = QMimeData()
        mime.setImageData(image)
        return mime

    set_clipboard(mime_data, lambda data: data is not None and data.hasImage() and not data.hasFormat(MIME_TYPE))
    return True


def cut_selection(scene) -> bool:
    # Was gelöscht wird, steht vor dem Kopieren fest (das Bild entsteht mit vorübergehend ausgeblendeten Teilen)
    scene.prepare_for_command()
    element_ids = [item.element_id for item in scene.selected_elements()]
    connection_ids = [conn.connection_id for conn in scene.selected_connections()]
    if not copy_selection(scene):
        return False
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
