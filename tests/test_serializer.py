"""Tests für das Dateiformat .pap."""

import os
import re
import xml.etree.ElementTree as ET

import pytest

from app.fileformat.project import CURRENT_FORMAT_VERSION, EXTENSION_NAMESPACE, ProjectFileError
from app.fileformat.serializer import (diagram_from_xml, diagram_to_xml, load_diagram, save_diagram,
                                       storable_text)
from app.model.diagram import ConnectionData, Diagram, ElementData
from app.model.element_types import ElementType

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")
PAP_SAMPLE = os.path.join(ROOT, "tests", "data", "papdesigner", "mittelwert.pap")
BST = f"{{{EXTENSION_NAMESPACE}}}"

NASTY_TEXTS = [
    "", " ", "  führende und folgende Leerzeichen  ", "Zeile 1\nZeile 2\n", "\n\nx", "a\tb",
    'x < 3 && y > "4" & \'z\'', "]]>", "a]]>b]]>c", "<![CDATA[x]]>", "<!DOCTYPE x>", '<!ENTITY a "b">',
    "<?xml version=\"1.0\"?>", "&amp; &#10; &lt;", "äöüß „Zitat“ – € ² ³", "😀 𝔘𝔫𝔦", "x\r\ny", "nur\rCR",
    "{\"format\": \"json\"}", "100 %", "a" * 5000,
]


def sample_diagram() -> Diagram:
    diagram = Diagram()
    diagram.meta.name = "Test"
    diagram.meta.author = "Autor"
    diagram.settings.grid_size = 25
    diagram.settings.snap_to_grid = False
    diagram.settings.zoom = 1.5
    diagram.elements = [
        ElementData("a", ElementType.START, 0, 0, 120, 40, "Start"),
        ElementData("b", ElementType.PROCESS, 0, 100, 160, 60, "x = 1\ny = 2", 3.0),
        ElementData("c", ElementType.LOOP, 0, 200, 160, 60, "Wiederhole", 0, {"part": "end"}),
    ]
    diagram.connections = [
        ConnectionData("k1", "a", "b", "bottom", "top", "", {"mode": "auto"}),
        ConnectionData("k2", "b", "c", "bottom", "top", "weiter", {"mode": "manual", "axis": "x", "value": 40}),
    ]
    return diagram


