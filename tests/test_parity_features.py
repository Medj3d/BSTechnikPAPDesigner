"""Version 1.10.0: Funktionen aus dem PapDesigner – moderner umgesetzt.

Schleife mit Kopf-/Fußbedingung, Verbindungspunkt auf einer Verbindung, bedingter Trennstrich „~“,
Zeilenumbruch mit Strg+Enter, Sonderzeichen, Seiten duplizieren/kopieren/einfügen/verschieben,
„Auswahl in Unterprogramm auslagern“ und Zurück/Vorwärts zwischen den Seiten.
"""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from app import subprograms
from app.analysis.graph import FlowGraph
from app.document import DiagramDocument
from app.fileformat.serializer import diagram_from_xml, diagram_to_xml
from app.items.shapes import display_text
from app.model.element_types import LOOP_END, LOOP_PART_KEY, ElementType as T, is_default_text
from tests.conftest import add, connect
from tests.test_subprograms import run


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


@pytest.fixture
def window(qapp):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=False)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


def chain(scene, *steps, x=0, gap=120):
    """Bausteine untereinander, jeweils unten → oben verbunden."""
    items = []
    for index, (etype, text) in enumerate(steps):
        item = add(scene, etype, x, index * gap)
        if text is not None:
            item.set_text(text)
        items.append(item)
    for upper, lower in zip(items, items[1:]):
        connect(scene, upper, "bottom", lower, "top")
    return items


def texts(scene):
    return sorted(item.data.text for item in scene.elements())


# ------------------------------------------------------------------ Schleifen mit Kopf- und Fußbedingung
@pytest.mark.parametrize("kind, begin, end", [("head", "solange Bedingung", "Schleifenende"),
                                              ("foot", "wiederhole", "bis Bedingung"),
                                              (None, "Schleifenbeginn", "Schleifenende")])
def test_loop_with_head_or_foot_condition(scene, kind, begin, end):
    scene.insert_element(T.LOOP, QPointF(0, 0), loop_kind=kind)
    loops = sorted((item for item in scene.elements() if item.element_type is T.LOOP), key=lambda it: it.pos().y())
    assert [item.data.text for item in loops] == [begin, end]
    assert loops[1].data.properties[LOOP_PART_KEY] == LOOP_END
    # die Platzhalter gelten als Standardtext (werden beim Bearbeiten markiert, nicht als Bedingung gelesen)
    for item in loops:
        assert is_default_text(item.data.text, item.element_type, item.data.properties)


def test_loop_head_menu_action_inserts_a_loop_pair(window):
    window.new_document()
    window.actions["insert_loop_foot"].trigger()
    scene = window.current_scene()
    assert sorted(item.data.text for item in scene.elements()) == ["bis Bedingung", "wiederhole"]
    window.current_document().undo_stack.undo()
    assert not scene.elements()


# ------------------------------------------------------------------ Verbindungspunkt auf einer Verbindung
def test_insert_junction_splits_a_connection_in_one_undo_step(scene):
    a, b = chain(scene, (T.PROCESS, "a"), (T.PROCESS, "b"), gap=240)
    conn = scene.connections()[0]
    conn.set_label("weiter")
    steps = scene.undo_stack.count()
    junction_id = scene.insert_junction(conn, QPointF(0, 120))
    assert junction_id is not None
    junction = scene.element(junction_id)
    assert junction.is_junction
    pairs = {(c.source.data.text or "●", c.target.data.text or "●") for c in scene.connections()}
    assert pairs == {("a", "●"), ("●", "b")}
    assert scene.undo_stack.count() == steps + 1
    scene.undo_stack.undo()
    assert len(scene.connections()) == 1 and scene.connections()[0].data.label == "weiter"
    assert scene.element(junction_id) is None
    scene.undo_stack.redo()
    assert scene.element(junction_id) is not None


# ------------------------------------------------------------------ Texte
def test_soft_hyphen_marker_is_shown_as_conditional_hyphen():
    assert display_text("Schleifen~durchlauf") == "Schleifen­durchlauf"
    assert display_text("ohne") == "ohne"


