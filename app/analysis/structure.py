"""Strukturierung: Ablaufgraph → Strukturbaum.

Der Algorithmus läuft vom Start-Element aus durch den Graphen und erkennt
die klassischen Kontrollstrukturen:

* **Folge** – Bausteine mit genau einem Nachfolger
* **Verzweigung** – Die Zweige laufen an dem Baustein wieder zusammen, durch
  den *jeder* Weg von der Verzweigung zum Ende führt (nächster
  Nachdominator). Mündet ein Zweig in einen Baustein, der schon in einem
  anderen Zweig steht, wird dieser Teil wiederholt (``repeated``).
* **kopfgesteuerte Schleife** – Verzweigung, von der ein Zweig zu ihr
  zurückführt. Springt der Rumpf vor die Prüfung zurück (Eingabe → Prüfung
  → Rumpf → zurück zur Eingabe), wird der Teil vor der Prüfung am Ende des
  Rumpfs wiederholt.
* **fußgesteuerte Schleife** – Rücksprung aus einer späteren Verzweigung
  zu einem früheren Baustein
* **Schleifenbegrenzung** – Schleifenbeginn … Schleifenende (DIN 66001)
* **allgemeine Schleife** – alles andere, was im Kreis läuft (z. B. ein
  Menü oder eine Suchschleife mit zwei Ausgängen): „wiederhole“ mit
  „nächster Durchlauf“ und „Schleife verlassen“

Was sich nicht strukturiert darstellen lässt (z. B. Sprünge über zwei
Schleifen hinweg), wird als ``Unstructured`` mit Hinweis ausgegeben; die
Analyse bricht nie mit einer Ausnahme ab und läuft nie endlos.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.analysis.ast import (Action, Block, Break, Continue, DoWhileLoop, EndStmt, If, LimitLoop, Loop,
                              Program, Unstructured, WhileLoop)
from app.analysis.graph import Edge, FlowGraph, has_yes_no_labels, yes_no_edges
from app.analysis.text import branch_condition, is_choice
from app.i18n import tr
from app.labels import no_label, yes_label
from app.model.element_types import ElementType, default_text_for

ACTION_KINDS = {
    ElementType.INPUT: "input",
    ElementType.OUTPUT: "output",
    ElementType.PROCESS: "process",
    ElementType.SUBPROGRAM: "subprogram",
    ElementType.JUNCTION: "junction",
}
MAX_DEPTH = 200
MAX_REPLAYS = 60
_EXIT = "\0exit"


def structure_diagram(graph: FlowGraph) -> list[Program]:
    """Strukturiert alle Abläufe (einer je Start-Element)."""
    graph = graph.collapse_junctions()
    return [_structure(graph, start.id) for start in graph.starts()]


def structure_program(graph: FlowGraph, start_id: str) -> Program:
    return _structure(graph.collapse_junctions(), start_id)


def _structure(graph: FlowGraph, start_id: str) -> Program:
    """Strukturiert einen Ablauf.

    Bleibt ein Sprung übrig, der sich nicht als kopf- oder fußgesteuerte
    Schleife darstellen lässt, wird die betroffene Schleife im nächsten
    Versuch als allgemeine Schleife („wiederhole“) aufgebaut.
    """
    loop_heads: set[str] = set()
    program = None
    for _ in range(len(graph.nodes) + 2):
        structurer = _Structurer(graph, loop_heads)
        program = structurer.program(start_id)
        new = [target for target in structurer.cycle_targets if target not in loop_heads]
        if not new:
            break
        loop_heads.add(new[0])  # einer nach dem anderen: oft erledigen sich die übrigen damit
    return program


def is_choice_decision(graph: FlowGraph, node_id: str) -> bool:
    """Wählt die Verzweigung über die Beschriftung ihrer Ausgänge („1“, „2“, „< 0“ …)?"""
    outs = graph.outgoing(node_id)
    if len(outs) > 2:
        return True
    return len(outs) == 2 and not has_yes_no_labels(outs) \
        and is_choice(graph.nodes[node_id].text, [edge.label for edge in outs])


@dataclass
class _OpenLoop:
    """Eine Schleife, deren Rumpf gerade aufgebaut wird."""
    exit: str | None          # Baustein hinter der Schleife: ein Sprung dorthin verlässt sie
    head: str | None = None   # Anfang einer allgemeinen Schleife: ein Sprung dorthin = nächster Durchlauf
    end: str | None = None    # wo der Rumpf regulär endet (Schleifenkopf, Fußprüfung, Schleifenende)
    convert: str | None = None  # Baustein, ab dem man sie als allgemeine Schleife neu aufbauen kann


class _Structurer:
    def __init__(self, graph: FlowGraph, loop_heads: set | frozenset = frozenset()):
        self.g = graph
        self.loop_heads = loop_heads          # Bausteine, an denen eine allgemeine Schleife beginnt
        self.cycle_targets: list[str] = []    # Schleifen, die als allgemeine Schleife neu aufzubauen sind
        self._entering: str | None = None
        self.emitted: set[str] = set()
        self.warnings: list[str] = []
        self.end_id: str | None = None
        self.end_text = ""
        self._dowhile_heads: set[str] = set()
        self._depth = 0
        self._loops: list[_OpenLoop] = []
        self._loop_ends: dict[str, str] = {}  # Schleifenbeginn → zugehöriges Schleifenende
        self._replaying: set[str] = set()
        self._replays = 0
        self._max_replays = max(MAX_REPLAYS, 2 * len(graph.nodes))
        self._ipdom = self._post_dominators()

    # ----------------------------------------------------------- Einstieg
    def program(self, start_id: str) -> Program:
        start = self.g.nodes[start_id]
        self.emitted.add(start_id)
        outs = self.g.outgoing(start_id)
        body = Block()
        name = start.text or default_text_for(ElementType.START)
        if outs:
            if len(outs) > 1:
                self.warn(tr("„{name}“ hat mehrere Ausgänge; nur der erste wird verwendet.", name=name))
            body, _ = self.block(outs[0].target, frozenset())
        else:
            self.warn(tr("„{name}“ ist mit keinem Baustein verbunden.", name=name))
        return Program(name, start_id, self.end_id, self.end_text, body, self.warnings)

    # ------------------------------------------------------------ Hilfen
    def node(self, nid: str):
        return self.g.nodes[nid]

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)

    def label(self, nid: str) -> str:
        node = self.node(nid)
        return " ".join(node.text.split()) or node.type.value

    def comments(self, nid: str) -> list[str]:
        return list(self.g.annotations.get(nid, []))

    def _open_heads(self) -> set[str]:
        """Anfänge der offenen allgemeinen Schleifen: Grenzen für alles, was in ihnen liegt."""
        return {loop.head for loop in self._loops if loop.head}

    def _rebuild_as_general_loop(self, head: str | None = None) -> None:
        """Merkt vor, die (innerste umwandelbare) Schleife beim nächsten Versuch allgemein aufzubauen."""
        if head is None:
            head = next((loop.convert for loop in reversed(self._loops) if loop.convert), None)
        if head is not None and head not in self.cycle_targets:
            self.cycle_targets.append(head)

    def _lost_jump(self, block: Block, target: str, convert: str | None = None) -> None:
        """Ein Zweig führt an eine Stelle, an der der Code nicht weitermachen kann."""
        block.statements.append(Unstructured(tr("Sprung zu „{name}“", name=self.label(target)), [target], fatal=True))
        self.warn(tr("Der Sprung zu „{name}“ lässt sich nicht als strukturiertes Programm darstellen.",
                     name=self.label(target)))
        self._rebuild_as_general_loop(convert)

    def reach(self, start: str, blocked: frozenset | set, expand_start: bool = False) -> dict[str, int]:
        """Erreichbare Knoten mit Abstand, ohne durch ``blocked`` hindurchzulaufen.

        Blockierte Knoten werden noch aufgenommen (als Endpunkt), aber nicht
        weiter verfolgt – auch nicht, wenn die Suche dort beginnt (außer mit
        ``expand_start``).
        """
        dist = {start: 0}
        if start in blocked and not expand_start:
            return dist
        queue = deque([start])
        while queue:
            current = queue.popleft()
            if current in blocked and current != start:
                continue
            for nxt in self.g.successors(current):
                if nxt not in dist:
                    dist[nxt] = dist[current] + 1
                    queue.append(nxt)
        return dist

    def _post_dominators(self) -> dict[str, str]:
        """Nächster Nachdominator je Knoten: der erste Baustein, durch den jeder Weg zum Ende führt."""
        nodes = list(self.g.nodes)
        succ = {}
        for nid in nodes:
            targets = self.g.successors(nid)
            succ[nid] = list(dict.fromkeys(targets)) if targets else [_EXIT]
            if self.g.nodes[nid].type is ElementType.END:
                succ[nid] = [_EXIT]
        # nur Knoten, von denen aus das Ende erreichbar ist (rückwärts vom Ende aus)
        pred: dict[str, list[str]] = {nid: [] for nid in nodes}
        pred[_EXIT] = []
        for nid in nodes:
            for target in succ[nid]:
                pred[target].append(nid)
        can_exit: set[str] = set()
        order: list[str] = []  # vom Ende her: Nachfolger möglichst vor ihren Vorgängern
        queue = deque([_EXIT])
        while queue:
            current = queue.popleft()
            for source in pred[current]:
                if source not in can_exit:
                    can_exit.add(source)
                    order.append(source)
                    queue.append(source)
        universe = can_exit | {_EXIT}
        pdom = {nid: set(universe) for nid in can_exit}
        pdom[_EXIT] = {_EXIT}
        changed = True
        while changed:
            changed = False
            for nid in order:
                followers = [pdom[s] for s in succ[nid] if s == _EXIT or s in can_exit]
                new = set.intersection(*followers) | {nid} if followers else {nid}
                if new != pdom[nid]:
                    pdom[nid] = new
                    changed = True
        result = {}
        for nid in can_exit:
            strict = pdom[nid] - {nid}
            size = len(strict)
            for candidate in strict:
                if candidate != _EXIT and len(pdom[candidate]) == size:
                    result[nid] = candidate  # der nächste: seine Nachdominatoren sind genau die übrigen
                    break
            else:
                result[nid] = _EXIT
        return result

    # ------------------------------------------------------------- Block
    def block(self, start: str | None, stop: frozenset, stop_at_loop_end: bool = False) -> tuple[Block, str | None]:
        """Baut eine Anweisungsfolge ab ``start`` bis zu einem Knoten in ``stop``.

        Gibt den Block und den Knoten zurück, an dem angehalten wurde
        (``None``: der Ablauf endet oder verlässt die Schleife).
        """
        self._depth += 1
        try:
            return self._block(start, stop, stop_at_loop_end)
        finally:
            self._depth -= 1

    def _block(self, start: str | None, stop: frozenset, stop_at_loop_end: bool) -> tuple[Block, str | None]:
        stmts: list = []
        cur = start
        while cur is not None:
            if self._entering == cur:
                self._entering = None  # der Anfang der allgemeinen Schleife selbst
            elif self._loops and cur == self._loops[-1].head:
                # zurück zum Anfang der innersten allgemeinen Schleife
                stmts.append(Continue(cur))
                return Block(stmts), None
            elif self._loops and cur == self._loops[-1].exit:
                # Sprung hinter die innerste Schleife
                stmts.append(Break(cur))
                return Block(stmts), None
            if cur in stop:
                return Block(stmts), cur
            node = self.node(cur)
            if stop_at_loop_end and node.is_loop_end:
                return Block(stmts), cur
            if self._depth > MAX_DEPTH:
                stmts.append(Unstructured(tr("Verschachtelung zu tief."), [cur], fatal=True))
                return Block(stmts), None
            if cur in self.emitted and node.type is not ElementType.END:
                if cur in self._replaying:
                    self._rebuild_as_general_loop(cur)  # echter Kreis: nächster Versuch mit allgemeiner Schleife
                replay = self._replay(cur, stop, stop_at_loop_end)
                if replay is None:
                    stmts.append(Unstructured(tr("Sprung zu „{name}“", name=self.label(cur)), [cur], fatal=True))
                    self.warn(tr("Der Ablauf springt zu „{name}“ zurück, ohne dass sich das als "
                                 "Schleife darstellen lässt.", name=self.label(cur)))
                    return Block(stmts), None
                block, stopped = replay
                stmts.extend(block.statements)
                return Block(stmts), stopped

            if node.type is ElementType.END:
                end_text = node.text or default_text_for(ElementType.END)
                stmts.append(EndStmt(end_text, cur))
                if self.end_id is None:
                    self.end_id, self.end_text = cur, end_text
                self.emitted.add(cur)
                return Block(stmts), None

            if node.type is ElementType.START:
                self.emitted.add(cur)
                cur = self._single_next(cur)
                continue

            open_heads = self._open_heads()
            if cur in self.loop_heads and cur not in open_heads:
                stmt, cur = self._general_loop(cur, stop)
                stmts.append(stmt)
                continue

            # fußgesteuerte Schleife: späterer Rücksprung zu diesem Baustein
            if cur not in self._dowhile_heads and cur not in open_heads:
                latch = self._find_latch(cur, stop)
                if latch is not None:
                    stmt, cur = self._do_while(cur, latch, stop)
                    stmts.append(stmt)
                    continue

            if node.is_loop_begin:
                stmt, cur = self._limit_loop(cur, stop)
                stmts.append(stmt)
                if cur is None and stmt.end_id is not None and not self.g.outgoing(stmt.end_id):
                    stmts.append(EndStmt("kein Nachfolger", stmt.end_id, repeated=True))
                continue

            if node.is_loop_end:
                # Schleifenende ohne passenden Beginn
                self.emitted.add(cur)
                stmts.append(Unstructured(tr("Schleifenende „{name}“ ohne Schleifenbeginn", name=node.text), [cur]))
                cur = self._single_next(cur)
                continue

            if node.type is ElementType.DECISION and len(self.g.outgoing(cur)) >= 2:
                stmt, cur = self._decision(cur, stop, stop_at_loop_end)
                stmts.append(stmt)
                continue

            if node.type is ElementType.DECISION and len(self.g.outgoing(cur)) == 1:
                stmt, cur = self._one_exit_decision(cur)
                stmts.append(stmt)
                continue

            # einfache Anweisung
            self.emitted.add(cur)
            kind = ACTION_KINDS.get(node.type, "process")
            stmts.append(Action(kind, node.text, cur, self.comments(cur)))
            nxt = self._single_next(cur)
            if nxt is None:
                # Sackgasse: Der Ablauf endet hier (wie im Schreibtischtest)
                stmts.append(EndStmt("kein Nachfolger", cur, repeated=True))
                return Block(stmts), None
            cur = nxt
        return Block(stmts), None

    def _replay(self, cur: str, stop: frozenset, stop_at_loop_end: bool):
        """Der Ablauf mündet in einen Baustein, der schon an anderer Stelle steht.

        Der Teil ab dort wird wiederholt – das ist immer gleichwertig, solange
        dabei kein Kreis entsteht (dann: ``None`` → nicht strukturierbar).
        """
        if cur in self._replaying or self._replays >= self._max_replays:
            return None
        self._replays += 1
        self._replaying.add(cur)
        saved = self.emitted
        self.emitted = saved - self.g.reachable_from(cur)
        try:
            block, stopped = self.block(cur, stop, stop_at_loop_end)
        finally:
            self.emitted = saved | self.emitted
            self._replaying.discard(cur)
        for stmt in block.statements:
            stmt.repeated = True
        return block, stopped

    def _single_next(self, nid: str) -> str | None:
        outs = self.g.outgoing(nid)
        if not outs:
            node = self.node(nid)
            if node.type is not ElementType.END:
                self.warn(tr("„{name}“ hat keinen Nachfolger.", name=node.text or node.type.value))
            return None
        if len(outs) > 1:
            node = self.node(nid)
            self.warn(tr("„{name}“ hat mehrere Ausgänge ohne Bedingung; nur der erste wird berücksichtigt.",
                         name=node.text or node.type.value))
        return outs[0].target

    # ------------------------------------------------------ Verzweigung
    def _branch(self, target: str, merge: str | None, stop: frozenset, stop_at_loop_end: bool):
        """Ein Zweig bis zur Zusammenführung: (Block, Knoten, an dem er anhält)."""
        if target == merge:
            return Block(), merge
        return self.block(target, stop, stop_at_loop_end)

    def _continuation(self, merge: str | None, branches: list) -> str | None:
        """Wo es nach der Verzweigung weitergeht.

        Hält ein Zweig an einer anderen Stelle an als die übrigen, kann der Code
        dort nicht einfach weiterlaufen: Der Zweig bekommt einen deutlichen
        Abbruch, und die umgebende Schleife wird als allgemeine Schleife neu versucht.
        """
        if merge is None:
            found = list(dict.fromkeys(stop for _, stop in branches if stop is not None))
            if not found:
                return None
            regular = self._loops[-1].end if self._loops else None
            merge = regular if regular in found else found[0]
        for block, stop in branches:
            if stop is not None and stop != merge:
                self._lost_jump(block, stop)
        return merge

    def _usable_merge(self, merge: str | None) -> str | None:
        """Der Baustein hinter einer offenen Schleife ist keine Zusammenführung:
        Jeder Zweig, der dorthin führt, verlässt die Schleife für sich."""
        if merge is not None and any(merge == loop.exit for loop in self._loops):
            return None
        return merge

    def _decision(self, cur: str, stop: frozenset, stop_at_loop_end: bool):
        node = self.node(cur)
        outs = self.g.outgoing(cur)
        open_heads = self._open_heads()
        blocked = stop | {cur} | open_heads
        choice = is_choice_decision(self.g, cur)

        # kopfgesteuerte Schleife: genau ein Zweig führt zurück zur Verzweigung
        loop_branches = [e for e in outs if e.target == cur or cur in self.reach(e.target, blocked)]
        exit_branches = [e for e in outs if e not in loop_branches]
        if cur not in open_heads and len(outs) == 2 and len(loop_branches) == 1 and len(exit_branches) == 1 \
                and not choice:
            loop_edge, exit_edge = loop_branches[0], exit_branches[0]
            self.emitted.add(cur)
            self._unlabelled_hint(cur, outs)
            if loop_edge.target == cur:
                body = Block()
            else:
                self._loops.append(_OpenLoop(exit_edge.target, end=cur, convert=cur))
                try:
                    body, stopped = self.block(loop_edge.target, stop | {cur})
                finally:
                    self._loops.pop()
                if stopped is not None and stopped != cur:
                    self._lost_jump(body, stopped, convert=cur)  # der Rumpf verlässt die Schleife woandershin
            negate = loop_edge is yes_no_edges(outs)[1]
            return WhileLoop(node.text, cur, body, negate, self.comments(cur)), exit_edge.target

        self.emitted.add(cur)
        if choice:
            return self._multi_branch(cur, outs, stop, stop_at_loop_end)

        self._unlabelled_hint(cur, outs)
        then_edge, else_edge = yes_no_edges(outs)
        merge = self._usable_merge(self._merge_point(cur, [then_edge.target, else_edge.target], blocked))
        inner_stop = stop | ({merge} if merge else set())
        then_block, then_stop = self._branch(then_edge.target, merge, inner_stop, stop_at_loop_end)
        else_block, else_stop = self._branch(else_edge.target, merge, inner_stop, stop_at_loop_end)
        stmt = If(node.text, cur, then_block, else_block, then_edge.label or yes_label(),
                  else_edge.label or no_label(), self.comments(cur))
        return stmt, self._continuation(merge, [(then_block, then_stop), (else_block, else_stop)])

    def _unlabelled_hint(self, cur: str, outs: list[Edge]) -> None:
        if not has_yes_no_labels(outs):
            self.warn(tr("Die Ausgänge der Verzweigung „{name}“ sind nicht mit ja/nein beschriftet; "
                         "der erste Ausgang gilt als „ja“.", name=self.label(cur)))

    def _one_exit_decision(self, cur: str):
        """Verzweigung mit nur einem Ausgang: Beim anderen Ergebnis endet der Ablauf."""
        node = self.node(cur)
        self.emitted.add(cur)
        yes_edge, no_edge = yes_no_edges(self.g.outgoing(cur))
        self.warn(tr("Die Verzweigung „{name}“ hat nur einen Ausgang; beim anderen Ergebnis endet der Ablauf.",
                     name=self.label(cur)))
        dead_end = Block([EndStmt("kein Ausgang", cur, repeated=True)])
        if yes_edge is not None:
            return If(node.text, cur, Block(), dead_end, yes_edge.label or yes_label(), no_label(),
                      self.comments(cur)), yes_edge.target
        return If(node.text, cur, dead_end, Block(), yes_label(), no_edge.label or no_label(),
                  self.comments(cur)), no_edge.target

    def _multi_branch(self, cur: str, outs: list[Edge], stop: frozenset, stop_at_loop_end: bool):
        """Verzweigung über beschriftete Ausgänge → verschachtelte Wenn-Folge."""
        node = self.node(cur)
        subject = " ".join(node.text.split()).rstrip("?").strip()
        # Ausgänge mit demselben Ziel gehören zusammen („6“ oder „7“ → Wochenende)
        groups: dict[str, list[Edge]] = {}
        for edge in outs:
            groups.setdefault(edge.target, []).append(edge)
        blocked = stop | {cur} | self._open_heads()
        merge = self._usable_merge(self._merge_point(cur, list(groups), blocked))
        inner_stop = stop | ({merge} if merge else set())
        built = []
        for target, edges in groups.items():
            block, stopped = self._branch(target, merge, inner_stop, stop_at_loop_end)
            built.append((edges, block, stopped))
        # der letzte Ausgang (bzw. „sonst“) ist der Sonst-Zweig
        else_index = next(i for i, (edges, _, _) in enumerate(built) if outs[-1] in edges)
        else_block = built[else_index][1]
        chain = [entry for i, entry in enumerate(built) if i != else_index]
        for edges, block, _ in reversed(chain):
            conditions = []
            for edge in edges:
                conditions.append(branch_condition(node.text, edge.label) or f"{subject} = ?")
                if not edge.label.strip():
                    self.warn(tr("Ein Ausgang der Verzweigung „{name}“ ist nicht beschriftet.", name=self.label(cur)))
            # „oder“ verbindet Bedingungen im Plantext: Schlüsselwort der Plansprache, wird vom Programm ausgewertet
            else_block = Block([If(" oder ".join(conditions), cur, block, else_block, yes_label(), no_label(),
                                   self.comments(cur))])
        if not chain:
            # alle Ausgänge führen zum selben Baustein
            else_block = Block([If(node.text, cur, Block(), Block(), yes_label(), no_label(), self.comments(cur))])
        continuation = self._continuation(merge, [(block, stopped) for _, block, stopped in built])
        return else_block.statements[0], continuation

    def _merge_point(self, cur: str, starts: list[str], blocked: frozenset) -> str | None:
        """Baustein, an dem die Zweige wieder zusammenlaufen.

        Das ist der nächste Baustein, durch den *jeder* Weg von der Verzweigung
        zum Ende führt – sofern ihn alle Zweige innerhalb des aktuellen Bereichs
        erreichen. Sonst gibt es keine gemeinsame Fortsetzung.
        """
        reaches = [self.reach(s, blocked) for s in starts]
        common = set(reaches[0])
        for r in reaches[1:]:
            common &= set(r)
        if cur in self._ipdom:
            merge = self._ipdom[cur]
            return merge if merge in common else None
        if not common:
            return None

        # Ablauf ohne Ende (Endlosschleife): nächster gemeinsam erreichbarer Baustein
        def cost(nid: str) -> tuple:
            n = self.node(nid)
            return (max(r[nid] for r in reaches), sum(r[nid] for r in reaches), n.y, n.x, nid)
        return min(common, key=cost)

    # --------------------------------------------------------- Schleifen
    def _find_latch(self, head: str, stop: frozenset) -> str | None:
        """Verzweigung weiter unten, die zu ``head`` zurückspringt (fußgesteuert)."""
        blocked = stop | {head} | self._open_heads()
        candidates = []
        dist = None
        for edge in self.g.incoming(head):
            src = edge.source
            if src == head or src in self.emitted:
                continue
            src_node = self.node(src)
            if src_node.type is not ElementType.DECISION or len(self.g.outgoing(src)) != 2:
                continue
            if is_choice_decision(self.g, src):
                continue
            if dist is None:
                dist = self.reach(head, blocked, expand_start=True)
            if src not in dist:
                continue
            # der andere Ausgang muss die Schleife verlassen (nicht zurück zu head)
            others = [e for e in self.g.outgoing(src) if e.target != head]
            if len(others) != 1:
                continue
            if head in self.reach(others[0].target, blocked):
                continue
            candidates.append((dist[src], src))
        if not candidates:
            return None
        return max(candidates)[1]  # äußerste Schleife zuerst

    def _do_while(self, head: str, latch: str, stop: frozenset):
        outs = self.g.outgoing(latch)
        back = [e for e in outs if e.target == head][0]
        exit_edge = [e for e in outs if e is not back][0]
        self._dowhile_heads.add(head)
        self._loops.append(_OpenLoop(exit_edge.target, end=latch, convert=head))
        try:
            body, stopped = self.block(head, stop | {latch})
        finally:
            self._loops.pop()
            self._dowhile_heads.discard(head)
        if stopped is not None and stopped != latch:
            self._lost_jump(body, stopped, convert=head)
        latch_node = self.node(latch)
        self.emitted.add(latch)
        self._unlabelled_hint(latch, outs)
        negate = back is yes_no_edges(outs)[1]
        return DoWhileLoop(latch_node.text, latch, body, negate, self.comments(latch)), exit_edge.target

    def _general_loop(self, head: str, stop: frozenset):
        """Schleife ohne eigene Bedingung ab ``head``: Rücksprünge dorthin beginnen den nächsten Durchlauf.

        Verlassen wird sie zu dem ersten Baustein hinter der Schleife, durch den
        jeder Weg zum Ende führt – so laufen mehrere Ausgänge dort zusammen.
        """
        blocked = stop | self._open_heads()
        inside = {n for n in self.reach(head, blocked, expand_start=True)
                  if n not in blocked and head in self.reach(n, blocked)}
        inside.add(head)
        after = self._ipdom.get(head)
        for _ in range(len(self.g.nodes) + 1):
            if after is None or after == _EXIT or after not in inside:
                break
            after = self._ipdom.get(after)
        if after == _EXIT or after in inside:
            after = None
        self._loops.append(_OpenLoop(after, head=head))
        self._entering = head
        try:
            body, stopped = self.block(head, stop)
        finally:
            self._loops.pop()
            self._entering = None
        if stopped is not None:
            self._lost_jump(body, stopped)
        return Loop(body, head), after

    def _matching_loop_end(self, begin: str) -> str | None:
        """Das Schleifenende, das zu diesem Schleifenbeginn gehört.

        Verschachtelte Schleifen werden übersprungen; Schleifenenden, die schon zu
        einem umgebenden Schleifenbeginn gehören, sind eine Grenze. Führen mehrere
        Wege zu verschiedenen Enden (Sprung aus der inneren Schleife), gilt das
        innere: dasjenige, von dem aus die anderen noch erreichbar sind.
        """
        if begin in self._loop_ends:
            return self._loop_ends[begin]
        claimed = set(self._loop_ends.values())
        max_depth = sum(1 for node in self.g.nodes.values() if node.is_loop_begin)
        candidates: dict[str, int] = {}
        seen = set()
        queue = deque((target, 0, 1) for target in self.g.successors(begin))
        while queue:
            current, depth, distance = queue.popleft()
            if current == begin or (current, depth) in seen:
                continue  # der Rumpf ist wieder am eigenen Anfang angekommen
            seen.add((current, depth))
            node = self.node(current)
            if node.is_loop_end:
                if depth == 0:
                    if current not in claimed:
                        candidates.setdefault(current, distance)
                    continue
                depth -= 1
            elif node.is_loop_begin:
                depth += 1
                if depth > max_depth:
                    continue  # Kreis ohne Schleifenende: nicht endlos weiterzählen
            queue.extend((target, depth, distance + 1) for target in self.g.successors(current))
        if not candidates:
            return None
        ordered = sorted(candidates, key=lambda nid: (candidates[nid], nid))
        end = ordered[0]
        for candidate in ordered:
            reachable = self.g.reachable_from(candidate)
            if all(other in reachable for other in candidates):
                end = candidate
                break
        self._loop_ends[begin] = end
        return end

    def _limit_loop(self, begin: str, stop: frozenset):
        node = self.node(begin)
        self.emitted.add(begin)
        nxt = self._single_next(begin)
        end = self._matching_loop_end(begin)
        if end is None:
            self.warn(tr("Zum Schleifenbeginn „{name}“ wurde kein Schleifenende gefunden.", name=node.text))
            body, stopped = self.block(nxt, stop, stop_at_loop_end=True) if nxt else (Block(), None)
            return LimitLoop(node.text, "", begin, None, body, self.comments(begin)), stopped
        after = self.g.outgoing(end)
        self._loops.append(_OpenLoop(after[0].target if after else None, end=end))
        try:
            body, stopped = self.block(nxt, stop | {end}) if nxt else (Block(), end)
        finally:
            self._loops.pop()
        if stopped is not None and stopped != end:
            self.warn(tr("Der Rumpf der Schleife „{name}“ führt an ihrem Schleifenende vorbei.", name=node.text))
            self._lost_jump(body, stopped)
        self.emitted.add(end)
        return LimitLoop(node.text, self.node(end).text, begin, end, body, self.comments(begin)), \
            self._single_next(end)