def full_diagram() -> Diagram:
    """Alle Bausteintypen und alle Angaben, die ein Projekt enthalten kann."""
    diagram = Diagram()
    diagram.meta.name = "Voll „ständig“ <1> & 2"
    diagram.meta.author = "A. Utor"
    diagram.meta.description = "Zeile 1\nZeile 2\t(Tab)\n"
    diagram.meta.created = "2025-01-02T03:04:05+01:00"
    diagram.meta.modified = "2026-10-07T12:00:00+02:00"
    diagram.settings.grid_size = 30
    diagram.settings.grid_visible = False
    diagram.settings.snap_to_grid = False
    diagram.settings.zoom = 0.3333333333333333
    diagram.settings.view_center_x = -1234.5678901234
    diagram.settings.view_center_y = 0.1 + 0.2
    diagram.elements = [
        ElementData("start", ElementType.START, 0.0, 0.0, 120.0, 40.0, "Start"),
        ElementData("in", ElementType.INPUT, 0.125, 100.0, 200.0, 60.0, "n einlesen"),
        ElementData("lb", ElementType.LOOP, 0.0, 200.0, 160.0, 60.0, "Für i = 1 bis n", 0.0, {"part": "begin"}),
        ElementData("proc", ElementType.PROCESS, -17.3, 300.7, 173.0, 61.5, "s = s + i\nt = t * 2", 2.0),
        ElementData("sub", ElementType.SUBPROGRAM, 0.0, 400.0, 160.0, 60.0, "pruefe(s)"),
        ElementData("le", ElementType.LOOP, 0.0, 500.0, 160.0, 60.0, "", 0.0, {"part": "end"}),
        ElementData("dec", ElementType.DECISION, 0.0, 640.0, 160.0, 120.0, "s > 10 ?", -1.0),
        ElementData("out", ElementType.OUTPUT, 0.0, 800.0, 160.0, 60.0, "s ausgeben"),
        ElementData("other", ElementType.OUTPUT, 300.0, 800.0, 160.0, 60.0, "„zu klein“ ausgeben"),
        ElementData("j", ElementType.JUNCTION, 0.0, 900.0, 12.0, 12.0, "", 0.0,
                    {"trunk_in": "c8", "trunk_out": "c10"}),
        ElementData("end", ElementType.END, 0.0, 1000.0, 120.0, 40.0, "Ende"),
        ElementData("note", ElementType.COMMENT, 320.0, 0.0, 200.0, 60.0, "Hinweis:\n  eingerückt"),
        ElementData("extra", ElementType.PROCESS, 49000.0, -49000.0, 160.0, 60.0, "weit weg", 0.0,
                    {"farbe": "rot", "zahl": 3, "kommazahl": 1.5, "wahr": True, "nichts": None,
                     "liste": [1, "zwei", {"drei": 3}]}),
        # dieselbe Zelle wie „start“: im Raster nur einmal vergebbar, die Position bleibt trotzdem exakt
        ElementData("doppelt", ElementType.PROCESS, 0.0, 0.0, 160.0, 60.0, "liegt auf Start"),
    ]
    diagram.connections = [
        ConnectionData("c1", "start", "in", "bottom", "top", path=[(0.0, 20.0), (0.0, 70.0)]),
        ConnectionData("c2", "in", "lb", "bottom", "top"),
        ConnectionData("c3", "lb", "proc", "bottom", "top"),
        ConnectionData("c4", "proc", "sub", "bottom", "top", "", {"mode": "manual", "axis": "y", "value": 350.25}),
        ConnectionData("c5", "sub", "le", "bottom", "top"),
        ConnectionData("c6", "le", "dec", "bottom", "top"),
        ConnectionData("c7", "dec", "out", "bottom", "top", "ja"),
        ConnectionData("c8", "out", "j", "bottom", "top"),
        ConnectionData("c9", "dec", "other", "right", "top", "nein", {"mode": "manual", "axis": "x", "value": -40.0},
                       path=[(80.0, 640.0), (300.125, 640.0), (300.125, 770.0)]),
        ConnectionData("c10", "j", "end", "bottom", "top"),
        ConnectionData("c11", "other", "j", "bottom", "right"),
        ConnectionData("c12", "note", "start", "left", "right"),
        # fachlich fragwürdig, aber erlaubt: Baustein über zwei Anschlüsse mit sich selbst verbunden
        ConnectionData("c13", "proc", "proc", "right", "left", "noch mal"),
        # zweimal dieselbe Verbindung: die spätere wird beim Öffnen rot markiert
        ConnectionData("c14", "start", "in", "bottom", "top"),
    ]
    return diagram


def roundtrip(diagram: Diagram):
    return diagram_from_xml(diagram_to_xml(diagram))


