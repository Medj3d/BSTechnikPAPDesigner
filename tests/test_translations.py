"""Die mitgelieferten Übersetzungen: vollständig, formal fehlerfrei und ohne Einfluss auf das Verhalten.

Geprüft wird jede Sprache aus ``assets/translations``: Vollständigkeit und Form (Platzhalter, Tastenkürzel,
Zeilenumbrüche), das Wiedererkennen gespeicherter Texte über Sprachgrenzen hinweg, Schreibtischtest und
Code-Erzeugung sowie der Aufbau von Hauptfenster und Dialogen.
"""

import json
import os
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton, QDockWidget, QLabel, QLineEdit, QMenu, QTabWidget, QWidget

from app import config, i18n, labels
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.document import DiagramDocument
from app.model.element_types import (LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, ElementType, default_text_for,
                                     description_for, display_name_for, is_default_text)
from tests.conftest import add, connect
from tools import check_translations
from tools.extract_strings import collect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")
TRANSLATED = [code for code in i18n.LANGUAGES if code != i18n.SOURCE_LANGUAGE]
ALL_LANGUAGES = list(i18n.LANGUAGES)
# Unsichtbare Zeichen, die die Schreibrichtung umschalten: Die Oberfläche spiegelt selbst, im Text stören sie
DIRECTION_MARKS = re.compile("[‎‏‪-‮⁦-⁩]")
UNRESOLVED = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(:[^{}]*)?\}")
PSEUDO_MARKS = ("⟦", "⟧")


@pytest.fixture(autouse=True)
def _application(qapp):
    """Nach jedem Test gilt wieder Deutsch – auch für Qt (Schreibrichtung, Gebietsschema, Schriften)."""
    yield
    i18n.set_language("de")
    i18n.apply_to_application(qapp, "de")
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


@pytest.fixture(scope="module")
def entries():
    found, _dynamic = collect()
    return found


def catalog_file(code: str) -> dict:
    with open(os.path.join(i18n.translations_directory(), f"{code}.json"), encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------------ Kataloge
def test_every_language_of_the_menu_has_a_translation():
    assert i18n.available_languages() == ALL_LANGUAGES


@pytest.mark.parametrize("code", TRANSLATED)
def test_translation_is_complete_and_well_formed(code, entries):
    errors, _warnings = check_translations.check_language(code, entries)
    assert errors == [], "\n".join(errors[:25])


@pytest.mark.parametrize("code", TRANSLATED)
def test_translation_file_is_plain_text_without_direction_marks(code):
    catalog = catalog_file(code)
    assert catalog and all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in catalog.items())
    marked = [key for key, value in catalog.items() if DIRECTION_MARKS.search(value)]
    assert marked == []
    assert not any(mark in value for value in catalog.values() for mark in PSEUDO_MARKS)


def test_program_text_for_generated_code_exists_only_in_english(entries):
    """Texte, die nur in erzeugten Programmen stehen, braucht außer Deutsch nur das Englische."""
    only_code = [key for key, entry in entries.items() if entry.kinds == {"tr_code"}]
    assert only_code
    english = catalog_file("en")
    assert all(key in english for key in only_code)
    for key in only_code:
        # ein Anführungszeichen oder Backslash würde das erzeugte Programm stören
        assert '"' not in english[key] and "\\" not in english[key], key


# --------------------------------------------------- Bausteine, Beschriftungen
@pytest.mark.parametrize("code", ALL_LANGUAGES)
def test_blocks_and_labels_have_distinct_names(code):
    i18n.set_language(code)
    names = [display_name_for(t) for t in ElementType]
    assert all(name.strip() for name in names) and len(set(names)) == len(names)
    assert all(description_for(t).strip() for t in ElementType)
    words = [labels.yes_label(), labels.no_label(), labels.else_label()]
    assert all(word.strip() and len(word) <= 16 for word in words) and len(set(words)) == 3


def _stored_texts() -> dict:
    """Was in der eingestellten Sprache in einer Projektdatei landet."""
    defaults = []
    for element_type in ElementType:
        variants = [{LOOP_PART_KEY: LOOP_BEGIN}, {LOOP_PART_KEY: LOOP_END}] if element_type is ElementType.LOOP \
            else [None]
        for properties in variants:
            defaults.append((element_type, properties, default_text_for(element_type, properties)))
    return {"defaults": defaults, "yes": labels.yes_label(), "no": labels.no_label(), "else": labels.else_label(),
            "start": default_text_for(ElementType.START)}


