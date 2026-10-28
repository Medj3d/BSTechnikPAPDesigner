"""Lesen und Schreiben von ``.pap``-Projektdateien.

``.pap`` ist das einzige Projektformat der Anwendung. Die Datei ist XML im
Aufbau des PapDesigners (Friedrich Folkmann)::

    <FRAME GUID="…" FORMAT="0000" APP_VERSION="2.2.0.8" CHECKSUM="UNSIGNED"
           xmlns:bst="urn:bstechnik:pap-designer" bst:VERSION="1" …>
      <PROJECT FORMAT="1.00" NAME="…" AUTHOR="…" CREATED="2020.04.15 18:24:47" MODIFIED="…"
               bst:DESCRIPTION="…" bst:CREATED="…" bst:MODIFIED="…">
        <DIAGRAMS>
          <DIAGRAM FORMAT="1.00" ID="0" NAME="…" CREATED="…" MODIFIED="…">
            <LAYOUT FORMAT="1.00" COLUMNS="2" ROWS="13" bst:GRID_SIZE="20" bst:ZOOM="1" …>
              <ENTRIES>
                <ENTRY COLUMN="0" ROW="1" bst:X="0" bst:Y="0" bst:WIDTH="120" bst:HEIGHT="40">
                  <FIGURE SUBTYPE="PapStart" FORMAT="1.00" ID="1" bst:UID="…">
                    <TEXT><![CDATA[Start]]></TEXT>
                  </FIGURE>
                </ENTRY> …
              </ENTRIES>
            </LAYOUT>
            <CONNECTIONS>
              <CONNECTION FORMAT="1.00" ID="14" FROM="1" TO="2" TEXT="" bst:UID="…"
                          bst:SOURCE_PORT="bottom" bst:TARGET_PORT="top" /> …
            </CONNECTIONS>
          </DIAGRAM>
        </DIAGRAMS>
      </PROJECT>
    </FRAME>

Elemente und Attribute ohne Präfix sind die des PapDesigners: Bausteine
liegen dort auf einem Raster (``COLUMN``/``ROW``) und tragen fortlaufende
Nummern, auf die sich die Verbindungen beziehen. Alles, was darüber
hinausgeht (genaue Position und Größe, eindeutige IDs, Anschlüsse,
Linienführung, angezeigter Linienverlauf ``PATH``, Ansicht), steht in
Attributen des Namensraums ``bst`` an denselben Elementen; ``PROPERTIES``
nimmt weitere Eigenschaften eines Bausteins als JSON-Objekt auf. Enthält
eine Datei diese Angaben, wird das Projekt exakt wiederhergestellt. Fehlen
sie (Datei direkt aus dem PapDesigner), wird die Anordnung aus dem Raster
abgeleitet.

Das erste ``DIAGRAM`` ist das Hauptprogramm, jedes weitere ein Unterprogramm
auf einer eigenen Seite (``Diagram.subprograms``) – so legt auch der
PapDesigner Unterprogramme an. Aufgerufen wird ein Unterprogramm über den
Text seines Start-Elements.

Warnungen (rote Verbindungen) werden nicht gespeichert, sondern beim Öffnen
aus Bausteinen und Verbindungen in ihrer gespeicherten Reihenfolge neu
berechnet.

Beim Laden wird jede Angabe geprüft. Fehlerhafte Einzelwerte (Position,
Größe, Ebene, Anschlüsse, Linienführung, IDs, Rastergröße, Eigenschaften)
werden – soweit möglich – korrigiert und als Warnung gemeldet; ungültige
Ansichtsangaben werden stillschweigend ersetzt. Eine unlesbare oder
inkompatible Datei führt zu einem ``ProjectFileError`` mit verständlicher
Meldung. Gespeichert wird atomar (temporäre Datei + Umbenennen), damit eine
bestehende Datei bei einem Fehler nicht beschädigt wird.
"""

from __future__ import annotations

import heapq
import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

from app import config
from app.fileformat.project import (CURRENT_FORMAT_VERSION, EXTENSION_NAMESPACE, EXTENSION_PREFIX,
                                    PAP_APP_VERSION, PAP_CHECKSUM, PAP_ELEMENT_FORMAT,
                                    PAP_FRAME_FORMAT, PAP_FRAME_GUID, PAP_TIME_FORMAT,
                                    SINGLE_PAGE_FORMAT_VERSION, SUBPROGRAM_FORMAT_VERSION, ProjectFileError,
                                    check_version)
from app.i18n import tr
from app.model.diagram import (ConnectionData, Diagram, DiagramSettings, ElementData,
                               ProjectMeta, SubprogramPage, new_id, now_iso)
from app.model.element_types import (ALL_PORTS, LOOP_BEGIN, LOOP_END, LOOP_PART_KEY, TRUNK_IN_KEY,
                                     TRUNK_OUT_KEY, ElementType, default_properties_for, spec_for)

MAX_FILE_SIZE = 200 * 1024 * 1024

# Bausteintypen des PapDesigners
SUBTYPES = {
    "PapStart": ElementType.START,
    "PapEnd": ElementType.END,
    "PapInput": ElementType.INPUT,
    "PapOutput": ElementType.OUTPUT,
    "PapActivity": ElementType.PROCESS,
    "PapModule": ElementType.SUBPROGRAM,
    "PapCondition": ElementType.DECISION,
    "PapLoopStart": ElementType.LOOP,
    "PapLoopEnd": ElementType.LOOP,
    "PapConnector": ElementType.JUNCTION,
    "PapComment": ElementType.COMMENT,
    "PapTitle": ElementType.COMMENT,
}
_SUBTYPE_FOR_TYPE = {
    ElementType.START: "PapStart",
    ElementType.END: "PapEnd",
    ElementType.INPUT: "PapInput",
    ElementType.OUTPUT: "PapOutput",
    ElementType.PROCESS: "PapActivity",
    ElementType.SUBPROGRAM: "PapModule",
    ElementType.DECISION: "PapCondition",
    ElementType.JUNCTION: "PapConnector",
    ElementType.COMMENT: "PapComment",
}
# Verbindungsknoten: Verweise auf die beiden Teile des aufgetrennten Pfeils
_TRUNK_ATTRIBUTES = ((TRUNK_IN_KEY, "TRUNK_IN"), (TRUNK_OUT_KEY, "TRUNK_OUT"))

# Rastermaße, mit denen eine Datei ohne Zusatzangaben angeordnet wird
COLUMN_WIDTH = 240.0
ROW_HEIGHT = 140.0
# Bausteine, deren Mittelpunkte höchstens so weit auseinanderliegen, teilen
# sich beim Speichern eine Rasterspalte bzw. -zeile
COLUMN_TOLERANCE = 60.0
ROW_TOLERANCE = 30.0
# Grenzen für Angaben aus Dateien: Rasterzelle, Schachtelung weiterer Eigenschaften
MAX_GRID_INDEX = 100000
MAX_PROPERTY_DEPTH = 16


@dataclass
class LoadResult:
    diagram: Diagram
    warnings: list = field(default_factory=list)
    # True: Die Datei enthielt die Zusatzangaben (exakte Wiederherstellung).
    # False: Anordnung wurde aus dem PapDesigner-Raster abgeleitet.
    native: bool = True


# ------------------------------------------------------------------ Helfer
def _ext(name: str) -> str:
    """Name eines Zusatzattributs beim Schreiben."""
    return f"{EXTENSION_PREFIX}:{name}"


def _key(name: str) -> str:
    """Name eines Zusatzattributs beim Lesen (ElementTree-Schreibweise)."""
    return f"{{{EXTENSION_NAMESPACE}}}{name}"


def _number(value, default: float) -> tuple[float, bool]:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return float(default), False
    if value is None or not math.isfinite(number):
        return float(default), False
    return number, True


def _flag(value, default: bool) -> bool:
    text = str(value).strip().lower() if value is not None else ""
    if text in ("true", "1"):
        return True
    if text in ("false", "0"):
        return False
    return default