def strip_extension_data(xml_text: str) -> bytes:
    """Der Inhalt so, wie ihn ein Programm sieht, das nur das PapDesigner-Format kennt."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    for element in root.iter():
        for key in [k for k in element.attrib if k.startswith(BST)]:
            del element.attrib[key]
    return ET.tostring(root, encoding="utf-8")


# --------------------------------------------------------------- Rundreise
def test_roundtrip(tmp_path):
    path = tmp_path / "projekt.pap"
    save_diagram(sample_diagram(), str(path))
    result = load_diagram(str(path))
    d = result.diagram
    assert result.warnings == [] and result.native
    assert d.meta.name == "Test" and d.meta.author == "Autor"
    assert d.settings.grid_size == 25 and d.settings.snap_to_grid is False and d.settings.zoom == 1.5
    assert [e.id for e in d.elements] == ["a", "b", "c"]
    assert d.elements[1].text == "x = 1\ny = 2"
    assert d.elements[2].properties["part"] == "end"
    assert d.connections[1].label == "weiter"
    assert d.connections[1].routing == {"mode": "manual", "axis": "x", "value": 40.0}


def test_roundtrip_loses_nothing(tmp_path):
    original = full_diagram()
    path = tmp_path / "voll.pap"
    save_diagram(original, str(path))
    result = load_diagram(str(path))
    assert result.warnings == [] and result.native
    # Dataclass-Vergleich: jedes Feld jedes Bausteins und jeder Verbindung, in derselben Reihenfolge
    assert result.diagram == original
    assert all(type(e.type) is ElementType for e in result.diagram.elements)
    # erneutes Speichern ergibt exakt dieselbe Datei
    again = tmp_path / "voll2.pap"
    save_diagram(result.diagram, str(again))
    assert again.read_bytes() == path.read_bytes()


def test_empty_project_roundtrip(tmp_path):
    path = tmp_path / "leer.pap"
    save_diagram(Diagram(), str(path))
    result = load_diagram(str(path))
    assert result.native and result.warnings == []
    assert result.diagram.elements == [] and result.diagram.connections == []


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_texts_survive_unchanged(text):
    diagram = Diagram()
    diagram.meta.name = text if text.strip() else "Name"
    diagram.meta.author = text
    diagram.meta.description = text
    diagram.elements = [
        ElementData("id " + text[:40], ElementType.PROCESS, 0, 0, 160, 60, text, 0, {"merkmal": text}),
        ElementData("b", ElementType.COMMENT, 300, 0, 160, 60, text),
        ElementData("j", ElementType.JUNCTION, 0, 200, 12, 12, "", 0, {"trunk_in": "k " + text[:40]}),
    ]
    diagram.connections = [ConnectionData("k " + text[:40], "id " + text[:40], "j", "bottom", "top", text)]
    result = roundtrip(diagram)
    assert result.warnings == []
    assert result.diagram == diagram


def test_unrepresentable_characters_are_replaced_instead_of_breaking_the_file():
    """Steuerzeichen kann XML nicht aufnehmen: weiche Umbrüche werden Zeilenumbrüche, der Rest entfällt."""
    diagram = Diagram()
    diagram.meta.description = "a\x00b\x0bc"
    diagram.elements = [ElementData("a", ElementType.PROCESS, 0, 0, 160, 60, "x\x01y\ud800z\U0000FFFF!\x0cEnde")]
    diagram.connections = [ConnectionData("k", "a", "a", "right", "left", "l\x1fm")]
    result = roundtrip(diagram)
    assert result.warnings == []
    assert result.diagram.meta.description == "ab\nc"
    assert result.diagram.elements[0].text == "xyz!\nEnde"
    assert result.diagram.connections[0].label == "lm"
    assert storable_text("Zeile 1\x0bZeile 2\tTab \U0001F600") == "Zeile 1\nZeile 2\tTab \U0001F600"


def test_formatting_of_the_xml_does_not_matter():
    """Anders eingerückt, ohne CDATA, mit anderem Präfix: derselbe Inhalt, dasselbe Projekt."""
    original = full_diagram()
    root = ET.fromstring(diagram_to_xml(original).encode("utf-8"))
    ET.register_namespace("anders", EXTENSION_NAMESPACE)
    compact = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    assert b"CDATA" not in compact and b"anders:" in compact
    assert diagram_from_xml(compact).diagram == original
    assert diagram_from_xml(b"\xef\xbb\xbf" + diagram_to_xml(original).encode("utf-8")).diagram == original
    assert diagram_from_xml("\r\n\n  " + diagram_to_xml(original)).diagram == original
    assert diagram_from_xml(diagram_to_xml(original).replace("\n", "\r\n")).diagram == original


# ------------------------------------------------------ Aufbau der Datei
def test_file_is_papdesigner_xml(tmp_path):
    path = tmp_path / "p.pap"
    save_diagram(full_diagram(), str(path))
    raw = path.read_bytes()
    assert raw.startswith(b'<?xml version="1.0" encoding="utf-8"?>\n<FRAME ')
    root = ET.fromstring(raw)
    assert root.tag == "FRAME" and root.get("APP_VERSION") and root.get("CHECKSUM")
    assert root.get(BST + "VERSION") == str(CURRENT_FORMAT_VERSION)
    project = root.find("PROJECT")
    assert project.get("NAME") == full_diagram().meta.name and project.get("CREATED") == "2025.01.02 03:04:05"
    (diagram,) = project.findall("./DIAGRAMS/DIAGRAM")
    layout = diagram.find("LAYOUT")
    entries = layout.findall("./ENTRIES/ENTRY")
    figures = [entry.find("FIGURE") for entry in entries]
    assert len(entries) == len(full_diagram().elements) + 1  # + Diagrammtitel
    assert entries[0].get("ANCHOR") == "True" and figures[0].get("SUBTYPE") == "PapTitle"
    assert [f.get("SUBTYPE") for f in figures[1:]] == [
        "PapStart", "PapInput", "PapLoopStart", "PapActivity", "PapModule", "PapLoopEnd", "PapCondition",
        "PapOutput", "PapOutput", "PapConnector", "PapEnd", "PapComment", "PapActivity", "PapActivity"]
    assert all(f.find("TEXT") is not None and f.get("FORMAT") == "1.00" for f in figures)
    # jede Rasterzelle nur einmal, alle innerhalb der angegebenen Rastergröße
    cells = [(int(e.get("COLUMN")), int(e.get("ROW"))) for e in entries]
    assert len(set(cells)) == len(cells)
    assert max(c for c, _ in cells) < int(layout.get("COLUMNS")) and max(r for _, r in cells) < int(layout.get("ROWS"))
    # fortlaufende Nummern; Verbindungen verweisen auf vorhandene Bausteine
    connections = diagram.findall("./CONNECTIONS/CONNECTION")
    numbers = [f.get("ID") for f in figures] + [c.get("ID") for c in connections]
    assert len(set(numbers)) == len(numbers) and all(n.isdigit() for n in numbers)
    figure_numbers = {f.get("ID") for f in figures}
    assert all(c.get("FROM") in figure_numbers and c.get("TO") in figure_numbers for c in connections)
    assert [c.get("TEXT") for c in connections][6] == "ja"
    # zusammengehörige Schleifenbegrenzungen verweisen aufeinander
    by_subtype = {f.get("SUBTYPE"): f for f in figures}
    assert by_subtype["PapLoopStart"].get("ASSOCIATE") == by_subtype["PapLoopEnd"].get("ID")
    assert by_subtype["PapLoopEnd"].get("ASSOCIATE") == by_subtype["PapLoopStart"].get("ID")


def test_nested_loops_are_paired_from_the_inside():
    diagram = Diagram()
    names = ["s", "b1", "b2", "x", "e2", "e1", "z"]
    kinds = {"b1": "begin", "b2": "begin", "e2": "end", "e1": "end"}
    for index, name in enumerate(names):
        if name in kinds:
            diagram.elements.append(ElementData(name, ElementType.LOOP, 0, index * 100, 160, 60, name, 0,
                                                {"part": kinds[name]}))
        else:
            diagram.elements.append(ElementData(name, ElementType.PROCESS, 0, index * 100, 160, 60, name))
    diagram.connections = [ConnectionData(f"k{i}", a, b, "bottom", "top")
                           for i, (a, b) in enumerate(zip(names, names[1:]))]
    root = ET.fromstring(diagram_to_xml(diagram).encode("utf-8"))
    figures = {f.find("TEXT").text: f for f in root.iter("FIGURE")}
    assert figures["b1"].get("ASSOCIATE") == figures["e1"].get("ID")
    assert figures["b2"].get("ASSOCIATE") == figures["e2"].get("ID")
    assert figures["x"].get("ASSOCIATE") is None


def test_file_stays_readable_without_the_extension_data():
    """Ohne die Zusatzangaben bleibt der Plan vollständig: Bausteine, Texte, Verbindungen."""
    original = full_diagram()
    result = diagram_from_xml(strip_extension_data(diagram_to_xml(original)))
    assert not result.native
    elements = result.diagram.elements
    assert elements[0].type is ElementType.COMMENT and elements[0].text == original.meta.name  # Diagrammtitel
    assert [(e.type, e.text) for e in elements[1:]] == [(e.type, e.text.strip()) for e in original.elements]
    assert [e.properties.get("part") for e in elements[1:]] == [e.properties.get("part") for e in original.elements]
    index_of = {e.id: i for i, e in enumerate(original.elements)}
    loaded_index = {e.id: i - 1 for i, e in enumerate(elements)}
    expected = [(index_of[c.source_id], index_of[c.target_id], c.label) for c in original.connections
                if c.source_id != c.target_id]
    assert [(loaded_index[c.source_id], loaded_index[c.target_id], c.label) for c in result.diagram.connections] == expected
    # jede Rasterzelle ist eine eigene Position
    positions = [(e.x, e.y) for e in elements]
    assert len(set(positions)) == len(positions)


# ------------------------------------------------- Dateien ohne Zusatzangaben
def test_papdesigner_file_is_read():
    result = load_diagram(PAP_SAMPLE)
    diagram = result.diagram
    assert not result.native and result.warnings == []
    assert diagram.meta.name == "Mittelwert" and diagram.meta.author == "Testautor"
    assert diagram.meta.created.startswith("2021-03-01T08:15:00")
    types = [e.type for e in diagram.elements]
    assert types.count(ElementType.START) == 2 and ElementType.JUNCTION in types
    assert {e.properties["part"] for e in diagram.elements if e.type is ElementType.LOOP} == {"begin", "end"}
    assert {"ja", "nein"} <= {c.label for c in diagram.connections}
    assert all(e.x % 20 == 0 and e.y % 20 == 0 for e in diagram.elements)


def test_papdesigner_file_becomes_exact_after_saving(tmp_path):
    first = load_diagram(PAP_SAMPLE)
    path = tmp_path / "mittelwert.pap"
    save_diagram(first.diagram, str(path))
    second = load_diagram(str(path))
    assert second.native and second.warnings == []
    assert second.diagram == first.diagram


def test_example_file_is_current_and_stable():
    result = load_diagram(EXAMPLE)
    assert result.native and result.warnings == []
    assert len(result.diagram.elements) == 13 and len(result.diagram.connections) == 13
    with open(EXAMPLE, encoding="utf-8", newline="") as handle:
        stored = handle.read()
    # Die Datei nennt die Programmversion, die sie geschrieben hat – eine neue
    # Versionsnummer allein macht das Beispiel nicht veraltet.
    writer = re.compile(r'bst:APP_VERSION="[^"]*"')
    assert writer.sub("", diagram_to_xml(result.diagram)) == writer.sub("", stored)


# ------------------------------------------------------------ Fehlerfälle
@pytest.mark.parametrize("content", [
    b"", b"   ", b"{kein json", b"\xff\xfe\x00garbage", b"[]", b"42", b"<kaputt", b"<FRAME></FRAME>",
    b"<HTML><PROJECT/></HTML>", b'<!DOCTYPE x [<!ENTITY a "b">]><FRAME><PROJECT/></FRAME>',
    b'<?xml version="1.0"?><!DOCTYPE FRAME><FRAME><PROJECT/></FRAME>',
    # das frühere JSON-Format wird nicht mehr gelesen
    b'{"format": "bsTechnik-pap", "format_version": 1, "items": [], "connections": []}',
])
def test_corrupted_files_raise_friendly_error(tmp_path, content):
    path = tmp_path / "kaputt.pap"
    path.write_bytes(content)
    with pytest.raises(ProjectFileError) as info:
        load_diagram(str(path))
    assert info.value.message


def test_missing_file(tmp_path):
    with pytest.raises(ProjectFileError):
        load_diagram(str(tmp_path / "gibt_es_nicht.pap"))


def with_version(version: str) -> bytes:
    xml_text = diagram_to_xml(sample_diagram())
    marker = f'bst:VERSION="{CURRENT_FORMAT_VERSION}"'
    assert marker in xml_text
    return xml_text.replace(marker, f'bst:VERSION="{version}"').encode("utf-8")


def test_future_version_rejected():
    with pytest.raises(ProjectFileError) as info:
        diagram_from_xml(with_version(str(CURRENT_FORMAT_VERSION + 1)))
    assert "neueren" in info.value.message


@pytest.mark.parametrize("version", ["", "abc", "0", "-1", "1.5"])
def test_invalid_version_rejected(version):
    with pytest.raises(ProjectFileError):
        diagram_from_xml(with_version(version))


def native_file(entries: str, connections: str = "", layout: str = "") -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<FRAME xmlns:bst="{EXTENSION_NAMESPACE}" bst:VERSION="1">
  <PROJECT NAME="P">
    <DIAGRAMS><DIAGRAM ID="0">
      <LAYOUT COLUMNS="3" ROWS="9" {layout}><ENTRIES>{entries}</ENTRIES></LAYOUT>
      <CONNECTIONS>{connections}</CONNECTIONS>
    </DIAGRAM></DIAGRAMS>
  </PROJECT>
</FRAME>""".encode("utf-8")


