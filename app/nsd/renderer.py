"""Struktogramm (Nassi-Shneiderman-Diagramm) aus dem Strukturbaum.

Darstellung nach DIN 66261:

* Anweisung      – Rechteck mit Text
* Verzweigung    – Kopf mit Bedingung und Dreieck (ja links, nein rechts),
                   darunter zwei Spalten
* kopfgesteuert  – Kopfzeile mit Bedingung, Rumpf eingerückt (linker Balken)
* fußgesteuert   – Rumpf eingerückt, Fußzeile mit Bedingung
* Zählschleife   – wie kopfgesteuert (Schleifenkopf als Text)

Die Maße werden zweistufig bestimmt: bevorzugte Breite von unten nach oben,
dann tatsächliche Breiten/Höhen von oben nach unten.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize, QPainter,
                           QPdfWriter, QPen, QPolygonF)

from app import config, styles
from app.analysis.ast import (Action, Block, Break, Continue, DoWhileLoop, EndStmt, If, LimitLoop, Loop,
                              Program,
                              Unstructured, WhileLoop)
from app.export import ExportError
from app.i18n import N_, tr
from app.labels import no_label as default_no_label, yes_label as default_yes_label

PAD_X = 8.0
PAD_Y = 6.0
BAR = 26.0             # Breite des Schleifenbalkens
MIN_WIDTH = 120.0
MAX_TEXT_WIDTH = 260.0
LABEL_ROW = 16.0       # Platz für „ja“/„nein“ im Verzweigungskopf
TITLE_HEIGHT = 30.0
PROGRAM_GAP = 36.0


def _font(pixel: int = 13, bold: bool = False) -> QFont:
    font = styles.item_font(pixel)
    font.setBold(bold)
    # ohne ClearType-Subpixel (wirkt nicht überall, siehe render_image)
    font.setStyleStrategy(QFont.StyleStrategy(QFont.StyleStrategy.PreferAntialias.value
                                              | QFont.StyleStrategy.NoSubpixelAntialias.value))
    return font


class _Node:
    def pref_width(self, fm: QFontMetricsF) -> float:
        raise NotImplementedError

    def min_width(self, fm: QFontMetricsF) -> float:
        """Schmaler geht es nicht, ohne dass Text abgeschnitten wird."""
        raise NotImplementedError

    def height(self, width: float, fm: QFontMetricsF) -> float:
        raise NotImplementedError

    def paint(self, p: QPainter, rect: QRectF, fm: QFontMetricsF, colors) -> None:
        raise NotImplementedError


def _text_size(fm: QFontMetricsF, text: str, width: float) -> QSizeF:
    flags = int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
    rect = fm.boundingRect(QRectF(0, 0, max(10.0, width), 100000.0), flags, text or " ")
    return rect.size()


def _word_width(fm: QFontMetricsF, text: str) -> float:
    """Breite des längsten Wortes – Zeilenumbruch kann Wörter nicht trennen."""
    return max((fm.horizontalAdvance(word) for word in (text or "").split()), default=0.0)


def _natural_width(fm: QFontMetricsF, text: str) -> float:
    lines = (text or " ").splitlines() or [" "]
    return min(MAX_TEXT_WIDTH, max(fm.horizontalAdvance(line) for line in lines))


def _draw_text(p: QPainter, rect: QRectF, text: str, colors, align=Qt.AlignmentFlag.AlignLeft) -> None:
    p.setPen(QColor(colors["text"]))
    flags = int(align | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
    p.drawText(rect.adjusted(PAD_X, PAD_Y, -PAD_X, -PAD_Y), flags, text)


def _frame(p: QPainter, rect: QRectF, colors, fill=None) -> None:
    p.setPen(QPen(QColor(colors["line"]), 1.2))
    p.setBrush(QColor(fill or colors["fill"]))
    p.drawRect(rect)


class _Text(_Node):
    def __init__(self, text: str, fill_key: str = "fill", dashed: bool = False, center: bool = False):
        self.text = " ".join((text or "").split()) if "\n" not in (text or "") else text.strip()
        self.fill_key = fill_key
        self.dashed = dashed
        self.center = center

    def pref_width(self, fm):
        return max(MIN_WIDTH, _natural_width(fm, self.text) + 2 * PAD_X)

    def min_width(self, fm):
        return _word_width(fm, self.text) + 2 * PAD_X + 2

    def height(self, width, fm):
        return _text_size(fm, self.text, width - 2 * PAD_X).height() + 2 * PAD_Y

    def paint(self, p, rect, fm, colors):
        _frame(p, rect, colors, colors[self.fill_key])
        if self.dashed:
            pen = QPen(QColor(colors["muted"]), 1.0, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect.adjusted(3, 3, -3, -3))
        _draw_text(p, rect, self.text, colors,
                   Qt.AlignmentFlag.AlignHCenter if self.center else Qt.AlignmentFlag.AlignLeft)


class _Sequence(_Node):
    def __init__(self, children: list[_Node]):
        self.children = children or [_Text("∅", center=True)]

    def pref_width(self, fm):
        return max(child.pref_width(fm) for child in self.children)

    def min_width(self, fm):
        return max(child.min_width(fm) for child in self.children)

    def height(self, width, fm):
        return sum(child.height(width, fm) for child in self.children)

    def paint(self, p, rect, fm, colors):
        y = rect.top()
        for child in self.children:
            h = child.height(rect.width(), fm)
            child.paint(p, QRectF(rect.left(), y, rect.width(), h), fm, colors)
            y += h


class _If(_Node):
    def __init__(self, condition: str, yes: _Node, no: _Node, yes_label: str, no_label: str):
        self.condition = " ".join(condition.split())
        self.yes, self.no = yes, no
        self.yes_label, self.no_label = yes_label or default_yes_label(), no_label or default_no_label()

    def split(self, width, fm) -> float:
        a, b = self.yes.pref_width(fm), self.no.pref_width(fm)
        left = width * a / (a + b)
        # keine Spalte schmaler als ihr längstes Wort
        low, high = self.yes.min_width(fm), width - self.no.min_width(fm)
        return min(max(left, low), high) if low <= high else left

    def pref_width(self, fm):
        return max(self.yes.pref_width(fm) + self.no.pref_width(fm), _natural_width(fm, self.condition) * 1.6 + 40)

    def min_width(self, fm):
        return max(self.yes.min_width(fm) + self.no.min_width(fm), _word_width(fm, self.condition) * 2 + 24)

    def _condition_size(self, width, fm) -> QSizeF:
        """Größe des umbrochenen Bedingungstextes (höchstens die halbe Kopfbreite)."""
        limit = max(width * 0.5, _word_width(fm, self.condition) + 2)
        size = _text_size(fm, self.condition, limit)
        return QSizeF(min(size.width(), limit), size.height())

    def header_height(self, width, fm):
        # Der Text steht oben im Dreieck; der Kopf ist so hoch, dass die beiden
        # Schrägen an der Unterkante des Textes noch genug Platz lassen.
        size = self._condition_size(width, fm)
        share = min(0.8, size.width() / width)
        return max(size.height() + 2 * PAD_Y + LABEL_ROW, (PAD_Y + size.height()) / (1 - share) + 4)

    def height(self, width, fm):
        left = self.split(width, fm)
        return self.header_height(width, fm) + max(self.yes.height(left, fm), self.no.height(width - left, fm))

    def paint(self, p, rect, fm, colors):
        width = rect.width()
        left = self.split(width, fm)
        head_h = self.header_height(width, fm)
        head = QRectF(rect.left(), rect.top(), width, head_h)
        _frame(p, head, colors, colors["head"])
        tip = QPointF(rect.left() + left, head.bottom())
        p.setPen(QPen(QColor(colors["line"]), 1.2))
        p.drawLine(head.topLeft(), tip)
        p.drawLine(head.topRight(), tip)
        # Text mittig zwischen den Schrägen (auf Höhe seiner Unterkante gemessen)
        size = self._condition_size(width, fm)
        level = (PAD_Y + size.height()) / head_h
        free_left = left * level
        free_right = width - (width - left) * level
        center = rect.left() + (free_left + free_right) / 2
        text_rect = QRectF(center - size.width() / 2 - 1, head.top() + PAD_Y, size.width() + 2, size.height())
        p.setPen(QColor(colors["text"]))
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), self.condition)
        small = QFont(p.font())
        small.setPixelSize(11)
        p.save()
        p.setFont(small)
        p.setPen(QColor(colors["muted"]))
        p.drawText(QRectF(head.left() + 6, head.bottom() - LABEL_ROW, left, LABEL_ROW - 2),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom), self.yes_label)
        p.drawText(QRectF(tip.x(), head.bottom() - LABEL_ROW, width - left - 6, LABEL_ROW - 2),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom), self.no_label)
        p.restore()
        body_top = head.bottom()
        body_h = rect.bottom() - body_top
        yes_rect = QRectF(rect.left(), body_top, left, body_h)
        no_rect = QRectF(rect.left() + left, body_top, width - left, body_h)
        self._paint_column(p, self.yes, yes_rect, fm, colors)
        self._paint_column(p, self.no, no_rect, fm, colors)

    @staticmethod
    def _paint_column(p, node, rect, fm, colors):
        h = node.height(rect.width(), fm)
        node.paint(p, QRectF(rect.left(), rect.top(), rect.width(), h), fm, colors)
        if h < rect.height():  # Rest der Spalte leer auffüllen
            _frame(p, QRectF(rect.left(), rect.top() + h, rect.width(), rect.height() - h), colors)


class _Loop(_Node):
    """Schleife: Kopf- und/oder Fußzeile, Rumpf rechts neben dem Balken."""

    def __init__(self, header: str | None, body: _Node, footer: str | None):
        self.header = " ".join(header.split()) if header else None
        self.footer = " ".join(footer.split()) if footer else None
        self.body = body

    def pref_width(self, fm):
        widths = [self.body.pref_width(fm) + BAR]
        for text in (self.header, self.footer):
            if text:
                widths.append(_natural_width(fm, text) + 2 * PAD_X)
        return max(widths)

    def min_width(self, fm):
        words = [_word_width(fm, text) + 2 * PAD_X + 2 for text in (self.header, self.footer) if text]
        return max([self.body.min_width(fm) + BAR] + words)

    def _row(self, text, width, fm):
        return _text_size(fm, text, width - 2 * PAD_X).height() + 2 * PAD_Y if text else 0.0

    def height(self, width, fm):
        return (self._row(self.header, width, fm) + self.body.height(width - BAR, fm)
                + self._row(self.footer, width, fm))

    def paint(self, p, rect, fm, colors):
        width = rect.width()
        head_h = self._row(self.header, width, fm)
        foot_h = self._row(self.footer, width, fm)
        _frame(p, rect, colors, colors["head"])
        if self.header:
            _draw_text(p, QRectF(rect.left(), rect.top(), width, head_h), self.header, colors)
        if self.footer:
            _draw_text(p, QRectF(rect.left(), rect.bottom() - foot_h, width, foot_h), self.footer, colors)
        body_rect = QRectF(rect.left() + BAR, rect.top() + head_h, width - BAR, rect.height() - head_h - foot_h)
        self.body.paint(p, body_rect, fm, colors)


def _build(block: Block, top_level: bool = False) -> _Node:
    statements = list(block)
    if top_level and statements and isinstance(statements[-1], EndStmt):
        statements = statements[:-1]
    return _Sequence([node for node in (_stmt(s) for s in statements) if node is not None])


# Vorsatz einer Ein-/Ausgabe oder eines Aufrufs im Struktogramm (deutscher Quelltext, angezeigt mit ``tr``)
_PREFIXES = {"input": N_("Eingabe: "), "output": N_("Ausgabe: "), "subprogram": N_("Aufruf: ")}


def _action_text(kind: str, text: str) -> str:
    """Text einer Anweisung, bei Ein-/Ausgabe und Aufruf mit Vorsatz („Eingabe: x“).

    Beginnt der Text des Bausteins schon mit dem Wort (auf Deutsch – der Sprache der Plantexte – oder in der
    Sprache der Oberfläche), bleibt der Vorsatz weg.
    """
    source = _PREFIXES.get(kind)
    if not source:
        return text
    prefix = tr(source)
    lowered = text.lower()
    if any(word and lowered.startswith(word) for word in (source.lower().rstrip(": "), prefix.lower().rstrip(": "))):
        return text
    return prefix + text


def _stmt(stmt) -> _Node | None:
    if isinstance(stmt, Action):
        if stmt.kind == "junction":
            return None
        return _Text(_action_text(stmt.kind, stmt.text.strip()), "sub" if stmt.kind == "subprogram" else "fill")
    if isinstance(stmt, If):
        return _If(stmt.condition, _build(stmt.then_block), _build(stmt.else_block), stmt.then_label,
                   stmt.else_label)
    if isinstance(stmt, WhileLoop):
        text = stmt.condition.strip()
        condition = tr("solange nicht ({condition})", condition=text) if stmt.negate \
            else tr("solange {condition}", condition=text)
        return _Loop(condition, _build(stmt.body), None)
    if isinstance(stmt, DoWhileLoop):
        text = stmt.condition.strip()
        condition = tr("bis {condition}", condition=text) if stmt.negate else tr("solange {condition}", condition=text)
        return _Loop(None, _build(stmt.body), condition)
    if isinstance(stmt, LimitLoop):
        return _Loop(stmt.header, _build(stmt.body), stmt.footer or None)
    if isinstance(stmt, Loop):
        return _Loop(tr("wiederhole"), _build(stmt.body), None)
    if isinstance(stmt, Continue):
        return _Text(tr("nächster Durchlauf"), "head", center=True)
    if isinstance(stmt, Break):
        return _Text(tr("Schleife verlassen"), "head", center=True)
    if isinstance(stmt, EndStmt):
        return _Text(tr("Ende", ctx="Struktogramm"), "head", center=True)
    if isinstance(stmt, Unstructured):
        return _Text(tr("Nicht strukturierbar: {note}", note=stmt.note), "fill", dashed=True)
    return None


def _colors(theme) -> dict:
    return {
        "line": theme.text_muted if theme.name == "dark" else theme.connection,
        "text": theme.element_text,
        "muted": theme.text_muted,
        "fill": theme.panel_raised if theme.name == "dark" else "#FFFFFF",
        "head": theme.panel_bg if theme.name == "dark" else "#F1F3F6",
        "sub": theme.panel_bg if theme.name == "dark" else "#F7F8FA",
        "background": theme.canvas_bg,
    }


class NsdRenderer:
    """Struktogramm eines Ablaufs."""

    def __init__(self, program: Program, theme=None, font: QFont | None = None):
        self.program = program
        self.theme = theme or styles.current_theme()
        self.font = font or _font()
        self.fm = QFontMetricsF(self.font)
        self.root = _build(program.body, top_level=True)
        # höchstens 900 px breit – außer der Inhalt braucht mehr, damit kein Wort abgeschnitten wird
        self.width = max(360.0, min(900.0, self.root.pref_width(self.fm)), self.root.min_width(self.fm))

    def size(self) -> QSizeF:
        return QSizeF(self.width, TITLE_HEIGHT + self.root.height(self.width, self.fm))

    def paint(self, painter: QPainter, origin: QPointF = QPointF(0, 0)) -> None:
        colors = _colors(self.theme)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self.font)
        painter.translate(origin)
        title = QRectF(0, 0, self.width, TITLE_HEIGHT)
        bold = _font(14, True)
        painter.setFont(bold)
        painter.setPen(QColor(colors["text"]))
        painter.drawText(title.adjusted(2, 0, 0, -6), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
                         self.program.name)
        painter.setFont(self.font)
        height = self.root.height(self.width, self.fm)
        self.root.paint(painter, QRectF(0, TITLE_HEIGHT, self.width, height), self.fm, colors)
        painter.setPen(QPen(QColor(colors["line"]), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0, TITLE_HEIGHT, self.width, height))
        painter.restore()


def _layout(programs: list[Program], theme) -> tuple[list[tuple[NsdRenderer, float]], QSizeF]:
    renderers = [NsdRenderer(program, theme) for program in programs]
    y = 0.0
    placed = []
    width = 0.0
    for renderer in renderers:
        placed.append((renderer, y))
        size = renderer.size()
        y += size.height() + PROGRAM_GAP
        width = max(width, size.width())
    return placed, QSizeF(width, max(0.0, y - PROGRAM_GAP))


def paint_programs(painter: QPainter, programs: list[Program], theme, margin: float = 20.0) -> QSizeF:
    placed, size = _layout(programs, theme)
    for renderer, y in placed:
        renderer.paint(painter, QPointF(margin, margin + y))
    return QSizeF(size.width() + 2 * margin, size.height() + 2 * margin)


def total_size(programs: list[Program], theme, margin: float = 20.0) -> QSizeF:
    _, size = _layout(programs, theme)
    return QSizeF(size.width() + 2 * margin, size.height() + 2 * margin)


def render_image(programs: list[Program], theme=None, scale: float = 2.0, transparent: bool = False) -> QImage:
    theme = theme or styles.current_theme()
    size = total_size(programs, theme)
    pixels = QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale)))
    # RGBA8888: Qt glättet Text hier in Graustufen. Bei ARGB32/RGB32 nutzt es unter
    # Windows ClearType → farbige Säume im Bild (auch mit NoSubpixelAntialias).
    image = QImage(pixels, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(Qt.GlobalColor.transparent if transparent else QColor(theme.canvas_bg if theme.name == "dark"
                                                                       else "#FFFFFF"))
    painter = QPainter(image)
    painter.scale(scale, scale)
    paint_programs(painter, programs, theme)
    painter.end()
    return image


def export_nsd(programs: list[Program], path: str, fmt: str, theme=None) -> None:
    """Exportiert das Struktogramm als PNG, SVG oder PDF. Wirft ``ExportError``."""
    theme = theme or styles.LIGHT
    if not programs:
        raise ExportError(tr("Es gibt kein Struktogramm zu exportieren (kein Start-Element)."))
    fmt = fmt.upper()
    name = os.path.basename(path)
    if fmt == "PNG":
        if not render_image(programs, theme, 2.0).save(path, "PNG"):
            raise ExportError(tr("Die Datei „{name}“ konnte nicht geschrieben werden.", name=name))
        return
    size = total_size(programs, theme)
    painter = QPainter()
    if fmt == "SVG":
        from PySide6.QtSvg import QSvgGenerator

        device = QSvgGenerator()
        device.setFileName(path)
        device.setSize(QSize(int(size.width()), int(size.height())))
        device.setViewBox(QRectF(0, 0, size.width(), size.height()))
        device.setTitle(tr("Struktogramm – {app}", app=config.APP_NAME))
        if not painter.begin(device):
            raise ExportError(tr("Die Datei „{name}“ konnte nicht geschrieben werden.", name=name))
        try:
            painter.fillRect(QRectF(0, 0, size.width(), size.height()), QColor("#FFFFFF"))
            paint_programs(painter, programs, theme)
        finally:
            painter.end()
        return
    if fmt == "PDF":
        writer = QPdfWriter(path)
        writer.setCreator(config.APP_NAME)
        writer.setResolution(300)
        page = QPageSize(QSizeF(size.width() * 72 / 96, size.height() * 72 / 96), QPageSize.Unit.Point,
                         tr("Struktogramm"), QPageSize.SizeMatchPolicy.ExactMatch)
        writer.setPageLayout(QPageLayout(page, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
        if not painter.begin(writer):
            raise ExportError(tr("Die Datei „{name}“ konnte nicht geschrieben werden.", name=name))
        try:
            factor = writer.width() / size.width()
            painter.scale(factor, factor)
            paint_programs(painter, programs, theme)
        finally:
            painter.end()
        return
    raise ExportError(tr("Unbekanntes Format „{format}“.", format=fmt))
