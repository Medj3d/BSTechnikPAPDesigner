"""Tests für Ablaufgraph und Strukturierung (ohne Qt)."""

import os

from app.analysis.ast import (Action, DoWhileLoop, EndStmt, If, LimitLoop, Unstructured, WhileLoop)
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.fileformat.serializer import load_diagram
from app.model.diagram import ConnectionData, ElementData
from app.model.element_types import ElementType as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class G:
    """Kleiner Baukasten für Testgraphen."""

    def __init__(self):
        self.elements = []
        self.connections = []
        self._y = 0

    def node(self, nid, etype, text="", **props):
        self._y += 100
        self.elements.append(ElementData(nid, etype, 0, self._y, 160, 60, text or nid, 0, props))
        return self

    def edge(self, a, b, label="", sp="bottom", tp="top"):
        self.connections.append(ConnectionData(f"{a}-{b}-{len(self.connections)}", a, b, sp, tp, label))
        return self

    def programs(self):
        return structure_diagram(FlowGraph.from_diagram(self.elements, self.connections))


def kinds(block):
    return [type(s).__name__ for s in block]


def test_sequence():
    g = (G().node("s", T.START).node("i", T.INPUT).node("p", T.PROCESS).node("o", T.OUTPUT).node("e", T.END)
         .edge("s", "i").edge("i", "p").edge("p", "o").edge("o", "e"))
    (prog,) = g.programs()
    assert kinds(prog.body) == ["Action", "Action", "Action", "EndStmt"]
    assert [s.kind for s in prog.body.statements[:3]] == ["input", "process", "output"]
    assert prog.end_id == "e" and not prog.warnings


def test_if_else_with_merge():
    g = (G().node("s", T.START).node("d", T.DECISION, "x > 0").node("a", T.PROCESS).node("b", T.PROCESS)
         .node("m", T.OUTPUT).node("e", T.END)
         .edge("s", "d").edge("d", "a", "ja").edge("d", "b", "nein", sp="right")
         .edge("a", "m").edge("b", "m").edge("m", "e"))
    (prog,) = g.programs()
    stmt = prog.body.statements[0]
    assert isinstance(stmt, If) and stmt.condition == "x > 0"
    assert [s.element_id for s in stmt.then_block] == ["a"]
    assert [s.element_id for s in stmt.else_block] == ["b"]
    assert prog.body.statements[1].element_id == "m"


def test_if_without_else():
    g = (G().node("s", T.START).node("d", T.DECISION).node("a", T.PROCESS).node("m", T.PROCESS).node("e", T.END)
         .edge("s", "d").edge("d", "a", "ja").edge("d", "m", "nein", sp="right").edge("a", "m").edge("m", "e"))
    (prog,) = g.programs()
    stmt = prog.body.statements[0]
    assert isinstance(stmt, If) and len(stmt.then_block) == 1 and len(stmt.else_block) == 0


def test_while_loop():
    g = (G().node("s", T.START).node("d", T.DECISION, "i < n").node("b", T.PROCESS).node("e", T.END)
         .edge("s", "d").edge("d", "b", "ja").edge("b", "d", tp="left").edge("d", "e", "nein", sp="right"))
    (prog,) = g.programs()
    loop = prog.body.statements[0]
    assert isinstance(loop, WhileLoop) and not loop.negate
    assert [s.element_id for s in loop.body] == ["b"]
    assert isinstance(prog.body.statements[1], EndStmt)


def test_while_loop_negated():
    g = (G().node("s", T.START).node("d", T.DECISION, "fertig?").node("b", T.PROCESS).node("e", T.END)
         .edge("s", "d").edge("d", "e", "ja").edge("d", "b", "nein", sp="right").edge("b", "d", tp="right"))
    (prog,) = g.programs()
    loop = prog.body.statements[0]
    assert isinstance(loop, WhileLoop) and loop.negate


def test_do_while_loop():
    g = (G().node("s", T.START).node("a", T.INPUT).node("b", T.PROCESS).node("d", T.DECISION, "x < 0")
         .node("e", T.END)
         .edge("s", "a").edge("a", "b").edge("b", "d").edge("d", "a", "ja", sp="left", tp="left")
         .edge("d", "e", "nein"))
    (prog,) = g.programs()
    loop = prog.body.statements[0]
    assert isinstance(loop, DoWhileLoop) and loop.condition == "x < 0" and not loop.negate
    assert [s.element_id for s in loop.body] == ["a", "b"]


def test_limit_loop():
    g = (G().node("s", T.START).node("lb", T.LOOP, "Für i = 1 bis 10", part="begin").node("b", T.PROCESS)
         .node("le", T.LOOP, "nächstes i", part="end").node("e", T.END)
         .edge("s", "lb").edge("lb", "b").edge("b", "le").edge("le", "e"))
    (prog,) = g.programs()
    loop = prog.body.statements[0]
    assert isinstance(loop, LimitLoop) and loop.end_id == "le" and loop.footer == "nächstes i"
    assert [s.element_id for s in loop.body] == ["b"]


def test_nested_loop_in_if_and_early_end():
    g = (G().node("s", T.START).node("d", T.DECISION).node("w", T.DECISION).node("b", T.PROCESS)
         .node("e1", T.END).node("e2", T.END)
         .edge("s", "d").edge("d", "w", "ja").edge("d", "e2", "nein", sp="right")
         .edge("w", "b", "ja").edge("b", "w", tp="left").edge("w", "e1", "nein", sp="right"))
    (prog,) = g.programs()
    stmt = prog.body.statements[0]
    assert isinstance(stmt, If)
    assert isinstance(stmt.then_block.statements[0], WhileLoop)
    assert any(isinstance(s, EndStmt) for s in stmt.else_block)


def test_junction_is_transparent():
    g = (G().node("s", T.START).node("a", T.PROCESS).node("j", T.JUNCTION).node("b", T.PROCESS)
         .node("c", T.INPUT).node("e", T.END)
         .edge("s", "a").edge("a", "j").edge("j", "b").edge("c", "j", tp="right").edge("b", "e"))
    graph = FlowGraph.from_diagram(g.elements, g.connections).collapse_junctions()
    assert "j" not in graph.nodes
    assert graph.successors("a") == ["b"] and graph.successors("c") == ["b"]


def test_comments_become_annotations():
    g = (G().node("s", T.START).node("a", T.PROCESS).node("k", T.COMMENT, "Hinweis").node("e", T.END)
         .edge("s", "a").edge("a", "e").edge("k", "a", sp="left", tp="right"))
    (prog,) = g.programs()
    assert prog.body.statements[0].comments == ["Hinweis"]


def test_unstructured_jump_does_not_crash():
    g = (G().node("s", T.START).node("d", T.DECISION).node("a", T.PROCESS).node("b", T.PROCESS).node("e", T.END)
         .edge("s", "d").edge("d", "a", "ja").edge("d", "b", "nein").edge("a", "b").edge("b", "a", sp="left")
         .edge("b", "e", sp="right"))
    programs = g.programs()
    assert programs  # kein Absturz


def test_example_file_structures_cleanly():
    result = load_diagram(os.path.join(ROOT, "examples", "Beispiel_Mittelwert.pap"))
    (prog,) = structure_diagram(FlowGraph.from_diagram(result.diagram.elements, result.diagram.connections))
    kinds_top = kinds(prog.body)
    assert "LimitLoop" in kinds_top and "If" in kinds_top
    assert not any(isinstance(s, Unstructured) for s in prog.body)
    assert not prog.warnings