def entry(number, uid, subtype="PapActivity", extra='bst:X="0" bst:Y="0"', column=0, row=1) -> str:
    uid_attribute = f'bst:UID="{uid}"' if uid is not None else ""
    return (f'<ENTRY COLUMN="{column}" ROW="{row}" {extra}>'
            f'<FIGURE SUBTYPE="{subtype}" ID="{number}" {uid_attribute}><TEXT>t{number}</TEXT></FIGURE></ENTRY>')


def test_invalid_entries_are_repaired_with_warnings():
    entries = (entry(1, "a") + entry(2, "b", extra='bst:X="0" bst:Y="100"')
               + entry(3, "x", subtype="PapUnbekannt")
               + entry(4, "y", extra='bst:X="abc" bst:Y="nan"', column=2, row=5)
               + entry(5, None) + "<ENTRY COLUMN=\"1\" ROW=\"1\"/>")
    ports = 'bst:SOURCE_PORT="bottom" bst:TARGET_PORT="{}"'
    connections = (
        f'<CONNECTION ID="10" FROM="1" TO="2" TEXT="" bst:UID="ok" {ports.format("top")} />'
        f'<CONNECTION ID="11" FROM="1" TO="99" TEXT="" bst:UID="z" {ports.format("top")} />'
        # gleicher Anschluss als Anfang und Ende: technisch unmöglich → entfernt
        f'<CONNECTION ID="12" FROM="1" TO="1" TEXT="" bst:UID="s" {ports.format("bottom")} />'
        # Schleife auf sich selbst über zwei Anschlüsse: fachlich fragwürdig, bleibt erhalten
        f'<CONNECTION ID="13" FROM="2" TO="2" TEXT="" bst:UID="loop" {ports.format("top")} />'
        # ohne gespeicherte Anschlüsse: aus dem Raster abgeleitet
        '<CONNECTION ID="14" FROM="2" TO="4" TEXT="" bst:UID="abgeleitet" />')
    result = diagram_from_xml(native_file(entries, connections, layout='bst:GRID_SIZE="99999"'))
    elements = {e.id: e for e in result.diagram.elements}
    assert len(elements) == 5 and {"a", "b", "x", "y"} <= set(elements)
    assert elements["x"].type is ElementType.PROCESS  # unbekannter Typ → Vorgang
    assert (elements["y"].x, elements["y"].y) == (480, 700)  # ungültige Position → Rasterzelle
    connection_ids = [c.id for c in result.diagram.connections]
    assert connection_ids == ["ok", "loop", "abgeleitet"]
    assert result.diagram.connections[2].source_port in ("bottom", "right")
    assert result.diagram.settings.grid_size == 20
    assert len(result.warnings) >= 6


