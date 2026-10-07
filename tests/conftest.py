"""Gemeinsame Test-Hilfsmittel.

Unter Windows wird die native Plattform verwendet (echte Schriftmetriken),
Fenster werden jedoch nicht auf dem Bildschirm angezeigt. Auf Systemen ohne
Anzeige wird automatisch die ``offscreen``-Plattform genutzt.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if not sys.platform.startswith("win") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import config  # noqa: E402

# Tests dürfen die echten Programmeinstellungen (Fensterlayout, Farbschema,
# zuletzt geöffnete Dateien) nicht verändern.
config.SETTINGS_APP_NAME = "PAPDesignerTests"
# Tests öffnen auch Dateien des Projekts (Beispiel, Testdaten); nichts davon
# darf von selbst überschrieben werden. Tests zum automatischen Speichern
# schalten es gezielt ein.
config.AUTO_SAVE_DEFAULT = False


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch):
    """Kein Test darf einen echten Dialog auf dem Bildschirm öffnen.

    Wer einen Dialog erwartet, ersetzt ihn im Test selbst (monkeypatch); alles
    andere schlägt hier sofort fehl, statt auf eine Eingabe zu warten.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    def blocked(name):
        def call(*_args, **_kwargs):
            raise AssertionError(f"Ein Test wollte den Dialog {name} wirklich öffnen – bitte im Test ersetzen.")
        return call

    for name in ("exec", "question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, blocked(f"QMessageBox.{name}"))
    for name in ("getOpenFileName", "getSaveFileName", "getExistingDirectory"):
        monkeypatch.setattr(QFileDialog, name, blocked(f"QFileDialog.{name}"))
    yield


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    from app import styles
    styles.apply_application_style(app)
    yield app


@pytest.fixture
def document(qapp):
    from app.document import DiagramDocument
    doc = DiagramDocument()
    yield doc
    doc.scene.clear_diagram()
    doc.deleteLater()


@pytest.fixture
def scene(document):
    return document.scene


@pytest.fixture
def view(document, qapp):
    """Eine sichtbare (aber nicht auf dem Bildschirm dargestellte) Ansicht."""
    from app.canvas import DiagramView
    v = DiagramView(document)
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.resize(1000, 700)
    v.show()
    qapp.processEvents()
    v.centerOn(QPointF(0, 0))
    qapp.processEvents()
    yield v
    v.close()
    v.deleteLater()


def add(scene, element_type, x, y):
    """Fügt einen Baustein per Befehl ein und liefert das Item."""
    from app.model.element_types import ElementType
    element_id = scene.insert_element(ElementType(element_type), QPointF(x, y))
    return scene.element(element_id)


def connect(scene, source, source_port, target, target_port):
    connection_id = scene.create_connection(source, source_port, target, target_port)
    return scene.connection(connection_id) if connection_id else None
