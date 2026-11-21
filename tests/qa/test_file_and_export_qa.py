"""Datei- und Exportprüfungen für den lokalen QA-Bericht."""

from __future__ import annotations

import os
import random
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QSettings
from PySide6.QtGui import QImage
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox

from app import config, document as document_module, export
from app.autosave import AutosaveManager
from app.commands.edit_text import EditTextCommand
from app.document import DiagramDocument
from app.fileformat.project import ProjectFileError
from app.fileformat.serializer import load_diagram, save_diagram
from app.main_window import MainWindow
from app.model.diagram import Diagram, ElementData
from app.model.element_types import ElementType


ROOT = Path(__file__).resolve().parents[2]
PAP_FIXTURE = ROOT / "tests" / "data" / "papdesigner" / "mittelwert.pap"


def add_process(scene, x=0, y=0, label="Vorgang"):
    element_id = scene.insert_element(ElementType.PROCESS, QPointF(x, y))
    item = scene.element(element_id)
    if item.data.text != label:
        scene.undo_stack.push(EditTextCommand(scene, element_id, item.data.text, label))
    return item


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    from app import settings_store

    monkeypatch.setattr(settings_store, "QSettings",
                        lambda *_: QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    result = MainWindow()
    result.new_document()
    yield result
    result.set_auto_save(False)
    result.close_without_asking.update(view.document for view in result.views())
    result.close()
    result.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize(
    "raw",
    [b"", b"  \r\n\t", b"%PDF-1.7\n", b"PK\x03\x04", b'{"cells":[]}', b"<html/>",
     b"<FRAME><PROJECT>", b"<FRAME><PROJECT><DIAGRAMS/></PROJECT></FRAME>",
     b"<!DOCTYPE FRAME><FRAME><PROJECT/></FRAME>", b"\x00\x01\xff"],
)
def test_rejects_empty_corrupt_foreign_and_non_project_files(tmp_path, raw):
    candidate = tmp_path / "Kaputt.pap"
    candidate.write_bytes(raw)
    with pytest.raises(ProjectFileError) as failure:
        load_diagram(str(candidate))
    assert failure.value.message
    assert candidate.read_bytes() == raw


def test_fuzz_random_and_mutated_pap_files(tmp_path, record_property):
    rng = random.Random(66001)
    seed = PAP_FIXTURE.read_bytes()
    candidate = tmp_path / "Fuzz Kopie.pap"
    corpus = [rng.randbytes(rng.randrange(0, 4097)) for _ in range(300)]
    for _ in range(300):
        mutated = bytearray(seed)
        pos = rng.randrange(len(mutated))
        end = pos + rng.randrange(1, 15)
        mutated[pos:end] = rng.randbytes(rng.randrange(0, 15))
        corpus.append(bytes(mutated))
    accepted = 0
    for raw in corpus:
        candidate.write_bytes(raw)
        try:
            result = load_diagram(str(candidate))
        except ProjectFileError as failure:
            assert failure.message
        else:
            accepted += 1
            for elements, connections in [
                (result.diagram.elements, result.diagram.connections),
                *((page.elements, page.connections) for page in result.diagram.subprograms),
            ]:
                ids = {element.id for element in elements}
                assert len(ids) == len(elements)
                assert all(connection.source_id in ids and connection.target_id in ids
                           for connection in connections)
        assert candidate.read_bytes() == raw
    assert 0 < accepted < 300
    record_property("accepted_inputs", accepted)
    record_property("rejected_inputs", len(corpus) - accepted)


def test_papdesigner_format_fixture_roundtrip(tmp_path):
    imported = load_diagram(str(PAP_FIXTURE))
    assert not imported.native
    assert imported.diagram.meta.name == "Mittelwert"
    assert imported.diagram.connections
    target = tmp_path / "Mittelwert – Neu.pap"
    save_diagram(imported.diagram, str(target))
    reopened = load_diagram(str(target))
    assert reopened.native
    assert reopened.diagram.elements == imported.diagram.elements
    assert reopened.diagram.connections == imported.diagram.connections


def test_unicode_path_and_text_plus_backup_and_undo(document, tmp_path):
    folder = tmp_path / "Größe & Übung"
    folder.mkdir()
    path = folder / "Prüfung 🧪.pap"
    add_process(document.scene, label="äöüß 🧪 <>& ' \"\nZeile 2")
    document.save(str(path))
    first = path.read_bytes()
    add_process(document.scene, 300, 100, "weiter")
    document.save(str(path), backup=True)
    assert not document.is_modified
    assert Path(config.backup_path_for(str(path))).read_bytes() == first
    reopened = DiagramDocument.open_file(str(path))
    assert len(reopened.scene.elements()) == 2
    assert reopened.scene.elements()[0].data.text == "äöüß 🧪 <>& ' \"\nZeile 2"
    document.undo_stack.undo()
    document.undo_stack.undo()
    assert document.is_modified and len(document.scene.elements()) == 1
    document.undo_stack.redo()
    document.undo_stack.redo()
    assert not document.is_modified and len(document.scene.elements()) == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows-Schreibschutzattribut")
def test_read_only_destination_keeps_old_file_and_unsaved_edit(document, tmp_path):
    target = tmp_path / "Nur lesen.pap"
    add_process(document.scene)
    document.save(str(target))
    prior = target.read_bytes()
    add_process(document.scene, 0, 200)
    target.chmod(stat.S_IREAD)
    try:
        with pytest.raises(ProjectFileError, match="Keine Schreibberechtigung"):
            document.save(str(target))
        assert target.read_bytes() == prior
        assert document.is_modified
        assert not list(tmp_path.glob(".pap-*.tmp"))
    finally:
        target.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_crash_recovery_restores_unsaved_and_preserves_original(document, tmp_path):
    target = tmp_path / "Original.pap"
    document.save(str(target))
    before = target.read_bytes()
    crashed = AutosaveManager(str(tmp_path / "crash"))
    recovery = AutosaveManager(str(tmp_path / "crash"), pid_alive_func=lambda _pid: False)
    try:
        crashed.register(document)
        add_process(document.scene, label="Nur in der Sicherung")
        assert crashed.save_now() == 1
        entries = recovery.find_orphans()
        assert len(entries) == 1
        restored = recovery.restore(entries[0])
        assert restored.is_modified and restored.restored_from_backup
        assert restored.scene.elements()[0].data.text == "Nur in der Sicherung"
        assert target.read_bytes() == before
        recovery.adopt(restored, entries[0])
        assert not Path(entries[0].backup_path).exists()
    finally:
        crashed.shutdown()
        recovery.shutdown()


def test_export_png_svg_quality_and_transparency(scene, tmp_path):
    item = add_process(scene, 80, 80, "Prüfung äöü")
    item.setSelected(True)
    png = tmp_path / "Name ü.png"
    svg = tmp_path / "Name ü.svg"
    options = export.ExportOptions(scale=2.0, transparent=True, margin=40, stamp="Name · Klasse · Datum")
    export.export_png(scene, str(png), options)
    export.export_svg(scene, str(svg), options)
    image = QImage(str(png))
    assert not image.isNull()
    assert image.width() >= (item.scene_rect().width() + 80) * options.scale - 1
    assert image.height() >= (item.scene_rect().height() + 80) * options.scale - 1
    assert image.pixelColor(0, 0).alpha() == 0
    assert abs(image.dotsPerMeterX() * 0.0254 - 192) < 1
    root = ET.parse(svg).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert "Prüfung äöü" in "".join(root.itertext())
    assert item.isSelected() and not scene.exporting


def read_pdf(path):
    QtPdf = pytest.importorskip("PySide6.QtPdf")
    pdf = QtPdf.QPdfDocument()
    assert pdf.load(str(path)) == QtPdf.QPdfDocument.Error.None_
    return pdf


def test_export_pdf_and_print_keep_two_distinct_pages(document, tmp_path):
    add_process(document.scene, label="Hauptprogramm")
    page = document.new_page(name="Nebenprogramm")
    document.insert_page(1, page)
    add_process(page.scene, 0, 0, "Teil 1")
    add_process(page.scene, 0, 370, "Teil 2")
    options = export.ExportOptions(stamp="Name · Klasse · Datum")
    output = tmp_path / "Diagrammgröße.pdf"
    export.export_pdf(document.scenes(), str(output), options)
    pdf = read_pdf(output)
    assert pdf.pageCount() == 2
    assert pdf.pagePointSize(1).height() > pdf.pagePointSize(0).height() * 2
    assert "Hauptprogramm" in pdf.getAllText(0).text()
    assert "Teil 2" in pdf.getAllText(1).text()

    printout = tmp_path / "Druck.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(printout))
    export.print_scene(document.scenes(), printer, options)
    printed = read_pdf(printout)
    assert printed.pageCount() == 2
    assert printed.pagePointSize(0) == printed.pagePointSize(1)
    assert "Teil 2" in printed.getAllText(1).text()


def test_print_pdf_large_diagram_keeps_last_of_525_symbols(qapp, tmp_path):
    model = Diagram(elements=[
        ElementData(id=f"process-{index}", type=ElementType.PROCESS, x=(index % 25) * 200,
                    y=(index // 25) * 120, width=140, height=60, text=f"Symbol {index:03d}")
        for index in range(525)
    ])
    document = DiagramDocument(model)
    path = tmp_path / "525 Symbole.pdf"
    export.export_pdf(document.scenes(), str(path), export.ExportOptions())
    pdf = read_pdf(path)
    assert pdf.pageCount() == 1
    visible_text = pdf.getAllText(0).text()
    assert "Symbol 000" in visible_text
    assert "Symbol 524" in visible_text
    assert visible_text.count("Symbol") == 525


@pytest.mark.parametrize("format_name", ["PNG", "SVG", "PDF"])
def test_export_does_not_overwrite_after_adding_suffix(window, monkeypatch, tmp_path, format_name):
    add_process(window.current_scene())
    chosen = tmp_path / "Ausgabe.dat"
    actual = tmp_path / f"Ausgabe.dat.{format_name.lower()}"
    old = b"bereits vorhandene Datei"
    actual.write_bytes(old)
    monkeypatch.setattr(window, "_export_options", lambda _format: export.ExportOptions())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(chosen), format_name))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    window.actions[f"export_{format_name.lower()}"].trigger()
    assert actual.read_bytes() == old


def test_autosave_does_not_recreate_an_externally_deleted_file(window, tmp_path):
    window.set_auto_save(True)
    document = window.current_document()
    target = tmp_path / "Extern gelöscht.pap"
    add_process(document.scene)
    assert window._save_to(document, str(target))
    target.unlink()
    add_process(document.scene, 0, 200)
    window._run_auto_save()
    assert not target.exists()
    assert document.is_modified


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Dateistempel gehört nicht zum gelesenen Inhalt")
def test_external_replacement_during_open_is_detected(document, monkeypatch, tmp_path):
    target = tmp_path / "Zeitgleich geändert.pap"
    add_process(document.scene, label="Stand beim Öffnen")
    document.save(str(target))
    replacement = document.to_diagram()
    replacement.elements[0].text = "Extern durch eine neuere Version ersetzt"
    incoming = tmp_path / "Fremde Version.pap"
    save_diagram(replacement, str(incoming))

    def read_then_replace(path):
        loaded = load_diagram(path)
        os.replace(incoming, path)
        return loaded

    monkeypatch.setattr(document_module, "load_diagram", read_then_replace)
    opened = DiagramDocument.open_file(str(target))
    assert opened.scene.elements()[0].data.text == "Stand beim Öffnen"
    assert load_diagram(str(target)).diagram.elements[0].text == "Extern durch eine neuere Version ersetzt"
    assert opened.changed_on_disk()


def test_closing_saved_tab_does_not_access_destroyed_undo_stack(window, monkeypatch, tmp_path):
    window.set_auto_save(True)
    document = window.current_document()
    add_process(document.scene)
    assert window._save_to(document, str(tmp_path / "Tab.pap"))
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda _type, value, _trace: errors.append(str(value)))
    assert window.close_tab(window.tabs.currentIndex())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not errors