def test_duplicate_ids_get_new_ids():
    result = diagram_from_xml(native_file(entry(1, "a") + entry(2, "a") + entry(2, "c") + entry(3, "d"),
                                          '<CONNECTION ID="9" FROM="1" TO="3" bst:UID="k" />'
                                          '<CONNECTION ID="9" FROM="2" TO="3" bst:UID="k" />'))
    ids = [e.id for e in result.diagram.elements]
    assert len(ids) == len(set(ids)) == 3 and ids[0] == "a" and ids[2] == "d"
    connection_ids = [c.id for c in result.diagram.connections]
    assert len(connection_ids) == len(set(connection_ids)) == 2
    assert result.warnings


def test_save_failure_keeps_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "p.pap"
    save_diagram(sample_diagram(), str(path))
    original = path.read_bytes()

    def broken_replace(*_args, **_kwargs):
        raise PermissionError("gesperrt")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(ProjectFileError):
        save_diagram(Diagram(), str(path))
    assert path.read_bytes() == original
    assert [p.name for p in tmp_path.iterdir()] == ["p.pap"]


def test_save_into_missing_directory(tmp_path):
    with pytest.raises(ProjectFileError):
        save_diagram(sample_diagram(), str(tmp_path / "fehlt" / "p.pap"))


def test_properties_that_cannot_be_stored_raise_friendly_error(tmp_path):
    diagram = sample_diagram()
    diagram.elements[0].properties["objekt"] = object()
    with pytest.raises(ProjectFileError):
        save_diagram(diagram, str(tmp_path / "p.pap"))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("properties", [
    {1: "a"}, {None: "a"}, {"a": {2: "b"}}, {"a": (1, 2)}, {"a": b"bytes"}, {"a": float("nan")},
    {"a": float("inf")}, {("x", "y"): 1},
])
def test_properties_are_never_converted_silently(properties):
    """Was nicht unverändert zurückkäme, wird beim Speichern abgelehnt statt stillschweigend umgewandelt."""
    diagram = sample_diagram()
    diagram.elements[0].properties.update(properties)
    with pytest.raises((TypeError, ValueError)):
        diagram_to_xml(diagram)


