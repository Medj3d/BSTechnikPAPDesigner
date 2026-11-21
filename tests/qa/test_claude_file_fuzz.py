"""QA (Claude): kaputte, fremde und zufällig veränderte Projektdateien.

Jede Datei muss entweder mit einer verständlichen ``ProjectFileError``-Meldung abgelehnt werden oder danach in
allem funktionieren, was ein Schüler mit ihr macht: anzeigen, prüfen, Code erzeugen, Schreibtischtest, als Bild
ausgeben, speichern und wieder laden. Hänger fallen über eine Zeitgrenze auf.

``PAP_QA_FUZZ=300`` erhöht die Zahl der veränderten Dateien je Ausgangsdatei (Standard: 25).
"""

from __future__ import annotations

import glob
import os
import random
import time
import xml.etree.ElementTree as ET

import pytest

from app.analysis.structure import structure_diagram
from app.codegen.generators import LANGUAGES, generate
from app.document import DiagramDocument
from app.export import ExportError, ExportOptions, render_image
from app.fileformat.project import ProjectFileError
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from tests.qa.claude_qa_helpers import ROOT, check_scene, snapshot_document

COUNT = int(os.environ.get("PAP_QA_FUZZ", "25"))
SOURCES = sorted(glob.glob(os.path.join(ROOT, "examples", "*.pap"))
                 + glob.glob(os.path.join(ROOT, "assets", "examples", "*.pap"))
                 + glob.glob(os.path.join(ROOT, "tests", "data", "papdesigner", "*.pap")))
NASTY_VALUES = ["", " ", "-1", "0", "1e309", "-1e309", "NaN", "inf", "-0", "99999999999999999999", "abc", "😀",
                "x" * 5000, "<", "&", "1,5", "0x10", "None", "[]", "{}", '{"a": [1, {"b": null}]}', "1e9",
                "-49999", "3.4028235e38", "True", "False", "PapLoopEnd", "auto0", "\t\n"]
NASTY_TEXTS = ["", "😀👨‍👩‍👧 ≠ ≤ ∑", "ä" * 3000, "a\u202eb\u202c", "x = 1\ny = 2\n" * 200, "]]>", "solange",
               "Für i = 1 bis 10000000000", "wiederhole", "x = 10 ** 10 ** 10", "runden(1, 100000000)",
               "warte 99999 s", "Eingabe " + ", ".join(f"v{i}" for i in range(60))]
TIME_LIMIT = 15.0   # Sekunden für Laden und alle Folgeschritte einer Datei


def _mutate_tree(rng: random.Random, root) -> None:
    nodes = list(root.iter())
    for _ in range(rng.randint(1, 4)):
        node = rng.choice(nodes)
        roll = rng.random()
        if roll < 0.45 and node.attrib:
            key = rng.choice(list(node.attrib))
            node.set(key, rng.choice(NASTY_VALUES))
        elif roll < 0.6 and node.tag == "TEXT":
            node.text = rng.choice(NASTY_TEXTS)
        elif roll < 0.75:
            parent = next((p for p in nodes if node in list(p)), None)
            if parent is not None:
                parent.remove(node)
                nodes = list(root.iter())
        elif roll < 0.88:
            parent = next((p for p in nodes if node in list(p)), None)
            if parent is not None:
                parent.append(ET.fromstring(ET.tostring(node)))  # gleiche IDs doppelt
                nodes = list(root.iter())
        else:
            node.set("SUBTYPE", rng.choice(["PapStart", "PapEnd", "PapCondition", "PapLoopStart", "PapLoopEnd",
                                            "PapModule", "PapConnector", "PapComment", "PapTitle", "PapFoo"]))


def _mutate_bytes(rng: random.Random, raw: bytes) -> bytes:
    data = bytearray(raw)
    roll = rng.random()
    if roll < 0.4:
        return bytes(data[: rng.randrange(1, len(data))])          # abgeschnitten (wie nach einem Absturz beim Speichern)
    for _ in range(rng.randint(1, 8)):
        position = rng.randrange(len(data))
        if roll < 0.8:
            data[position] = rng.randrange(256)                       # einzelne Bytes kaputt
        else:
            data[position:position] = os.urandom(rng.randint(1, 30))  # Müll eingefügt
    return bytes(data)


def _variants(source: str, count: int):
    with open(source, "rb") as handle:
        raw = handle.read()
    rng = random.Random(f"{os.path.basename(source)}:{count}")
    for number in range(count):
        if number % 3 == 2:
            yield f"bytes{number}", _mutate_bytes(rng, raw)
        else:
            root = ET.fromstring(raw)
            _mutate_tree(rng, root)
            yield f"tree{number}", ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _run_simulation(document) -> None:
    simulator = Simulator(document.flow_graph())
    for _ in range(400):
        result = simulator.step()
        if result.finished:
            return
        if result.needs == NEEDS_INPUT:
            simulator.provide_input("3")
        elif result.needs == NEEDS_DECISION:
            simulator.provide_decision(1 if result.options else False)


