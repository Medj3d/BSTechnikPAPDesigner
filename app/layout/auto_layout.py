"""Automatisches Anordnen eines Programmablaufplans.

Grundlage ist der Strukturbaum (``app.analysis.structure``). Jede Struktur
wird nach den üblichen PAP-Konventionen angeordnet:

* Folge: untereinander in einer Spalte
* Verzweigung: „ja“-Zweig gerade nach unten, „nein“-Zweig in einer Spalte
  rechts daneben; danach geht es unter dem längeren Zweig weiter
* Schleifen: Kopf, Rumpf und Fuß untereinander, links etwas Platz für den
  Rücksprung
* mehrere Abläufe (mehrere Start-Elemente) nebeneinander

Kommentare wandern mit dem Baustein, dem sie zugeordnet sind (ohne Kommentarlinie
mit dem nächstgelegenen). Nicht erreichbare Bausteine werden rechts neben den
angeordneten Bereich gesetzt.

Nach dem Platzieren werden die Verbindungen aufgeräumt: Reine Eckpunkte (ein
Pfeil hinein, einer heraus – im PapDesigner ist jede Ecke einer) fallen weg,
Zusammenführungen stehen in einer eigenen Zeile kurz über ihrem Ziel, und die
Anschlüsse passen zur neuen Lage. Der Ablauf bleibt dabei derselbe.

Alles wird nur berechnet (``plan_auto_layout``); ``apply_layout`` wendet es als
ein einziger Rückgängig-Schritt an.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.analysis.ast import (Action, Block, Break, Continue, DoWhileLoop, EndStmt, If, LimitLoop, Loop,
                              Unstructured, WhileLoop)
from app.analysis.graph import Edge, FlowGraph, edge_order
from app.analysis.structure import structure_diagram
from app.i18n import tr
from app.model.diagram import ConnectionData, new_id
from app.model.element_types import (LOOSE_END_KEY, PORT_BOTTOM, PORT_LEFT, PORT_RIGHT, PORT_TOP, TRUNK_IN_KEY,
                                     TRUNK_OUT_KEY, ElementType)

V_GAP = 60.0          # Abstand zwischen Unterkante und Oberkante
H_GAP = 80.0          # Abstand zwischen Spalten
LOOP_MARGIN = 60.0    # Platz für Rücksprunglinien
MERGE_ROW = 30.0      # zusätzliche Zeile unter einer Verzweigung für die Zusammenführung
MERGE_GAP = 30.0      # Abstand einer Zusammenführung zu ihrem Ziel
PROGRAM_GAP = 160.0
UNPLACED_GAP = 160.0
COMMENT_REACH = 240.0  # bis zu diesem Abstand gehört ein Kommentar ohne Linie zum nächsten Baustein
COMMENT_SPACE = 20.0   # Mindestabstand eines Kommentars zu seinem Baustein


@dataclass
class LayoutPlan:
    moves: dict = field(default_factory=dict)          # id → ((alt_x, alt_y), (neu_x, neu_y))
    reset_routing: list = field(default_factory=list)  # Verbindungen mit manueller Linienführung
    ports: dict = field(default_factory=dict)          # id → ((alt_quelle, alt_ziel), (neu_quelle, neu_ziel))
    removed_corners: list = field(default_factory=list)  # reine Eckpunkte, die wegfallen
    bridges: list = field(default_factory=list)        # Verbindungen, die stattdessen direkt laufen
    trunks: list = field(default_factory=list)         # (Verbindungspunkt, Schlüssel, alt, neu) der Stammverweise

    def is_empty(self) -> bool:
        return not (self.moves or self.reset_routing or self.ports or self.removed_corners)


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
        box.height = head.height + (V_GAP + branch_height if branch_height else 0.0) + MERGE_ROW
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
    partners = _comment_partners(items)
    layouter = _Layouter(sizes, _comment_extents(items, partners), primary)

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
    plan = LayoutPlan()
    edges = _final_edges(scene, items, plan) if only_ids is None else _current_edges(scene)
    _place_merges(items, new_positions, edges, grid)
    if only_ids is None:
        _plan_ports(items, new_positions, edges, plan)
    _place_comments(items, new_positions, partners)

    for eid, (nx, ny) in new_positions.items():
        if (only_ids is not None and eid not in only_ids) or eid in plan.removed_corners:
            continue
        item = items[eid]
        old = (item.pos().x(), item.pos().y())
        if abs(old[0] - nx) > 1e-6 or abs(old[1] - ny) > 1e-6:
            plan.moves[eid] = (old, (nx, ny))
    moved = set(plan.moves)
    for conn in scene.connections():
        if conn.has_manual_routing() and (conn.data.source_id in moved or conn.data.target_id in moved
                                          or conn.connection_id in plan.ports):
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


@dataclass
class _Edge:
    """Verbindung, wie sie nach dem Aufräumen läuft."""
    source: str
    target: str
    ports: tuple
    connection_id: str
    label: str = ""
    data: ConnectionData | None = None  # gesetzt: Verbindung, die anstelle reiner Eckpunkte neu entsteht


def _current_edges(scene) -> list:
    return [_Edge(c.data.source_id, c.data.target_id, (c.data.source_port, c.data.target_port), c.connection_id,
                  c.data.label) for c in scene.ordered_connections() if not c.is_annotation]


def _is_pass_through(item) -> bool:
    """Ein Verbindungspunkt mit genau einem Pfeil heraus: Er ist eine Ecke oder führt Pfeile zusammen."""
    if not item.is_junction or item.data.properties.get(LOOSE_END_KEY):
        return False
    if any(c.is_annotation for c in item.connections):
        return False
    outgoing = [c for c in item.connections if c.source is item]
    return len(outgoing) == 1 and outgoing[0].target is not item


def _final_edges(scene, items: dict, plan: LayoutPlan) -> list:
    """Verbindungen nach dem Aufräumen; was sich ändert, steht danach in ``plan``.

    Verbindungspunkte, die auf denselben Baustein zulaufen, werden zu einem einzigen: Ein Plan aus dem PapDesigner
    hat oft ganze Ketten davon. Führt in eine solche Gruppe nur ein Pfeil, ist sie bloß eine Ecke und fällt ganz weg.
    """
    passing = {eid for eid, item in items.items() if _is_pass_through(item)}
    next_of = {eid: next(c for c in items[eid].connections if c.source is items[eid]) for eid in passing}

    def terminal(element_id: str) -> str | None:
        seen = set()
        while element_id in passing:
            if element_id in seen:
                return None  # ein Ring aus Verbindungspunkten bleibt, wie er ist
            seen.add(element_id)
            element_id = next_of[element_id].data.target_id
        return element_id

    groups: dict = {}
    for eid in passing:
        end = terminal(eid)
        if end is not None:
            groups.setdefault(end, []).append(eid)
    grouped = {eid for members in groups.values() for eid in members}
    keep: dict = {}          # Gruppe → verbleibender Verbindungspunkt
    entering: dict = {}
    for conn in scene.ordered_connections():
        if not conn.is_annotation and conn.data.target_id in grouped and conn.data.source_id not in grouped:
            entering.setdefault(terminal(conn.data.target_id), []).append(conn)
    for end, members in groups.items():
        if len(entering.get(end, [])) >= 2:
            # der Punkt direkt vor dem Ziel bleibt (bei mehreren der erste in Dateireihenfolge)
            keep[end] = next(eid for eid in sorted(members, key=list(items).index)
                             if next_of[eid].data.target_id == end)

    edges = []
    removed = grouped - set(keep.values())
    replaced: dict = {}      # Verbindung, die wegfällt → Verbindung, die an ihre Stelle tritt
    for conn in scene.ordered_connections():
        data = conn.data
        if conn.is_annotation:
            continue
        if data.source_id in removed:
            continue
        ports = (data.source_port, data.target_port)
        if data.target_id not in removed:
            edges.append(_Edge(data.source_id, data.target_id, ports, conn.connection_id, data.label))
            continue
        end = terminal(data.target_id)
        target = keep.get(end, end)
        label, last = data.label, conn
        while last.data.target_id != target and last.data.target_id in grouped:
            last = next_of[last.data.target_id]
            label = label or last.data.label
            replaced[last.connection_id] = conn.connection_id
        # Die neue Verbindung trägt die ID der ersten: Die Reihenfolge der Ausgänge hängt auch an der ID
        bridge = ConnectionData(conn.connection_id, data.source_id, target, data.source_port, last.data.target_port,
                                label)
        if bridge.source_id == bridge.target_id and bridge.source_port == bridge.target_port:
            # eine Linie von einem Anschluss zu demselben hätte keine Länge
            bridge.target_port = next(p for p in items[target].ports if p != bridge.source_port)
        scene.keep_order(conn, bridge.id)
        plan.bridges.append(bridge)
        edges.append(_Edge(bridge.source_id, bridge.target_id, (bridge.source_port, bridge.target_port),
                           bridge.id, label, bridge))
    plan.removed_corners = sorted(removed)
    for eid, item in items.items():
        if item.is_junction and eid not in removed:
            for key in (TRUNK_IN_KEY, TRUNK_OUT_KEY):
                old = item.data.properties.get(key)
                if old in replaced:
                    plan.trunks.append((eid, key, old, replaced[old]))
    return edges


def _top_of(items: dict, positions: dict, element_id: str) -> tuple[float, float]:
    """Mitte der Oberkante eines Elements an seiner neuen Stelle."""
    item = items[element_id]
    x, y = positions.get(element_id, (item.pos().x(), item.pos().y()))
    return x, y - item.height / 2


def _place_merges(items: dict, positions: dict, edges: list, grid: int) -> None:
    """Zusammenführungen kommen in die Zeile über ihrem Ziel, von unten nach oben."""
    junctions = {eid for eid, item in items.items() if item.is_junction and not item.data.properties.get(LOOSE_END_KEY)}
    junctions &= {edge.source for edge in edges} | {edge.target for edge in edges}
    targets: dict = {}
    for edge in edges:
        if edge.source in junctions:
            targets.setdefault(edge.source, edge.target)
    waiting = {eid for eid in junctions if eid in targets}
    taken = set()
    step = max(float(grid), 20.0)
    while waiting:
        ready = [eid for eid in waiting if targets[eid] not in waiting]
        if not ready:
            break  # ein Ring aus Verbindungspunkten: Die übrigen bleiben an ihrem Platz
        for eid in ready:
            waiting.discard(eid)
            target = targets[eid]
            if target not in positions and not items[target].is_junction:
                continue
            x, top = _top_of(items, positions, target)
            y = _snap(top - MERGE_GAP, grid)
            while top - y < step / 2 or (x, y) in taken:
                y -= step
            taken.add((x, y))
            positions[eid] = (_snap(x, grid), y)


def _side_toward(x: float, other_x: float) -> str:
    return PORT_RIGHT if other_x >= x else PORT_LEFT


def _plan_ports(items: dict, positions: dict, edges: list, plan: LayoutPlan) -> None:
    """Wählt Anschlüsse passend zur neuen Lage: gerade Wege nach unten, Seitenzweige nach rechts, Rücksprünge links."""
    current = {edge.connection_id: edge.ports for edge in edges}

    def exit_order(group: list, ports_of) -> list:
        return [e.id for e in sorted((Edge(edge.connection_id, edge.source, edge.target, edge.label, ports_of(edge)[0],
                                           ports_of(edge)[1]) for edge in group), key=edge_order)]

    def center(element_id: str) -> tuple[float, float]:
        item = items[element_id]
        return positions.get(element_id, (item.pos().x(), item.pos().y()))

    outgoing: dict = {}
    for edge in edges:
        if edge.source != edge.target:
            outgoing.setdefault(edge.source, []).append(edge)
    used_out: dict = {}
    for source_id, group in outgoing.items():
        source = items[source_id]
        sx, sy = center(source_id)
        bottom = sy + source.height / 2
        taken: set = set()
        used_out[source_id] = taken
        branching = source.element_type is ElementType.DECISION or len(group) > 1
        group = sorted(group, key=lambda e: abs(center(e.target)[0] - sx))
        for edge in group:
            tx, ty = center(edge.target)
            forward = ty - items[edge.target].height / 2 >= bottom - 1
            if forward and abs(tx - sx) < 1 and PORT_BOTTOM not in taken:
                port = PORT_BOTTOM
            elif abs(ty - sy) < 1:
                port = _side_toward(sx, tx)
            elif forward and not branching:
                port = PORT_BOTTOM
            elif forward:
                port = _side_toward(sx, tx)
            elif branching:
                port = _side_toward(sx, tx) if abs(tx - sx) >= 1 else PORT_LEFT
            else:
                port = PORT_BOTTOM
            if port in taken:
                port = next((p for p in (PORT_RIGHT, PORT_LEFT, PORT_BOTTOM) if p not in taken), port)
            taken.add(port)
            edge.ports = (port if port in source.ports else edge.ports[0], edge.ports[1])
        # Die Reihenfolge der Ausgänge gehört zum Ablauf: Würde sie sich ändern, bleiben die Anschlüsse
        if exit_order(group, lambda e: e.ports) != exit_order(group, lambda e: current[e.connection_id]):
            for edge in group:
                edge.ports = current[edge.connection_id]
            used_out[source_id] = {edge.ports[0] for edge in group}

    for edge in edges:
        if edge.source == edge.target:
            continue
        target = items[edge.target]
        sx, sy = center(edge.source)
        tx, ty = center(edge.target)
        bottom = sy + items[edge.source].height / 2
        forward = ty - target.height / 2 >= bottom - 1
        free_sides = [p for p in (PORT_LEFT, PORT_RIGHT) if p not in used_out.get(edge.target, ())]
        if abs(ty - sy) < 1:
            port = _side_toward(tx, sx)
        elif forward and abs(tx - sx) < 1:
            port = PORT_TOP if edge.ports[0] == PORT_BOTTOM else edge.ports[0]
        elif forward and edge.ports[0] == PORT_BOTTOM:
            port = _side_toward(tx, sx)
        elif forward:
            port = PORT_TOP
        else:
            port = _side_toward(tx, sx) if abs(tx - sx) >= 1 else PORT_LEFT
        if port not in target.ports or (port in (PORT_LEFT, PORT_RIGHT) and port not in free_sides):
            port = PORT_TOP if forward and PORT_TOP in target.ports else (free_sides or [edge.ports[1]])[0]
        edge.ports = (edge.ports[0], port if port in target.ports else edge.ports[1])

    for edge in edges:
        if edge.data is not None:
            edge.data.source_port, edge.data.target_port = edge.ports
        else:
            old = current[edge.connection_id]
            if old != edge.ports:
                plan.ports[edge.connection_id] = (old, edge.ports)


def _rect_gap(a, b) -> float:
    """Abstand der Rechtecke zweier Bausteine (0, wenn sie sich berühren)."""
    ax, ay, bx, by = a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y()
    return max(abs(ax - bx) - (a.width + b.width) / 2, abs(ay - by) - (a.height + b.height) / 2, 0.0)


def _comment_partners(items: dict) -> dict:
    """Baustein je Kommentar: der per Kommentarlinie verbundene, sonst der nächstgelegene."""
    blocks = [item for item in items.values() if not item.is_comment and not item.is_junction]
    partners = {}
    for item in items.values():
        if not item.is_comment:
            continue
        partner = next((other for conn in item.connections
                        for other in (conn.target if conn.source is item else conn.source,)
                        if not other.is_comment), None)
        if partner is None and blocks:
            nearest = min(blocks, key=lambda block: _rect_gap(item, block))
            partner = nearest if _rect_gap(item, nearest) <= COMMENT_REACH else None
        if partner is not None:
            partners[item.element_id] = partner
    return partners


def _comment_offset(item, partner) -> tuple[float, float]:
    """Lage des Kommentars zu seinem Baustein; überdeckt er ihn, rückt er auf seiner Seite daneben."""
    dx, dy = item.pos().x() - partner.pos().x(), item.pos().y() - partner.pos().y()
    beside = (item.width + partner.width) / 2 + COMMENT_SPACE
    if abs(dx) < beside and abs(dy) < (item.height + partner.height) / 2:
        dx = beside if dx >= 0 else -beside
    return dx, dy


def _comment_extents(items: dict, partners: dict) -> dict:
    """Platz, den angehängte Kommentare links, rechts und unter ihrem Baustein brauchen."""
    extents: dict[str, tuple[float, float, float]] = {}
    for item in items.values():
        partner = partners.get(item.element_id)
        if partner is None:
            continue
        dx, dy = _comment_offset(item, partner)
        left, right, bottom = extents.get(partner.element_id, (0.0, 0.0, 0.0))
        extents[partner.element_id] = (max(left, item.width / 2 - dx), max(right, dx + item.width / 2),
                                       max(bottom, partner.height / 2 + dy + item.height / 2))
    return extents


def _place_comments(items: dict, positions: dict, partners: dict) -> None:
    """Kommentare behalten ihren Abstand zum zugeordneten Baustein."""
    for item in items.values():
        partner = partners.get(item.element_id)
        if partner is None or partner.element_id not in positions:
            continue
        nx, ny = positions[partner.element_id]
        dx, dy = _comment_offset(item, partner)
        positions[item.element_id] = (nx + dx, ny + dy)


def apply_layout(scene, plan: LayoutPlan, text: str | None = None) -> bool:
    """Wendet eine Anordnung als ein Rückgängig-Schritt an.

    ``text``: Beschriftung des Rückgängig-Schritts (schon übersetzt); ohne Angabe „Automatisch anordnen“.
    """
    from app.commands import (AddElementsCommand, DeleteCommand, MoveItemsCommand, SetElementPropertyCommand,
                              SetPortsCommand, SetRoutingCommand)

    if plan.is_empty():
        return False
    if text is None:
        text = tr("Automatisch anordnen")
    scene.prepare_for_command()
    stack = scene.undo_stack
    stack.beginMacro(text)
    for connection_id in plan.reset_routing:
        conn = scene.connection(connection_id)
        if conn is not None and conn.has_manual_routing():
            stack.push(SetRoutingCommand(scene, connection_id, conn.data.routing, {"mode": "auto"}))
    if plan.removed_corners:
        stack.push(DeleteCommand(scene, plan.removed_corners, [], text=text))
        stack.push(AddElementsCommand(scene, [], plan.bridges, text=text, select=False))
        for element_id, key, old, new in plan.trunks:
            stack.push(SetElementPropertyCommand(scene, element_id, key, old, new, text=text))
    if plan.ports:
        stack.push(SetPortsCommand(scene, plan.ports, text=text))
    if plan.moves:
        stack.push(MoveItemsCommand(scene, plan.moves, text=text))
    stack.endMacro()
    # Nach dem Verschieben alle Linien sauber neu führen; im zweiten Durchgang sehen sie einander an ihrem neuen Platz
    for _round in range(2):
        with scene.batch_routing():
            for conn in scene.ordered_connections():
                scene._schedule_route(conn, force=True)
    return True