# ------------------------------------------------------- Linienverlauf
def test_displayed_route_is_stored():
    diagram = sample_diagram()
    diagram.connections[0].path = [(0, 20), (0.5, 20), (0.5, 70)]
    xml_text = diagram_to_xml(diagram)
    assert 'bst:PATH="0,20 0.5,20 0.5,70"' in xml_text and xml_text.count("bst:PATH") == 1
    result = diagram_from_xml(xml_text)
    assert result.warnings == []
    assert result.diagram.connections[0].path == [(0.0, 20.0), (0.5, 20.0), (0.5, 70.0)]
    assert result.diagram.connections[1].path is None


@pytest.mark.parametrize("path", ["", "1,2", "1,2 3", "1,2 a,b", "1,2 nan,4", "1,2,3 4,5,6", "1;2 3;4"])
def test_invalid_route_is_discarded_with_a_hint(path):
    xml_text = diagram_to_xml(sample_diagram()).replace('bst:TARGET_PORT="top" />',
                                                       f'bst:TARGET_PORT="top" bst:PATH="{path}" />', 1)
    result = diagram_from_xml(xml_text)
    assert result.diagram.connections[0].path is None
    assert any("Linienverlauf" in warning for warning in result.warnings)


# ------------------------------------------------- präparierte Dateien
def test_every_repair_of_a_native_file_is_reported():
    entries = (entry(1, "a", extra='bst:X="0" bst:Y="0" bst:WIDTH="-5" bst:HEIGHT="abc" bst:Z="hoch"')
               + entry(2, "b", extra='bst:X="0" bst:Y="200"', row=2))
    connections = ('<CONNECTION ID="9" FROM="1" TO="2" bst:UID="k" bst:SOURCE_PORT="unten" bst:TARGET_PORT="top"'
                   ' bst:ROUTE_AXIS="z" bst:ROUTE_VALUE="1" />')
    result = diagram_from_xml(native_file(entries, connections))
    element = result.diagram.elements[0]
    assert (element.width, element.height, element.z) == (160.0, 60.0, 0.0)  # Standardgröße statt 1 × 1
    connection = result.diagram.connections[0]
    assert (connection.source_port, connection.target_port) == ("bottom", "top")
    assert connection.routing == {"mode": "auto"}
    for word in ("Größe", "Ebene", "Anschlüsse", "Linienführung"):
        assert any(word in warning for warning in result.warnings), word