def test_soft_hyphen_is_ignored_by_the_analysis(scene):
    start, call, end = chain(scene, (T.START, "Start"), (T.SUBPROGRAM, "Fehler~meldung"), (T.END, "Ende"))
    assert "~" not in FlowGraph.from_scene(scene).nodes[call.element_id].text


def _key(key, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers, text)


def test_ctrl_enter_inserts_a_line_break_while_enter_finishes(scene, qapp):
    item = add(scene, T.PROCESS, 0, 0)
    item.set_text("a")
    scene.begin_element_edit(item)
    editor = scene._editor
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.keyPressEvent(_key(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier))
    editor.insert_text("b")
    assert scene.is_editing
    editor.keyPressEvent(_key(Qt.Key.Key_Return))
    qapp.processEvents()
    assert not scene.is_editing
    assert item.data.text == "a\nb"


def test_special_character_goes_into_the_open_editor(window):
    window.new_document()
    scene = window.current_scene()
    item = add(scene, T.DECISION, 0, 0)
    item.set_text("x ")
    scene.select_items([item])
    window._insert_special("≤")
    assert scene.is_editing
    scene.commit_edit()
    assert item.data.text.endswith("≤")


# ------------------------------------------------------------------ Seiten
def two_page_document():
    document = DiagramDocument()
    chain(document.main_scene, (T.START, "Start"), (T.SUBPROGRAM, "zeige(x)"), (T.END, "Ende"))
    page = subprograms.create_subprogram(document, "zeige")
    process = add(page.scene, T.OUTPUT, 200, 200)
    process.set_text("x")
    return document, page


def test_duplicate_subprogram_gets_a_free_name_and_renamed_start():
    document, page = two_page_document()
    copy = subprograms.duplicate_subprogram(document, page)
    assert copy.display_name == "zeige2"
    assert document.page_index(copy) == document.page_index(page) + 1
    assert texts(copy.scene) == ["Ende", "x", "zeige2"]
    # der Aufruf im Hauptprogramm ruft weiterhin das Original
    assert document.flow_start("zeige(x)")[0] is page
    second = subprograms.duplicate_subprogram(document, page)
    assert second.display_name == "zeige3"
    document.undo_stack.undo()
    document.undo_stack.undo()
    assert len(document.pages) == 2


def test_copy_and_paste_page_between_projects(qapp):
    source, page = two_page_document()
    subprograms.copy_page(page)
    assert subprograms.can_paste_page()
    target = DiagramDocument()
    pasted = subprograms.paste_page(target)
    assert pasted is not None and pasted.display_name == "zeige"
    assert texts(pasted.scene) == texts(page.scene)
    assert len(pasted.scene.connections()) == len(page.scene.connections())
    # neue IDs: nichts wird mit dem Original geteilt
    assert not {i.element_id for i in pasted.scene.elements()} & {i.element_id for i in page.scene.elements()}
    # ein zweites Einfügen bekommt einen eigenen Namen
    again = subprograms.paste_page(target)
    assert again.display_name == "zeige2"
    assert [item.data.text for item in again.start_items()] == ["zeige2"]
    target.undo_stack.undo()
    target.undo_stack.undo()
    assert len(target.pages) == 1


def test_copy_main_page_pastes_as_subprogram(qapp):
    source, _page = two_page_document()
    source.meta.name = "Projekt"
    subprograms.copy_page(source.pages[0])
    target = DiagramDocument()
    pasted = subprograms.paste_page(target)
    assert pasted is not None and not pasted.is_main
    assert "zeige(x)" in texts(pasted.scene)


def test_cut_page_removes_it_and_paste_restores_it(qapp):
    document, page = two_page_document()
    subprograms.cut_page(document, page)
    assert len(document.pages) == 1
    pasted = subprograms.paste_page(document)
    assert pasted.display_name == "zeige"
    assert document.flow_start("zeige(x)")[0] is pasted


def test_move_subprogram_keeps_main_page_first():
    document, page = two_page_document()
    other = subprograms.create_subprogram(document, "rechne")
    assert [p.display_name for p in document.pages] == [document.pages[0].display_name, "zeige", "rechne"]
    assert subprograms.move_subprogram(document, other, -1)
    assert [p.display_name for p in document.pages[1:]] == ["rechne", "zeige"]
    assert not subprograms.move_subprogram(document, other, -1)  # nicht vor das Hauptprogramm
    assert not subprograms.move_subprogram(document, document.pages[0], 1)
    document.undo_stack.undo()
    assert [p.display_name for p in document.pages[1:]] == ["zeige", "rechne"]


