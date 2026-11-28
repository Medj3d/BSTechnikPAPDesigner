"""Das Hauptfenster.

Aufbau: Menüleiste · kompakte Werkzeugleiste · Feld „Bausteine“ (rechts) ·
Arbeitsfläche mit Tabs (ein Projekt pro Tab) · Seitenleiste (Hauptprogramm
und Unterprogramme des Projekts) · Statusleiste.
"""

from __future__ import annotations

import logging
import os
import time

import shiboken6

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QUndoGroup
from PySide6.QtWidgets import (QApplication, QDialog, QDockWidget, QFileDialog, QHBoxLayout, QLabel,
                               QSizePolicy,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget,
                               QTabBar, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget)

from app import (alignment, clipboard, config, examples, export, file_association, i18n, icons, platforms, preferences, restart,
                 single_instance, styles, subprograms)
from app import theme as theme_module
from app.actions import ALIGN_ACTIONS, ActionRegistry, INSERTABLE_BLOCKS, clean_text, insert_action_name, sequence_text
from app.autosave import AutosaveManager
from app.block_list import BlockListPanel, ConnectDialog, can_connect, can_start_line, connect_targets
from app.block_list import item_title as block_title
from app.canvas import DiagramView
from app.codegen.dialog import CodeDialog
from app.codegen.live_panel import CodePanel
from app.diagnostics.panel import COUNT_ICON_SIZE, DiagnosticsPanel, count_icon
from app.minimap import Minimap
from app.simulation import breakpoints
from app.task_panel import TaskDialog, TaskPanel, ask_password
from app.dialogs.recovery import RecoveryDialog
from app.layout.auto_layout import apply_layout, plan_auto_layout
from app.nsd.dialog import StructogramDialog
from app.simulation.panel import SimulationPanel
from app.commands import ProjectPropertiesCommand, ViewSettingCommand
from app.connections.connection import ConnectionItem
from app.connections.follow import line_end
from app.connections.label import ConnectionLabel
from app.dialogs.about import AboutDialog
from app.dialogs.export_options import ExportOptionsDialog, StampSettings
from app.dialogs.project_properties import ProjectPropertiesDialog
from app.dialogs import settings as settings_dialog
from app.dialogs.notation import NotationDialog
from app.dialogs.shortcuts import ShortcutsDialog
from app.dialogs.subprogram_name import SubprogramNameDialog
from app.inline_editor import add_special_characters
from app.document import DiagramDocument, display_name_for_path
from app.fileformat.project import ProjectFileError
from app.fileformat.serializer import load_diagram
from app.items.base_item import FlowItem
from app.model.element_types import FLOW_TERMINALS, PALETTE_ORDER, ElementType, display_name_for
from app.page_bar import PageBar
from app.search_bar import SearchBar, SearchEntry
from app.palette import ToolPalette
from app.i18n import N_, tr
from app.settings_store import SettingsStore
from app.update_dialogs import UpdateController

log = logging.getLogger(__name__)

# Typen, in die sich ein Baustein über das Kontextmenü umwandeln lässt (wie im PapDesigner)
CHANGEABLE_TYPES = (ElementType.PROCESS, ElementType.INPUT, ElementType.OUTPUT, ElementType.SUBPROGRAM,
                    ElementType.DECISION, ElementType.START, ElementType.END)

# Version des gespeicherten Fensterlayouts (bei neuen Docks erhöhen)
WINDOW_STATE_VERSION = 2

# Anzeige „Auto-Speichern“ in der Statusleiste: Symbol mit Zustandspunkt; schmaler als das nur als Symbol
SAVE_STATE_ICON_SIZE = QSize(20, 18)
SAVE_STATE_COMPACT_WIDTH = 1400
BLOCK_LIST_WIDTH = 300   # Breite der Bausteinliste beim ersten Zeigen


def save_state_icon(state: str):
    """Speichern-Symbol mit einem farbigen Punkt: an (Akzentfarbe), aus (grau), sonst (orange)."""
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

    theme = styles.current_theme()
    color = {"auto": theme.accent, "off": theme.text_disabled}.get(state, theme.connection_caution)
    ratio = 3.0
    pixmap = QPixmap(int(SAVE_STATE_ICON_SIZE.width() * ratio), int(SAVE_STATE_ICON_SIZE.height() * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 1, icons.icon("save").pixmap(QSize(16, 16), ratio))
    painter.setPen(QPen(QColor(theme.window_bg), 1.5))
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(11.5, 9.5, 8, 8))
    painter.end()
    return QIcon(pixmap)


def language_label() -> str:
    """„Sprache / Language“: in jeder Oberflächensprache auch auf Englisch, damit man die Einstellung findet."""
    local = tr("Sprache", ctx="Oberfläche")
    return local if local.casefold() == "language" else f"{local} / Language"


