"""Gespeicherte Dateien öffnen sich im PapDesigner.

Der PapDesigner verbindet nur waagerecht oder senkrecht von Rasterzelle zu Rasterzelle; jede Ecke ist ein
eigener Verbindungspunkt. Verlässt eine Verbindung eine Verzweigung schräg oder nach oben, öffnet er die
ganze Datei nicht (am Original geprüft). Beim Speichern bekommt deshalb jede andere Verbindung Eckpunkte, die
nur der PapDesigner sieht: Dieses Programm setzt sie beim Öffnen wieder zu einer Verbindung zusammen, ältere
Versionen lesen sie als gewöhnliche Verbindungspunkte – ohne dass etwas verloren geht.
"""

import glob
import os
import re
import xml.etree.ElementTree as ET

import pytest

from app.analysis.graph import FlowGraph
from app.fileformat.project import EXTENSION_NAMESPACE
from app.fileformat.serializer import diagram_from_xml, diagram_to_xml, load_diagram
from app.model.diagram import ConnectionData, Diagram, ElementData
from app.model.element_types import ElementType as T
from tests.papdesigner_corpus import generate

BST = "{" + EXTENSION_NAMESPACE + "}"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def grid_problems(xml: str, through: bool = False) -> list[str]:
    """Verbindungen, die der PapDesigner nicht (oder nur schief) zeichnet. ``through``: auch Strecken, die
    über einen anderen Baustein laufen (so schreibt dieses Programm keine)."""
    problems = []
    root = ET.fromstring(xml.lstrip("﻿").encode("utf-8"))
    for diagram in root.iter("DIAGRAM"):
        cells, subtype = {}, {}
        for entry in diagram.iter("ENTRY"):
            figure = entry.find("FIGURE")
            cells[figure.get("ID")] = (int(entry.get("COLUMN")), int(entry.get("ROW")))
            subtype[figure.get("ID")] = figure.get("SUBTYPE")
        if len(set(cells.values())) != len(cells):
            problems.append(f"{diagram.get('NAME')}: zwei Bausteine in einer Rasterzelle")
        for node in diagram.iter("CONNECTION"):
            (c1, r1), (c2, r2) = cells[node.get("FROM")], cells[node.get("TO")]
            if c1 != c2 and r1 != r2:
                problems.append(f"{diagram.get('NAME')}: schräg {node.attrib}")
            elif subtype[node.get("FROM")] == "PapCondition" and r2 < r1:
                problems.append(f"{diagram.get('NAME')}: Verzweigung nach oben {node.attrib}")
            elif through:
                occupied = set(cells.values())
                between = ([(c1, r) for r in range(min(r1, r2) + 1, max(r1, r2))] if c1 == c2 else
                           [(c, r1) for c in range(min(c1, c2) + 1, max(c1, c2))])
                if any(cell in occupied for cell in between):
                    problems.append(f"{diagram.get('NAME')}: über einen Baustein {node.attrib}")
    return problems


def as_old_version(xml: str) -> str:
    """So sieht eine ältere Version dieses Programms die Datei: Sie kennt bst:CORNER, bst:TO und bst:FULL_… nicht."""
    return re.sub(r' bst:(CORNER|TO|FULL_[A-Z_]+)="[^"]*"', "", xml)


def collapsed(diagram: Diagram) -> list:
    """Verbindungen ohne die Verbindungspunkte dazwischen: (Quelltext, Zieltext, Beschriftung)."""
    elements = {e.id: e for e in diagram.all_elements()}
    junctions = {e.id for e in elements.values() if e.type is T.JUNCTION}
    onward = {}
    connections = list(diagram.connections) + [c for page in diagram.subprograms for c in page.connections]
    for c in connections:
        onward.setdefault(c.source_id, []).append(c)

    def end(element_id, seen=()):
        while element_id in junctions and element_id not in seen:
            seen = seen + (element_id,)
            element_id = onward[element_id][0].target_id
        return element_id

    return sorted((c.source_id, end(c.target_id), c.label) for c in connections if c.source_id not in junctions)


def branching_plan() -> Diagram:
    """Verzweigung mit Zweigen nach unten und zur Seite, Zusammenführung, Rücksprung von links nach oben."""
    def element(eid, etype, x, y, text=""):
        return ElementData(eid, etype, x, y, 160, 60 if etype is not T.DECISION else 100, text)

    elements = [element("s", T.START, 0, 0, "Start"), element("d", T.DECISION, 0, 140, "x > 0"),
                element("a", T.PROCESS, 0, 280, "a"), element("b", T.PROCESS, 240, 280, "b"),
                element("j", T.JUNCTION, 0, 420), element("q", T.DECISION, 0, 560, "nochmal?"),
                element("e", T.END, 0, 700, "Ende")]
    connections = [ConnectionData("c1", "s", "d", "bottom", "top"),
                   ConnectionData("c2", "d", "a", "bottom", "top", "ja"),
                   ConnectionData("c3", "d", "b", "right", "top", "nein"),
                   ConnectionData("c4", "a", "j", "bottom", "top"),
                   ConnectionData("c5", "b", "j", "bottom", "right"),
                   ConnectionData("c6", "j", "q", "bottom", "top"),
                   ConnectionData("c7", "q", "d", "left", "left", "ja"),
                   ConnectionData("c8", "q", "e", "bottom", "top", "nein")]
    return Diagram(elements=elements, connections=connections)