def test_page_order_is_saved():
    document, page = two_page_document()
    other = subprograms.create_subprogram(document, "rechne")
    subprograms.move_subprogram(document, other, -1)
    loaded = diagram_from_xml(diagram_to_xml(document.to_diagram())).diagram
    assert [sub.name for sub in loaded.subprograms] == ["rechne", "zeige"]


def test_page_bar_drag_moves_page_in_one_undo_step(window):
    window.new_document()
    document = window.current_document()
    subprograms.create_subprogram(document, "eins")
    subprograms.create_subprogram(document, "zwei")
    steps = document.undo_stack.count()
    assert window.move_page_to(2, 1)
    assert [p.display_name for p in document.pages[1:]] == ["zwei", "eins"]
    assert document.undo_stack.count() == steps + 1
    assert not window.move_page_to(0, 1)


def test_page_commands_from_the_window(window):
    window.new_document()
    document = window.current_document()
    subprograms.create_subprogram(document, "eins")
    assert window.page_command("duplicate_page")
    assert [p.display_name for p in document.pages[1:]] == ["eins", "eins2"]
    assert window.page_command("copy_page", 1)
    assert window.page_command("paste_page", 1)
    assert [p.display_name for p in document.pages[1:]] == ["eins", "eins3", "eins2"]
    assert not window.page_command("cut_page", 0)  # das Hauptprogramm bleibt
    assert window.page_command("cut_page", 1)
    assert [p.display_name for p in document.pages[1:]] == ["eins3", "eins2"]


def test_callers_menu_reveals_the_call(window):
    window.new_document()
    document = window.current_document()
    start, call, end = chain(document.main_scene, (T.START, "Start"), (T.SUBPROGRAM, "eins"), (T.END, "Ende"))
    page = subprograms.create_subprogram(document, "eins")
    assert subprograms.callers(document, page) == [(document.pages[0], call)]
    window.reveal_element(document.pages[0], call)
    assert document.current_page_index == 0
    assert document.main_scene.selected_elements() == [call]


# ------------------------------------------------------------------ Zurück / Vorwärts
def test_back_and_forward_between_pages():
    document, page = two_page_document()
    other = subprograms.create_subprogram(document, "rechne")
    assert document.current_page is other
    document.show_page(document.pages[0])
    assert document.go_back() and document.current_page is other
    assert document.go_back() and document.current_page is page
    assert document.go_forward() and document.current_page is other
    assert document.can_go_forward()
    # eine neue Seitenwahl löscht „Vorwärts“
    document.show_page(document.pages[0])
    assert not document.can_go_forward()


def test_back_skips_deleted_pages():
    document, page = two_page_document()
    document.show_page(document.pages[0])
    subprograms.delete_subprogram(document, page)
    assert not document.can_go_back()
    assert not document.go_back()


def test_alt_left_returns_from_opened_subprogram(window):
    window.new_document()
    document = window.current_document()
    start, call, end = chain(document.main_scene, (T.START, "Start"), (T.SUBPROGRAM, "eins"), (T.END, "Ende"))
    subprograms.create_subprogram(document, "eins")
    document.show_page(document.pages[0])
    assert window.open_subprogram_for(call)
    assert document.current_page_index == 1
    window._update_actions()
    assert window.actions["go_back"].isEnabled()
    window.actions["go_back"].trigger()
    assert document.current_page_index == 0


# ------------------------------------------------------------------ Auswahl in Unterprogramm auslagern
def counting_document():
    document = DiagramDocument()
    scene = document.main_scene
    start, read, square, show, end = chain(scene, (T.START, "Start"), (T.INPUT, "x"), (T.PROCESS, "y = x * x"),
                                           (T.OUTPUT, "y"), (T.END, "Ende"))
    return document, scene, (start, read, square, show, end)


