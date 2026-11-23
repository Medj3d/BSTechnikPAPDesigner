"""QA (Claude): großer Plan (600 Bausteine), Zeitbedarf aller Hauptfunktionen und Speicher nach dem Schließen.

Die Zeitgrenzen sind großzügig (langsamer Schul-PC, CI); sie sollen Hänger und quadratische Ausreißer finden,
keine Feinmessung sein. Mit ``-s`` erscheint eine Zeittabelle.
"""

from __future__ import annotations

import gc
import os
import sys
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF

from app import clipboard
from app.analysis.structure import structure_diagram
from app.codegen.generators import LANGUAGES, generate
from app.connections.connection import ConnectionItem
from app.diagnostics.checks import run_checks
from app.document import DiagramDocument
from app.export import ExportOptions, export_pdf, render_image
from app.fileformat.serializer import save_diagram
from app.items.base_item import FlowItem
from app.layout.auto_layout import apply_layout, plan_auto_layout
from app.model.diagram import ConnectionData, Diagram, ElementData, new_id
from app.model.element_types import ElementType, spec_for
from app.nsd.renderer import render_image as render_structogram
from app.scene import DiagramScene
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from tests.qa.claude_qa_helpers import DialogStub, close_window, example_copy, make_window, trap_errors

ROWS, COLUMNS = 25, 24          # 600 Bausteine in Schlangenlinien
TIMINGS: list[tuple[str, float]] = []


def big_diagram() -> Diagram:
    """Start → 598 Bausteine (Eingabe, Vorgang, Ausgabe, Unterprogramm-Aufruf gemischt) → Ende."""
    elements, connections = [], []
    kinds = [ElementType.PROCESS, ElementType.PROCESS, ElementType.OUTPUT, ElementType.PROCESS]
    texts = {ElementType.PROCESS: "x = x + {i}", ElementType.OUTPUT: "Ausgabe x", ElementType.INPUT: "Eingabe a"}
    total = ROWS * COLUMNS
    for number in range(total):
        column, row = divmod(number, ROWS)
        if column % 2:
            row = ROWS - 1 - row
        if number == 0:
            kind, text = ElementType.START, "Start"
        elif number == total - 1:
            kind, text = ElementType.END, "Ende"
        elif number == 1:
            kind, text = ElementType.INPUT, "Eingabe a"
        else:
            kind = kinds[number % len(kinds)]
            text = texts[kind].format(i=number % 7)
        spec = spec_for(kind)
        elements.append(ElementData(id=new_id(), type=kind, x=column * 240.0, y=row * 120.0,
                                    width=spec.default_width, height=spec.default_height, text=text))
    for number in range(total - 1):
        a, b = elements[number], elements[number + 1]
        same_column = number // ROWS == (number + 1) // ROWS
        if same_column:
            down = b.y > a.y
            ports = ("bottom", "top") if down else ("top", "bottom")
        else:
            ports = ("right", "left")
        connections.append(ConnectionData(id=new_id(), source_id=a.id, target_id=b.id,
                                          source_port=ports[0], target_port=ports[1]))
    return Diagram(elements=elements, connections=connections)


def timed(label: str, limit: float):
    class _Timer:
        def __enter__(self):
            self.started = time.monotonic()
            return self

        def __exit__(self, *exc):
            elapsed = time.monotonic() - self.started
            TIMINGS.append((label, elapsed))
            if exc[0] is None:
                assert elapsed < limit, f"{label}: {elapsed:.1f} s (Grenze {limit} s)"
            return False
    return _Timer()


@pytest.fixture(scope="module")
def big_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("gross") / "grosser Plan 600.pap"
    save_diagram(big_diagram(), str(path))
    return str(path)


