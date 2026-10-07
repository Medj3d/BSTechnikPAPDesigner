"""Tests für das Arbeiten mit .pap-Dateien im Programm: Öffnen, Speichern,
Dateidialoge, Zwischenablage und automatisches Sichern."""

import os
import shutil

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app import clipboard, config
from app.diagnostics.checks import run_checks
from app.document import DiagramDocument, display_name_for_path
from app.fileformat.serializer import diagram_from_xml, load_diagram
from app.model.element_types import TRUNK_IN_KEY, TRUNK_OUT_KEY
from app.model.element_types import ElementType as T
from tests.conftest import add, connect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")
PAP_SAMPLE = os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap")
OLD_FORMAT = b'{"format": "bsTechnik-pap", "format_version": 1, "items": [], "connections": []}'


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


@pytest.fixture
def messages(monkeypatch):
    """Fängt Meldungsfenster ab und merkt sich ihre Texte."""
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: shown.append((title, text)))
    monkeypatch.setattr(QMessageBox, "information", lambda _p, title, text, *a, **k: shown.append((title, text)))
    return shown


def model(scene):
    """Alle gespeicherten Angaben einer Szene – ungerundet und in ihrer Reihenfolge."""
    return scene.element_data(), scene.connection_data()


def issues(scene):
    return [(i.severity, i.message, tuple(i.element_ids), tuple(i.connection_ids)) for i in run_checks(scene)]


def build_plan(scene):
    """Ein Plan mit allem, was beim Speichern verloren gehen könnte."""
    start = add(scene, T.START, 0, 0)
    read = add(scene, T.INPUT, 0, 120)
    read.set_text("n einlesen")
    begin = add(scene, T.LOOP, 0, 240)
    body = add(scene, T.PROCESS, 0, 480)
    body.set_text("summe = summe + i\nzaehler = zaehler + 1")
    loop_end = [e for e in scene.elements() if e.element_type is T.LOOP and e is not begin]
    decision = add(scene, T.DECISION, 0, 800)
    decision.set_text("summe > 10 ?")
    yes = add(scene, T.OUTPUT, 0, 980)
    no = add(scene, T.SUBPROGRAM, 320, 980)
    end = add(scene, T.END, 0, 1200)
    note = add(scene, T.COMMENT, 340, 0)
    note.set_text("Ein Kommentar\n  mit Einrückung")
    connect(scene, start, "bottom", read, "top")
    connect(scene, read, "bottom", begin, "top")
    connect(scene, begin, "bottom", body, "top")
    if loop_end:
        connect(scene, body, "bottom", loop_end[0], "top")
        connect(scene, loop_end[0], "bottom", decision, "top")
    else:
        connect(scene, body, "bottom", decision, "top")
    connect(scene, decision, "bottom", yes, "top")
    connect(scene, decision, "right", no, "top")
    trunk = connect(scene, yes, "bottom", end, "top")
    scene.connect_to_edge(no, "bottom", trunk, QPointF(0, 1100))  # Verbindungspunkt auf dem Pfeil
    connect(scene, note, "left", start, "right")
    # fachlich fragwürdig → rot: zweiter Ausgang, Eingang am Start, doppelte Verbindung
    red = [connect(scene, read, "right", no, "left"),
           connect(scene, body, "left", start, "left"),
           connect(scene, start, "bottom", read, "top")]
    manual = scene.connections()[2]
    old = dict(manual.data.routing)
    manual.data.routing = {"mode": "manual", "axis": "y", "value": 333.25}
    manual.update_route()
    scene.commit_routing_change(manual, old, dict(manual.data.routing))
    scene.select_items([body])
    scene.bring_to_front()
    scene.select_items([])
    return red