def _attr_int(element, name: str, default: int = 0) -> int:
    try:
        value = int(str(element.get(name, default)).strip())
    except (TypeError, ValueError):
        return default
    return max(-MAX_GRID_INDEX, min(MAX_GRID_INDEX, value))


def _reference(value) -> str:
    """Nummer eines Bausteins, wie sie ``ID``, ``FROM`` und ``TO`` verwenden."""
    return str(value or "").strip()


def _finite(value) -> float:
    number, _ = _number(value, 0.0)
    return number


def _format_number(value) -> str:
    """Zahl ohne Genauigkeitsverlust; ganze Zahlen ohne Nachkommastelle."""
    number = float(value)
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return repr(number)


def _format_flag(value) -> str:
    return "True" if value else "False"


# Zeichen, die XML 1.0 nicht darstellen kann (Steuerzeichen, einzelne Surrogate)
_ILLEGAL_XML = re.compile("[^\x09\x0A\x0D\x20-\U0000D7FF\U0000E000-\U0000FFFD\U00010000-\U0010FFFF]")
# Vertikaler Tabulator und Seitenvorschub: weiche Zeilenumbrüche aus Textprogrammen
_SOFT_BREAKS = str.maketrans({"\x0b": "\n", "\x0c": "\n"})


def storable_text(value) -> str:
    """Der Text so, wie ihn eine ``.pap``-Datei aufnehmen kann.

    Weiche Zeilenumbrüche (z. B. aus Word oder PowerPoint eingefügt) werden zu
    normalen Zeilenumbrüchen, übrige nicht darstellbare Steuerzeichen entfallen.
    Die Texteingabe wendet dies sofort an, damit das Programm nie etwas anzeigt,
    das nicht genau so gespeichert wird.
    """
    return _ILLEGAL_XML.sub("", str(value).translate(_SOFT_BREAKS))


_clean = storable_text


def _attribute(value) -> str:
    text = _clean(value)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    # Zeilenumbrüche und Tabulatoren als Zeichenreferenz, sonst macht der
    # XML-Parser beim Lesen Leerzeichen daraus
    return text.replace("\r", "&#13;").replace("\n", "&#10;").replace("\t", "&#9;")


def _text_content(value) -> str:
    text = _clean(value)
    if "\r" in text:
        # In CDATA würde ein Wagenrücklauf beim Lesen zu einem Zeilenumbruch
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\r", "&#13;"))
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _tag(name: str, attributes: list, indent: int, empty: bool = False) -> str:
    parts = "".join(f' {key}="{_attribute(value)}"' for key, value in attributes)
    return f"{'  ' * indent}<{name}{parts}{' /' if empty else ''}>"


def _pap_timestamp(value: str) -> str:
    """Zeitpunkt in der Schreibweise des PapDesigners."""
    try:
        return datetime.fromisoformat(value).strftime(PAP_TIME_FORMAT)
    except (TypeError, ValueError):
        return datetime.now().strftime(PAP_TIME_FORMAT)