def test_damaged_extra_properties_cannot_break_the_program():
    deep = "[" * 500 + "]" * 500
    entries = (entry(1, "a", subtype="PapConnector",
                     extra="bst:X=\"0\" bst:Y=\"0\"") .replace('bst:UID="a"', 'bst:UID="a" bst:PROPERTIES=\'{"trunk_in": [1], "trunk_out": {"x": 1}, "farbe": "rot"}\'')
               + entry(2, "b", extra='bst:X="0" bst:Y="200"', row=2).replace(
                   'bst:UID="b"', f'bst:UID="b" bst:PROPERTIES=\'{{"a": {deep}}}\'')
               + entry(3, "c", extra='bst:X="0" bst:Y="400"', row=3).replace(
                   'bst:UID="c"', 'bst:UID="c" bst:PROPERTIES="[1, 2]"'))
    result = diagram_from_xml(native_file(entries))
    first, second, third = result.diagram.elements
    assert first.properties == {"farbe": "rot"}  # Verweise auf Verbindungen müssen Texte sein
    assert second.properties == {} and third.properties == {}
    assert result.warnings == ["Ungültige Zusatzeigenschaften eines Bausteins wurden verworfen."]
    for element in result.diagram.elements:
        element.copy()
    assert diagram_from_xml(diagram_to_xml(result.diagram)).diagram == result.diagram


@pytest.mark.parametrize("attribute", ['COLUMN="9" ROW="1"', 'COLUMN="1" ROW="9"'])
@pytest.mark.parametrize("value", ["99999999999999", "9" * 400, "-" + "9" * 400, "1e400", "abc", ""])
def test_absurd_grid_positions_do_not_crash(attribute, value):
    raw = (f'<FRAME><PROJECT><DIAGRAMS><DIAGRAM><LAYOUT COLUMNS="{value}"><ENTRIES>'
           f'<ENTRY {attribute.replace("9", value)}><FIGURE SUBTYPE="PapStart" ID="1"><TEXT>s</TEXT></FIGURE></ENTRY>'
           '<ENTRY COLUMN="0" ROW="2"><FIGURE SUBTYPE="PapEnd" ID="2"><TEXT>e</TEXT></FIGURE></ENTRY>'
           '</ENTRIES></LAYOUT><CONNECTIONS><CONNECTION FROM="1" TO="2"/></CONNECTIONS></DIAGRAM>'
           '<DIAGRAM><LAYOUT><ENTRIES><ENTRY COLUMN="0" ROW="0"><FIGURE SUBTYPE="PapStart" ID="1"/></ENTRY>'
           '</ENTRIES></LAYOUT></DIAGRAM></DIAGRAMS></PROJECT></FRAME>').encode("utf-8")
    result = diagram_from_xml(raw)
    assert len(result.diagram.elements) == 3 and len(result.diagram.connections) == 1
    assert all(abs(e.x) <= 49000 and abs(e.y) <= 49000 for e in result.diagram.elements)