# ------------------------------------------------------- Speichern und Laden
def test_project_is_restored_exactly(document, tmp_path):
    scene = document.scene
    red = build_plan(scene)
    assert all(conn is not None and conn.warning for conn in red)
    document.meta.author = "Autor"
    document.meta.description = "Beschreibung\nmit zwei Zeilen"
    document.settings.grid_size = 30
    document.set_snap_to_grid(False)
    path = tmp_path / "plan.pap"
    document.save(str(path))

    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == [] and reopened.native_file and not reopened.is_modified
    assert model(reopened.scene) == model(scene)
    assert reopened.meta == document.meta
    assert reopened.settings == document.settings
    # Prüfzustände: dieselben Verbindungen rot, mit denselben Begründungen; dieselbe Hinweisliste
    assert scene.connection_warnings() and reopened.scene.connection_warnings() == scene.connection_warnings()
    assert issues(reopened.scene) == issues(scene)
    junctions = [e for e in reopened.scene.elements() if e.is_junction]
    assert len(junctions) == 1
    assert reopened.scene.connection(junctions[0].data.properties[TRUNK_IN_KEY]).target is junctions[0]
    assert reopened.scene.connection(junctions[0].data.properties[TRUNK_OUT_KEY]).source is junctions[0]
    # Bausteine wurden nicht neu vermessen oder verschoben
    for item in reopened.scene.elements():
        original = scene.element(item.element_id)
        assert (item.pos(), item.width, item.height, item.zValue()) == \
               (original.pos(), original.width, original.height, original.zValue())
    for conn in reopened.scene.connections():
        assert conn.points() == scene.connection(conn.connection_id).points()

    # zweites Speichern ändert nichts mehr (bis auf den Änderungszeitpunkt)
    again = tmp_path / "plan2.pap"
    reopened.meta.modified = document.meta.modified
    from app.fileformat.serializer import save_diagram
    save_diagram(reopened.to_diagram(), str(again))
    assert again.read_bytes() == path.read_bytes()
    reopened.scene.clear_diagram()


def test_example_file_opens_unchanged():
    result = load_diagram(EXAMPLE)
    document = DiagramDocument.open_file(EXAMPLE)
    assert document.native_file and document.load_warnings == []
    assert document.display_name == "Beispiel_Mittelwert"
    assert all(connection.path for connection in result.diagram.connections)
    assert model(document.scene) == (result.diagram.elements, result.diagram.connections)
    document.scene.clear_diagram()


def test_lines_run_exactly_as_before_after_reopening(document, tmp_path):
    """Die automatische Linienführung hängt von der Entstehung ab – gespeichert wird, was zu sehen ist."""
    scene = document.scene
    a = add(scene, T.PROCESS, 0, 0)
    b = add(scene, T.PROCESS, 0, 400)
    back = connect(scene, b, "bottom", a, "top")  # Rücksprung, läuft seitlich vorbei
    add(scene, T.PROCESS, -200, 200)
    add(scene, T.PROCESS, 200, 200)  # später ergänzt: neu berechnet verliefe die Linie anders
    shown = back.points()
    path = tmp_path / "linie.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.scene.connection(back.connection_id).points() == shown
    assert model(reopened.scene) == model(scene)
    # die übernommene Linie verhält sich wie jede andere: Verschieben führt sie neu
    moved = reopened.scene.element(a.element_id)
    reopened.scene.apply_moves({moved.element_id: ((0.0, 0.0), (400.0, 0.0))}, "verschieben")
    points = reopened.scene.connection(back.connection_id).points()
    assert points != shown and points[-1] == pytest.approx((400.0, -30.0))
    reopened.undo_stack.undo()
    reopened.scene.clear_diagram()


