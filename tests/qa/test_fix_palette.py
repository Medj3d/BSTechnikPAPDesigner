"""Paletteneinträge: Tastaturbedienung, Fokusrahmen und Bildschirmleser (Codex QA-24)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QColor
from PySide6.QtTest import QTest

from app import styles
from app.model.element_types import ElementType
from app.palette import PaletteEntry, ToolPalette


def _palette(qapp):
    palette = ToolPalette()
    palette.resize(240, 700)
    palette.show()
    qapp.processEvents()
    return palette


def test_entries_reachable_by_tab(qapp):
    palette = _palette(qapp)
    first, second = palette.entries[0], palette.entries[1]
    assert first.focusPolicy() & Qt.FocusPolicy.TabFocus
    first.setFocus()
    qapp.processEvents()
    assert first.hasFocus() or not palette.isActiveWindow()
    palette.close()


def test_space_and_enter_insert_like_click(qapp):
    palette = _palette(qapp)
    entry = palette.entries[0]
    seen = []
    palette.element_activated.connect(seen.append)
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
        QTest.keyClick(entry, key)
    assert seen == [entry.element_type] * 3
    QTest.mouseClick(entry, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    assert len(seen) == 4
    palette.close()


def test_disabled_entry_does_not_activate(qapp):
    entry = PaletteEntry(ElementType.PROCESS)
    seen = []
    entry.activated.connect(seen.append)
    entry.setEnabled(False)
    entry.activate()
    assert seen == []


def test_accessible_button_with_press_action(qapp):
    palette = _palette(qapp)
    entry = palette.entries[0]
    seen = []
    palette.element_activated.connect(seen.append)
    accessible = QAccessible.queryAccessibleInterface(entry)
    assert accessible.role() == QAccessible.Role.Button
    assert accessible.text(QAccessible.Text.Name) == entry.label
    assert accessible.state().focusable
    actions = accessible.actionInterface()
    assert QAccessibleActionInterface.pressAction() in actions.actionNames()
    actions.doAction(QAccessibleActionInterface.pressAction())
    assert seen == [entry.element_type]
    palette.close()


def test_focus_ring_visible(qapp):
    entry = PaletteEntry(ElementType.PROCESS)
    entry.resize(220, 44)
    accent = QColor(styles.current_theme().accent).rgb()

    def accent_pixels():
        image = entry.grab().toImage()
        return sum(image.pixel(x, y) == accent for y in range(image.height()) for x in range(image.width()))

    before = accent_pixels()
    entry.hasFocus = lambda: True   # Fokus ohne aktives Fenster nachstellen
    assert accent_pixels() > before
