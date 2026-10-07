"""Programmatisch gezeichnete Vektor-Icons.

Alle Icons werden zur Laufzeit mit ``QPainter`` erzeugt – es werden keine
externen Bilddateien oder Icon-Pakete benötigt. Gezeichnet wird auf einem
24×24-Raster mit einheitlicher Strichstärke.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from app import styles
from app.items.shapes import geometry_for, paint_shape
from app.model.element_types import LOOP_BEGIN, LOOP_PART_KEY, ElementType

ICON_SIZE = 24


def _pen(color: QColor, width: float = 1.6) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _arrow_head(p: QPainter, tip: QPointF, direction: str, size: float = 3.2) -> None:
    x, y = tip.x(), tip.y()
    if direction == "right":
        pts = [QPointF(x - size, y - size), tip, QPointF(x - size, y + size)]
    elif direction == "left":
        pts = [QPointF(x + size, y - size), tip, QPointF(x + size, y + size)]
    elif direction == "up":
        pts = [QPointF(x - size, y + size), tip, QPointF(x + size, y + size)]
    else:
        pts = [QPointF(x - size, y - size), tip, QPointF(x + size, y - size)]
    path = QPainterPath(pts[0])
    path.lineTo(pts[1])
    path.lineTo(pts[2])
    p.drawPath(path)


# --------------------------------------------------------------- Zeichner
def _draw_new(p, c):
    path = QPainterPath()
    path.moveTo(6, 3.5)
    path.lineTo(14, 3.5)
    path.lineTo(18.5, 8)
    path.lineTo(18.5, 20.5)
    path.lineTo(6, 20.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(14, 3.5), QPointF(14, 8))
    p.drawLine(QPointF(14, 8), QPointF(18.5, 8))
    p.drawLine(QPointF(12.25, 11.5), QPointF(12.25, 17))
    p.drawLine(QPointF(9.5, 14.25), QPointF(15, 14.25))


def _draw_open(p, c):
    path = QPainterPath()
    path.moveTo(3.5, 18.5)
    path.lineTo(3.5, 6)
    path.lineTo(9, 6)
    path.lineTo(11, 8)
    path.lineTo(18, 8)
    path.lineTo(18, 10.5)
    p.drawPath(path)
    path2 = QPainterPath()
    path2.moveTo(3.5, 18.5)
    path2.lineTo(6.5, 10.5)
    path2.lineTo(21, 10.5)
    path2.lineTo(18, 18.5)
    path2.closeSubpath()
    p.drawPath(path2)


def _draw_save(p, c):
    path = QPainterPath()
    path.moveTo(4.5, 4.5)
    path.lineTo(16.5, 4.5)
    path.lineTo(19.5, 7.5)
    path.lineTo(19.5, 19.5)
    path.lineTo(4.5, 19.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawRect(QRectF(8, 4.5, 7, 4.5))
    p.drawRect(QRectF(7.5, 13, 9, 6.5))


def _draw_save_as(p, c):
    _draw_save(p, c)
    p.drawLine(QPointF(15, 21), QPointF(21, 15))


def _draw_close(p, c):
    p.drawLine(QPointF(7, 7), QPointF(17, 17))
    p.drawLine(QPointF(17, 7), QPointF(7, 17))


def _draw_undo(p, c):
    path = QPainterPath()
    path.moveTo(8, 9)
    path.lineTo(15, 9)
    path.cubicTo(18.5, 9, 20, 11.5, 20, 13.5)
    path.cubicTo(20, 16, 18, 18, 15, 18)
    path.lineTo(10, 18)
    p.drawPath(path)
    _arrow_head(p, QPointF(4.5, 9), "left", 3.5)
    p.drawLine(QPointF(4.5, 9), QPointF(8, 9))


def _draw_redo(p, c):
    p.save()
    p.translate(24, 0)
    p.scale(-1, 1)
    _draw_undo(p, c)
    p.restore()


def _draw_cut(p, c):
    p.drawEllipse(QPointF(7.5, 17), 2.7, 2.7)
    p.drawEllipse(QPointF(16.5, 17), 2.7, 2.7)
    p.drawLine(QPointF(9.3, 15), QPointF(17, 4))
    p.drawLine(QPointF(14.7, 15), QPointF(7, 4))


def _draw_copy(p, c):
    p.drawRoundedRect(QRectF(8.5, 8.5, 11, 11.5), 1.5, 1.5)
    path = QPainterPath()
    path.moveTo(5, 15.5)
    path.lineTo(4.5, 15.5)
    path.lineTo(4.5, 4.5)
    path.lineTo(15.5, 4.5)
    path.lineTo(15.5, 5)
    p.drawPath(path)


def _draw_paste(p, c):
    p.drawRoundedRect(QRectF(5.5, 5.5, 13, 15), 1.5, 1.5)
    p.drawRoundedRect(QRectF(9, 3.5, 6, 3.5), 1, 1)
    p.drawLine(QPointF(9, 12), QPointF(15, 12))
    p.drawLine(QPointF(9, 15.5), QPointF(13.5, 15.5))


def _draw_delete(p, c):
    p.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
    p.drawLine(QPointF(9.5, 7), QPointF(10, 4.5))
    p.drawLine(QPointF(10, 4.5), QPointF(14, 4.5))
    p.drawLine(QPointF(14, 4.5), QPointF(14.5, 7))
    path = QPainterPath()
    path.moveTo(6.5, 7)
    path.lineTo(7.5, 20)
    path.lineTo(16.5, 20)
    path.lineTo(17.5, 7)
    p.drawPath(path)
    p.drawLine(QPointF(10.5, 10.5), QPointF(10.5, 16.5))
    p.drawLine(QPointF(13.5, 10.5), QPointF(13.5, 16.5))


def _draw_duplicate(p, c):
    p.drawRoundedRect(QRectF(4.5, 4.5, 10, 10), 1.5, 1.5)
    p.drawRoundedRect(QRectF(9.5, 9.5, 10, 10), 1.5, 1.5)


def _draw_select_all(p, c):
    pen = p.pen()
    dashed = QPen(pen)
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    p.drawRect(QRectF(4, 4, 16, 16))
    p.setPen(pen)
    p.drawRect(QRectF(8, 8, 8, 8))


def _magnifier(p):
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20, 20))


def _draw_zoom_in(p, c):
    _magnifier(p)
    p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))
    p.drawLine(QPointF(10.5, 7.5), QPointF(10.5, 13.5))


def _draw_zoom_out(p, c):
    _magnifier(p)
    p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))


def _draw_zoom_reset(p, c):
    _magnifier(p)
    p.drawLine(QPointF(9.5, 8), QPointF(11, 7.5))
    p.drawLine(QPointF(11, 7.5), QPointF(11, 13.5))


def _draw_zoom_fit(p, c):
    for (x, y, dx, dy) in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + 5 * dx, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + 5 * dy))
    p.drawRoundedRect(QRectF(8.5, 9, 7, 6), 1, 1)


def _draw_grid(p, c):
    p.setBrush(c)
    for x in (6, 12, 18):
        for y in (6, 12, 18):
            p.drawEllipse(QPointF(x, y), 1.1, 1.1)


def _draw_snap(p, c):
    path = QPainterPath()
    path.moveTo(6, 4.5)
    path.lineTo(6, 12)
    path.cubicTo(6, 18.5, 18, 18.5, 18, 12)
    path.lineTo(18, 4.5)
    p.drawPath(path)
    p.drawLine(QPointF(10, 4.5), QPointF(10, 12))
    p.drawLine(QPointF(14, 4.5), QPointF(14, 12))
    p.drawLine(QPointF(5, 8), QPointF(10, 8))
    p.drawLine(QPointF(14, 8), QPointF(19, 8))


def _align_bars(p, bars, vertical_axis):
    for rect in bars:
        p.drawRoundedRect(QRectF(*rect), 1, 1)


def _draw_align_left(p, c):
    p.drawLine(QPointF(4.5, 3.5), QPointF(4.5, 20.5))
    _align_bars(p, [(7, 6, 12, 4.5), (7, 13.5, 7, 4.5)], True)


def _draw_align_right(p, c):
    p.drawLine(QPointF(19.5, 3.5), QPointF(19.5, 20.5))
    _align_bars(p, [(5, 6, 12, 4.5), (10, 13.5, 7, 4.5)], True)


def _draw_align_top(p, c):
    p.drawLine(QPointF(3.5, 4.5), QPointF(20.5, 4.5))
    _align_bars(p, [(6, 7, 4.5, 12), (13.5, 7, 4.5, 7)], False)


def _draw_align_bottom(p, c):
    p.drawLine(QPointF(3.5, 19.5), QPointF(20.5, 19.5))
    _align_bars(p, [(6, 5, 4.5, 12), (13.5, 10, 4.5, 7)], False)


def _draw_align_center_x(p, c):
    p.drawLine(QPointF(12, 3), QPointF(12, 21))
    _align_bars(p, [(6, 6, 12, 4.5), (8.5, 13.5, 7, 4.5)], True)


def _draw_align_center_y(p, c):
    p.drawLine(QPointF(3, 12), QPointF(21, 12))
    _align_bars(p, [(6, 6, 4.5, 12), (13.5, 8.5, 4.5, 7)], False)


def _draw_distribute_h(p, c):
    p.drawLine(QPointF(3.5, 4), QPointF(3.5, 20))
    p.drawLine(QPointF(20.5, 4), QPointF(20.5, 20))
    p.drawRoundedRect(QRectF(9.5, 7, 5, 10), 1, 1)


def _draw_distribute_v(p, c):
    p.drawLine(QPointF(4, 3.5), QPointF(20, 3.5))
    p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))
    p.drawRoundedRect(QRectF(7, 9.5, 10, 5), 1, 1)


def _draw_front(p, c):
    p.drawRoundedRect(QRectF(4.5, 4.5, 10, 10), 1.5, 1.5)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(9.5, 9.5, 10, 10), 1.5, 1.5)


def _draw_back(p, c):
    p.setBrush(c)
    p.drawRoundedRect(QRectF(4.5, 4.5, 10, 10), 1.5, 1.5)
    p.setBrush(QColor(styles.current_theme().window_bg))
    p.drawRoundedRect(QRectF(9.5, 9.5, 10, 10), 1.5, 1.5)


def _draw_export(p, c):
    path = QPainterPath()
    path.moveTo(9, 6.5)
    path.lineTo(5, 6.5)
    path.lineTo(5, 19.5)
    path.lineTo(19, 19.5)
    path.lineTo(19, 15)
    p.drawPath(path)
    p.drawLine(QPointF(11, 13), QPointF(19.5, 4.5))
    p.drawLine(QPointF(14, 4.5), QPointF(19.5, 4.5))
    p.drawLine(QPointF(19.5, 4.5), QPointF(19.5, 10))


def _draw_print(p, c):
    p.drawRect(QRectF(7, 3.5, 10, 5))
    p.drawRoundedRect(QRectF(3.5, 8.5, 17, 8), 1.5, 1.5)
    p.drawRect(QRectF(7, 13.5, 10, 7))


def _draw_properties(p, c):
    for y, x in ((7, 15), (12, 8), (17, 13)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.setBrush(QColor(styles.current_theme().window_bg))
        p.drawEllipse(QPointF(x, y), 2, 2)


def _draw_info(p, c):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawLine(QPointF(12, 11), QPointF(12, 16.5))
    p.setBrush(c)
    p.drawEllipse(QPointF(12, 7.8), 0.6, 0.6)


def _draw_keyboard(p, c):
    p.drawRoundedRect(QRectF(3, 6.5, 18, 11), 2, 2)
    for x in (6.5, 10, 13.5, 17):
        p.drawPoint(QPointF(x, 10))
    p.drawLine(QPointF(8, 14), QPointF(16, 14))


def _draw_connect(p, c):
    p.drawRoundedRect(QRectF(3.5, 3.5, 8, 5), 1, 1)
    p.drawRoundedRect(QRectF(12.5, 15.5, 8, 5), 1, 1)
    p.drawLine(QPointF(7.5, 8.5), QPointF(7.5, 12))
    p.drawLine(QPointF(7.5, 12), QPointF(16.5, 12))
    p.drawLine(QPointF(16.5, 12), QPointF(16.5, 15))
    _arrow_head(p, QPointF(16.5, 15.2), "down", 2.2)


def _draw_register(p, c):
    _draw_new(p, c)


def _draw_code(p, c):
    p.drawPolyline(QPolygonF([QPointF(8, 7), QPointF(3.5, 12), QPointF(8, 17)]))
    p.drawPolyline(QPolygonF([QPointF(16, 7), QPointF(20.5, 12), QPointF(16, 17)]))
    p.drawLine(QPointF(13.5, 5), QPointF(10.5, 19))


def _draw_structogram(p, c):
    p.drawRect(QRectF(4, 4, 16, 16))
    p.drawLine(QPointF(4, 8.5), QPointF(20, 8.5))
    p.drawLine(QPointF(4, 8.5), QPointF(12, 14))
    p.drawLine(QPointF(20, 8.5), QPointF(12, 14))
    p.drawLine(QPointF(12, 14), QPointF(12, 20))


def _draw_layout(p, c):
    p.drawRoundedRect(QRectF(8, 3.5, 8, 4.5), 1, 1)
    p.drawRoundedRect(QRectF(3.5, 16, 7, 4.5), 1, 1)
    p.drawRoundedRect(QRectF(13.5, 16, 7, 4.5), 1, 1)
    p.drawLine(QPointF(12, 8), QPointF(12, 12))
    p.drawLine(QPointF(7, 12), QPointF(17, 12))
    p.drawLine(QPointF(7, 12), QPointF(7, 16))
    p.drawLine(QPointF(17, 12), QPointF(17, 16))


def _draw_play(p, c):
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)]))


def _draw_step(p, c):
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(6, 6), QPointF(14, 12), QPointF(6, 18)]))
    p.drawLine(QPointF(17.5, 6), QPointF(17.5, 18))


def _draw_stop(p, c):
    p.setBrush(c)
    p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 1.5, 1.5)


def _draw_restart(p, c):
    path = QPainterPath()
    path.arcMoveTo(QRectF(5, 5, 14, 14), 60)
    path.arcTo(QRectF(5, 5, 14, 14), 60, 300)
    p.drawPath(path)
    _arrow_head(p, QPointF(15.5, 6), "right", 3)


def _draw_warning(p, c):
    path = QPainterPath()
    path.moveTo(12, 4)
    path.lineTo(21, 19.5)
    path.lineTo(3, 19.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(12, 10), QPointF(12, 14))
    p.setBrush(c)
    p.drawEllipse(QPointF(12, 16.8), 0.6, 0.6)


_DRAWERS = {
    "new": _draw_new, "open": _draw_open, "save": _draw_save, "save_as": _draw_save_as,
    "close": _draw_close, "undo": _draw_undo, "redo": _draw_redo, "cut": _draw_cut,
    "copy": _draw_copy, "paste": _draw_paste, "delete": _draw_delete, "duplicate": _draw_duplicate,
    "select_all": _draw_select_all, "zoom_in": _draw_zoom_in, "zoom_out": _draw_zoom_out,
    "zoom_reset": _draw_zoom_reset, "zoom_fit": _draw_zoom_fit, "grid": _draw_grid, "snap": _draw_snap,
    "align_left": _draw_align_left, "align_right": _draw_align_right, "align_top": _draw_align_top,
    "align_bottom": _draw_align_bottom, "align_center_x": _draw_align_center_x,
    "align_center_y": _draw_align_center_y, "distribute_h": _draw_distribute_h,
    "distribute_v": _draw_distribute_v, "front": _draw_front, "back": _draw_back,
    "export": _draw_export, "print": _draw_print, "properties": _draw_properties, "info": _draw_info,
    "keyboard": _draw_keyboard, "connect": _draw_connect, "register": _draw_register,
    "code": _draw_code, "structogram": _draw_structogram, "layout": _draw_layout, "play": _draw_play,
    "step": _draw_step, "stop": _draw_stop, "restart": _draw_restart, "warning": _draw_warning,
}


def _render(name: str, color: QColor, dpr: float) -> QPixmap:
    size = int(ICON_SIZE * dpr)
    pixmap = QPixmap(size, size)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(_pen(color))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _DRAWERS[name](painter, color)
    painter.end()
    return pixmap


def icon(name: str) -> QIcon:
    """Liefert ein Icon (normal, aktiv und deaktiviert) im aktuellen Farbschema."""
    return _icon(name, styles.current_theme().name)


def element_icon(element_type: ElementType) -> QIcon:
    """Kleines Icon der echten Bausteinform (für Menüs) im aktuellen Farbschema."""
    return _element_icon(ElementType(element_type), styles.current_theme().name)


def clear_cache() -> None:
    """Nach einem Wechsel des Farbschemas: Icons neu zeichnen."""
    _icon.cache_clear()
    _element_icon.cache_clear()


def _theme_by_name(name: str):
    for theme in (styles.current_theme(), *styles.UI_THEMES.values()):
        if theme.name == name:
            return theme
    return styles.current_theme()


@lru_cache(maxsize=None)
def _icon(name: str, theme_name: str) -> QIcon:
    if name not in _DRAWERS:
        return QIcon()
    theme = _theme_by_name(theme_name)
    result = QIcon()
    for dpr in (1.0, 2.0):
        result.addPixmap(_render(name, QColor(theme.text), dpr), QIcon.Mode.Normal)
        result.addPixmap(_render(name, QColor(theme.accent_hover), dpr), QIcon.Mode.Active)
        result.addPixmap(_render(name, QColor(theme.text_disabled), dpr), QIcon.Mode.Disabled)
    return result


@lru_cache(maxsize=None)
def _element_icon(element_type: ElementType, theme_name: str) -> QIcon:
    geometry = geometry_for(element_type)
    colors = _theme_by_name(theme_name).element_colors(element_type)
    result = QIcon()
    for dpr in (1.0, 2.0):
        size = int(ICON_SIZE * dpr)
        pixmap = QPixmap(size, size)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(12, 12)
        w, h = (20.0, 20.0) if element_type is ElementType.DECISION else (21.0, 11.0)
        if element_type in (ElementType.START, ElementType.END):
            w, h = 21.0, 10.0
        # Formen wirken erst bei Originalproportionen richtig; daher skalieren
        scale = w / 80.0
        painter.scale(scale, scale)
        props = {LOOP_PART_KEY: LOOP_BEGIN} if element_type is ElementType.LOOP else None
        paint_shape(painter, geometry, w / scale, h / scale, colors, props, pen_width=1.3 / scale)
        painter.end()
        result.addPixmap(pixmap)
    return result


@lru_cache(maxsize=None)
def app_icon() -> QIcon:
    """Programmsymbol: stilisierter Programmablaufplan."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(render_app_icon(size))
    return result


