"""Orthogonale Linienführung für Verbindungen.

Die Routinglogik arbeitet ohne Qt mit einfachen Tupeln und ist dadurch schnell
und isoliert testbar.

Vorgehen:

1. Von Quell- und Zielanschluss wird ein kurzer Stich in Anschlussrichtung
   gebildet, damit Linien immer senkrecht aus einem Baustein heraus- bzw. in
   ihn hineinlaufen.
2. Zwischen den Stichenden werden rechtwinklige Kandidaten erzeugt
   (gerade, L-Form, Z-Form mit verschiedenen Mittelachsen, U-Form um die
   Bausteine herum und um Hindernisse herum).
3. Jeder Kandidat wird bewertet: Länge + Knicke + (hohe Strafe) für das
   Durchqueren von Bausteinen. Der beste Kandidat gewinnt. Die Reihenfolge
   der Kandidaten ist fest, dadurch ist das Ergebnis deterministisch.

Von Hand verschobene Linien (``manual``) legen fest, wo jedes innere
Linienstück liegt (``{"mode": "manual", "axes": [["y", 120.0], ["x", 340.0], …]}``).
Anfang und Ende hängen weiter an den Anschlüssen; die Linie bleibt dadurch
immer rechtwinklig, auch wenn ein Baustein verschoben wird. Das ändert nur das
Aussehen, nicht den Ablauf. Ältere Dateien kennen nur eine verschobene
Mittelachse (``"axis"`` und ``"value"``).
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]

STUB = 20.0
MARGIN = 40.0
CLEARANCE = 24.0
LINE_CLEARANCE = 14.0
BEND_PENALTY = 24.0
CROSS_PENALTY = 2000.0
ENDPOINT_CROSS_PENALTY = 5000.0
NEAR_PENALTY = 80.0
LINE_OVERLAP_PENALTY = 400.0
LINE_NEAR_PENALTY = 30.0
LINE_CROSS_PENALTY = 60.0
SHORT_STUB_PENALTY = 12.0
MAX_OBSTACLE_AXES = 16
# Beim Verschieben: kürzester Stich am Anschluss, und wie lang ein Stück zum Teilen sein muss
MIN_STUB = 12.0
SPLIT_LENGTH = 2 * MIN_STUB

DIRECTIONS = {
    "top": (0.0, -1.0),
    "bottom": (0.0, 1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
}


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def from_xywh(cls, x: float, y: float, w: float, h: float) -> "Rect":
        return cls(x, y, x + w, y + h)

    def inflated(self, d: float) -> "Rect":
        return Rect(self.left - d, self.top - d, self.right + d, self.bottom + d)

    def united(self, other: "Rect") -> "Rect":
        return Rect(min(self.left, other.left), min(self.top, other.top),
                    max(self.right, other.right), max(self.bottom, other.bottom))

    @property
    def center(self) -> Point:
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2


def segment_crosses_rect(a: Point, b: Point, rect: Rect, eps: float = 0.5) -> bool:
    """True, wenn das achsenparallele Segment a-b das Innere von ``rect`` schneidet."""
    left, top, right, bottom = rect.left + eps, rect.top + eps, rect.right - eps, rect.bottom - eps
    if left >= right or top >= bottom:
        return False
    (x1, y1), (x2, y2) = a, b
    if abs(y1 - y2) < 1e-6:  # horizontal
        if not (top < y1 < bottom):
            return False
        lo, hi = min(x1, x2), max(x1, x2)
        return hi > left and lo < right
    if abs(x1 - x2) < 1e-6:  # vertikal
        if not (left < x1 < right):
            return False
        lo, hi = min(y1, y2), max(y1, y2)
        return hi > top and lo < bottom
    # schräge Segmente kommen nicht vor; konservativ über Bounding-Box prüfen
    return max(x1, x2) > left and min(x1, x2) < right and max(y1, y2) > top and min(y1, y2) < bottom


def simplify(points: list[Point]) -> list[Point]:
    """Entfernt doppelte und kollineare Zwischenpunkte."""
    result: list[Point] = []
    for p in points:
        if result and abs(result[-1][0] - p[0]) < 1e-6 and abs(result[-1][1] - p[1]) < 1e-6:
            continue
        result.append(p)
    changed = True
    while changed and len(result) > 2:
        changed = False
        for i in range(1, len(result) - 1):
            a, b, c = result[i - 1], result[i], result[i + 1]
            same_x = abs(a[0] - b[0]) < 1e-6 and abs(b[0] - c[0]) < 1e-6
            same_y = abs(a[1] - b[1]) < 1e-6 and abs(b[1] - c[1]) < 1e-6
            if same_x or same_y:
                del result[i]
                changed = True
                break
    return result


def path_length(points: list[Point]) -> float:
    return sum(abs(points[i + 1][0] - points[i][0]) + abs(points[i + 1][1] - points[i][1])
               for i in range(len(points) - 1))


def _direction(a: Point, b: Point) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return (0.0 if abs(dx) < 1e-6 else (1.0 if dx > 0 else -1.0),
            0.0 if abs(dy) < 1e-6 else (1.0 if dy > 0 else -1.0))


def base_cost(points: list[Point]) -> float:
    """Grundkosten eines Linienzugs: Länge + Knicke (Untergrenze der Bewertung)."""
    return path_length(points) + BEND_PENALTY * max(0, len(points) - 2)


def line_penalty(a: Point, b: Point, lines: list) -> float:
    """Strafe dafür, dass das Stück a-b auf, neben oder quer über anderen Linien läuft."""
    penalty = 0.0
    vertical = abs(a[0] - b[0]) < 1e-6
    lo, hi = (min(a[1], b[1]), max(a[1], b[1])) if vertical else (min(a[0], b[0]), max(a[0], b[0]))
    position = a[0] if vertical else a[1]
    for c, d in lines:
        other_vertical = abs(c[0] - d[0]) < 1e-6
        other_lo, other_hi = (min(c[1], d[1]), max(c[1], d[1])) if other_vertical else (min(c[0], d[0]), max(c[0], d[0]))
        other_position = c[0] if other_vertical else c[1]
        if vertical == other_vertical:
            distance = abs(position - other_position)
            shared = min(hi, other_hi) - max(lo, other_lo)
            if distance < LINE_CLEARANCE and shared > 1.0:
                penalty += (LINE_OVERLAP_PENALTY if distance < 1.0 else LINE_NEAR_PENALTY) * min(1.0, shared / 60.0)
        elif lo + 1 < other_position < hi - 1 and other_lo + 1 < position < other_hi - 1:
            penalty += LINE_CROSS_PENALTY
    return penalty


def score_path(points: list[Point], source_rect: Rect | None, target_rect: Rect | None,
               obstacles: list[Rect], start_dir: str | None = None, end_dir: str | None = None,
               near_obstacles: list[Rect] | None = None, lines: list | None = None) -> float:
    """Bewertet einen Linienzug (kleiner = besser)."""
    score = base_cost(points)
    segments = list(zip(points[:-1], points[1:]))
    if lines:
        score += sum(line_penalty(a, b, lines) for a, b in segments)
    last = len(segments) - 1
    if near_obstacles is None:
        near_obstacles = [r.inflated(CLEARANCE) for r in obstacles]
    near_source = source_rect.inflated(CLEARANCE) if source_rect is not None else None
    near_target = target_rect.inflated(CLEARANCE) if target_rect is not None else None
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    relevant = [(rect, near) for rect, near in zip(obstacles, near_obstacles)
                if near.right > min_x and near.left < max_x and near.bottom > min_y and near.top < max_y]
    for index, (a, b) in enumerate(segments):
        for rect, near in relevant:
            if segment_crosses_rect(a, b, rect):
                score += CROSS_PENALTY
            elif segment_crosses_rect(a, b, near):
                score += NEAR_PENALTY
        if source_rect is not None:
            if segment_crosses_rect(a, b, source_rect):
                score += ENDPOINT_CROSS_PENALTY
            elif index != 0 and segment_crosses_rect(a, b, near_source):
                score += NEAR_PENALTY
        if target_rect is not None:
            if segment_crosses_rect(a, b, target_rect):
                score += ENDPOINT_CROSS_PENALTY
            elif index != last and segment_crosses_rect(a, b, near_target):
                score += NEAR_PENALTY

    # Linien sollen senkrecht und mit ausreichendem Stich aus dem Baustein
    # heraus- bzw. in ihn hineinlaufen (gerade Direktverbindung ausgenommen).
    if len(points) > 2:
        if start_dir is not None:
            (a, b) = segments[0]
            if _direction(a, b) != DIRECTIONS[start_dir]:
                score += ENDPOINT_CROSS_PENALTY
            else:
                length = abs(b[0] - a[0]) + abs(b[1] - a[1])
                score += max(0.0, STUB - length) * SHORT_STUB_PENALTY
        if end_dir is not None:
            (a, b) = segments[-1]
            ex, ey = DIRECTIONS[end_dir]
            if _direction(a, b) != (-ex, -ey):
                score += ENDPOINT_CROSS_PENALTY
            else:
                length = abs(b[0] - a[0]) + abs(b[1] - a[1])
                score += max(0.0, STUB - length) * SHORT_STUB_PENALTY
    elif start_dir is not None and end_dir is not None and len(points) == 2:
        a, b = points
        sx, sy = DIRECTIONS[start_dir]
        ex, ey = DIRECTIONS[end_dir]
        if _direction(a, b) != (sx, sy) or _direction(a, b) != (-ex, -ey):
            score += ENDPOINT_CROSS_PENALTY
    return score


def _unique(values: list[float]) -> list[float]:
    seen: list[float] = []
    for v in values:
        if all(abs(v - s) > 0.5 for s in seen):
            seen.append(v)
    return seen


def is_vertical_port(port: str) -> bool:
    return port in ("top", "bottom")


def points_from_axes(start: Point, start_dir: str, end: Point, end_dir: str, axes: list) -> list[Point] | None:
    """Linienzug aus den Lagen der inneren Stücke; ``None``, wenn sie nicht zu den Anschlüssen passen.

    ``axes`` beschreibt jedes Stück außer dem ersten und letzten: ``["x", wert]`` ist ein senkrechtes Stück bei
    ``x = wert``, ``["y", wert]`` ein waagerechtes. Die Stücke wechseln sich ab.
    """
    vertical = is_vertical_port(start_dir)
    points = [start]
    x, y = start
    for axis, value in axes:
        if axis != ("y" if vertical else "x"):
            return None
        if vertical:
            y = value
        else:
            x = value
        points.append((x, y))
        vertical = not vertical
    last_vertical = not vertical
    if last_vertical != is_vertical_port(end_dir):
        return None
    points.append((end[0], y) if last_vertical else (x, end[1]))
    points.append(end)
    return simplify(points)


def axes_from_points(points: list[Point]) -> list:
    """Lagen der inneren Stücke eines rechtwinkligen Linienzugs (Gegenstück zu ``points_from_axes``)."""
    return [["x", float(a[0])] if abs(a[0] - b[0]) < 1e-6 else ["y", float(a[1])]
            for a, b in zip(points[1:-2], points[2:-1])]


def _leaves_blocks_cleanly(points: list[Point], source_rect: Rect | None, target_rect: Rect | None,
                           start_dir: str, end_dir: str | None) -> bool:
    """Läuft der Linienzug in Richtung der Anschlüsse und nicht durch die eigenen Bausteine?"""
    if _direction(points[0], points[1]) != DIRECTIONS[start_dir]:
        return False
    if end_dir is not None:
        ex, ey = DIRECTIONS[end_dir]
        if _direction(points[-2], points[-1]) != (-ex, -ey):
            return False
    return not any(rect is not None and segment_crosses_rect(a, b, rect)
                   for a, b in zip(points[:-1], points[1:]) for rect in (source_rect, target_rect))


def manual_points(start: Point, start_dir: str, end: Point, end_dir: str | None, manual: dict | None) -> list | None:
    """Der von Hand festgelegte Linienzug; ``None``, wenn es keinen gibt oder er nicht zu den Anschlüssen passt."""
    if not manual or manual.get("mode") != "manual" or end_dir is None or "axes" not in manual:
        return None
    try:
        axes = [(str(axis), float(value)) for axis, value in manual["axes"]]
    except (TypeError, ValueError):
        return None
    points = points_from_axes(start, start_dir, end, end_dir, axes)
    return points if points is not None and len(points) >= 2 and _is_orthogonal(points) else None


def _segment_length(points: list[Point], index: int) -> float:
    a, b = points[index], points[index + 1]
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


def can_move_segment(points: list[Point], index: int) -> bool:
    """Lässt sich das Stück verschieben? Das erste und letzte muss dafür lang genug zum Teilen sein."""
    last = len(points) - 2
    if len(points) < 2 or not 0 <= index <= last:
        return False
    return 0 < index < last or _segment_length(points, index) >= SPLIT_LENGTH


def _is_vertical(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) < 1e-6


def _clamped(anchor: float, current: float, value: float) -> float:
    """Hält ``value`` auf der Seite des Anschlusses ``anchor``, auf der ``current`` liegt."""
    if current > anchor + 1e-6:
        return max(value, anchor + MIN_STUB)
    if current < anchor - 1e-6:
        return min(value, anchor - MIN_STUB)
    return value


def _placed(points: list[Point], index: int, vertical: bool, value: float) -> list[Point]:
    """Setzt das innere Stück ``index`` auf ``value``; neben einem Anschluss bleibt ein Stich von ``MIN_STUB``."""
    result = list(points)
    axis = 0 if vertical else 1
    if index == 1:
        value = _clamped(result[0][axis], result[1][axis], value)
    if index + 2 == len(result) - 1:
        value = _clamped(result[-1][axis], result[-2][axis], value)
    for position in (index, index + 1):
        x, y = result[position]
        result[position] = (value, y) if vertical else (x, value)
    return result


def move_segment(points: list[Point], index: int, value: float) -> list[Point]:
    """Linienzug, in dem das Stück ``index`` auf ``value`` liegt (``x`` eines senkrechten, ``y`` eines waagerechten).

    Das erste und letzte Stück hängen am Anschluss: Sie bleiben dort mit einem kurzen Stich, dahinter entsteht eine
    Stufe. Das Ergebnis kann doppelte Punkte enthalten (``simplify`` räumt sie weg).
    """
    last = len(points) - 2
    a, b = points[index], points[index + 1]
    vertical = _is_vertical(a, b)
    if 0 < index < last:
        return _placed(points, index, vertical, value)
    dx, dy = _direction(a, b)
    near_a = (a[0] + dx * MIN_STUB, a[1] + dy * MIN_STUB)
    near_b = (b[0] - dx * MIN_STUB, b[1] - dy * MIN_STUB)

    def moved(p: Point) -> Point:
        return (value, p[1]) if vertical else (p[0], value)

    if last == 0:
        return [a, near_a, moved(near_a), moved(near_b), near_b, b]
    if index == 0:
        return [a, near_a, moved(near_a), moved(b), *points[2:]]
    return [*points[:index], moved(a), moved(near_b), near_b, b]


def move_corner(points: list[Point], corner: int, x: float, y: float) -> list[Point]:
    """Linienzug mit der Ecke ``corner`` bei (x, y); Stücke an den Anschlüssen bleiben, wo sie sind."""
    result = list(points)
    last = len(points) - 2
    for index in (corner - 1, corner):
        if 0 < index < last:
            vertical = _is_vertical(points[index], points[index + 1])
            result = _placed(result, index, vertical, x if vertical else y)
    return result


def insert_bend(points: list[Point], index: int, at: Point, step: float) -> list[Point]:
    """Fügt in das Stück ``index`` bei ``at`` eine Stufe der Höhe ``step`` ein (nur das Aussehen ändert sich)."""
    a, b = points[index], points[index + 1]
    vertical = _is_vertical(a, b)
    axis = 1 if vertical else 0
    low, high = min(a[axis], b[axis]) + MIN_STUB, max(a[axis], b[axis]) - MIN_STUB
    place = (low + high) / 2 if low > high else max(low, min(high, at[axis]))

    def on_line(value: float) -> Point:
        return (a[0], value) if vertical else (value, a[1])

    def shifted(p: Point) -> Point:
        return (p[0] + step, p[1]) if vertical else (p[0], p[1] + step)

    middle = on_line(place)
    last = len(points) - 2
    if index == last == 0:  # einziges Stück: Ausbuchtung um die Stelle herum
        half = max(1.0, min(abs(step), (high - low) / 2 if high > low else 1.0))
        place = max(low + half, min(high - half, place)) if high - low > 2 * half else (low + high) / 2
        first, second = sorted((place - half, place + half), reverse=b[axis] < a[axis])
        return [a, on_line(first), shifted(on_line(first)), shifted(on_line(second)), on_line(second), b]
    if index == last:  # am Ziel: der vordere Teil weicht aus
        return [*points[:index], shifted(a), shifted(middle), middle, b]
    return [*points[:index + 1], middle, shifted(middle), shifted(b), *points[index + 2:]]


def route(start: Point, start_dir: str, end: Point, end_dir: str | None,
          source_rect: Rect | None = None, target_rect: Rect | None = None,
          obstacles: list[Rect] | None = None, manual: dict | None = None,
          lines: list | None = None) -> list[Point]:
    """Berechnet einen rechtwinkligen Linienzug von ``start`` nach ``end``.

    ``start_dir``/``end_dir`` sind Anschlussnamen (top/bottom/left/right) und
    geben an, in welche Richtung die Linie den jeweiligen Baustein verlässt.
    ``end_dir`` darf ``None`` sein (freies Ende, z. B. während des Ziehens).
    ``lines``: Stücke anderer Verbindungen, zu denen die Linie Abstand halten soll.
    """
    obstacles = obstacles or []
    sdx, sdy = DIRECTIONS[start_dir]
    s1 = (start[0] + sdx * STUB, start[1] + sdy * STUB)
    if end_dir is not None:
        edx, edy = DIRECTIONS[end_dir]
        t1 = (end[0] + edx * STUB, end[1] + edy * STUB)
    else:
        t1 = end

    # Von Hand verschobene Linien gelten, solange sie nicht durch ihre eigenen Bausteine führen; sonst wird
    # automatisch geführt (und die Handarbeit gilt wieder, sobald sie wieder passt).
    drawn = manual_points(start, start_dir, end, end_dir, manual)
    if drawn is not None and _leaves_blocks_cleanly(drawn, source_rect, target_rect, start_dir, end_dir):
        return drawn

    manual_axis = manual.get("axis") if manual and manual.get("mode") == "manual" else None
    if manual_axis in ("x", "y"):
        try:
            value = float(manual.get("value"))
        except (TypeError, ValueError):
            value = None
        if value is not None:
            middle = [(value, s1[1]), (value, t1[1])] if manual_axis == "x" else [(s1[0], value), (t1[0], value)]
            points = simplify([start, s1, *middle, t1] + ([end] if end_dir is not None else []))
            if len(points) >= 2 and _is_orthogonal(points):
                # Die manuelle Achse gilt, solange sie die eigenen Endbausteine
                # nicht durchschneidet; sonst wird automatisch geführt.
                if _leaves_blocks_cleanly(points, source_rect, target_rect, start_dir, end_dir):
                    return points

    candidates: list[list[Point]] = []
    candidates.append([])  # gerade (falls ausgerichtet)
    candidates.append([(t1[0], s1[1])])  # erst horizontal, dann vertikal
    candidates.append([(s1[0], t1[1])])  # erst vertikal, dann horizontal

    bounds = [r for r in (source_rect, target_rect) if r is not None]
    union = None
    for r in bounds:
        union = r if union is None else union.united(r)

    xs = [(s1[0] + t1[0]) / 2]
    ys = [(s1[1] + t1[1]) / 2]
    if union is not None:
        xs += [union.left - MARGIN, union.right + MARGIN]
        ys += [union.top - MARGIN, union.bottom + MARGIN]

    # Achsen entlang naher Hindernisse
    lo_x, hi_x = min(s1[0], t1[0]), max(s1[0], t1[0])
    lo_y, hi_y = min(s1[1], t1[1]), max(s1[1], t1[1])
    near = [r for r in obstacles
            if r.right > lo_x - 200 and r.left < hi_x + 200
            and r.bottom > lo_y - 200 and r.top < hi_y + 200]
    near.sort(key=lambda r: abs(r.center[0] - (lo_x + hi_x) / 2) + abs(r.center[1] - (lo_y + hi_y) / 2))
    for r in near[:MAX_OBSTACLE_AXES]:
        xs += [r.left - MARGIN, r.right + MARGIN]
        ys += [r.top - MARGIN, r.bottom + MARGIN]

    for x in _unique(xs):
        candidates.append([(x, s1[1]), (x, t1[1])])
    for y in _unique(ys):
        candidates.append([(s1[0], y), (t1[0], y)])

    prepared = []
    for index, middle in enumerate(candidates):
        points = [start, s1, *middle, t1]
        if end_dir is not None:
            points.append(end)
        points = simplify(points)
        if len(points) < 2:
            points = [start, end]
        if _is_orthogonal(points):
            prepared.append((base_cost(points), index, points))
    # Kandidaten nach Grundkosten prüfen; da Strafen nie negativ sind, kann
    # abgebrochen werden, sobald die Grundkosten den besten Wert erreichen.
    prepared.sort(key=lambda entry: (entry[0], entry[1]))
    near_obstacles = [r.inflated(CLEARANCE) for r in obstacles]
    best: list[Point] | None = None
    best_score = float("inf")
    for cost, _index, points in prepared:
        if cost >= best_score - 1e-6:
            break
        score = score_path(points, source_rect, target_rect, obstacles, start_dir, end_dir, near_obstacles, lines)
        if score < best_score - 1e-6:
            best, best_score = points, score
    if best is None:
        best = simplify([start, s1, (s1[0], t1[1]), t1, end])
    return best


def _is_orthogonal(points: list[Point]) -> bool:
    for a, b in zip(points[:-1], points[1:]):
        if abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6:
            return False
    return True


def interior_segments(points: list[Point]) -> list[int]:
    """Indizes der Segmente, die nicht am Anschluss hängen (weder erstes noch letztes)."""
    count = len(points) - 1
    return list(range(1, count - 1)) if count >= 3 else []


def movable_segments(points: list[Point]) -> list[int]:
    """Indizes aller Segmente, die der Benutzer verschieben darf."""
    return [index for index in range(len(points) - 1) if can_move_segment(points, index)]


def translated(manual: dict, dx: float, dy: float) -> dict:
    """Von Hand festgelegte Linienführung, um (dx, dy) verschoben."""
    shifted = dict(manual)
    if "axes" in shifted:
        shifted["axes"] = [[axis, float(value) + (dx if axis == "x" else dy)] for axis, value in shifted["axes"]]
    elif shifted.get("axis") in ("x", "y"):
        try:
            value = float(shifted.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        shifted["value"] = value + (dx if shifted["axis"] == "x" else dy)
    return shifted


def segment_axis(points: list[Point], index: int) -> str | None:
    a, b = points[index], points[index + 1]
    if abs(a[0] - b[0]) < 1e-6:
        return "x"
    if abs(a[1] - b[1]) < 1e-6:
        return "y"
    return None
