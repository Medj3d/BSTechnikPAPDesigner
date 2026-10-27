"""Version 1.9.0: Bild in die Zwischenablage, Schreibtischtest (Schritt zurück, Abspielen, Tabelle mit Bedingung
und Ausgabe, Kopieren/CSV) und vom Administrator abschaltbare Updates."""

import csv

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app import clipboard, policy
from app.model.element_types import ElementType as T
from app.simulation.panel import SimulationPanel, rows_as_tsv, table_rows
from tests.conftest import add, connect


@pytest.fixture(autouse=True)
def _application(qapp):
    yield


@pytest.fixture
def window(qapp, tmp_path):
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


def counting_plan(scene):
    """Start → x = 0 → x < 3? (ja: x = x + 1 → zurück) nein: Ausgabe x → Ende."""
    items = []
    for index, (etype, text) in enumerate([(T.START, "Start"), (T.PROCESS, "x = 0"), (T.DECISION, "x < 3"),
                                           (T.PROCESS, "x = x + 1"), (T.OUTPUT, "x"), (T.END, "Ende")]):
        item = add(scene, etype, 0, index * 140)
        item.set_text(text)
        items.append(item)
    start, init, check, increment, output, end = items
    connect(scene, start, "bottom", init, "top")
    connect(scene, init, "bottom", check, "top")
    connect(scene, check, "right", increment, "top").set_label("ja")
    connect(scene, check, "bottom", output, "top").set_label("nein")
    connect(scene, increment, "left", check, "left")
    connect(scene, output, "bottom", end, "top")
    return items


# ------------------------------------------------------------------ Bild in die Zwischenablage
def test_copy_puts_pap_text_and_image_on_the_clipboard(scene):
    a = add(scene, T.START, 0, 0)
    b = add(scene, T.PROCESS, 0, 120)
    far = add(scene, T.END, 600, 600)
    connect(scene, a, "bottom", b, "top")
    scene.select_items([a, b])
    assert clipboard.copy_selection(scene)
    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat(clipboard.MIME_TYPE) and mime.hasText() and mime.hasImage()
    selection = QApplication.clipboard().image()
    # doppelte Auflösung, nur die Auswahl (der entfernte Baustein liegt nicht mit im Bild)
    assert 0 < selection.width() < 2 * 400 and 0 < selection.height() < 2 * 400
    assert selection.dotsPerMeterX() == int(96 * clipboard.IMAGE_SCALE / 0.0254)
    assert all(item.isVisible() for item in scene.elements() + scene.connections())
    assert far.isVisible()


def test_copy_image_without_selection_copies_the_whole_page(scene):
    add(scene, T.START, 0, 0)
    add(scene, T.END, 600, 600)
    scene.clearSelection()
    assert clipboard.copy_image(scene)
    mime = QApplication.clipboard().mimeData()
    assert mime.hasImage() and not mime.hasFormat(clipboard.MIME_TYPE) and not clipboard.can_paste()
    image = QApplication.clipboard().image()
    assert image.width() > 2 * 600 and image.height() > 2 * 600


def test_copy_image_of_an_empty_page_fails_quietly(scene):
    assert not clipboard.copy_image(scene)


def test_copy_image_action_and_structogram_button(window):
    window.new_document()
    document = window.current_document()
    assert not window.actions["copy_image"].isEnabled()
    counting_plan(document.scene)
    window._update_actions()
    assert window.actions["copy_image"].isEnabled()
    window.actions["copy_image"].trigger()
    assert QApplication.clipboard().mimeData().hasImage()
    from app.nsd.dialog import StructogramDialog
    QApplication.clipboard().clear()
    dialog = StructogramDialog(document, window)
    dialog.copy_image()
    assert QApplication.clipboard().mimeData().hasImage()
    dialog.deleteLater()


# ------------------------------------------------------------------ Schreibtischtest
@pytest.fixture
def panel(document):
    counting_plan(document.scene)
    widget = SimulationPanel()
    widget.set_document(document)
    yield widget
    widget.set_document(None)
    widget.deleteLater()


def test_step_back_restores_everything(panel):
    panel.restart()
    for _ in range(4):
        panel.step()
    before = (dict(panel.simulator.variables), panel.simulator.current, len(panel.simulator.trace),
              panel.log.toPlainText())
    panel.step()
    panel.step()
    assert panel.back_button.isEnabled()
    panel.step_back()
    panel.step_back()
    after = (dict(panel.simulator.variables), panel.simulator.current, len(panel.simulator.trace),
             panel.log.toPlainText())
    assert after == before
    assert panel.trace_table.rowCount() == before[2]
    # und bis ganz an den Anfang
    while panel.back_button.isEnabled():
        panel.step_back()
    assert panel.simulator.trace == [] and panel.simulator.variables == {}


