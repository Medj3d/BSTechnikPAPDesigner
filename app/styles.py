"""Farben, Schriften und Stylesheet der Anwendung.

Es gibt zwei Farbschemata:

* ``DARK``  – Standard für die Bearbeitung (augenschonend, gedämpfte Akzente)
* ``LIGHT`` – für Export und Druck auf weißem Hintergrund

Die Farben dienen ausschließlich der visuellen Unterscheidung; die Bedeutung
eines Bausteins ergibt sich aus Form und Beschriftung.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from app import config, i18n
from app.model.element_types import ElementType


def mix(color_a: str, color_b: str, amount: float) -> str:
    """Mischt zwei Farben. ``amount`` = Anteil von ``color_a`` (0..1)."""
    a, b = QColor(color_a), QColor(color_b)
    r = a.redF() * amount + b.redF() * (1 - amount)
    g = a.greenF() * amount + b.greenF() * (1 - amount)
    bl = a.blueF() * amount + b.blueF() * (1 - amount)
    return QColor.fromRgbF(r, g, bl).name()


@dataclass(frozen=True)
class ElementColors:
    border: str
    fill: str
    text: str


@dataclass(frozen=True)
class Theme:
    name: str
    window_bg: str
    panel_bg: str
    panel_raised: str
    canvas_bg: str
    grid_dot: str
    grid_dot_major: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_disabled: str
    accent: str
    accent_hover: str
    accent_text: str
    selection: str
    connection: str
    connection_hover: str
    connection_invalid: str
    label_bg: str
    label_text: str
    port_fill: str
    danger: str
    element_text: str
    element_accents: dict = field(default_factory=dict)
    fill_amount: float = 0.16

    def element_colors(self, element_type: ElementType) -> ElementColors:
        accent = self.element_accents[ElementType(element_type)]
        return ElementColors(
            border=accent,
            fill=mix(accent, self.canvas_bg, self.fill_amount),
            text=self.element_text,
        )


DARK = Theme(
    name="dark",
    window_bg="#1F2227",
    panel_bg="#24272D",
    panel_raised="#2B2F36",
    canvas_bg="#1B1D21",
    grid_dot="#34383F",
    grid_dot_major="#434852",
    border="#30343B",
    border_strong="#3E434C",
    text="#D6DAE0",
    text_muted="#8D949E",
    text_disabled="#5C626B",
    accent="#5B96E8",
    accent_hover="#6FA4EE",
    accent_text="#F2F5F9",
    selection="#6FA8F2",
    connection="#8E959F",
    connection_hover="#BAC1CA",
    connection_invalid="#D46A6A",
    label_bg="#1B1D21",
    label_text="#C8CDD4",
    port_fill="#1B1D21",
    danger="#D46A6A",
    element_text="#E2E5EA",
    element_accents={
        ElementType.START: "#A7B0BC",
        ElementType.END: "#A7B0BC",
        ElementType.INPUT: "#4FB2A4",
        ElementType.OUTPUT: "#B28BD8",
        ElementType.PROCESS: "#6A9ADF",
        ElementType.SUBPROGRAM: "#8BB16C",
        ElementType.DECISION: "#DCA35B",
        ElementType.LOOP: "#D6808A",
        ElementType.COMMENT: "#868D97",
        ElementType.JUNCTION: "#8E959F",
    },
    fill_amount=0.15,
)

LIGHT = Theme(
    name="light",
    window_bg="#F4F5F7",
    panel_bg="#FFFFFF",
    panel_raised="#F0F1F3",
    canvas_bg="#FFFFFF",
    grid_dot="#D5D8DD",
    grid_dot_major="#C2C6CD",
    border="#D9DCE1",
    border_strong="#C5C9D0",
    text="#1F2328",
    text_muted="#5E6570",
    text_disabled="#A0A6AF",
    accent="#2F6FCE",
    accent_hover="#3C7BD8",
    accent_text="#FFFFFF",
    selection="#2F6FCE",
    connection="#4A5059",
    connection_hover="#2B3036",
    connection_invalid="#C0392B",
    label_bg="#FFFFFF",
    label_text="#2B3036",
    port_fill="#FFFFFF",
    danger="#C0392B",
    element_text="#1F2328",
    element_accents={
        ElementType.START: "#5B6573",
        ElementType.END: "#5B6573",
        ElementType.INPUT: "#23857A",
        ElementType.OUTPUT: "#7B55A6",
        ElementType.PROCESS: "#3A6CB2",
        ElementType.SUBPROGRAM: "#58873A",
        ElementType.DECISION: "#B4762A",
        ElementType.LOOP: "#B2525C",
        ElementType.COMMENT: "#6B727C",
        ElementType.JUNCTION: "#4A5059",
    },
    fill_amount=0.09,
)

THEMES = {"dark": DARK, "light": LIGHT}

# Helles Farbschema für die Bedienoberfläche (z. B. für Beamer). Die
# Arbeitsfläche ist leicht getönt, damit weiße Flächen nicht blenden.
LIGHT_UI = Theme(
    name="light_ui",
    window_bg="#ECEEF1",
    panel_bg="#F6F7F9",
    panel_raised="#FFFFFF",
    canvas_bg="#F9FAFB",
    grid_dot="#CBD0D7",
    grid_dot_major="#AFB6C0",
    border="#D6DAE0",
    border_strong="#BFC5CE",
    text="#1D2229",
    text_muted="#5B6370",
    text_disabled="#A2A9B3",
    accent="#2F6FCE",
    accent_hover="#3A7AD8",
    accent_text="#FFFFFF",
    selection="#2F6FCE",
    connection="#565D68",
    connection_hover="#262B32",
    connection_invalid="#D03A3C",
    label_bg="#F9FAFB",
    label_text="#2A2F36",
    port_fill="#FFFFFF",
    danger="#C0392B",
    element_text="#1D2229",
    element_accents={
        ElementType.START: "#5B6573",
        ElementType.END: "#5B6573",
        ElementType.INPUT: "#23857A",
        ElementType.OUTPUT: "#7B55A6",
        ElementType.PROCESS: "#3A6CB2",
        ElementType.SUBPROGRAM: "#58873A",
        ElementType.DECISION: "#B4762A",
        ElementType.LOOP: "#B2525C",
        ElementType.COMMENT: "#6B727C",
        ElementType.JUNCTION: "#565D68",
    },
    fill_amount=0.11,
)

# Umschaltbare Farbschemata der Bedienoberfläche
UI_THEMES = {"dark": DARK, "light": LIGHT_UI}

# Aktuelles Farbschema der Bedienoberfläche (Editor). Export/Druck wählen ihr
# Schema unabhängig davon.
_current_theme: Theme = DARK


def current_theme() -> Theme:
    """Farbschema der Bedienoberfläche (dunkel oder hell)."""
    return _current_theme


def set_current_theme(theme: Theme) -> None:
    global _current_theme
    _current_theme = theme


def ui_font(point_size: float = 9.5) -> QFont:
    font = QFont()
    # Die Schriften für Chinesisch, Japanisch, … stehen dahinter: Qt greift je Zeichen auf sie zurück
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial",
                      *i18n.font_fallbacks()])
    font.setPointSizeF(point_size)
    return font


def item_font(pixel_size: int = config.ITEM_FONT_PIXEL_SIZE) -> QFont:
    """Schrift für Text in Bausteinen.

    Die Größe wird in Pixeln (= Szeneneinheiten) angegeben, damit der Text
    gemeinsam mit dem Diagramm zoomt. Hinting ist abgeschaltet, damit die
    Textbreite bei jeder Zoomstufe identisch bleibt.
    """
    font = QFont()
    font.setFamilies(config.ITEM_FONT_FAMILIES)
    font.setPixelSize(pixel_size)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def apply_application_style(app: QApplication, theme: Theme = DARK) -> None:
    """Setzt Fusion-Stil, dunkle Palette und das Stylesheet."""
    app.setStyle("Fusion")
    app.setFont(ui_font())
    app.setPalette(build_palette(theme))
    app.setStyleSheet(build_stylesheet(theme))


def build_palette(t: Theme) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    p.setColor(role.Window, QColor(t.window_bg))
    p.setColor(role.WindowText, QColor(t.text))
    p.setColor(role.Base, QColor(t.panel_bg))
    p.setColor(role.AlternateBase, QColor(t.panel_raised))
    p.setColor(role.ToolTipBase, QColor(t.panel_raised))
    p.setColor(role.ToolTipText, QColor(t.text))
    p.setColor(role.PlaceholderText, QColor(t.text_muted))
    p.setColor(role.Text, QColor(t.text))
    p.setColor(role.Button, QColor(t.panel_raised))
    p.setColor(role.ButtonText, QColor(t.text))
    p.setColor(role.BrightText, QColor(t.danger))
    p.setColor(role.Highlight, QColor(t.accent))
    p.setColor(role.HighlightedText, QColor(t.accent_text))
    p.setColor(role.Link, QColor(t.accent_hover))
    p.setColor(role.Light, QColor(t.border_strong))
    p.setColor(role.Midlight, QColor(t.border))
    p.setColor(role.Mid, QColor(t.border))
    p.setColor(role.Dark, QColor(t.window_bg))
    p.setColor(role.Shadow, QColor("#101114"))
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(group.Disabled, r, QColor(t.text_disabled))
    return p


def build_stylesheet(t: Theme) -> str:
    return f"""
