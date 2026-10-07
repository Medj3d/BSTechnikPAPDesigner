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

Eine manuell verschobene Mittelachse (``manual``) schränkt die Kandidaten auf
genau diese Achse ein.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]

STUB = 20.0
MARGIN = 20.0
CLEARANCE = 12.0
BEND_PENALTY = 24.0
CROSS_PENALTY = 2000.0
ENDPOINT_CROSS_PENALTY = 5000.0
NEAR_PENALTY = 80.0
SHORT_STUB_PENALTY = 12.0
MAX_OBSTACLE_AXES = 16

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


def score_path(points: list[Point], source_rect: Rect | None, target_rect: Rect | None,
               obstacles: list[Rect], start_dir: str | None = None, end_dir: str | None = None,
               near_obstacles: list[Rect] | None = None) -> float:
    """Bewertet einen Linienzug (kleiner = besser)."""
    score = base_cost(points)
    segments = list(zip(points[:-1], points[1:]))
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


def route(start: Point, start_dir: str, end: Point, end_dir: str | None,
          source_rect: Rect | None = None, target_rect: Rect | None = None,
          obstacles: list[Rect] | None = None, manual: dict | None = None) -> list[Point]:
    """Berechnet einen rechtwinkligen Linienzug von ``start`` nach ``end``.

    ``start_dir``/``end_dir`` sind Anschlussnamen (top/bottom/left/right) und
    geben an, in welche Richtung die Linie den jeweiligen Baustein verlässt.
    ``end_dir`` darf ``None`` sein (freies Ende, z. B. während des Ziehens).
    """
    obstacles = obstacles or []
    sdx, sdy = DIRECTIONS[start_dir]
    s1 = (start[0] + sdx * STUB, start[1] + sdy * STUB)
    if end_dir is not None:
        edx, edy = DIRECTIONS[end_dir]
        t1 = (end[0] + edx * STUB, end[1] + edy * STUB)
    else:
        t1 = end

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
                score = score_path(points, source_rect, target_rect, obstacles, start_dir, end_dir)
                # Die manuelle Achse gilt, solange sie die eigenen Endbausteine
                # nicht durchschneidet; sonst wird automatisch geführt.
                if score < ENDPOINT_CROSS_PENALTY:
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
        score = score_path(points, source_rect, target_rect, obstacles, start_dir, end_dir, near_obstacles)
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
    """Indizes der Segmente, die der Benutzer verschieben darf (nicht erstes/letztes)."""
    count = len(points) - 1
    return list(range(1, count - 1)) if count >= 3 else []


def segment_axis(points: list[Point], index: int) -> str | None:
    a, b = points[index], points[index + 1]
    if abs(a[0] - b[0]) < 1e-6:
        return "x"
    if abs(a[1] - b[1]) < 1e-6:
        return "y"
    return None
