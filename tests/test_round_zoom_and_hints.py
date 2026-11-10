"""Lupe auf runden Werten, Hinweise beim Start zu (mit Zähler), Urheberzeile passt, Raster-Knöpfe."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetricsF

from app import config, splash
from app.canvas import next_zoom_level
from app.diagnostics.panel import count_icon
from app.dialogs.project_properties import ProjectPropertiesDialog
from app.model.element_types import ElementType


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
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


def test_zoom_buttons_land_on_round_values():
    zoom, seen = config.MIN_ZOOM, []
    while True:
        seen.append(round(zoom * 100))
        following = next_zoom_level(zoom, +1)
        if following == zoom:
            break
        zoom = following
    assert seen[0] == 25 and seen[-1] == 400
    assert all(value % 5 == 0 for value in seen)
    assert {100, 110, 200, 225} <= set(seen) and 210 not in seen
    back = []
    while True:
        back.append(round(zoom * 100))
        following = next_zoom_level(zoom, -1)
        if following == zoom:
            break
        zoom = following
    assert back == seen[::-1]


@pytest.mark.parametrize("start, up, down", [(1.15, 120, 110), (1.3225, 140, 130), (0.87, 90, 80),
                                             (2.1, 225, 200), (1.0, 110, 90), (2.0, 225, 190)])
def test_zoom_buttons_snap_from_odd_wheel_values(start, up, down):
    assert round(next_zoom_level(start, +1) * 100) == up
    assert round(next_zoom_level(start, -1) * 100) == down


def test_zoom_actions_use_round_values(window, qapp):
    window.new_document()
    view = window.current_view()
    view.set_zoom(1.15)  # wie nach einer Mausrad-Raste
    window.actions["zoom_in"].trigger()
    assert window.zoom_button.text() == "120 %"
    window.actions["zoom_out"].trigger()
    window.actions["zoom_out"].trigger()
    assert window.zoom_button.text() == "100 %"


def test_hints_start_closed_and_button_shows_count(window, qapp):
    assert window.diagnostics_dock.isHidden()
    window.new_document()
    window.insert_element(ElementType.PROCESS)
    window.diagnostics_panel.refresh()
    total = len(window.diagnostics_panel.issues)
    assert total > 0 and window.diagnostics_dock.isHidden()
    assert window.issues_button.iconSize() == window.issues_button.icon().availableSizes()[0] / 3
    window.issues_button.click()
    qapp.processEvents()
    assert not window.diagnostics_dock.isHidden()


def test_count_icon_differs_with_count(qapp):
    def image(count, warnings):
        return count_icon(count, warnings).pixmap(36, 18).toImage()

    assert image(0, False) != image(3, False)
    assert image(3, False) != image(4, False)
    assert image(3, False) != image(3, True)
    assert not image(250, True).isNull()


def test_hints_panel_can_shrink_to_its_header(window, qapp):
    panel = window.diagnostics_panel
    assert panel.minimumSizeHint().height() < 50   # nur noch die Kopfzeile, keine Mindesthöhe der Liste
    assert panel.sizeHint().height() >= 100         # öffnet trotzdem mit Platz für einige Zeilen


def test_splash_credit_fits(qapp):
    from app.styles import register_bundled_fonts

    register_bundled_fonts()
    font = QFont()
    font.setFamilies(config.ITEM_FONT_FAMILIES)
    width = splash.SPLASH_WIDTH - 2 * splash.CREDIT_MARGIN
    sizes = [size for size in range(splash.CREDIT_FONT_SIZE, splash.CREDIT_MIN_FONT_SIZE - 1, -1)]
    fitting = []
    for size in sizes:
        font.setPixelSize(size)
        if QFontMetricsF(font).horizontalAdvance(config.SPLASH_CREDIT) <= width:
            fitting.append(size)
    assert fitting, "die Urheberzeile passt in keiner erlaubten Größe"
    # rechts neben der Zeile bleibt der Rand schwarz: kein Buchstabe ist abgeschnitten
    image = splash.render_splash(1.0).toImage()
    top = int(splash.LOGO_TOP + splash.LOGO_SIZE) + 22
    for y in range(top, top + 26):
        for x in list(range(0, 8)) + list(range(splash.SPLASH_WIDTH - 8, splash.SPLASH_WIDTH)):
            assert image.pixelColor(x, y).lightness() < 40


def test_grid_size_has_visible_step_buttons(window, qapp):
    window.new_document()
    document = window.current_document()
    dialog = ProjectPropertiesDialog(document.meta, 20, None, window)
    dialog.show()
    qapp.processEvents()
    assert dialog.grid_spin.lineEdit().width() > 60   # die Zahl bleibt sichtbar
    assert dialog.grid_plus.isVisible() and dialog.grid_minus.isVisible()
    dialog.grid_plus.click()
    dialog.grid_plus.click()
    dialog.grid_minus.click()
    assert dialog.result_grid_size() == 25
    dialog.close()