QMainWindow, QDialog {{
    background: {t.window_bg};
    color: {t.text};
}}
QWidget {{
    color: {t.text};
}}
QToolTip {{
    background: {t.panel_raised};
    color: {t.text};
    border: 1px solid {t.border_strong};
    padding: 4px 6px;
}}
QMenuBar {{
    background: {t.window_bg};
    border-bottom: 1px solid {t.border};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {t.panel_raised};
}}
QMenu {{
    background: {t.panel_bg};
    border: 1px solid {t.border_strong};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 28px 5px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {t.panel_raised};
}}
QMenu::item:disabled {{
    color: {t.text_disabled};
}}
QMenu::separator {{
    height: 1px;
    background: {t.border};
    margin: 4px 6px;
}}
QMenu::icon {{
    padding-left: 6px;
}}
QToolBar {{
    background: {t.window_bg};
    border: none;
    border-bottom: 1px solid {t.border};
    padding: 3px 6px;
    spacing: 2px;
}}
QToolBar::separator {{
    width: 1px;
    background: {t.border};
    margin: 5px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px;
}}
QToolButton:hover {{
    background: {t.panel_raised};
    border-color: {t.border};
}}
QToolButton:pressed {{
    background: {t.border};
}}
QToolButton:checked {{
    background: {t.panel_raised};
    border-color: {t.border_strong};
}}
QStatusBar {{
    background: {t.window_bg};
    border-top: 1px solid {t.border};
    color: {t.text_muted};
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    color: {t.text_muted};
    padding: 0 8px;
}}
QDockWidget {{
    color: {t.text_muted};
    titlebar-close-icon: none;
}}
QDockWidget::title {{
    background: {t.window_bg};
    padding: 6px 10px;
    border-bottom: 1px solid {t.border};
}}
QTabWidget::pane {{
    border: none;
}}
QTabBar {{
    background: {t.window_bg};
}}
QTabBar::tab {{
    background: {t.window_bg};
    color: {t.text_muted};
    padding: 6px 14px;
    border: none;
    border-right: 1px solid {t.border};
    min-width: 80px;
}}
QTabBar::tab:selected {{
    background: {t.canvas_bg};
    color: {t.text};
    border-top: 2px solid {t.accent};
}}
QTabBar::tab:hover:!selected {{
    background: {t.panel_bg};
    color: {t.text};
}}
QToolButton#TabCloseButton {{
    padding: 2px;
    border: none;
    border-radius: 3px;
    background: transparent;
}}
QToolButton#TabCloseButton:hover {{
    background: {t.border_strong};
}}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t.canvas_bg};
    border: 1px solid {t.border_strong};
    border-radius: 5px;
    padding: 4px 6px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {t.accent};
}}
QLineEdit:read-only {{
    color: {t.text_muted};
    background: {t.panel_bg};
}}
QComboBox QAbstractItemView {{
    background: {t.panel_bg};
    border: 1px solid {t.border_strong};
    selection-background-color: {t.panel_raised};
}}
QPushButton {{
    background: {t.panel_raised};
    border: 1px solid {t.border_strong};
    border-radius: 5px;
    padding: 6px 16px;
    min-width: 72px;
}}
QPushButton:hover {{
    border-color: {t.text_muted};
}}
QPushButton:pressed {{
    background: {t.border};
}}
QPushButton:default {{
    background: {t.accent};
    border-color: {t.accent};
    color: {t.accent_text};
}}
QPushButton:default:hover {{
    background: {t.accent_hover};
}}
QPushButton:disabled {{
    color: {t.text_disabled};
    border-color: {t.border};
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QGroupBox {{
    border: 1px solid {t.border};
    border-radius: 6px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {t.text_muted};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t.border_strong};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t.border_strong};
    border-radius: 4px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QTableWidget, QTreeWidget, QListWidget {{
    background: {t.panel_bg};
    border: 1px solid {t.border};
    gridline-color: {t.border};
}}
QHeaderView::section {{
    background: {t.panel_raised};
    color: {t.text_muted};
    border: none;
    border-right: 1px solid {t.border};
    padding: 4px 8px;
}}
QLabel#DialogTitle {{
    font-size: 15pt;
    font-weight: 600;
}}
QLabel#Muted {{
    color: {t.text_muted};
}}
QWidget#EmptyState {{
    background: {t.canvas_bg};
}}
QWidget#PaletteWidget {{
    background: {t.window_bg};
}}
QLabel#PaletteSection {{
    color: {t.text_muted};
    font-size: 8pt;
    font-weight: 600;
    padding: 8px 10px 2px 10px;
}}
"""