def test_stored_route_that_no_longer_fits_is_ignored(document, tmp_path):
    scene = document.scene
    a = add(scene, T.PROCESS, 0, 0)
    b = add(scene, T.PROCESS, 0, 200)
    conn = connect(scene, a, "bottom", b, "top")
    fresh = conn.points()
    diagram = document.to_diagram()
    diagram.connections[0].path = [(500.0, 500.0), (500.0, 900.0)]  # passt nicht zu den Anschlüssen
    from app.fileformat.serializer import save_diagram
    path = tmp_path / "unpassend.pap"
    save_diagram(diagram, str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert reopened.load_warnings == []
    assert reopened.scene.connections()[0].points() == fresh
    reopened.scene.clear_diagram()


def test_hint_list_has_the_same_order_after_reopening(document, tmp_path):
    scene = document.scene
    start = add(scene, T.START, 0, 0)
    x = add(scene, T.PROCESS, 0, 200)
    y = add(scene, T.PROCESS, 300, 200)
    connect(scene, start, "bottom", x, "top")
    red_first = connect(scene, x, "left", start, "left")   # rot: Eingang am Start
    connect(scene, x, "right", y, "left")                  # rot: zweiter Ausgang
    scene.select_items([red_first])
    scene.delete_selection()
    document.undo_stack.undo()  # wieder da – und weiterhin älter als die zweite rote Verbindung
    scene.select_items([])
    path = tmp_path / "hinweise.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert len([i for i in issues(scene) if i[3]]) == 2
    assert issues(reopened.scene) == issues(scene)
    reopened.scene.clear_diagram()


@pytest.mark.parametrize("typed, stored", [
    ("Zeile eins\x0bZeile zwei", "Zeile eins\nZeile zwei"),   # weicher Umbruch aus Word/PowerPoint
    ("Seite 1\x0cSeite 2", "Seite 1\nSeite 2"),
    ("a\x00b\x1bc", "abc"),
    ("Tab\tbleibt", "Tab\tbleibt"),
])
def test_typed_text_is_shown_exactly_as_it_will_be_stored(document, tmp_path, typed, stored):
    scene = document.scene
    item = add(scene, T.PROCESS, 0, 0)
    target = add(scene, T.PROCESS, 0, 200)
    conn = connect(scene, item, "bottom", target, "top")
    scene.begin_element_edit(item, select_all=True)
    scene._editor.setPlainText(typed)
    scene.commit_edit()
    scene.begin_label_edit(conn)
    scene._editor.setPlainText(typed)
    scene.commit_edit()
    assert item.data.text == stored and conn.data.label == stored
    path = tmp_path / "text.pap"
    document.save(str(path))
    reopened = DiagramDocument.open_file(str(path))
    assert model(reopened.scene) == model(scene)
    reopened.scene.clear_diagram()


def test_display_name_drops_the_extension():
    assert display_name_for_path("C:/x/Mein Plan.pap") == "Mein Plan"
    assert display_name_for_path("C:/x/PLAN.PAP") == "PLAN"
    assert config.FILE_EXTENSION == ".pap"


# ------------------------------------------------------------- Dateidialoge
def test_save_dialog_offers_only_pap_and_appends_the_extension(window, monkeypatch, tmp_path):
    window.new_document()
    document = window.current_document()
    add(document.scene, T.PROCESS, 0, 0)
    calls = []

    def fake_save(_parent, _title, suggestion, file_filter, *args, **kwargs):
        calls.append((suggestion, file_filter))
        return str(tmp_path / "ohne_endung"), file_filter

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_save)
    assert window.save_document(document)
    suggestion, file_filter = calls[0]
    assert suggestion.endswith(".pap")
    assert file_filter == config.FILE_DIALOG_FILTER and "*.pap" in file_filter and ";;" not in file_filter
    assert document.file_path == str(tmp_path / "ohne_endung.pap")
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["ohne_endung.pap"]
    assert load_diagram(document.file_path).native
    # einmal gespeichert: „Speichern“ fragt nicht mehr nach
    add(document.scene, T.PROCESS, 0, 200)
    assert window.save_document(document) and len(calls) == 1


def test_other_extensions_typed_by_the_user_still_end_in_pap(window, monkeypatch, tmp_path):
    window.new_document()
    document = window.current_document()
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(tmp_path / "plan.bsTechnik"), ""))
    assert window.save_document_as(document)
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == ["plan.bsTechnik.pap"]


def test_open_dialog_filters_pap(window, monkeypatch):
    calls = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda _p, _t, _d, file_filter, *a, **k: calls.append(file_filter) or ("", ""))
    window.open_file_dialog()
    assert calls == ["Programmablaufpläne (*.pap)"] == [config.FILE_DIALOG_FILTER]


def test_save_suggestion_uses_the_extension_exactly_once(window, monkeypatch, tmp_path):
    window.new_document()
    document = window.current_document()
    meta = document.meta.copy()
    meta.name = "Mittelwert.pap"
    document.apply_properties(meta, document.settings.grid_size)
    suggestions = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda _p, _t, suggestion, *a, **k: suggestions.append(suggestion) or ("", ""))
    assert not window.save_document(document)
    assert os.path.basename(suggestions[0]) == "Mittelwert.pap"


def test_appending_the_extension_never_replaces_a_file_unasked(window, monkeypatch, tmp_path):
    """Der Dialog prüft nur den eingegebenen Namen – existiert der Name mit Endung schon, wird nachgefragt."""
    existing = tmp_path / "plan.pap"
    existing.write_bytes(b"wichtig")
    window.new_document()
    document = window.current_document()
    add(document.scene, T.PROCESS, 0, 0)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "plan"), ""))
    questions = []
    answer = [QMessageBox.StandardButton.No]
    monkeypatch.setattr(QMessageBox, "question", lambda _p, _t, text, *a, **k: questions.append(text) or answer[0])
    assert not window.save_document(document)
    assert existing.read_bytes() == b"wichtig" and "plan.pap" in questions[0] and document.file_path is None
    answer[0] = QMessageBox.StandardButton.Yes
    assert window.save_document(document)
    assert load_diagram(str(existing)).native and len(questions) == 2


