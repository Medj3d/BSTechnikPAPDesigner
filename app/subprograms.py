"""Unterprogramme auf eigenen Seiten: anlegen, umbenennen, löschen und finden.

Ein Unterprogramm ist ein eigener Ablauf (Start → … → Ende) auf einer eigenen
Seite des Projekts. Ein Unterprogramm-Baustein ruft es über den Namen auf:
Der Baustein „Fehlermeldung“ (oder „berechne(x, y)“) ruft den Ablauf, dessen
Start-Element „Fehlermeldung“ (bzw. „berechne“) heißt. So verstehen es auch
Schreibtischtest, Code-Erzeugung und Struktogramm.

Alle Änderungen sind jeweils ein Rückgängig-Schritt.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPointF
from PySide6.QtWidgets import QApplication

from app import clipboard
from app.analysis import text as T
from app.analysis.graph import call_target, flow_name, routine_label
from app.commands import AddElementsCommand, DeleteCommand, EditTextCommand
from app.commands.pages import AddPageCommand, MovePageCommand, RemovePageCommand, RenamePageCommand
from app.fileformat.project import ProjectFileError
from app.fileformat.serializer import diagram_from_xml, diagram_to_xml, loop_partners
from app.i18n import tr
from app.items.factory import new_element_data
from app.model.diagram import ConnectionData, Diagram, new_id
from app.model.element_types import (PORT_BOTTOM, PORT_TOP, TRUNK_IN_KEY, ElementType, is_default_text,
                                     spec_for)

# Abstand zwischen Start und Ende einer neuen Unterprogramm-Seite
NEW_PAGE_GAP = 80.0
# Eine ganze Seite in der Zwischenablage (zum Einfügen als Seite – auch in ein anderes Projekt)
PAGE_MIME_TYPE = "application/x-bstechnik-pap-page+xml"
# zuletzt kopierte Seite (Inhalt, Text in der Zwischenablage): Manche Zwischenablage-Programme legen nur den Text
# zurück und verwerfen das eigene Format – solange der Text noch derselbe ist, gilt diese Seite.
_last_page: tuple[bytes, str] | None = None


def clean_name(name: str) -> str:
    """Name in einer Zeile ohne doppelte Leerzeichen."""
    return " ".join(str(name or "").split())


def name_error(document, name: str, page=None) -> str | None:
    """Warum ``name`` als Name eines (neuen oder umbenannten) Unterprogramms nicht geht – oder ``None``.

    ``page``: die Seite, die umbenannt wird (ihr eigener Name zählt nicht als belegt).
    """
    name = clean_name(name)
    if not name:
        return tr("Bitte einen Namen für das Unterprogramm eingeben.")
    wanted = flow_name(name)
    if not wanted:
        return tr("Der Name muss mindestens einen Buchstaben oder eine Ziffer enthalten.")
    main_start = document.main_start_id()
    for other in document.pages:
        if other is page:
            continue
        if not other.is_main and other.flow_name == wanted:
            return tr("Es gibt schon ein Unterprogramm „{name}“.", name=other.display_name)
        for item in other.start_items():
            if flow_name(item.data.text) != wanted:
                continue
            if item.element_id == main_start:
                return tr("So heißt schon der Start des Hauptprogramms. Bitte einen anderen Namen wählen.")
            # ein Ablauf mit diesem Namen auf einer anderen Seite (z. B. ältere Pläne mit allem auf einer Fläche)
            return tr("Es gibt schon einen Ablauf „{name}“.", name=clean_name(item.data.text))
    return None


def suggested_name(document) -> str:
    """Vorschlag für ein neues Unterprogramm: ein noch nicht angelegter Aufruf, sonst „Unterprogramm 1“ usw."""
    for page in document.pages:
        for item in sorted(page.scene.elements(), key=lambda it: (it.data.y, it.data.x)):
            if item.element_type is ElementType.SUBPROGRAM and not is_placeholder(item):
                name = call_name(item.data.text)
                if name and document.flow_start(item.data.text) is None and name_error(document, name) is None:
                    return name
    number = 1
    while name_error(document, tr("Unterprogramm {number}", number=number)) is not None:
        number += 1
    return tr("Unterprogramm {number}", number=number)


def call_name(text: str) -> str:
    """Name des Unterprogramms, das ein Baustein aufruft: „berechne(x, y)“ → „berechne“."""
    call = T.call_parts(text)
    return call[0] if call else clean_name(text)


def is_placeholder(item) -> bool:
    """Ein Unterprogramm-Baustein, der noch den Standardtext trägt, ruft (noch) nichts Bestimmtes auf."""
    return not item.data.text.strip() or is_default_text(item.data.text, item.element_type, item.data.properties)


def create_subprogram(document, name: str):
    """Legt eine neue Seite mit Start „name“ → Ende an, zeigt sie an und gibt sie zurück."""
    name = clean_name(name)
    page = document.new_page(name)
    start = new_element_data(ElementType.START, 0.0, 0.0, text=name)
    end_y = start.height / 2 + NEW_PAGE_GAP + spec_for(ElementType.END).default_height / 2
    end_y = document.main_scene.snap_value(end_y) if document.settings.snap_to_grid else end_y
    end = new_element_data(ElementType.END, 0.0, end_y)
    link = ConnectionData(new_id(), start.id, end.id, PORT_BOTTOM, PORT_TOP)
    page.view_state = (1.0, 0.0, end_y / 2)
    stack = document.undo_stack
    stack.beginMacro(tr("Unterprogramm „{name}“ anlegen", name=name))
    stack.push(AddPageCommand(document, page))
    stack.push(AddElementsCommand(page.scene, [start, end], [link], select_ids=[start.id]))
    stack.endMacro()
    return page


def rename_subprogram(document, page, new_name: str) -> bool:
    """Benennt ein Unterprogramm um: Seite, Start-Element und alle Bausteine, die es aufrufen.

    Gibt ``False`` zurück, wenn sich nichts ändert.
    """
    new_name = clean_name(new_name)
    old_name = page.display_name
    old_target = page.flow_name
    if not new_name or new_name == old_name:
        return False
    edits = []
    # Start-Elemente der Seite, die so heißen wie das Unterprogramm (bzw. das einzige ohne Text)
    starts = page.start_items()
    for item in starts:
        if flow_name(item.data.text) == old_target or (len(starts) == 1 and not item.data.text.strip()):
            edits.append((page.scene, item, new_name))
    # Aufrufe auf allen Seiten
    if old_target:
        for other in document.pages:
            for item in other.scene.elements():
                if item.element_type is ElementType.SUBPROGRAM and call_target(item.data.text) == old_target:
                    edits.append((other.scene, item, renamed_call(item.data.text, new_name)))
    stack = document.undo_stack
    stack.beginMacro(tr("Unterprogramm „{old}“ in „{new}“ umbenennen", old=old_name, new=new_name))
    stack.push(RenamePageCommand(document, page, page.name, new_name))
    for scene, item, text in edits:
        if text != item.data.text:
            stack.push(EditTextCommand(scene, item.element_id, item.data.text, text))
    stack.endMacro()
    return True


def renamed_call(text: str, new_name: str) -> str:
    """Aufruftext mit neuem Namen. Getauscht wird nur der Name vor der Klammer; Argumente, Zuweisung und
    Rückgabetyp bleiben: „berechne(x, y)“ → „summe(x, y)“, „ok := isLeapYear(j)“ → „ok := istSchaltjahr(j)“.
    Ohne Klammer ist der Aufruf einfach der neue Name."""
    new_label = routine_label(new_name)
    head, bracket, rest = " ".join(text.split()).partition("(")
    old_label = routine_label(text)
    position = head.rfind(old_label) if bracket and head.strip() else -1
    if position < 0:
        return new_label
    name = new_label if T.is_identifier(new_label) else T.slug(new_label)
    return f"{head[:position]}{name}{head[position + len(old_label):]}({rest}"


def delete_subprogram(document, page) -> None:
    """Entfernt eine Unterprogramm-Seite samt Inhalt (ein Rückgängig-Schritt)."""
    if page.is_main:
        return
    document.undo_stack.push(RemovePageCommand(document, page,
                                               tr("Unterprogramm „{name}“ löschen", name=page.display_name)))


def callers(document, page) -> list:
    """(Seite, Baustein) aller Unterprogramm-Bausteine, die diese Seite aufrufen."""
    target = page.flow_name
    if not target:
        return []
    return [(other, item) for other in document.pages for item in other.scene.elements()
            if item.element_type is ElementType.SUBPROGRAM and call_target(item.data.text) == target]


# ------------------------------------------------------------------ Seiten kopieren, verschieben, einfügen
def unique_name(document, name: str) -> str:
    """„X“, sonst „X2“ bzw. „X 2“, „X3“ … – ein Name, den noch kein Ablauf trägt.

    Gezählt wird ohne Klammern: Aufrufe nennen das Unterprogramm beim Wort vor der Klammer, „X (Kopie)“ hieße
    also wieder „X“.
    """
    name = clean_name(name)
    if name and name_error(document, name) is None:
        return name
    base = clean_name(routine_label(name)) if name else ""
    if not flow_name(base):
        return suggested_name(document)
    for number in range(2, 10_000):
        # ein Bezeichner bekommt die Zahl angehängt („f2“), ein Name aus Wörtern mit Leerzeichen („Werte prüfen 2“);
        # Rückgabetyp und Parameter bleiben: „int f(int x)“ → „int f2(int x)“
        label = f"{base}{number}" if T.is_identifier(base) else f"{base} {number}"
        candidate = renamed_call(name, label) if "(" in name else label
        if name_error(document, candidate) is None:
            return candidate
    return suggested_name(document)


def page_payload(page) -> Diagram:
    """Inhalt einer Seite als eigenständiges Diagramm (Kopien der Modelldaten)."""
    page.scene.prepare_for_command()
    return Diagram(elements=page.scene.element_data(), connections=page.scene.connection_data())


def _renamed_starts(payload: Diagram, old_name: str, new_name: str) -> Diagram:
    """Start-Elemente, die wie die alte Seite heißen, tragen in der Kopie den neuen Namen."""
    old = flow_name(old_name)
    for element in payload.elements:
        if ElementType(element.type) is ElementType.START and old and flow_name(element.text) == old:
            element.text = new_name
    return payload


def add_page_with(document, name: str, payload: Diagram, view: tuple = (1.0, 0.0, 0.0),
                  index: int | None = None, text: str | None = None):
    """Neue Seite „name“ mit dem Inhalt ``payload`` (neue IDs; ein Rückgängig-Schritt). Gibt die Seite zurück."""
    page = document.new_page(name, view)
    stack = document.undo_stack
    stack.beginMacro(text or tr("Unterprogramm „{name}“ anlegen", name=name))
    stack.push(AddPageCommand(document, page, index))
    if payload.elements:
        clipboard.paste_payload(page.scene, payload, offset=QPointF(0, 0))
        page.scene.clearSelection()
    stack.endMacro()
    return page


def duplicate_subprogram(document, page):
    """Kopie einer Unterprogramm-Seite direkt dahinter, mit eigenem Namen. Gibt die neue Seite zurück."""
    if page.is_main:
        return None
    name = unique_name(document, page.display_name)
    payload = _renamed_starts(page_payload(page), page.display_name, name)
    return add_page_with(document, name, payload, page.view_state, document.page_index(page) + 1,
                         tr("Unterprogramm „{name}“ duplizieren", name=page.display_name))


def copy_page(page) -> bool:
    """Legt eine ganze Seite in die Zwischenablage – zum Einfügen als neues Unterprogramm, auch in einem anderen
    Projekt (mit „Einfügen“ auf einer Seite kommen die Bausteine selbst)."""
    global _last_page
    payload = page_payload(page)
    payload.meta.name = page.display_name
    content = diagram_to_xml(payload).encode("utf-8")
    name = page.display_name
    _last_page = (content, name)

    def mime_data() -> QMimeData:
        mime = QMimeData()
        mime.setData(PAGE_MIME_TYPE, content)
        mime.setData(clipboard.MIME_TYPE, content)
        mime.setText(name)
        return mime

    return clipboard.set_clipboard(mime_data, lambda data: data is not None and data.hasFormat(PAGE_MIME_TYPE))


def cut_page(document, page) -> bool:
    """Seite in die Zwischenablage legen und entfernen (ein Rückgängig-Schritt). Kommt sie nicht in der
    Zwischenablage an (sie ist gerade von einem anderen Programm belegt), bleibt die Seite stehen."""
    if page.is_main or not copy_page(page):
        return False
    document.undo_stack.push(RemovePageCommand(document, page,
                                               tr("Unterprogramm „{name}“ ausschneiden", name=page.display_name)))
    return True


def _page_content() -> bytes | None:
    """Die kopierte Seite aus der Zwischenablage – oder ``None``."""
    mime = QApplication.clipboard().mimeData()
    if mime is None:
        return None
    if mime.hasFormat(PAGE_MIME_TYPE):
        return bytes(mime.data(PAGE_MIME_TYPE))
    if _last_page is not None and mime.hasText() and mime.text() == _last_page[1]:
        return _last_page[0]
    return None


def can_paste_page() -> bool:
    return _page_content() is not None


def paste_page(document, index: int | None = None):
    """Fügt eine kopierte Seite als neues Unterprogramm ein. Gibt die Seite zurück (oder ``None``)."""
    content = _page_content()
    if content is None:
        return None
    try:
        payload = diagram_from_xml(content).diagram
    except ProjectFileError:
        return None
    original = clean_name(payload.meta.name)
    name = unique_name(document, original)
    return add_page_with(document, name, _renamed_starts(payload, original, name), index=index,
                         text=tr("Unterprogramm „{name}“ einfügen", name=name))


def move_subprogram(document, page, step: int) -> bool:
    """Verschiebt eine Unterprogramm-Seite um ``step`` Plätze (das Hauptprogramm bleibt vorn)."""
    index = document.page_index(page)
    target = index + step
    if index <= 0 or not 1 <= target < len(document.pages):
        return False
    document.undo_stack.push(MovePageCommand(document, page, target))
    return True


# ------------------------------------------------------------------ Auswahl auslagern
def _moved_items(scene) -> list:
    """Was beim Auslagern auf die neue Seite kommt: die markierten Bausteine – ohne Kommentare, die an einem
    Baustein außerhalb der Auswahl hängen (die bleiben bei ihm)."""
    selected = scene.selected_elements()
    ids = {item.element_id for item in selected}

    def anchored_outside(item) -> bool:
        partners = [conn.target if conn.source is item else conn.source for conn in item.connections]
        return bool(partners) and all(other.element_id not in ids for other in partners)

    return [item for item in selected if not (item.is_comment and anchored_outside(item))]


def _boundary(items) -> tuple[list, list]:
    """Verbindungen, die von außen in die Bausteine führen bzw. aus ihnen hinaus (ohne Kommentarlinien)."""
    ids = {item.element_id for item in items}
    incoming, outgoing, seen = [], [], set()
    for item in items:
        for conn in item.connections:
            if conn.is_annotation or conn.connection_id in seen:
                continue
            seen.add(conn.connection_id)
            if conn.target is item and conn.source.element_id not in ids:
                incoming.append(conn)
            elif conn.source is item and conn.target.element_id not in ids:
                outgoing.append(conn)
    return incoming, outgoing


def _payload_of(scene, items) -> Diagram:
    ids = {item.element_id for item in items}
    connections = [conn for conn in scene.connections()
                   if conn.data.source_id in ids and conn.data.target_id in ids]
    return Diagram(elements=[item.data.copy() for item in items],
                   connections=[conn.data.copy() for conn in connections])


def extraction_error(scene) -> str | None:
    """Warum sich die Auswahl nicht in ein Unterprogramm auslagern lässt – oder ``None``."""
    flow = [item for item in scene.selected_elements() if not item.is_comment]
    if not flow:
        return tr("Bitte zuerst die Bausteine markieren, die ins Unterprogramm sollen.")
    if any(item.element_type in (ElementType.START, ElementType.END) for item in flow):
        return tr("Start und Ende bleiben, wo sie sind – bitte nur die Bausteine dazwischen markieren.")
    # Schleifenbeginn und -ende gehören zusammen: beide oder keinen auslagern (der Inhalt allein geht)
    ids = {item.element_id for item in flow}
    partners = loop_partners(scene.element_data(), scene.connection_data())
    if any(item.element_type is ElementType.LOOP and partners.get(item.element_id, item.element_id) not in ids
           for item in flow):
        return tr("Schleifenbeginn und Schleifenende gehören zusammen – bitte beide markieren oder nur den Inhalt "
                  "der Schleife.")
    incoming, outgoing = _boundary(_moved_items(scene))
    if len({conn.target.element_id for conn in incoming}) > 1:
        return tr("Der markierte Abschnitt hat mehrere Eingänge. Ein Unterprogramm braucht genau einen Einstieg – "
                  "bitte ein zusammenhängendes Stück des Ablaufs markieren.")
    if len({conn.target.element_id for conn in outgoing}) > 1:
        return tr("Der markierte Abschnitt führt an mehreren Stellen weiter. Ein Unterprogramm kehrt immer an "
                  "dieselbe Stelle zurück – bitte ein zusammenhängendes Stück des Ablaufs markieren.")
    return None


def extract_to_subprogram(document, scene, name: str):
    """Verschiebt die markierten Bausteine auf eine neue Seite „Start name → Abschnitt → Ende“. An ihrer Stelle
    steht danach ein Unterprogramm-Baustein, der sie aufruft; die Pfeile davor und danach bleiben. Ein
    Rückgängig-Schritt. Gibt die neue Seite zurück (oder ``None``, wenn sich die Auswahl nicht auslagern lässt).
    """
    if extraction_error(scene) is not None:
        return None
    scene.prepare_for_command()
    name = clean_name(name)
    moved = _moved_items(scene)
    incoming, outgoing = _boundary(moved)
    payload = _payload_of(scene, moved)
    flow = [item for item in moved if not item.is_comment]
    entry = incoming[0].target if incoming else min(flow, key=lambda item: (item.pos().y(), item.pos().x()))
    original_page = document.page_of_scene(scene)

    # neue Seite: Start oben, der Abschnitt mittig darunter, Ende darunter
    page = document.new_page(name)
    start = new_element_data(ElementType.START, 0.0, 0.0, text=name)
    bounds = clipboard.payload_bounds(payload)
    delta = page.scene.snap_point(QPointF(-bounds.center().x(), start.height / 2 + NEW_PAGE_GAP - bounds.top()))
    end_y = page.scene.snap_value(bounds.bottom() + delta.y() + NEW_PAGE_GAP
                                  + spec_for(ElementType.END).default_height / 2)
    end = new_element_data(ElementType.END, 0.0, end_y)
    page.view_state = (1.0, 0.0, end_y / 2)

    stack = document.undo_stack
    stack.beginMacro(tr("Auswahl in Unterprogramm „{name}“ auslagern", name=name))
    stack.push(AddPageCommand(document, page))
    new_ids = clipboard.paste_payload(page.scene, payload, offset=delta)
    id_map = {element.id: new for element, new in zip(payload.elements, new_ids)}
    entry_port = incoming[0].data.target_port if incoming else PORT_TOP
    links = [ConnectionData(new_id(), start.id, id_map[entry.element_id], PORT_BOTTOM, entry_port)]
    exits = [(conn.data.source_id, conn.data.source_port, conn.data.label) for conn in outgoing]
    if not exits:
        last = _last_step(flow)
        if last is not None:
            exits = [(last.element_id, PORT_BOTTOM, "")]
    links += [ConnectionData(new_id(), id_map[source], end.id, port, PORT_TOP, label)
              for source, port, label in exits]
    stack.push(AddElementsCommand(page.scene, [start, end], links, select=False))

    # an der alten Stelle: ein Unterprogramm-Baustein mit denselben Pfeilen davor und danach. Die Pfeile behalten
    # ihre IDs, damit Verbindungspunkte, die an ihnen ausgerichtet sind, es auch bleiben.
    block = new_element_data(ElementType.SUBPROGRAM, entry.pos().x(), entry.pos().y(), text=name)
    outer = [ConnectionData(conn.data.id, conn.data.source_id, block.id, conn.data.source_port,
                            conn.data.target_port, conn.data.label) for conn in incoming]
    if outgoing:
        # mehrere Ausgänge führen zum selben Ziel; weiter gilt der, an dem ein Verbindungspunkt ausgerichtet ist
        target = outgoing[0].target
        trunk = target.data.properties.get(TRUNK_IN_KEY) if target.is_junction else None
        kept = next((conn.data for conn in outgoing if conn.connection_id == trunk), outgoing[0].data)
        outer.append(ConnectionData(kept.id, block.id, kept.target_id, PORT_BOTTOM, kept.target_port))
    # Kommentare außerhalb, die an einem ausgelagerten Baustein hingen, hängen danach am Aufruf
    moved_ids = {element.id for element in payload.elements}
    notes = [conn for item in flow for conn in item.connections
             if conn.is_annotation and (conn.source.element_id not in moved_ids
                                        or conn.target.element_id not in moved_ids)]
    for conn in {conn.connection_id: conn for conn in notes}.values():
        data = conn.data
        source = block.id if data.source_id in moved_ids else data.source_id
        target = block.id if data.target_id in moved_ids else data.target_id
        outer.append(ConnectionData(data.id, source, target, data.source_port, data.target_port, data.label))
    removed = [element.id for element in payload.elements]
    stack.push(DeleteCommand(scene, removed, [conn.connection_id for conn in incoming + outgoing],
                             text=tr("Auslagern")))
    stack.push(AddElementsCommand(scene, [block], outer, select_ids=[block.id]))
    stack.endMacro()
    if original_page is not None:
        document.show_page(original_page)
    return page


def _last_step(flow: list):
    """Der unterste Baustein des Abschnitts ohne weiterführenden Pfeil (Anschluss für das Ende) – oder ``None``."""
    ids = {item.element_id for item in flow}
    candidates = [item for item in flow if item.element_type is not ElementType.DECISION
                  and not any(conn.source is item and conn.target.element_id in ids and not conn.is_annotation
                              for conn in item.connections)]
    return max(candidates, key=lambda item: (item.pos().y(), item.pos().x()), default=None)