@pytest.mark.parametrize("written_in", ALL_LANGUAGES)
def test_stored_texts_are_recognised_in_every_other_language(written_in):
    """Ein Plan, der in einer Sprache angelegt wurde, verhält sich in jeder anderen Sprache gleich."""
    i18n.set_language(written_in)
    stored = _stored_texts()
    for opened_in in ALL_LANGUAGES:
        i18n.set_language(opened_in)
        for element_type, properties, text in stored["defaults"]:
            if text:
                assert is_default_text(text, element_type, properties), (written_in, opened_in, text)
        assert labels.is_yes(stored["yes"]) and not labels.is_no(stored["yes"]) and not labels.is_else(stored["yes"])
        assert labels.is_no(stored["no"]) and not labels.is_yes(stored["no"]) and not labels.is_else(stored["no"])
        assert labels.is_else(stored["else"]) and not labels.is_yes(stored["else"])
        assert stored["start"].strip().lower() in labels.generic_program_names()


def _decision_program(scene) -> None:
    """Start → Eingabe x → „x > 0“ → ja: Ausgabe "plus" / nein: Ausgabe "minus" → Ende."""
    start = add(scene, ElementType.START, 0, 0)
    read = add(scene, ElementType.INPUT, 0, 120)
    read.set_text("x")
    decision = add(scene, ElementType.DECISION, 0, 260)
    decision.set_text("x > 0")
    plus = add(scene, ElementType.OUTPUT, 0, 420)
    plus.set_text('"plus"')
    minus = add(scene, ElementType.OUTPUT, 320, 420)
    minus.set_text('"minus"')
    end = add(scene, ElementType.END, 0, 600)
    connect(scene, start, "bottom", read, "top")
    connect(scene, read, "bottom", decision, "top")
    connect(scene, decision, "bottom", plus, "top")     # erster Ausgang: „ja“ der Sprache
    connect(scene, decision, "right", minus, "top")     # zweiter Ausgang: „nein“ der Sprache
    connect(scene, plus, "bottom", end, "top")
    connect(scene, minus, "bottom", end, "left")


def _run(scene, value: str) -> list[str]:
    from app.simulation.engine import NEEDS_INPUT, Simulator
    simulator = Simulator(FlowGraph.from_scene(scene))
    for _ in range(100):
        result = simulator.step()
        if result.needs == NEEDS_INPUT:
            simulator.provide_input(value)
        if simulator.finished:
            break
    assert simulator.finished
    return simulator.outputs


@pytest.mark.parametrize("code", ALL_LANGUAGES)
def test_a_plan_drawn_in_one_language_runs_the_same_in_german_and_english(code, scene):
    from app.codegen.generators import generate
    i18n.set_language(code)
    _decision_program(scene)
    exits = sorted(c.data.label for c in scene.connections() if c.data.label)
    assert exits == sorted([labels.yes_label(), labels.no_label()])
    for opened_in in ("de", "en", code):
        i18n.set_language(opened_in)
        assert _run(scene, "5") == ["plus"] and _run(scene, "-5") == ["minus"]
        programs = structure_diagram(FlowGraph.from_scene(scene))
        assert not programs[0].warnings
        python = generate(programs, "python", "Test")
        compile(python, "generated.py", "exec")
        assert python.index('print("plus")') < python.index("else:") < python.index('print("minus")')


# ------------------------------------------------- Schreibtischtest und Code
@pytest.mark.parametrize("code", ALL_LANGUAGES)
def test_example_runs_and_generates_valid_code_in_every_language(code):
    from app.codegen.generators import generate
    from app.simulation.engine import NEEDS_INPUT, Simulator
    i18n.set_language(code)
    document = DiagramDocument.open_file(EXAMPLE)
    try:
        simulator = Simulator(FlowGraph.from_scene(document.scene))
        values = iter(["3", "1", "2", "3"])
        for _ in range(200):
            result = simulator.step()
            assert result.message is None or not UNRESOLVED.search(result.message), result.message
            if result.needs == NEEDS_INPUT:
                simulator.provide_input(next(values))
            if simulator.finished:
                break
        assert simulator.finished and simulator.outputs == ["Mittelwert: 2"] and simulator.variables["summe"] == 6

        programs = structure_diagram(FlowGraph.from_scene(document.scene))
        python = generate(programs, "python", document.meta.name)
        compile(python, "generated.py", "exec")
        java = generate(programs, "java", document.meta.name)
        assert java.count("{") == java.count("}") and "public class BeispielMittelwert" in java
        pseudo = generate(programs, "pseudo", document.meta.name)
        assert not any(mark in text for text in (python, java, pseudo) for mark in PSEUDO_MARKS)
        if code == "de":
            assert "WENN n > 0 ? DANN" in pseudo and "Automatisch erzeugt" in python
        else:
            # jede andere Sprache erzeugt denselben englischen Programmtext
            i18n.set_language("en")
            assert (python, java, pseudo) == tuple(generate(programs, kind, document.meta.name)
                                                   for kind in ("python", "java", "pseudo"))
            assert "WENN" not in pseudo and "Automatisch erzeugt" not in python and "Hinweis" not in java
    finally:
        document.scene.clear_diagram()


