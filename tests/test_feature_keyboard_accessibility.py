"""Bedienung ohne Maus: „Verbinden mit …“ (Strg+Umschalt+V) und die Bausteinliste (Strg+Umschalt+L)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QListWidgetItem, QMenu

from app import block_list
from app.actions import clean_text, sequence_text
from app.block_list import BlockListPanel, ConnectDialog, flow_order, item_summary, item_title
from app.dialogs.settings import ShortcutTable
from app.dialogs.shortcuts import ShortcutsDialog
from app.model.element_types import ElementType
from tests.conftest import add, connect


@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    from app.settings_store import SettingsStore

    store = SettingsStore()
    for group in ("preferences", "view", "window", "shortcuts"):
        store._settings.remove(group)
    win = MainWindow(enable_autosave=False, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(1200, 800)
    win.show()
    if win.current_document() is None:
        win.new_document()
    win.current_scene().clear_diagram()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()
    qapp.processEvents()


def _menu_entries(menu: QMenu) -> list:
    found = []
    for action in menu.actions():
        found.append(action)
        if action.menu() is not None:
            found += _menu_entries(action.menu())
    return found


def _menus(window) -> dict:
    return {clean_text(action.text()): _menu_entries(action.menu()) for action in window.menuBar().actions()}


def _set_text(scene, item, text):
    item.set_text(text)
    item.data.text = text


def _lines(scene, source, target):
    return [c for c in scene.connections() if c.source is source and c.target is target]


def _choose(monkeypatch, element_id=None, label=None, accept=True):
    """Ersetzt ConnectDialog.exec: wählt das Ziel (und die Beschriftung) und bestätigt."""
    seen = {}

    def fake_exec(dialog):
        seen["dialog"] = dialog
        seen["targets"] = [dialog.list.item(row).data(block_list.ELEMENT_ID_ROLE) for row in range(dialog.list.count())]
        seen["texts"] = [dialog.list.item(row).text() for row in range(dialog.list.count())]
        if element_id is not None:
            dialog.select_target(element_id)
        if label is not None and dialog.label_combo is not None:
            dialog.label_combo.setCurrentIndex(dialog.label_combo.findData(label))
        if accept:
            dialog.accept()
        else:
            dialog.reject()
        return dialog.result()

    monkeypatch.setattr(ConnectDialog, "exec", fake_exec)
    return seen


# ================================================================== Befehle und Tasten
@pytest.mark.parametrize("name, key, menu", [("connect_to", "Ctrl+Shift+V", "Bearbeiten"),
                                             ("toggle_block_list", "Ctrl+Shift+L", "Ansicht")])
def test_new_commands_have_a_key_a_menu_entry_and_a_tooltip(window, name, key, menu):
    action = window.actions[name]
    assert action.shortcuts()[0] == QKeySequence(key)
    assert window.actions.default_shortcuts(name)[0] == QKeySequence(key)
    assert action.toolTip().endswith(f"({sequence_text(QKeySequence(key))})"), action.toolTip()
    assert action in _menus(window)[menu]
    assert name in window.actions.bindable()
    assert action.statusTip()


def test_new_keys_collide_with_nothing(window):
    owners: dict[str, str] = {}
    for name in window.actions.bindable():
        for sequence in window.actions.default_shortcuts(name):
            text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            assert text not in owners, f"{text}: {owners.get(text)} und {name}"
            owners[text] = name
    assert owners["Ctrl+Shift+V"] == "connect_to"
    assert owners["Ctrl+Shift+L"] == "toggle_block_list"


def test_settings_and_f1_list_the_new_keys(window):
    table = ShortcutTable(window.actions)
    assert table.edits["connect_to"][0].keySequence() == QKeySequence("Ctrl+Shift+V")
    assert table.edits["toggle_block_list"][0].keySequence() == QKeySequence("Ctrl+Shift+L")
    table.deleteLater()
    dialog = ShortcutsDialog(window, window.actions)
    keys = {dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())}
    assert sequence_text(QKeySequence("Ctrl+Shift+V")) in keys
    assert sequence_text(QKeySequence("Ctrl+Shift+L")) in keys
    # nach einer Änderung zeigt die Hilfe die neue Taste
    window.actions.assign("connect_to", [QKeySequence("Ctrl+Alt+F8")])
    dialog = ShortcutsDialog(window, window.actions)
    keys = {dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())}
    assert sequence_text(QKeySequence("Ctrl+Alt+F8")) in keys


def test_connect_command_is_only_active_for_a_block_that_can_start_a_line(window):
    scene = window.current_scene()
    action = window.actions["connect_to"]
    a = add(scene, ElementType.PROCESS, 0, 0)
    window._update_actions()
    assert not action.isEnabled()                  # nichts ausgewählt bzw. kein anderes Ziel
    end = add(scene, ElementType.END, 0, 200)
    scene.select_items([a])
    window._update_actions()
    assert action.isEnabled()
    scene.select_items([end])                      # aus einem Ende führt kein Pfeil heraus
    window._update_actions()
    assert not action.isEnabled()
    scene.select_items([a, end])                   # Mehrfachauswahl: unklar, von wo
    window._update_actions()
    assert not action.isEnabled()


def test_block_context_menu_offers_connect_to(window, monkeypatch):
    from app import main_window as main_window_module

    scene = window.current_scene()
    a = add(scene, ElementType.PROCESS, 0, 0)
    add(scene, ElementType.PROCESS, 0, 200)
    shown = {}

    class CapturingMenu(QMenu):
        def exec(self, *_args):
            shown.update({a.text(): a for a in self.actions() if not a.isSeparator()})

    monkeypatch.setattr(main_window_module, "QMenu", CapturingMenu)
    window.show_context_menu(a.scenePos(), QPoint(0, 0))
    assert shown.get("Verbinden &mit …") is window.actions["connect_to"]
    assert window.actions["connect_to"].isEnabled()


# ================================================================== Anschlüsse
def test_ports_follow_the_flow_downwards(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    assert scene.keyboard_ports(a, b) == ("bottom", "top")
    c = add(scene, ElementType.PROCESS, 400, 0)
    assert scene.keyboard_ports(a, c) == ("right", "left")


def test_back_arrow_leaves_from_the_side(scene):
    top = add(scene, ElementType.DECISION, 0, 0)
    below = add(scene, ElementType.PROCESS, 0, 300)
    connect(scene, top, "bottom", below, "top")
    source_port, target_port = scene.keyboard_ports(below, top)
    assert source_port in ("left", "right") and target_port == source_port
    # nie am Anschluss, an dem schon der Pfeil hereinkommt bzw. hinausgeht
    assert source_port != "top" and target_port != "bottom"


def test_decision_uses_a_free_exit(scene):
    decision = add(scene, ElementType.DECISION, 0, 0)
    yes = add(scene, ElementType.PROCESS, 0, 250)
    no = add(scene, ElementType.PROCESS, 300, 250)
    connect(scene, decision, "bottom", yes, "top")
    source_port, target_port = scene.keyboard_ports(decision, no)
    assert source_port == "right" and target_port in ("top", "left")


# ================================================================== Verbinden
def test_connect_blocks_is_one_undo_step_and_selects_the_arrow(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    stack = scene.undo_stack
    before = stack.count()
    connection_id = scene.connect_blocks(a, b)
    conn = scene.connection(connection_id)
    assert conn is not None and conn.source is a and conn.target is b
    assert (conn.data.source_port, conn.data.target_port) == ("bottom", "top")
    assert stack.count() == before + 1
    assert scene.selectedItems() == [conn]
    stack.undo()
    assert scene.connection(connection_id) is None and not _lines(scene, a, b)
    stack.redo()
    assert len(_lines(scene, a, b)) == 1


def test_decision_gets_yes_then_no_or_the_chosen_label(scene):
    decision = add(scene, ElementType.DECISION, 0, 0)
    first = add(scene, ElementType.PROCESS, 0, 250)
    second = add(scene, ElementType.PROCESS, 300, 250)
    yes = scene.connection(scene.connect_blocks(decision, first))
    no = scene.connection(scene.connect_blocks(decision, second))
    assert yes.data.label == "ja" and no.data.label == "nein"
    assert yes.data.source_port != no.data.source_port
    scene.undo_stack.undo()
    scene.undo_stack.undo()
    chosen = scene.connection(scene.connect_blocks(decision, first, label="nein"))
    assert chosen.data.label == "nein"
    # die Beschriftung gilt nur an einer Verzweigung
    other = scene.connection(scene.connect_blocks(first, second, label="nein"))
    assert other.data.label == ""


def test_menu_command_connects_to_the_chosen_target(window, monkeypatch):
    scene = window.current_scene()
    start = add(scene, ElementType.START, 0, 0)
    a = add(scene, ElementType.PROCESS, 0, 150)
    b = add(scene, ElementType.OUTPUT, 0, 300)
    _set_text(scene, a, "x = 1")
    _set_text(scene, b, "x")
    connect(scene, start, "bottom", a, "top")
    scene.select_items([a])
    window._update_actions()
    seen = _choose(monkeypatch, element_id=b.element_id)
    before = scene.undo_stack.count()
    window.actions["connect_to"].trigger()
    lines = _lines(scene, a, b)
    assert len(lines) == 1 and scene.selectedItems() == lines
    assert scene.undo_stack.count() == before + 1
    # Ziele: alle anderen Bausteine, in die ein Pfeil führen kann (ohne Quelle und Start)
    assert seen["targets"] == [b.element_id]
    assert seen["texts"] == ["Ausgabe „x“"]


def test_cancel_creates_nothing(window, monkeypatch):
    scene = window.current_scene()
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    scene.select_items([a])
    _choose(monkeypatch, element_id=b.element_id, accept=False)
    before = scene.undo_stack.count()
    assert window.connect_selected_to() is None
    assert not scene.connections() and scene.undo_stack.count() == before


def test_menu_command_passes_the_chosen_decision_label(window, monkeypatch):
    scene = window.current_scene()
    decision = add(scene, ElementType.DECISION, 0, 0)
    target = add(scene, ElementType.PROCESS, 300, 250)
    scene.select_items([decision])
    seen = _choose(monkeypatch, element_id=target.element_id, label="nein")
    window.connect_selected_to()
    assert seen["dialog"].label_combo is not None
    (line,) = _lines(scene, decision, target)
    assert line.data.label == "nein"


def test_shortcut_opens_the_dialog_from_the_canvas(window, monkeypatch, qapp):
    window.activateWindow()
    QTest.qWait(30)
    if QApplication.activeWindow() is not window:
        pytest.skip("Das Testfenster wird nicht aktiv – echte Tastendrücke lassen sich hier nicht prüfen")
    scene = window.current_scene()
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    scene.select_items([a])
    seen = _choose(monkeypatch, element_id=b.element_id)
    view = window.current_view()
    view.setFocus()
    qapp.processEvents()
    QTest.keyClick(view, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert "dialog" in seen and len(_lines(scene, a, b)) == 1


# ================================================================== Dialog
def test_dialog_lists_filters_and_is_accessible(scene, qapp):
    start = add(scene, ElementType.START, 0, -150)
    first = add(scene, ElementType.PROCESS, 0, 0)
    decision = add(scene, ElementType.DECISION, 0, 200)
    out = add(scene, ElementType.OUTPUT, 0, 450)
    _set_text(scene, first, "i = 0")
    _set_text(scene, decision, "i >= 3")
    _set_text(scene, out, "summe")
    connect(scene, start, "bottom", first, "top")
    connect(scene, first, "bottom", decision, "top")
    connect(scene, decision, "bottom", out, "top")
    dialog = ConnectDialog(decision, block_list.connect_targets(scene, decision))
    texts = [dialog.list.item(row).text() for row in range(dialog.list.count())]
    # ohne die Quelle und ohne Start (in einen Start führt kein Pfeil), in Ablaufreihenfolge
    assert texts == ["Vorgang „i = 0“", "Ausgabe „summe“ – schon verbunden"]
    for widget in (dialog.search, dialog.list, dialog.label_combo):
        assert widget.accessibleName()
    assert dialog.accessibleName()
    assert dialog.list.item(0).data(Qt.ItemDataRole.AccessibleTextRole) == texts[0]
    # Ja-Ausgang ist belegt: vorgeschlagen wird „nein“
    assert dialog.label() == "nein"
    assert dialog.target() is first
    dialog.search.setText("summe")
    assert dialog.list.item(0).isHidden() and dialog.target() is out
    dialog.search.setText("gibt es nicht")
    assert dialog.target() is None and not dialog.ok_button.isEnabled()
    dialog.search.setText("")
    dialog.select_target(first.element_id)
    QTest.keyClick(dialog.search, Qt.Key.Key_Down)   # Pfeiltasten im Suchfeld wählen in der Liste
    assert dialog.target() is out
    QTest.keyClick(dialog.search, Qt.Key.Key_Up)
    assert dialog.target() is first
    dialog.deleteLater()


def test_dialog_warns_when_the_source_already_has_its_arrow(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    c = add(scene, ElementType.PROCESS, 300, 200)
    connect(scene, a, "bottom", b, "top")
    dialog = ConnectDialog(a, block_list.connect_targets(scene, a))
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("schon ein Pfeil" in text for text in texts), texts
    assert dialog.label_combo is None and dialog.label() is None
    assert c in block_list.connect_targets(scene, a)
    dialog.deleteLater()


def test_dialog_tab_order_reaches_every_field(scene):
    decision = add(scene, ElementType.DECISION, 0, 0)
    add(scene, ElementType.PROCESS, 0, 250)
    dialog = ConnectDialog(decision, block_list.connect_targets(scene, decision))
    chain, widget = [], dialog.search
    for _ in range(8):
        chain.append(widget)
        widget = widget.nextInFocusChain()
        while not widget.focusPolicy() & Qt.FocusPolicy.TabFocus:
            widget = widget.nextInFocusChain()
    assert dialog.list in chain and dialog.label_combo in chain and dialog.ok_button in chain
    dialog.deleteLater()


# ================================================================== Reihenfolge und Texte
def test_flow_order_follows_yes_before_no_and_skips_junctions(scene):
    start = add(scene, ElementType.START, 0, 0)
    decision = add(scene, ElementType.DECISION, 0, 200)
    no_branch = add(scene, ElementType.OUTPUT, 300, 300)   # liegt weiter oben als der Ja-Zweig
    yes_branch = add(scene, ElementType.PROCESS, 0, 450)
    end = add(scene, ElementType.END, 0, 650)
    comment = add(scene, ElementType.COMMENT, -400, -100)   # ganz oben, aber nicht Teil des Ablaufs
    connect(scene, start, "bottom", decision, "top")
    connect(scene, decision, "right", no_branch, "top")
    no = _lines(scene, decision, no_branch)[0]
    no.data.label = "nein"
    connect(scene, decision, "bottom", yes_branch, "top")
    _lines(scene, decision, yes_branch)[0].data.label = "ja"
    host = connect(scene, yes_branch, "bottom", end, "top")
    scene.insert_junction(host, QPointF(0, 560))
    connect(scene, no_branch, "bottom", end, "right")
    order = flow_order(scene)
    assert order[:5] == [start, decision, yes_branch, end, no_branch]
    assert comment in order and all(not item.is_junction for item in order)


def test_summary_names_targets_and_labels(scene):
    start = add(scene, ElementType.START, 0, 0)
    decision = add(scene, ElementType.DECISION, 0, 200)
    out = add(scene, ElementType.OUTPUT, 0, 450)
    end = add(scene, ElementType.END, 300, 450)
    _set_text(scene, decision, "i >= 3")
    connect(scene, start, "bottom", decision, "top")
    scene.connect_blocks(decision, out)
    scene.connect_blocks(decision, end)
    assert item_summary(start) == "Start „Start“  → Verzweigung „i >= 3“"
    assert item_summary(decision) == "Verzweigung „i >= 3“  → Ausgabe „Ausgabe“ (ja); → Ende „Ende“ (nein)"
    assert item_summary(out) == "Ausgabe „Ausgabe“  kein Pfeil heraus"
    assert item_summary(end) == "Ende „Ende“"


def test_summary_goes_through_junctions_and_names_loops_and_comments(scene):
    loop = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    host = connect(scene, loop, "bottom", b, "top")
    scene.insert_junction(host, QPointF(0, 150))
    assert item_summary(loop).endswith("→ Vorgang „Vorgang“")
    begin = add(scene, ElementType.LOOP, 400, 0)
    assert item_title(begin).startswith("Schleifenbeginn")
    comment = add(scene, ElementType.COMMENT, 300, 300)
    scene.create_connection(comment, "left", b, "right")
    assert item_summary(comment) == "Kommentar „Kommentar“  gehört zu Vorgang „Vorgang“"


# ================================================================== Bausteinliste
def test_block_list_is_hidden_by_default_and_sits_beside_the_palette(window):
    dock = window.block_list_dock
    assert isinstance(dock, QDockWidget) and dock.isHidden()
    assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.actions["toggle_block_list"] is dock.toggleViewAction()
    assert clean_text(window.actions["toggle_block_list"].text()) == "Bausteinliste"
    assert dock.windowTitle() == "Bausteinliste"


def test_shortcut_action_shows_the_list_and_puts_the_focus_into_it(window, qapp):
    canvas_width = window.current_view().width()
    window.actions["toggle_block_list"].trigger()
    QTest.qWait(20)
    assert window.block_list_dock.isVisible()
    panel = window.block_list_panel
    assert panel.list.accessibleName() == "Bausteinliste" and panel.list.accessibleDescription()
    if QApplication.activeWindow() is window:
        assert QApplication.focusWidget() is panel.list
    # eigene Spalte neben dem Feld „Bausteine“: dessen Einträge bleiben ganz zu sehen (nicht darunter gestapelt)
    palette = window.palette_dock.geometry()
    listed = window.block_list_dock.geometry()
    assert listed.left() >= palette.right() and listed.height() >= palette.height() - 2, (palette, listed)
    assert canvas_width > 0
    window.actions["toggle_block_list"].trigger()
    assert window.block_list_dock.isHidden()


def test_block_list_shows_the_page_and_follows_every_change(window, qapp):
    window.block_list_dock.show()
    scene = window.current_scene()
    panel = window.block_list_panel
    a = add(scene, ElementType.START, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    QTest.qWait(250)
    assert panel.element_ids() == [a.element_id, b.element_id]
    assert "2 Bausteine" in panel.summary.text()
    scene.connect_blocks(a, b)
    QTest.qWait(250)
    entry = panel.list.item(0)
    assert entry.text() == "Start „Start“\n   → Vorgang „Vorgang“"        # je Pfeil eine eingerückte Zeile
    assert entry.data(Qt.ItemDataRole.AccessibleTextRole) == "Start „Start“  → Vorgang „Vorgang“"   # vorgelesen
    entry = panel.list.item(1)
    assert entry.data(Qt.ItemDataRole.AccessibleDescriptionRole) == "Baustein 2 von 2"
    scene.undo_stack.undo()   # auch Rückgängig wird gezeigt
    QTest.qWait(250)
    assert panel.list.item(0).data(Qt.ItemDataRole.AccessibleTextRole) == "Start „Start“  kein Pfeil heraus"
    # eine andere Seite: die Liste zeigt deren Bausteine
    document = window.current_document()
    page_count = len(document.pages)
    assert window.new_subprogram("rechnen")
    QTest.qWait(250)
    assert len(document.pages) == page_count + 1
    assert set(panel.element_ids()) == {item.element_id for item in document.scene.elements()
                                        if not item.is_junction}
    assert "rechnen" in panel.summary.text()


def test_enter_selects_and_centers_the_block_and_esc_goes_back(window, qapp):
    window.block_list_dock.show()
    scene = window.current_scene()
    view = window.current_view()
    add(scene, ElementType.START, 0, 0)
    far = add(scene, ElementType.PROCESS, 3000, 2500)
    QTest.qWait(250)
    panel = window.block_list_panel
    panel.list.setCurrentRow(panel.element_ids().index(far.element_id))
    panel.list.setFocus()
    QTest.keyClick(panel.list, Qt.Key.Key_Return)
    assert scene.selectedItems() == [far]
    center = view.mapToScene(view.viewport().rect().center())
    assert abs(center.x() - far.scene_rect().center().x()) < 60
    assert abs(center.y() - far.scene_rect().center().y()) < 60
    # Esc: zurück in den Plan – die Auswahl bleibt
    panel.list.setFocus()
    focused = []
    panel.back_requested.connect(lambda: focused.append(True))
    QTest.keyClick(panel.list, Qt.Key.Key_Escape)
    assert focused and scene.selectedItems() == [far]


def test_double_click_activates_too(qapp):
    panel = BlockListPanel()
    activated = []
    panel.element_activated.connect(activated.append)
    entry = QListWidgetItem("Vorgang")
    entry.setData(block_list.ELEMENT_ID_ROLE, "abc")
    panel.list.addItem(entry)
    panel.list.itemDoubleClicked.emit(entry)
    assert activated == ["abc"]
    panel.deleteLater()


def test_selection_on_the_canvas_moves_the_current_row(window, qapp):
    window.block_list_dock.show()
    scene = window.current_scene()
    a = add(scene, ElementType.START, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    QTest.qWait(250)
    panel = window.block_list_panel
    scene.select_items([b])
    assert panel.list.currentItem().data(block_list.ELEMENT_ID_ROLE) == b.element_id
    scene.select_items([a])
    assert panel.list.currentRow() == 0


def test_tab_from_the_list_leaves_it(window, qapp):
    """Die Liste ist ein normales Bedienelement: Tab führt weiter, sie fängt den Fokus nicht ein."""
    window.block_list_dock.show()
    add(window.current_scene(), ElementType.START, 0, 0)
    QTest.qWait(250)
    panel = window.block_list_panel
    assert panel.list.focusPolicy() & Qt.FocusPolicy.TabFocus
    assert panel.focusProxy() is panel.list
