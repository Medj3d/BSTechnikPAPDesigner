"""Tests für Verbindungsregeln und Linienführung (ohne Qt)."""

from app.connections import routing
from app.connections.routing import Rect
from app.model import rules
from app.model.element_types import ElementType

E = rules.ConnectionEnd
X = rules.ExistingConnection


def test_self_connection_flagged():
    error = rules.validate_connection(E("a", ElementType.PROCESS, "bottom"), E("a", ElementType.PROCESS, "top"), [])
    assert error is not None


def test_only_technical_problems_block():
    # fachliche Probleme sind nur Warnungen …
    assert rules.blocking_error(E("a", ElementType.PROCESS, "bottom"), E("a", ElementType.PROCESS, "top")) is None
    assert rules.blocking_error(E("a", ElementType.PROCESS, "bottom"), E("s", ElementType.START, "bottom")) is None
    assert rules.blocking_error(E("e", ElementType.END, "top"), E("a", ElementType.PROCESS, "top")) is None
    # … blockiert wird nur, was technisch unmöglich ist
    assert rules.blocking_error(E("a", ElementType.PROCESS, "bottom"), E("a", ElementType.PROCESS, "bottom"))
    assert rules.blocking_error(E("s", ElementType.START, "top"), E("a", ElementType.PROCESS, "top"))


def test_evaluation_marks_the_later_connection():
    info = rules.ConnectionInfo
    P = ElementType.PROCESS
    connections = [info("ab", "a", P, "bottom", "b", P, "top"),
                   info("ac", "a", P, "right", "c", P, "top"),
                   info("ab2", "a", P, "left", "b", P, "left")]
    warnings = rules.evaluate_connections(connections)
    assert "ab" not in warnings
    assert "ac" in warnings and "ab2" in warnings


def test_junction_branch_is_a_warning_but_merge_is_fine():
    info = rules.ConnectionInfo
    J, P = ElementType.JUNCTION, ElementType.PROCESS
    split = [info("in", "a", P, "bottom", "j", J, "top"), info("out", "j", J, "bottom", "b", P, "top"),
             info("branch", "j", J, "right", "c", P, "left")]
    assert set(rules.evaluate_connections(split)) == {"branch"}
    merge = [info("in", "a", P, "bottom", "j", J, "top"), info("out", "j", J, "bottom", "b", P, "top"),
             info("merge", "c", P, "left", "j", J, "right")]
    assert rules.evaluate_connections(merge) == {}


def test_start_cannot_be_target_and_end_cannot_be_source():
    assert rules.validate_connection(E("a", ElementType.PROCESS, "bottom"), E("s", ElementType.START, "bottom"), [])
    assert rules.validate_connection(E("e", ElementType.END, "top"), E("a", ElementType.PROCESS, "top"), [])


def test_backward_connections_and_cycles_allowed():
    existing = [X("a", "b", False), X("b", "c", False)]
    assert rules.validate_connection(E("c", ElementType.DECISION, "left"), E("a", ElementType.PROCESS, "left"),
                                     existing) is None


def test_only_decision_has_multiple_outputs():
    existing = [X("a", "b", False)]
    assert rules.validate_connection(E("a", ElementType.PROCESS, "right"), E("c", ElementType.PROCESS, "top"),
                                     existing) is not None
    existing = [X("d", "b", False)]
    assert rules.validate_connection(E("d", ElementType.DECISION, "right"), E("c", ElementType.PROCESS, "top"),
                                     existing) is None


def test_duplicate_connection_flagged():
    existing = [X("d", "b", False)]
    assert rules.validate_connection(E("d", ElementType.DECISION, "left"), E("b", ElementType.PROCESS, "top"),
                                     existing) is not None


def test_comment_annotation_rules():
    assert rules.validate_connection(E("k", ElementType.COMMENT, "left"), E("a", ElementType.PROCESS, "right"),
                                     []) is None
    assert rules.validate_connection(E("k", ElementType.COMMENT, "left"), E("l", ElementType.COMMENT, "right"),
                                     []) is not None
    # Kommentarlinie zählt nicht als Ablaufausgang
    existing = [X("a", "b", False)]
    assert rules.validate_connection(E("a", ElementType.PROCESS, "right"), E("k", ElementType.COMMENT, "left"),
                                     existing) is None


def test_invalid_port_is_blocking():
    assert rules.validate_connection(E("s", ElementType.START, "top"), E("a", ElementType.PROCESS, "top"), [])


def test_decision_label_suggestion():
    assert rules.suggest_decision_label([]) == "ja"
    assert rules.suggest_decision_label(["ja"]) == "nein"
    assert rules.suggest_decision_label(["Ja", "Nein"]) == ""


def _orthogonal(points):
    return all(abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6 for a, b in zip(points, points[1:]))


def test_straight_vertical_route():
    points = routing.route((0, 30), "bottom", (0, 90), "top", Rect(-80, -30, 80, 30), Rect(-80, 90, 80, 150))
    assert points == [(0, 30), (0, 90)]


def test_route_is_orthogonal_and_ends_at_target():
    points = routing.route((0, 30), "bottom", (200, 190), "top", Rect(-80, -30, 80, 30), Rect(120, 190, 280, 250))
    assert _orthogonal(points)
    assert points[0] == (0, 30)
    assert points[-1] == (200, 190)
    # letztes Segment läuft von oben in den Zielanschluss
    assert points[-2][0] == 200 and points[-2][1] < 190


def test_back_edge_goes_around_elements():
    source = Rect(-80, 200, 80, 320)   # Verzweigung unten
    target = Rect(-80, 90, 80, 150)    # Vorgang oben
    points = routing.route((-80, 260), "left", (-80, 120), "left", source, target)
    assert _orthogonal(points)
    xs = [p[0] for p in points[1:-1]]
    assert min(xs) <= -80 - routing.STUB + 1e-6  # ausreichender Abstand
    for a, b in zip(points, points[1:]):
        assert not routing.segment_crosses_rect(a, b, source)
        assert not routing.segment_crosses_rect(a, b, target)


def test_route_avoids_obstacle():
    source = Rect(-80, -30, 80, 30)
    target = Rect(-80, 370, 80, 430)
    obstacle = Rect(-84, 150, 84, 250)
    points = routing.route((0, 30), "bottom", (0, 370), "top", source, target, [obstacle])
    assert _orthogonal(points)
    for a, b in zip(points, points[1:]):
        assert not routing.segment_crosses_rect(a, b, obstacle)


def test_manual_axis_is_respected():
    points = routing.route((0, 30), "bottom", (300, 190), "top", Rect(-80, -30, 80, 30), Rect(220, 190, 380, 250),
                           manual={"mode": "manual", "axis": "y", "value": 100})
    assert any(abs(p[1] - 100) < 1e-6 for p in points)


def test_free_end_route():
    points = routing.route((0, 30), "bottom", (120, 200), None, Rect(-80, -30, 80, 30))
    assert points[0] == (0, 30) and points[-1] == (120, 200)
    assert _orthogonal(points)