def test_extract_selection_to_subprogram():
    document, scene, (start, read, square, show, end) = counting_document()
    scene.select_items([square, show])
    assert subprograms.extraction_error(scene) is None
    steps = document.undo_stack.count()
    page = subprograms.extract_to_subprogram(document, scene, "quadriere")
    assert page is not None and page.display_name == "quadriere"
    assert document.undo_stack.count() == steps + 1
    assert document.current_page_index == 0
    # Hauptprogramm: Start → x → [quadriere] → Ende
    assert texts(scene) == ["Ende", "Start", "quadriere", "x"]
    block = next(item for item in scene.elements() if item.element_type is T.SUBPROGRAM)
    pairs = {(c.source.data.text, c.target.data.text) for c in scene.connections()}
    assert pairs == {("Start", "x"), ("x", "quadriere"), ("quadriere", "Ende")}
    assert scene.selected_elements() == [block]
    # Unterprogramm: quadriere → y = x * x → y → Ende
    sub_pairs = {(c.source.data.text, c.target.data.text or "Ende") for c in page.scene.connections()}
    assert sub_pairs == {("quadriere", "y = x * x"), ("y = x * x", "y"), ("y", "Ende")}
    assert document.flow_start(block.data.text)[0] is page
    # der Schreibtischtest läuft durch das Unterprogramm
    assert "9" in " ".join(run(document, ["3"]).outputs)
    # ein Rückgängig-Schritt stellt alles wieder her
    document.undo_stack.undo()
    assert len(document.pages) == 1
    assert texts(scene) == ["Ende", "Start", "x", "y", "y = x * x"]
    assert len(scene.connections()) == 4
    document.undo_stack.redo()
    assert len(document.pages) == 2 and texts(scene) == ["Ende", "Start", "quadriere", "x"]


def test_extract_keeps_labels_of_branches_that_leave():
    document = DiagramDocument()
    scene = document.main_scene
    start, check = chain(scene, (T.START, "Start"), (T.DECISION, "x > 0"))
    yes = add(scene, T.PROCESS, 0, 240)
    yes.set_text("y = 1")
    after = add(scene, T.END, 0, 480)
    connect(scene, check, "bottom", yes, "top").set_label("ja")
    connect(scene, check, "right", after, "right").set_label("nein")
    connect(scene, yes, "bottom", after, "top")
    scene.select_items([check, yes])
    page = subprograms.extract_to_subprogram(document, scene, "prüfe")
    labels = sorted(c.data.label for c in page.scene.connections())
    assert labels == ["", "", "ja", "nein"]


@pytest.mark.parametrize("pick, message", [
    (lambda items: [], "markieren"),
    (lambda items: [items[0], items[1]], "Start und Ende"),
])
def test_extraction_is_refused_with_a_reason(pick, message):
    document, scene, items = counting_document()
    scene.select_items(pick(items))
    assert message in subprograms.extraction_error(scene)


def test_extraction_needs_a_single_exit():
    document = DiagramDocument()
    scene = document.main_scene
    start, check = chain(scene, (T.START, "Start"), (T.DECISION, "x > 0"))
    a = add(scene, T.END, -200, 300)
    b = add(scene, T.END, 200, 300)
    connect(scene, check, "left", a, "top").set_label("ja")
    connect(scene, check, "right", b, "top").set_label("nein")
    scene.select_items([check])
    assert "mehreren Stellen" in subprograms.extraction_error(scene)
    assert subprograms.extract_to_subprogram(document, scene, "x") is None


def test_extract_from_window_asks_for_a_name(window, monkeypatch):
    window.new_document()
    document = window.current_document()
    start, a, b, end = chain(document.main_scene, (T.START, "Start"), (T.PROCESS, "a = 1"),
                             (T.PROCESS, "b = 2"), (T.END, "Ende"))
    document.main_scene.select_items([a, b])
    monkeypatch.setattr(window, "_ask_subprogram_name", lambda *args, **kwargs: "init")
    assert window.extract_subprogram()
    assert [p.display_name for p in document.pages[1:]] == ["init"]
    # ein Name, den es schon gibt, wird abgelehnt
    errors = []
    monkeypatch.setattr(window, "_error", lambda title, message: errors.append(message))
    document.main_scene.select_items([next(i for i in document.main_scene.elements() if i.data.text == "init")])
    assert not window.extract_subprogram("init")
    assert errors == ["Es gibt schon ein Unterprogramm „init“."]