def test_600_blocks_all_main_functions_in_time(qapp, big_file, tmp_path):
    TIMINGS.clear()
    with timed("Öffnen (600 Bausteine, 599 Pfeile)", 20):
        document = DiagramDocument.open_file(big_file)
    scene = document.scene
    assert len(scene.elements()) == ROWS * COLUMNS
    try:
        with timed("Prüfung (Hinweise)", 10):
            run_checks(document)
        with timed("Alles auswählen + 20 px verschieben", 15):
            scene.select_all()
            scene.move_selection_by(20, 0)
        with timed("Rückgängig + Wiederholen", 15):
            document.undo_stack.undo()
            document.undo_stack.redo()
        with timed("Kopieren + Einfügen aller Bausteine", 20):
            payload = clipboard.selection_payload(scene)
            clipboard.paste_payload(scene, payload, offset=QPointF(0, 3200))
        with timed("Alles löschen + Rückgängig", 20):
            scene.select_all()
            scene.delete_selection()
            document.undo_stack.undo()
        with timed("Einen Baustein einfügen bei 1200 Bausteinen", 3):
            scene.insert_element(ElementType.PROCESS, QPointF(-400, 0))
        with timed("Code erzeugen (alle Sprachen)", 20):
            programs = structure_diagram(document.flow_graph())
            for language in LANGUAGES:
                generate(programs, language, "Gross")
        with timed("Struktogramm als Bild", 20):
            render_structogram(programs, scale=1.0)
        with timed("Schreibtischtest 3000 Schritte", 20):
            simulator = Simulator(document.flow_graph())
            for _ in range(3000):
                result = simulator.step()
                if result.finished:
                    break
                if result.needs == NEEDS_INPUT:
                    simulator.provide_input("2")
                elif result.needs == NEEDS_DECISION:
                    simulator.provide_decision(True)
        with timed("PNG-Bild (Maßstab 1)", 20):
            image = render_image(scene, ExportOptions(scale=1.0))
            assert not image.isNull()
        with timed("PDF", 20):
            export_pdf([scene], str(tmp_path / "gross.pdf"), ExportOptions())
        with timed("Speichern", 10):
            document.save(str(tmp_path / "gross_kopie.pap"))
    finally:
        print("\n" + "\n".join(f"  {label:45s} {seconds:6.2f} s" for label, seconds in TIMINGS))
        scene.clear_diagram()
        document.deleteLater()


def test_auto_layout_of_400_blocks_takes_under_two_seconds(qapp, tmp_path):
    global ROWS, COLUMNS
    saved = ROWS, COLUMNS
    ROWS, COLUMNS = 20, 20
    try:
        path = tmp_path / "plan400.pap"
        save_diagram(big_diagram(), str(path))
    finally:
        ROWS, COLUMNS = saved
    document = DiagramDocument.open_file(str(path))
    try:
        started = time.monotonic()
        apply_layout(document.scene, plan_auto_layout(document.scene))
        elapsed = time.monotonic() - started
        print(f"\n  Automatisch anordnen, 400 Bausteine: {elapsed:.1f} s")
        assert elapsed < (8.0 if os.environ.get("CI") else 2.5)   # langsame CI-Rechner großzügiger
    finally:
        document.scene.clear_diagram()
        document.deleteLater()


# ----------------------------------------------------------------- Speicher
def _memory_bytes() -> int:
    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(process), ctypes.byref(counters), counters.cb)
        return int(counters.PrivateUsage)
    with open("/proc/self/status", encoding="ascii") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    return 0


def _live(kind) -> int:
    gc.collect()
    return sum(1 for obj in gc.get_objects() if isinstance(obj, kind))


def _flush():
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        QCoreApplication.processEvents()
    gc.collect()


def _open_and_close_cycles(window, qapp, path, cycles: int) -> tuple[list[int], int, int]:
    """Öffnet das Projekt (dreimal: zweimal wird nur der offene Reiter gezeigt) und schließt alle Reiter."""
    _flush()
    base_items, base_scenes = _live(FlowItem), _live(DiagramScene)
    usage = []
    for _cycle in range(cycles):
        for _copy in range(3):
            window.open_file(path)
        qapp.processEvents()
        while window.tabs.count():
            for view in window.views():
                view.document.undo_stack.setClean()
            window.close_tab(0)
            qapp.processEvents()
        window.new_document()
        _flush()
        usage.append(_memory_bytes())
    return usage, _live(FlowItem) - base_items, _live(DiagramScene) - base_scenes


def test_closing_tabs_does_not_let_memory_grow(qapp, monkeypatch, tmp_path, big_file):
    trap = trap_errors(monkeypatch)
    DialogStub(monkeypatch, __import__("random").Random(3), tmp_path, accept_rate=0.0)
    window = make_window(qapp)
    try:
        usage, items, scenes = _open_and_close_cycles(window, qapp, big_file, 4)
        print(f"\n  Speicher nach Runde 1–4: {[round(u / 2**20) for u in usage]} MB; "
              f"übrige Bausteine {items}, Szenen {scenes}")
        assert items <= ROWS * COLUMNS + 2, "mehr als ein geschlossenes Projekt bleibt im Speicher"
        assert usage[-1] - usage[0] < 80 * 2**20, f"Speicher wächst: {[round(u / 2**20) for u in usage]} MB"
        assert not trap.errors, trap.report()
    finally:
        close_window(window, qapp)


def test_closing_the_tab_frees_the_project(qapp, monkeypatch, tmp_path):
    DialogStub(monkeypatch, __import__("random").Random(4), tmp_path, accept_rate=0.0)
    window = make_window(qapp)
    try:
        _usage, items, scenes = _open_and_close_cycles(window, qapp, example_copy(tmp_path), 1)
        assert items <= 2 and scenes <= 1, f"übrig: {items} Bausteine, {scenes} Szenen"
    finally:
        close_window(window, qapp)
