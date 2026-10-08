"""Ablauf-Engine des Schreibtischtests.

Die Engine läuft Baustein für Baustein durch den Ablaufgraphen, verwaltet
Variablen, Ausgaben und ein Protokoll (Schreibtischtest-Tabelle).
Eingaben und nicht auswertbare Bedingungen werden beim Benutzer
nachgefragt (``needs``); danach geht es mit ``provide_input`` bzw.
``provide_decision`` weiter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import i18n, labels
from app.analysis import text as T
from app.analysis.ast import DoWhileLoop, If, LimitLoop, Loop, WhileLoop
from app.analysis.graph import FlowGraph, yes_no_edges
from app.analysis.structure import is_choice_decision, structure_program
from app.i18n import N_, tr
from app.model.element_types import ElementType, default_text_for, display_name_for
from app.analysis.variables import BOOLEAN, DEFAULTS, STRING, Variables
from app.simulation.evaluator import (EvaluationError, Scope, display, evaluate, evaluate_condition, format_value,
                                      parse_number, parse_value)

MAX_STEPS = 10_000
MAX_CALL_DEPTH = 100
NEEDS_INPUT = "input"
NEEDS_DECISION = "decision"

# Wer hat entschieden? (steht in der Protokollzeile; angezeigt mit tr(...))
HOW_AUTOMATIC = N_("automatisch")
HOW_BY_USER = N_("vom Benutzer")


def _is_yes_answer(text: str) -> bool:
    """Eingabe für eine Wahrheitsvariable: „j…“ (ja, jawohl) oder das Wort „ja“ einer anderen Sprache."""
    lowered = text.strip().lower()
    if lowered.startswith("j"):
        return True
    return lowered in {word.strip().lower() for word in i18n.all_translations(labels.YES_SOURCE, ctx="Beschriftung")}


@dataclass
class StepResult:
    element_id: str | None
    message: str
    needs: str | None = None
    prompt: str = ""
    variables: list = field(default_factory=list)
    output: str | None = None
    finished: bool = False
    # Mehrfachverzweigung: Beschriftungen der Ausgänge (sonst ja/nein)
    options: list = field(default_factory=list)


@dataclass
class TraceRow:
    step: int
    element_id: str
    element_text: str
    variables: dict


class Simulator:
    def __init__(self, graph: FlowGraph, start_id: str | None = None):
        self.graph = graph.collapse_junctions()
        starts = self.graph.starts()
        if start_id is None or start_id not in self.graph.nodes:
            start_id = starts[0].id if starts else None
        self.start_id = start_id
        self.loop_end_of: dict[str, str] = {}
        self.loop_begin_of: dict[str, str] = {}
        # Schleifenpaare aller Abläufe (auch der Unterprogramme)
        programs = []
        for start in starts:
            try:
                program = structure_program(self.graph, start.id)
                self._collect_loops(program.body)
                programs.append(program)
            except Exception:
                pass
        # Typen der Variablen – dieselben wie in den erzeugten Programmen
        try:
            info = Variables(programs)
        except Exception:
            info = Variables([])
        self.types: dict[str, str] = info.types
        self.dynamic: set[str] = info.dynamic
        self.known: set[str] = set(info.names)
        self._defaults = {name: DEFAULTS[kind] for name, kind in info.types.items()}
        self._missing: list[str] = []
        self.reset()

    def _scope(self) -> Scope:
        """Variablen für eine Auswertung; fehlende Werte des Plans bekommen den Startwert ihres Typs."""
        return Scope(self.variables, self._defaults, self._missing)

    def _collect_loops(self, block) -> None:
        for stmt in block:
            if isinstance(stmt, LimitLoop):
                if stmt.end_id:
                    self.loop_end_of[stmt.begin_id] = stmt.end_id
                    self.loop_begin_of[stmt.end_id] = stmt.begin_id
                self._collect_loops(stmt.body)
            elif isinstance(stmt, If):
                self._collect_loops(stmt.then_block)
                self._collect_loops(stmt.else_block)
            elif isinstance(stmt, (WhileLoop, DoWhileLoop, Loop)):
                self._collect_loops(stmt.body)

    def reset(self) -> None:
        self.current: str | None = self.start_id
        self.variables: dict = {}
        self.outputs: list[str] = []
        self.trace: list[TraceRow] = []
        self.steps = 0
        self.finished = self.start_id is None
        self.pending: StepResult | None = None
        self._loop_state: dict[str, dict] = {}
        self._reentering: set[str] = set()
        self._call_stack: list[tuple[str | None, str]] = []  # (Rücksprungziel, Aufruf-Text)

    # ------------------------------------------------------------- Helfer
    def node(self, nid: str):
        return self.graph.nodes[nid]

    def _next(self, nid: str) -> str | None:
        outs = self.graph.outgoing(nid)
        return outs[0].target if outs else None

    def _record(self, nid: str) -> None:
        self.trace.append(TraceRow(len(self.trace) + 1, nid, " ".join(self.node(nid).text.split()),
                                   dict(self.variables)))

    def _advance(self, nid: str, target: str | None, message: str, output: str | None = None) -> StepResult:
        self._record(nid)
        self.current = target
        if target is None:
            self.finished = True
            message = tr("{message} – Ablauf endet hier (kein Nachfolger).", message=message)
        return StepResult(nid, message, output=output, finished=self.finished)

    # -------------------------------------------------------------- Schritt
    def step(self) -> StepResult:
        if self.finished:
            return StepResult(self.current, tr("Der Ablauf ist beendet."), finished=True)
        if self.pending is not None:
            return self.pending
        if self.steps >= MAX_STEPS:
            self.finished = True
            return StepResult(self.current, tr("Abbruch nach {n} Schritten (Endlosschleife?).", n=MAX_STEPS),
                              finished=True)
        nid = self.current
        if nid not in self.graph.nodes:
            self.finished = True
            return StepResult(None, tr("Der nächste Baustein existiert nicht mehr."), finished=True)
        self.steps += 1
        node = self.node(nid)
        handler = {
            ElementType.START: self._start, ElementType.END: self._end, ElementType.INPUT: self._input,
            ElementType.OUTPUT: self._output, ElementType.PROCESS: self._process,
            ElementType.SUBPROGRAM: self._subprogram, ElementType.DECISION: self._decision,
            ElementType.LOOP: self._loop, ElementType.JUNCTION: self._junction,
        }.get(node.type, self._process)
        self._missing.clear()
        try:
            result = handler(nid, node)
            return self._with_hint(result)
        except Exception as exc:  # Absicherung: der Schreibtischtest darf nie abstürzen
            self.pending = None
            self.finished = True
            return StepResult(nid, tr("Abbruch: „{text}“ ließ sich nicht ausführen ({error_type}).",
                                      text=' '.join(node.text.split()), error_type=type(exc).__name__),
                              finished=True)

    def _with_hint(self, result: StepResult) -> StepResult:
        """Hinweis, wenn eine Variable gelesen wurde, bevor sie einen Wert hatte."""
        if self._missing and result.needs is None:
            names = ", ".join(tr("„{name}“", name=name) for name in self._missing)
            values = ", ".join(format_value(self._defaults[name]) for name in self._missing)
            if len(self._missing) == 1:
                result.message = tr("{message} – Hinweis: {names} hatte noch keinen Wert, angenommen wird {values}",
                                    message=result.message, names=names, values=values)
            else:
                result.message = tr("{message} – Hinweis: {names} hatten noch keinen Wert, angenommen wird {values}",
                                    message=result.message, names=names, values=values)
        self._missing.clear()
        return result

    def _start(self, nid, node):
        return self._advance(nid, self._next(nid),
                             tr("Start: {text}", text=node.text or default_text_for(ElementType.START)))

    def _end(self, nid, node):
        if self._call_stack:
            return_to, name = self._call_stack.pop()
            return self._advance(nid, return_to, tr("Ende von „{name}“: zurück zum Aufrufer", name=name))
        self._record(nid)
        self.finished = True
        return StepResult(nid, tr("Ende: {text}", text=node.text or default_text_for(ElementType.END)),
                          finished=True)

    def _junction(self, nid, node):
        return self._advance(nid, self._next(nid), display_name_for(ElementType.JUNCTION))

    def _subprogram_start(self, text: str) -> str | None:
        """Start-Element des Ablaufs, der so heißt wie der Aufruf („Verdoppeln“)."""
        call = T.call_parts(text)
        wanted = T.slug(call[0] if call else text, "")
        if not wanted:
            return None
        found = [start.id for start in self.graph.starts() if T.slug(start.text, "") == wanted]
        # ein Aufruf meint den gleichnamigen Ablauf – nicht das gerade laufende Hauptprogramm
        others = [start_id for start_id in found if start_id != self.start_id]
        return (others or found or [None])[0]

    def _subprogram(self, nid, node):
        name = " ".join(node.text.split())
        start = self._subprogram_start(node.text)
        if start is None:
            return self._advance(nid, self._next(nid),
                                 tr("Unterprogramm „{name}“: kein Ablauf mit diesem Namen – übersprungen.",
                                    name=name))
        if len(self._call_stack) >= MAX_CALL_DEPTH:
            self._record(nid)
            self.finished = True
            return StepResult(nid, tr("Abbruch: zu viele verschachtelte Aufrufe von „{name}“ (Rekursion?).",
                                      name=name), finished=True)
        self._call_stack.append((self._next(nid), name))
        return self._advance(nid, start, tr("Unterprogramm „{name}“ aufgerufen.", name=name))

    def _process(self, nid, node):
        assignments = T.parse_assignments(node.text)
        if not assignments:
            return self._advance(nid, self._next(nid),
                                 tr("Nicht ausgewertet: {text}", text=' '.join(node.text.split())))
        parts = []
        for name, expr in assignments:
            try:
                value = evaluate(expr, self._scope())
            except EvaluationError as exc:
                return self._advance(nid, self._next(nid),
                                     tr("Fehler bei „{assignment}“: {error}", assignment=f"{name} = {expr}",
                                        error=exc))
            self.variables[name] = value
            parts.append(f"{name} = {format_value(value)}")
        return self._advance(nid, self._next(nid), ", ".join(parts))

    def _output(self, nid, node):
        spec = T.output_spec(node.text, self.known | set(self.variables))
        scope = self._scope()
        try:
            if spec.kind == "string":
                text = spec.value
            elif spec.kind == "mixed":
                text = " ".join(value if kind == "string" else display(evaluate(value, scope))
                                for kind, value in spec.parts)
            elif spec.kind == "expression":
                text = display(evaluate(spec.value, scope))
            elif spec.kind == "variables":
                values = ", ".join(display(scope[v]) for v in spec.variables)
                text = f"{spec.value}: {values}"
            else:
                text = spec.value  # Freitext: genau das, was auch die erzeugten Programme ausgeben
        except (EvaluationError, KeyError) as exc:
            text = f"{spec.value} ({exc})"
        self.outputs.append(text)
        return self._advance(nid, self._next(nid), tr("Ausgabe: {text}", text=text), output=text)

    # --------------------------------------------------------- Eingabe
    def _input(self, nid, node):
        # Platzhaltername, wenn im Text keine Variable erkennbar ist: wird nur angezeigt, nie als Variable gespeichert
        names = T.input_variables(node.text) or [tr("eingabe", ctx="Variable")]
        prompt = " ".join(node.text.split())
        self.pending = StepResult(nid, tr("Eingabe erforderlich: {prompt}", prompt=prompt), NEEDS_INPUT, prompt,
                                  names)
        self.steps -= 1  # zählt erst mit der Eingabe
        return self.pending

    def provide_input(self, values) -> StepResult:
        pending = self.pending
        if pending is None or pending.needs != NEEDS_INPUT:
            return StepResult(self.current, tr("Es wird gerade keine Eingabe erwartet."))
        names = pending.variables
        if isinstance(values, dict):
            parsed = {name: values.get(name) for name in names}
        else:
            raw = [v for v in re.split(r"[;\s]+|,(?!\d)", str(values).strip()) if v != ""] if len(names) > 1 \
                else [str(values)]
            parsed = {name: raw[i] if i < len(raw) else None for i, name in enumerate(names)}
        if any(value is None or str(value).strip() == "" for value in parsed.values()):
            return StepResult(pending.element_id, tr("Bitte Werte für {names} eingeben.", names=', '.join(names)),
                              NEEDS_INPUT, pending.prompt, names)
        nid = pending.element_id
        discard = not T.input_variables(self.node(nid).text)
        typed = {}
        for name, value in parsed.items():
            if not isinstance(value, str) or discard:
                typed[name] = value
                continue
            text, kind = value.strip(), self.types.get(name)
            if name in self.dynamic or kind is None:
                typed[name] = parse_value(text)       # Zahl, wenn es wie eine Zahl aussieht
            elif kind == STRING:
                typed[name] = text                    # der Plan benutzt die Variable als Text
            elif kind == BOOLEAN:
                typed[name] = _is_yes_answer(text)
            else:
                number = parse_number(text)
                if number is None:
                    return StepResult(nid, tr("Bitte eine Zahl für {name} eingeben – „{text}“ ist keine.",
                                              name=name, text=text),
                                      NEEDS_INPUT, pending.prompt, names)
                typed[name] = number
        self.pending = None
        self.steps += 1
        if discard:
            # Kein Variablenname im Text erkennbar: Der Wert wird – wie im erzeugten
            # Programm – eingelesen, aber keiner Variablen zugewiesen.
            value = " ".join(str(v) for v in parsed.values())
            return self._advance(nid, self._next(nid),
                                 tr("Eingabe: {value} (keiner Variablen zugeordnet – bitte im Text einen Namen "
                                    "angeben)", value=value))
        self.variables.update(typed)
        text = ", ".join(f"{name} = {format_value(self.variables[name])}" for name in names)
        return self._advance(nid, self._next(nid), tr("Eingabe: {text}", text=text))

    # ------------------------------------------------------ Verzweigung
    def _branch_targets(self, nid) -> tuple[str | None, str | None]:
        yes_edge, no_edge = yes_no_edges(self.graph.outgoing(nid))  # dieselbe Regel wie die Code-Erzeugung
        return (yes_edge.target if yes_edge else None, no_edge.target if no_edge else None)

    def _decision(self, nid, node):
        outs = self.graph.outgoing(nid)
        if is_choice_decision(self.graph, nid):
            return self._multi_decision(nid, node, outs)
        try:
            result = evaluate_condition(node.text, self._scope())
        except EvaluationError as exc:
            question = " ".join(node.text.split()) or tr("Bedingung erfüllt?")
            self.pending = StepResult(nid, tr("Bedingung nicht auswertbar ({error}) – bitte entscheiden.", error=exc),
                                      NEEDS_DECISION, question)
            self.steps -= 1
            return self.pending
        return self._take_branch(nid, bool(result), HOW_AUTOMATIC)

    def _multi_decision(self, nid, node, outs):
        """Mehrfachverzweigung: Ausgänge der Reihe nach prüfen (wie die Code-Erzeugung),
        der letzte Ausgang ist der Sonst-Zweig."""
        subject = " ".join(node.text.split())
        for index, edge in enumerate(outs[:-1]):
            condition = T.branch_condition(node.text, edge.label)
            try:
                if condition is None:
                    raise EvaluationError(tr("Ausgang ohne Beschriftung"))
                matched = evaluate_condition(condition, self._scope())
            except EvaluationError as exc:
                exit_labels = [" ".join(e.label.split()) or tr("Ausgang {n}", n=i + 1) for i, e in enumerate(outs)]
                self.pending = StepResult(nid, tr("Verzweigung nicht auswertbar ({error}) – bitte einen Ausgang "
                                                  "wählen.", error=exc),
                                          NEEDS_DECISION, subject or tr("Welcher Ausgang?"),
                                          options=exit_labels)
                self.steps -= 1
                return self.pending
            if matched:
                return self._take_exit(nid, index, HOW_AUTOMATIC)
        return self._take_exit(nid, len(outs) - 1, HOW_AUTOMATIC)

    def _take_exit(self, nid, index: int, how: str) -> StepResult:
        """``how`` ist ``HOW_AUTOMATIC`` oder ``HOW_BY_USER`` (deutscher Quelltext, wird hier übersetzt)."""
        outs = self.graph.outgoing(nid)
        edge = outs[max(0, min(index, len(outs) - 1))]
        label = " ".join(edge.label.split()) or tr("Ausgang {n}", n=index + 1)
        return self._advance(nid, edge.target, tr("Verzweigung „{text}“: {label} ({how})",
                                                  text=' '.join(self.node(nid).text.split()), label=label,
                                                  how=tr(how)))

    def _take_branch(self, nid, yes: bool, how: str) -> StepResult:
        yes_target, no_target = self._branch_targets(nid)
        target = yes_target if yes else no_target
        answer = labels.yes_label() if yes else labels.no_label()
        return self._advance(nid, target, tr("Bedingung „{text}“: {answer} ({how})",
                                             text=' '.join(self.node(nid).text.split()), answer=answer,
                                             how=tr(how)))

    def provide_decision(self, answer) -> StepResult:
        """``True``/``False`` (ja/nein) oder – bei Mehrfachverzweigungen – die Nummer des Ausgangs."""
        pending = self.pending
        if pending is None or pending.needs != NEEDS_DECISION:
            return StepResult(self.current, tr("Es wird gerade keine Entscheidung erwartet."))
        self.pending = None
        self.steps += 1
        nid = pending.element_id
        node = self.node(nid)
        if pending.options and not isinstance(answer, bool):
            return self._take_exit(nid, int(answer), HOW_BY_USER)
        if node.type is ElementType.LOOP and node.is_loop_end:
            return self._loop_end_decision(nid, bool(answer), HOW_BY_USER)
        if node.type is ElementType.LOOP:
            return self._loop_decision(nid, bool(answer))
        return self._take_branch(nid, bool(answer), HOW_BY_USER)

    # --------------------------------------------------------- Schleifen
    def _after_loop(self, begin_id: str) -> str | None:
        end_id = self.loop_end_of.get(begin_id)
        return self._next(end_id) if end_id else None

    def _loop(self, nid, node):
        if node.is_loop_end:
            return self._loop_end(nid, node)
        return self._loop_begin(nid, node)

    def _loop_begin(self, nid, node):
        header = T.parse_loop_header(node.text)
        end_id = self.loop_end_of.get(nid)
        footer = T.parse_loop_footer(self.node(end_id).text) if end_id else None
        reentering = nid in self._reentering
        self._reentering.discard(nid)
        body = self._next(nid)
        try:
            if footer is not None and header.kind != "for":
                # fußgesteuert: Kopf wird nicht geprüft
                return self._advance(nid, body, tr("Schleife: Rumpf wird ausgeführt"))
            if header.kind == "for":
                scope = self._scope()
                # Ende und Schrittweite gelten – wie im erzeugten Programm – mit ihren aktuellen Werten
                end, step = evaluate(header.end, scope), evaluate(header.step, scope)
                if not reentering or nid not in self._loop_state:
                    value = evaluate(header.start, scope)
                else:
                    value = scope[header.variable] + step
                self._loop_state[nid] = {}
                self.variables[header.variable] = value
                inside = value >= end if step < 0 else value <= end
            elif header.kind == "while":
                inside = bool(evaluate(header.condition, self._scope(), condition=True))
            elif header.kind == "times":
                state = self._loop_state.get(nid)
                if not reentering or state is None:
                    state = {"left": int(evaluate(header.count, self._scope()))}
                    self._loop_state[nid] = state
                else:
                    state["left"] -= 1
                inside = state["left"] > 0
            else:
                question = tr("Schleife „{text}“ (erneut) durchlaufen?", text=' '.join(node.text.split()))
                self.pending = StepResult(nid, tr("Schleifenbedingung nicht auswertbar – bitte entscheiden."),
                                          NEEDS_DECISION, question)
                self.steps -= 1
                return self.pending
        except (EvaluationError, TypeError, ValueError, OverflowError) as exc:
            question = tr("Schleife „{text}“ (erneut) durchlaufen?", text=' '.join(node.text.split()))
            self.pending = StepResult(nid, tr("Schleifenkopf nicht auswertbar ({error}) – bitte entscheiden.",
                                              error=exc),
                                      NEEDS_DECISION, question)
            self.steps -= 1
            return self.pending
        return self._loop_decision(nid, inside, automatic=True)

    def _loop_decision(self, nid, inside: bool, automatic: bool = False) -> StepResult:
        how = tr(HOW_AUTOMATIC if automatic else HOW_BY_USER)
        text = ' '.join(self.node(nid).text.split())
        if inside:
            return self._advance(nid, self._next(nid),
                                 tr("Schleife „{text}“: Durchlauf ({how})", text=text, how=how))
        self._loop_state.pop(nid, None)
        return self._advance(nid, self._after_loop(nid),
                             tr("Schleife „{text}“ beendet ({how})", text=text, how=how))

    def _loop_end(self, nid, node):
        begin_id = self.loop_begin_of.get(nid)
        if begin_id is None:
            return self._advance(nid, self._next(nid), tr("Schleifenende (ohne Schleifenbeginn)"))
        footer = T.parse_loop_footer(node.text)
        if footer is not None:
            kind, cond = footer
            try:
                result = bool(evaluate(cond, self._scope()))
            except EvaluationError as exc:
                # wie im erzeugten Programm: den Benutzer fragen
                self.pending = StepResult(nid, tr("Schleifenende nicht auswertbar ({error}) – bitte entscheiden.",
                                                  error=exc),
                                          NEEDS_DECISION, " ".join(node.text.split()))
                self.steps -= 1
                return self.pending
            return self._loop_end_decision(nid, result, HOW_AUTOMATIC)
        self._reentering.add(begin_id)
        return self._advance(nid, begin_id, tr("Schleifenende: zurück zum Schleifenbeginn"))

    def _loop_end_decision(self, nid, result: bool, how: str) -> StepResult:
        """Fuß der Schleife: „bis …“ verlässt sie, wenn die Bedingung gilt; „solange …“ wiederholt dann.

        ``how`` ist ``HOW_AUTOMATIC`` oder ``HOW_BY_USER`` (deutscher Quelltext, wird hier übersetzt).
        """
        node = self.node(nid)
        begin_id = self.loop_begin_of[nid]
        kind, _ = T.parse_loop_footer(node.text)
        text = " ".join(node.text.split())
        how = tr(how)
        if (not result) if kind == "until" else result:
            if T.parse_loop_header(self.node(begin_id).text).kind == "for":
                # Zählschleife mit zusätzlicher Bedingung am Ende: weiterzählen
                self._reentering.add(begin_id)
                return self._advance(nid, begin_id, tr("Schleifenende „{text}“: nächster Durchlauf ({how})",
                                                       text=text, how=how))
            return self._advance(nid, self._next(begin_id),
                                 tr("Schleifenende „{text}“: nächster Durchlauf ({how})", text=text, how=how))
        self._loop_state.pop(begin_id, None)
        return self._advance(nid, self._next(nid), tr("Schleifenende „{text}“: Schleife beendet ({how})",
                                                      text=text, how=how))
