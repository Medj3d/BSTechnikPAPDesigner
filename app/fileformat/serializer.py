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
abgeleitet; mehrere Diagramme einer solchen Datei (Hauptprogramm,
Unterprogramme) werden nebeneinander angeordnet.

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
                                    ProjectFileError, check_version)
from app.i18n import tr
from app.model.diagram import (ConnectionData, Diagram, DiagramSettings, ElementData,
                               ProjectMeta, new_id, now_iso)
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
DIAGRAM_GAP_COLUMNS = 1.5
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


def _loop_partners(elements: list[ElementData], connections: list[ConnectionData]) -> dict[str, str]:
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


def _connection_attributes(connection: ConnectionData, number: int, source: int, target: int) -> list:
    attributes = [("FORMAT", PAP_ELEMENT_FORMAT), ("ID", number), ("FROM", source), ("TO", target),
                  ("TEXT", connection.label), (_ext("UID"), connection.id),
                  (_ext("SOURCE_PORT"), connection.source_port),
                  (_ext("TARGET_PORT"), connection.target_port)]
    routing = connection.routing if isinstance(connection.routing, dict) else {}
    if routing.get("mode") == "manual" and routing.get("axis") in ("x", "y"):
        value, ok = _number(routing.get("value"), 0.0)
        if ok:
            attributes += [(_ext("ROUTE_AXIS"), routing["axis"]), (_ext("ROUTE_VALUE"), _format_number(value))]
    path = _valid_path(connection.path)
    if path:
        attributes.append((_ext("PATH"), " ".join(f"{_format_number(x)},{_format_number(y)}" for x, y in path)))
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
    """Das Diagramm als Inhalt einer ``.pap``-Datei."""
    meta, settings = diagram.meta, diagram.settings
    elements, connections = list(diagram.elements), list(diagram.connections)
    cells = _grid_cells(elements)
    # Nummern des PapDesigners: 0 = Titel, dann Bausteine, dann Verbindungen
    numbers: dict[str, int] = {}
    for number, element in enumerate(elements, start=1):
        numbers.setdefault(element.id, number)
    partners = _loop_partners(elements, connections)
    created, modified = _pap_timestamp(meta.created), _pap_timestamp(meta.modified)

    out = ['<?xml version="1.0" encoding="utf-8"?>']
    out.append(_tag("FRAME", [
        ("GUID", PAP_FRAME_GUID), ("FORMAT", PAP_FRAME_FORMAT), ("APP_VERSION", PAP_APP_VERSION),
        ("CHECKSUM", PAP_CHECKSUM), (f"xmlns:{EXTENSION_PREFIX}", EXTENSION_NAMESPACE),
        (_ext("VERSION"), CURRENT_FORMAT_VERSION), (_ext("APP"), config.APP_NAME),
        (_ext("APP_VERSION"), config.APP_VERSION)], 0))
    out.append(_tag("PROJECT", [
        ("FORMAT", PAP_ELEMENT_FORMAT), ("NAME", meta.name), ("AUTHOR", meta.author),
        ("CREATED", created), ("MODIFIED", modified), (_ext("DESCRIPTION"), meta.description),
        (_ext("CREATED"), meta.created), (_ext("MODIFIED"), meta.modified)], 1))
    out.append(_tag("DIAGRAMS", [], 2))
    out.append(_tag("DIAGRAM", [("FORMAT", PAP_ELEMENT_FORMAT), ("ID", 0), ("NAME", meta.name),
                                ("CREATED", created), ("MODIFIED", modified)], 3))
    out.append(_tag("LAYOUT", [
        ("FORMAT", PAP_ELEMENT_FORMAT),
        ("COLUMNS", max((column for column, _row in cells), default=0) + 1),
        ("ROWS", max((row for _column, row in cells), default=0) + 1),
        (_ext("GRID_SIZE"), int(settings.grid_size)),
        (_ext("GRID_VISIBLE"), _format_flag(settings.grid_visible)),
        (_ext("SNAP_TO_GRID"), _format_flag(settings.snap_to_grid)),
        (_ext("ZOOM"), _format_number(settings.zoom)),
        (_ext("VIEW_X"), _format_number(settings.view_center_x)),
        (_ext("VIEW_Y"), _format_number(settings.view_center_y))], 4))
    out.append(_tag("ENTRIES", [], 5))
    # Der PapDesigner erwartet je Diagramm einen Titel als Ankerzelle. Er ist
    # kein Baustein des Projekts und wird beim Laden übersprungen.
    out.append(_tag("ENTRY", [("COLUMN", 0), ("ROW", 0), ("ANCHOR", "True"), (_ext("GENERATED"), "True")], 6))
    out.append(_tag("FIGURE", [("SUBTYPE", "PapTitle"), ("FORMAT", PAP_ELEMENT_FORMAT), ("ID", 0)], 7))
    out.append(f"{'  ' * 8}<TEXT>{_text_content(meta.name)}</TEXT>")
    out.append(f"{'  ' * 7}</FIGURE>")
    out.append(f"{'  ' * 6}</ENTRY>")
    for number, (element, (column, row)) in enumerate(zip(elements, cells), start=1):
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
    out.append(f"{'  ' * 5}</ENTRIES>")
    out.append(f"{'  ' * 4}</LAYOUT>")
    out.append(_tag("CONNECTIONS", [], 4))
    number = len(elements)
    for connection in connections:
        source, target = numbers.get(connection.source_id), numbers.get(connection.target_id)
        if source is None or target is None:
            continue  # ohne vorhandenen Baustein nicht darstellbar (würde beim Laden entfernt)
        number += 1
        out.append(_tag("CONNECTION", _connection_attributes(connection, number, source, target), 5, empty=True))
    out.append(f"{'  ' * 4}</CONNECTIONS>")
    out.append(f"{'  ' * 3}</DIAGRAM>")
    out.append(f"{'  ' * 2}</DIAGRAMS>")
    out.append("  </PROJECT>")
    out.append("</FRAME>")
    return "\n".join(out) + "\n"


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