def test_step_back_after_the_end_and_after_input(document):
    scene = document.scene
    items = []
    for index, (etype, text) in enumerate([(T.START, "Start"), (T.INPUT, "Eingabe: n"), (T.OUTPUT, "n * 2"),
                                           (T.END, "Ende")]):
        item = add(scene, etype, 0, index * 120)
        item.set_text(text)
        items.append(item)
    for source, target in zip(items, items[1:]):
        connect(scene, source, "bottom", target, "top")
    panel = SimulationPanel()
    panel.set_document(document)
    panel.restart()
    panel.step()
    panel.step()  # wartet auf die Eingabe
    panel.input_field.setText("abc")  # wird abgelehnt: kein eigener Schritt
    panel.submit_input()
    history = len(panel._history)
    panel.input_field.setText("4")
    panel.submit_input()
    assert len(panel._history) == history + 1
    while not panel.simulator.finished:
        panel.step()
    assert panel.simulator.outputs == ["8"] and panel.outputs.toPlainText() == "8"
    panel.step_back()  # vor die Ausgabe des Endes
    panel.step_back()  # vor die Ausgabe
    assert panel.simulator.outputs == [] and panel.outputs.toPlainText() == ""
    panel.step_back()  # vor die Eingabe: wartet wieder
    assert panel.simulator.pending is not None and panel.input_row.isVisibleTo(panel)
    panel.deleteLater()


def test_autoplay_runs_to_the_end_and_waits_for_input(document, qapp):
    import time
    scene = document.scene
    items = []
    for index, (etype, text) in enumerate([(T.START, "Start"), (T.INPUT, "Eingabe: n"), (T.PROCESS, "n = n + 1"),
                                           (T.OUTPUT, "n"), (T.END, "Ende")]):
        item = add(scene, etype, 0, index * 120)
        item.set_text(text)
        items.append(item)
    for source, target in zip(items, items[1:]):
        connect(scene, source, "bottom", target, "top")
    panel = SimulationPanel()
    panel.set_document(document)
    panel.speed_slider.setValue(panel.speed_slider.maximum())

    def wait(condition, seconds=5):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        return condition()

    panel.toggle_play()
    assert panel.playing
    assert wait(lambda: panel.simulator.pending is not None)  # hält bei der Eingabe an …
    assert panel.playing
    panel.input_field.setText("41")
    panel.submit_input()  # … und läuft danach von selbst weiter
    assert wait(lambda: panel.simulator.finished)
    assert panel.simulator.outputs == ["42"] and not panel.playing
    # Anhalten
    panel.restart()
    panel.speed_slider.setValue(0)  # langsam: ein Schritt alle 2 Sekunden
    panel.toggle_play()
    qapp.processEvents()
    panel.toggle_play()
    assert not panel.playing
    steps = len(panel.simulator.trace)
    wait(lambda: False, 0.1)
    assert len(panel.simulator.trace) == steps
    panel.deleteLater()


def test_changing_the_plan_stops_playing_and_clears_history(panel, document):
    panel.restart()
    panel.step()
    panel.toggle_play()
    add(document.scene, T.PROCESS, 400, 0)
    assert not panel.playing and not panel.back_button.isEnabled()


def test_trace_table_has_condition_and_output_columns(panel):
    panel.restart()
    while not panel.simulator.finished:
        panel.step()
    rows = table_rows(panel.trace_table)
    assert rows[0][:5] == ["Schritt", "Baustein", "Bedingung", "Ausgabe", "x"]
    conditions = [row[2] for row in rows[1:] if row[1] == "x < 3"]
    assert conditions == ["ja", "ja", "ja", "nein"]
    outputs = [row[3] for row in rows[1:] if row[3]]
    assert outputs == ["3"]


def test_trace_table_copy_and_csv(panel, monkeypatch, tmp_path):
    panel.restart()
    for _ in range(4):
        panel.step()
    panel.tabs.setCurrentWidget(panel.trace_table)
    panel.copy_current()
    text = QApplication.clipboard().text()
    assert text.splitlines()[0] == "Schritt\tBaustein\tBedingung\tAusgabe\tx"
    assert len(text.splitlines()) == 5
    # nur markierte Zeilen (Strg+C in der Tabelle)
    panel.trace_table.selectRow(2)
    panel.trace_table.copy_rows()
    assert QApplication.clipboard().text().splitlines()[1].startswith("3\tx < 3\tja")
    target = tmp_path / "test"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    panel.save_current()
    with open(str(target) + ".csv", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0][:4] == ["Schritt", "Baustein", "Bedingung", "Ausgabe"] and len(rows) == 5
    # Texte (Protokoll) als Textdatei
    panel.tabs.setCurrentWidget(panel.log)
    panel.save_current()
    assert (tmp_path / "test.txt").read_text(encoding="utf-8").startswith("Start")


def test_tsv_keeps_one_line_per_row():
    assert rows_as_tsv([["a", "b\nc"], ["1", "2"]]) == "a\tb c\n1\t2\n"


# ------------------------------------------------------------------ Updates abschaltbar
def test_policy_file_disables_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "_registry_value", lambda name: None)
    assert not policy.updates_disabled(str(tmp_path))
    (tmp_path / policy.POLICY_FILE_NAME).write_text("﻿[Updates]\nDisabled=1\n", encoding="utf-8")
    assert policy.updates_disabled(str(tmp_path))
    (tmp_path / policy.POLICY_FILE_NAME).write_text("[Updates]\nDisabled=0\n", encoding="utf-8")
    assert not policy.updates_disabled(str(tmp_path))
    (tmp_path / policy.POLICY_FILE_NAME).write_text("kaputt ohne Abschnitt", encoding="utf-8")
    assert not policy.updates_disabled(str(tmp_path))