def test_branches_are_written_with_corners_and_read_back_unchanged():
    diagram = branching_plan()
    xml = diagram_to_xml(diagram)
    assert grid_problems(xml, through=True) == []
    assert 'bst:CORNER="True"' in xml
    loaded = diagram_from_xml(xml)
    assert loaded.native and loaded.warnings == []
    assert loaded.diagram.elements == diagram.elements
    assert loaded.diagram.connections == diagram.connections


def test_older_versions_read_corners_as_junctions_without_losing_anything():
    diagram = branching_plan()
    old = diagram_from_xml(as_old_version(diagram_to_xml(diagram)))
    assert old.native and old.warnings == []
    extra = [e for e in old.diagram.elements if e.id not in {d.id for d in diagram.elements}]
    assert extra and all(e.type is T.JUNCTION for e in extra)
    assert collapsed(old.diagram) == collapsed(diagram)
    # der Ablauf ist derselbe (Verbindungspunkte sind nur Durchgangsstellen)
    assert FlowGraph.from_diagram(old.diagram.elements, old.diagram.connections).nodes.keys() >= \
        {e.id for e in diagram.elements}


def test_manual_line_and_path_stay_with_the_whole_connection():
    diagram = branching_plan()
    diagram.connections[2].routing = {"mode": "manual", "axis": "x", "value": 260.0}
    diagram.connections[2].path = [(80.0, 140.0), (260.0, 140.0), (260.0, 250.0)]
    xml = diagram_to_xml(diagram)
    loaded = diagram_from_xml(xml).diagram
    assert loaded.connections[2].routing == diagram.connections[2].routing
    assert loaded.connections[2].path == diagram.connections[2].path
    # ältere Versionen wenden den Verlauf der ganzen Linie nicht auf das erste Stück an
    old = diagram_from_xml(as_old_version(xml)).diagram
    first = next(c for c in old.connections if c.id == "c3")
    assert first.path is None and first.routing == {"mode": "auto"}


def test_corners_are_shared_by_arrows_into_the_same_target():
    elements = [ElementData("d", T.DECISION, 0, 0, 160, 100, "x?"),
                ElementData("l", T.PROCESS, -240, 140, 160, 60, "l"),
                ElementData("r", T.PROCESS, 240, 140, 160, 60, "r"),
                ElementData("z", T.END, 0, 420, 120, 40, "Ende")]
    connections = [ConnectionData("c1", "d", "l", "left", "top", "ja"),
                   ConnectionData("c2", "d", "r", "right", "top", "nein"),
                   ConnectionData("c3", "l", "z", "bottom", "left"),
                   ConnectionData("c4", "r", "z", "bottom", "right")]
    diagram = Diagram(elements=elements, connections=connections)
    xml = diagram_to_xml(diagram)
    assert grid_problems(xml) == []
    assert diagram_from_xml(xml).diagram.connections == connections


@pytest.mark.parametrize("seed", range(0, 60, 3))
def test_generated_papdesigner_plans_are_saved_drawable(seed, tmp_path):
    project = generate(seed)
    assert grid_problems(project.to_xml()) == []  # so schreibt sie der PapDesigner
    loaded = diagram_from_xml(project.to_xml().encode("utf-8")).diagram
    # die erzeugten Pläne sind dicht gepackt: Wo ein Ziel ringsum zugebaut ist, darf eine Linie (wie im
    # PapDesigner erlaubt) über einen Baustein laufen – schräg oder aus einer Verzweigung nach oben nie
    assert grid_problems(diagram_to_xml(loaded)) == []