def test_empty_native_project_keeps_its_valid_structure(tmp_path):
    path = tmp_path / "Leer aber gültig.pap"
    save_diagram(Diagram(), str(path))
    result = load_diagram(str(path))
    assert result.native and not result.warnings and not result.diagram.elements


def test_native_file_missing_diagrams_structure_is_reported(document, tmp_path):
    path = tmp_path / "Beschädigter Container.pap"
    add_process(document.scene)
    document.save(str(path))
    payload = path.read_bytes()
    damaged = payload.replace(b"<DIAGRAMS", b"<DIAGRMAS").replace(b"</DIAGRAMS>", b"</DIAGRMAS>")
    assert damaged != payload
    path.write_bytes(damaged)
    try:
        result = load_diagram(str(path))
    except ProjectFileError:
        return
    assert result.warnings


def _pdf_text_bounds(pdf, page, value):
    text = pdf.getAllText(page).text()
    start = text.index(value)
    return pdf.getSelectionAtIndex(page, start, len(value)).boundingRectangle()


def test_print_stamp_and_diagram_use_the_same_alignment(document, tmp_path):
    add_process(document.scene, label="Hauptprogramm")
    add_process(document.scene, 0, 800, "Zweiter Baustein")
    page = document.new_page(name="Nebenprogramm")
    document.insert_page(1, page)
    add_process(page.scene, label="Breite Zeichenfolge für den A4-Ausdruck")
    options = export.ExportOptions(stamp="Name · Klasse · Datum")
    expected_path = tmp_path / "Diagrammgröße.pdf"
    export.export_pdf(document.scenes(), str(expected_path), options)
    expected = read_pdf(expected_path)

    printout = tmp_path / "Druck.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(printout))
    export.print_scene(document.scenes(), printer, options)
    actual = read_pdf(printout)

    def gap_in_line_heights(pdf):
        symbol = _pdf_text_bounds(pdf, 1, "Breite Zeichenfolge")
        stamp = _pdf_text_bounds(pdf, 1, "Name")
        return (stamp.top() - symbol.bottom()) / symbol.height()

    assert gap_in_line_heights(actual) == pytest.approx(gap_in_line_heights(expected), abs=1)


