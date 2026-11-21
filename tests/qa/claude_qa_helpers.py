"""Hilfsmittel für die QA-Tests von Claude (QA-BERICHT-CLAUDE.md).

* ``ErrorTrap`` fängt jede Ausnahme, die Qt in einem Slot oder einer überschriebenen Methode „verschluckt“
  (PySide gibt sie sonst nur auf der Konsole aus) – so fällt jeder Absturz einer Bedienung auf.
* ``DialogStub`` ersetzt alle modalen Dialoge: Nichts erscheint auf dem Bildschirm, nichts wird gedruckt, die
  Antworten sind zufällig, aber sicher (kein Neustart, kein Update, keine Registrierung).
* ``snapshot_document`` beschreibt alle Seiten eines Projekts für Vergleiche nach Speichern/Laden.
"""

from __future__ import annotations

import os
import re
import sys
import traceback

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from app import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")

# Knöpfe, die nie gedrückt werden dürfen (würden das Programm neu starten oder etwas installieren)
_UNSAFE_BUTTON = re.compile(r"neu starten|neustart|install|herunterladen|update", re.IGNORECASE)

# Einstellungen, die ein Test im Test-Registry-Schlüssel verändern kann
SETTINGS_GROUPS = ("auto_save", "backup_on_save", "language", "last_directory", "project", "recent_files",
                   "shortcuts", "updates", "view", "window", "export", "preferences", "ui")

# Beispieldateien des Projekts: Tests dürfen sie öffnen (als Kopie!), aber nie verändern
PROJECT_SAMPLES = ("examples", os.path.join("assets", "examples"), os.path.join("tests", "data"))


def project_file_hashes() -> dict:
    """Prüfsummen aller Beispieldateien des Projekts – vorher/nachher vergleichen."""
    import hashlib

    hashes = {}
    for folder in PROJECT_SAMPLES:
        for current, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                path = os.path.join(current, name)
                with open(path, "rb") as handle:
                    hashes[os.path.relpath(path, ROOT)] = hashlib.sha256(handle.read()).hexdigest()
    return hashes


def example_copy(folder) -> str:
    """Kopie des Beispiels im Testordner – Speichern im Test trifft so nie die Datei im Projekt."""
    import shutil

    target = os.path.join(str(folder), "Beispiel_Mittelwert_Kopie.pap")
    if not os.path.exists(target):
        shutil.copyfile(EXAMPLE, target)
    return target


class ErrorTrap:
    def __init__(self):
        self.errors: list[str] = []

    def hook(self, exc_type, exc, tb) -> None:
        self.errors.append("".join(traceback.format_exception(exc_type, exc, tb)))

    def unraisable(self, info) -> None:
        self.errors.append(f"unraisable {info.exc_type.__name__}: {info.exc_value!r} in {info.object!r}")

    def report(self) -> str:
        return "\n\n".join(self.errors[:3])


def trap_errors(monkeypatch) -> ErrorTrap:
    trap = ErrorTrap()
    monkeypatch.setattr(sys, "excepthook", trap.hook)
    monkeypatch.setattr(sys, "unraisablehook", trap.unraisable)
    return trap


class DialogStub:
    """Beantwortet alle Dialoge selbst. ``log`` hält fest, was gefragt wurde."""

    def __init__(self, monkeypatch, rng, folder, accept_rate: float = 0.5, open_files=None):
        self.rng = rng
        self.folder = str(folder)
        self.accept_rate = accept_rate
        # „Öffnen“ liefert eine Kopie des Beispiels – nie die Datei im Projekt (Strg+S würde sie überschreiben)
        self.open_files = list(open_files) if open_files is not None else [example_copy(folder)]
        self.log: list[tuple] = []
        self.counter = 0
        mp = monkeypatch
        # Funktionen (keine gebundenen Methoden), damit ``box.exec()`` das Dialogobjekt übergibt
        mp.setattr(QMessageBox, "exec", lambda box, *args: self._box_exec(box))
        for name in ("question", "warning", "information", "critical"):
            mp.setattr(QMessageBox, name, self._box_static(name))
        mp.setattr(QDialog, "exec", lambda dialog, *args: self._dialog_exec(dialog))
        mp.setattr(QFileDialog, "getSaveFileName", self._save_name)
        mp.setattr(QFileDialog, "getOpenFileName", self._open_name)
        mp.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
        mp.setattr(QInputDialog, "getText", self._get_text)
        from PySide6.QtPrintSupport import QPageSetupDialog, QPrintDialog, QPrintPreviewDialog

        # Drucken nie wirklich ausführen
        mp.setattr(QPrintDialog, "exec", lambda dialog: self._log("print_dialog") or 0)
        mp.setattr(QPrintPreviewDialog, "exec", lambda dialog: self._log("print_preview") or 0)
        mp.setattr(QPageSetupDialog, "exec", lambda dialog: self._log("page_setup") or 0)

    def _log(self, *entry) -> None:
        self.log.append(entry)

    # ------------------------------------------------------------ Meldungen
    def _box_exec(self, box) -> int:
        self._log("box", box.icon(), box.text())
        buttons = [b for b in box.buttons() if not _UNSAFE_BUTTON.search(b.text())]
        if not buttons:
            return 0
        button = self.rng.choice(buttons)
        button.click()
        standard = box.standardButton(button)
        return int(standard.value) if standard != QMessageBox.StandardButton.NoButton else box.buttons().index(button)

    def _box_static(self, name):
        def call(parent, title, text, *args, **kwargs):
            self._log("static_box", name, text)
            if name == "question":
                return self.rng.choice([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No,
                                        QMessageBox.StandardButton.Cancel])
            return QMessageBox.StandardButton.Ok
        return call

    # ------------------------------------------------------------ eigene Dialoge
    def _dialog_exec(self, dialog) -> int:
        self._log("dialog", type(dialog).__name__)
        if self.rng.random() < self.accept_rate:
            dialog.accept()
        else:
            dialog.reject()
        return dialog.result()

    # ------------------------------------------------------------ Dateien
    def _save_name(self, parent=None, caption="", directory="", file_filter="", *args, **kwargs):
        self.counter += 1
        extension = os.path.splitext(str(directory))[1] or ".pap"
        if self.rng.random() < 0.15:
            self._log("save_cancel", extension)
            return "", ""
        name = self.rng.choice(["Plan", "Übung Nr 1", "a b c ä ö ü", "test😀"]) + f" {self.counter}{extension}"
        self._log("save", name)
        return os.path.join(self.folder, name), file_filter

    def _open_name(self, *args, **kwargs):
        if self.open_files and self.rng.random() < 0.5:
            path = self.rng.choice(self.open_files)
            self._log("open", path)
            return path, ""
        self._log("open_cancel")
        return "", ""

    def _get_text(self, parent=None, title="", label="", *args, **kwargs):
        text = self.rng.choice(["Unterprogramm A", "berechne", "x", "", "Ä ö ü ß", "Teil 2"])
        ok = self.rng.random() < 0.7
        self._log("get_text", title, text, ok)
        return text, ok