def test_there_is_no_separate_import_or_second_project_format(window):
    assert window.actions.get("import_pap") is None
    assert not any("mport" in name for name in window.actions.all())
    assert not hasattr(window, "import_papdesigner")
    file_menu = window.menuBar().actions()[0].menu()
    titles = [a.text().replace("&", "") for a in file_menu.actions()]
    assert not any("mport" in title for title in titles)
    assert window._openable("C:/x/plan.pap") and window._openable("C:/x/PLAN.PAP")
    assert not window._openable("C:/x/plan.bsTechnik") and not window._openable("C:/x/plan.json")


# ----------------------------------------------- Öffnen und Speichern im Fenster
def test_old_format_is_rejected(window, messages, tmp_path):
    for name in ("alt.bsTechnik", "alt.pap"):
        path = tmp_path / name
        path.write_bytes(OLD_FORMAT)
        assert not window.open_file(str(path))
    assert len(messages) == 2 and window.views() == []
    assert all(title == "Datei kann nicht geöffnet werden" for title, _ in messages)
    # beide Meldungen nennen den Grund: kein .pap – nicht „beschädigt“
    assert all("Format .pap" in text and "beschädigt" not in text for _, text in messages)
    assert window.settings_store.recent_files()[:1] != [str(tmp_path / "alt.pap")]


def test_only_pap_files_can_be_opened_whatever_they_contain(window, messages, tmp_path):
    for name in ("plan.xml", "plan", "plan.pap.bak", "plan.bsTechnik"):
        other = shutil.copy(EXAMPLE, tmp_path / name)  # gültiger Inhalt, falsche Endung
        assert not window.open_file(str(other))
    assert window.views() == [] and len(messages) == 4
    assert all("nur .pap-Dateien" in text for _, text in messages)


def test_recent_files_list_only_offers_pap_files(window, tmp_path):
    store = window.settings_store
    good = str(tmp_path / "neu.pap")
    try:
        store.set_value("recent_files", [str(tmp_path / "alt.bsTechnik"), good, str(tmp_path / "x.json"),
                                         str(tmp_path / "GROSS.PAP")])
        assert store.recent_files() == [good, str(tmp_path / "GROSS.PAP")]
        window._refresh_recent_menu()
        titles = [action.text() for action in window.recent_menu.actions()]
        assert len([t for t in titles if ".pap" in t.lower()]) == 2 and not any("bsTechnik" in t for t in titles)
    finally:
        store.clear_recent_files()


def test_file_from_another_program_is_not_replaced_unasked(window, messages, monkeypatch, tmp_path):
    """Eine PapDesigner-Datei öffnet wie jedes Projekt; vor dem ersten Überschreiben wird gefragt."""
    path = shutil.copy(PAP_SAMPLE, tmp_path / "mittelwert.pap")
    original = open(path, "rb").read()
    assert window.open_file(str(path))
    document = window.current_document()
    assert document.file_path == str(path) and not document.is_modified and not document.native_file
    assert messages == []
    before = model(document.scene)
    asked = []
    choice = ["cancel"]
    monkeypatch.setattr(window, "_ask_foreign_overwrite", lambda doc: asked.append(doc) or choice[0])
    save_dialogs = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda _p, _t, suggestion, *a, **k: save_dialogs.append(suggestion) or ("", ""))

    assert not window.save_document(document)  # Abbrechen
    choice[0] = "save_as"
    assert not window.save_document(document)  # Speichern unter … (hier ebenfalls abgebrochen)
    assert save_dialogs == [str(path)] and len(asked) == 2
    assert open(path, "rb").read() == original

    choice[0] = "overwrite"
    assert window.save_document(document)
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == ["mittelwert.pap"]
    result = load_diagram(str(path))
    assert result.native and result.warnings == []
    assert (result.diagram.elements, result.diagram.connections) == before
    # ab jetzt ein gewöhnliches Projekt: keine weitere Rückfrage
    add(document.scene, T.PROCESS, 600, 600)
    assert window.save_document(document) and len(asked) == 3


