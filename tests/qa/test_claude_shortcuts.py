"""QA (Claude): Jedes Tastenkürzel wird mit einem echten Tastendruck geprüft – nicht nur über ``trigger()``.

Ein Kürzel kann trotz richtiger Belegung wirkungslos sein, wenn zwei aktive Befehle dieselbe Taste haben
(Qt meldet dann „Ambiguous shortcut overload“ und führt keinen von beiden aus).
"""

from __future__ import annotations

import random

import pytest
from PySide6.QtCore import QPointF, Qt, qInstallMessageHandler
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.model.element_types import ElementType
from tests.qa.claude_qa_helpers import DialogStub, close_window, make_window, trap_errors

# Befehle, die das Fenster schließen, das Programm beenden oder auf Ein-/Ausschalter mit eigenem Test liegen
SKIP = {"quit", "close", "presentation", "deselect"}


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    DialogStub(monkeypatch, random.Random(1), tmp_path, accept_rate=0.0)
    created = make_window(qapp)
    created.activateWindow()
    QTest.qWait(50)
    if QApplication.activeWindow() is not created:
        close_window(created, qapp)
        pytest.skip("Das Testfenster wird nicht aktiv – echte Tastendrücke lassen sich hier nicht prüfen")
    yield created
    close_window(created, qapp)


def _press(widget, sequence: QKeySequence) -> None:
    combination = sequence[0]
    QTest.keyClick(widget, combination.key(), combination.keyboardModifiers())
    QTest.qWait(10)


def _prepare(window):
    """Ein Plan mit zwei Bausteinen und einer Auswahl – damit möglichst viele Befehle aktiv sind."""
    scene = window.current_scene()
    a = scene.element(scene.insert_element(ElementType.PROCESS, QPointF(0, -200)))
    b = scene.element(scene.insert_element(ElementType.DECISION, QPointF(0, 0)))
    scene.create_connection(a, "bottom", b, "top")
    scene.select_items([a])
    view = window.current_view()
    view.setFocus()
    QApplication.processEvents()
    return view


def test_every_enabled_shortcut_triggers_its_action(window, monkeypatch):
    trap = trap_errors(monkeypatch)
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    try:
        view = _prepare(window)
        silent = []
        for name, action in window.actions.all().items():
            if name in SKIP or not action.shortcuts():
                continue
            if window.current_view() is None:
                window.new_document()
            view = window.current_view()
            scene = view.document.scene
            if not scene.selected_elements() and scene.elements():
                scene.select_items([scene.elements()[0]])
            if QApplication.activeWindow() is not window:
                # ein (nur ersetzter, nie gezeigter) Dialog kann die Aktivierung wegnehmen – wie nach dem
                # Schließen eines echten Dialogs ist danach wieder das Hauptfenster aktiv
                window.activateWindow()
                QTest.qWait(30)
            view.setFocus()
            QApplication.processEvents()
            if not action.isEnabled():
                continue
            fired = []
            action.triggered.connect(lambda *_args, store=fired: store.append(1))
            _press(view, action.shortcuts()[0])
            if not fired:
                silent.append(f"{name} ({action.shortcuts()[0].toString()})")
            if scene.is_editing:
                scene.cancel_edit()
        assert not silent, f"Tastenkürzel ohne Wirkung: {silent}"
        assert not [m for m in messages if "mbiguous" in m], messages
        assert not trap.errors, trap.report()
    finally:
        qInstallMessageHandler(previous)


def test_escape_ends_presentation_like_the_tooltip_promises(window):
    view = _prepare(window)
    window.current_scene().clearSelection()
    window.set_presentation(True)
    QTest.qWait(50)
    view = window.current_view()
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Escape)
    QTest.qWait(50)
    assert not window.presenting


def test_f11_ends_presentation(window):
    _prepare(window)
    window.set_presentation(True)
    QTest.qWait(50)
    QTest.keyClick(window.current_view(), Qt.Key.Key_F11)
    QTest.qWait(50)
    assert not window.presenting