def check_scene(scene) -> None:
    """Wie ``tests.test_fuzz_undo.check_invariants``, aber die erwarteten Warnungen folgen den Schaltern
    (erweiterte Prüfung, lose Pfeilenden), die ein Zufallstest umlegen kann."""
    import pytest

    from app import preferences
    from app.analysis.graph import FlowGraph
    from app.connections.connection import ConnectionItem
    from app.i18n import tr
    from app.items.base_item import FlowItem
    from app.model import rules

    items = [it for it in scene.items() if isinstance(it, FlowItem)]
    conns = [it for it in scene.items() if isinstance(it, ConnectionItem)]
    assert {it.element_id for it in items} == set(scene._elements)
    assert {c.connection_id for c in conns} == set(scene._connections)
    for item in items:
        assert (item.data.x, item.data.y) == (item.pos().x(), item.pos().y())
        assert (item.data.width, item.data.height) == (item.width, item.height)
        for conn in item.connections:
            assert conn.scene() is scene
    for conn in conns:
        assert conn.source.scene() is scene and conn.target.scene() is scene
        assert conn in conn.source.connections and conn in conn.target.connections
        points = conn.points()
        s = conn.source.port_scene_pos(conn.data.source_port)
        t = conn.target.port_scene_pos(conn.data.target_port)
        assert points[0] == pytest.approx((s.x(), s.y()))
        assert points[-1] == pytest.approx((t.x(), t.y()))
    ordered = scene.ordered_connections()
    findings = rules.evaluate_connections([scene._connection_info(c) for c in ordered])
    if preferences.enabled(preferences.EXTENDED_CHECKS):
        for connection_id, finding in rules.extended_findings(FlowGraph.from_scene(scene)).items():
            findings.setdefault(connection_id, finding)
    expected = {}
    for conn in ordered:
        if conn.has_loose_end:
            expected[conn.connection_id] = tr("Dieser Pfeil ist noch nicht angeschlossen.")
        elif conn.connection_id in findings:
            expected[conn.connection_id] = findings[conn.connection_id].message
    actual = scene.connection_warnings()
    assert actual == expected, f"Szene: {sorted(actual.values())} erwartet: {sorted(expected.values())}"


def snapshot_scene(scene):
    from tests.test_fuzz_undo import snapshot

    return snapshot(scene)


def snapshot_document(document) -> list:
    return [(page.display_name, snapshot_scene(scene)) for page, scene in zip(document.pages, document.scenes())]


def clear_test_settings() -> None:
    settings = QSettings(config.ORGANIZATION_NAME, config.SETTINGS_APP_NAME)
    for group in SETTINGS_GROUPS:
        settings.remove(group)
    settings.sync()


def make_window(qapp):
    from app.main_window import MainWindow

    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()
    if window.current_view() is None:
        window.new_document()
    qapp.processEvents()
    return window


def close_window(window, qapp) -> None:
    from app import theme

    if window.presenting() if callable(getattr(window, "presenting", None)) else False:
        window.set_presentation(False)
    from PySide6.QtCore import QCoreApplication, QEvent

    for view in window.views():
        view.document.undo_stack.setClean()
    window.close()
    qapp.processEvents()
    # Fenster und Projekte wirklich abbauen (wie am Programmende), solange der Fehlerfang noch aktiv ist
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    # wieder das Standard-Farbschema (andere Tests gehen davon aus)
    theme.apply_ui_theme(qapp, theme.DEFAULT_THEME)
    clear_test_settings()