def _timestamp(value: str | None, default: str | None = None) -> str:
    """Zeitpunkt aus der Schreibweise des PapDesigners als ISO-8601."""
    for fmt in (PAP_TIME_FORMAT, "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime((value or "").strip(), fmt).astimezone().isoformat(timespec="seconds")
        except (ValueError, OSError, OverflowError):
            continue
    return default or now_iso()


def _dedupe(messages: list[str]) -> list[str]:
    result = []
    for message in messages:
        if message not in result:
            result.append(message)
    return result


# --------------------------------------------------------------- Schreiben
def _cluster(values: list[float], tolerance: float) -> dict[float, int]:
    """Fortlaufende Indizes für sortierte Werte; nahe Werte teilen sich einen Index."""
    result: dict[float, int] = {}
    index, anchor = -1, None
    for value in sorted(set(values)):
        if anchor is None or value - anchor > tolerance:
            index += 1
            anchor = value
        result[value] = index
    return result


def _grid_cells(elements: list[ElementData]) -> list[tuple[int, int]]:
    """Rasterzelle (Spalte, Zeile) je Baustein für Programme, die nur das Raster kennen.

    Zeile 0 gehört dem Diagrammtitel. Jede Zelle wird nur einmal vergeben.
    """
    xs = [_finite(e.x) for e in elements]
    ys = [_finite(e.y) for e in elements]
    columns, rows = _cluster(xs, COLUMN_TOLERANCE), _cluster(ys, ROW_TOLERANCE)
    cells: list = [(0, 0)] * len(elements)
    taken = {(0, 0)}
    # belegte Zelle → nächste Spalte, die noch frei sein könnte (kürzt die Suche
    # ab, wenn sehr viele Bausteine auf derselben Stelle liegen)
    skip: dict[tuple[int, int], int] = {}
    for i in sorted(range(len(elements)), key=lambda n: (rows[ys[n]], columns[xs[n]], n)):
        column, row = columns[xs[i]], rows[ys[i]] + 1
        visited = []
        while (column, row) in taken:
            visited.append(column)
            column = skip.get((column, row), column + 1)
        taken.add((column, row))
        for passed in visited:
            skip[(passed, row)] = column + 1
        cells[i] = (column, row)
    return cells


# Richtung eines Anschlusses im Raster des PapDesigners: (Spalte, Zeile)
_PORT_DIRECTIONS = {"bottom": (0, 1), "right": (1, 0), "left": (-1, 0), "top": (0, -1)}


def _leaving_port(a: tuple[int, int], b: tuple[int, int]) -> str:
    """Anschluss, über den eine gerade Strecke von Zelle ``a`` nach ``b`` ``a`` verlässt."""
    if b[0] != a[0]:
        return "right" if b[0] > a[0] else "left"
    return "bottom" if b[1] > a[1] else "top"


def _arriving_port(a: tuple[int, int], b: tuple[int, int]) -> str:
    """Anschluss, über den eine gerade Strecke von ``a`` nach ``b`` in ``b`` ankommt."""
    return {"right": "left", "left": "right", "bottom": "top", "top": "bottom"}[_leaving_port(a, b)]


@dataclass
class _Corner:
    """Ein Eckpunkt, den nur der PapDesigner sieht: ein ``PapConnector`` in einer freien Rasterzelle."""
    cell: tuple[int, int]
    owner: str                  # Verbindung, für die er angelegt wurde (seine ID leitet sich davon ab)
    leads_to: str | None        # Ziel, zu dem er direkt weiterführt – dann dürfen weitere Pfeile hinein
    x: float = 0.0              # Lage für ältere Versionen dieses Programms (dort ein Verbindungspunkt)
    y: float = 0.0
    number: int = 0


def _pap_routes(elements: list[ElementData], cells: list[tuple[int, int]],
                connections: list[ConnectionData]) -> tuple[dict[str, list[_Corner]], list[_Corner]]:
    """Rechtwinklige Wege für den PapDesigner.

    Der PapDesigner zeichnet Verbindungen nur waagerecht oder senkrecht von Zelle zu Zelle; jede Ecke ist
    ein eigener Verbindungspunkt. Läuft der Ausgang einer Verzweigung schräg oder nach oben, öffnet er die
    ganze Datei nicht; andere schräge Linien zeichnet er schief und ohne Pfeil. Deshalb bekommt jede
    Verbindung, die nicht frei und gerade in Richtung ihres Anschlusses läuft, Eckpunkte in freien Zellen –
    so, dass keine Strecke über einen anderen Baustein führt. Pfeile zum selben Ziel teilen sich einen
    Eckpunkt, wo es passt (wie eine Zusammenführung im PapDesigner).

    Gibt je Verbindung ihre Eckpunkte (leer = gerade) und alle Eckpunkte in der Reihenfolge des Anlegens zurück.
    """
    cell_of = {element.id: cell for element, cell in zip(elements, cells)}
    point_of = {element.id: (_finite(element.x), _finite(element.y)) for element in elements}
    decisions = {element.id for element in elements if ElementType(element.type) is ElementType.DECISION}
    column_x = _axis_positions({c: _finite(e.x) for e, (c, _r) in zip(elements, cells)}, COLUMN_WIDTH)
    row_y = _axis_positions({r: _finite(e.y) for e, (_c, r) in zip(elements, cells)}, ROW_HEIGHT)
    taken = set(cells) | {(0, 0)}
    corners: dict[tuple[int, int], _Corner] = {}
    lines: set[tuple[int, int]] = set()  # Zellen, über die schon eine Linie läuft: dort kein neuer Eckpunkt
    used = list(cells) or [(0, 0)]
    extent = (max(c for c, _r in used) - min(c for c, _r in used)) + (max(r for _c, r in used)
                                                                         - min(r for _c, r in used)) + 4
    # Suchraum der Wegsuche: das Diagramm mit zwei Zellen Rand
    bounds = (min(c for c, _r in used) - 2, min(r for _c, r in used) - 2,
              max(c for c, _r in used) + 2, max(r for _c, r in used) + 2)
    routes: dict[str, list[_Corner]] = {}
    for connection in connections:
        source, target = cell_of.get(connection.source_id), cell_of.get(connection.target_id)
        if source is None or target is None:
            continue

        def free(cell) -> bool:
            return cell not in taken and cell not in corners and cell not in lines

        def shared(cell, target_id=connection.target_id) -> bool:
            corner = corners.get(cell)
            return corner is not None and corner.leads_to == target_id

        def blocked(cell) -> bool:
            return cell in taken or cell in corners

        way = _route_cells(source, target, connection.source_port, connection.source_id in decisions,
                           free, shared, blocked, extent + len(corners), bounds)
        (sx, sy), (tx, ty) = point_of[connection.source_id], point_of[connection.target_id]
        route = []
        for index, cell in enumerate(way):
            corner = corners.get(cell)
            if corner is None:
                last = index == len(way) - 1
                # Lage wie die Ecke der Linie: in der Spalte bzw. Zeile von Quelle oder Ziel, sonst im Raster
                x = sx if cell[0] == source[0] else tx if cell[0] == target[0] else column_x(cell[0])
                y = sy if cell[1] == source[1] else ty if cell[1] == target[1] else row_y(cell[1])
                corner = _Corner(cell, connection.id, connection.target_id if last else None, x, y)
                corners[cell] = corner
            route.append(corner)
        routes[connection.id] = route
        hops = [source] + way + [target]
        for a, b in zip(hops, hops[1:]):
            lines.update(_cells_between(a, b))
    return routes, list(corners.values())


def _cells_between(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Die Zellen zwischen zwei Zellen einer geraden Strecke (ohne die beiden selbst)."""
    if a[0] == b[0]:
        step = 1 if b[1] > a[1] else -1
        return [(a[0], row) for row in range(a[1] + step, b[1], step)]
    if a[1] == b[1]:
        step = 1 if b[0] > a[0] else -1
        return [(column, a[1]) for column in range(a[0] + step, b[0], step)]
    return []


def _route_cells(source: tuple[int, int], target: tuple[int, int], port: str, from_decision: bool,
                 free, shared, blocked, extent: int, bounds: tuple | None = None) -> list[tuple[int, int]]:
    """Zellen der Eckpunkte von ``source`` nach ``target`` (leer: die Verbindung läuft gerade).

    Bevorzugt wird – in dieser Reihenfolge – ein Weg, der ab der Quelle in Richtung ihres Anschlusses läuft und
    über keinen anderen Baustein führt, dann einer, der wenigstens frei ist, dann irgendein rechtwinkliger.
    """
    (cs, rs), (ct, rt) = source, target
    dx, dy = _PORT_DIRECTIONS.get(port, (0, 1))
    if from_decision and dy < 0:
        # nach oben verlässt im PapDesigner nichts eine Verzweigung: zur Seite des Ziels hinaus
        dx, dy = (1 if ct >= cs else -1), 0

    def clear(a, b) -> bool:
        """Liegt zwischen den Zellen ``a`` und ``b`` (gerade Strecke) kein Baustein und kein Eckpunkt?"""
        return not any(blocked(cell) for cell in _cells_between(a, b))

    def acceptable(way, strictness: int) -> bool:
        if any(cell in (source, target) for cell in way):
            return False
        if not all(free(cell) or (cell == way[-1] and shared(cell)) for cell in way):
            return False
        hops = [source] + way + [target]
        if any(a == b or (a[0] != b[0] and a[1] != b[1]) for a, b in zip(hops, hops[1:])):
            return False  # schräg (oder ohne Länge)
        first = hops[1]
        heading = ((first[0] > cs) - (first[0] < cs), (first[1] > rs) - (first[1] < rs))
        if from_decision and heading[1] < 0:
            return False  # aus einer Verzweigung nie nach oben
        if strictness >= 2 and heading != (dx, dy):
            return False
        return strictness < 1 or all(clear(a, b) for a, b in zip(hops, hops[1:]))

    candidates: list[list[tuple[int, int]]] = [[]] if source != target else []
    one_corner = [[(ct, rs)], [(cs, rt)]]
    candidates += one_corner[::-1] if dy else one_corner
    # zwei Ecken: ein Stück in eine Richtung (zuerst die des Anschlusses), dann quer zur Zeile bzw. Spalte des Ziels
    directions = [(dx, dy)] + [d for d in ((0, 1), (1, 0), (-1, 0), (0, -1)) if d != (dx, dy)]
    for ex, ey in directions:
        for step in range(1, extent + 1):
            first = (cs + ex * step, rs + ey * step)
            if first[0] == ct or first[1] == rt:
                candidates.append([first])
            else:
                candidates.append([first, (first[0], rt) if ex else (ct, first[1])])
    for strictness in (2, 1):
        for way in candidates:
            if acceptable(way, strictness):
                return way
    if bounds is not None:
        way = _search_way(source, target, (dx, dy), from_decision, free, blocked, bounds)
        if way is not None and acceptable(way, 1):
            return way
    for way in candidates:
        if acceptable(way, 0):
            return way
    # (kommt nicht vor: jenseits des ganzen Diagramms ist immer Platz) – sicherheitshalber gerade weiter hinaus
    step = extent + 1
    while not free((cs + dx * step, rs + dy * step)):
        step += 1
    first = (cs + dx * step, rs + dy * step)
    return [first, (first[0], rt) if dx else (ct, first[1])]


def _search_way(source, target, heading: tuple[int, int], from_decision: bool, free, blocked,
                bounds: tuple) -> list[tuple[int, int]] | None:
    """Kürzester rechtwinkliger Weg mit wenigen Ecken, der über keinen Baustein und keinen Eckpunkt läuft –
    für enge Stellen, an denen ein oder zwei Ecken nicht reichen. Gibt die Eckzellen zurück oder ``None``."""
    left, top, right, bottom = bounds
    turn_cost, wrong_start = 4, 6
    directions = ((0, 1), (1, 0), (-1, 0), (0, -1))
    # Zustand: (Zelle, Richtung, in der sie erreicht wurde); an der Quelle: die Richtung, in der es losgeht
    queue, best, parent = [], {}, {}
    for direction in directions:
        if from_decision and direction[1] < 0:
            continue  # aus einer Verzweigung nie nach oben
        state = (source, direction)
        best[state] = 0 if direction == heading else wrong_start
        parent[state] = None
        heapq.heappush(queue, (best[state], 0, state))
    order = 0
    while queue:
        cost, _order, state = heapq.heappop(queue)
        if cost > best.get(state, cost):
            continue
        cell, direction = state
        for turn in directions:
            if turn == (-direction[0], -direction[1]):
                continue  # nie zurück
            if turn != direction and (cell == source or not free(cell)):
                continue  # abbiegen nur in einer freien Zelle (dort entsteht der Eckpunkt)
            following = (cell[0] + turn[0], cell[1] + turn[1])
            if following == target:
                corners = [cell] if turn != direction else []
                node = state
                while parent[node] is not None:
                    previous = parent[node]
                    if previous[0] != source and previous[1] != node[1]:
                        corners.append(previous[0])
                    node = previous
                return corners[::-1]
            if not (left <= following[0] <= right and top <= following[1] <= bottom) or blocked(following):
                continue
            new_state = (following, turn)
            new_cost = cost + 1 + (turn_cost if turn != direction else 0)
            if new_cost < best.get(new_state, new_cost + 1):
                best[new_state] = new_cost
                parent[new_state] = state
                order += 1
                heapq.heappush(queue, (new_cost, order, new_state))
    return None


def _axis_positions(indices: dict[int, float], step: float):
    """Szenen-Koordinate einer Rasterspalte bzw. -zeile – auch für Spalten ohne Baustein (für Eckpunkte)."""
    known = sorted(indices)

    def position(index: int) -> float:
        if index in indices:
            return indices[index]
        nearest = min(known, key=lambda k: abs(k - index)) if known else 0
        return indices.get(nearest, 0.0) + (index - nearest) * step

    return position


def loop_partners(elements: list[ElementData], connections: list[ConnectionData]) -> dict[str, str]:
    """Zusammengehörige Schleifenbegrenzungen (Beginn ↔ Ende) entlang des Ablaufs."""
    parts = {e.id: (LOOP_END if e.properties.get(LOOP_PART_KEY) == LOOP_END else LOOP_BEGIN)
             for e in elements if ElementType(e.type) is ElementType.LOOP}
    if LOOP_BEGIN not in parts.values() or LOOP_END not in parts.values():
        return {}
    successors: dict[str, list[str]] = {}
    for connection in connections:
        successors.setdefault(connection.source_id, []).append(connection.target_id)
    partners: dict[str, str] = {}
    for begin in (e_id for e_id, part in parts.items() if part == LOOP_BEGIN):
        seen: set = set()
        stack = [(target, 0) for target in reversed(successors.get(begin, []))]
        while stack:
            node, depth = stack.pop()
            if (node, depth) in seen or depth > 32:
                continue
            seen.add((node, depth))
            part = parts.get(node)
            if part == LOOP_END:
                if depth == 0:
                    if node not in partners:
                        partners[begin], partners[node] = node, begin
                    break
                depth -= 1
            elif part == LOOP_BEGIN:
                depth += 1
            stack.extend((target, depth) for target in reversed(successors.get(node, [])))
    return partners


def _check_properties(value, depth: int = 0) -> None:
    """Stellt sicher, dass weitere Eigenschaften unverändert gespeichert werden können.

    Erlaubt sind Texte, Zahlen, Wahrheitswerte, ``None`` sowie Listen und
    Wörterbücher (mit Texten als Schlüssel) daraus. Wirft ``TypeError`` bzw.
    ``ValueError`` für alles andere, statt es stillschweigend umzuwandeln.
    """
    if depth > MAX_PROPERTY_DEPTH:
        raise ValueError("Eigenschaften sind zu tief verschachtelt.")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Eigenschaften dürfen keine unendlichen Zahlen enthalten.")
        return
    if isinstance(value, list):
        for entry in value:
            _check_properties(entry, depth + 1)
        return
    if isinstance(value, dict):
        for key, entry in value.items():
            if not isinstance(key, str):
                raise TypeError("Namen von Eigenschaften müssen Texte sein.")
            _check_properties(entry, depth + 1)
        return
    raise TypeError(f"Eigenschaft vom Typ {type(value).__name__} kann nicht gespeichert werden.")


def _figure_attributes(element: ElementData, number: int, associate: int | None) -> list:
    etype = ElementType(element.type)
    extra = dict(element.properties)
    _check_properties(extra)
    if etype is ElementType.LOOP:
        # Beginn/Ende steckt im SUBTYPE
        subtype = "PapLoopEnd" if extra.pop(LOOP_PART_KEY, LOOP_BEGIN) == LOOP_END else "PapLoopStart"
    else:
        subtype = _SUBTYPE_FOR_TYPE[etype]
    attributes = [("SUBTYPE", subtype), ("FORMAT", PAP_ELEMENT_FORMAT), ("ID", number)]
    if associate is not None:
        attributes.append(("ASSOCIATE", associate))
    attributes.append((_ext("UID"), element.id))
    for key, name in _TRUNK_ATTRIBUTES:
        if isinstance(extra.get(key), str):
            attributes.append((_ext(name), extra.pop(key)))
    if extra:
        attributes.append((_ext("PROPERTIES"), json.dumps(extra, ensure_ascii=False, sort_keys=True)))
    return attributes


def _connection_attributes(connection: ConnectionData, number: int, source: int, target: int,
                           first_hop: int | None = None) -> list:
    """Angaben einer Verbindung. ``first_hop``: Nummer ihres ersten Eckpunkts, wenn der PapDesigner sie über
    Eckpunkte geführt sieht – dann steht ihr eigentliches Ziel in ``bst:TO``, und Linienführung und -verlauf
    heißen ``bst:FULL_…`` (ältere Versionen dieses Programms lesen das Stück bis zum Eckpunkt als eigene
    Verbindung und sollen den Verlauf der ganzen Linie nicht darauf anwenden)."""
    split = first_hop is not None
    attributes = [("FORMAT", PAP_ELEMENT_FORMAT), ("ID", number), ("FROM", source),
                  ("TO", first_hop if split else target), ("TEXT", connection.label), (_ext("UID"), connection.id),
                  (_ext("SOURCE_PORT"), connection.source_port),
                  (_ext("TARGET_PORT"), connection.target_port)]
    if split:
        attributes.append((_ext("TO"), target))
    prefix = "FULL_" if split else ""
    routing = connection.routing if isinstance(connection.routing, dict) else {}
    if routing.get("mode") == "manual" and routing.get("axis") in ("x", "y"):
        value, ok = _number(routing.get("value"), 0.0)
        if ok:
            attributes += [(_ext(prefix + "ROUTE_AXIS"), routing["axis"]),
                           (_ext(prefix + "ROUTE_VALUE"), _format_number(value))]
    path = _valid_path(connection.path)
    if path:
        attributes.append((_ext(prefix + "PATH"),
                           " ".join(f"{_format_number(x)},{_format_number(y)}" for x, y in path)))
    return attributes


def _valid_path(points) -> list | None:
    """Linienverlauf als Liste von (x, y) – oder ``None``, wenn er nicht verwendbar ist."""
    try:
        path = [(float(x), float(y)) for x, y in points]
    except (TypeError, ValueError):
        return None
    if len(path) < 2 or not all(math.isfinite(x) and math.isfinite(y) for x, y in path):
        return None
    return path


def diagram_to_xml(diagram: Diagram) -> str:
    """Das Diagramm als Inhalt einer ``.pap``-Datei.

    Das Hauptprogramm ist das erste ``DIAGRAM``, jedes Unterprogramm folgt als eigenes ``DIAGRAM``
    (wie im PapDesigner). Die Nummern (``ID``) zählen – wie beim PapDesigner – in jedem Diagramm neu ab 0
    (dem Titel).
    """
    meta, settings = diagram.meta, diagram.settings
    created, modified = _pap_timestamp(meta.created), _pap_timestamp(meta.modified)

    out = ['<?xml version="1.0" encoding="utf-8"?>']
    out.append(_tag("FRAME", [
        ("GUID", PAP_FRAME_GUID), ("FORMAT", PAP_FRAME_FORMAT), ("APP_VERSION", PAP_APP_VERSION),
        ("CHECKSUM", PAP_CHECKSUM), (f"xmlns:{EXTENSION_PREFIX}", EXTENSION_NAMESPACE),
        (_ext("VERSION"), format_version_for(diagram)), (_ext("APP"), config.APP_NAME),
        (_ext("APP_VERSION"), config.APP_VERSION)], 0))
    out.append(_tag("PROJECT", [
        ("FORMAT", PAP_ELEMENT_FORMAT), ("NAME", meta.name), ("AUTHOR", meta.author),
        ("CREATED", created), ("MODIFIED", modified), (_ext("DESCRIPTION"), meta.description),
        (_ext("CREATED"), meta.created), (_ext("MODIFIED"), meta.modified)], 1))
    out.append(_tag("DIAGRAMS", [], 2))
    grid = [(_ext("GRID_SIZE"), int(settings.grid_size)),
            (_ext("GRID_VISIBLE"), _format_flag(settings.grid_visible)),
            (_ext("SNAP_TO_GRID"), _format_flag(settings.snap_to_grid))]
    _write_diagram(out, 0, meta.name, diagram.elements, diagram.connections, grid,
                   (settings.zoom, settings.view_center_x, settings.view_center_y), created, modified)
    for index, page in enumerate(diagram.subprograms, start=1):
        _write_diagram(out, index, page.name, page.elements, page.connections, [],
                       (page.zoom, page.view_center_x, page.view_center_y), created, modified)
    out.append(f"{'  ' * 2}</DIAGRAMS>")
    out.append("  </PROJECT>")
    out.append("</FRAME>")
    return "\n".join(out) + "\n"


def format_version_for(diagram: Diagram) -> int:
    """Version der Zusatzangaben: so niedrig wie möglich, damit ältere Programmversionen die Datei öffnen, wo
    sie es ohne Verlust können (Version 1 ohne Unterprogramm-Seiten, 2 mit, 3 mit Kommentarlinien)."""
    if any(_has_comment_lines(elements, connections) for elements, connections in
           [(diagram.elements, diagram.connections)] + [(p.elements, p.connections) for p in diagram.subprograms]):
        return CURRENT_FORMAT_VERSION
    return SUBPROGRAM_FORMAT_VERSION if diagram.subprograms else SINGLE_PAGE_FORMAT_VERSION


def _has_comment_lines(elements, connections) -> bool:
    comments = {element.id for element in elements if ElementType(element.type) is ElementType.COMMENT}
    return any(c.source_id in comments or c.target_id in comments for c in connections)


def _write_diagram(out: list, index: int, name: str, elements, connections, grid: list, view: tuple,
                   created: str, modified: str, title_number: int = 0) -> int:
    """Schreibt ein ``DIAGRAM`` (eine Seite). Gibt die zuletzt vergebene Nummer zurück."""
    elements, connections = list(elements), list(connections)
    cells = _grid_cells(elements)
    # Kommentarlinien kennt der PapDesigner nicht (er zeichnete sie als Ablaufpfeil): Sie stehen nur in den
    # Zusatzangaben, mit ihrer Stelle in der Reihenfolge aller Verbindungen
    comments = {element.id for element in elements if ElementType(element.type) is ElementType.COMMENT}
    notes = [(position, connection) for position, connection in enumerate(connections)
             if connection.source_id in comments or connection.target_id in comments]
    noted = {id(connection) for _position, connection in notes}
    connections = [connection for connection in connections if id(connection) not in noted]
    routes, corners = _pap_routes(elements, cells, connections)
    # Der PapDesigner braucht Zeile 0 für den Titel und keine negativen Zellen: alles passend verschieben
    used = cells + [corner.cell for corner in corners]
    shift_column = -min((column for column, _row in used), default=0)
    shift_row = max(0, 1 - min((row for _column, row in used), default=1))
    placed = [(column + shift_column, row + shift_row) for column, row in cells]
    # Nummern des PapDesigners: Titel, dann Bausteine, dann Eckpunkte, dann Verbindungen
    numbers: dict[str, int] = {}
    for number, element in enumerate(elements, start=title_number + 1):
        numbers.setdefault(element.id, number)
    for number, corner in enumerate(corners, start=title_number + len(elements) + 1):
        corner.number = number
    partners = loop_partners(elements, connections)
    zoom, view_x, view_y = view
    every_cell = placed + [(c + shift_column, r + shift_row) for c, r in (corner.cell for corner in corners)]
    out.append(_tag("DIAGRAM", [("FORMAT", PAP_ELEMENT_FORMAT), ("ID", index), ("NAME", name),
                                ("CREATED", created), ("MODIFIED", modified)], 3))
    out.append(_tag("LAYOUT", [
        ("FORMAT", PAP_ELEMENT_FORMAT),
        ("COLUMNS", max((column for column, _row in every_cell), default=0) + 1),
        ("ROWS", max((row for _column, row in every_cell), default=0) + 1),
        *grid,
        (_ext("ZOOM"), _format_number(zoom)),
        (_ext("VIEW_X"), _format_number(view_x)),
        (_ext("VIEW_Y"), _format_number(view_y))], 4))
    out.append(_tag("ENTRIES", [], 5))
    # Der PapDesigner erwartet je Diagramm einen Titel als Ankerzelle. Er ist
    # kein Baustein des Projekts und wird beim Laden übersprungen.
    out.append(_tag("ENTRY", [("COLUMN", 0), ("ROW", 0), ("ANCHOR", "True"), (_ext("GENERATED"), "True")], 6))
    out.append(_tag("FIGURE", [("SUBTYPE", "PapTitle"), ("FORMAT", PAP_ELEMENT_FORMAT), ("ID", title_number)], 7))
    out.append(f"{'  ' * 8}<TEXT>{_text_content(name)}</TEXT>")
    out.append(f"{'  ' * 7}</FIGURE>")
    out.append(f"{'  ' * 6}</ENTRY>")
    for number, (element, (column, row)) in enumerate(zip(elements, placed), start=title_number + 1):
        entry = [("COLUMN", column), ("ROW", row),
                 (_ext("X"), _format_number(element.x)), (_ext("Y"), _format_number(element.y)),
                 (_ext("WIDTH"), _format_number(element.width)),
                 (_ext("HEIGHT"), _format_number(element.height))]
        if float(element.z) != 0.0:
            entry.append((_ext("Z"), _format_number(element.z)))
        out.append(_tag("ENTRY", entry, 6))
        out.append(_tag("FIGURE", _figure_attributes(element, number, numbers.get(partners.get(element.id))), 7))
        out.append(f"{'  ' * 8}<TEXT>{_text_content(element.text)}</TEXT>")
        out.append(f"{'  ' * 7}</FIGURE>")
        out.append(f"{'  ' * 6}</ENTRY>")
    # Eckpunkte: für den PapDesigner Verbindungspunkte, für dieses Programm Teil der Verbindung (bst:CORNER).
    # Sie tragen Lage und ID, damit ältere Versionen sie als gewöhnliche Verbindungspunkte lesen.
    junction = spec_for(ElementType.JUNCTION)
    for corner in corners:
        column, row = corner.cell
        out.append(_tag("ENTRY", [("COLUMN", column + shift_column), ("ROW", row + shift_row),
                                  (_ext("X"), _format_number(corner.x)),
                                  (_ext("Y"), _format_number(corner.y)),
                                  (_ext("WIDTH"), _format_number(junction.default_width)),
                                  (_ext("HEIGHT"), _format_number(junction.default_height)),
                                  (_ext("CORNER"), "True")], 6))
        out.append(_tag("FIGURE", [("SUBTYPE", "PapConnector"), ("FORMAT", PAP_ELEMENT_FORMAT),
                                   ("ID", corner.number), (_ext("UID"), f"{corner.owner}.{corner.number}")], 7))
        out.append(f"{'  ' * 8}<TEXT></TEXT>")
        out.append(f"{'  ' * 7}</FIGURE>")
        out.append(f"{'  ' * 6}</ENTRY>")
    out.append(f"{'  ' * 5}</ENTRIES>")
    out.append(f"{'  ' * 4}</LAYOUT>")
    annotations = []
    for position, connection in notes:
        source, target = numbers.get(connection.source_id), numbers.get(connection.target_id)
        if source is not None and target is not None:
            attributes = dict(_connection_attributes(connection, 0, source, target))
            attributes.pop("FORMAT"), attributes.pop("ID")
            annotations.append({"index": position, "attributes": attributes})
    out.append(_tag("CONNECTIONS", [(_ext("ANNOTATIONS"), json.dumps(annotations, ensure_ascii=False))]
                    if annotations else [], 4))
    number = title_number + len(elements) + len(corners)
    leaving: set[int] = set()  # Eckpunkte, deren Weg zum Ziel schon geschrieben ist
    by_id = {element.id: element for element in elements}
    cell_of = {element.id: cell for element, cell in zip(elements, cells)}
    for connection in connections:
        source, target = numbers.get(connection.source_id), numbers.get(connection.target_id)
        if source is None or target is None:
            continue  # ohne vorhandenen Baustein nicht darstellbar (würde beim Laden entfernt)
        route = routes.get(connection.id, [])
        number += 1
        if not route:
            out.append(_tag("CONNECTION", _connection_attributes(connection, number, source, target), 5,
                            empty=True))
            continue
        # Ältere Versionen dieses Programms lesen die Teilstrecken als eigene Verbindungen über Verbindungspunkte.
        # Ist das Ziel ein Verbindungspunkt, der an dieser Verbindung ausgerichtet ist (bst:TRUNK_IN), trägt für
        # sie das letzte Stück die ID der Verbindung – dieses Programm liest sie aus bst:FULL_UID.
        end_element = by_id.get(connection.target_id)
        trunk_last = (end_element is not None and ElementType(end_element.type) is ElementType.JUNCTION
                      and end_element.properties.get(TRUNK_IN_KEY) == connection.id)
        cells_on_way = [cell_of[connection.source_id]] + [corner.cell for corner in route] + \
            [cell_of[connection.target_id]]
        attributes = _connection_attributes(connection, number, source, target, route[0].number)
        attributes = [(name, _arriving_port(cells_on_way[0], cells_on_way[1]) if name == _ext("TARGET_PORT")
                       else f"{connection.id}.a" if name == _ext("UID") and trunk_last else value)
                      for name, value in attributes]
        attributes.append((_ext("FULL_TARGET_PORT"), connection.target_port))
        if trunk_last:
            attributes.append((_ext("FULL_UID"), connection.id))
        out.append(_tag("CONNECTION", attributes, 5, empty=True))
        hops = [corner.number for corner in route] + [target]
        for step, (start, end) in enumerate(zip(hops, hops[1:]), start=1):
            if start in leaving:
                break  # ab hier teilt sie den Weg einer anderen Verbindung
            leaving.add(start)
            number += 1
            last = step == len(hops) - 1
            a, b = cells_on_way[step], cells_on_way[step + 1]
            uid = connection.id if last and trunk_last else f"{connection.id}.{number}"
            out.append(_tag("CONNECTION", [
                ("FORMAT", PAP_ELEMENT_FORMAT), ("ID", number), ("FROM", start), ("TO", end), ("TEXT", ""),
                (_ext("UID"), uid), (_ext("SOURCE_PORT"), _leaving_port(a, b)),
                (_ext("TARGET_PORT"), connection.target_port if last else _arriving_port(a, b)),
                (_ext("CORNER"), "True")], 5, empty=True))
    out.append(f"{'  ' * 4}</CONNECTIONS>")
    out.append(f"{'  ' * 3}</DIAGRAM>")
    return number


# ------------------------------------------------------------------ Lesen
class _NoDoctypeBuilder(ET.TreeBuilder):
    """Lehnt Dokumenttyp-Definitionen (und damit eigene Entitäten) ab."""

    def doctype(self, name, pubid, system):
        raise ProjectFileError(tr("Die Datei enthält nicht unterstützte XML-Definitionen."))


def _parse(raw: bytes):
    parser = ET.XMLParser(target=_NoDoctypeBuilder())
    try:
        parser.feed(raw)
        return parser.close()
    except ProjectFileError:
        raise
    except Exception as exc:  # ParseError, unbekannte Kodierung, …
        # XML beginnt (nach einer Kodierungsmarke) immer mit „<“
        looks_like_xml = raw.lstrip(b"\xef\xbb\xbf\xff\xfe\x00 \t\r\n")[:1] == b"<"
        if looks_like_xml:
            message = tr("Die Datei ist beschädigt und kann nicht gelesen werden.")
        else:
            message = tr("Die Datei ist kein Programmablaufplan im Format .pap.")
        raise ProjectFileError(message, str(exc)) from exc


def _meta_from(project, native: bool, fallback_name: str) -> ProjectMeta:
    meta = ProjectMeta()
    name, author = project.get("NAME") or "", project.get("AUTHOR") or ""
    if not native:
        name, author = name.strip(), author.strip()
    meta.name = name if name.strip() else (fallback_name.strip() or config.DEFAULT_PROJECT_NAME)
    meta.author = author
    meta.description = (project.get(_key("DESCRIPTION")) or "") if native else ""
    meta.created = (project.get(_key("CREATED")) if native else None) or _timestamp(project.get("CREATED"))
    meta.modified = ((project.get(_key("MODIFIED")) if native else None)
                     or _timestamp(project.get("MODIFIED"), meta.created))
    return meta


def _settings_from(layout, warnings: list) -> DiagramSettings:
    settings = DiagramSettings()
    if layout is None:
        return settings
    raw_grid = layout.get(_key("GRID_SIZE"))
    if raw_grid is not None:
        grid, ok = _number(raw_grid, config.DEFAULT_GRID_SIZE)
        if not ok or not grid.is_integer() or not (config.MIN_GRID_SIZE <= grid <= config.MAX_GRID_SIZE):
            warnings.append(tr("Eine ungültige Rastergröße wurde auf den Standardwert gesetzt."))
            grid = config.DEFAULT_GRID_SIZE
        settings.grid_size = int(grid)
    settings.grid_visible = _flag(layout.get(_key("GRID_VISIBLE")), config.DEFAULT_GRID_VISIBLE)
    settings.snap_to_grid = _flag(layout.get(_key("SNAP_TO_GRID")), config.DEFAULT_SNAP_TO_GRID)
    zoom, _ = _number(layout.get(_key("ZOOM")), 1.0)
    settings.zoom = max(config.MIN_ZOOM, min(config.MAX_ZOOM, zoom))
    settings.view_center_x, _ = _number(layout.get(_key("VIEW_X")), 0.0)
    settings.view_center_y, _ = _number(layout.get(_key("VIEW_Y")), 0.0)
    return settings


def _figure_text(figure, native: bool) -> str:
    node = figure.find("TEXT")
    text = node.text if node is not None and node.text else ""
    if native:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _properties_from(figure, etype: ElementType, subtype: str, native: bool, warnings: list) -> dict:
    properties = default_properties_for(etype)
    if native:
        raw = figure.get(_key("PROPERTIES"))
        if raw:
            try:
                extra = json.loads(raw)
                if not isinstance(extra, dict):
                    raise ValueError("kein Objekt")
                _check_properties(extra)
            except (TypeError, ValueError, RecursionError):
                warnings.append(tr("Ungültige Zusatzeigenschaften eines Bausteins wurden verworfen."))
            else:
                properties.update(extra)
        for key, name in _TRUNK_ATTRIBUTES:
            value = figure.get(_key(name))
            if value is not None:
                properties[key] = value
            elif not isinstance(properties.get(key, ""), str):
                # Verweise auf Verbindungen sind immer IDs (Texte)
                del properties[key]
                warnings.append(tr("Ungültige Zusatzeigenschaften eines Bausteins wurden verworfen."))
    if etype is ElementType.LOOP:
        properties[LOOP_PART_KEY] = LOOP_END if subtype == "PapLoopEnd" else LOOP_BEGIN
    return properties


def _annotation_nodes(container, warnings: list) -> list:
    """Kommentarlinien aus ``bst:ANNOTATIONS``: (Stelle, Angaben wie ein ``CONNECTION``) – oder leer."""
    raw = container.get(_key("ANNOTATIONS")) if container is not None else None
    if raw is None:
        return []
    try:
        entries = json.loads(raw)
        nodes = []
        for entry in entries:
            attributes = {}
            for name, value in entry["attributes"].items():
                prefix, _colon, local = str(name).partition(":")
                attributes[_key(local) if prefix == EXTENSION_PREFIX and local else str(name)] = str(value)
            nodes.append((int(entry["index"]), ET.Element("CONNECTION", attributes)))
        return nodes
    except (TypeError, ValueError, KeyError, AttributeError):
        warnings.append(tr("Ungültige Angaben zu Kommentarlinien wurden übersprungen."))
        return []


def _routing_from(node, native: bool, warnings: list, prefix: str = "") -> dict:
    axis = node.get(_key(prefix + "ROUTE_AXIS")) if native else None
    if axis is None:
        return {"mode": "auto"}
    value, ok = _number(node.get(_key(prefix + "ROUTE_VALUE")), 0.0)
    if axis in ("x", "y") and ok:
        return {"mode": "manual", "axis": axis, "value": value}
    warnings.append(tr("Eine ungültige Linienführung wurde auf „automatisch“ zurückgesetzt."))
    return {"mode": "auto"}


def _path_from(node, native: bool, warnings: list, prefix: str = "") -> list | None:
    raw = node.get(_key(prefix + "PATH")) if native else None
    if raw is None:
        return None
    try:
        path = _valid_path([point.split(",") for point in raw.split()])
    except ValueError:  # Punkt ohne genau zwei Angaben
        path = None
    if path is None:
        warnings.append(tr("Ein ungültiger Linienverlauf wurde verworfen; die Linie wird neu geführt."))
    return path


def _size_from(entry, native: bool, default_width: float, default_height: float, warnings: list) -> tuple:
    """Größe eines Bausteins; ungültige oder nicht positive Angaben → Standardgröße."""
    result = []
    for name, default in (("WIDTH", default_width), ("HEIGHT", default_height)):
        raw = entry.get(_key(name)) if native else None
        value, ok = _number(raw, default)
        if raw is not None and (not ok or value <= 0):
            warnings.append(tr("Eine ungültige Größe wurde auf die Standardgröße gesetzt."))
            value = float(default)
        result.append(max(1.0, value))
    return tuple(result)


def _grid_ports(etype: ElementType, source_cell, target_cell, used: set) -> tuple[str, str]:
    """Anschlüsse aus der Lage der Rasterzellen bestimmen."""
    (c1, r1), (c2, r2) = source_cell, target_cell
    dx, dy = c2 - c1, r2 - r1
    if dy > 0 and dx == 0:
        source, target = "bottom", "top"
    elif dy > 0:
        source = ("right" if dx > 0 else "left") if etype is ElementType.DECISION else "bottom"
        target = "top"
    elif dy == 0 and dx != 0:
        source, target = ("right", "left") if dx > 0 else ("left", "right")
    else:  # Rücksprung nach oben (Schleife)
        side = "right" if dx > 0 else "left"
        source, target = side, side
    if etype is ElementType.DECISION and source in used:
        source = next((p for p in ("bottom", "right", "left") if p not in used), source)
    return source, target


def _fit_port(port: str, etype: ElementType, fallbacks: tuple) -> str:
    ports = spec_for(etype).ports
    if port in ports:
        return port
    return next((p for p in fallbacks if p in ports), ports[0])


def _page_from(pap_diagram, layout, native: bool) -> SubprogramPage:
    """Eine Unterprogramm-Seite mit Namen und – bei eigenen Dateien – ihrer Ansicht (noch ohne Inhalt)."""
    name = pap_diagram.get("NAME") or ""
    page = SubprogramPage(name=name if native and name.strip() else " ".join(name.split()))
    if native and layout is not None:
        zoom, _ = _number(layout.get(_key("ZOOM")), 1.0)
        page.zoom = max(config.MIN_ZOOM, min(config.MAX_ZOOM, zoom))
        page.view_center_x, _ = _number(layout.get(_key("VIEW_X")), 0.0)
        page.view_center_y, _ = _number(layout.get(_key("VIEW_Y")), 0.0)
    return page


def _page_name_from(elements: list[ElementData], number: int) -> str:
    """Name einer Seite ohne Namen: der Text ihres Start-Elements, sonst „Unterprogramm 2“ usw."""
    for element in elements:
        if element.type is ElementType.START and element.text.strip():
            return " ".join(element.text.split())
    return tr("Unterprogramm {number}", number=number)


def diagram_from_xml(raw: bytes | str, fallback_name: str = "") -> LoadResult:
    """Liest den Inhalt einer ``.pap``-Datei. Wirft ``ProjectFileError``."""
    try:
        return _read_project(raw, fallback_name)
    except ProjectFileError:
        raise
    except Exception as exc:  # letzte Absicherung gegen unerwartete Inhalte
        raise ProjectFileError(tr("Die Datei ist beschädigt oder inkompatibel."), repr(exc)) from exc


def _read_project(raw: bytes | str, fallback_name: str) -> LoadResult:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    raw = bytes(raw)
    if not raw.strip():
        raise ProjectFileError(tr("Die Datei ist leer oder beschädigt."))
    if raw[:1] in b" \t\r\n" and raw.lstrip(b" \t\r\n")[:1] == b"<":
        raw = raw.lstrip(b" \t\r\n")  # Leerzeilen vor dem Inhalt stören den XML-Parser
    root = _parse(raw)
    project = root if root.tag == "PROJECT" else root.find("PROJECT")
    if root.tag not in ("FRAME", "PROJECT") or project is None:
        raise ProjectFileError(tr("Die Datei ist keine PAP-Datei."))
    native = check_version(root.get(_key("VERSION")))

    warnings: list[str] = []
    layout = project.find("./DIAGRAMS/DIAGRAM/LAYOUT") if native else None
    diagram = Diagram(meta=_meta_from(project, native, fallback_name),
                      settings=_settings_from(layout, warnings))
    seen_ids: set[str] = set()
    seen_connections: set[str] = set()
    unknown_types: set[str] = set()
    figure_count = 0
    limit = config.SCENE_HALF_EXTENT - 1000
    for index, pap_diagram in enumerate(project.findall("./DIAGRAMS/DIAGRAM")):
        layout = pap_diagram.find("LAYOUT")
        # Das erste Diagramm ist das Hauptprogramm, jedes weitere eine Unterprogramm-Seite
        if index == 0:
            elements, connections = diagram.elements, diagram.connections
        else:
            page = _page_from(pap_diagram, layout, native)
            diagram.subprograms.append(page)
            elements, connections = page.elements, page.connections
        # Nummer des PapDesigners → (Baustein, Rasterzelle)
        figures: dict[str, tuple[ElementData, tuple[int, int]]] = {}
        for entry in pap_diagram.findall("./LAYOUT/ENTRIES/ENTRY"):
            figure = entry.find("FIGURE")
            if figure is None:
                continue
            figure_count += 1
            if native and (_flag(entry.get(_key("GENERATED")), False) or _flag(entry.get(_key("CORNER")), False)):
                continue  # Titel bzw. Eckpunkt, den nur der PapDesigner braucht
            page_name = " ".join((pap_diagram.get("NAME") or "").split())
            if (not native and index > 0 and figure.get("SUBTYPE") == "PapTitle"
                    and " ".join(_figure_text(figure, False).split()) == page_name):
                # Titel einer Unterprogramm-Seite: der Name steht im Reiter und wird beim Speichern neu geschrieben
                continue
            number = _reference(figure.get("ID")) or f"auto{len(figures)}"
            if number in figures:
                warnings.append(tr("Ein doppelt vergebener Baustein wurde übersprungen."))
                continue
            subtype = figure.get("SUBTYPE", "")
            etype = SUBTYPES.get(subtype)
            if etype is None:
                unknown_types.add(subtype or "?")
                etype = ElementType.PROCESS
            spec = spec_for(etype)
            column, row = _attr_int(entry, "COLUMN"), _attr_int(entry, "ROW")
            x, y, placed = column * COLUMN_WIDTH, row * ROW_HEIGHT, False
            if native:
                exact_x, ok_x = _number(entry.get(_key("X")), x)
                exact_y, ok_y = _number(entry.get(_key("Y")), y)
                if ok_x and ok_y:
                    x, y, placed = exact_x, exact_y, True
                else:
                    warnings.append(tr("Ein Element mit ungültiger Position wurde nach dem Raster "
                                       "der Datei eingeordnet."))
            if not placed:
                # Positionen aus dem Raster auf das Zeichenraster (20) setzen
                x, y = round(x / 20) * 20, round(y / 20) * 20
            if abs(x) > limit or abs(y) > limit:
                warnings.append(tr("Bausteine außerhalb der Arbeitsfläche wurden an deren Rand gesetzt."))
                x, y = max(-limit, min(limit, x)), max(-limit, min(limit, y))
            width, height = _size_from(entry, native, spec.default_width, spec.default_height, warnings)
            raw_z = entry.get(_key("Z")) if native else None
            z, ok_z = _number(raw_z, 0.0)
            if raw_z is not None and not ok_z:
                warnings.append(tr("Eine ungültige Ebene eines Bausteins wurde zurückgesetzt."))
            element_id = figure.get(_key("UID")) if native else None
            if not element_id or not element_id.strip():
                if native:
                    warnings.append(tr("Ein Element ohne gültige ID hat eine neue ID erhalten."))
                element_id = new_id()
            if element_id in seen_ids:
                warnings.append(tr("Ein Element mit doppelter ID hat eine neue ID erhalten."))
                element_id = new_id()
            seen_ids.add(element_id)
            element = ElementData(
                id=element_id,
                type=etype,
                x=x,
                y=y,
                width=width,
                height=height,
                text=_figure_text(figure, native),
                z=z,
                properties=_properties_from(figure, etype, subtype, native, warnings),
            )
            figures[number] = (element, (column, row))
            elements.append(element)

        used_ports: dict[str, set] = {}
        nodes = [(None, node) for node in pap_diagram.findall("./CONNECTIONS/CONNECTION")]
        if native:
            nodes += _annotation_nodes(pap_diagram.find("CONNECTIONS"), warnings)
        placed: list[tuple[int, ConnectionData]] = []
        flow_start = len(connections)
        for position, node in nodes:
            if native and _flag(node.get(_key("CORNER")), False):
                continue  # Teilstrecke zwischen Eckpunkten: gehört zur Verbindung davor
            split = native and node.get(_key("TO")) is not None
            source = figures.get(_reference(node.get("FROM")))
            target = figures.get(_reference(node.get(_key("TO")) if split else node.get("TO")))
            if source is None or target is None:
                warnings.append(tr("Eine Verbindung zu einem nicht vorhandenen Element wurde entfernt."))
                continue
            (s_elem, s_cell), (t_elem, t_cell) = source, target
            s_port = node.get(_key("SOURCE_PORT")) if native else None
            t_port = None
            if native:
                t_port = (split and node.get(_key("FULL_TARGET_PORT"))) or node.get(_key("TARGET_PORT"))
            if s_port in ALL_PORTS and t_port in ALL_PORTS:
                if s_elem is t_elem and s_port == t_port:
                    warnings.append(tr("Eine Verbindung ohne Länge (gleicher Anschluss) wurde entfernt."))
                    continue
            else:
                # ohne (gültige) gespeicherte Anschlüsse: aus der Lage im Raster ableiten
                if s_port is not None or t_port is not None:
                    warnings.append(tr("Ungültige Anschlüsse einer Verbindung wurden neu bestimmt."))
                if s_elem is t_elem:
                    warnings.append(tr("Eine Verbindung eines Bausteins mit sich selbst wurde übersprungen."))
                    continue
                used = used_ports.setdefault(s_elem.id, set())
                s_port, t_port = _grid_ports(s_elem.type, s_cell, t_cell, used)
                s_port = _fit_port(s_port, s_elem.type, ("bottom", "right", "left", "top"))
                t_port = _fit_port(t_port, t_elem.type, ("top", "left", "right", "bottom"))
                used.add(s_port)
            connection_id = (node.get(_key("FULL_UID")) or node.get(_key("UID"))) if native else None
            if not connection_id or not connection_id.strip() or connection_id in seen_connections:
                connection_id = new_id()
            seen_connections.add(connection_id)
            label = node.get("TEXT") or ""
            connection = ConnectionData(
                id=connection_id,
                source_id=s_elem.id,
                target_id=t_elem.id,
                source_port=s_port,
                target_port=t_port,
                label=label if native else label.strip(),
                routing=_routing_from(node, native, warnings, "FULL_" if split else ""),
                path=_path_from(node, native, warnings, "FULL_" if split else ""),
            )
            if position is None:
                connections.append(connection)
            else:
                placed.append((position, connection))
        for position, connection in sorted(placed, key=lambda item: item[0]):
            connections.insert(flow_start + min(max(position, 0), len(connections) - flow_start), connection)
        if index > 0 and not diagram.subprograms[-1].name:
            diagram.subprograms[-1].name = _page_name_from(elements, len(diagram.subprograms))

    if not native and figure_count == 0:
        # Nur ein mit diesem Programm gespeichertes Projekt darf leer sein
        raise ProjectFileError(tr("Die Datei enthält keinen Programmablaufplan."))
    if unknown_types:
        warnings.append(tr("Unbekannte Bausteintypen wurden als Vorgang übernommen: {types}",
                           types=", ".join(sorted(unknown_types))))
    return LoadResult(diagram=diagram, warnings=_dedupe(warnings), native=native)


# ---------------------------------------------------------------- Dateien
def save_diagram(diagram: Diagram, path: str) -> None:
    """Speichert atomar. Wirft ``ProjectFileError`` mit verständlicher Meldung."""
    try:
        payload = diagram_to_xml(diagram).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(tr("Das Projekt konnte nicht in das Dateiformat umgewandelt werden."),
                               str(exc)) from exc
    directory = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(directory):
        raise ProjectFileError(tr("Der Ordner „{directory}“ existiert nicht.", directory=directory))
    fd, temp_path = None, None
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".pap-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except PermissionError as exc:
        raise ProjectFileError(tr("Die Datei konnte nicht gespeichert werden: Keine Schreibberechtigung "
                                  "(ist die Datei schreibgeschützt oder in einem anderen Programm geöffnet?)."),
                               str(exc)) from exc
    except OSError as exc:
        raise ProjectFileError(tr("Die Datei konnte nicht gespeichert werden: {reason}", reason=exc.strerror or exc),
                               str(exc)) from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def load_diagram(path: str) -> LoadResult:
    """Lädt eine Projektdatei. Wirft ``ProjectFileError`` mit verständlicher Meldung."""
    try:
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE:
            raise ProjectFileError(tr("Die Datei ist zu groß, um als Projekt geöffnet zu werden."))
        with open(path, "rb") as handle:
            raw = handle.read()
    except ProjectFileError:
        raise
    except FileNotFoundError as exc:
        raise ProjectFileError(tr("Die Datei „{path}“ wurde nicht gefunden.", path=path), str(exc)) from exc
    except IsADirectoryError as exc:
        raise ProjectFileError(tr("„{path}“ ist ein Ordner und keine Projektdatei.", path=path), str(exc)) from exc
    except PermissionError as exc:
        raise ProjectFileError(tr("Keine Berechtigung, die Datei zu lesen."), str(exc)) from exc
    except (OSError, ValueError) as exc:  # ValueError: unzulässige Zeichen im Pfad
        raise ProjectFileError(tr("Die Datei konnte nicht gelesen werden: {reason}",
                                  reason=getattr(exc, "strerror", None) or exc), str(exc)) from exc
    return diagram_from_xml(raw, os.path.splitext(os.path.basename(path))[0])