def render_app_icon(size: int) -> QPixmap:
    theme = styles.DARK
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 64.0
    p.scale(s, s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#23272E"))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 13, 13)
    line = QPen(QColor(theme.connection_hover), 2.6)
    line.setCapStyle(Qt.PenCapStyle.RoundCap)
    # Start
    p.setPen(QPen(QColor(theme.element_accents[ElementType.START]), 2.6))
    p.setBrush(QColor("#2E333B"))
    p.drawRoundedRect(QRectF(20, 8, 24, 10), 5, 5)
    # Verbindung
    p.setPen(line)
    p.drawLine(QPointF(32, 18), QPointF(32, 23))
    # Verzweigung
    p.setPen(QPen(QColor(theme.element_accents[ElementType.DECISION]), 2.6))
    p.setBrush(QColor("#3A3124"))
    p.drawPolygon(QPolygonF([QPointF(32, 23), QPointF(44, 32), QPointF(32, 41), QPointF(20, 32)]))
    p.setPen(line)
    p.drawLine(QPointF(32, 41), QPointF(32, 46))
    p.drawLine(QPointF(44, 32), QPointF(52, 32))
    p.drawLine(QPointF(52, 32), QPointF(52, 50))
    # Vorgang
    p.setPen(QPen(QColor(theme.element_accents[ElementType.PROCESS]), 2.6))
    p.setBrush(QColor("#243149"))
    p.drawRoundedRect(QRectF(19, 46, 26, 10), 1.5, 1.5)
    p.end()
    return pixmap