# ------------------------------------------------------------------ Präsentationsansicht
def test_presentation_hides_chrome_and_restores_it(window):
    window.new_document()
    window.palette_dock.show()
    assert window.menuBar().isVisible()
    window.actions["presentation"].trigger()
    assert window.presenting and window.actions["presentation"].isChecked()
    assert not window.menuBar().isVisible() and not window.statusBar().isVisible()
    assert not window.palette_dock.isVisible() and not window.toolbar.isVisible()
    assert window.page_bar.isVisible()
    # Esc: zuerst die Auswahl aufheben, dann beenden
    scene = window.current_scene()
    item = add(scene, T.PROCESS, 0, 0)
    scene.select_items([item])
    window._on_presentation_escape()
    assert window.presenting and not scene.selectedItems()
    window._on_presentation_escape()
    assert not window.presenting
    assert window.menuBar().isVisible() and window.statusBar().isVisible()
    assert window.palette_dock.isVisible() and window.toolbar.isVisible()


# ------------------------------------------------------------------ Sicherungskopie und Standard-Autor
def test_backup_keeps_the_state_from_before_the_session(tmp_path):
    from app import config
    path = tmp_path / "plan.pap"
    document = DiagramDocument()
    add(document.main_scene, T.START, 0, 0)
    document.save(str(path))
    original = path.read_bytes()
    opened = DiagramDocument.open_file(str(path))
    add(opened.main_scene, T.END, 0, 200)
    opened.save(str(path), backup=True)
    backup = tmp_path / "plan.pap-backup"
    assert backup.read_bytes() == original
    # weitere Speichervorgänge der Sitzung lassen die Sicherungskopie unverändert
    add(opened.main_scene, T.PROCESS, 0, 100)
    opened.save(str(path), backup=True)
    assert backup.read_bytes() == original
    assert config.backup_path_for(str(path)) == str(backup)


def test_backup_file_opens_as_untitled_copy(window, tmp_path):
    path = tmp_path / "plan.pap-backup"
    document = DiagramDocument()
    add(document.main_scene, T.START, 0, 0)
    document.save(str(path))
    assert window.open_file(str(path))
    opened = window.current_document()
    assert opened.file_path is None
    assert len(opened.main_scene.elements()) == 1


def test_new_projects_take_the_last_author(window):
    window.settings_store.set_default_author("A. Schäfer")
    try:
        window.new_document()
        assert window.current_document().meta.author == "A. Schäfer"
    finally:
        window.settings_store.set_default_author("")


# ------------------------------------------------------------------ Nachbesserungen aus dem Review
def test_page_bar_drag_uses_the_final_tab_order(window):
    window.new_document()
    document = window.current_document()
    for name in ("eins", "zwei", "drei"):
        subprograms.create_subprogram(document, name)
    bar = window.page_bar
    bar.refresh()
    bar._pressed = 1                       # „eins“ wird gezogen …
    bar.tabs.moveTab(1, 3)                 # … und hinter „drei“ abgelegt
    assert bar._moved
    bar._finish_drag()
    assert [p.display_name for p in document.pages[1:]] == ["zwei", "drei", "eins"]
    assert bar.tabs.tabText(3) == "eins" and bar.tabs.currentIndex() == document.current_page_index
    # das Hauptprogramm bleibt vorn; wer davor abgelegt wird, kommt an die zweite Stelle
    bar._pressed = 3
    bar.tabs.moveTab(3, 0)
    bar._finish_drag()
    assert [p.display_name for p in document.pages[1:]] == ["eins", "zwei", "drei"]
    bar._pressed = 0
    bar.tabs.moveTab(0, 2)
    bar._finish_drag()
    assert document.pages[0].is_main and bar.tabs.tabData(0) == 0