def test_registry_policy_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "_registry_value", lambda name: 1 if name == policy.DISABLE_UPDATES_VALUE else None)
    assert policy.updates_disabled(str(tmp_path))
    monkeypatch.setattr(policy, "_registry_value", lambda name: 0)
    assert not policy.updates_disabled(str(tmp_path))


def test_user_can_switch_off_the_check_on_start(window):
    store = window.settings_store
    try:
        store.set_check_updates_on_start(True)
        window._sync_update_actions()
        assert window.updates.check_on_start() == (not policy.updates_disabled())
        action = window.actions["check_updates_on_start"]
        assert action.isChecked() == (not policy.updates_disabled())
        action.trigger()  # ausschalten
        assert not store.check_updates_on_start() and not window.updates.check_on_start()
    finally:
        store.set_check_updates_on_start(True)


def test_admin_policy_locks_the_update_actions(window, monkeypatch):
    monkeypatch.setattr(policy, "updates_disabled", lambda directory=None: True)
    window._sync_update_actions()
    assert not window.actions["check_updates_on_start"].isEnabled()
    assert not window.actions["check_updates_on_start"].isChecked()
    assert not window.updates.check_on_start()
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, title, text, *a, **k: shown.append(text))
    started = []
    monkeypatch.setattr("threading.Thread.start", lambda self: started.append(self))
    window.updates.check(manual=True)
    assert shown and "Administrator" in shown[0] and started == []
    window.updates.check()
    assert started == [] and len(shown) == 1


def test_no_redirect_to_user_copy_when_updates_are_disabled(monkeypatch):
    """main.py fragt die Richtlinie vor dem Umleiten auf eine Kopie im Benutzerordner."""
    import main
    source = open(main.__file__, encoding="utf-8").read()
    assert "not policy.updates_disabled() and updater.redirect_to_user_program(arguments)" in source


def test_about_dialog_links_the_website(qapp):
    from app import config
    from app.dialogs.about import AboutDialog
    dialog = AboutDialog()
    label = dialog.website_label
    assert config.AUTHOR_WEBSITE == "https://medjed.net"
    assert 'href="https://medjed.net"' in label.text() and ">medjed.net</a>" in label.text()
    assert label.openExternalLinks()
    dialog.deleteLater()


# ------------------------------------------------------------------ Befunde aus dem Review (ChatGPT)
def test_cut_with_a_separately_selected_connection_removes_both(scene):
    a = add(scene, T.PROCESS, 0, 0)
    b = add(scene, T.PROCESS, 400, 0)
    c = add(scene, T.PROCESS, 400, 200)
    link = connect(scene, b, "bottom", c, "top")
    scene.select_items([a, link])
    assert clipboard.cut_selection(scene)
    assert scene.element(a.element_id) is None and scene.connection(link.connection_id) is None
    assert scene.element(b.element_id) is not None


def test_copy_keeps_the_selection(scene):
    a = add(scene, T.PROCESS, 0, 0)
    b = add(scene, T.PROCESS, 400, 0)
    c = add(scene, T.PROCESS, 400, 200)
    link = connect(scene, b, "bottom", c, "top")
    scene.select_items([a, link])
    clipboard.copy_selection(scene)
    assert a.isSelected() and link.isSelected()


def test_table_copy_keeps_spaces_inside_values():
    assert rows_as_tsv([["Ausgabe"], ["a  b"]]) == "Ausgabe\na  b\n"
    assert rows_as_tsv([["x\ty", "z"]]) == "x y\tz\n"


def test_user_copy_reads_the_policy_of_the_installation(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "_registry_value", lambda name: None)
    own, installed = tmp_path / "benutzerkopie", tmp_path / "installiert"
    own.mkdir()
    installed.mkdir()
    (installed / policy.POLICY_FILE_NAME).write_text("[Updates]\nDisabled=1\n", encoding="utf-8")
    monkeypatch.setattr(policy, "program_directory", lambda: str(own))
    monkeypatch.delenv(policy.INSTALLATION_ENV, raising=False)
    assert not policy.updates_disabled()
    monkeypatch.setenv(policy.INSTALLATION_ENV, str(installed))
    assert policy.updates_disabled()


def test_redirect_passes_the_installation_folder(monkeypatch, tmp_path):
    from app import updater
    started = []
    monkeypatch.setattr(updater.resources, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "user_updates_blocked", lambda: False)
    monkeypatch.setattr(updater, "newer_user_program", lambda: ("9.9.9", str(tmp_path)))
    monkeypatch.setattr(updater, "application_directory", lambda: "C:/Programme/PAP")
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: started.append(k["env"]))
    monkeypatch.delenv(updater.STARTED_FROM_UPDATE_ENV, raising=False)
    assert updater.redirect_to_user_program([])
    assert started[0][policy.INSTALLATION_ENV] == "C:/Programme/PAP"
