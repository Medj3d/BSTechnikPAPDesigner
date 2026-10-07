"""Automatisches Anordnen eines Programmablaufplans.

Grundlage ist der Strukturbaum (``app.analysis.structure``). Jede Struktur
wird nach den üblichen PAP-Konventionen angeordnet:

* Folge: untereinander in einer Spalte
* Verzweigung: „ja“-Zweig gerade nach unten, „nein“-Zweig in einer Spalte
  rechts daneben; danach geht es unter dem längeren Zweig weiter
* Schleifen: Kopf, Rumpf und Fuß untereinander, links etwas Platz für den
  Rücksprung
* mehrere Abläufe (mehrere Start-Elemente) nebeneinander

Kommentare wandern mit dem Baustein, dem sie zugeordnet sind;
Verbindungspunkte werden zwischen ihre beiden Stammteile gesetzt. Nicht
erreichbare Bausteine werden rechts neben den angeordneten Bereich gesetzt.
Die Positionen werden nur berechnet (``plan_auto_layout``); ``apply_layout``
wendet sie als ein einziger Rückgängig-Schritt an.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.analysis.ast import (Action, Block, Break, Continue, DoWhileLoop, EndStmt, If, LimitLoop, Loop,
                              Unstructured, WhileLoop)
from app.analysis.graph import FlowGraph
from app.analysis.structure import structure_diagram
from app.model.element_types import PORT_DIRECTIONS, TRUNK_IN_KEY, TRUNK_OUT_KEY

V_GAP = 60.0          # Abstand zwischen Unterkante und Oberkante
H_GAP = 80.0          # Abstand zwischen Spalten
LOOP_MARGIN = 40.0    # Platz für Rücksprunglinien
PROGRAM_GAP = 160.0
UNPLACED_GAP = 160.0


@dataclass
class LayoutPlan:
    moves: dict = field(default_factory=dict)          # id → ((alt_x, alt_y), (neu_x, neu_y))
    reset_routing: list = field(default_factory=list)  # Verbindungen mit manueller Linienführung

    def is_empty(self) -> bool:
        return not self.moves and not self.reset_routing


@dataclass
class _Box:
    """Angeordneter Teilbaum relativ zu seiner Spaltenachse (x = 0) und Oberkante (y = 0)."""
    positions: dict = field(default_factory=dict)   # id → (x, y) Mittelpunkt
    left: float = 0.0     # Ausdehnung links der Achse
    right: float = 0.0    # Ausdehnung rechts der Achse
    height: float = 0.0

    def place(self, other: "_Box", dx: float, dy: float) -> None:
        for eid, (x, y) in other.positions.items():
            self.positions.setdefault(eid, (x + dx, y + dy))
        self.left = max(self.left, other.left - dx)
        self.right = max(self.right, other.right + dx)


def _snap(value: float, grid: int) -> float:
    return math.floor(value / grid + 0.5) * grid if grid > 0 else value


def _element_ids(stmt) -> set[str]:
    """Bausteine, die eine Anweisung (samt Inhalt) im Plan belegt."""
    if isinstance(stmt, (Break, Continue)):
        return set()
    if isinstance(stmt, Unstructured):
        return set() if stmt.fatal else set(stmt.element_ids)
    ids = set()
    if isinstance(stmt, LimitLoop):
        ids.add(stmt.begin_id)
        if stmt.end_id:
            ids.add(stmt.end_id)
    elif getattr(stmt, "element_id", None):
        ids.add(stmt.element_id)
    for name in ("then_block", "else_block", "body"):
        for child in getattr(stmt, name, None) or []:
            ids |= _element_ids(child)
    return ids


def _primary_ids(block: Block) -> set[str]:
    """Bausteine, die der Strukturbaum an ihrer eigentlichen Stelle enthält (ohne Wiederholungen)."""
    ids = set()
    for stmt in block:
        if getattr(stmt, "repeated", False):
            continue
        if isinstance(stmt, LimitLoop):
            ids.add(stmt.begin_id)
            if stmt.end_id:
                ids.add(stmt.end_id)
        elif isinstance(stmt, Unstructured):
            ids |= _element_ids(stmt)
        elif getattr(stmt, "element_id", None) and not isinstance(stmt, (Break, Continue)):
            ids.add(stmt.element_id)
        for name in ("then_block", "else_block", "body"):
            child = getattr(stmt, name, None)
            if child is not None:
                ids |= _primary_ids(child)
    return ids


class _Layouter:
    def __init__(self, sizes: dict[str, tuple[float, float]], extras: dict | None = None,
                 primary: set | None = None):
        self.sizes = sizes
        self.extras = extras or {}       # Baustein → (links, rechts, unten) für angehängte Kommentare
        self.known = set(primary or ())  # Bausteine, die an ihrer eigentlichen Stelle angeordnet werden

    def size(self, eid: str) -> tuple[float, float]:
        return self.sizes.get(eid, (160.0, 60.0))

    def element(self, eid: str) -> _Box:
        w, h = self.size(eid)
        left, right, bottom = self.extras.get(eid, (0.0, 0.0, 0.0))
        # angehängte Kommentare brauchen Platz neben (und unter) ihrem Baustein
        return _Box({eid: (0.0, h / 2)}, max(w / 2, left), max(w / 2, right), max(h, bottom))

    def sequence(self, parts: list[_Box]) -> _Box:
        box = _Box()
        y = 0.0
        for index, part in enumerate(parts):
            if index:
                y += V_GAP
            box.place(part, 0.0, y)
            y += part.height
        box.height = y
        return box

    def block(self, block: Block) -> _Box:
        return self.sequence([b for b in (self.stmt(s) for s in block) if b is not None])

    def stmt(self, stmt) -> _Box | None:
        if getattr(stmt, "repeated", False):
            ids = _element_ids(stmt)
            if ids <= self.known:
                return None  # Wiederholung von Bausteinen, die schon an anderer Stelle stehen
            self.known |= ids  # kommt nur in einer Wiederholung vor: hier anordnen
        if isinstance(stmt, Action):
            return self.element(stmt.element_id)
        if isinstance(stmt, EndStmt):
            return self.element(stmt.element_id)
        if isinstance(stmt, If):
            return self.if_box(stmt)
        if isinstance(stmt, WhileLoop):
            head = self.element(stmt.element_id)
            box = self.sequence([head, self.block(stmt.body)] if len(stmt.body) else [head])
            # Ausgang nach rechts: dort ebenfalls Platz für die Linie
            box.left += LOOP_MARGIN
            box.right += LOOP_MARGIN
            return box
        if isinstance(stmt, DoWhileLoop):
            parts = [self.block(stmt.body)] if len(stmt.body) else []
            box = self.sequence(parts + [self.element(stmt.element_id)])
            box.left += LOOP_MARGIN
            return box
        if isinstance(stmt, Loop):
            box = self.block(stmt.body)
            box.left += LOOP_MARGIN
            return box
        if isinstance(stmt, LimitLoop):
            parts = [self.element(stmt.begin_id)]
            if len(stmt.body):
                parts.append(self.block(stmt.body))
            if stmt.end_id:
                parts.append(self.element(stmt.end_id))
            return self.sequence(parts)
        if isinstance(stmt, Unstructured):
            if stmt.fatal:
                return None  # ein Sprung: sein Ziel steht an anderer Stelle
            parts = [self.element(eid) for eid in stmt.element_ids]
            return self.sequence(parts) if parts else None
        return None

    def if_box(self, stmt: If) -> _Box:
        """Verzweigung: erster Zweig gerade nach unten, die übrigen als Spalten rechts daneben.

        Eine Mehrfachverzweigung kommt als Kette verschachtelter Wenn-Folgen
        desselben Bausteins an; ihre Zweige stehen nebeneinander in einer Reihe.
        """
        branches = [stmt.then_block]
        current = stmt
        while len(current.else_block) == 1:
            inner = current.else_block.statements[0]
            if not isinstance(inner, If) or inner.element_id != stmt.element_id or inner.repeated:
                break
            current = inner
            branches.append(current.then_block)
        branches.append(current.else_block)
        head = self.element(stmt.element_id)
        boxes = [self.block(branch) for branch in branches]
        box = _Box()
        box.place(head, 0.0, 0.0)
        y0 = head.height + V_GAP
        column_right = head.right
        placed_right = False
        for index, branch in enumerate(boxes):
            if not branch.positions:
                continue
            if index == 0:
                box.place(branch, 0.0, y0)
                column_right = max(column_right, branch.right)
            else:
                dx = column_right + H_GAP + branch.left
                box.place(branch, dx, y0)
                column_right = dx + branch.right
                placed_right = True
        if not placed_right:
            # Platz für den „nein“-Weg rechts um den Ja-Zweig herum
            box.right = max(box.right, column_right + LOOP_MARGIN)
        branch_height = max((branch.height for branch in boxes if branch.positions), default=0.0)
        box.height = head.height + (V_GAP + branch_height if branch_height else 0.0)
        return box


def plan_auto_layout(scene, only_ids: set | None = None) -> LayoutPlan:
    """Berechnet eine übersichtliche Anordnung aller Bausteine."""
    items = {item.element_id: item for item in scene.elements()}
    if not items:
        return LayoutPlan()
    grid = scene.grid_size
    sizes = {eid: (item.width, item.height) for eid, item in items.items()}
    graph = FlowGraph.from_scene(scene)
    try:
        programs = structure_diagram(graph)
    except Exception:
        programs = []
    primary = set()
    for program in programs:
        primary |= {program.start_id} | _primary_ids(program.body)
    layouter = _Layouter(sizes, _comment_extents(items), primary)

    placed: dict[str, tuple[float, float]] = {}
    x_cursor = None
    for program in programs:
        box = layouter.sequence([layouter.element(program.start_id), layouter.block(program.body)])
        if x_cursor is None:
            dx = 0.0
            x_cursor = box.right
        else:
            dx = x_cursor + PROGRAM_GAP + box.left
            x_cursor = dx + box.right
        for eid, (x, y) in box.positions.items():
            if eid in items and eid not in placed:
                placed[eid] = (x + dx, y)

    new_positions: dict[str, tuple[float, float]] = {}
    if placed:
        # Verankerung: das erste Start-Element bleibt, wo es ist
        anchor_id = programs[0].start_id
        ax, ay = items[anchor_id].pos().x(), items[anchor_id].pos().y()
        px, py = placed[anchor_id]
        ox, oy = _snap(ax - px, grid), _snap(ay - py, grid)
        for eid, (x, y) in placed.items():
            new_positions[eid] = (_snap(x + ox, grid), _snap(y + oy, grid))

    _place_unplaced_flow(items, new_positions, grid)
    _place_junctions(scene, items, new_positions, grid)
    _place_comments(scene, items, new_positions)

    plan = LayoutPlan()
    for eid, (nx, ny) in new_positions.items():
        if only_ids is not None and eid not in only_ids:
            continue
        item = items[eid]
        old = (item.pos().x(), item.pos().y())
        if abs(old[0] - nx) > 1e-6 or abs(old[1] - ny) > 1e-6:
            plan.moves[eid] = (old, (nx, ny))
    moved = set(plan.moves)
    for conn in scene.connections():
        if conn.has_manual_routing() and (conn.data.source_id in moved or conn.data.target_id in moved):
            plan.reset_routing.append(conn.connection_id)
    return plan


def _rect(item, pos) -> tuple[float, float, float, float]:
    x, y = pos
    return x - item.width / 2, y - item.height / 2, x + item.width / 2, y + item.height / 2


def _place_unplaced_flow(items: dict, positions: dict, grid: int) -> None:
    """Nicht erreichte Ablaufbausteine rechts neben den angeordneten Bereich setzen."""
    rest = [item for eid, item in items.items()
            if eid not in positions and not item.is_comment and not item.is_junction]
    if not rest or not positions:
        return
    right = max(_rect(items[eid], pos)[2] for eid, pos in positions.items())
    top = min(_rect(items[eid], pos)[1] for eid, pos in positions.items())
    min_left = min(item.pos().x() - item.width / 2 for item in rest)
    min_top = min(item.pos().y() - item.height / 2 for item in rest)
    dx = _snap(right + UNPLACED_GAP - min_left, grid)
    dy = _snap(top - min_top, grid)
    for item in rest:
        positions[item.element_id] = (_snap(item.pos().x() + dx, grid), _snap(item.pos().y() + dy, grid))


def _place_junctions(scene, items: dict, positions: dict, grid: int) -> None:
    """Verbindungspunkte in die Mitte zwischen ihre beiden Stammteile setzen."""
    for item in items.values():
        if not item.is_junction:
            continue
        trunk_in = scene.connection(item.data.properties.get(TRUNK_IN_KEY, ""))
        trunk_out = scene.connection(item.data.properties.get(TRUNK_OUT_KEY, ""))
        if trunk_in is None or trunk_out is None:
            _place_merge_point(item, positions, grid)
            continue
        a, b = trunk_in.source, trunk_out.target
        if a.element_id not in positions and b.element_id not in positions:
            continue

        def port_point(node, port):
            x, y = positions.get(node.element_id, (node.pos().x(), node.pos().y()))
            local = node.port_local_pos(port)
            return x + local.x(), y + local.y()

        ax, ay = port_point(a, trunk_in.data.source_port)
        bx, by = port_point(b, trunk_out.data.target_port)
        positions[item.element_id] = (_snap((ax + bx) / 2, grid), _snap((ay + by) / 2, grid))


def _place_merge_point(item, positions: dict, grid: int) -> None:
    """Zusammenführungspunkt ohne Stamm (z. B. aus PapDesigner): kurz vor seinen Nachfolger setzen."""
    outgoing = [c for c in item.connections if c.source is item and not c.is_annotation]
    if len(outgoing) != 1:
        return
    target = outgoing[0].target
    if target.element_id not in positions:
        return
    x, y = positions[target.element_id]
    local = target.port_local_pos(outgoing[0].data.target_port)
    dx, dy = PORT_DIRECTIONS.get(outgoing[0].data.target_port, (0.0, -1.0))
    distance = V_GAP / 2
    positions[item.element_id] = (_snap(x + local.x() + dx * distance, grid),
                                  _snap(y + local.y() + dy * distance, grid))


def _comment_partner(item):
    for conn in item.connections:
        other = conn.target if conn.source is item else conn.source
        if not other.is_comment:
            return other
    return None


def _comment_extents(items: dict) -> dict:
    """Platz, den angehängte Kommentare links, rechts und unter ihrem Baustein brauchen."""
    extents: dict[str, tuple[float, float, float]] = {}
    for item in items.values():
        if not item.is_comment:
            continue
        partner = _comment_partner(item)
        if partner is None:
            continue
        dx, dy = item.pos().x() - partner.pos().x(), item.pos().y() - partner.pos().y()
        left, right, bottom = extents.get(partner.element_id, (0.0, 0.0, 0.0))
        extents[partner.element_id] = (max(left, item.width / 2 - dx), max(right, dx + item.width / 2),
                                       max(bottom, partner.height / 2 + dy + item.height / 2))
    return extents


def _place_comments(scene, items: dict, positions: dict) -> None:
    """Kommentare behalten ihren Abstand zum zugeordneten Baustein."""
    for item in items.values():
        if not item.is_comment:
            continue
        partner = _comment_partner(item)
        if partner is None or partner.element_id not in positions:
            continue
        nx, ny = positions[partner.element_id]
        dx, dy = nx - partner.pos().x(), ny - partner.pos().y()
        positions[item.element_id] = (item.pos().x() + dx, item.pos().y() + dy)


def apply_layout(scene, plan: LayoutPlan, text: str = "Automatisch anordnen") -> bool:
    """Wendet eine Anordnung als ein Rückgängig-Schritt an."""
    from app.commands import MoveItemsCommand, SetRoutingCommand

    if plan.is_empty():
        return False
    scene.prepare_for_command()
    stack = scene.undo_stack
    stack.beginMacro(text)
    for connection_id in plan.reset_routing:
        conn = scene.connection(connection_id)
        if conn is not None and conn.has_manual_routing():
            stack.push(SetRoutingCommand(scene, connection_id, conn.data.routing, {"mode": "auto"}))
    if plan.moves:
        stack.push(MoveItemsCommand(scene, plan.moves, text=text))
    stack.endMacro()
    # nach dem Verschieben alle Linien sauber neu führen
    with scene.batch_routing():
        for conn in scene.connections():
            scene._schedule_route(conn, force=True)
    return True