def test_references_tolerate_surrounding_blanks():
    raw = ('<FRAME><PROJECT><DIAGRAMS><DIAGRAM><LAYOUT><ENTRIES>'
           '<ENTRY COLUMN="0" ROW="1"><FIGURE SUBTYPE="PapStart" ID=" 1"><TEXT>s</TEXT></FIGURE></ENTRY>'
           '<ENTRY COLUMN="0" ROW="2"><FIGURE SUBTYPE="PapEnd" ID="2 "><TEXT>e</TEXT></FIGURE></ENTRY>'
           '</ENTRIES></LAYOUT><CONNECTIONS><CONNECTION FROM="1 " TO=" 2"/></CONNECTIONS></DIAGRAM>'
           '</DIAGRAMS></PROJECT></FRAME>')
    result = diagram_from_xml(raw)
    assert result.warnings == [] and len(result.diagram.connections) == 1


@pytest.mark.parametrize("content", [
    b"<FRAME><PROJECT/></FRAME>", b"<PROJECT><DIAGRAMS/></PROJECT>",
    b"<FRAME><PROJECT><DIAGRAMS><DIAGRAM><LAYOUT><ENTRIES/></LAYOUT></DIAGRAM></DIAGRAMS></PROJECT></FRAME>",
    b"<PROJECT><ETWAS><GANZ ANDERES='1'/></ETWAS></PROJECT>",
])
def test_foreign_xml_without_a_plan_is_not_opened_as_an_empty_project(content):
    with pytest.raises(ProjectFileError) as info:
        diagram_from_xml(content)
    assert "keinen Programmablaufplan" in info.value.message


def test_non_xml_content_is_named_as_such():
    with pytest.raises(ProjectFileError) as info:
        diagram_from_xml(b'{"format": "bsTechnik-pap", "items": []}')
    assert "kein Programmablaufplan im Format .pap" in info.value.message
    with pytest.raises(ProjectFileError) as info:
        diagram_from_xml(b"<FRAME><PROJECT>")
    assert "beschädigt" in info.value.message


def test_anything_unreadable_ends_in_a_friendly_error(tmp_path):
    for bad in (None, 5, b"\x00\x01\x02", "<FRAME", b"<FRAME><PROJECT NAME='x'></FRAME>"):
        with pytest.raises(ProjectFileError):
            diagram_from_xml(bad)
    with pytest.raises(ProjectFileError):
        load_diagram(str(tmp_path / "mit\x00null.pap"))
    with pytest.raises(ProjectFileError):
        load_diagram(str(tmp_path))  # ein Ordner


def test_thousands_of_blocks_on_one_spot_are_written_quickly():
    """Jede Rasterzelle wird nur einmal vergeben – auch dann ohne quadratischen Aufwand."""
    import time
    diagram = Diagram()
    diagram.elements = [ElementData(f"e{i}", ElementType.PROCESS, 0, 0, 160, 60, "x") for i in range(30000)]
    started = time.perf_counter()
    xml_text = diagram_to_xml(diagram)
    assert time.perf_counter() - started < 5.0
    root = ET.fromstring(xml_text.encode("utf-8"))
    cells = {(e.get("COLUMN"), e.get("ROW")) for e in root.iter("ENTRY")}
    assert len(cells) == 30001


def test_blocks_outside_the_work_area_are_reported():
    raw = ('<FRAME><PROJECT><DIAGRAMS><DIAGRAM><LAYOUT><ENTRIES>'
           + "".join(f'<ENTRY COLUMN="0" ROW="{row}"><FIGURE SUBTYPE="PapActivity" ID="{row}"/></ENTRY>'
                     for row in range(400))
           + '</ENTRIES></LAYOUT></DIAGRAM></DIAGRAMS></PROJECT></FRAME>')
    result = diagram_from_xml(raw)
    assert len(result.diagram.elements) == 400
    assert result.warnings == ["Bausteine außerhalb der Arbeitsfläche wurden an deren Rand gesetzt."]
