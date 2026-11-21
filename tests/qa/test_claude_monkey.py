"""QA (Claude): Zufallsbedienung des ganzen Hauptfensters („Monkey-Test“).

Anders als ``tests/test_fuzz_undo.py`` (Szene direkt) geht dieser Test über das Fenster: Menübefehle,
Kontextmenüs, Seitenleiste, Tasten, Mausziehen, Reiter, Unterprogramme, Schreibtischtest, Code-Ansicht und
Dialoge in zufälliger Reihenfolge. Geprüft wird: keine Ausnahme in einem Slot, gültige Szenen, und jedes offene
Projekt übersteht Speichern und Laden unverändert. ``PAP_QA_MONKEY=40`` erhöht die Zahl der Läufe (Standard 6).
"""

from __future__ import annotations

import os
import random

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

import app.main_window as main_window_module
import app.page_bar as page_bar_module
from app.document import DiagramDocument
from app.model.element_types import ElementType
from tests.qa.claude_qa_helpers import (DialogStub, check_scene, close_window, make_window, project_file_hashes,
                                        snapshot_document, trap_errors)


# nie zufällig auslösen: beendet das Programm, geht ins Netz, schreibt in die Registry des Systems
EXCLUDED = {"quit", "check_updates", "check_updates_on_start", "register_filetype"}
KEYS = [Qt.Key.Key_1, Qt.Key.Key_3, Qt.Key.Key_5, Qt.Key.Key_6, Qt.Key.Key_Delete, Qt.Key.Key_Tab,
        Qt.Key.Key_Escape, Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_A,
        Qt.Key.Key_Space, Qt.Key.Key_Backspace]


class CapturingMenu(QMenu):
    """Kontextmenü, das sich nicht öffnet, sondern seine Einträge für den Test bereithält."""

    last = None

    def exec(self, *args, **kwargs):
        CapturingMenu.last = self
        return None


def _leaf_actions(menu):
    found = []
    for action in menu.actions():
        if action.isSeparator() or not action.isEnabled():
            continue
        if action.menu() is not None:
            found.extend(_leaf_actions(action.menu()))
        else:
            found.append(action)
    return found


def _random_point(rng, scene):
    items = scene.elements()
    if items and rng.random() < 0.7:
        rect = rng.choice(items).sceneBoundingRect()
        return QPointF(rect.center().x() + rng.uniform(-20, 20), rect.center().y() + rng.uniform(-20, 20))
    if scene.connections() and rng.random() < 0.5:
        points = rng.choice(scene.connections()).points()
        x, y = points[len(points) // 2]
        return QPointF(x, y)
    return QPointF(rng.randint(-600, 600), rng.randint(-400, 400))


def _step(rng, window, log):
    view = window.current_view()
    if view is None:
        window.new_document()
        log.append("new_document")
        return
    scene = view.document.scene
    roll = rng.random()
    if roll < 0.40:
        names = [n for n, a in window.actions.all().items() if n not in EXCLUDED and a.isEnabled()]
        name = rng.choice(names)
        log.append(f"action {name}")
        window.actions[name].trigger()
    elif roll < 0.55:
        point = _random_point(rng, scene)
        CapturingMenu.last = None
        window.show_context_menu(point, view.mapToGlobal(view.mapFromScene(point)))
        menu = CapturingMenu.last
        leaves = _leaf_actions(menu) if menu is not None else []
        if leaves:
            action = rng.choice(leaves)
            log.append(f"context {action.text()!r} at {point.x():.0f},{point.y():.0f}")
            action.trigger()
    elif roll < 0.62:
        CapturingMenu.last = None
        window.page_bar._on_context_menu(window.page_bar.rect().center())
        leaves = _leaf_actions(CapturingMenu.last) if CapturingMenu.last is not None else []
        if leaves:
            action = rng.choice(leaves)
            log.append(f"pagebar {action.text()!r}")
            action.trigger()
    elif roll < 0.75:
        key = rng.choice(KEYS)
        log.append(f"key {key}")
        view.setFocus()
        QTest.keyClick(view.viewport() if scene.is_editing else view, key)
    elif roll < 0.85:
        start, end = _random_point(rng, scene), _random_point(rng, scene)
        log.append(f"drag {start.x():.0f},{start.y():.0f} -> {end.x():.0f},{end.y():.0f}")
        viewport = view.viewport()
        a, b = view.mapFromScene(start), view.mapFromScene(end)
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
        QTest.mouseMove(viewport, (a + b) / 2)
        QTest.mouseMove(viewport, b)
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    elif roll < 0.90:
        point = _random_point(rng, scene)
        log.append(f"doubleclick {point.x():.0f},{point.y():.0f}")
        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                          view.mapFromScene(point))
        if scene.is_editing and rng.random() < 0.8:
            scene._editor.setPlainText(rng.choice(["x = x + 1", "i < 10", "Ausgabe x", "", "Ä😀\n2. Zeile",
                                                   "solange i < 3", "warte 2 ms"]))
            scene.commit_edit()
    elif roll < 0.95 and window.tabs.count() > 1:
        index = rng.randrange(window.tabs.count())
        log.append(f"tab {index}")
        window.tabs.setCurrentIndex(index)
    else:
        element_type = rng.choice([ElementType.PROCESS, ElementType.DECISION, ElementType.LOOP,
                                   ElementType.SUBPROGRAM, ElementType.INPUT, ElementType.OUTPUT])
        log.append(f"insert {element_type.value}")
        window.insert_element(element_type)
    QApplication.processEvents()


