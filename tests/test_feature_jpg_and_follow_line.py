"""Datei → Exportieren → Als JPG-Bild und „Zum Anfang/Ziel des Pfeils“ (Kontextmenü, Alt+Pos1 / Alt+Ende)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QKeySequence
from PySide6.QtWidgets import QFileDialog, QLabel, QMenu, QMessageBox

from app import export, styles
from app.actions import sequence_text
from app.connections.follow import line_end
from app.dialogs.export_options import ExportOptionsDialog
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
    win.resize(1000, 700)
    win.show()
    if win.current_document() is None:
        win.new_document()
    qapp.processEvents()
    yield win
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()
    qapp.processEvents()


def _menus(window) -> dict:
    return {menu.title().replace("&", ""): menu for menu in window.menuBar().findChildren(QMenu)}


def _conn(scene, source, target):
    found = [c for c in scene.connections() if c.source is source and c.target is target]
    return found[0] if found else None


def _junctions(scene):
    return [e for e in scene.elements() if e.element_type is ElementType.JUNCTION]


# ================================================================== JPG
def test_jpg_entry_sits_in_the_export_menu_next_to_png(window):
    entries = [a for a in window.export_menu.actions() if not a.isSeparator()]
    names = [window.actions[n] for n in ("export_png", "export_jpg", "export_svg", "export_pdf")]
    assert entries == names
    assert window.actions["export_jpg"].text() == "Als &JPG-Bild …"


def test_jpg_export_is_opaque_on_the_theme_background(document, tmp_path):
    scene = document.scene
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    connect(scene, a, "bottom", b, "top")
    path = tmp_path / "plan.jpg"
    # „Transparent“ aus einem PNG-Export darf beim JPG nichts ausmachen
    export.export_jpg(scene, str(path), export.ExportOptions(transparent=True, scale=2.0))
    image = QImage(str(path))
    assert not image.isNull() and not image.hasAlphaChannel()
    assert bytes(path.read_bytes()[:3]) == b"\xff\xd8\xff"   # echtes JPEG, kein umbenanntes PNG
    corner = QColor(image.pixel(2, 2))
    expected = QColor(styles.LIGHT.canvas_bg)
    assert max(abs(corner.red() - expected.red()), abs(corner.green() - expected.green()),
               abs(corner.blue() - expected.blue())) <= 3
    # Auflösung wie beim PNG: doppelte Größe bei 2×
    png = tmp_path / "plan.png"
    export.export_png(scene, str(png), export.ExportOptions(scale=2.0))
    assert QImage(str(png)).size() == image.size()


def test_jpg_export_with_dark_theme_uses_dark_background(document, tmp_path):
    add(document.scene, ElementType.PROCESS, 0, 0)
    path = tmp_path / "dunkel.jpg"
    export.export_jpg(document.scene, str(path), export.ExportOptions(theme_name="dark", scale=1.0))
    corner = QColor(QImage(str(path)).pixel(1, 1))
    assert corner.lightness() < 60


def test_jpg_options_offer_resolution_but_no_transparency(window):
    dialog = ExportOptionsDialog("JPG", export.ExportOptions(scale=3.0), window)
    assert dialog.scale_combo is not None and dialog.transparent_check is None
    assert dialog.options().scale == 3.0 and dialog.options().transparent is False
    notes = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("keine Transparenz" in text for text in notes)
    dialog.deleteLater()


def test_jpg_export_through_the_menu_keeps_jpeg_name(window, monkeypatch, tmp_path):
    add(window.current_scene(), ElementType.PROCESS, 0, 0)
    monkeypatch.setattr(window, "_export_options", lambda _fmt: export.ExportOptions(scale=1.0))
    asked = []

    def save_name(_parent, title, suggestion, filters):
        asked.append((title, suggestion, filters))
        return str(tmp_path / "Bild.jpeg"), filters

    opened = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", save_name)
    monkeypatch.setattr("PySide6.QtGui.QDesktopServices.openUrl", lambda *args: opened.append(args))
    window.actions["export_jpg"].trigger()
    assert (tmp_path / "Bild.jpeg").exists() and not (tmp_path / "Bild.jpeg.jpg").exists()
    title, suggestion, filters = asked[0]
    assert title == "Als JPG exportieren" and suggestion.endswith(".jpg") and "*.jpg" in filters
    assert not opened   # das Bild wird nicht von selbst geöffnet


def test_jpg_export_asks_before_overwriting_after_adding_suffix(window, monkeypatch, tmp_path):
    add(window.current_scene(), ElementType.PROCESS, 0, 0)
    actual = tmp_path / "Ausgabe.jpg"
    actual.write_bytes(b"alt")
    asked = []
    monkeypatch.setattr(window, "_export_options", lambda _fmt: export.ExportOptions())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(tmp_path / "Ausgabe"), "JPG"))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: asked.append(args) or QMessageBox.StandardButton.No)
    window.actions["export_jpg"].trigger()
    assert asked and actual.read_bytes() == b"alt"
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.actions["export_jpg"].trigger()
    assert actual.read_bytes()[:2] == b"\xff\xd8"


def test_ensure_extension_accepts_alternatives():
    assert export.ensure_extension("a.JPEG", ".jpg", also=(".jpeg",)) == "a.JPEG"
    assert export.ensure_extension("a.jpg", ".jpg", also=(".jpeg",)) == "a.jpg"
    assert export.ensure_extension("a", ".jpg", also=(".jpeg",)) == "a.jpg"
    assert export.ensure_extension("a.png", ".png") == "a.png"


# ================================================================== Pfeil folgen
def test_line_end_returns_direct_blocks(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    line = connect(scene, a, "bottom", b, "top")
    assert line_end(line, forward=True) is b
    assert line_end(line, forward=False) is a


def test_line_end_skips_junction_on_the_trunk(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 150)
    host = connect(scene, a, "bottom", b, "top")
    scene.connect_to_edge(c, "left", host, QPointF(0, 150))
    junction = _junctions(scene)[0]
    branch = _conn(scene, c, junction)
    first, second = _conn(scene, a, junction), _conn(scene, junction, b)
    assert branch is not None and first is not None and second is not None
    # der Abzweig C → ● führt weiter auf dem Stamm bis B
    assert line_end(branch, forward=True) is b
    assert line_end(branch, forward=False) is c
    # vom zweiten Stammteil zurück: auf dem Stamm zu A (nicht zum Abzweig C)
    assert line_end(second, forward=False) is a
    assert line_end(first, forward=True) is b


def test_line_end_chain_of_corner_points(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 400)
    host = connect(scene, a, "bottom", b, "top")
    scene.insert_junction(host, QPointF(0, 130))
    middle = _conn(scene, _junctions(scene)[0], b)
    scene.insert_junction(middle, QPointF(0, 260))
    assert len(_junctions(scene)) == 2
    for line in scene.connections():
        assert line_end(line, forward=True) is b
        assert line_end(line, forward=False) is a


def test_line_end_stops_at_a_loose_end(scene):
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    host = connect(scene, a, "bottom", b, "top")
    junction = scene.element(scene.insert_junction(host, QPointF(0, 150)))
    # zwei Abzweige ohne Stamm: nicht eindeutig → beim Verbindungspunkt bleiben
    junction.data.properties.pop("trunk_out", None)
    c = add(scene, ElementType.PROCESS, 300, 300)
    extra = connect(scene, junction, "right", c, "top")
    assert extra is not None
    assert line_end(_conn(scene, a, junction), forward=True) is junction


def _select_line(window, line):
    window.current_scene().select_items([line])
    window._update_actions()


def test_jump_actions_need_exactly_one_selected_arrow(window):
    scene = window.current_scene()
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 200)
    line = connect(scene, a, "bottom", b, "top")
    jump_source, jump_target = window.actions["jump_to_source"], window.actions["jump_to_target"]
    scene.select_items([a])
    window._update_actions()
    assert not jump_source.isEnabled() and not jump_target.isEnabled()
    _select_line(window, line)
    assert jump_source.isEnabled() and jump_target.isEnabled()
    jump_target.trigger()
    assert scene.selectedItems() == [b]
    _select_line(window, line)
    jump_source.trigger()
    assert scene.selectedItems() == [a]


def test_jump_scrolls_a_far_block_into_view(window, qapp):
    scene = window.current_scene()
    view = window.current_view()
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 3000)
    line = connect(scene, a, "bottom", b, "top")
    view.centerOn(a.scene_rect().center())
    qapp.processEvents()
    assert not view.visible_scene_rect().contains(b.scene_rect())
    _select_line(window, line)
    window.actions["jump_to_target"].trigger()
    qapp.processEvents()
    assert view.visible_scene_rect().contains(b.scene_rect())
    assert scene.selectedItems() == [b]


def test_default_keys_and_menu_place(window):
    jump_source, jump_target = window.actions["jump_to_source"], window.actions["jump_to_target"]
    assert jump_source.shortcuts()[0] == QKeySequence("Alt+Home")
    assert jump_target.shortcuts()[0] == QKeySequence("Alt+End")
    assert jump_target.toolTip().endswith(f"({sequence_text(QKeySequence('Alt+End'))})")
    view_menu = _menus(window)["Ansicht"]
    assert jump_source in view_menu.actions() and jump_target in view_menu.actions()
    assert "jump_to_source" in window.actions.bindable()
    # die F1-Hilfe zeigt die aktuelle Belegung
    dialog = ShortcutsDialog(window, window.actions)
    keys = {dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())}
    assert f"{sequence_text(QKeySequence('Alt+Home'))} / {sequence_text(QKeySequence('Alt+End'))}" in keys
    dialog.deleteLater()


def _context_menu_entries(window, monkeypatch, scene_pos) -> dict:
    from app import main_window as main_window_module

    shown = {}

    class CapturingMenu(QMenu):
        def exec(self, *_args):   # nicht wirklich öffnen, nur die Einträge merken
            shown.update({a.text(): a for a in self.actions() if not a.isSeparator()})

    monkeypatch.setattr(main_window_module, "QMenu", CapturingMenu)
    window.show_context_menu(scene_pos, QPoint(0, 0))
    return shown


def test_arrow_context_menu_jumps_to_both_ends(window, monkeypatch):
    scene = window.current_scene()
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    c = add(scene, ElementType.PROCESS, 300, 150)
    host = connect(scene, a, "bottom", b, "top")
    scene.connect_to_edge(c, "left", host, QPointF(0, 150))
    branch = _conn(scene, c, _junctions(scene)[0])
    points = branch.points()
    middle = QPointF((points[0][0] + points[1][0]) / 2, (points[0][1] + points[1][1]) / 2)
    entries = _context_menu_entries(window, monkeypatch, middle)
    assert "Zum &Anfang des Pfeils" in entries and "Zum Z&iel des Pfeils" in entries
    assert QKeySequence("Alt+End") in entries["Zum Z&iel des Pfeils"].shortcuts()
    entries["Zum Z&iel des Pfeils"].trigger()
    assert scene.selectedItems() == [b]           # über den Verbindungspunkt hinweg zum echten Baustein
    entries = _context_menu_entries(window, monkeypatch, middle)
    entries["Zum &Anfang des Pfeils"].trigger()
    assert scene.selectedItems() == [c]


def test_double_click_on_arrow_still_edits_its_label(window, qapp):
    from PySide6.QtTest import QTest

    scene = window.current_scene()
    view = window.current_view()
    a = add(scene, ElementType.PROCESS, 0, 0)
    b = add(scene, ElementType.PROCESS, 0, 300)
    line = connect(scene, a, "bottom", b, "top")
    view.centerOn(QPointF(0, 150))
    qapp.processEvents()
    points = line.points()
    point = view.mapFromScene(QPointF((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2))
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    qapp.processEvents()
    assert scene.is_editing
    scene.cancel_edit()