def test_generic_java_class_name_is_a_plain_identifier(scene):
    """Heißt der Ablauf nur „Start“, bekommt die Java-Klasse einen allgemeinen Namen aus ASCII-Buchstaben."""
    from app.codegen.generators import generate
    for code in ALL_LANGUAGES:
        i18n.set_language(code)
        scene.clear_diagram()
        start = add(scene, ElementType.START, 0, 0)
        end = add(scene, ElementType.END, 0, 200)
        connect(scene, start, "bottom", end, "top")
        java = generate(structure_diagram(FlowGraph.from_scene(scene)), "java", None)
        name = re.search(r"public class (\S+) \{", java).group(1)
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name), (code, name)
        assert name == ("Programm" if code == "de" else "Program")


# ---------------------------------------------------- Hauptfenster und Dialoge
def _visible_texts(root: QWidget) -> list[str]:
    texts = [root.windowTitle()]
    for action in root.findChildren(QAction):
        texts += [action.text(), action.statusTip(), action.toolTip()]
    for menu in root.findChildren(QMenu):
        texts.append(menu.title())
    for widget in root.findChildren(QWidget):
        texts.append(widget.toolTip())
        if isinstance(widget, (QLabel, QAbstractButton)):
            texts.append(widget.text())
        elif isinstance(widget, QLineEdit):
            texts.append(widget.placeholderText())
        elif isinstance(widget, QDockWidget):
            texts.append(widget.windowTitle())
        elif isinstance(widget, QTabWidget):
            texts += [widget.tabText(index) for index in range(widget.count())]
    return [text for text in texts if text]


def _assert_clean(texts: list[str], where: str) -> None:
    for text in texts:
        assert not UNRESOLVED.search(text), f"{where}: Platzhalter nicht gefüllt: {text!r}"
        assert not any(mark in text for mark in PSEUDO_MARKS), f"{where}: {text!r}"


@pytest.mark.parametrize("code", ALL_LANGUAGES)
def test_main_window_and_dialogs_build_in_every_language(code, qapp, tmp_path):
    from app.autosave import RecoveryEntry
    from app.codegen.dialog import CodeDialog
    from app.dialogs.about import AboutDialog
    from app.dialogs.export_options import ExportOptionsDialog
    from app.dialogs.project_properties import ProjectPropertiesDialog
    from app.dialogs.recovery import RecoveryDialog
    from app.dialogs.shortcuts import ShortcutsDialog
    from app.export import ExportOptions
    from app.main_window import MainWindow
    from app.nsd.dialog import StructogramDialog

    i18n.set_language(code)
    i18n.apply_to_application(qapp, code)
    window = MainWindow(enable_autosave=False, autosave_directory=str(tmp_path / "autosave"))
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    qapp.processEvents()
    try:
        expected = Qt.LayoutDirection.RightToLeft if code == "ar" else Qt.LayoutDirection.LeftToRight
        assert window.layoutDirection() == expected
        assert window.open_file(EXAMPLE)
        document = window.current_document()
        document.scene.select_items(document.scene.elements()[:2])
        qapp.processEvents()
        window.simulation_panel.restart()
        window.simulation_panel.step()
        window.diagnostics_panel.refresh()
        qapp.processEvents()
        _assert_clean(_visible_texts(window), f"Hauptfenster ({code})")

        titles = [action.text() for action in window.menuBar().actions()]
        assert len(titles) >= 7 and all(title.strip() for title in titles)
        if code != "de":
            assert "&Datei" not in titles and "&Bearbeiten" not in titles and "&Hilfe" not in titles

        entry = RecoveryEntry(str(tmp_path / "a.pap"), str(tmp_path / "a.json"), "Plan", None,
                              "2026-10-08T10:00:00", "s1")
        dialogs = [AboutDialog(window), ShortcutsDialog(window),
                   ProjectPropertiesDialog(document.meta, 20, None, window),
                   ExportOptionsDialog("PNG", ExportOptions(), window),
                   StructogramDialog(document, window), RecoveryDialog([entry], window)]
        dialogs += [CodeDialog(document, window, language=kind) for kind in ("pseudo", "python", "java")]
        for dialog in dialogs:
            texts = _visible_texts(dialog)
            assert dialog.windowTitle().strip() and texts
            _assert_clean(texts, f"{type(dialog).__name__} ({code})")
            dialog.deleteLater()
    finally:
        for view in window.views():
            view.document.undo_stack.setClean()
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("code", ALL_LANGUAGES)
def test_about_and_splash_name_version_and_month(code):
    from app import splash
    i18n.set_language(code)
    assert config.APP_VERSION in splash.version_text()
    month = i18n.release_date_text()
    assert month.strip() and config.APP_RELEASE_DATE.split()[-1] in month
    if code not in ("de", i18n.PSEUDO_LANGUAGE):
        assert month != config.APP_RELEASE_DATE
