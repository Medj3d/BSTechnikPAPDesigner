"""Tests für das Fundament der Mehrsprachigkeit (app/i18n.py), die Spracheinstellung und das Auslese-Werkzeug."""

import importlib.util
import json
import os
import sys

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QMessageBox

from app import config, i18n, restart
from app.i18n import N_, tr, tr_code

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # sonst können Datenklassen im Werkzeug ihr Modul nicht finden
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def catalogs(monkeypatch, tmp_path):
    """Ein leerer Ordner für Übersetzungsdateien (statt assets/translations) und ein leerer Zwischenspeicher."""
    monkeypatch.setattr(i18n, "translations_directory", lambda: str(tmp_path))
    monkeypatch.setattr(i18n, "_catalogs", {})

    def write(code, data, raw=None):
        (tmp_path / f"{code}.json").write_text(raw if raw is not None else json.dumps(data, ensure_ascii=False),
                                               encoding="utf-8")
        i18n._catalogs.clear()  # gelesene Kataloge werden gemerkt; neue Dateien sollen gelten

    return write


@pytest.fixture(autouse=True)
def _qt_application(qapp):
    yield


# ---------------------------------------------------------------- tr / N_
def test_german_is_the_source_and_needs_no_catalog():
    assert i18n.language() == "de"
    assert tr("Datei speichern") == "Datei speichern"
    assert tr("{n} Bausteine", n=3) == "3 Bausteine"
    assert tr("Ende", ctx="Baustein") == "Ende"
    assert N_("Vorgang") == "Vorgang"
    assert tr("Geschweifte Klammern { } ohne Platzhalter bleiben stehen") == "Geschweifte Klammern { } ohne Platzhalter bleiben stehen"
    assert tr("Mit {{doppelten}} Klammern {n}", n=1) == "Mit {doppelten} Klammern 1"


def test_translation_replaces_the_german_text(catalogs):
    catalogs("en", {"Datei speichern": "Save file", "{n} Bausteine": "{n} blocks", "Baustein::Ende": "End block",
                    "Ende": "End"})
    assert i18n.set_language("en") == "en"
    assert tr("Datei speichern") == "Save file"
    assert tr("{n} Bausteine", n=3) == "3 blocks"
    assert tr("Ende") == "End"
    assert tr("Ende", ctx="Baustein") == "End block"   # eigener Eintrag für diese Bedeutung
    assert tr("Ende", ctx="Menü") == "End"             # ohne eigenen Eintrag gilt die allgemeine Übersetzung
    assert tr("Unbekannter Text") == "Unbekannter Text"  # fehlt es, erscheint der deutsche Text
    assert tr("Unbekannt {x}", x=1) == "Unbekannt 1"


def test_wrong_placeholders_never_break_the_program(catalogs):
    catalogs("en", {"{n} Bausteine": "{count} blocks", "Zahl {n}": "Number {n} {m}", "Text {n": "kaputt"})
    i18n.set_language("en")
    assert tr("{n} Bausteine", n=3) == "3 Bausteine"  # falscher Platzhalter: der deutsche Text
    assert tr("Zahl {n}", n=1) == "Zahl 1"


def test_empty_and_malformed_catalog_entries_are_ignored(catalogs):
    catalogs("fr", {"A": "", "B": 5, "C": None, "D": "ok"})
    assert i18n.load_catalog("fr") == {"D": "ok"}
    catalogs("es", None, raw="{kein json")
    assert i18n.load_catalog("es") == {}
    catalogs("ru", None, raw="[1, 2]")
    assert i18n.load_catalog("ru") == {}
    catalogs("ja", {"A": "あ"}, raw="﻿" + json.dumps({"A": "あ"}, ensure_ascii=False))  # mit BOM
    assert i18n.load_catalog("ja") == {"A": "あ"}
    assert i18n.load_catalog("zh") == {}  # Datei fehlt


def test_available_languages_are_german_plus_every_language_with_a_file(catalogs):
    assert i18n.available_languages() == ["de"]
    catalogs("en", {"A": "a"})
    catalogs("ja", {"A": "あ"})
    catalogs("xx", {"A": "x"})  # keine Sprache des Programms
    assert i18n.available_languages() == ["de", "en", "ja"]


def test_pseudo_language_marks_every_text_and_keeps_placeholders(catalogs):
    assert i18n.set_language(i18n.PSEUDO_LANGUAGE) == "xx"
    assert tr("Datei") == "⟦Datei⟧" and tr("{n} Bausteine", n=2) == "⟦2 Bausteine⟧"
    assert tr_code("Eingabe") == "⟦Eingabe⟧"
    assert N_("Vorgang") == "Vorgang"  # nur die Markierung; angezeigt wird erst tr(...)