def test_print_honors_selected_page_range(document, tmp_path):
    add_process(document.scene, label="Diese Seite bleibt draußen")
    page = document.new_page(name="Nebenprogramm")
    document.insert_page(1, page)
    add_process(page.scene, label="Nur diese Seite drucken")
    printout = tmp_path / "Eine Druckseite.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(printout))
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    printer.setFromTo(2, 2)
    dialog = QPrintDialog(printer)
    assert dialog.options() & QPrintDialog.PrintDialogOption.PrintPageRange
    export.print_scene(document.scenes(), printer, export.ExportOptions())
    printed = read_pdf(printout)
    assert printed.pageCount() == 1
    assert "Nur diese Seite" in printed.getAllText(0).text()


@pytest.mark.parametrize("output_type", ["struktogramm", "code", "variablen", "ausgaben"])
def test_other_save_dialogs_do_not_overwrite_after_adding_suffix(window, monkeypatch, tmp_path, output_type):
    from app.codegen.dialog import CodeDialog
    from app.nsd.dialog import StructogramDialog, export_filters

    assert window.open_file(str(PAP_FIXTURE))
    document = window.current_document()
    chosen = tmp_path / "Ausgabe.dat"
    old = b"bereits vorhandene Datei"
    if output_type == "struktogramm":
        dialog = StructogramDialog(document)
        save, suffix, chosen_filter = dialog.export, ".png", export_filters()["PNG"]
    elif output_type == "code":
        dialog = CodeDialog(document, language="python")
        save, suffix, chosen_filter = dialog.save_code, ".py", "Python-Datei (*.py)"
    else:
        panel = window.simulation_panel
        tab = panel.variables_table if output_type == "variablen" else panel.outputs
        panel.tabs.setCurrentWidget(tab)
        save = panel.save_current
        suffix, chosen_filter = {
            "variablen": (".csv", "CSV-Datei (*.csv)"),
            "ausgaben": (".txt", "Textdatei (*.txt)"),
        }[output_type]
    actual = chosen.with_name(chosen.name + suffix)
    actual.write_bytes(old)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(chosen), chosen_filter))
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    save()
    assert actual.read_bytes() == old


def test_closing_unsaved_project_can_be_cancelled(window, monkeypatch):
    document = window.current_document()
    add_process(document.scene)
    dialogs = []

    def press_escape(box):
        dialogs.append(box.text())
        box.escapeButton().click()
        return QMessageBox.DialogCode.Rejected

    monkeypatch.setattr(QMessageBox, "exec", press_escape)
    assert not window.close_tab(window.tabs.currentIndex())
    assert window.current_document() is document and document.is_modified
    assert dialogs and "wurde geändert" in dialogs[0]
