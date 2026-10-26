"""Unterprogramme auf eigenen Seiten: anlegen, umbenennen, löschen und finden.

Ein Unterprogramm ist ein eigener Ablauf (Start → … → Ende) auf einer eigenen
Seite des Projekts. Ein Unterprogramm-Baustein ruft es über den Namen auf:
Der Baustein „Fehlermeldung“ (oder „berechne(x, y)“) ruft den Ablauf, dessen
Start-Element „Fehlermeldung“ (bzw. „berechne“) heißt. So verstehen es auch
Schreibtischtest, Code-Erzeugung und Struktogramm.

Alle Änderungen sind jeweils ein Rückgängig-Schritt.
"""

from __future__ import annotations

from app.analysis import text as T
from app.analysis.graph import call_target, flow_name
from app.commands import AddElementsCommand, EditTextCommand
from app.commands.pages import AddPageCommand, RemovePageCommand, RenamePageCommand
from app.i18n import tr
from app.items.factory import new_element_data
from app.model.diagram import ConnectionData, new_id
from app.model.element_types import PORT_BOTTOM, PORT_TOP, ElementType, is_default_text, spec_for

# Abstand zwischen Start und Ende einer neuen Unterprogramm-Seite
NEW_PAGE_GAP = 80.0


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
    if call_target(name) != wanted:
        # „berechne(x)“ als Name: Aufrufe „berechne(2)“ fänden das Unterprogramm nicht
        return tr("Bitte nur den Namen angeben – ohne Klammern und Argumente.")
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
    """Aufruftext mit neuem Namen; Argumente bleiben erhalten: „berechne(x, y)“ → „summe(x, y)“."""
    call = T.call_parts(text)
    if not call or not call[1]:
        return new_name
    name = new_name if T.is_identifier(new_name) else T.slug(new_name)
    return f"{name}({', '.join(call[1])})"


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