def test_set_language_and_codes():
    assert i18n.normalize("de-DE") == "de" and i18n.normalize("PT_br") == "pt" and i18n.normalize("zh-Hans") == "zh"
    assert i18n.normalize("xx") == "" and i18n.normalize(None) == "" and i18n.normalize("") == ""
    assert i18n.set_language("unbekannt") == "de"
    assert i18n.set_language("JA") == "ja" and i18n.language() == "ja"
    assert i18n.is_rtl("ar") and not i18n.is_rtl("de") and i18n.is_rtl() is False
    assert set(i18n.LANGUAGES) == {"de", "en", "fr", "es", "pt", "ru", "ar", "zh", "ja"}
    assert i18n.language_name("ar") == "العربية" and i18n.language_name("zz") == "zz"


def test_resolve_falls_back_to_english_then_german(catalogs, monkeypatch):
    monkeypatch.setattr(i18n, "system_language", lambda: "fr")
    assert i18n.resolve("auto") == "en" or i18n.resolve("auto") == "de"  # ohne Dateien
    assert i18n.resolve("de") == "de" and i18n.resolve("xyz") == i18n.resolve("auto")
    catalogs("en", {"A": "a"})
    assert i18n.resolve("auto") == "en"         # Französisch fehlt → Englisch
    catalogs("fr", {"A": "a"})
    assert i18n.resolve("auto") == "fr" and i18n.resolve("fr") == "fr"
    assert i18n.resolve("ru") == "en"           # gewählt, aber ohne Übersetzung → Englisch
    assert i18n.resolve(None) == "fr"


def test_system_language_is_taken_from_the_operating_system(monkeypatch):
    from PySide6.QtCore import QLocale
    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale("pt_BR")))
    assert i18n.system_language() == "pt"
    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale("it_IT")))
    assert i18n.system_language() == "en"   # unbekannte Systemsprache
    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale("de_AT")))
    assert i18n.system_language() == "de"


def test_all_translations_find_a_text_in_every_language(catalogs):
    catalogs("en", {"Vorgang": "Process", "Baustein::Ende": "End"})
    catalogs("fr", {"Vorgang": "Traitement"})
    catalogs("ar", {"Vorgang": "عملية"})
    assert i18n.all_translations("Vorgang") == {"Vorgang", "Process", "Traitement", "عملية"}
    assert i18n.all_translations("Ende", ctx="Baustein") == {"Ende", "End"}
    assert i18n.all_translations("Etwas anderes") == {"Etwas anderes"}


def test_code_text_is_german_for_german_and_english_for_every_other_language(catalogs):
    catalogs("en", {"Eingabe": "Input", "{n} Werte": "{n} values"})
    catalogs("ru", {"Eingabe": "Ввод"})
    assert tr_code("Eingabe") == "Eingabe"
    i18n.set_language("ru")
    assert tr("Eingabe") == "Ввод" and tr_code("Eingabe") == "Input"  # erzeugter Programmtext bleibt englisch
    assert tr_code("{n} Werte", n=2) == "2 values" and tr_code("Nur deutsch") == "Nur deutsch"


def test_placeholders_helper():
    assert i18n.placeholders("Text {b} und {a} und {a}") == ["a", "b"]
    assert i18n.placeholders("ohne") == [] and i18n.placeholders("{{wörtlich}}") == []
    assert i18n.placeholders("kaputt {") == ["<ungültig>"]
    assert i18n.placeholders("{0} {1:>5}") == ["0", "1"]


def test_release_date_uses_the_month_name_of_the_language(catalogs):
    assert i18n.release_date_text("Oktober 2026") == "Oktober 2026"
    catalogs("en", {"A": "a"})
    catalogs("fr", {"A": "a"})
    catalogs("ru", {"A": "a"})
    catalogs("ja", {"A": "a"})
    i18n.set_language("en")
    assert i18n.release_date_text("Oktober 2026") == "October 2026"
    i18n.set_language("fr")
    assert i18n.release_date_text("März 2027") == "mars 2027"
    i18n.set_language("ru")
    assert i18n.release_date_text("Oktober 2026").endswith(" 2026") and i18n.release_date_text("Oktober 2026")[0].isalpha()
    assert i18n.release_date_text("Oktober 2026") != "Oktober 2026"
    i18n.set_language("ja")
    assert "10" in i18n.release_date_text("Oktober 2026")
    assert i18n.release_date_text("irgendwas") == "irgendwas" and i18n.release_date_text("Foo 2026") == "Foo 2026"
    assert i18n.release_date_text() != ""