def test_document_with_another_extension_is_saved_as_pap(window, monkeypatch, tmp_path):
    """Sicherheitsnetz: Selbst mit einem fremden Dateinamen im Dokument entsteht nur eine .pap-Datei."""
    source = shutil.copy(EXAMPLE, tmp_path / "plan.xml")
    original = open(source, "rb").read()
    document = DiagramDocument.open_file(str(source))
    window.add_document(document)
    calls = []

    def fake_save(_parent, _title, suggestion, file_filter, *args, **kwargs):
        calls.append(suggestion)
        return suggestion, file_filter

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_save)
    assert window.save_document(document)
    assert calls == [str(source) + ".pap"]
    assert document.file_path == str(source) + ".pap"
    assert open(source, "rb").read() == original  # die fremd benannte Datei bleibt unberührt
    assert load_diagram(document.file_path).native


def test_dropped_files(window, messages, tmp_path):
    from PySide6.QtCore import QMimeData, QPoint, QUrl
    from PySide6.QtGui import QDropEvent
    good = shutil.copy(EXAMPLE, tmp_path / "gut.pap")
    other = tmp_path / "anders.bsTechnik"
    other.write_bytes(OLD_FORMAT)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(other)), QUrl.fromLocalFile(str(good))])
    window.dropEvent(QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                                Qt.KeyboardModifier.NoModifier))
    assert [view.document.file_path for view in window.views()] == [str(good)]
    assert messages == []


def test_view_does_not_creep_when_a_file_is_opened_and_saved_again(window, qapp, tmp_path):
    path = str(shutil.copy(EXAMPLE, tmp_path / "ansicht.pap"))
    states = []
    for _ in range(5):
        assert window.open_file(path)
        qapp.processEvents()
        assert window.save_document(window.current_document())
        settings = load_diagram(path).diagram.settings
        states.append((settings.zoom, settings.view_center_x, settings.view_center_y))
        assert window.close_tab(window.tabs.currentIndex())
    # die Ansicht rastet beim ersten Mal auf ganze Bildschirmpixel ein und bleibt dann stehen
    assert states[1] == states[2] == states[3] == states[4]
    assert abs(states[4][1] - 100.0) <= 2 and abs(states[4][2] - 560.0) <= 2


# ---------------------------------------------------------- Zwischenablage
def test_clipboard_holds_pap_content(scene):
    a = add(scene, T.PROCESS, 0, 0)
    a.set_text("x = 1 & y < 2")
    b = add(scene, T.DECISION, 0, 200)
    connect(scene, a, "bottom", b, "top")
    scene.select_items([a, b])
    assert clipboard.copy_selection(scene)
    mime = QApplication.clipboard().mimeData()
    assert mime.formats().count(clipboard.MIME_TYPE) == 1 and clipboard.MIME_TYPE.endswith("+xml")
    assert not any("json" in fmt for fmt in mime.formats())
    result = diagram_from_xml(bytes(mime.data(clipboard.MIME_TYPE)))
    assert result.native and result.warnings == []
    assert sorted(e.id for e in result.diagram.elements) == sorted([a.element_id, b.element_id])
    assert result.diagram.connections == [scene.connections()[0].data]
    selection = clipboard.selection_payload(scene)
    assert (result.diagram.elements, result.diagram.connections) == (selection.elements, selection.connections)
    pasted = clipboard.clipboard_payload()
    assert (pasted.elements, pasted.connections) == (selection.elements, selection.connections)


def test_clipboard_ignores_foreign_content(scene):
    from PySide6.QtCore import QMimeData
    mime = QMimeData()
    mime.setData(clipboard.MIME_TYPE, OLD_FORMAT)
    QApplication.clipboard().setMimeData(mime)
    assert clipboard.clipboard_payload() is None


def test_cut_and_paste_returns_to_the_original_position(window):
    window.new_document()
    scene = window.current_document().scene
    item = add(scene, T.PROCESS, 120, 80)
    scene.select_items([item])
    window.cut()
    assert scene.elements() == []
    window.paste()
    (pasted,) = scene.elements()
    assert (pasted.pos().x(), pasted.pos().y()) == (120, 80)
    window.paste()
    assert sorted((e.pos().x(), e.pos().y()) for e in scene.elements()) == [(120, 80), (160, 120)]


# ------------------------------------------------------ Automatisches Sichern
def test_autosave_writes_pap_backups(window, tmp_path):
    window.new_document()
    document = window.current_document()
    build_plan(document.scene)
    assert window.autosave.save_now() == 1
    backups = [n for n in os.listdir(window.autosave.directory) if n.endswith(".pap")]
    assert len(backups) == 1
    assert not [n for n in os.listdir(window.autosave.directory) if n.endswith(".bsTechnik")]
    result = load_diagram(os.path.join(window.autosave.directory, backups[0]))
    assert result.native and (result.diagram.elements, result.diagram.connections) == model(document.scene)