class EmptyState(QWidget):
    """Anzeige, wenn kein Projekt geöffnet ist."""

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.setObjectName("EmptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._window = window
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = QLabel()
        logo.setPixmap(icons.render_app_icon(88))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(config.APP_NAME)
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel(tr("Kein Projekt geöffnet."))
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_button = QPushButton(tr("Neues Projekt"))
        new_button.setDefault(True)
        new_button.clicked.connect(window.new_document)
        open_button = QPushButton(tr("Projekt öffnen …"))
        open_button.clicked.connect(window.open_file_dialog)
        buttons.addWidget(new_button)
        buttons.addWidget(open_button)
        self.recent_box = QVBoxLayout()
        self.recent_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(6)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(14)
        layout.addLayout(buttons)
        layout.addSpacing(18)
        layout.addLayout(self.recent_box)

    def refresh_recent(self, files: list[str]) -> None:
        while self.recent_box.count():
            widget = self.recent_box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if not files:
            return
        caption = QLabel(tr("Zuletzt geöffnet"))
        caption.setObjectName("Muted")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_box.addWidget(caption)
        for path in files[:5]:
            button = QPushButton(os.path.basename(path))
            button.setToolTip(path)
            button.setFlat(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, p=path: self._window.open_file(p))
            self.recent_box.addWidget(button)


class MainWindow(QMainWindow):
    theme_changed = Signal(str)   # „dark“ oder „light“: das Einstellungsfenster folgt dem Knopf in der Werkzeugleiste

    def __init__(self, enable_autosave: bool = False, autosave_directory: str | None = None):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setAcceptDrops(True)
        self.resize(1400, 880)

        self.settings_store = SettingsStore()
        self._presentation: tuple | None = None  # (Fensterzustand, Fensterstatus) während der Präsentation
        self.undo_group = QUndoGroup(self)
        self.paste_tracker = clipboard.PasteTracker()
        self.export_options: dict[str, export.ExportOptions] = {}
        self._load_preferences()
        self.actions = ActionRegistry(self)
        self.autosave = AutosaveManager(autosave_directory, parent=self) if enable_autosave else None
        self.updates = UpdateController(self)
        self.instance_server = None  # lauscht auf Dateien weiterer Programmstarts (siehe app/single_instance.py)
        self._restart_files: list[str] | None = None  # gesetzt, solange ein Neustart (z. B. Sprachwechsel) läuft
        # Projekte, deren Änderungen der Benutzer schon verworfen hat (Update): beim Schließen nicht noch einmal fragen
        self.close_without_asking: set = set()
        # Automatisches Speichern bereits gespeicherter Projekte (kurz nach der letzten Änderung)
        self._auto_save_enabled = self.settings_store.auto_save()
        self._auto_save_pending: set = set()
        self._auto_save_since: float | None = None
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(config.AUTO_SAVE_DELAY_MS)
        self._auto_save_timer.timeout.connect(self._run_auto_save)

        self._build_central()
        self._build_menus()
        self._build_toolbar()
        self._build_palette()
        self._build_tool_docks()
        self._build_block_list()
        self._build_statusbar()
        self._connect_actions()
        self._sync_theme_actions()

        geometry = self.settings_store.window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings_store.window_state()
        if state is not None:
            self.restoreState(state, WINDOW_STATE_VERSION)
        # Die Hinweise sind beim Start immer zu – auch wenn sie beim letzten Beenden offen waren.
        # Geöffnet werden sie über den Knopf mit dem Zähler unten in der Statusleiste.
        self.diagnostics_dock.hide()
        self._apply_tools()

        QApplication.clipboard().dataChanged.connect(self._update_actions)
        self._refresh_recent_menu()
        self._update_ui()

    # ============================================================ Aufbau
    def _build_central(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # Seiten des angezeigten Projekts: Hauptprogramm und Unterprogramme
        self.page_bar = PageBar()
        self.page_bar.page_selected.connect(self.show_page)
        self.page_bar.add_requested.connect(self.new_subprogram)
        self.page_bar.rename_requested.connect(self.rename_subprogram)
        self.page_bar.delete_requested.connect(self.delete_subprogram)
        self.page_bar.action_requested.connect(self.page_command)
        self.page_bar.move_requested.connect(self.move_page_to)
        self.page_bar.caller_requested.connect(self.reveal_element)
        self.workspace = QWidget()
        workspace_layout = QVBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self.tabs, 1)
        workspace_layout.addWidget(self.page_bar)
        self.empty_state = EmptyState(self)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.workspace)
        self.stack.addWidget(self.empty_state)
        self.setCentralWidget(self.stack)

    def _build_menus(self) -> None:
        a = self.actions
        bar = self.menuBar()

        file_menu = bar.addMenu(tr("&Datei"))
        for name in ("new", "open"):
            file_menu.addAction(a[name])
        self.recent_menu = file_menu.addMenu(tr("&Zuletzt geöffnet"))
        file_menu.addAction(a["edit_task_file"])   # Lehrkraft: Aufgabendatei selbst ändern (sonst Kopie)
        file_menu.addSeparator()
        # „Automatisch speichern“ und „Sicherungskopie anlegen“ stellt man einmal ein: Einstellungen → Allgemein
        for name in ("save", "save_as", "save_all"):
            file_menu.addAction(a[name])
        file_menu.addSeparator()
        export_menu = file_menu.addMenu(icons.icon("export"), tr("E&xportieren"))
        for name in ("export_png", "export_jpg", "export_svg", "export_pdf"):
            export_menu.addAction(a[name])
        self.export_menu = export_menu
        file_menu.addAction(a["print_preview"])
        file_menu.addAction(a["print"])
        file_menu.addSeparator()
        file_menu.addAction(a["properties"])
        file_menu.addSeparator()
        file_menu.addAction(a["close"])
        file_menu.addAction(a["close_all"])
        file_menu.addAction(a["quit"])

        edit_menu = bar.addMenu(tr("&Bearbeiten"))
        for name in ("undo", "redo", None, "cut", "copy", "copy_image", "paste", "duplicate", "delete", None,
                     "select_all", "deselect", None, "edit_text", "connect_to"):
            if name is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(a[name])
        # Sonderzeichen in die gerade offene Texteingabe (wie „Symbolzeichen“ im PapDesigner)
        self.special_menu = edit_menu.addMenu(tr("&Sonderzeichen"))
        add_special_characters(self.special_menu, self._insert_special)
        edit_menu.addSeparator()
        edit_menu.addAction(a["extract_subprogram"])
        page_menu = edit_menu.addMenu(tr("S&eite"))
        for name in ("duplicate_page", "copy_page", "cut_page", "paste_page", None, "move_page_left",
                     "move_page_right"):
            if name is None:
                page_menu.addSeparator()
            else:
                page_menu.addAction(a[name])

        view_menu = bar.addMenu(tr("&Ansicht"))
        for name in ("zoom_in", "zoom_out", "zoom_reset", "zoom_fit", None, "toggle_grid", "toggle_snap"):
            if name is None:
                view_menu.addSeparator()
            else:
                view_menu.addAction(a[name])
        view_menu.addAction(a["presentation"])
        # Farbschema, Sprache und Werkzeugleiste stehen in den Einstellungen (Hell/Dunkel auch als Knopf oben rechts)
        view_menu.addSeparator()
        for name in ("open_subprogram", "next_page", "previous_page", "go_back", "go_forward"):
            view_menu.addAction(a[name])
        view_menu.addSeparator()
        # einem ausgewählten Pfeil folgen (auch im Kontextmenü des Pfeils)
        for name in ("jump_to_source", "jump_to_target"):
            view_menu.addAction(a[name])
        view_menu.addSeparator()
        self.view_menu = view_menu

        insert_menu = bar.addMenu(tr("&Einfügen", ctx="Menü"))  # Bausteine einfügen (nicht: aus der Zwischenablage)
        for element_type in PALETTE_ORDER:
            insert_menu.addAction(a[insert_action_name(element_type)])
            if element_type is ElementType.LOOP:
                for name in ("insert_loop_head", "insert_loop_foot"):
                    a[name].setIcon(icons.element_icon(ElementType.LOOP))
                    insert_menu.addAction(a[name])
        insert_menu.addAction(a[insert_action_name(ElementType.JUNCTION)])
        insert_menu.addAction(a[insert_action_name(ElementType.CONNECTOR)])
        insert_menu.addSeparator()
        for element_type in FLOW_TERMINALS:
            insert_menu.addAction(a[insert_action_name(element_type)])
        insert_menu.addSeparator()
        insert_menu.addAction(a["new_subprogram"])   # „Auswahl in Unterprogramm auslagern“ steht unter Bearbeiten

        arrange_menu = bar.addMenu(tr("An&ordnen"))
        for name in ALIGN_ACTIONS[:6]:
            arrange_menu.addAction(a[name])
        arrange_menu.addSeparator()
        for name in ALIGN_ACTIONS[6:]:
            arrange_menu.addAction(a[name])
        arrange_menu.addAction(a[alignment.SNAP_TO_GRID])
        arrange_menu.addSeparator()
        arrange_menu.addAction(a["bring_front"])
        arrange_menu.addAction(a["send_back"])
        arrange_menu.addSeparator()
        arrange_menu.addAction(a["toggle_loop_part"])
        arrange_menu.addAction(a["add_bend"])
        arrange_menu.addAction(a["reset_routing"])
        arrange_menu.addSeparator()
        arrange_menu.addAction(a["auto_layout"])

        extras_menu = bar.addMenu(tr("E&xtras"))
        extras_menu.addAction(a["generate_code"])
        extras_menu.addAction(a["structogram"])
        extras_menu.addSeparator()
        # Jeder Befehl steht in genau einem Menü: „Automatisch anordnen“ unter Anordnen, Schreibtischtest, Hinweise
        # und Aufgabe unter Ansicht; die Schalter für Pfeile und Prüfung in den Einstellungen
        self.extras_menu = extras_menu  # Haltepunkte, Aufgabe stellen, Suchen und Einstellungen in _build_tool_docks

        help_menu = bar.addMenu(tr("&Hilfe"))
        help_menu.addAction(a["shortcuts"])
        help_menu.addAction(a["notation_help"])   # was Schreibtischtest und Code in den Texten verstehen
        examples_menu = help_menu.addMenu(tr("&Lernbeispiele"))
        for path, title in examples.example_files():
            action = examples_menu.addAction(icons.icon("open"), tr(title))
            action.setStatusTip(tr("Lernbeispiel als neues, unbenanntes Projekt öffnen"))
            action.triggered.connect(lambda _=False, p=path: self.open_example(p))
        examples_menu.setEnabled(not examples_menu.isEmpty())
        help_menu.addSeparator()
        # „Dateityp registrieren“ und „Beim Start nach Updates suchen“: Einstellungen → Allgemein
        help_menu.addAction(a["check_updates"])
        help_menu.addSeparator()
        help_menu.addAction(a["about"])

    def _on_language_chosen(self, code: str) -> None:
        """Merkt sich die gewählte Sprache; sie gilt nach einem Neustart (auf Wunsch sofort)."""
        if code == self.settings_store.language():
            return
        self.settings_store.set_language(code)
        if i18n.resolve(code) == i18n.language():
            return  # die Systemsprache ist die, die ohnehin läuft
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(config.APP_NAME)
        box.setText(tr("Die Sprache wird nach einem Neustart des Programms geändert."))
        box.setInformativeText(tr("Gespeicherte Projekte werden danach wieder geöffnet."))
        now = box.addButton(tr("Jetzt neu starten"), QMessageBox.ButtonRole.AcceptRole)
        later = box.addButton(tr("Später"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(now)
        box.setEscapeButton(later)
        box.exec()
        if box.clickedButton() is now:
            self.restart_program()

    def restart_program(self) -> None:
        """Schließt das Programm (mit Nachfrage zum Speichern) und startet es neu.

        Die gespeicherten Projekte öffnen sich danach wieder. Bricht der Benutzer das Schließen ab,
        bleibt alles, wie es ist.
        """
        self._restart_files = [view.document.file_path for view in self.views() if view.document.file_path]
        self.close()

    def _build_toolbar(self) -> None:
        a = self.actions
        toolbar = QToolBar(tr("Werkzeugleiste"), self)
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        # Die Knöpfe entstehen in _finish_toolbar (dann gibt es auch die Docks); jeder lässt sich in den Einstellungen
        # (Werkzeugleiste) ein- und ausblenden. Im Menü und unter „Mehr“ steht immer alles.
        self._toolbar_groups: dict[str, list] = {}
        self._toolbar_segments: list[tuple] = []
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toolbar_end = toolbar.addWidget(spacer)
        self.search_bar = SearchBar(self.search_entries, self)
        self._search_action = toolbar.addWidget(self.search_bar)   # davor kommt in _finish_toolbar Hell/Dunkel
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.toolbar = toolbar
        # Ist das Fenster zu schmal (z. B. Laptop mit Skalierung), schiebt Qt die Suchleiste in den versteckten
        # Überlauf der Werkzeugleiste; ist die Werkzeugleiste ausgeblendet, fehlt sie ganz. Dann erscheint ein
        # Suchfeld rechts in der Menüzeile – so erreicht Strg+K immer eines.
        self.menu_search_bar = SearchBar(self.search_entries, self)
        self.menuBar().setCornerWidget(self.menu_search_bar, Qt.Corner.TopRightCorner)
        self.menu_search_bar.hide()
        toolbar.visibilityChanged.connect(lambda _visible: self._schedule_search_place())
        # Ein-/Ausblenden in den Einstellungen (Werkzeugleiste → Anzeige); über Strg+K ist es auch zu finden
        toggle = toolbar.toggleViewAction()
        toggle.setText(tr("Werkzeugleiste &anzeigen"))
        toggle.setStatusTip(tr("Die Leiste mit den Knöpfen oben im Fenster ein- oder ausblenden"))
        self.actions.adopt("toggle_toolbar", toggle, [])

    def _build_palette(self) -> None:
        self.palette = ToolPalette()
        self.palette.element_activated.connect(self.insert_element)
        dock = QDockWidget(tr("Bausteine"), self)
        dock.setObjectName("PaletteDock")
        dock.setWidget(self.palette)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.palette_dock = dock
        # Die Bedienhinweise stehen am Titel „Bausteine“ (eine zweite Überschrift im Feld gibt es nicht mehr)
        dock.setToolTip(self.palette.hints)
        toggle = dock.toggleViewAction()
        toggle.setText(tr("&Bausteine"))   # heißt wie das Feld selbst (früher „Werkzeugpalette“)
        toggle.setStatusTip(tr("Das Feld „Bausteine“ am Rand ein- oder ausblenden"))
        self.actions.adopt("toggle_palette", toggle, ["Ctrl+B"])
        self.view_menu.addAction(toggle)

    def _build_tool_docks(self) -> None:
        """Schreibtischtest und Hinweise als Docks am unteren Rand."""
        self.simulation_panel = SimulationPanel()
        self.simulation_panel.element_focus_requested.connect(self._focus_element)
        self.simulation_dock = self._make_dock(tr("Schreibtischtest"), "SimulationDock", self.simulation_panel)
        self.diagnostics_panel = DiagnosticsPanel()
        self.diagnostics_panel.navigate_requested.connect(self._navigate_to)
        self.diagnostics_panel.issues_changed.connect(self._update_diagnostics_title)
        self.diagnostics_dock = self._make_dock(tr("Hinweise"), "DiagnosticsDock", self.diagnostics_panel)
        self.tabifyDockWidget(self.diagnostics_dock, self.simulation_dock)
        self.diagnostics_dock.raise_()
        for name, dock, text, shortcut in (
                ("toggle_simulation", self.simulation_dock, tr("&Schreibtischtest"), "Ctrl+T"),
                ("toggle_diagnostics", self.diagnostics_dock, tr("&Hinweise"), "Ctrl+Shift+H")):
            toggle = dock.toggleViewAction()
            toggle.setText(text)
            self.actions.adopt(name, toggle, [shortcut])
            self.view_menu.addAction(toggle)
        self.extras_menu.addAction(self.actions["toggle_breakpoint"])
        self.extras_menu.addAction(self.actions["clear_breakpoints"])
        self.extras_menu.addSeparator()

        # Code neben dem Plan (zuschaltbar, links)
        self.code_panel = CodePanel(language=str(self.settings_store.value("view/code_language", "asm")))
        self.code_panel.element_requested.connect(self._show_code_element)
        self.code_panel.language.currentIndexChanged.connect(
            lambda _i: self.settings_store.set_value("view/code_language", self.code_panel.current_language))
        self.code_dock = self._make_dock(tr("Code"), "CodeDock", self.code_panel)
        self.removeDockWidget(self.code_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.code_dock)   # eigene Spalte neben dem Plan
        self.code_dock.show()
        # Aufgabe über der Arbeitsfläche (zuschaltbar, oben)
        self.task_panel = TaskPanel()
        self.task_panel.edit_requested.connect(self.edit_task)
        self.task_dock = self._make_dock(tr("Aufgabe"), "TaskDock", self.task_panel)
        self.task_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.removeDockWidget(self.task_dock)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.task_dock)
        self.task_dock.show()
        for name, dock, text, shortcut, icon_name in (
                ("toggle_task", self.task_dock, tr("A&ufgabe anzeigen"), "Ctrl+Shift+A", "task"),
                ("toggle_code_view", self.code_dock, tr("&Code-Ansicht"), "F12", "code_view")):
            toggle = dock.toggleViewAction()
            toggle.setText(text)
            toggle.setIcon(icons.icon(icon_name))
            toggle.setProperty("icon_name", icon_name)
            self.actions.adopt(name, toggle, [shortcut] if shortcut else [])
            self.view_menu.addAction(toggle)
        self.view_menu.addAction(self.actions["toggle_minimap"])
        self.extras_menu.addAction(self.actions["edit_task"])
        self.extras_menu.addSeparator()
        self.extras_menu.addActions([self.actions["search"], self.actions["settings"]])
        self.code_dock.hide()
        self.task_dock.hide()
        self._finish_toolbar()
        self.simulation_dock.visibilityChanged.connect(self._on_simulation_visibility)
        # visibilityChanged meldet auch, ob der Reiter vorne liegt (tabifizierte Docks)
        self._diagnostics_on_top = False
        self.diagnostics_dock.visibilityChanged.connect(self._on_diagnostics_visibility)
        # Standardmäßig ausgeblendet: die Arbeitsfläche behält den meisten Platz.
        self.simulation_dock.hide()
        self.diagnostics_dock.hide()

    def _build_block_list(self) -> None:
        """Bausteinliste (für Bildschirmleser und Tastatur): rechts in einer eigenen Spalte neben dem Feld „Bausteine“,
        anfangs verborgen."""
        self.block_list_panel = BlockListPanel()
        self.block_list_panel.element_activated.connect(self._show_listed_element)
        self.block_list_panel.back_requested.connect(lambda: self._with_view(lambda v: v.setFocus()))
        dock = QDockWidget(tr("Bausteinliste"), self)
        dock.setObjectName("BlockListDock")
        dock.setWidget(self.block_list_panel)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
                             | Qt.DockWidgetArea.BottomDockWidgetArea)
        dock.setAccessibleName(tr("Bausteinliste"))
        # Eigene Spalte neben dem Feld „Bausteine“: Dessen Einträge (auch Start und Ende) bleiben ganz zu sehen, und
        # die Zeilen der Liste haben Platz. Verborgen nimmt sie der Arbeitsfläche nichts weg.
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.splitDockWidget(self.palette_dock, dock, Qt.Orientation.Horizontal)
        self.block_list_dock = dock
        self._block_list_sized = False
        dock.visibilityChanged.connect(self._on_block_list_visibility)
        toggle = dock.toggleViewAction()
        toggle.setText(tr("Baus&teinliste"))
        toggle.setStatusTip(tr("Alle Bausteine der Seite mit ihren Pfeilen als Liste – auch für Bildschirmleser; "
                               "Enter zeigt den Baustein im Plan"))
        self.actions.adopt("toggle_block_list", toggle, ["Ctrl+Shift+L"])
        # Wer die Liste mit der Tastatur öffnet, ist gleich in ihr
        toggle.triggered.connect(lambda checked: checked and QTimer.singleShot(0, self._focus_block_list))
        self.view_menu.addAction(toggle)
        self._show_checkmarks()   # der neue Schalter zeigt im Menü ein Häkchen wie alle anderen
        dock.hide()

    def _on_block_list_visibility(self, visible: bool) -> None:
        if visible and not self._block_list_sized and not self.block_list_dock.isFloating():
            # beim ersten Zeigen breit genug für „Verzweigung „i >= 3“ → …“ (danach bleibt, was man zieht)
            self._block_list_sized = True
            self.resizeDocks([self.block_list_dock], [BLOCK_LIST_WIDTH], Qt.Orientation.Horizontal)

    def _focus_block_list(self) -> None:
        if self.block_list_dock.isVisible():
            self.block_list_dock.raise_()
            self.block_list_panel.list.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _show_listed_element(self, element_id: str) -> None:
        """Bausteinliste: Enter/Doppelklick wählt den Baustein im Plan aus und holt ihn in die Mitte."""
        view = self.current_view()
        item = view.document.scene.element(element_id) if view is not None and element_id else None
        if item is None:
            return
        scene = view.document.scene
        scene.commit_edit()
        scene.select_items([item])
        view.centerOn(item.scene_rect().center())
        view.setFocus()

    def _sync_block_list_selection(self) -> None:
        """Die Bausteinliste markiert den Baustein, der im Plan ausgewählt ist."""
        if not hasattr(self, "block_list_panel") or not self.block_list_dock.isVisible():
            return
        scene = self.current_scene()
        item = scene.single_selected if scene is not None and self.sender() is scene else None
        if item is not None:
            self.block_list_panel.show_element(item.element_id)

    def connect_selected_to(self, source: FlowItem | None = None, dialog_class=ConnectDialog) -> str | None:
        """„Verbinden mit …“: Pfeil vom ausgewählten Baustein zu einem Baustein aus einer Liste (ohne Maus)."""
        view = self.current_view()
        if view is None:
            return None
        scene = view.document.scene
        scene.commit_edit()
        source = source if source is not None else scene.single_selected
        if not can_start_line(source) or source.scene() is not scene:
            return None
        targets = connect_targets(scene, source)
        if not targets:
            self.statusBar().showMessage(tr("Auf dieser Seite gibt es keinen anderen Baustein, zu dem ein Pfeil "
                                            "führen kann."), 5000)
            return None
        dialog = dialog_class(source, targets, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        target = dialog.target() if accepted else None
        label = dialog.label()
        dialog.deleteLater()
        if target is None or not shiboken6.isValid(source) or source.scene() is not scene \
                or target.scene() is not scene:
            view.setFocus()
            return None
        connection_id = scene.connect_blocks(source, target, label=label)
        conn = scene.connection(connection_id) if connection_id is not None else None
        if conn is not None:
            view.ensureVisible(conn.sceneBoundingRect(), 40, 40)
            if not conn.warning:
                self.statusBar().showMessage(tr("Pfeil von {source} zu {target} angelegt.",
                                                source=block_title(source), target=block_title(target)), 5000)
        view.setFocus()
        return connection_id

    def _make_dock(self, title: str, name: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        return dock

    def _on_simulation_visibility(self, visible: bool) -> None:
        # Nur beenden, wenn das Dock wirklich geschlossen wurde – nicht, wenn nur
        # der Reiter „Hinweise“ nach vorne geholt wurde.
        if not visible and self.simulation_dock.isHidden() and self.simulation_panel.simulator is not None:
            self.simulation_panel.stop(silent=True)

    def _on_diagnostics_visibility(self, visible: bool) -> None:
        self._diagnostics_on_top = visible

    def _update_diagnostics_title(self, warnings: int, infos: int) -> None:
        total = warnings + infos
        self.diagnostics_dock.setWindowTitle(tr("Hinweise ({total})", total=total) if total else tr("Hinweise"))
        if not hasattr(self, "issues_button"):
            return
        if not total:
            self.issues_button.setText(tr("Keine Hinweise"))
            self.issues_button.setIcon(count_icon(0, False))
        else:
            parts = []
            if warnings:
                parts.append(tr("{n} Warnung", n=warnings) if warnings == 1 else tr("{n} Warnungen", n=warnings))
            if infos:
                parts.append(tr("{n} Hinweis", n=infos) if infos == 1 else tr("{n} Hinweise", n=infos))
            self.issues_button.setText(" · ".join(parts))
            self.issues_button.setIcon(count_icon(total, bool(warnings)))

    def _toggle_diagnostics(self) -> None:
        """Hinweise zeigen bzw. nach vorne holen; nur ausblenden, wenn sie schon vorne liegen."""
        dock = self.diagnostics_dock
        if dock.isHidden() or not self._diagnostics_on_top:
            dock.show()
            dock.raise_()
            self.diagnostics_panel.refresh()
        else:
            dock.hide()

    def _focus_element(self, element_id: str) -> None:
        view = self.current_view()
        found = view.document.find_element(element_id) if view is not None else None
        if found is None:
            return
        page, item = found
        view.document.show_page(page)  # z. B. der Schreibtischtest springt in ein Unterprogramm
        view.ensureVisible(item.scene_rect(), 60, 60)

    def _navigate_to(self, element_ids: list, connection_ids: list) -> None:
        view = self.current_view()
        if view is None:
            return
        document = view.document
        # Die Stelle kann auf einer anderen Seite liegen (Unterprogramm)
        found = [document.find_element(eid) for eid in element_ids]
        found += [document.find_connection(cid) for cid in connection_ids]
        found = [entry for entry in found if entry is not None]
        if not found:
            return
        page = found[0][0]
        document.show_page(page)
        scene = page.scene
        items = [item for item_page, item in found if item_page is page]
        scene.select_items(items)
        rect = QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect())
        view.ensureVisible(rect, 80, 80)
        view.setFocus()

    def _build_statusbar(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.count_label = QLabel("")
        self.selection_label = QLabel("")
        self.position_label = QLabel("")
        self.grid_label = QLabel("")
        self.zoom_label = QLabel("")
        self.issues_button = QToolButton()
        self.issues_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.issues_button.setIconSize(COUNT_ICON_SIZE)
        self.issues_button.setAutoRaise(True)
        self.issues_button.clicked.connect(self._toggle_diagnostics)
        # Wird das Projekt automatisch gespeichert – und wohin? Ein Klick öffnet Einstellungen → Allgemein → Speichern
        self.save_state_button = QToolButton()
        self.save_state_button.setObjectName("SaveStateButton")
        self.save_state_button.setAutoRaise(True)
        self.save_state_button.setIconSize(SAVE_STATE_ICON_SIZE)
        self.save_state_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.save_state_button.clicked.connect(lambda: self.show_settings(focus="auto_save"))
        status.addPermanentWidget(self.save_state_button)
        status.addPermanentWidget(self.issues_button)
        for label in (self.count_label, self.selection_label, self.position_label, self.grid_label,
                      self.zoom_label):
            status.addPermanentWidget(label)
        self.position_label.hide()   # erscheint mit der ersten Mausbewegung über dem Plan
        self._update_diagnostics_title(0, 0)

    def _connect_actions(self) -> None:
        a = self.actions
        a["new"].triggered.connect(self.new_document)
        a["open"].triggered.connect(self.open_file_dialog)
        a["save"].triggered.connect(lambda: self._with_document(self.save_document))
        a["save_as"].triggered.connect(lambda: self._with_document(self.save_document_as))
        a["save_all"].triggered.connect(self.save_all)
        a["edit_task_file"].triggered.connect(self.edit_task_file_dialog)
        a["export_png"].triggered.connect(lambda: self.export_diagram("PNG"))
        a["export_jpg"].triggered.connect(lambda: self.export_diagram("JPG"))
        a["export_svg"].triggered.connect(lambda: self.export_diagram("SVG"))
        a["export_pdf"].triggered.connect(lambda: self.export_diagram("PDF"))
        a["print"].triggered.connect(self.print_diagram)
        a["print_preview"].triggered.connect(self.print_preview)
        a["properties"].triggered.connect(self.edit_properties)
        a["close"].triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))
        a["close_all"].triggered.connect(self.close_all)
        a["quit"].triggered.connect(self.close)

        a["undo"].triggered.connect(self._undo)
        a["redo"].triggered.connect(self._redo)
        self.undo_group.canUndoChanged.connect(lambda _: self._update_actions())
        self.undo_group.canRedoChanged.connect(lambda _: self._update_actions())
        self.undo_group.undoTextChanged.connect(lambda _: self._update_undo_texts())
        self.undo_group.redoTextChanged.connect(lambda _: self._update_undo_texts())
        a["cut"].triggered.connect(self.cut)
        a["copy"].triggered.connect(self.copy)
        a["copy_image"].triggered.connect(self.copy_image)
        a["paste"].triggered.connect(lambda: self.paste())
        a["duplicate"].triggered.connect(self.duplicate)
        a["delete"].triggered.connect(lambda: self._with_scene(lambda s: s.delete_selection()))
        a["select_all"].triggered.connect(lambda: self._with_scene(lambda s: s.select_all()))
        a["deselect"].triggered.connect(self._on_escape)
        a["edit_text"].triggered.connect(self.edit_selected_text)
        a["connect_to"].triggered.connect(lambda: self.connect_selected_to())

        a["zoom_in"].triggered.connect(lambda: self._with_view(lambda v: v.zoom_in()))
        a["zoom_out"].triggered.connect(lambda: self._with_view(lambda v: v.zoom_out()))
        a["zoom_reset"].triggered.connect(lambda: self._with_view(lambda v: v.zoom_reset()))
        a["zoom_fit"].triggered.connect(lambda: self._with_view(lambda v: v.fit_diagram()))
        a["toggle_grid"].toggled.connect(self._set_grid_visible)
        a["toggle_snap"].toggled.connect(self._set_snap)

        for element_type in INSERTABLE_BLOCKS:
            a[insert_action_name(element_type)].triggered.connect(
                lambda _=False, t=element_type: self.insert_element(t))
        a["insert_loop_head"].triggered.connect(lambda: self.insert_element(ElementType.LOOP, loop_kind="head"))
        a["insert_loop_foot"].triggered.connect(lambda: self.insert_element(ElementType.LOOP, loop_kind="foot"))

        for name in ALIGN_ACTIONS + [alignment.SNAP_TO_GRID]:
            a[name].triggered.connect(lambda _=False, mode=name: self.align(mode))
        a["bring_front"].triggered.connect(lambda: self._with_scene(lambda s: s.bring_to_front()))
        a["send_back"].triggered.connect(lambda: self._with_scene(lambda s: s.send_to_back()))
        a["toggle_loop_part"].triggered.connect(self.toggle_loop_part)
        a["reset_routing"].triggered.connect(self.reset_routing)
        a["add_bend"].triggered.connect(self.add_bend)
        a["jump_to_source"].triggered.connect(lambda: self.jump_along_line(forward=False))
        a["jump_to_target"].triggered.connect(lambda: self.jump_along_line(forward=True))
        a["new_subprogram"].triggered.connect(lambda: self.new_subprogram())
        a["open_subprogram"].triggered.connect(self.open_selected_subprogram)
        a["next_page"].triggered.connect(lambda: self._step_page(1))
        a["previous_page"].triggered.connect(lambda: self._step_page(-1))
        a["go_back"].triggered.connect(lambda: self._go_history(back=True))
        a["go_forward"].triggered.connect(lambda: self._go_history(back=False))
        a["extract_subprogram"].triggered.connect(lambda: self.extract_subprogram())
        for name in ("duplicate_page", "copy_page", "cut_page", "paste_page", "move_page_left", "move_page_right"):
            a[name].triggered.connect(lambda _=False, n=name: self.page_command(n))

        a["generate_code"].triggered.connect(self.show_code_dialog)
        a["edit_task"].triggered.connect(self.edit_task)
        stored = self.settings_store.value("view/minimap", True)   # standardmäßig an
        a["toggle_minimap"].setChecked(str(stored).strip().lower() in ("true", "1"))
        a["toggle_minimap"].toggled.connect(self._set_minimap_visible)
        a["toggle_breakpoint"].triggered.connect(self.toggle_breakpoint)
        a["clear_breakpoints"].triggered.connect(self.clear_breakpoints)
        self.simulation_panel.breakpoint_requested.connect(self.toggle_breakpoint)
        a["structogram"].triggered.connect(self.show_structogram)
        a["auto_layout"].triggered.connect(self.auto_layout)
        a["theme_dark"].triggered.connect(lambda: self.set_theme("dark"))
        a["theme_light"].triggered.connect(lambda: self.set_theme("light"))
        a["toggle_theme"].triggered.connect(self.toggle_theme)

        a["shortcuts"].triggered.connect(lambda: ShortcutsDialog(self, self.actions).exec())
        a["notation_help"].triggered.connect(self.show_notation_help)
        a["register_filetype"].triggered.connect(self.register_file_type)
        a["about"].triggered.connect(lambda: AboutDialog(self).exec())
        a["settings"].triggered.connect(lambda: self.show_settings())
        a["search"].triggered.connect(self.open_search)
        for preference in preferences.PREFERENCES:
            a[preferences.action_name(preference.name)].triggered.connect(
                lambda checked=False, name=preference.name: self._on_preference(name, checked))
        panel = self.simulation_panel
        for name, button in (("simulation_back", panel.back_button), ("simulation_step", panel.step_button),
                             ("simulation_run", panel.run_button), ("simulation_play", panel.play_button)):
            a[name].triggered.connect(lambda _=False, b=button: self._press_simulation_button(b))
        a["check_updates"].triggered.connect(lambda: self.updates.check(manual=True))
        a["check_updates_on_start"].triggered.connect(self._on_check_updates_on_start)
        self._sync_update_actions()
        a["auto_save"].setChecked(self._auto_save_enabled)
        a["auto_save"].triggered.connect(self._on_auto_save_triggered)
        a["backup_on_save"].setChecked(self.settings_store.backup_on_save())
        a["backup_on_save"].triggered.connect(self._on_backup_triggered)
        a["presentation"].triggered.connect(self.set_presentation)
        # Esc liegt nur auf „Auswahl aufheben“ (_on_escape): Ein zweiter Befehl auf derselben Taste wäre für Qt
        # mehrdeutig, und keiner von beiden würde ausgeführt
        # Tastenkürzel wirken auch, wenn die Menüleiste ausgeblendet ist (Präsentationsansicht)
        self.addActions(list(a.all().values()))
        self.actions.apply_custom_shortcuts(self.settings_store.shortcuts())
        self._on_shortcuts_changed()

    # ============================================================ Einstellungen
    def _press_simulation_button(self, button) -> None:
        if not self.simulation_dock.isVisible():
            # F5/F10 öffnen den Schreibtischtest, statt nichts zu tun
            self.simulation_dock.show()
            self.simulation_dock.raise_()
        button.click()

    # ------------------------------------------------------------ Zusatzknöpfe
    def _toolbar_proxy(self, action: QAction) -> QAction:
        """Knopf für die Werkzeugleiste, der ``action`` auslöst – so lässt er sich ausblenden, ohne dass der
        Menüeintrag verschwindet."""
        proxy = QAction(action.icon(), action.text(), self)
        proxy.setProperty("source", action)
        proxy.setCheckable(action.isCheckable())

        def sync() -> None:
            proxy.setIcon(action.icon())
            proxy.setToolTip(action.toolTip())
            proxy.setEnabled(action.isEnabled())
            if action.isCheckable():
                proxy.setChecked(action.isChecked())

        proxy.triggered.connect(lambda _checked=False: (action.trigger(), sync()))
        action.changed.connect(sync)
        sync()
        return proxy

    def _finish_toolbar(self) -> None:
        """Baut die Knöpfe der Werkzeugleiste und „Mehr“ – erst jetzt, weil die Docks nun bestehen.

        Jeder Knopf ist ein Stellvertreter seines Befehls: Blendet man ihn aus, bleibt der Menüeintrag erhalten.
        """
        a, toolbar = self.actions, self.toolbar
        simulation = a["toggle_simulation"]
        simulation.setIcon(icons.icon("play"))
        simulation.setProperty("icon_name", "play")
        self.zoom_button = QToolButton()
        self.zoom_button.setText("100 %")
        self.zoom_button.setMinimumWidth(58)
        self.zoom_button.clicked.connect(lambda: self._with_view(lambda v: v.zoom_reset()))
        P = preferences
        aligns = (alignment.ALIGN_LEFT, alignment.ALIGN_CENTER_X, alignment.ALIGN_RIGHT, alignment.ALIGN_TOP,
                  alignment.ALIGN_CENTER_Y, alignment.ALIGN_BOTTOM, alignment.DISTRIBUTE_H, alignment.DISTRIBUTE_V)
        # Abschnitte (durch Trennstriche getrennt) in der Reihenfolge der Arbeit
        segments = (
            ((P.TOOL_FILE, ("new", "open", "save")),),
            ((P.TOOL_UNDO, ("undo", "redo")), (P.TOOL_CLIPBOARD, ("cut", "copy", "paste")),
             (P.TOOL_DELETE, ("delete",))),
            ((P.TOOL_ZOOM, ("zoom_out", self.zoom_button, "zoom_in", "zoom_fit")),
             (P.TOOL_GRID, ("toggle_grid", "toggle_snap"))),
            ((P.TOOL_ALIGN, aligns),),
            ((P.TOOL_LAYOUT, ("auto_layout",)), (P.TOOL_SIMULATION, ("toggle_simulation",)),
             (P.TOOL_GENERATE_CODE, ("generate_code",)), (P.TOOL_STRUCTOGRAM, ("structogram",))),
            ((P.TOOL_CODE_VIEW, ("toggle_code_view",)), (P.TOOL_MINIMAP, ("toggle_minimap",)),
             (P.TOOL_BREAKPOINTS, ("toggle_breakpoint",)), (P.TOOL_TEACHER, ("edit_task",))),
            ((P.TOOL_PRINT, ("print",)),),   # PDF: Datei → Exportieren (Strg+E)
        )
        end = self._toolbar_end
        for segment in segments:
            separator = toolbar.insertSeparator(end)
            for key, items in segment:
                entries = []
                for item in items:
                    if isinstance(item, QWidget):
                        entries.append(toolbar.insertWidget(end, item))
                    else:
                        entries.append(self._toolbar_proxy(a[item]))
                        toolbar.insertAction(end, entries[-1])
                self._toolbar_groups[key] = entries
            self._toolbar_segments.append((separator, [key for key, _items in segment]))
        self._more_separator = toolbar.insertSeparator(end)
        # „Mehr“: alle Zusatzfunktionen mit einem Klick – auch wenn die Einstellungen zurückgesetzt wurden
        menu = QMenu(tr("Mehr"), self)
        for name in ("generate_code", "toggle_code_view", "toggle_minimap", None, "toggle_task", "edit_task", None,
                     "toggle_breakpoint", "clear_breakpoints", None, "toggle_grid", "toggle_snap"):
            menu.addSeparator() if name is None else menu.addAction(a[name])
        align_menu = menu.addMenu(tr("Ausrichten"))
        for name in ALIGN_ACTIONS + [alignment.SNAP_TO_GRID]:
            align_menu.addAction(a[name])
        menu.addSeparator()
        menu.addAction(a["copy_image"])
        menu.addAction(a["presentation"])
        menu.addSeparator()
        menu.addAction(a["settings"])
        self.more_menu = menu
        self.more_button = QToolButton()
        self.more_button.setText(tr("Mehr"))
        self.more_button.setToolTip(tr("Weitere Funktionen: Code-Ansicht, Minikarte, Aufgabe, Haltepunkte, Raster, "
                                       "Ausrichten …"))
        self.more_button.setMenu(menu)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.insertWidget(end, self.more_button)
        # Hell/Dunkel mit einem Klick (immer sichtbar), rechts direkt vor der Suchleiste; das Symbol zeigt das
        # eingestellte Farbschema
        toolbar.insertAction(self._search_action, a["toggle_theme"])
        self.theme_button = toolbar.widgetForAction(a["toggle_theme"])
        self._show_checkmarks()

    def _show_checkmarks(self) -> None:
        """Schalter zeigen in allen Menüs ein Häkchen, wenn sie an sind.

        Hat ein Menüeintrag ein Symbol, zeichnet Qt statt des Häkchens nur einen kaum sichtbaren Rahmen um das Symbol.
        Deshalb erscheinen Schalter in Menüs ohne Symbol (in der Werkzeugleiste behalten sie es).
        """
        for menu in [self.menuBar(), *self.findChildren(QMenu)]:
            for action in menu.actions():
                if action.isCheckable():
                    action.setIconVisibleInMenu(False)

    def _apply_tools(self) -> None:
        """Zeigt die in den Einstellungen gewählten Knöpfe der Werkzeugleiste (im Menü und unter „Mehr“ stehen sie
        immer). Trennstriche erscheinen nur zwischen Abschnitten, die etwas zeigen."""
        for key, entries in self._toolbar_groups.items():
            for entry in entries:
                entry.setVisible(preferences.enabled(key))
        shown_before = False
        for separator, keys in self._toolbar_segments:
            shown = any(preferences.enabled(key) for key in keys)
            separator.setVisible(shown and shown_before)
            shown_before = shown_before or shown
        self._more_separator.setVisible(shown_before)

    def _set_minimap_visible(self, visible: bool, store: bool = True) -> None:
        if store:
            self.settings_store.set_value("view/minimap", bool(visible))
        for view in self.views():
            view.minimap.setVisible(bool(visible))

    # ------------------------------------------------------------ Code-Ansicht
    def _show_code_element(self, element_id: str) -> None:
        """Klick auf eine Codezeile: Baustein auswählen und zeigen (der Fokus bleibt in der Code-Ansicht)."""
        view = self.current_view()
        found = view.document.find_element(element_id) if view is not None else None
        if found is None:
            return
        page, item = found
        view.document.show_page(page)
        page.scene.select_items([item])
        self.code_panel.show_selection([element_id])   # sofort, nicht erst mit der (verzögerten) Auswahlmeldung
        view.ensureVisible(item.scene_rect(), 80, 80)

    def _sync_breakpoint_action(self) -> None:
        """Häkchen bei „Haltepunkt setzen/entfernen“: haben alle ausgewählten Bausteine einen Haltepunkt?"""
        document = self.current_document()
        ids = [item.element_id for item in document.scene.selected_elements() if not item.is_comment]             if document is not None else []
        action = self.actions["toggle_breakpoint"]
        action.blockSignals(True)
        action.setChecked(bool(ids) and all(breakpoints.has_breakpoint(document, eid) for eid in ids))
        action.blockSignals(False)

    def _sync_code_selection(self) -> None:
        document = self.current_document()
        if document is None or not self.code_dock.isVisible():
            return
        self.code_panel.show_selection([item.element_id for item in document.scene.selected_elements()])

    # ------------------------------------------------------------ Haltepunkte
    def _refresh_breakpoints(self, document) -> None:
        if getattr(document, "breakpoints", None):
            breakpoints.refresh_markers(document)

    def toggle_breakpoint(self) -> None:
        document = self.current_document()
        if document is None:
            return
        items = [item for item in document.scene.selected_elements() if not item.is_comment]
        if not items:
            self._sync_breakpoint_action()
            self.statusBar().showMessage(tr("Bitte zuerst einen Baustein auswählen."), 4000)
            return
        switched_on = breakpoints.toggle(document, [item.element_id for item in items])
        self._sync_breakpoint_action()
        if switched_on:
            self.statusBar().showMessage(tr("Haltepunkt gesetzt – der Schreibtischtest hält vor diesem Baustein an."),
                                         5000)
        else:
            self.statusBar().showMessage(tr("Haltepunkt entfernt."), 4000)

    def clear_breakpoints(self) -> None:
        document = self.current_document()
        if document is not None:
            breakpoints.clear(document)
            self.statusBar().showMessage(tr("Alle Haltepunkte entfernt."), 4000)

    # ------------------------------------------------------------ Aufgabe (Lehrermodus)
    def edit_task(self) -> None:
        from app import task as T

        document = self.current_document()
        if document is None:
            return
        current = T.task_of(document.meta)
        password, solution = "", ""
        if current.locked or current.has_solution:
            entered = ask_password(self, tr("Aufgabe stellen"), tr("Passwort der Lehrkraft:"))
            if entered is None:
                return
            try:
                if current.locked and not T.check_lock(current.lock, entered):
                    raise T.WrongPassword()
                if current.has_solution:
                    solution = T.decrypt(current.solution, entered)
            except T.WrongPassword:
                QMessageBox.warning(self, tr("Aufgabe stellen"), tr("Das Passwort ist falsch."))
                return
            password = entered
        dialog = TaskDialog(current, solution, self)
        dialog.set_previous_password(password)
        try:
            if dialog.exec() != TaskDialog.DialogCode.Accepted:
                # nur angesehen (z. B. die Musterlösung): Am Projekt und an seiner Datei ändert sich nichts
                return
            task = dialog.result_task()
        finally:
            dialog.deleteLater()
        new_meta = document.meta.copy()
        T.apply_task(new_meta, task)
        if task.present or task.locked:
            # Wer die Aufgabe eben gestellt hat, ist die Lehrkraft: Das Projekt ist jetzt eine Aufgabe, keine
            # Schülerlösung mehr. Gespeichert wird in die eigene Datei; eine Kopie fragt nach dem Namen.
            new_meta.task_copy = ""
            document.task_unlocked = True
        grid = document.settings.grid_size
        document.undo_stack.push(ProjectPropertiesCommand(document, document.meta, new_meta, grid, grid))
        self.task_panel.refresh()
        self._update_save_state()
        if not document.file_path and document.task_source and not new_meta.task_copy:
            self.statusBar().showMessage(tr("Aufgabe geändert – beim Speichern wählen Sie den Dateinamen. Die "
                                            "Aufgabe „{name}“ wird nur ersetzt, wenn Sie ihren Namen wählen.",
                                            name=os.path.basename(document.task_source)), 10000)
        if new_meta.task_title or new_meta.task_text:
            self.task_dock.show()
            self.task_dock.raise_()

    def _load_preferences(self) -> None:
        for preference in preferences.PREFERENCES:
            stored = self.settings_store.preference(preference.name)
            if stored is not None:
                preferences.set_enabled(preference.name, stored)

    def _on_preference(self, name: str, enabled: bool) -> None:
        preferences.set_enabled(name, enabled)
        self.settings_store.set_preference(name, enabled)
        if name in preferences.TOOLS:
            self._apply_tools()
            return
        for view in self.views():
            for page in view.document.pages:
                page.scene.preferences_changed()

    def show_notation_help(self) -> None:
        """Hilfe → Schreibweisen im Plan (auch über den Tipp auf der leeren Arbeitsfläche erreichbar)."""
        dialog = NotationDialog(self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()   # sonst bliebe jedes geöffnete Fenster samt Tabelle im Speicher

    def show_settings(self, show_shortcuts: bool = False, focus: str | None = None) -> None:
        """Einstellungen öffnen; ``focus``: dieser Schalter bekommt gleich den Fokus (z. B. „auto_save“)."""
        dialog = settings_dialog.SettingsDialog(self.actions, self, show_shortcuts, options=self.settings_options())
        dialog.shortcuts_changed.connect(self._on_shortcuts_changed)
        switch = dialog.switches.get(focus) if focus else None
        if switch is not None:
            QTimer.singleShot(0, switch, switch.setFocus)   # erst, wenn das Fenster zu sehen ist
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()   # sonst bliebe jedes geöffnete Fenster unsichtbar bestehen (und folgte dem Farbschema)

    def settings_options(self) -> dict:
        """Felder des Einstellungsfensters, die zum Fenster gehören (die Schalter kommen aus der Befehlsliste)."""
        S, a = settings_dialog, self.actions
        options = {
            S.THEME: S.Choice(
                S.THEME, tr("Farbschema"), tr("Farben der Bedienoberfläche; „Hell“ eignet sich z. B. für den Beamer"),
                [("dark", clean_text(a["theme_dark"].text())), ("light", clean_text(a["theme_light"].text()))],
                self.current_theme_name, self.set_theme, self.theme_changed),
            # zweisprachig, damit man es auch in einer fremden Sprache findet
            S.LANGUAGE: S.Choice(
                S.LANGUAGE, language_label(), tr("Die Sprache wird nach einem Neustart des Programms geändert."),
                [(i18n.AUTOMATIC, tr("Automatisch (Systemsprache)"))]
                + [(code, i18n.language_name(code)) for code in i18n.available_languages()],
                self.settings_store.language, self._on_language_chosen),
            S.TOOLBAR: S.Toggle(S.TOOLBAR, clean_text(a["toggle_toolbar"].text()), a["toggle_toolbar"].statusTip(),
                                a["toggle_toolbar"], default=True),
        }
        if file_association.is_supported():
            options[S.REGISTER_FILETYPE] = S.Button(
                S.REGISTER_FILETYPE, a["register_filetype"].text(),
                tr("Projektdateien ({ext}) mit einem Doppelklick in diesem Programm öffnen", ext=config.FILE_EXTENSION),
                a["register_filetype"].trigger)
        return options

    def _on_shortcuts_changed(self) -> None:
        self.settings_store.set_shortcuts(self.actions.custom_shortcuts())
        hints = {}
        for element_type in INSERTABLE_BLOCKS:
            keys = self.actions[insert_action_name(element_type)].shortcuts()
            hints[element_type] = sequence_text(keys[0]) if keys else ""
        self.palette.set_key_hints(hints)
        panel = self.simulation_panel
        for name, button in (("simulation_back", panel.back_button), ("simulation_step", panel.step_button),
                             ("simulation_run", panel.run_button), ("simulation_play", panel.play_button)):
            button.setToolTip(self.actions[name].toolTip())
        self.zoom_button.setToolTip(self.actions["zoom_reset"].toolTip())
        keys = self.actions["toggle_diagnostics"].shortcuts()
        tip = tr("Hinweisliste ein-/ausblenden")
        self.issues_button.setToolTip(f"{tip} ({sequence_text(keys[0])})" if keys else tip)
        keys = self.actions["new_subprogram"].shortcuts()
        tip = tr("Neues Unterprogramm auf einer eigenen Seite anlegen")
        self.page_bar.add_button.setToolTip(f"{tip} ({sequence_text(keys[0])})" if keys else tip)
        search_keys = self.actions["search"].shortcuts()
        for bar in (self.search_bar, self.menu_search_bar):
            bar.setPlaceholderText(
                tr("Suchen … ({key})", key=sequence_text(search_keys[0])) if search_keys else tr("Suchen …"))

    # ------------------------------------------------------------ Suche
    def active_search_bar(self) -> SearchBar:
        """Das sichtbare Suchfeld: in der Werkzeugleiste oder – wenn es dort keinen Platz hat – in der Menüzeile."""
        return self.search_bar if self.search_bar.isVisible() else self.menu_search_bar

    def open_search(self) -> None:
        self._place_search()
        self.active_search_bar().open()

    def _schedule_search_place(self) -> None:
        QTimer.singleShot(0, self, self._place_search)  # mit Kontext: entfällt, wenn das Fenster schon weg ist

    def _place_search(self) -> None:
        if not self.isVisible():
            return
        in_toolbar = self.toolbar.isVisible() and self.search_bar.isVisible()
        if self.menu_search_bar.isHidden() != in_toolbar:
            self.menu_search_bar.setVisible(not in_toolbar)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_search_place()
        self._update_save_state()   # schmales Fenster: die Speicher-Anzeige nur als Symbol

    def search_entries(self) -> list:
        """Alles, was die Suchleiste finden kann: Funktionen, Einstellungen und Bausteine aller Seiten."""
        entries = []
        for name, action in self.actions.all().items():
            if not action.isEnabled():
                continue
            title = clean_text(action.text())
            keys = action.shortcuts()
            detail = sequence_text(keys[0]) if keys else ""
            if action.isCheckable():
                state = tr("ein") if action.isChecked() else tr("aus")
                detail = f"{state}  {detail}".strip()
            entries.append(SearchEntry(title, detail, action.trigger, action.statusTip()))
        document = self.current_document()
        if document is not None:
            for index, page in enumerate(document.pages):
                for item in page.scene.elements():
                    text = " ".join(item.data.text.split())
                    if text:
                        detail = f"{display_name_for(item.element_type)} · {page.display_name}"
                        entries.append(SearchEntry(text, detail, lambda p=index, i=item.element_id: self._go_to(p, i)))
        # die Sprache ist kein Befehl, soll aber über Strg+K zu finden sein (auch auf Englisch)
        entries.append(SearchEntry(language_label(), tr("Einstellungen"), self.show_settings,
                                   "Sprache Language " + tr("Automatisch (Systemsprache)")))
        return entries

    def _go_to(self, page: int, element_id: str) -> None:
        self.show_page(page)
        self._reveal([element_id])

    # ============================================================ Zugriff
    def current_view(self) -> DiagramView | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, DiagramView) else None

    def current_document(self) -> DiagramDocument | None:
        view = self.current_view()
        return view.document if view is not None else None

    def current_scene(self):
        document = self.current_document()
        return document.scene if document is not None else None

    def views(self) -> list[DiagramView]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())
                if isinstance(self.tabs.widget(i), DiagramView)]

    def _with_view(self, fn) -> None:
        view = self.current_view()
        if view is not None:
            fn(view)

    def _with_scene(self, fn) -> None:
        scene = self.current_scene()
        if scene is not None:
            fn(scene)

    def _with_document(self, fn) -> None:
        document = self.current_document()
        if document is not None:
            fn(document)

    # ============================================================ Tabs
    def add_document(self, document: DiagramDocument) -> DiagramView:
        view = DiagramView(document)
        view.minimap = Minimap(view)
        view.minimap.setVisible(self.actions["toggle_minimap"].isChecked())
        document.content_changed.connect(lambda d=document: self._refresh_breakpoints(d))
        index = self.tabs.addTab(view, document.display_name)
        close_button = QToolButton()
        close_button.setObjectName("TabCloseButton")
        close_button.setIcon(icons.icon("close"))
        close_button.setIconSize(QSize(12, 12))
        close_button.setAutoRaise(True)
        close_button.setToolTip(tr("Projekt schließen"))
        close_button.clicked.connect(lambda _=False, v=view: self.close_tab(self.tabs.indexOf(v)))
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close_button)
        self.undo_group.addStack(document.undo_stack)
        if self.autosave is not None:
            self.autosave.register(document)
        document.title_changed.connect(lambda d=document: self._update_document_title(d))
        document.modified_changed.connect(lambda _m, d=document: self._update_document_title(d))
        document.undo_stack.indexChanged.connect(lambda _i, d=document: self._schedule_auto_save(d))
        document.settings_changed.connect(self._update_status)
        document.settings_changed.connect(self._sync_grid_actions)   # nach Rückgängig
        for page in document.pages:
            self._connect_scene(page.scene)
        document.page_added.connect(lambda page: self._connect_scene(page.scene))
        document.current_page_changed.connect(lambda _i, d=document: self._on_page_changed(d))
        view.zoom_changed.connect(lambda _z: self._update_status())
        view.cursor_scene_pos_changed.connect(self._update_position)
        view.context_menu_requested.connect(self.show_context_menu)
        self.tabs.setCurrentIndex(index)
        self._update_document_title(document)
        self._update_ui()
        if document.meta.task_title or document.meta.task_text:
            self.task_dock.show()   # Wer eine Aufgabe öffnet, soll sie gleich sehen
            self.task_dock.raise_()
        view.setFocus()
        return view

    def _connect_scene(self, scene) -> None:
        """Signale einer Seite (Szene) mit dem Fenster verbinden – auch für später angelegte Unterprogramme."""
        if scene.property("bst_connected"):
            return
        scene.setProperty("bst_connected", True)
        scene.selection_state_changed.connect(self._update_actions)
        scene.selection_state_changed.connect(self._update_status)
        scene.selection_state_changed.connect(self._sync_code_selection)
        scene.selection_state_changed.connect(self._sync_breakpoint_action)
        scene.selection_state_changed.connect(self._sync_block_list_selection)
        scene.content_changed.connect(self._schedule_status_update)
        scene.editing_changed.connect(lambda _e: self._update_actions())
        scene.status_message.connect(self._show_scene_message)
        scene.subprogram_requested.connect(self._request_subprogram)
        scene.theme = styles.current_theme()

    def _on_tab_changed(self, index: int) -> None:
        document = self.current_document()
        self.undo_group.setActiveStack(document.undo_stack if document is not None else None)
        self._update_ui()

    def _on_page_changed(self, document: DiagramDocument) -> None:
        if document is self.current_document():
            self._update_actions()
            self._update_status()
            self.page_bar.refresh()

    def _sync_panels(self) -> None:
        document = self.current_document()
        if hasattr(self, "simulation_panel"):
            self.simulation_panel.set_document(document)
            self.diagnostics_panel.set_document(document)
            self.code_panel.set_document(document)
            self.task_panel.set_document(document)
        if hasattr(self, "block_list_panel"):
            self.block_list_panel.set_document(document)
        self.page_bar.set_document(document)

    def _update_document_title(self, document: DiagramDocument) -> None:
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, DiagramView) and view.document is document:
                title = document.display_name + (" *" if document.is_modified else "")
                self.tabs.setTabText(i, title)
                self.tabs.setTabToolTip(i, document.file_path or tr("Noch nicht gespeichert"))
        self._update_window_title()

    def _update_window_title(self) -> None:
        self._update_save_state()
        document = self.current_document()
        if document is None:
            self.setWindowTitle(config.APP_NAME)
            self.setWindowModified(False)
            return
        self.setWindowTitle(f"{document.display_name}[*] – {config.APP_NAME}")
        self.setWindowModified(document.is_modified)

    def save_state(self, document: DiagramDocument | None) -> tuple[str, str, str]:
        """Wie das Projekt gespeichert wird: (Zustand, kurzer Text, Kurzinfo) für die Anzeige in der Statusleiste.

        Zustand: ``"auto"`` (speichert automatisch), ``"off"`` (ausgeschaltet), ``"paused"`` (diese Datei nicht
        automatisch), ``"untitled"`` (noch ohne Dateinamen) oder ``""`` (kein Projekt offen).
        """
        if document is None:
            return "", "", ""
        keys = self.actions["save"].shortcuts()
        key = sequence_text(keys[0]) if keys else tr("Speichern")
        click = tr("Klicken öffnet die Einstellungen (Allgemein → Speichern).")
        path = document.file_path
        if not path:
            tip = tr("Dieses Projekt hat noch keinen Dateinamen. Automatisch gespeichert wird erst, wenn Sie es "
                     "einmal selbst gespeichert haben ({key}).", key=key)
            if document.task_source:
                tip = "\n".join((tr("Kopie der Aufgabe „{name}“ – die Aufgabendatei bleibt unverändert.",
                                     name=os.path.basename(document.task_source)), tip))
            return "untitled", tr("Nicht gespeichert"), "\n\n".join((tip, click))
        if not self._auto_save_enabled:
            tip = tr("Automatisches Speichern ist ausgeschaltet – gespeichert wird nur mit {key}:", key=key)
            return "off", tr("Auto-Speichern aus"), "\n".join((tip, path, "", click))
        reason = ""
        if not document.native_file:
            reason = tr("Die Datei stammt aus einem anderen Programm – speichern Sie sie einmal selbst ({key}).",
                        key=key)
        elif getattr(document, "restored_from_backup", False):
            reason = tr("Aus einer Sicherung wiederhergestellt – speichern Sie einmal selbst ({key}).", key=key)
        elif self._is_task_original(document):
            reason = tr("Aufgabe der Lehrkraft – sie wird nie automatisch überschrieben.")
        elif not _has_project_extension(path):
            reason = tr("Automatisch gespeichert werden nur {ext}-Dateien.", ext=config.FILE_EXTENSION)
        elif (document.disk_stamp is not None and not os.path.exists(path)) or document.changed_on_disk():
            reason = tr("Die Datei wurde außerhalb des Programms geändert, verschoben oder gelöscht – speichern Sie "
                        "selbst ({key}).", key=key)
        elif document.auto_save_failed:
            reason = tr("Das letzte automatische Speichern ist fehlgeschlagen (z. B. keine Schreibrechte) – "
                        "speichern Sie selbst ({key}).", key=key)
        if reason:
            return "paused", tr("Auto-Speichern pausiert"), "\n".join((reason, path, "", click))
        tip = tr("Jede Änderung wird kurz danach automatisch gespeichert:")
        return "auto", tr("Auto-Speichern an"), "\n".join((tip, path, "", click))

    def _update_save_state(self) -> None:
        """Anzeige in der Statusleiste: nach Reiterwechsel, Speichern, Änderung und Umschalten der Einstellung.

        Ein farbiger Punkt am Symbol zeigt den Zustand; in einem schmalen Fenster steht nur das Symbol da (der Text
        bleibt Kurzinfo und Name für Bildschirmleser), damit Meldungen in der Statusleiste Platz behalten."""
        button = getattr(self, "save_state_button", None)
        if button is None:
            return
        state, text, tip = self.save_state(self.current_document())
        button.setVisible(bool(state))
        compact = self.width() < SAVE_STATE_COMPACT_WIDTH
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if compact
                                  else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        if state and button.property("save_state_icon") != f"{state}/{styles.current_theme().name}":
            button.setIcon(save_state_icon(state))
            button.setProperty("save_state_icon", f"{state}/{styles.current_theme().name}")
        button.setText(text)
        button.setToolTip("\n\n".join((text, tip)) if compact else tip)
        button.setAccessibleName(text)
        button.setAccessibleDescription(tip)
        button.setProperty("save_state", state)

    def close_tab(self, index: int, ask: bool = True) -> bool:
        """Schließt einen Reiter; ``ask=False``: ohne Nachfrage (die Frage ist schon beantwortet, z. B. bei
        „Alle schließen“)."""
        if index < 0 or index >= self.tabs.count():
            return False
        view = self.tabs.widget(index)
        if not isinstance(view, DiagramView):
            return False
        self.tabs.setCurrentIndex(index)
        if ask and not self.maybe_save(view.document):
            return False
        document = view.document
        document.scene.cancel_edit()
        if self.simulation_panel.simulator is not None and self.current_document() is document:
            self.simulation_panel.stop(silent=True)
        self.simulation_panel.set_document(None)
        self.diagnostics_panel.set_document(None)
        self.page_bar.set_document(None)
        if self.autosave is not None:
            self.autosave.unregister(document)
        self._auto_save_pending.discard(document)
        self.undo_group.removeStack(document.undo_stack)
        self.tabs.removeTab(index)
        if getattr(view, "minimap", None) is not None:
            view.minimap.release()   # sonst halten Minikarte und Szene das geschlossene Projekt im Speicher
            view.minimap = None
        document.view_state_provider = None   # gebundene Methode der Ansicht: hielte Ansicht und Projekt fest
        # Die Szenen gehören keinem Qt-Elternobjekt: ausdrücklich leeren und abbauen, sonst bleiben sie samt
        # aller Bausteine im Speicher
        document.undo_stack.clear()
        for page in document.pages:
            connections = page.scene.connections()
            page.scene.clear_diagram()
            for conn in connections:
                conn.label.connection = None   # Pfeil ↔ Beschriftung hielten sich sonst gegenseitig fest
            page.scene.deleteLater()
        view.deleteLater()
        document.deleteLater()
        self._update_ui()
        return True

    def _find_document_by_path(self, path: str) -> int:
        target = _path_key(path)
        for i, view in enumerate(self.views()):
            other = view.document.file_path
            if not other:
                continue
            if _path_key(other) == target:
                return i
            try:
                # dieselbe Datei auf anderem Weg: 8.3-Kurzname, Netzlaufwerk, subst, Verknüpfung
                if os.path.exists(path) and os.path.exists(other) and os.path.samefile(path, other):
                    return i
            except OSError:
                pass
        return -1

    # ============================================================ Datei
    def new_document(self) -> None:
        document = DiagramDocument()
        # wie „Default author“ im PapDesigner: der zuletzt eingetragene Autor gilt auch für neue Projekte
        document.meta.author = self.settings_store.default_author()
        if preferences.enabled(preferences.START_END):
            document.add_start_end()
        self.add_document(document)

    def open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Projekt öffnen"), self.settings_store.last_directory(),
                                              config.open_dialog_filter())
        if path:
            self.open_file(path)

    def open_file(self, path: str, task_original: bool = False) -> bool:
        """Öffnet eine Projektdatei in einem eigenen Reiter.

        Eine Aufgabe der Lehrkraft öffnet sich immer als unbenannte Kopie: „Speichern“ fragt nach einem neuen
        Namen, die Aufgabendatei bleibt unverändert. ``task_original``: die Aufgabendatei selbst (Datei → Aufgabe
        bearbeiten, das Passwort ist schon geprüft).
        """
        path = os.path.abspath(path)
        backup = path.lower().endswith(config.BACKUP_EXTENSION)
        if not _has_project_extension(path) and not backup:
            # .pap ist das einzige Projektformat – auf jedem Weg (Dialog, Befehlszeile, Zuletzt geöffnet)
            self._error(tr("Datei kann nicht geöffnet werden"),
                        tr("„{name}“ ist kein Programmablaufplan im Format {ext}.\n\n"
                           "Es können nur {ext}-Dateien geöffnet werden.",
                           name=os.path.basename(path), ext=config.FILE_EXTENSION))
            return False
        existing = self._find_document_by_path(path)
        if existing >= 0:
            self.tabs.setCurrentIndex(existing)
            if task_original:
                self.views()[existing].document.task_unlocked = True
            return True
        copy = -1 if task_original else self._find_task_copy(path)
        if copy >= 0:
            # dieselbe Aufgabe noch einmal: zur schon offenen, noch nicht gespeicherten Kopie
            self.tabs.setCurrentIndex(copy)
            self.statusBar().showMessage(tr("Diese Aufgabe ist schon als Kopie geöffnet."), 5000)
            return True
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                document = DiagramDocument.open_file(path)
                if backup:
                    # eine Sicherungskopie wird nicht überschrieben: „Speichern“ fragt nach dem Ort
                    document.file_path = None
                elif task_original:
                    document.task_unlocked = True
                elif self._is_task_file(document.meta):
                    self._make_task_copy(document, path)
            finally:
                QApplication.restoreOverrideCursor()
        except ProjectFileError as exc:
            log.warning("Datei konnte nicht geöffnet werden: %s (%s)", path, exc.details)
            if not os.path.exists(path):
                self.settings_store.remove_recent_file(path)
                self._refresh_recent_menu()
            self._error(tr("Datei kann nicht geöffnet werden"), exc.message)
            return False
        except Exception as exc:  # pragma: no cover - Absicherung
            log.exception("Unerwarteter Fehler beim Öffnen von %s", path)
            self._error(tr("Datei kann nicht geöffnet werden"),
                        tr("Die Datei ist beschädigt oder inkompatibel.\n\n({error})", error=type(exc).__name__))
            return False

        # Ein unberührtes, leeres neues Projekt wird ersetzt
        replace_index = self.tabs.currentIndex() if self._replaceable(self.current_document()) else -1
        view = self.add_document(document)
        if replace_index >= 0:
            self.close_tab(replace_index)
            self.tabs.setCurrentIndex(self.tabs.indexOf(view))
        if not backup:
            self.settings_store.add_recent_file(path)
        self.settings_store.set_last_directory(path)
        self._refresh_recent_menu()
        if document.load_warnings:
            shown = document.load_warnings[:10]
            more = len(document.load_warnings) - len(shown)
            text = "\n".join(f"• {w}" for w in shown)
            if more > 0:
                text += "\n" + tr("… und {more} weitere Hinweise.", more=more)
            QMessageBox.information(self, tr("Datei wurde mit Korrekturen geöffnet"),
                                    tr("Die Datei enthielt fehlerhafte Angaben, die automatisch korrigiert "
                                       "wurden:\n\n{text}", text=text))
        if backup:
            self.statusBar().showMessage(tr("Sicherungskopie geöffnet – „Speichern“ legt eine neue Datei an."), 6000)
        elif document.task_source:
            keys = self.actions["save"].shortcuts()
            self.statusBar().showMessage(tr("Aufgabe „{name}“ als Kopie geöffnet – {key} speichert Ihre Lösung als "
                                            "eigene Datei, die Aufgabe bleibt unverändert.",
                                            name=display_name_for_path(path),
                                            key=sequence_text(keys[0]) if keys else "Strg+S"), 8000)
        elif task_original:
            self.statusBar().showMessage(tr("Aufgabe „{name}“ zum Bearbeiten geöffnet – „Speichern“ ändert die "
                                            "Aufgabendatei.", name=document.display_name), 8000)
        elif document.native_file:
            self.statusBar().showMessage(tr("„{name}“ geöffnet.", name=document.display_name), 4000)
        else:
            # Datei ohne gespeicherte Anordnung (z. B. aus dem PapDesigner)
            view.fit_diagram()
            self.statusBar().showMessage(tr("„{name}“ geöffnet – die Anordnung wurde aus "
                                            "dem Raster der Datei übernommen.", name=document.display_name), 8000)
        return True

    def open_example(self, path: str) -> bool:
        """Öffnet ein Lernbeispiel als unbenannte Kopie: „Speichern“ fragt nach dem Ort."""
        try:
            document = DiagramDocument.open_file(path)
        except ProjectFileError as exc:
            log.warning("Lernbeispiel nicht lesbar: %s (%s)", path, exc.details)
            self._error(tr("Datei kann nicht geöffnet werden"), exc.message)
            return False
        document.file_path = None
        for page in document.pages[1:]:
            page.fit_on_show = True
        replace = self._replaceable(self.current_document())
        replace_index = self.tabs.currentIndex()
        view = self.add_document(document)
        if replace:
            self.close_tab(replace_index)
            self.tabs.setCurrentIndex(self.tabs.indexOf(view))
        view.fit_diagram()
        keys = self.actions["toggle_simulation"].shortcuts()
        self.statusBar().showMessage(tr("Lernbeispiel „{name}“ geöffnet – {key} öffnet den Schreibtischtest.",
                                        name=document.display_name,
                                        key=sequence_text(keys[0]) if keys else "F5"), 6000)
        return True

    def open_external_files(self, paths: list[str]) -> None:
        """Öffnet Dateien, die ein weiterer Programmstart (z. B. Doppelklick im Explorer) hierher übergeben hat.

        Jede Datei wird als eigener Reiter geöffnet – wie beim Öffnen im Programm selbst; schon geöffnete Dateien
        werden nur in den Vordergrund geholt. Danach kommt das Fenster nach vorn.
        """
        for path in paths:
            self.open_file(path)
        single_instance.bring_to_front(self)

    def save_document(self, document: DiagramDocument) -> bool:
        # Gespeichert wird ausschließlich als .pap-Datei
        if not document.file_path or not _has_project_extension(document.file_path):
            return self.save_document_as(document)
        if self._is_task_original(document):
            return self._save_task_copy(document)
        if not document.native_file:
            # Die Datei stammt aus einem anderen Programm: nicht stillschweigend ersetzen
            choice = self._ask_foreign_overwrite(document)
            if choice == "save_as":
                return self.save_document_as(document)
            if choice != "overwrite":
                return False
        if document.changed_on_disk():
            choice = self._ask_disk_conflict(document)
            if choice == "save_as":
                return self.save_document_as(document)
            if choice != "overwrite":
                return False
        return self._save_to(document, document.file_path)

    def _ask_disk_conflict(self, document: DiagramDocument) -> str:
        """Die Datei wurde seit dem Öffnen außerhalb des Programms geändert. ``"overwrite"``, ``"save_as"`` oder
        ``"cancel"``."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(config.APP_NAME)
        box.setText(tr("„{name}“ wurde außerhalb des Programms geändert.", name=os.path.basename(document.file_path)))
        box.setInformativeText(tr("Seit dem Öffnen hat ein anderes Programm (oder das Synchronisieren, z. B. "
                                  "OneDrive) die Datei verändert. Beim Überschreiben gehen diese Änderungen "
                                  "verloren.\n\nSoll die Datei trotzdem überschrieben werden?"))
        overwrite = box.addButton(tr("Überschreiben"), QMessageBox.ButtonRole.AcceptRole)
        save_as = box.addButton(tr("Speichern unter …"), QMessageBox.ButtonRole.ActionRole)
        cancel = box.addButton(tr("Abbrechen"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_as)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite:
            return "overwrite"
        return "save_as" if clicked is save_as else "cancel"

    def _ask_foreign_overwrite(self, document: DiagramDocument) -> str:
        """Erstes Speichern einer Datei, die nicht mit diesem Programm geschrieben wurde.

        Ergebnis: ``"overwrite"``, ``"save_as"`` oder ``"cancel"``.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(config.APP_NAME)
        box.setText(tr("„{name}“ wurde mit einem anderen Programm erstellt (z. B. dem PapDesigner).",
                       name=os.path.basename(document.file_path)))
        box.setInformativeText(tr("Beim Speichern wird die Datei neu geschrieben: Die genaue Anordnung kommt "
                                  "hinzu, Unterprogramme bleiben eigene Seiten.\n\n"
                                  "Soll die Datei überschrieben werden?"))
        overwrite = box.addButton(tr("Überschreiben"), QMessageBox.ButtonRole.AcceptRole)
        save_as = box.addButton(tr("Speichern unter …"), QMessageBox.ButtonRole.ActionRole)
        cancel = box.addButton(tr("Abbrechen"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_as)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite:
            return "overwrite"
        return "save_as" if clicked is save_as else "cancel"

    @staticmethod
    def _is_task_original(document: DiagramDocument) -> bool:
        """Aufgabe der Lehrkraft (mit Passwort), nicht die Kopie eines Schülers und nicht mit Passwort entsperrt:
        Diese Datei wird nie still überschrieben – weder automatisch noch mit „Speichern“."""
        meta = document.meta
        return bool(meta.task_lock) and not meta.task_copy and not getattr(document, "task_unlocked", False)

    @staticmethod
    def _is_task_file(meta) -> bool:
        """Aufgabendatei der Lehrkraft („Aufgabe stellen“), nicht die gespeicherte Lösung eines Schülers."""
        return bool(meta.task_lock or meta.task_title.strip() or meta.task_text.strip()) and not meta.task_copy

    @staticmethod
    def _make_task_copy(document: DiagramDocument, source: str) -> None:
        """Aus der geöffneten Aufgabe wird eine unbenannte Kopie („Aufgabe – Kopie“): Speichern fragt nach einem
        neuen Namen, automatisch gespeichert wird erst danach – die Aufgabendatei bleibt immer unverändert."""
        document.task_source = os.path.abspath(source)
        document.file_path = None
        document.meta.task_copy = "1"   # gespeichert ist es die Lösung eines Schülers, keine Aufgabe mehr
        document.title_changed.emit()

    @staticmethod
    def _replaceable(document: DiagramDocument | None) -> bool:
        """Ein unberührtes, leeres neues Projekt, das beim Öffnen einer Datei Platz machen darf (keine Aufgabe)."""
        return document is not None and document.file_path is None and not document.task_source \
            and not document.is_modified and document.is_blank()

    def _find_task_copy(self, path: str) -> int:
        """Reiter mit einer noch nicht gespeicherten Kopie dieser Aufgabe (-1: keiner)."""
        target = _path_key(path)
        for i, view in enumerate(self.views()):
            source = view.document.task_source
            if source and not view.document.file_path and _path_key(source) == target:
                return i
        return -1

    def _would_overwrite_task(self, document: DiagramDocument, path: str) -> bool:
        """Würde das Speichern eine Aufgabendatei der Lehrkraft ersetzen? Das wird nicht erlaubt – weder für die
        Lösung eines Schülers noch für ein ganz anderes Projekt.

        Ausnahme: die Lehrkraft und ihre eigene Aufgabe. Das Projekt ist selbst eine Aufgabe (keine Schülerlösung),
        freigegeben (Datei → Aufgabe bearbeiten mit Passwort, oder eben mit „Aufgabe stellen“ geändert), und das Ziel
        ist seine eigene Datei bzw. die Aufgabe, aus der die Kopie stammt."""
        if not os.path.exists(path):
            return False
        own = [p for p in (document.file_path, document.task_source) if p]
        if document.task_unlocked and not document.meta.task_copy \
                and any(_path_key(p) == _path_key(path) for p in own):
            return False
        try:
            meta = load_diagram(path).diagram.meta
        except Exception:
            return False   # keine lesbare Aufgabe: wie bisher (der Dialog hat schon nach dem Ersetzen gefragt)
        return self._is_task_file(meta)

    def edit_task_file_dialog(self) -> None:
        """Datei → Aufgabe bearbeiten: die Aufgabendatei selbst öffnen (Lehrkraft, mit Passwort)."""
        path, _ = QFileDialog.getOpenFileName(self, tr("Aufgabe bearbeiten"), self.settings_store.last_directory(),
                                              config.file_dialog_filter())
        if path:
            self.edit_task_file(path)

    def edit_task_file(self, path: str) -> bool:
        """Öffnet eine Aufgabendatei zum Ändern: Nach dem Passwort schreibt „Speichern“ in diese Datei."""
        from app import task as T

        path = os.path.abspath(path)
        if not _has_project_extension(path):
            return self.open_file(path)   # meldet den falschen Dateityp wie sonst auch
        try:
            meta = load_diagram(path).diagram.meta
        except ProjectFileError:
            return self.open_file(path)   # meldet den Fehler wie sonst auch
        except Exception:  # pragma: no cover - Absicherung
            return self.open_file(path)
        if not self._is_task_file(meta):
            if not self.open_file(path):
                return False
            if not meta.task_copy:   # die gespeicherte Lösung eines Schülers öffnet sich ohne Hinweis
                self.statusBar().showMessage(tr("„{name}“ enthält keine Aufgabe – normal geöffnet.",
                                                name=os.path.basename(path)), 6000)
            return True
        if meta.task_lock:
            entered = ask_password(self, tr("Aufgabe bearbeiten"), tr("Passwort der Lehrkraft:"))
            if entered is None:
                return False
            if not T.check_lock(meta.task_lock, entered):
                QMessageBox.warning(self, tr("Aufgabe bearbeiten"), tr("Das Passwort ist falsch."))
                return False
        return self.open_file(path, task_original=True)

    def _save_task_copy(self, document: DiagramDocument) -> bool:
        """Lösung zu einer Aufgabe als eigene Datei speichern (das Original der Lehrkraft bleibt unverändert)."""
        self.statusBar().showMessage(tr("Das ist eine Aufgabe der Lehrkraft – Ihre Lösung wird als eigene Datei "
                                        "gespeichert. (Lehrkraft: über „Aufgabe stellen“ mit Passwort entsperren.)"),
                                     10000)
        document.meta.task_copy = "1"
        if self.save_document_as(document, task_copy=True):
            return True
        document.meta.task_copy = ""
        return False

    def save_document_as(self, document: DiagramDocument, task_copy: bool = False) -> bool:
        document.scene.commit_edit()
        if document.file_path and task_copy:
            stem = os.path.splitext(document.file_path)[0]
            suggestion = tr("{name} – Lösung", name=stem) + config.FILE_EXTENSION
        elif not document.file_path and document.task_source and not document.meta.task_copy:
            # Die Lehrkraft hat die Aufgabe in der Kopie geändert: vorgeschlagen wird die Aufgabendatei selbst (das
            # Ersetzen bestätigt sie im Dialog) – ein anderer Name legt eine neue Aufgabe an
            suggestion = document.task_source
        elif not document.file_path and document.task_source:
            # Kopie einer Aufgabe: eigener Name für die Lösung, nie der Name der Aufgabendatei
            name = tr("{name} – Lösung", name=display_name_for_path(document.task_source))
            suggestion = os.path.join(self.settings_store.last_directory(),
                                      _safe_filename(name) + config.FILE_EXTENSION)
        elif document.file_path:
            suggestion = export.ensure_extension(document.file_path, config.FILE_EXTENSION)
        else:
            name = export.ensure_extension(_safe_filename(document.display_name), config.FILE_EXTENSION)
            suggestion = os.path.join(self.settings_store.last_directory(), name)
        chosen, _ = QFileDialog.getSaveFileName(self, tr("Speichern unter"), suggestion, config.file_dialog_filter())
        if not chosen:
            return False
        path = export.ensure_extension(chosen, config.FILE_EXTENSION)
        if path != chosen and os.path.exists(path):
            # Der Dialog hat nur den eingegebenen Namen geprüft, nicht den mit Endung
            answer = QMessageBox.question(
                self, tr("Speichern unter"),
                tr("„{name}“ ist bereits vorhanden.\nSoll die Datei ersetzt werden?", name=os.path.basename(path)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        if self._would_overwrite_task(document, path):
            self._error(tr("Speichern nicht möglich"),
                        tr("„{name}“ ist eine Aufgabe der Lehrkraft und wird nicht überschrieben. Bitte wählen Sie "
                           "einen anderen Namen für Ihre Lösung.", name=os.path.basename(path)))
            return False
        other = self._find_document_by_path(path)
        if other >= 0 and self.views()[other].document is not document:
            self._error(tr("Speichern nicht möglich"),
                        tr("Diese Datei ist bereits in einem anderen Tab geöffnet. "
                           "Bitte schließen Sie sie zuerst oder wählen Sie einen anderen Namen."))
            return False
        return self._save_to(document, path)

    def _save_to(self, document: DiagramDocument, path: str, automatic: bool = False) -> bool:
        """Speichert das Projekt. ``automatic``: ohne Meldungsfenster (automatisches Speichern)."""
        if automatic and path == document.file_path and document.disk_stamp is not None and not os.path.exists(path):
            # außerhalb gelöscht oder verschoben: nicht still neu anlegen – beim Speichern von Hand entscheidet man selbst
            self.statusBar().showMessage(tr("„{name}“ wurde gelöscht oder verschoben – automatisches Speichern ist "
                                            "angehalten. Bitte selbst speichern.", name=os.path.basename(path)), 8000)
            self._update_save_state()
            return False
        if automatic and path == document.file_path and document.changed_on_disk():
            # nicht still über fremde Änderungen schreiben – beim Speichern von Hand wird gefragt
            self.statusBar().showMessage(tr("„{name}“ wurde außerhalb des Programms geändert – automatisches "
                                            "Speichern ist angehalten. Bitte selbst speichern.",
                                            name=os.path.basename(path)), 8000)
            self._update_save_state()
            return False
        try:
            document.save(path, backup=self.actions["backup_on_save"].isChecked())
        except ProjectFileError as exc:
            log.warning("Speichern fehlgeschlagen: %s (%s)", path, exc.details)
            if automatic:
                document.auto_save_failed = True   # Anzeige in der Statusleiste: „angehalten“
                self.statusBar().showMessage(tr("Automatisches Speichern nicht möglich: {reason}",
                                                reason=exc.message), 8000)
                self._update_save_state()
            else:
                self._error(tr("Speichern nicht möglich"), exc.message)
            return False
        except Exception:  # pragma: no cover - Absicherung
            log.exception("Unerwarteter Fehler beim Speichern")
            if automatic:
                document.auto_save_failed = True
                self._update_save_state()
            else:
                self._error(tr("Speichern nicht möglich"),
                            tr("Beim Speichern ist ein unerwarteter Fehler aufgetreten."))
            return False
        document.auto_save_failed = False
        if not automatic:
            self.settings_store.add_recent_file(path)
            self.settings_store.set_last_directory(path)
            self._refresh_recent_menu()
        self._update_document_title(document)
        if self.autosave is not None:
            self.autosave.document_saved(document)
        self.statusBar().showMessage(tr("Automatisch gespeichert.") if automatic
                                     else tr("Gespeichert: {path}", path=path),
                                     2000 if automatic else 4000)
        return True

    # ------------------------------------------------ Automatisches Speichern
    def set_auto_save(self, enabled: bool) -> None:
        """Schaltet das automatische Speichern für dieses Fenster ein oder aus."""
        self._auto_save_enabled = bool(enabled)
        self.actions["auto_save"].setChecked(self._auto_save_enabled)
        self._update_save_state()
        if not self._auto_save_enabled:
            self._auto_save_timer.stop()
            self._auto_save_pending.clear()
            self._auto_save_since = None
            return
        for view in self.views():
            self._schedule_auto_save(view.document)

    def _sync_update_actions(self) -> None:
        """Update-Befehle: gesperrt, wenn der Administrator die Updates abgeschaltet hat."""
        a = self.actions
        locked = self.updates.disabled_by_policy()
        a["check_updates_on_start"].setChecked(not locked and self.settings_store.check_updates_on_start())
        a["check_updates_on_start"].setEnabled(not locked)
        if locked:
            for name in ("check_updates", "check_updates_on_start"):
                a[name].setStatusTip(tr("Updates wurden vom Administrator abgeschaltet."))

    def _on_check_updates_on_start(self, checked: bool) -> None:
        self.settings_store.set_check_updates_on_start(checked)
        self.statusBar().showMessage(tr("Das Programm sieht beim Start nach neuen Versionen.") if checked
                                     else tr("Beim Start wird nicht mehr nach neuen Versionen gesehen – von Hand "
                                             "weiterhin über Hilfe → Nach Updates suchen."), 5000)

    def _on_backup_triggered(self, checked: bool) -> None:
        self.settings_store.set_backup_on_save(checked)
        self.statusBar().showMessage(tr("Beim ersten Speichern wird der bisherige Stand als „.pap-backup“ "
                                        "aufgehoben.") if checked
                                     else tr("Es werden keine Sicherungskopien mehr angelegt."), 5000)

    # ------------------------------------------------ Präsentationsansicht
    @property
    def presenting(self) -> bool:
        return self._presentation is not None

    def set_presentation(self, enabled: bool) -> None:
        """Präsentationsansicht: nur der Plan (mit der Seitenleiste) im Vollbild – ohne Menüs, Leisten und Fenster.

        Beim Beenden kommt alles so zurück, wie es war.
        """
        enabled = bool(enabled)
        self.actions["presentation"].setChecked(enabled)
        if enabled == self.presenting:
            return
        if enabled:
            self._presentation = (self.saveState(WINDOW_STATE_VERSION), self.windowState())
            for widget in self.findChildren(QDockWidget) + self.findChildren(QToolBar):
                widget.hide()
            self.menuBar().hide()
            self.statusBar().hide()
            self.tabs.tabBar().hide()
            self.showFullScreen()
            view = self.current_view()
            if view is not None:
                view.setFocus()
            self._refresh_notation_hints()
            return
        state, window_state = self._presentation
        self._presentation = None
        self.menuBar().show()
        self.statusBar().show()
        self.tabs.tabBar().show()
        self.restoreState(state, WINDOW_STATE_VERSION)
        self.setWindowState(window_state)
        self._refresh_notation_hints()

    def _refresh_notation_hints(self) -> None:
        """Der Tipp auf leeren Seiten bleibt in der Präsentationsansicht weg."""
        for view in self.views():
            view.notation_hint.refresh()

    def _on_escape(self) -> None:
        """Esc: in der Präsentationsansicht schrittweise abbrechen und zuletzt die Ansicht beenden, sonst wie bisher
        Texteingabe bzw. Auswahl aufheben."""
        if self.presenting:
            self._on_presentation_escape()
        else:
            self._with_scene(lambda s: s.handle_escape())

    def _on_presentation_escape(self) -> None:
        """Esc: zuerst Texteingabe bzw. Auswahl aufheben, dann die Präsentationsansicht beenden."""
        scene = self.current_scene()
        if scene is not None and scene.is_editing:
            scene.cancel_edit()
        elif scene is not None and scene.selectedItems():
            scene.clearSelection()
        else:
            self.set_presentation(False)

    def _on_auto_save_triggered(self, checked: bool) -> None:
        self.settings_store.set_auto_save(checked)
        self.set_auto_save(checked)
        self.statusBar().showMessage(tr("Automatisches Speichern ist eingeschaltet.") if checked
                                     else tr("Automatisches Speichern ist ausgeschaltet."), 4000)

    def _auto_save_applies(self, document: DiagramDocument) -> bool:
        """Nur Projekte, die schon einmal mit diesem Programm als .pap gespeichert wurden."""
        return bool(self._auto_save_enabled and document.file_path and document.native_file
                    and not getattr(document, "restored_from_backup", False)
                    and not self._is_task_original(document)
                    and _has_project_extension(document.file_path))

    def _schedule_auto_save(self, document: DiagramDocument) -> None:
        # Beim Schließen eines Reiters meldet die Rückgängig-Liste während ihres Abbaus noch eine Änderung
        if not shiboken6.isValid(document) or not shiboken6.isValid(document.undo_stack):
            return
        if not self._auto_save_applies(document) or not document.is_modified:
            return
        self._auto_save_pending.add(document)
        now = time.monotonic()
        if self._auto_save_since is None:
            self._auto_save_since = now
        if (now - self._auto_save_since) * 1000 >= config.AUTO_SAVE_MAX_WAIT_MS:
            # Es wird ununterbrochen gearbeitet: nicht länger aufschieben
            self._auto_save_timer.start(0)
        else:
            self._auto_save_timer.start(config.AUTO_SAVE_DELAY_MS)  # Wartezeit beginnt neu

    def _run_auto_save(self) -> None:
        self._auto_save_timer.stop()
        pending, self._auto_save_pending = self._auto_save_pending, set()
        open_documents = {view.document for view in self.views()}
        for document in pending:
            if document not in open_documents or not document.is_modified \
                    or not self._auto_save_applies(document):
                continue
            if document.scene.is_editing or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
                # mitten in einer Texteingabe oder beim Ziehen nicht stören – gleich noch einmal
                self._auto_save_pending.add(document)
                continue
            self._save_to(document, document.file_path, automatic=True)
        if self._auto_save_pending:
            self._auto_save_timer.start(config.AUTO_SAVE_DELAY_MS)
        else:
            self._auto_save_since = None

    def maybe_save(self, document: DiagramDocument) -> bool:
        """Fragt bei ungespeicherten Änderungen nach. False = Abbrechen."""
        return self._settle_changes(document) != "cancel"

    def _settle_changes(self, document: DiagramDocument, more_to_come: bool = False) -> str:
        """Ungespeicherte Änderungen vor dem Schließen: speichern (automatisch oder nach Nachfrage) oder verwerfen.

        Ergebnis: ``"kept"`` (nichts geändert oder gespeichert), ``"discard"``, ``"discard_all"`` (nur mit
        ``more_to_come``: auch alle weiteren Projekte verwerfen) oder ``"cancel"``.
        """
        document.scene.commit_edit()
        if not document.is_modified:
            return "kept"
        if self._auto_save_applies(document) and self._save_to(document, document.file_path, automatic=True):
            return "kept"  # automatisches Speichern: keine Nachfrage nötig
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(config.APP_NAME)
        box.setText(tr("Das Projekt „{name}“ wurde geändert.", name=document.display_name))
        box.setInformativeText(tr("Möchten Sie die Änderungen speichern?"))
        save = box.addButton(tr("Speichern"), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(tr("Verwerfen"), QMessageBox.ButtonRole.DestructiveRole)
        discard_all = box.addButton(tr("Alle Änderungen verwerfen"), QMessageBox.ButtonRole.DestructiveRole) \
            if more_to_come else None
        cancel = box.addButton(tr("Abbrechen"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return "kept" if self.save_document(document) else "cancel"
        if clicked is discard:
            return "discard"
        if discard_all is not None and clicked is discard_all:
            return "discard_all"
        return "cancel"

    # ------------------------------------------------ Alle speichern / Alle schließen
    def save_all(self) -> bool:
        """Datei → Alle speichern: jedes geänderte Projekt; noch unbenannte fragen nacheinander nach einem Namen.

        „Abbrechen“ im Dialog hört auf. True, wenn danach alles gespeichert ist.
        """
        views = self.views()
        for view in views:
            view.document.scene.prepare_for_command()   # offene Texteingaben übernehmen
        start = self.current_view()
        saved = 0
        for view in views:
            document = view.document
            if not document.is_modified:
                continue
            self.tabs.setCurrentWidget(view)   # man sieht, welches Projekt gerade gespeichert wird
            if not self.save_document(document):
                self.statusBar().showMessage(tr("„Alle speichern“ abgebrochen – {n} Projekt(e) gespeichert.",
                                                n=saved), 6000)
                return False
            saved += 1
        if start is not None and self.tabs.indexOf(start) >= 0:
            self.tabs.setCurrentWidget(start)
        self.statusBar().showMessage(tr("{n} Projekt(e) gespeichert.", n=saved) if saved
                                     else tr("Alle Projekte sind schon gespeichert."), 4000)
        return True

    def close_all(self) -> bool:
        """Datei → Alle schließen: Bei Änderungen wird für jedes Projekt wie beim Schließen gefragt (mit „Alle
        verwerfen“). „Abbrechen“ lässt alle Reiter offen. Danach ist das Fenster leer – wie nach dem letzten Reiter."""
        views = self.views()
        for view in views:
            view.document.scene.prepare_for_command()
        if not self._settle_all(views):
            return False
        while self.tabs.count():
            if not self.close_tab(self.tabs.count() - 1, ask=False):
                return False   # pragma: no cover - kein Projekt-Reiter
        self.statusBar().showMessage(tr("Alle Projekte geschlossen."), 4000)
        return True

    def _settle_all(self, views: list) -> bool:
        """Vor dem Schließen mehrerer Projekte (Alle schließen, Beenden): ungespeicherte Änderungen klären.

        Erst wird still gespeichert, was ohnehin automatisch gespeichert wird; danach wird nur bei den übrigen
        gefragt – mit „Alle Änderungen verwerfen“, solange danach noch ein Projekt fragen würde. False = Abbrechen.
        """
        pending = [view for view in views if view.document.is_modified
                   and view.document not in self.close_without_asking]
        for view in pending:
            if self._auto_save_applies(view.document):
                self._save_to(view.document, view.document.file_path, automatic=True)
        asking = [view for view in pending if view.document.is_modified]
        for number, view in enumerate(asking):
            if not view.document.is_modified:
                continue   # inzwischen gespeichert
            self.tabs.setCurrentWidget(view)
            if number == len(asking) - 1:
                return self.maybe_save(view.document)   # das letzte: nichts mehr für „alle“
            answer = self._settle_changes(view.document, more_to_come=True)
            if answer == "cancel":
                return False
            if answer == "discard_all":
                return True
        return True

    def closeEvent(self, event) -> None:
        # Offene Texteingaben zuerst übernehmen – sonst gälte ein Projekt als
        # unverändert und der eingegebene Text ginge beim Beenden verloren.
        for view in self.views():
            view.document.scene.prepare_for_command()
        if not self._settle_all(self.views()):
            self._restart_files = None  # Schließen abgebrochen: auch kein Neustart
            event.ignore()
            return
        self.set_presentation(False)  # Fensteraufteilung ohne die ausgeblendeten Leisten merken
        self.settings_store.save_window(self.saveGeometry(), self.saveState(WINDOW_STATE_VERSION))
        self.simulation_panel.stop(silent=True)
        if self.autosave is not None:
            self.autosave.shutdown()
        if self.instance_server is not None:
            # Das Fenster schließt sich: weitere Programmstarts sollen nicht mehr hierher übergeben, sondern selbst
            # das erste Programm werden.
            self.instance_server.close()
        if self._restart_files is not None:
            # erst jetzt: auch Projekte, die eben im Schließen-Dialog zum ersten Mal gespeichert wurden
            self._restart_files = [view.document.file_path for view in self.views() if view.document.file_path]
            restart.launch_after_quit(QApplication.instance(), self._restart_files)
            self._restart_files = None
        event.accept()

    def offer_recovery(self) -> int:
        """Bietet nach einem Absturz die Wiederherstellung ungespeicherter Projekte an."""
        if self.autosave is None:
            return 0
        entries = self.autosave.find_orphans()
        if not entries:
            return 0
        dialog = RecoveryDialog(entries, self)
        result = dialog.exec()
        if result == RecoveryDialog.DISCARD_ALL:
            selected = []
        elif result == RecoveryDialog.DialogCode.Accepted:
            selected = dialog.selected_entries()
        else:
            return 0  # Esc / Fenster schließen: Sicherungen bleiben für den nächsten Start
        restored = 0
        for entry in entries:
            if entry in selected:
                try:
                    document = self.autosave.restore(entry)
                except ProjectFileError as exc:
                    # nicht löschen: beiseitegelegt bleibt die Datei für einen Rettungsversuch erhalten
                    kept = self.autosave.set_aside(entry)
                    message = exc.message if kept is None else exc.message + "\n\n" + tr(
                        "Die Sicherung wurde aufbewahrt: {path}", path=kept)
                    self._error(tr("Wiederherstellung nicht möglich"), message)
                    continue
                if document.file_path and self._is_task_file(document.meta) and not document.task_unlocked:
                    # Aufgabendatei, die niemand freigegeben hatte: auch wiederhergestellt nur als Kopie. Hatte die
                    # Lehrkraft sie über Datei → Aufgabe bearbeiten geöffnet, kommt sie wieder in ihre Datei
                    # (gespeichert wird wie nach jeder Wiederherstellung erst nach einem bewussten Speichern).
                    self._make_task_copy(document, document.file_path)
                self.add_document(document)
                self.autosave.adopt(document, entry)
                restored += 1
            else:
                self.autosave.discard(entry)
        if restored:
            self.statusBar().showMessage(tr("{n} Projekt(e) wiederhergestellt – bitte speichern.", n=restored), 8000)
        return restored

    # ============================================================ Extras
    def show_code_dialog(self) -> None:
        document = self.current_document()
        if document is not None:
            document.scene.prepare_for_command()
            CodeDialog(document, self).exec()

    def show_structogram(self) -> None:
        document = self.current_document()
        if document is not None:
            document.scene.prepare_for_command()
            StructogramDialog(document, self).exec()

    def auto_layout(self) -> None:
        view = self.current_view()
        if view is None:
            return
        scene = view.document.scene
        scene.prepare_for_command()
        try:
            plan = plan_auto_layout(scene)
        except Exception:
            log.exception("Automatisches Anordnen fehlgeschlagen")
            self._error(tr("Anordnen nicht möglich"), tr("Beim automatischen Anordnen ist ein Fehler aufgetreten."))
            return
        if apply_layout(scene, plan):
            view.fit_diagram()
            self.statusBar().showMessage(tr("Plan automatisch angeordnet (Rückgängig mit Strg+Z)."), 5000)
        else:
            self.statusBar().showMessage(tr("Der Plan ist bereits angeordnet."), 4000)

    def _sync_theme_actions(self) -> None:
        name = self.current_theme_name()
        self.actions["theme_dark"].setChecked(name == "dark")
        self.actions["theme_light"].setChecked(name == "light")
        self.actions["toggle_theme"].setIcon(icons.icon("theme_light" if name == "light" else "theme_dark"))

    @staticmethod
    def current_theme_name() -> str:
        return theme_module.theme_name_of(styles.current_theme())

    def toggle_theme(self) -> None:
        """Knopf in der Werkzeugleiste: zwischen Dunkel und Hell wechseln."""
        self.set_theme("dark" if self.current_theme_name() == "light" else "light")

    def set_theme(self, name: str) -> None:
        """Farbschema zur Laufzeit umschalten (wird gespeichert)."""
        app = QApplication.instance()
        theme = theme_module.apply_ui_theme(app, name)
        theme_module.save_theme_name(name)
        for view in self.views():
            for scene in view.document.scenes():  # auch die gerade nicht angezeigten Seiten
                scene.theme = theme
                scene.update()
            view.refresh_background()
        self.actions.refresh_icons()
        self.export_menu.setIcon(icons.icon("export"))
        for view in self.views():
            index = self.tabs.indexOf(view)
            button = self.tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
            if button is not None:
                button.setIcon(icons.icon("close"))
        self.palette.update()
        for entry in self.palette.entries:
            entry.update()
        self.simulation_panel.refresh_theme()
        self.diagnostics_panel.refresh_theme()
        self.code_panel.refresh_theme()
        for name in ("toggle_task", "toggle_code_view", "toggle_simulation"):
            self.actions[name].setIcon(icons.icon(self.actions[name].property("icon_name")))
        for entries in self._toolbar_groups.values():
            for proxy in entries:
                source = proxy.property("source")
                if source is not None:
                    proxy.setIcon(source.icon())
        for view in self.views():
            view.minimap.invalidate()
        self.diagnostics_panel.refresh()
        self.page_bar.refresh_theme()
        self._sync_theme_actions()
        self._update_save_state()   # Symbol der Speicher-Anzeige im neuen Farbschema
        self.theme_changed.emit(self.current_theme_name())

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self.settings_store.recent_files()
        if not files:
            empty = self.recent_menu.addAction(tr("(keine)"))
            empty.setEnabled(False)
        for index, path in enumerate(files, start=1):
            action = self.recent_menu.addAction(f"&{index}  {os.path.basename(path)}")
            action.setStatusTip(path)
            action.setToolTip(path)
            action.triggered.connect(lambda _=False, p=path: self.open_file(p))
        if files:
            self.recent_menu.addSeparator()
            clear = self.recent_menu.addAction(tr("Liste leeren"))
            clear.triggered.connect(self._clear_recent)
        self.empty_state.refresh_recent(files)

    def _clear_recent(self) -> None:
        self.settings_store.clear_recent_files()
        self._refresh_recent_menu()

    # Dateien per Drag & Drop auf das Fenster öffnen
    @staticmethod
    def _openable(path: str) -> bool:
        return _has_project_extension(path)

    def dragEnterEvent(self, event) -> None:
        if any(self._openable(url.toLocalFile()) for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if self._openable(path):
                self.open_file(path)
        event.acceptProposedAction()

    # ============================================================ Bearbeiten
    def _undo(self) -> None:
        self._undo_redo(undo=True)

    def _redo(self) -> None:
        self._undo_redo(undo=False)

    def _undo_redo(self, undo: bool) -> None:
        """Rückgängig/Wiederholen; betrifft der Schritt eine andere Seite, wird sie danach angezeigt."""
        document = self.current_document()
        if document is None:
            self.undo_group.undo() if undo else self.undo_group.redo()
            return
        document.scene.prepare_for_command()
        stack = document.undo_stack
        page = document.command_page(stack.command(stack.index() - 1 if undo else stack.index()), last=not undo)
        stack.undo() if undo else stack.redo()
        if page is not None and page in document.pages:
            document.show_page(page)

    def _update_undo_texts(self) -> None:
        undo_text = self.undo_group.undoText()
        redo_text = self.undo_group.redoText()
        self.actions["undo"].setText(tr("&Rückgängig: {text}", text=undo_text) if undo_text else tr("&Rückgängig"))
        self.actions["redo"].setText(tr("&Wiederholen: {text}", text=redo_text) if redo_text else tr("&Wiederholen"))

    def copy(self) -> None:
        scene = self.current_scene()
        if scene is None or clipboard.selection_payload(scene) is None:
            return
        if clipboard.copy_selection(scene):
            self.paste_tracker.reset()
            self.statusBar().showMessage(tr("In die Zwischenablage kopiert."), 2500)
        else:
            self._error(clean_text(self.actions["copy"].text()), CLIPBOARD_BUSY())

    def _insert_special(self, text: str) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        if not scene.is_editing and scene.single_selected is not None:
            scene.begin_element_edit(scene.single_selected)  # Text des Bausteins am Ende ergänzen
        if not scene.insert_into_editor(text):
            self.statusBar().showMessage(tr("Sonderzeichen gibt es während der Texteingabe (Doppelklick auf einen "
                                            "Baustein)."), 4000)

    def copy_image(self) -> None:
        """Auswahl bzw. ganze Seite als Bild in die Zwischenablage."""
        scene = self.current_scene()
        if scene is None:
            return
        selected = bool(scene.selected_elements())
        if clipboard.copy_image(scene):
            self.statusBar().showMessage(tr("Auswahl als Bild kopiert – in Word oder OneNote mit Strg+V einfügen.")
                                         if selected else
                                         tr("Seite als Bild kopiert – in Word oder OneNote mit Strg+V einfügen."),
                                         4000)
        else:
            self._error(clean_text(self.actions["copy_image"].text()), CLIPBOARD_BUSY())

    def cut(self) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        payload = clipboard.selection_payload(scene)
        if payload is None:
            return
        if clipboard.cut_selection(scene):
            self.paste_tracker.prime_after_cut(payload)
        else:
            self._error(clean_text(self.actions["cut"].text()), CLIPBOARD_BUSY())

    def paste(self, at: QPointF | None = None) -> None:
        view = self.current_view()
        payload = clipboard.clipboard_payload()
        if view is None or payload is None:
            return
        scene = view.document.scene
        if at is not None:
            ids = clipboard.paste_payload(scene, payload, target_center=at)
        else:
            offset = self.paste_tracker.next_offset(payload, config.PASTE_OFFSET)
            if offset.isNull() and _originals_in_place(scene, payload):
                # Ausschneiden wurde rückgängig gemacht: nicht deckungsgleich auf das Original legen
                offset = self.paste_tracker.next_offset(payload, config.PASTE_OFFSET)
            bounds = clipboard.payload_bounds(payload).translated(offset)
            if bounds.isValid() and not view.visible_scene_rect().intersects(bounds):
                ids = clipboard.paste_payload(scene, payload, target_center=view.visible_center())
                self.paste_tracker.reset()
            else:
                ids = clipboard.paste_payload(scene, payload, offset=offset)
        self._reveal(ids)

    def duplicate(self) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        payload = clipboard.selection_payload(scene)
        if payload is None:
            return
        ids = clipboard.paste_payload(scene, payload, offset=QPointF(config.PASTE_OFFSET, config.PASTE_OFFSET),
                                      text=tr("Duplizieren"))
        self._reveal(ids)

    def _reveal(self, ids) -> None:
        view = self.current_view()
        if view is None or not ids:
            return
        rect = QRectF()
        for eid in ids:
            item = view.document.scene.element(eid)
            if item is not None:
                rect = rect.united(item.scene_rect())
        if not rect.isNull():
            view.ensureVisible(rect, 40, 40)
        view.setFocus()

    def edit_selected_text(self) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        if scene.single_selected is not None:
            scene.begin_element_edit(scene.single_selected, select_all=True)
            return
        connections = scene.selected_connections()
        if len(connections) == 1:
            scene.begin_label_edit(connections[0])

    def insert_element(self, element_type: ElementType, loop_kind: str | None = None) -> None:
        view = self.current_view()
        if view is None:
            self.new_document()
            view = self.current_view()
        if ElementType(element_type) is ElementType.JUNCTION:
            self._insert_junction(view)
            return
        element_id = view.document.scene.insert_element_smart(ElementType(element_type), view.visible_center(),
                                                              loop_kind=loop_kind)
        self._reveal([element_id] if element_id else [])

    def _insert_junction(self, view: DiagramView) -> None:
        """Verbindungspunkt per Klick oder Taste: auf den ausgewählten Pfeil bzw. den Ausgangspfeil des ausgewählten
        Bausteins, jeweils in die Mitte. (Ziehen aus der Palette setzt ihn genau dorthin, wo man loslässt.)"""
        scene = view.document.scene
        connections = scene.selected_connections()
        if not connections and scene.single_selected is not None:
            connections = [c for c in scene.single_selected.connections
                           if c.source is scene.single_selected and not c.is_annotation]
        if len(connections) != 1:
            self.statusBar().showMessage(tr("Verbindungspunkt: zuerst einen Pfeil auswählen – oder den Verbindungspunkt "
                                            "aus dem Feld „Bausteine“ auf einen Pfeil ziehen."), 6000)
            return
        points = connections[0].points()
        if len(points) < 2:
            return
        # Mitte des längsten Stücks der Linie (liegt sicher auf dem Pfeil, auch bei Knicken)
        a, b = max(zip(points[:-1], points[1:]), key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
        point = QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        element_id = scene.insert_junction(connections[0], point)
        self._reveal([element_id] if element_id else [])

    def align(self, mode: str) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        snap = scene.snap_value if scene.settings.snap_to_grid else None

        def force_snap(x: float, y: float) -> tuple[float, float]:
            point = scene.force_snap_point(QPointF(x, y))
            return point.x(), point.y()

        moves = alignment.compute_moves(scene.selected_elements(), mode, snap_value=snap, force_snap=force_snap)
        # Text des Rückgängig-Schritts: die Beschriftungen in alignment.LABELS sind dort mit N_ markiert
        scene.apply_moves(moves, tr(alignment.LABELS.get(mode, N_("Ausrichten"))))

    def toggle_loop_part(self) -> None:
        scene = self.current_scene()
        if scene is not None and scene.single_selected is not None:
            scene.toggle_loop_part(scene.single_selected)

    def add_bend(self) -> None:
        scene = self.current_scene()
        connections = scene.selected_connections() if scene is not None else []
        if len(connections) == 1:
            points = connections[0].points()
            middle = points[len(points) // 2 - 1], points[len(points) // 2]
            scene.add_bend(connections[0], QPointF((middle[0][0] + middle[1][0]) / 2, (middle[0][1] + middle[1][1]) / 2))

    def reset_routing(self) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        for conn in scene.selected_connections():
            scene.reset_routing(conn)

    def jump_along_line(self, forward: bool, connection: ConnectionItem | None = None) -> None:
        """Wählt den Baustein am Ziel (``forward``) bzw. Anfang des Pfeils aus und holt ihn ins Bild.

        Ohne ``connection`` gilt der einzige ausgewählte Pfeil. Verbindungspunkte unterwegs werden übersprungen.
        """
        view = self.current_view()
        if view is None:
            return
        scene = view.document.scene
        if connection is None:
            connections = scene.selected_connections()
            if len(connections) != 1:
                return
            connection = connections[0]
        if not shiboken6.isValid(connection) or connection.scene() is not scene:
            return
        scene.commit_edit()
        item = line_end(connection, forward)
        if item is None:
            return
        scene.select_items([item])
        rect = item.scene_rect()
        # Liegt der Baustein schon ganz im Bild, bleibt die Ansicht stehen – sonst kommt er in die Mitte
        if not view.visible_scene_rect().adjusted(20, 20, -20, -20).contains(rect):
            view.centerOn(rect.center())
        view.setFocus()

    def _set_grid_visible(self, visible: bool) -> None:
        self._change_view_setting("grid_visible", visible, tr("Raster anzeigen") if visible else tr("Raster ausblenden"))

    def _set_snap(self, enabled: bool) -> None:
        self._change_view_setting("snap_to_grid", enabled,
                                  tr("Einrasten einschalten") if enabled else tr("Einrasten ausschalten"))

    def _change_view_setting(self, attr: str, value: bool, text: str) -> None:
        """Raster/Einrasten gehören zum Projekt: als Rückgängig-Schritt, damit sie gespeichert werden."""
        document = self.current_document()
        if document is not None and bool(getattr(document.settings, attr)) != bool(value):
            document.undo_stack.push(ViewSettingCommand(document, attr, value, text))
        self._sync_grid_actions()
        self._update_status()

    def _sync_grid_actions(self) -> None:
        document = self.current_document()
        for name, attr in (("toggle_grid", "grid_visible"), ("toggle_snap", "snap_to_grid")):
            action = self.actions[name]
            action.blockSignals(True)
            action.setChecked(bool(getattr(document.settings, attr)) if document else True)
            action.blockSignals(False)

    # ============================================================ Kontextmenü
    def show_context_menu(self, scene_pos: QPointF, global_pos) -> None:
        view = self.sender() if isinstance(self.sender(), DiagramView) else self.current_view()
        if view is None:
            return
        scene = view.document.scene
        scene.commit_edit()
        item = _interactive_item_at(scene, scene_pos)
        if item is not None and not item.isSelected():
            scene.select_items([item])
        a = self.actions
        menu = QMenu(self)
        if isinstance(item, FlowItem):
            menu.addAction(a["edit_text"])
            if can_start_line(item):
                menu.addAction(a["connect_to"])   # Pfeil ohne Ziehen: Ziel aus einer Liste
            menu.addSeparator()
            for name in ("cut", "copy", "copy_image", "duplicate", "delete"):
                menu.addAction(a[name])
            menu.addSeparator()
            menu.addAction(a["bring_front"])
            menu.addAction(a["send_back"])
            if item.element_type is ElementType.LOOP:
                menu.addSeparator()
                is_end = item.data.properties.get("part") == "end"
                toggle = menu.addAction(tr("In Schleifenbeginn umwandeln") if is_end
                                        else tr("In Schleifenende umwandeln"))
                toggle.triggered.connect(lambda: scene.toggle_loop_part(item))
            if item.element_type is ElementType.SUBPROGRAM:
                menu.addSeparator()
                name = "" if subprograms.is_placeholder(item) else subprograms.call_name(item.data.text)
                if name and view.document.flow_start(item.data.text) is not None:
                    action = menu.addAction(icons.element_icon(ElementType.SUBPROGRAM),
                                            tr("Unterprogramm „{name}“ öffnen", name=name))
                else:
                    action = menu.addAction(icons.element_icon(ElementType.SUBPROGRAM),
                                            tr("Unterprogramm „{name}“ anlegen …", name=name) if name
                                            else tr("Unterprogramm anlegen …"))
                action.setToolTip(tr("Auch mit Strg+Doppelklick auf den Baustein"))
                action.triggered.connect(lambda: self.open_subprogram_for(item))
                # wie der Eingabedialog des PapDesigners: ein vorhandenes Unterprogramm als Aufruf wählen
                pages = view.document.pages[1:]
                if pages:
                    calls_menu = menu.addMenu(tr("Ruft auf"))
                    for page in pages:
                        choice = calls_menu.addAction(page.display_name)
                        choice.setCheckable(True)
                        choice.setChecked(subprograms.call_target(item.data.text) == page.flow_name)
                        choice.triggered.connect(lambda _=False, p=page: self._set_call(item, p))
            if not item.is_junction and not item.is_comment:
                menu.addSeparator()
                change_menu = menu.addMenu(tr("Ändern in"))
                for element_type in CHANGEABLE_TYPES:
                    if element_type is not item.element_type:
                        change = change_menu.addAction(icons.element_icon(element_type), display_name_for(element_type))
                        change.triggered.connect(lambda _=False, t=element_type: scene.change_element_type(item, t))
            if item.element_type not in (ElementType.START, ElementType.END) and not item.is_comment:
                menu.addAction(a["extract_subprogram"])
            if not item.is_comment:
                menu.addAction(a["toggle_breakpoint"])
            menu.addSeparator()
            if len(scene.selected_elements()) >= 2:
                align_menu = menu.addMenu(tr("Ausrichten"))
                for name in ALIGN_ACTIONS:
                    align_menu.addAction(a[name])
            menu.addAction(a[alignment.SNAP_TO_GRID])
        elif isinstance(item, ConnectionItem):
            label = menu.addAction(tr("Beschriftung bearbeiten"))
            label.setShortcut(QKeySequence("F2"))
            label.setEnabled(not item.is_annotation)
            label.triggered.connect(lambda: scene.begin_label_edit(item))
            bend = menu.addAction(tr("Knick hier einfügen"))
            bend.triggered.connect(lambda _=False, p=QPointF(scene_pos): scene.add_bend(item, p))
            reset = menu.addAction(tr("Linienführung zurücksetzen"))
            reset.setEnabled(item.has_manual_routing())
            reset.triggered.connect(lambda: scene.reset_routing(item))
            junction = menu.addAction(icons.element_icon(ElementType.JUNCTION), tr("Verbindungspunkt hier einfügen"))
            junction.setToolTip(tr("Teilt die Verbindung; am Punkt lassen sich die Linie führen und weitere Pfeile "
                                   "anschließen"))
            junction.setEnabled(not item.is_annotation)
            junction.triggered.connect(lambda _=False, p=QPointF(scene_pos): scene.insert_junction(item, p))
            menu.addSeparator()
            # dem Pfeil folgen: eigene Einträge, damit sie genau für diesen Pfeil gelten
            for name, forward in (("jump_to_source", False), ("jump_to_target", True)):
                jump = menu.addAction(a[name].text())
                jump.setShortcuts(a[name].shortcuts())
                jump.setStatusTip(a[name].statusTip())
                jump.triggered.connect(lambda _=False, f=forward: self.jump_along_line(f, item))
            menu.addSeparator()
            menu.addAction(a["delete"])
        else:
            new_menu = menu.addMenu(icons.icon("new"), tr("Neu"))
            for element_type in PALETTE_ORDER + (ElementType.CONNECTOR,) + FLOW_TERMINALS:
                action = new_menu.addAction(icons.element_icon(element_type), a[insert_action_name(element_type)].text())
                action.triggered.connect(lambda _=False, t=element_type, p=QPointF(scene_pos):
                                         self._insert_at(view, t, p))
                if element_type is ElementType.CONNECTOR:
                    new_menu.addSeparator()
            paste = menu.addAction(icons.icon("paste"), tr("Einfügen"))
            paste.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
            paste.setEnabled(clipboard.can_paste())
            paste.triggered.connect(lambda _=False, p=QPointF(scene_pos): self.paste(at=p))
            menu.addAction(a["select_all"])
            menu.addAction(a["copy_image"])
            menu.addSeparator()
            menu.addAction(a["new_subprogram"])
            menu.addSeparator()
            grid_menu = menu.addMenu(icons.icon("grid"), tr("Raster"))
            grid_menu.addAction(a["toggle_grid"])
            grid_menu.addAction(a["toggle_snap"])
            view_menu = menu.addMenu(icons.icon("zoom_fit"), tr("Ansicht"))
            for name in ("zoom_in", "zoom_out", "zoom_reset", "zoom_fit"):
                view_menu.addAction(a[name])
        menu.exec(global_pos)

    def _insert_at(self, view: DiagramView, element_type: ElementType, pos: QPointF) -> None:
        element_id = view.document.scene.insert_element(element_type, pos)
        self._reveal([element_id] if element_id else [])

    # ============================================================ Unterprogramme
    def show_page(self, index: int) -> None:
        document = self.current_document()
        if document is not None and 0 <= index < len(document.pages):
            document.set_current_page(index)
            view = self.current_view()
            if view is not None:
                view.setFocus()

    def _step_page(self, step: int) -> None:
        document = self.current_document()
        if document is not None:
            self.show_page(document.current_page_index + step)

    def _ask_subprogram_name(self, document: DiagramDocument, title: str, initial: str, page=None) -> str | None:
        """Fragt nach dem Namen eines Unterprogramms. ``None`` = abgebrochen."""
        dialog = SubprogramNameDialog(document, title, initial, page, self)
        if dialog.exec() != SubprogramNameDialog.DialogCode.Accepted:
            return None
        return dialog.name()

    def new_subprogram(self, name: str | None = None) -> bool:
        """Legt ein Unterprogramm auf einer eigenen Seite an (Start „Name“ → Ende) und zeigt es an.

        Ohne ``name`` wird nachgefragt; vorgeschlagen wird ein Aufruf, zu dem es noch keinen Ablauf gibt.
        """
        document = self.current_document()
        if document is None:
            return False
        document.scene.prepare_for_command()
        if name is None:
            name = self._ask_subprogram_name(document, tr("Neues Unterprogramm"), subprograms.suggested_name(document))
            if name is None:
                return False
        error = subprograms.name_error(document, name)
        if error is not None:
            self._error(tr("Unterprogramm anlegen"), error)
            return False
        page = subprograms.create_subprogram(document, name)
        self._after_page_created(page)
        self.statusBar().showMessage(tr("Unterprogramm „{name}“ angelegt – ein Unterprogramm-Baustein mit diesem "
                                        "Namen ruft es auf.", name=page.display_name), 6000)
        return True

    def _after_page_created(self, page) -> None:
        view = self.current_view()
        if view is not None:
            view.restore_view_state()
            view.setFocus()

    def rename_subprogram(self, index: int | None = None, name: str | None = None) -> bool:
        document = self.current_document()
        if document is None:
            return False
        index = document.current_page_index if index is None else index
        if not 0 < index < len(document.pages):
            return False
        page = document.pages[index]
        document.scene.prepare_for_command()
        if name is None:
            name = self._ask_subprogram_name(document, tr("Unterprogramm umbenennen"), page.display_name, page)
            if name is None:
                return False
        if subprograms.clean_name(name) == page.display_name:
            return False
        error = subprograms.name_error(document, name, page)
        if error is not None:
            self._error(tr("Unterprogramm umbenennen"), error)
            return False
        calls = len(subprograms.callers(document, page))
        if not subprograms.rename_subprogram(document, page, name):
            return False
        document.show_page(page)
        self.statusBar().showMessage(
            tr("Unterprogramm umbenannt – auch {n} Aufruf(e) wurden angepasst.", n=calls) if calls
            else tr("Unterprogramm umbenannt."), 5000)
        return True

    def delete_subprogram(self, index: int | None = None, confirm: bool = True) -> bool:
        document = self.current_document()
        if document is None:
            return False
        index = document.current_page_index if index is None else index
        if not 0 < index < len(document.pages):
            return False
        page = document.pages[index]
        document.scene.prepare_for_command()
        if confirm and page.scene.elements():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(config.APP_NAME)
            box.setText(tr("Unterprogramm „{name}“ löschen?", name=page.display_name))
            calls = len(subprograms.callers(document, page))
            info = tr("Die Seite wird mit allen Bausteinen gelöscht (Rückgängig mit Strg+Z).")
            if calls:
                info += "\n\n" + tr("{n} Unterprogramm-Baustein(e) rufen es noch auf; sie bleiben erhalten.", n=calls)
            box.setInformativeText(info)
            delete = box.addButton(tr("Löschen"), QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(tr("Abbrechen"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(cancel)
            box.setEscapeButton(cancel)
            box.exec()
            if box.clickedButton() is not delete:
                return False
        subprograms.delete_subprogram(document, page)
        self.statusBar().showMessage(tr("Unterprogramm gelöscht (Rückgängig mit Strg+Z)."), 5000)
        return True

    # ------------------------------------------------------------ Seiten kopieren, verschieben, auslagern
    def page_command(self, name: str, index: int | None = None) -> bool:
        """Seitenbefehle aus Menü und Seitenleiste: duplizieren, kopieren, ausschneiden, einfügen, verschieben."""
        document = self.current_document()
        if document is None:
            return False
        document.scene.prepare_for_command()
        index = document.current_page_index if index is None else index
        if not 0 <= index < len(document.pages):
            return False
        page = document.pages[index]
        if name == "copy_page":
            if not subprograms.copy_page(page):
                self._error(tr("Seite kopieren"), CLIPBOARD_BUSY())
                return False
            self.statusBar().showMessage(tr("Seite „{name}“ kopiert – mit „Seite einfügen“ (auch in einem anderen "
                                            "Projekt) wird sie ein Unterprogramm.", name=page.display_name), 6000)
            return True
        if name == "paste_page":
            new = subprograms.paste_page(document, index + 1 if index > 0 else None)
            if new is None:
                return False
            self._after_page_created(new)
            self.statusBar().showMessage(tr("Unterprogramm „{name}“ eingefügt.", name=new.display_name), 5000)
            return True
        if page.is_main:
            return False
        if name == "duplicate_page":
            new = subprograms.duplicate_subprogram(document, page)
            self._after_page_created(new)
            self.statusBar().showMessage(tr("Kopie „{name}“ angelegt.", name=new.display_name), 5000)
            return True
        if name == "cut_page":
            if not subprograms.cut_page(document, page):
                self._error(tr("Seite ausschneiden"), CLIPBOARD_BUSY())
                return False
            self.statusBar().showMessage(tr("Unterprogramm „{name}“ ausgeschnitten – mit „Seite einfügen“ wieder "
                                            "einfügen (Rückgängig mit Strg+Z).", name=page.display_name), 6000)
            return True
        if name in ("move_page_left", "move_page_right"):
            return subprograms.move_subprogram(document, page, -1 if name == "move_page_left" else 1)
        return False

    def move_page_to(self, source: int, target: int) -> bool:
        """Ein Reiter wurde in der Seitenleiste an eine andere Stelle gezogen."""
        document = self.current_document()
        if document is None or not 0 < source < len(document.pages):
            return False
        return subprograms.move_subprogram(document, document.pages[source], target - source)

    def _go_history(self, back: bool) -> None:
        document = self.current_document()
        if document is not None and (document.go_back() if back else document.go_forward()):
            view = self.current_view()
            if view is not None:
                view.setFocus()

    def reveal_element(self, page, item) -> None:
        """Zeigt eine Seite, markiert den Baustein und holt ihn ins Bild."""
        document = self.current_document()
        if document is None or document.page_index(page) < 0 or not shiboken6.isValid(item) \
                or item.scene() is not page.scene:
            return
        document.show_page(page)
        page.scene.select_items([item])
        view = self.current_view()
        if view is not None:
            view.ensureVisible(item.scene_rect(), 80, 80)
            view.setFocus()

    def extract_subprogram(self, name: str | None = None) -> bool:
        """„Auswahl in Unterprogramm auslagern“: die markierten Bausteine kommen auf eine eigene Seite."""
        document = self.current_document()
        if document is None:
            return False
        scene = document.scene
        scene.prepare_for_command()
        title = tr("Auswahl in Unterprogramm auslagern")
        error = subprograms.extraction_error(scene)
        if error is not None:
            self._error(title, error)
            return False
        if name is None:
            name = self._ask_subprogram_name(document, title, subprograms.suggested_name(document))
            if name is None:
                return False
        error = subprograms.name_error(document, name)
        if error is not None:
            self._error(title, error)
            return False
        page = subprograms.extract_to_subprogram(document, scene, name)
        if page is None:
            return False
        self.statusBar().showMessage(tr("Ausgelagert nach „{name}“ – Strg+Doppelklick auf den Baustein öffnet es, "
                                        "Alt+← kehrt zurück.", name=page.display_name), 6000)
        return True

    def _request_subprogram(self, item) -> None:
        """Strg+Doppelklick: erst nach dem Doppelklick öffnen – bis dahin gehört die Maus der bisherigen Seite."""
        QTimer.singleShot(0, lambda: self.open_subprogram_for(item) if shiboken6.isValid(item) else None)

    def _set_call(self, item, page) -> None:
        """Ein Unterprogramm-Baustein ruft danach das Unterprogramm dieser Seite auf (Argumente bleiben)."""
        scene = item.scene()
        if scene is None or subprograms.call_target(item.data.text) == page.flow_name:
            return
        scene.prepare_for_command()
        if subprograms.is_placeholder(item):
            text = subprograms.routine_label(page.display_name)
        else:
            text = subprograms.renamed_call(item.data.text, page.display_name)
        from app.commands import EditTextCommand
        scene.undo_stack.push(EditTextCommand(scene, item.element_id, item.data.text, text))

    def open_selected_subprogram(self) -> None:
        scene = self.current_scene()
        if scene is not None and scene.single_selected is not None \
                and scene.single_selected.element_type is ElementType.SUBPROGRAM:
            self.open_subprogram_for(scene.single_selected)

    def open_subprogram_for(self, item) -> bool:
        """Zeigt das Unterprogramm, das ein Unterprogramm-Baustein aufruft; fehlt es, wird es angelegt."""
        document = self.current_document()
        if document is None or item is None or item.element_type is not ElementType.SUBPROGRAM:
            return False
        document.scene.prepare_for_command()
        placeholder = subprograms.is_placeholder(item)  # noch der Standardtext: ruft nichts Bestimmtes auf
        found = None if placeholder else document.flow_start(item.data.text)
        if found is not None:
            page, start = found
            document.show_page(page)
            page.scene.select_items([start])
            view = self.current_view()
            if view is not None:
                view.ensureVisible(start.scene_rect(), 80, 80)
                view.setFocus()
            return True
        # noch kein Ablauf mit diesem Namen: anlegen (Name aus dem Baustein, wenn er schon einen trägt)
        initial = "" if placeholder else subprograms.call_name(item.data.text)
        name = self._ask_subprogram_name(document, tr("Neues Unterprogramm"),
                                         initial or subprograms.suggested_name(document))
        if name is None:
            return False
        error = subprograms.name_error(document, name)
        if error is not None:
            self._error(tr("Unterprogramm anlegen"), error)
            return False
        stack = document.undo_stack
        stack.beginMacro(tr("Unterprogramm „{name}“ anlegen", name=subprograms.clean_name(name)))
        if subprograms.call_name(item.data.text) != subprograms.clean_name(name):
            # der Baustein ruft danach genau dieses Unterprogramm auf
            from app.commands import EditTextCommand
            stack.push(EditTextCommand(item.scene(), item.element_id, item.data.text,
                                       subprograms.renamed_call(item.data.text, subprograms.clean_name(name))))
        page = subprograms.create_subprogram(document, name)
        stack.endMacro()
        self._after_page_created(page)
        self.statusBar().showMessage(tr("Unterprogramm „{name}“ angelegt.", name=page.display_name), 5000)
        return True

    # ============================================================ Dialoge
    def edit_properties(self) -> None:
        document = self.current_document()
        if document is None:
            return
        dialog = ProjectPropertiesDialog(document.meta, document.settings.grid_size, document.file_path, self)
        if dialog.exec() != ProjectPropertiesDialog.DialogCode.Accepted:
            return
        new_meta = dialog.result_meta()
        new_grid = dialog.result_grid_size()
        old_meta = document.meta
        changed = (new_meta.name != old_meta.name or new_meta.author != old_meta.author
                   or new_meta.description != old_meta.description
                   or new_grid != document.settings.grid_size)
        if changed:
            document.undo_stack.push(ProjectPropertiesCommand(document, old_meta, new_meta,
                                                              document.settings.grid_size, new_grid))
        if new_meta.author != old_meta.author:
            self.settings_store.set_default_author(new_meta.author)

    def _export_options(self, fmt: str) -> export.ExportOptions | None:
        current = self.export_options.get(fmt, export.ExportOptions())
        dialog = ExportOptionsDialog(fmt, current, self, self._stamp_settings())
        if dialog.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return None
        stamp = dialog.stamp_settings()
        self.settings_store.set_value("export/stamp", stamp.enabled)
        self.settings_store.set_value("export/name", stamp.name)
        self.settings_store.set_value("export/class", stamp.school_class)
        options = dialog.options()
        self.export_options[fmt] = options
        return options

    def _stamp_settings(self) -> StampSettings:
        """Name, Klasse und Datum auf dem Plan – wie beim letzten Export eingestellt."""
        enabled = str(self.settings_store.value("export/stamp", False)).strip().lower() in ("true", "1")
        return StampSettings(enabled, str(self.settings_store.value("export/name", "") or ""),
                             str(self.settings_store.value("export/class", "") or ""))

    def export_diagram(self, fmt: str) -> None:
        document = self.current_document()
        if document is None:
            return
        if (document.is_empty() if fmt == "PDF" else not document.scene.elements()):
            self._error(tr("Export nicht möglich"), tr("Das Diagramm ist leer – es gibt nichts zu exportieren."))
            return
        options = self._export_options(fmt)
        if options is None:
            return
        extension = {"PNG": ".png", "JPG": ".jpg", "SVG": ".svg", "PDF": ".pdf"}[fmt]
        filters = {"PNG": tr("PNG-Bild ({pattern})", pattern="*.png"),
                   "JPG": tr("JPG-Bild ({pattern})", pattern="*.jpg *.jpeg"),
                   "SVG": tr("SVG-Grafik ({pattern})", pattern="*.svg"),
                   "PDF": tr("PDF-Dokument ({pattern})", pattern="*.pdf")}
        # Ordner: wohin dieses Projekt zuletzt exportiert wurde, sonst der Ordner der Projektdatei, sonst der des
        # letzten Exports überhaupt (z. B. bei einem unbenannten Projekt), sonst der zuletzt benutzte Ordner
        base_dir = (getattr(document, "last_export_directory", None)
                    or (os.path.dirname(document.file_path) if document.file_path else None)
                    or self.settings_store.last_export_directory() or self.settings_store.last_directory())
        # Bilder zeigen die angezeigte Seite, ein PDF enthält alle Seiten des Projekts
        base_name = document.display_name
        if fmt != "PDF" and not document.current_page.is_main:
            base_name = f"{base_name} – {document.current_page.display_name}"
        suggestion = os.path.join(base_dir, _safe_filename(base_name) + extension)
        path, _ = QFileDialog.getSaveFileName(self, tr("Als {format} exportieren", format=fmt), suggestion,
                                              filters[fmt])
        if not path:
            return
        chosen = path
        path = export.ensure_extension(path, extension, also=(".jpeg",) if fmt == "JPG" else ())
        if path != chosen and os.path.exists(path):
            # Der Dialog hat nur den eingegebenen Namen geprüft, nicht den mit angehängter Endung
            answer = QMessageBox.question(
                self, tr("Als {format} exportieren", format=fmt),
                tr("„{name}“ ist bereits vorhanden.\nSoll die Datei ersetzt werden?", name=os.path.basename(path)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        exporter = {"PNG": export.export_png, "JPG": export.export_jpg, "SVG": export.export_svg,
                    "PDF": export.export_pdf}[fmt]
        source = _printable_scenes(document) if fmt == "PDF" else document.scene
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                exporter(source, path, options)
            finally:
                QApplication.restoreOverrideCursor()
        except export.ExportError as exc:
            self._error(tr("Export nicht möglich"), str(exc))
            return
        except Exception:
            log.exception("Export fehlgeschlagen")
            self._error(tr("Export nicht möglich"), tr("Beim Export ist ein unerwarteter Fehler aufgetreten."))
            return
        document.last_export_directory = os.path.dirname(os.path.abspath(path))
        self.settings_store.set_last_export_directory(path)
        self.statusBar().showMessage(tr("Exportiert: {path}", path=path), 5000)

    def _create_printer(self, document: DiagramDocument):
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(document.display_name)
        bounds = _printable_scenes(document)[0].diagram_bounds()
        if bounds.width() > bounds.height():
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        return printer

    def print_diagram(self) -> None:
        document = self.current_document()
        if document is None:
            return
        if document.is_empty():
            self._error(tr("Drucken nicht möglich"), tr("Das Diagramm ist leer."))
            return
        try:
            from PySide6.QtPrintSupport import QPrintDialog
        except ImportError:
            self._error(tr("Drucken nicht möglich"), tr("Die Druckunterstützung ist nicht verfügbar."))
            return
        printer = self._create_printer(document)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(tr("Drucken"))
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        try:
            export.print_scene(_printable_scenes(document), printer,
                               export.ExportOptions(theme_name="light", stamp=self._stamp_settings().text()))
        except export.ExportError as exc:
            self._error(tr("Drucken nicht möglich"), str(exc))

    def print_preview(self) -> None:
        document = self.current_document()
        if document is None:
            return
        if document.is_empty():
            self._error(tr("Druckvorschau nicht möglich"), tr("Das Diagramm ist leer."))
            return
        try:
            from PySide6.QtPrintSupport import QPrintPreviewDialog
        except ImportError:
            self._error(tr("Druckvorschau nicht möglich"), tr("Die Druckunterstützung ist nicht verfügbar."))
            return
        printer = self._create_printer(document)
        dialog = QPrintPreviewDialog(printer, self)
        dialog.setWindowTitle(tr("Druckvorschau"))
        dialog.resize(900, 700)
        options = export.ExportOptions(theme_name="light", stamp=self._stamp_settings().text())

        def paint(p):
            try:
                export.print_scene(_printable_scenes(document), p, options)
            except export.ExportError as exc:
                log.warning("Druckvorschau: %s", exc)

        dialog.paintRequested.connect(paint)
        dialog.exec()

    def register_file_type(self) -> None:
        if platforms.is_windows():
            question = tr("Sollen Dateien mit der Endung „{ext}“ für Ihr Benutzerkonto mit {app} geöffnet werden?\n\n"
                          "Die Zuordnung wird nur für den aktuellen Windows-Benutzer eingetragen. Eine bestehende "
                          "Zuordnung zu einem anderen Programm (z. B. dem PapDesigner) wird dabei ersetzt.",
                          ext=config.FILE_EXTENSION, app=config.APP_NAME)
        else:
            question = tr("Sollen Dateien mit der Endung „{ext}“ für Ihr Benutzerkonto mit {app} geöffnet werden?\n\n"
                          "Dazu kommen ein Eintrag im Startmenü und der Dateityp in Ihren Benutzerordner. Eine "
                          "bestehende Zuordnung zu einem anderen Programm wird dabei ersetzt.",
                          ext=config.FILE_EXTENSION, app=config.APP_NAME)
        answer = QMessageBox.question(self, tr("Dateityp registrieren"), question,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            file_association.register()
        except OSError as exc:
            self._error(tr("Registrierung fehlgeschlagen"),
                        tr("Die Dateizuordnung konnte nicht eingetragen werden.\n\n{error}", error=str(exc)))
            return
        QMessageBox.information(self, tr("Dateityp registriert"),
                                tr("„{ext}“-Dateien werden jetzt mit {app} geöffnet.",
                                   ext=config.FILE_EXTENSION, app=config.APP_NAME))

    def _error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    # ============================================================ Status
    def _show_scene_message(self, message: str) -> None:
        if message:
            self.statusBar().showMessage(message, 5000)

    def _schedule_status_update(self) -> None:
        if not hasattr(self, "_status_timer"):
            self._status_timer = QTimer(self)
            self._status_timer.setSingleShot(True)
            self._status_timer.setInterval(30)
            self._status_timer.timeout.connect(self._update_status)
            self._status_timer.timeout.connect(self._update_actions)
        self._status_timer.start()

    def _update_ui(self) -> None:
        has_document = self.tabs.count() > 0
        self.stack.setCurrentWidget(self.workspace if has_document else self.empty_state)
        self._sync_grid_actions()
        self._update_window_title()
        self._update_actions()
        self._update_status()
        self._sync_panels()

    def _update_actions(self) -> None:
        a = self.actions
        document = self.current_document()
        scene = document.scene if document is not None else None
        has_doc = scene is not None
        elements = scene.selected_elements() if has_doc else []
        connections = scene.selected_connections() if has_doc else []
        for name in ("save", "save_as", "save_all", "export_png", "export_jpg", "export_svg", "export_pdf", "print",
                     "print_preview", "properties", "close", "close_all", "select_all", "deselect", "zoom_in", "zoom_out", "zoom_reset",
                     "zoom_fit", "toggle_grid", "toggle_snap", "generate_code", "structogram", "auto_layout"):
            a[name].setEnabled(has_doc)
        a["undo"].setEnabled(has_doc and self.undo_group.canUndo())
        a["redo"].setEnabled(has_doc and self.undo_group.canRedo())
        self._update_undo_texts()
        a["cut"].setEnabled(bool(elements))
        a["copy"].setEnabled(bool(elements))
        a["copy_image"].setEnabled(has_doc and bool(scene.elements()))
        self.special_menu.setEnabled(has_doc and (scene.is_editing or scene.single_selected is not None))
        a["duplicate"].setEnabled(bool(elements))
        a["delete"].setEnabled(bool(elements or connections))
        a["paste"].setEnabled(has_doc and clipboard.can_paste())
        a["edit_text"].setEnabled(has_doc and (scene.single_selected is not None or len(connections) == 1))
        source = scene.single_selected if has_doc else None
        a["connect_to"].setEnabled(has_doc and can_connect(scene, source))
        for name in ALIGN_ACTIONS:
            a[name].setEnabled(len(elements) >= alignment.MIN_ITEMS[name])
        a[alignment.SNAP_TO_GRID].setEnabled(bool(elements))
        a["bring_front"].setEnabled(bool(elements))
        a["send_back"].setEnabled(bool(elements))
        single = scene.single_selected if has_doc else None
        a["toggle_loop_part"].setEnabled(single is not None and single.element_type is ElementType.LOOP)
        a["reset_routing"].setEnabled(any(c.has_manual_routing() for c in connections))
        a["add_bend"].setEnabled(len(connections) == 1)
        for name in ("jump_to_source", "jump_to_target"):
            a[name].setEnabled(len(connections) == 1 and not elements)
        a["new_subprogram"].setEnabled(has_doc)
        a["open_subprogram"].setEnabled(single is not None and single.element_type is ElementType.SUBPROGRAM)
        pages = len(document.pages) if has_doc else 0
        index = document.current_page_index if has_doc else -1
        a["next_page"].setEnabled(has_doc and index < pages - 1)
        a["previous_page"].setEnabled(has_doc and index > 0)
        a["go_back"].setEnabled(has_doc and document.can_go_back())
        a["go_forward"].setEnabled(has_doc and document.can_go_forward())
        a["extract_subprogram"].setEnabled(any(not item.is_comment for item in elements))
        for name in ("duplicate_page", "cut_page"):
            a[name].setEnabled(index > 0)
        a["copy_page"].setEnabled(has_doc)
        a["paste_page"].setEnabled(has_doc and subprograms.can_paste_page())
        a["move_page_left"].setEnabled(index > 1)
        a["move_page_right"].setEnabled(0 < index < pages - 1)
        self.palette.set_entries_enabled(True)
        self.zoom_button.setEnabled(has_doc)

    def _update_status(self) -> None:
        view = self.current_view()
        if view is None:
            for label in (self.count_label, self.selection_label, self.position_label, self.grid_label,
                          self.zoom_label):
                label.setText("")
            for label in (self.selection_label, self.position_label):
                label.hide()   # leere Felder nehmen Meldungen in der Statusleiste keinen Platz weg
            self.zoom_button.setText("100 %")
            return
        scene = view.document.scene
        settings = view.document.settings
        elements = len(scene.elements())
        connections = len(scene.connections())
        element_text = tr("1 Baustein") if elements == 1 else tr("{n} Bausteine", n=elements)
        connection_text = tr("1 Verbindung") if connections == 1 else tr("{n} Verbindungen", n=connections)
        self.count_label.setText(f"{element_text} · {connection_text}")
        selected = len(scene.selectedItems())
        self.selection_label.setText(tr("{n} ausgewählt", n=selected) if selected else "")
        self.selection_label.setVisible(bool(selected))
        size = settings.grid_size
        if settings.grid_visible and settings.snap_to_grid:
            grid_state = tr("Raster {size} · Einrasten an", size=size)
        elif settings.grid_visible:
            grid_state = tr("Raster {size} · Einrasten aus", size=size)
        elif settings.snap_to_grid:
            grid_state = tr("Raster {size} (aus) · Einrasten an", size=size)
        else:
            grid_state = tr("Raster {size} (aus) · Einrasten aus", size=size)
        self.grid_label.setText(grid_state)
        zoom_text = f"{round(view.zoom * 100)} %"
        self.zoom_label.setText(zoom_text)
        self.zoom_button.setText(zoom_text)

    def _update_position(self, pos: QPointF) -> None:
        self.position_label.setText(f"X {pos.x():.0f}  Y {pos.y():.0f}")
        self.position_label.show()


def _interactive_item_at(scene, pos: QPointF):
    for item in scene.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder):
        if isinstance(item, FlowItem) or isinstance(item, ConnectionItem):
            return item
        if isinstance(item, ConnectionLabel):
            return item.connection
    hit = scene._port_hit(pos)
    return hit[0] if hit else None


def _printable_scenes(document) -> list:
    """Seiten für Druck und PDF: alle, die etwas enthalten (Hauptprogramm zuerst)."""
    scenes = [scene for scene in document.scenes() if scene.elements()]
    return scenes or [document.scene]


def CLIPBOARD_BUSY() -> str:  # noqa: N802 - Text, der erst beim Anzeigen übersetzt wird
    return tr("Die Zwischenablage ist gerade von einem anderen Programm belegt. Bitte gleich noch einmal "
              "versuchen – die Seite bleibt unverändert.")


def _has_project_extension(path: str) -> bool:
    return path.lower().endswith(config.FILE_EXTENSION.lower())


def _path_key(path: str) -> str:
    """Vergleichsschlüssel eines Pfads: Kurznamen und Verknüpfungen aufgelöst, Groß/Klein wie im System."""
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(path))


def _originals_in_place(scene, payload) -> bool:
    """Liegen die ausgeschnittenen Bausteine wieder an ihrer Stelle (z. B. nach Rückgängig)?"""
    for data in payload.elements:
        item = scene.element(data.id)
        if item is not None and abs(item.pos().x() - data.x) < 0.5 and abs(item.pos().y() - data.y) < 0.5:
            return True
    return False


def _safe_filename(name: str) -> str:
    cleaned = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip().rstrip(".")
    # Unter Windows 10 sind diese Namen (auch mit Endung) Gerätenamen und lassen sich nicht speichern
    if cleaned.split(".")[0].strip().upper() in _RESERVED_NAMES:
        cleaned += "_"
    return cleaned or config.DEFAULT_PROJECT_NAME


_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