def test_font_fallbacks_prefer_the_script_of_the_language():
    assert i18n.font_fallbacks("zh")[0] == "Microsoft YaHei UI" and i18n.font_fallbacks("ja")[0] == "Yu Gothic UI"
    assert "Microsoft YaHei UI" in i18n.font_fallbacks("de") and "Yu Gothic UI" in i18n.font_fallbacks("ar")


# ------------------------------------------------------------- Qt-Anbindung
@pytest.fixture
def restore_application(qapp):
    yield
    i18n.apply_to_application(qapp, "de")
    i18n.set_language("de")
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


@pytest.mark.parametrize("code", ["fr", "es", "pt", "ru", "ar", "zh", "ja", "de"])
def test_qt_standard_texts_are_translated(qapp, code, restore_application):
    """Standardtexte von Qt (Ja/Nein, Kopieren/Einfügen, Druckdialog) kommen aus Qts eigenen Übersetzungen."""
    assert i18n.install_qt_translations(qapp, code) is True
    yes = QCoreApplication.translate("QPlatformTheme", "&Yes")
    assert yes and yes != "&Yes"


def test_applying_a_language_sets_direction_locale_and_fonts(qapp, restore_application):
    from PySide6.QtCore import QLocale
    i18n.apply_to_application(qapp, "ar")
    assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert QLocale().language() == QLocale.Language.Arabic
    i18n.apply_to_application(qapp, "ja")
    assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert QLocale().language() == QLocale.Language.Japanese
    assert config.ITEM_FONT_FAMILIES[:4] == ["Segoe UI", "Inter", "Helvetica Neue", "Arial"]
    assert config.ITEM_FONT_FAMILIES[4] == "Yu Gothic UI"
    i18n.apply_to_application(qapp, "zh")
    assert config.ITEM_FONT_FAMILIES[4] == "Microsoft YaHei UI" and config.ITEM_FONT_FAMILIES.count("Yu Gothic UI") == 1


# ----------------------------------------------------- Einstellung und Menü
@pytest.fixture
def window(qapp, tmp_path):
    from app.main_window import MainWindow
    win = MainWindow(enable_autosave=True, autosave_directory=str(tmp_path / "autosave"))
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    qapp.processEvents()
    yield win
    win.settings_store._settings.remove("language")
    for view in win.views():
        view.document.undo_stack.setClean()
    win.close()
    win.deleteLater()


def test_language_setting_defaults_to_the_system_language(window):
    store = window.settings_store
    assert store.language() == i18n.AUTOMATIC
    store.set_language("fr")
    assert store.language() == "fr"
    store.set_language("unsinn")
    assert store.language() == i18n.AUTOMATIC


def test_language_menu_lists_the_languages_in_their_own_names(window, catalogs):
    menu = next(a.menu() for a in window.menuBar().actions() if a.text().replace("&", "") == "Ansicht")
    language_menu = next(a.menu() for a in menu.actions() if a.text() == "Sprache / Language")
    labels = [a.text() for a in language_menu.actions()]
    assert labels[0] == "Automatisch (Systemsprache)" and "Deutsch" in labels
    assert window.language_actions[i18n.AUTOMATIC].isChecked()
    assert sum(1 for a in language_menu.actions() if a.isChecked()) == 1


def test_choosing_a_language_is_saved_and_offers_a_restart(window, monkeypatch, catalogs):
    restarts, boxes = [], []
    monkeypatch.setattr(window, "restart_program", lambda: restarts.append(True))
    answer = {"restart": False}
    catalogs("fr", {"A": "a"})  # nur Sprachen mit Übersetzung lassen sich einstellen
    catalogs("es", {"A": "a"})

    def fake_exec(self):
        boxes.append(self.text())
        self._chosen = [b for b in self.buttons() if (b.text() == tr("Jetzt neu starten")) == answer["restart"]][0]

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self._chosen)
    window._on_language_chosen("fr")
    assert window.settings_store.language() == "fr" and len(boxes) == 1 and restarts == []   # „Später“
    answer["restart"] = True
    window._on_language_chosen("es")
    assert window.settings_store.language() == "es" and len(boxes) == 2 and restarts == [True]
    window._on_language_chosen("es")  # unverändert: nichts passiert
    assert len(boxes) == 2


def test_choosing_the_running_language_needs_no_restart(window, monkeypatch):
    boxes = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: boxes.append(self.text()))
    window._on_language_chosen("de")
    assert window.settings_store.language() == "de" and boxes == []