def test_extraction_keeps_loop_parts_together():
    document = DiagramDocument()
    scene = document.main_scene
    start = add(scene, T.START, 0, 0)
    begin = add(scene, T.LOOP, 0, 120)  # legt Beginn und Ende an
    end = next(item for item in scene.elements() if item.element_type is T.LOOP and item is not begin)
    link = next(c for c in scene.connections() if c.source is begin and c.target is end)
    scene.insert_element(T.PROCESS, QPointF(0, 240), into_connection=link)
    body = next(item for item in scene.elements() if item.element_type is T.PROCESS)
    stop = add(scene, T.END, 0, 600)
    connect(scene, start, "bottom", begin, "top")
    connect(scene, end, "bottom", stop, "top")
    scene.select_items([begin])
    assert "gehören zusammen" in subprograms.extraction_error(scene)
    scene.select_items([body])
    assert subprograms.extraction_error(scene) is None
    scene.select_items([begin, body, end])
    assert subprograms.extraction_error(scene) is None


def test_cut_page_keeps_the_page_if_the_clipboard_is_busy(monkeypatch):
    from app import clipboard
    document, page = two_page_document()
    monkeypatch.setattr(clipboard, "set_clipboard", lambda *args, **kwargs: False)
    assert not subprograms.cut_page(document, page)
    assert len(document.pages) == 2


def test_extraction_keeps_comments_attached():
    document, scene, (start, read, square, show, end) = counting_document()
    outside_note = add(scene, T.COMMENT, 300, 240)
    connect(scene, outside_note, "left", square, "right")
    inside_note = add(scene, T.COMMENT, -300, 120)
    connect(scene, inside_note, "right", read, "left")
    scene.select_items([square, show, inside_note])
    page = subprograms.extract_to_subprogram(document, scene, "quadriere")
    block = next(item for item in scene.elements() if item.element_type is T.SUBPROGRAM)
    # der Kommentar außerhalb hängt jetzt am Aufruf, der am zurückbleibenden Baustein bleibt, wo er ist
    assert {(c.source.element_id, c.target.element_id) for c in scene.connections() if c.is_annotation} == {
        (outside_note.element_id, block.element_id), (inside_note.element_id, read.element_id)}
    assert not [item for item in page.scene.elements() if item.is_comment]
    document.undo_stack.undo()
    assert {(c.source.element_id, c.target.element_id) for c in scene.connections() if c.is_annotation} == {
        (outside_note.element_id, square.element_id), (inside_note.element_id, read.element_id)}


def test_extraction_keeps_the_trunk_of_a_junction():
    from app.model.element_types import TRUNK_IN_KEY
    document = DiagramDocument()
    scene = document.main_scene
    start, check = chain(scene, (T.START, "Start"), (T.DECISION, "x > 0"))
    yes = add(scene, T.PROCESS, 0, 240)
    yes.set_text("y = 1")
    no = add(scene, T.PROCESS, 240, 240)
    no.set_text("y = 2")
    join = add(scene, T.JUNCTION, 0, 360)
    end = add(scene, T.END, 0, 480)
    connect(scene, check, "bottom", yes, "top").set_label("ja")
    connect(scene, check, "right", no, "top").set_label("nein")
    connect(scene, yes, "bottom", join, "top")
    side = connect(scene, no, "bottom", join, "right")
    connect(scene, join, "bottom", end, "top")
    join.data.properties[TRUNK_IN_KEY] = side.connection_id
    scene.select_items([check, yes, no])
    subprograms.extract_to_subprogram(document, scene, "wähle")
    ids = {c.connection_id for c in scene.connections()}
    assert join.data.properties[TRUNK_IN_KEY] in ids


def test_output_of_with_a_variable_named_von():
    from app.analysis import text as TX
    spec = TX.output_spec('Ausgabe von "Summe:" x', {"x"})
    assert spec.parts == (("string", "Summe:"), ("expression", "x"))
    spec = TX.output_spec('Ausgabe "Summe:" von', {"von"})
    assert ("expression", "von") in spec.parts


def test_duplicate_keeps_return_type_and_parameters():
    document = DiagramDocument()
    page = subprograms.create_subprogram(document, "int f(int x)")
    copy = subprograms.duplicate_subprogram(document, page)
    assert copy.display_name == "int f2(int x)"
    assert [item.data.text for item in copy.start_items()] == ["int f2(int x)"]
    words = subprograms.create_subprogram(document, "Werte prüfen")
    assert subprograms.duplicate_subprogram(document, words).display_name == "Werte prüfen 2"