@pytest.mark.parametrize("seed", range(int(os.environ.get("PAP_QA_MONKEY", "6"))))
def test_random_window_use_never_raises_and_files_stay_intact(qapp, monkeypatch, tmp_path, seed):
    rng = random.Random(seed)
    trap = trap_errors(monkeypatch)
    stub = DialogStub(monkeypatch, rng, tmp_path)
    monkeypatch.setattr(main_window_module, "QMenu", CapturingMenu)
    monkeypatch.setattr(page_bar_module, "QMenu", CapturingMenu)
    samples_before = project_file_hashes()
    window = make_window(qapp)
    log: list[str] = []
    try:
        for _ in range(140):
            _step(rng, window, log)
            if trap.errors:
                break
        if window.presenting:
            window.set_presentation(False)
        for view in window.views():
            scene = view.document.scene
            if scene.is_editing:
                scene.commit_edit()
        assert not trap.errors, "Letzte Schritte: " + " | ".join(log[-8:]) + "\n" + trap.report()

        # Jede Seite jedes Projekts ist gültig und übersteht Speichern und Laden
        for number, view in enumerate(window.views()):
            document = view.document
            for scene in document.scenes():
                check_scene(scene)
            path = tmp_path / f"monkey_{seed}_{number}.pap"
            document.save(str(path))
            reopened = DiagramDocument.open_file(str(path))
            assert reopened.load_warnings == [], reopened.load_warnings
            assert snapshot_document(reopened) == snapshot_document(document), " | ".join(log[-8:])
            for scene in reopened.scenes():
                scene.clear_diagram()
            reopened.deleteLater()
        assert not trap.errors, trap.report()
    finally:
        close_window(window, qapp)
    # Auch das Schließen und Abbauen des Fensters darf keinen Fehler auslösen. Ausgenommen: Projekte früherer
    # Testfenster, die erst jetzt abgebaut werden und deren Slot noch auf ihre gelöschte Rückgängig-Liste zugreift
    # (nur mit mehreren Fenstern in einem Prozess beobachtet, siehe QA-BERICHT-CLAUDE.md, Abschnitt Code-Ebene).
    late = [error for error in trap.errors if "QUndoStack) already deleted" not in error]
    assert project_file_hashes() == samples_before, "Der Test hat eine Beispieldatei des Projekts verändert"
    assert not late, "Beim Schließen (Schritte: " + " | ".join(log) + ")\n" + "\n".join(late[:2])
    del stub