def _everything_a_user_does(document, folder) -> None:
    for scene in document.scenes():
        check_scene(scene)
    programs = structure_diagram(document.flow_graph())
    for language in LANGUAGES:
        generate(programs, language, document.meta.name)
    _run_simulation(document)
    try:
        render_image(document.scene, ExportOptions(scale=0.5))
    except ExportError:
        pass  # leerer oder zu großer Plan: verständliche Meldung, kein Absturz
    path = os.path.join(folder, "wieder.pap")
    document.save(path)
    reopened = DiagramDocument.open_file(path)
    try:
        assert reopened.load_warnings == [], reopened.load_warnings
        assert snapshot_document(reopened) == snapshot_document(document)
    finally:
        for scene in reopened.scenes():
            scene.clear_diagram()
        reopened.deleteLater()


@pytest.mark.parametrize("source", SOURCES, ids=os.path.basename)
def test_mutated_files_are_rejected_cleanly_or_fully_usable(qapp, source, tmp_path):
    problems = []
    for name, payload in _variants(source, COUNT):
        path = tmp_path / f"{name}.pap"
        path.write_bytes(payload)
        started = time.monotonic()
        try:
            document = DiagramDocument.open_file(str(path))
        except ProjectFileError as exc:
            if not str(exc).strip():
                problems.append(f"{name}: Fehlermeldung ohne Text")
            continue
        except Exception as exc:  # noqa: BLE001 – genau das soll nicht vorkommen
            problems.append(f"{name}: Laden wirft {type(exc).__name__}: {exc}")
            continue
        try:
            _everything_a_user_does(document, str(tmp_path))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: nach dem Laden {type(exc).__name__}: {str(exc)[:300]}")
        finally:
            for scene in document.scenes():
                scene.clear_diagram()
            document.deleteLater()
        elapsed = time.monotonic() - started
        if elapsed > TIME_LIMIT:
            problems.append(f"{name}: {elapsed:.1f} s für Laden und Folgeschritte")
    assert not problems, "\n".join(problems[:15])


# ----------------------------------------------------------------- gezielte Sonderfälle
SPECIAL = {
    "leer": b"",
    "nur_leerzeichen": b"   \r\n\t ",
    "bom_ohne_inhalt": b"\xef\xbb\xbf",
    "png_umbenannt": b"\x89PNG\r\n\x1a\n" + os.urandom(200),
    "zip_docx_umbenannt": b"PK\x03\x04" + os.urandom(200),
    "utf16_mit_bom": '<?xml version="1.0" encoding="utf-16"?><FRAME><PROJECT NAME="x"/></FRAME>'.encode("utf-16"),
    "fremdes_xml": b'<?xml version="1.0"?><html><body>Hallo</body></html>',
    "milliarden_lachen": (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;'
                          b'&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]><FRAME><PROJECT NAME="&lol2;"/></FRAME>'),
    "externe_entitaet": (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///C:/Windows/win.ini">]>'
                         b'<FRAME><PROJECT NAME="&e;"/></FRAME>'),
    "tief_verschachtelt": b"<FRAME>" + b"<a>" * 50000 + b"</a>" * 50000 + b"</FRAME>",
    "kein_diagramm": b'<?xml version="1.0"?><FRAME><PROJECT NAME="x"><DIAGRAMS/></PROJECT></FRAME>',
}


@pytest.mark.parametrize("name", sorted(SPECIAL))
def test_foreign_and_broken_files_give_a_clear_message(qapp, tmp_path, name):
    path = tmp_path / f"{name}.pap"
    path.write_bytes(SPECIAL[name])
    started = time.monotonic()
    with pytest.raises(ProjectFileError) as caught:
        DiagramDocument.open_file(str(path))
    assert str(caught.value).strip()
    assert time.monotonic() - started < 5.0


def test_huge_element_size_from_a_file_does_not_hang_view_or_export(qapp, tmp_path):
    """Eine (manipulierte) Datei mit einem Baustein von 10⁹ Pixel Breite."""
    with open(os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap"), "rb") as handle:
        root = ET.fromstring(handle.read())
    entry = next(e for e in root.iter("ENTRY") if e.find("FIGURE") is not None
                 and e.find("FIGURE").get("SUBTYPE") == "PapActivity")
    key = next(k for k in entry.attrib if k.endswith("WIDTH"))
    entry.set(key, "1e9")
    path = tmp_path / "riesig.pap"
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    started = time.monotonic()
    document = DiagramDocument.open_file(str(path))
    try:
        # Das Programm setzt die Größe nach dem Text neu – der Plan bleibt normal groß
        assert max(item.width for item in document.scene.elements()) < 2000
        image = render_image(document.scene, ExportOptions())
        assert image.width() * image.height() < 50_000_000
        assert time.monotonic() - started < 5.0
    finally:
        document.scene.clear_diagram()
        document.deleteLater()