def _routing_from(node, native: bool, warnings: list) -> dict:
    axis = node.get(_key("ROUTE_AXIS")) if native else None
    if axis is None:
        return {"mode": "auto"}
    value, ok = _number(node.get(_key("ROUTE_VALUE")), 0.0)
    if axis in ("x", "y") and ok:
        return {"mode": "manual", "axis": axis, "value": value}
    warnings.append(tr("Eine ungültige Linienführung wurde auf „automatisch“ zurückgesetzt."))
    return {"mode": "auto"}


def _path_from(node, native: bool, warnings: list) -> list | None:
    raw = node.get(_key("PATH")) if native else None
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
    column_offset = 0.0
    figure_count = 0
    limit = config.SCENE_HALF_EXTENT - 1000
    for pap_diagram in project.findall("./DIAGRAMS/DIAGRAM"):
        layout = pap_diagram.find("LAYOUT")
        columns = max(1, _attr_int(layout if layout is not None else pap_diagram, "COLUMNS", 1))
        # Nummer des PapDesigners → (Baustein, Rasterzelle)
        figures: dict[str, tuple[ElementData, tuple[int, int]]] = {}
        for entry in pap_diagram.findall("./LAYOUT/ENTRIES/ENTRY"):
            figure = entry.find("FIGURE")
            if figure is None:
                continue
            figure_count += 1
            if native and _flag(entry.get(_key("GENERATED")), False):
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
            columns = max(columns, column + 1)
            x, y, placed = (column + column_offset) * COLUMN_WIDTH, row * ROW_HEIGHT, False
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
            diagram.elements.append(element)

        used_ports: dict[str, set] = {}
        for node in pap_diagram.findall("./CONNECTIONS/CONNECTION"):
            source = figures.get(_reference(node.get("FROM")))
            target = figures.get(_reference(node.get("TO")))
            if source is None or target is None:
                warnings.append(tr("Eine Verbindung zu einem nicht vorhandenen Element wurde entfernt."))
                continue
            (s_elem, s_cell), (t_elem, t_cell) = source, target
            s_port = node.get(_key("SOURCE_PORT")) if native else None
            t_port = node.get(_key("TARGET_PORT")) if native else None
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
            connection_id = node.get(_key("UID")) if native else None
            if not connection_id or not connection_id.strip() or connection_id in seen_connections:
                connection_id = new_id()
            seen_connections.add(connection_id)
            label = node.get("TEXT") or ""
            diagram.connections.append(ConnectionData(
                id=connection_id,
                source_id=s_elem.id,
                target_id=t_elem.id,
                source_port=s_port,
                target_port=t_port,
                label=label if native else label.strip(),
                routing=_routing_from(node, native, warnings),
                path=_path_from(node, native, warnings),
            ))
        column_offset += columns + DIAGRAM_GAP_COLUMNS

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