# --------------------------------------------------------------- Neustart
def test_restart_command_waits_for_the_old_program_and_reopens_the_projects(monkeypatch, tmp_path):
    monkeypatch.setattr(restart.resources, "is_frozen", lambda: True)
    assert restart.command(["a.pap", "b c.pap"], pid=4711) == [
        sys.executable, config.WAIT_FOR_FLAG, "4711", "a.pap", "b c.pap"]
    monkeypatch.setattr(restart.resources, "is_frozen", lambda: False)
    command = restart.command([], pid=1, language="fr")
    assert command[:2] == [sys.executable, restart.MAIN_SCRIPT] and os.path.isfile(restart.MAIN_SCRIPT)
    assert command[2:] == [config.WAIT_FOR_FLAG, "1", config.LANGUAGE_FLAG, "fr"]


def test_restart_starts_only_when_the_program_really_ends(window, monkeypatch, qapp, tmp_path):
    started = []
    monkeypatch.setattr(restart.subprocess, "Popen", lambda command, **kwargs: started.append(command))
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    # 1. Der Benutzer bricht das Schließen ab: kein Neustart, auch nicht später
    window.new_document()
    from tests.conftest import add
    from app.model.element_types import ElementType
    add(window.current_document().scene, ElementType.PROCESS, 0, 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: [b for b in self.buttons() if b.text() == "Abbrechen"][0])
    window.restart_program()
    assert window.views() and window._restart_files is None
    qapp.aboutToQuit.emit()
    assert started == []
    # 2. Der Benutzer verwirft die Änderung: Der Neustart ist eingeplant und startet beim Beenden
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: [b for b in self.buttons() if b.text() == "Verwerfen"][0])
    window.restart_program()
    qapp.aboutToQuit.emit()
    assert len(started) == 1 and started[0][2:4] == [config.WAIT_FOR_FLAG, str(os.getpid())]


# ------------------------------------------------------ Auslese-Werkzeug
def write_tree(root, files):
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_extraction_finds_literals_contexts_and_flags_dynamic_calls(tmp_path):
    tool = load_tool("extract_strings")
    write_tree(tmp_path, {
        "main.py": 'from app.i18n import tr\nprint(tr("Hallo {name}", name=1))\n',
        "app/a.py": ('from app import i18n\nfrom app.i18n import N_, tr, tr_code\n'
                     'X = N_("Vorgang")\nY = i18n.tr("Datei")\nZ = tr("Ende", ctx="Baustein")\n'
                     'W = tr_code("Eingabe")\nV = tr(variable)\nU = tr("Mehrzeilig "\n "zusammengesetzt")\n'
                     'T = tr("Datei")\nS = other.tr("nicht gemeint")\nR = tr("Ende", ctx=kontext)\n'),
        "app/i18n.py": 'tr("wird übersprungen")\n',
        "app/__pycache__/x.py": 'tr("auch nicht")\n',
        "app/sub/b.py": 'N_("Unterordner")\n',
    })
    entries, dynamic = tool.collect(str(tmp_path))
    assert sorted(entries) == ["Baustein::Ende", "Datei", "Eingabe", "Ende", "Hallo {name}", "Mehrzeilig zusammengesetzt",
                               "Unterordner", "Vorgang"]
    assert entries["Hallo {name}"].placeholders == ["name"]
    assert entries["Datei"].kinds == {"tr"} and len(entries["Datei"].locations) == 2
    assert entries["Vorgang"].kinds == {"N_"} and entries["Eingabe"].kinds == {"tr_code"}
    assert entries["Baustein::Ende"].ctx == "Baustein" and entries["Baustein::Ende"].text == "Ende"
    assert [(d.path, d.line) for d in dynamic] == [("app/a.py", 7), ("app/a.py", 12)]


def test_extraction_reports_what_a_catalog_lacks(tmp_path, catalogs):
    tool = load_tool("extract_strings")
    write_tree(tmp_path, {"main.py": 'tr("Eins")\ntr("Zwei")\ntr("Drei")\n'})
    entries, _ = tool.collect(str(tmp_path))
    catalogs("en", {"Eins": "One", "Zwei": "Two"})
    assert tool.missing("en", entries) == ["Drei"] and tool.missing("fr", entries) == ["Eins", "Zwei", "Drei"]


def test_the_real_source_can_be_read_without_errors():
    tool = load_tool("extract_strings")
    entries, dynamic = tool.collect()
    assert entries  # mindestens das Sprachmenü
    assert all(e.text.strip() for e in entries.values())