def test_bundled_examples_are_drawable_in_papdesigner():
    paths = glob.glob(os.path.join(ROOT, "assets", "examples", "*.pap")) + \
        [os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap")]
    for path in paths:
        with open(path, encoding="utf-8-sig") as handle:
            assert grid_problems(handle.read(), through=True) == [], path
        assert load_diagram(path).warnings == []


def test_comment_lines_are_kept_out_of_papdesigners_view():
    """Kommentare verbindet der PapDesigner nie (eine Linie wäre dort ein Ablaufpfeil); hier bleiben sie samt
    Reihenfolge erhalten."""
    diagram = branching_plan()
    note = ElementData("n", T.COMMENT, 300, 140, 200, 60, "Hinweis")
    diagram.elements.append(note)
    diagram.connections.insert(3, ConnectionData("cn", "n", "d", "left", "right"))
    xml = diagram_to_xml(diagram)
    root = ET.fromstring(xml.encode("utf-8"))
    comment_numbers = {f.get("ID") for f in root.iter("FIGURE") if f.get("SUBTYPE") == "PapComment"}
    assert not [c for c in root.iter("CONNECTION") if comment_numbers & {c.get("FROM"), c.get("TO")}]
    loaded = diagram_from_xml(xml)
    assert loaded.warnings == [] and loaded.diagram.connections == diagram.connections



def test_a_branch_is_not_drawn_over_the_other_branch():
    """„nein“ geht nach rechts und läuft um „ja“ herum, statt senkrecht darüber (Lernbeispiel 5)."""
    elements = [ElementData("d", T.DECISION, 0, 0, 160, 100, "prim?"),
                ElementData("o", T.OUTPUT, 0, 140, 160, 60, "z"),
                ElementData("j", T.JUNCTION, 0, 280, 12, 12)]
    connections = [ConnectionData("c1", "d", "o", "bottom", "top", "ja"),
                   ConnectionData("c2", "d", "j", "right", "right", "nein"),
                   ConnectionData("c3", "o", "j", "bottom", "top")]
    xml = diagram_to_xml(Diagram(elements=elements, connections=connections))
    assert grid_problems(xml, through=True) == []
    root = ET.fromstring(xml.encode("utf-8"))
    first = next(c for c in root.iter("CONNECTION") if c.get(BST + "UID") == "c2")
    assert first.get(BST + "TO") is not None  # über Eckpunkte rechts herum


def test_a_loop_back_goes_beside_the_column():
    elements = [ElementData("s", T.START, 0, 0, 120, 40, "Start"),
                ElementData("d", T.DECISION, 0, 140, 160, 100, "i < 10?"),
                ElementData("b", T.PROCESS, 0, 280, 160, 60, "x = x + i"),
                ElementData("i", T.PROCESS, 0, 420, 160, 60, "i = i + 1"),
                ElementData("e", T.END, 240, 140, 120, 40, "Ende")]
    connections = [ConnectionData("c1", "s", "d", "bottom", "top"),
                   ConnectionData("c2", "d", "b", "bottom", "top", "ja"),
                   ConnectionData("c3", "b", "i", "bottom", "top"),
                   ConnectionData("c4", "i", "d", "left", "left"),
                   ConnectionData("c5", "d", "e", "right", "left", "nein")]
    diagram = Diagram(elements=elements, connections=connections)
    xml = diagram_to_xml(diagram)
    assert grid_problems(xml, through=True) == []
    assert diagram_from_xml(xml).diagram == diagram


def test_long_columns_still_get_a_straight_route():
    elements = [ElementData(f"m{i}", T.DECISION if i == 2 else T.PROCESS, 0, i * 140, 160, 60, f"m{i}")
                for i in range(70)]
    elements += [ElementData("side", T.PROCESS, 240, 280, 160, 60, "side"),
                 ElementData("t", T.PROCESS, 240, 1400, 160, 60, "t")]
    connections = [ConnectionData(f"k{i}", f"m{i}", f"m{i + 1}", "bottom", "top") for i in range(69)]
    connections.append(ConnectionData("x", "m2", "t", "right", "top", "ja"))
    xml = diagram_to_xml(Diagram(elements=elements, connections=connections))
    assert grid_problems(xml) == []


def test_older_versions_keep_junction_trunks_and_sensible_ports():
    from app.model.element_types import TRUNK_IN_KEY
    diagram = branching_plan()
    diagram.elements[4].properties[TRUNK_IN_KEY] = "c5"  # der Verbindungspunkt ist am Pfeil von „b“ ausgerichtet
    xml = diagram_to_xml(diagram)
    assert diagram_from_xml(xml).diagram == diagram
    old = diagram_from_xml(as_old_version(xml)).diagram
    entering = next(c for c in old.connections if c.id == "c5")
    assert entering.target_id == "j"  # das Stück, das im Verbindungspunkt ankommt, trägt dessen Stamm-ID
    old_cells = {e.id for e in old.elements}
    corner_ids = old_cells - {e.id for e in diagram.elements}
    for c in old.connections:
        if c.source_id in corner_ids or c.target_id in corner_ids:
            assert c.source_port in ("top", "bottom", "left", "right")
            assert c.target_port in ("top", "bottom", "left", "right")


def test_corner_positions_do_not_cover_other_blocks_for_older_versions():
    diagram = branching_plan()
    old = diagram_from_xml(as_old_version(diagram_to_xml(diagram))).diagram
    blocks = [e for e in old.elements if e.id in {d.id for d in diagram.elements}]
    for corner in (e for e in old.elements if e not in blocks):
        for block in blocks:
            assert not (abs(corner.x - block.x) < block.width / 2 and abs(corner.y - block.y) < block.height / 2), \
                (corner, block.text)
