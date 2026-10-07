"""Das Hauptfenster.

Aufbau: Menüleiste · kompakte Werkzeugleiste · Werkzeugpalette (rechts) ·
Arbeitsfläche mit Tabs (ein Projekt pro Tab) · Statusleiste.
"""

from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup, QKeySequence, QUndoGroup
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget,
                               QTabBar, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget)

from app import (alignment, clipboard, config, export, file_association, i18n, icons, restart, single_instance,
                 styles)
from app import theme as theme_module
from app.actions import ALIGN_ACTIONS, ActionRegistry, insert_action_name
from app.autosave import AutosaveManager
from app.canvas import DiagramView
from app.codegen.dialog import CodeDialog
from app.diagnostics.panel import DiagnosticsPanel
from app.dialogs.recovery import RecoveryDialog
from app.layout.auto_layout import apply_layout, plan_auto_layout
from app.nsd.dialog import StructogramDialog
from app.simulation.panel import SimulationPanel
from app.commands import ProjectPropertiesCommand
from app.connections.connection import ConnectionItem
from app.connections.label import ConnectionLabel
from app.dialogs.about import AboutDialog
from app.dialogs.export_options import ExportOptionsDialog
from app.dialogs.project_properties import ProjectPropertiesDialog
from app.dialogs.shortcuts import ShortcutsDialog
from app.document import DiagramDocument
from app.fileformat.project import ProjectFileError
from app.items.base_item import FlowItem
from app.model.element_types import FLOW_TERMINALS, PALETTE_ORDER, ElementType
from app.palette import ToolPalette
from app.i18n import tr
from app.settings_store import SettingsStore
from app.update_dialogs import UpdateController

log = logging.getLogger(__name__)

# Version des gespeicherten Fensterlayouts (bei neuen Docks erhöhen)
WINDOW_STATE_VERSION = 2


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
        hint = QLabel("Kein Projekt geöffnet.")
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_button = QPushButton("Neues Projekt")
        new_button.setDefault(True)
        new_button.clicked.connect(window.new_document)
        open_button = QPushButton("Projekt öffnen …")
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
        caption = QLabel("Zuletzt geöffnet")
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
    def __init__(self, enable_autosave: bool = False, autosave_directory: str | None = None):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setAcceptDrops(True)
        self.resize(1400, 880)

        self.settings_store = SettingsStore()
        self.undo_group = QUndoGroup(self)
        self.paste_tracker = clipboard.PasteTracker()
        self.export_options: dict[str, export.ExportOptions] = {}
        self.actions = ActionRegistry(self)
        self.autosave = AutosaveManager(autosave_directory, parent=self) if enable_autosave else None
        self.updates = UpdateController(self)
        self.instance_server = None  # lauscht auf Dateien weiterer Programmstarts (siehe app/single_instance.py)
        self._restart_files: list[str] | None = None  # gesetzt, solange ein Neustart (z. B. Sprachwechsel) läuft
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
        self._build_statusbar()
        self._connect_actions()
        self._sync_theme_actions()

        geometry = self.settings_store.window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings_store.window_state()
        if state is not None:
            self.restoreState(state, WINDOW_STATE_VERSION)

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
        self.empty_state = EmptyState(self)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tabs)
        self.stack.addWidget(self.empty_state)
        self.setCentralWidget(self.stack)

    def _build_menus(self) -> None:
        a = self.actions
        bar = self.menuBar()

        file_menu = bar.addMenu("&Datei")
        for name in ("new", "open"):
            file_menu.addAction(a[name])
        self.recent_menu = file_menu.addMenu("&Zuletzt geöffnet")
        file_menu.addSeparator()
        for name in ("save", "save_as", "auto_save"):
            file_menu.addAction(a[name])
        file_menu.addSeparator()
        export_menu = file_menu.addMenu(icons.icon("export"), "E&xportieren")
        for name in ("export_png", "export_svg", "export_pdf"):
            export_menu.addAction(a[name])
        self.export_menu = export_menu
        file_menu.addAction(a["print_preview"])
        file_menu.addAction(a["print"])
        file_menu.addSeparator()
        file_menu.addAction(a["properties"])
        file_menu.addSeparator()
        file_menu.addAction(a["close"])
        file_menu.addAction(a["quit"])

        edit_menu = bar.addMenu("&Bearbeiten")
        for name in ("undo", "redo", None, "cut", "copy", "paste", "duplicate", "delete", None,
                     "select_all", "deselect", None, "edit_text"):
            if name is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(a[name])

        view_menu = bar.addMenu("&Ansicht")
        for name in ("zoom_in", "zoom_out", "zoom_reset", "zoom_fit", None, "toggle_grid", "toggle_snap"):
            if name is None:
                view_menu.addSeparator()
            else:
                view_menu.addAction(a[name])
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Farbschema")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for name in ("theme_dark", "theme_light"):
            theme_group.addAction(a[name])
            theme_menu.addAction(a[name])
        self._build_language_menu(view_menu)
        view_menu.addSeparator()
        self.view_menu = view_menu

        insert_menu = bar.addMenu("&Einfügen")
        for element_type in PALETTE_ORDER:
            insert_menu.addAction(a[insert_action_name(element_type)])
        insert_menu.addSeparator()
        for element_type in FLOW_TERMINALS:
            insert_menu.addAction(a[insert_action_name(element_type)])

        arrange_menu = bar.addMenu("An&ordnen")
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
        arrange_menu.addAction(a["reset_routing"])
        arrange_menu.addSeparator()
        arrange_menu.addAction(a["auto_layout"])

        extras_menu = bar.addMenu("E&xtras")
        extras_menu.addAction(a["generate_code"])
        extras_menu.addAction(a["structogram"])
        extras_menu.addAction(a["auto_layout"])
        extras_menu.addSeparator()
        self.extras_menu = extras_menu  # Schreibtischtest/Hinweise folgen in _build_tool_docks

        help_menu = bar.addMenu("&Hilfe")
        help_menu.addAction(a["shortcuts"])
        if file_association.is_supported():
            help_menu.addAction(a["register_filetype"])
        help_menu.addAction(a["check_updates"])
        help_menu.addSeparator()
        help_menu.addAction(a["about"])

    def _build_language_menu(self, parent_menu: QMenu) -> None:
        """Untermenü „Sprache / Language“: die Systemsprache oder eine der vorhandenen Sprachen."""
        # Die Beschriftung ist bewusst zweisprachig und wird nicht übersetzt: So findet man sie in jeder Sprache.
        menu = parent_menu.addMenu("Sprache / Language")
        group = QActionGroup(self)
        group.setExclusive(True)
        self.language_actions: dict[str, object] = {}
        chosen = self.settings_store.language()
        entries = [(i18n.AUTOMATIC, tr("Automatisch (Systemsprache)"))]
        entries += [(code, i18n.language_name(code)) for code in i18n.available_languages()]
        for code, label in entries:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == chosen)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, c=code: self._on_language_chosen(c))
            self.language_actions[code] = action

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
        toolbar = QToolBar("Werkzeugleiste", self)
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        for name in ("new", "open", "save", None, "undo", "redo", None, "cut", "copy", "paste", "delete",
                     None, "zoom_out"):
            if name is None:
                toolbar.addSeparator()
            else:
                toolbar.addAction(a[name])
        self.zoom_button = QToolButton()
        self.zoom_button.setText("100 %")
        self.zoom_button.setToolTip("Zoom auf 100 % setzen (Strg+0)")
        self.zoom_button.setMinimumWidth(58)
        self.zoom_button.clicked.connect(lambda: self._with_view(lambda v: v.zoom_reset()))
        toolbar.addWidget(self.zoom_button)
        for name in ("zoom_in", "zoom_fit", None, "toggle_grid", "toggle_snap", None, "align_left_group"):
            if name is None:
                toolbar.addSeparator()
            elif name == "align_left_group":
                for align in (alignment.ALIGN_LEFT, alignment.ALIGN_CENTER_X, alignment.ALIGN_RIGHT,
                              alignment.ALIGN_TOP, alignment.ALIGN_CENTER_Y, alignment.ALIGN_BOTTOM,
                              alignment.DISTRIBUTE_H, alignment.DISTRIBUTE_V):
                    toolbar.addAction(a[align])
            else:
                toolbar.addAction(a[name])
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.toolbar = toolbar
        toggle = toolbar.toggleViewAction()
        toggle.setText("&Werkzeugleiste")
        self.view_menu.addAction(toggle)

    def _build_palette(self) -> None:
        self.palette = ToolPalette()
        self.palette.element_activated.connect(self.insert_element)
        dock = QDockWidget("Bausteine", self)
        dock.setObjectName("PaletteDock")
        dock.setWidget(self.palette)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.palette_dock = dock
        toggle = dock.toggleViewAction()
        toggle.setText("Werkzeug&palette")
        self.view_menu.addAction(toggle)

    def _build_tool_docks(self) -> None:
        """Schreibtischtest und Hinweise als Docks am unteren Rand."""
        self.simulation_panel = SimulationPanel()
        self.simulation_panel.element_focus_requested.connect(self._focus_element)
        self.simulation_dock = self._make_dock("Schreibtischtest", "SimulationDock", self.simulation_panel)
        self.diagnostics_panel = DiagnosticsPanel()
        self.diagnostics_panel.navigate_requested.connect(self._navigate_to)
        self.diagnostics_panel.issues_changed.connect(self._update_diagnostics_title)
        self.diagnostics_dock = self._make_dock("Hinweise", "DiagnosticsDock", self.diagnostics_panel)
        self.tabifyDockWidget(self.diagnostics_dock, self.simulation_dock)
        self.diagnostics_dock.raise_()
        for dock, text, shortcut in ((self.simulation_dock, "&Schreibtischtest", "F9"),
                                     (self.diagnostics_dock, "&Hinweise", "Ctrl+Shift+H")):
            toggle = dock.toggleViewAction()
            toggle.setText(text)
            toggle.setShortcut(QKeySequence(shortcut))
            self.extras_menu.addAction(toggle)
            self.view_menu.addAction(toggle)
        self.simulation_dock.visibilityChanged.connect(self._on_simulation_visibility)
        # visibilityChanged meldet auch, ob der Reiter vorne liegt (tabifizierte Docks)
        self._diagnostics_on_top = False
        self.diagnostics_dock.visibilityChanged.connect(self._on_diagnostics_visibility)
        # Standardmäßig ausgeblendet: die Arbeitsfläche behält den meisten Platz.
        self.simulation_dock.hide()
        self.diagnostics_dock.hide()

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
        self.diagnostics_dock.setWindowTitle(f"Hinweise ({total})" if total else "Hinweise")
        if not hasattr(self, "issues_button"):
            return
        if not total:
            self.issues_button.setText("Keine Hinweise")
            self.issues_button.setIcon(icons.icon("info"))
        else:
            parts = []
            if warnings:
                parts.append(f"{warnings} Warnung" + ("en" if warnings != 1 else ""))
            if infos:
                parts.append(f"{infos} Hinweis" + ("e" if infos != 1 else ""))
            self.issues_button.setText(" · ".join(parts))
            self.issues_button.setIcon(icons.icon("warning" if warnings else "info"))

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
        item = view.document.scene.element(element_id) if view is not None else None
        if item is not None:
            view.ensureVisible(item.scene_rect(), 60, 60)

    def _navigate_to(self, element_ids: list, connection_ids: list) -> None:
        view = self.current_view()
        if view is None:
            return
        scene = view.document.scene
        items = [scene.element(eid) for eid in element_ids] + [scene.connection(cid) for cid in connection_ids]
        items = [item for item in items if item is not None]
        if not items:
            return
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
        self.issues_button.setIconSize(QSize(14, 14))
        self.issues_button.setAutoRaise(True)
        self.issues_button.setToolTip("Hinweisliste ein-/ausblenden (Strg+Umschalt+H)")
        self.issues_button.clicked.connect(self._toggle_diagnostics)
        status.addPermanentWidget(self.issues_button)
        for label in (self.count_label, self.selection_label, self.position_label, self.grid_label,
                      self.zoom_label):
            status.addPermanentWidget(label)
        self._update_diagnostics_title(0, 0)

    def _connect_actions(self) -> None:
        a = self.actions
        a["new"].triggered.connect(self.new_document)
        a["open"].triggered.connect(self.open_file_dialog)
        a["save"].triggered.connect(lambda: self._with_document(self.save_document))
        a["save_as"].triggered.connect(lambda: self._with_document(self.save_document_as))
        a["export_png"].triggered.connect(lambda: self.export_diagram("PNG"))
        a["export_svg"].triggered.connect(lambda: self.export_diagram("SVG"))
        a["export_pdf"].triggered.connect(lambda: self.export_diagram("PDF"))
        a["print"].triggered.connect(self.print_diagram)
        a["print_preview"].triggered.connect(self.print_preview)
        a["properties"].triggered.connect(self.edit_properties)
        a["close"].triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))
        a["quit"].triggered.connect(self.close)

        a["undo"].triggered.connect(self._undo)
        a["redo"].triggered.connect(self._redo)
        self.undo_group.canUndoChanged.connect(lambda _: self._update_actions())
        self.undo_group.canRedoChanged.connect(lambda _: self._update_actions())
        self.undo_group.undoTextChanged.connect(lambda _: self._update_undo_texts())
        self.undo_group.redoTextChanged.connect(lambda _: self._update_undo_texts())
        a["cut"].triggered.connect(self.cut)
        a["copy"].triggered.connect(self.copy)
        a["paste"].triggered.connect(lambda: self.paste())
        a["duplicate"].triggered.connect(self.duplicate)
        a["delete"].triggered.connect(lambda: self._with_scene(lambda s: s.delete_selection()))
        a["select_all"].triggered.connect(lambda: self._with_scene(lambda s: s.select_all()))
        a["deselect"].triggered.connect(lambda: self._with_scene(lambda s: s.handle_escape()))
        a["edit_text"].triggered.connect(self.edit_selected_text)

        a["zoom_in"].triggered.connect(lambda: self._with_view(lambda v: v.zoom_in()))
        a["zoom_out"].triggered.connect(lambda: self._with_view(lambda v: v.zoom_out()))
        a["zoom_reset"].triggered.connect(lambda: self._with_view(lambda v: v.zoom_reset()))
        a["zoom_fit"].triggered.connect(lambda: self._with_view(lambda v: v.fit_diagram()))
        a["toggle_grid"].toggled.connect(self._set_grid_visible)
        a["toggle_snap"].toggled.connect(self._set_snap)

        for element_type in PALETTE_ORDER + FLOW_TERMINALS:
            a[insert_action_name(element_type)].triggered.connect(
                lambda _=False, t=element_type: self.insert_element(t))

        for name in ALIGN_ACTIONS + [alignment.SNAP_TO_GRID]:
            a[name].triggered.connect(lambda _=False, mode=name: self.align(mode))
        a["bring_front"].triggered.connect(lambda: self._with_scene(lambda s: s.bring_to_front()))
        a["send_back"].triggered.connect(lambda: self._with_scene(lambda s: s.send_to_back()))
        a["toggle_loop_part"].triggered.connect(self.toggle_loop_part)
        a["reset_routing"].triggered.connect(self.reset_routing)

        a["generate_code"].triggered.connect(self.show_code_dialog)
        a["structogram"].triggered.connect(self.show_structogram)
        a["auto_layout"].triggered.connect(self.auto_layout)
        a["theme_dark"].triggered.connect(lambda: self.set_theme("dark"))
        a["theme_light"].triggered.connect(lambda: self.set_theme("light"))

        a["shortcuts"].triggered.connect(lambda: ShortcutsDialog(self).exec())
        a["register_filetype"].triggered.connect(self.register_file_type)
        a["about"].triggered.connect(lambda: AboutDialog(self).exec())
        a["check_updates"].triggered.connect(lambda: self.updates.check(manual=True))
        a["auto_save"].setChecked(self._auto_save_enabled)
        a["auto_save"].triggered.connect(self._on_auto_save_triggered)

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
        index = self.tabs.addTab(view, document.display_name)
        close_button = QToolButton()
        close_button.setObjectName("TabCloseButton")
        close_button.setIcon(icons.icon("close"))
        close_button.setIconSize(QSize(12, 12))
        close_button.setAutoRaise(True)
        close_button.setToolTip("Projekt schließen")
        close_button.clicked.connect(lambda _=False, v=view: self.close_tab(self.tabs.indexOf(v)))
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close_button)
        self.undo_group.addStack(document.undo_stack)
        if self.autosave is not None:
            self.autosave.register(document)
        document.title_changed.connect(lambda d=document: self._update_document_title(d))
        document.modified_changed.connect(lambda _m, d=document: self._update_document_title(d))
        document.undo_stack.indexChanged.connect(lambda _i, d=document: self._schedule_auto_save(d))
        document.settings_changed.connect(self._update_status)
        scene = document.scene
        scene.selection_state_changed.connect(self._update_actions)
        scene.selection_state_changed.connect(self._update_status)
        scene.content_changed.connect(self._schedule_status_update)
        scene.editing_changed.connect(lambda _e: self._update_actions())
        scene.status_message.connect(self._show_scene_message)
        view.zoom_changed.connect(lambda _z: self._update_status())
        view.cursor_scene_pos_changed.connect(self._update_position)
        view.context_menu_requested.connect(self.show_context_menu)
        self.tabs.setCurrentIndex(index)
        self._update_document_title(document)
        self._update_ui()
        view.setFocus()
        return view

    def _on_tab_changed(self, index: int) -> None:
        document = self.current_document()
        self.undo_group.setActiveStack(document.undo_stack if document is not None else None)
        self._update_ui()

    def _sync_panels(self) -> None:
        document = self.current_document()
        if hasattr(self, "simulation_panel"):
            self.simulation_panel.set_document(document)
            self.diagnostics_panel.set_document(document)

    def _update_document_title(self, document: DiagramDocument) -> None:
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, DiagramView) and view.document is document:
                title = document.display_name + (" *" if document.is_modified else "")
                self.tabs.setTabText(i, title)
                self.tabs.setTabToolTip(i, document.file_path or "Noch nicht gespeichert")
        self._update_window_title()

    def _update_window_title(self) -> None:
        document = self.current_document()
        if document is None:
            self.setWindowTitle(config.APP_NAME)
            self.setWindowModified(False)
            return
        self.setWindowTitle(f"{document.display_name}[*] – {config.APP_NAME}")
        self.setWindowModified(document.is_modified)

    def close_tab(self, index: int) -> bool:
        if index < 0 or index >= self.tabs.count():
            return False
        view = self.tabs.widget(index)
        if not isinstance(view, DiagramView):
            return False
        self.tabs.setCurrentIndex(index)
        if not self.maybe_save(view.document):
            return False
        document = view.document
        document.scene.cancel_edit()
        if self.simulation_panel.simulator is not None and self.current_document() is document:
            self.simulation_panel.stop(silent=True)
        self.simulation_panel.set_document(None)
        self.diagnostics_panel.set_document(None)
        if self.autosave is not None:
            self.autosave.unregister(document)
        self._auto_save_pending.discard(document)
        self.undo_group.removeStack(document.undo_stack)
        self.tabs.removeTab(index)
        view.deleteLater()
        document.deleteLater()
        self._update_ui()
        return True

    def _find_document_by_path(self, path: str) -> int:
        target = os.path.normcase(os.path.abspath(path))
        for i, view in enumerate(self.views()):
            if view.document.file_path and os.path.normcase(view.document.file_path) == target:
                return i
        return -1

    # ============================================================ Datei
    def new_document(self) -> None:
        self.add_document(DiagramDocument())

    def open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", self.settings_store.last_directory(),
                                              config.FILE_DIALOG_FILTER)
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> bool:
        path = os.path.abspath(path)
        if not _has_project_extension(path):
            # .pap ist das einzige Projektformat – auf jedem Weg (Dialog, Befehlszeile, Zuletzt geöffnet)
            self._error("Datei kann nicht geöffnet werden",
                        f"„{os.path.basename(path)}“ ist kein Programmablaufplan im Format "
                        f"{config.FILE_EXTENSION}.\n\nEs können nur {config.FILE_EXTENSION}-Dateien geöffnet werden.")
            return False
        existing = self._find_document_by_path(path)
        if existing >= 0:
            self.tabs.setCurrentIndex(existing)
            return True
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                document = DiagramDocument.open_file(path)
            finally:
                QApplication.restoreOverrideCursor()
        except ProjectFileError as exc:
            log.warning("Datei konnte nicht geöffnet werden: %s (%s)", path, exc.details)
            if not os.path.exists(path):
                self.settings_store.remove_recent_file(path)
                self._refresh_recent_menu()
            self._error("Datei kann nicht geöffnet werden", exc.message)
            return False
        except Exception as exc:  # pragma: no cover - Absicherung
            log.exception("Unerwarteter Fehler beim Öffnen von %s", path)
            self._error("Datei kann nicht geöffnet werden",
                        f"Die Datei ist beschädigt oder inkompatibel.\n\n({type(exc).__name__})")
            return False

        # Ein unberührtes, leeres neues Projekt wird ersetzt
        current = self.current_document()
        replace_index = -1
        if current is not None and current.file_path is None and not current.is_modified \
                and not current.scene.elements():
            replace_index = self.tabs.currentIndex()
        view = self.add_document(document)
        if replace_index >= 0:
            self.close_tab(replace_index)
            self.tabs.setCurrentIndex(self._find_document_by_path(path))
        self.settings_store.add_recent_file(path)
        self.settings_store.set_last_directory(path)
        self._refresh_recent_menu()
        if document.load_warnings:
            shown = document.load_warnings[:10]
            more = len(document.load_warnings) - len(shown)
            text = "\n".join(f"• {w}" for w in shown)
            if more > 0:
                text += f"\n… und {more} weitere Hinweise."
            QMessageBox.information(self, "Datei wurde mit Korrekturen geöffnet",
                                    "Die Datei enthielt fehlerhafte Angaben, die automatisch korrigiert "
                                    f"wurden:\n\n{text}")
        if document.native_file:
            self.statusBar().showMessage(f"„{document.display_name}“ geöffnet.", 4000)
        else:
            # Datei ohne gespeicherte Anordnung (z. B. aus dem PapDesigner)
            view.fit_diagram()
            self.statusBar().showMessage(f"„{document.display_name}“ geöffnet – die Anordnung wurde aus "
                                         "dem Raster der Datei übernommen.", 8000)
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
        if not document.native_file:
            # Die Datei stammt aus einem anderen Programm: nicht stillschweigend ersetzen
            choice = self._ask_foreign_overwrite(document)
            if choice == "save_as":
                return self.save_document_as(document)
            if choice != "overwrite":
                return False
        return self._save_to(document, document.file_path)

    def _ask_foreign_overwrite(self, document: DiagramDocument) -> str:
        """Erstes Speichern einer Datei, die nicht mit diesem Programm geschrieben wurde.

        Ergebnis: ``"overwrite"``, ``"save_as"`` oder ``"cancel"``.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(config.APP_NAME)
        box.setText(f"„{os.path.basename(document.file_path)}“ wurde mit einem anderen Programm "
                    "erstellt (z. B. dem PapDesigner).")
        box.setInformativeText("Beim Speichern wird die Datei neu geschrieben: Die genaue Anordnung kommt "
                               "hinzu, mehrere Diagramme der Datei werden zu einem Plan zusammengefasst.\n\n"
                               "Soll die Datei überschrieben werden?")
        overwrite = box.addButton("Überschreiben", QMessageBox.ButtonRole.AcceptRole)
        save_as = box.addButton("Speichern unter …", QMessageBox.ButtonRole.ActionRole)
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_as)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite:
            return "overwrite"
        return "save_as" if clicked is save_as else "cancel"

    def save_document_as(self, document: DiagramDocument) -> bool:
        document.scene.commit_edit()
        if document.file_path:
            suggestion = export.ensure_extension(document.file_path, config.FILE_EXTENSION)
        else:
            name = export.ensure_extension(_safe_filename(document.display_name), config.FILE_EXTENSION)
            suggestion = os.path.join(self.settings_store.last_directory(), name)
        chosen, _ = QFileDialog.getSaveFileName(self, "Speichern unter", suggestion, config.FILE_DIALOG_FILTER)
        if not chosen:
            return False
        path = export.ensure_extension(chosen, config.FILE_EXTENSION)
        if path != chosen and os.path.exists(path):
            # Der Dialog hat nur den eingegebenen Namen geprüft, nicht den mit Endung
            answer = QMessageBox.question(
                self, "Speichern unter",
                f"„{os.path.basename(path)}“ ist bereits vorhanden.\nSoll die Datei ersetzt werden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        other = self._find_document_by_path(path)
        if other >= 0 and self.views()[other].document is not document:
            self._error("Speichern nicht möglich",
                        "Diese Datei ist bereits in einem anderen Tab geöffnet. "
                        "Bitte schließen Sie sie zuerst oder wählen Sie einen anderen Namen.")
            return False
        return self._save_to(document, path)

    def _save_to(self, document: DiagramDocument, path: str, automatic: bool = False) -> bool:
        """Speichert das Projekt. ``automatic``: ohne Meldungsfenster (automatisches Speichern)."""
        try:
            document.save(path)
        except ProjectFileError as exc:
            log.warning("Speichern fehlgeschlagen: %s (%s)", path, exc.details)
            if automatic:
                self.statusBar().showMessage(f"Automatisches Speichern nicht möglich: {exc.message}", 8000)
            else:
                self._error("Speichern nicht möglich", exc.message)
            return False
        except Exception:  # pragma: no cover - Absicherung
            log.exception("Unerwarteter Fehler beim Speichern")
            if not automatic:
                self._error("Speichern nicht möglich", "Beim Speichern ist ein unerwarteter Fehler aufgetreten.")
            return False
        if not automatic:
            self.settings_store.add_recent_file(path)
            self.settings_store.set_last_directory(path)
            self._refresh_recent_menu()
        self._update_document_title(document)
        if self.autosave is not None:
            self.autosave.document_saved(document)
        self.statusBar().showMessage("Automatisch gespeichert." if automatic else f"Gespeichert: {path}",
                                     2000 if automatic else 4000)
        return True

    # ------------------------------------------------ Automatisches Speichern
    def set_auto_save(self, enabled: bool) -> None:
        """Schaltet das automatische Speichern für dieses Fenster ein oder aus."""
        self._auto_save_enabled = bool(enabled)
        self.actions["auto_save"].setChecked(self._auto_save_enabled)
        if not self._auto_save_enabled:
            self._auto_save_timer.stop()
            self._auto_save_pending.clear()
            self._auto_save_since = None
            return
        for view in self.views():
            self._schedule_auto_save(view.document)

    def _on_auto_save_triggered(self, checked: bool) -> None:
        self.settings_store.set_auto_save(checked)
        self.set_auto_save(checked)
        self.statusBar().showMessage("Automatisches Speichern ist eingeschaltet." if checked
                                     else "Automatisches Speichern ist ausgeschaltet.", 4000)

    def _auto_save_applies(self, document: DiagramDocument) -> bool:
        """Nur Projekte, die schon einmal mit diesem Programm als .pap gespeichert wurden."""
        return bool(self._auto_save_enabled and document.file_path and document.native_file
                    and _has_project_extension(document.file_path))

    def _schedule_auto_save(self, document: DiagramDocument) -> None:
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
        document.scene.commit_edit()
        if not document.is_modified:
            return True
        if self._auto_save_applies(document) and self._save_to(document, document.file_path, automatic=True):
            return True  # automatisches Speichern: keine Nachfrage nötig
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(config.APP_NAME)
        box.setText(f"Das Projekt „{document.display_name}“ wurde geändert.")
        box.setInformativeText("Möchten Sie die Änderungen speichern?")
        save = box.addButton("Speichern", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Verwerfen", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return self.save_document(document)
        return clicked is discard

    def closeEvent(self, event) -> None:
        # Offene Texteingaben zuerst übernehmen – sonst gälte ein Projekt als
        # unverändert und der eingegebene Text ginge beim Beenden verloren.
        for view in self.views():
            view.document.scene.prepare_for_command()
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, DiagramView) and view.document.is_modified:
                self.tabs.setCurrentIndex(i)
                if not self.maybe_save(view.document):
                    self._restart_files = None  # Schließen abgebrochen: auch kein Neustart
                    event.ignore()
                    return
        self.settings_store.save_window(self.saveGeometry(), self.saveState(WINDOW_STATE_VERSION))
        self.simulation_panel.stop(silent=True)
        if self.autosave is not None:
            self.autosave.shutdown()
        if self.instance_server is not None:
            # Das Fenster schließt sich: weitere Programmstarts sollen nicht mehr hierher übergeben, sondern selbst
            # das erste Programm werden.
            self.instance_server.close()
        if self._restart_files is not None:
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
                    self._error("Wiederherstellung nicht möglich", exc.message)
                    self.autosave.discard(entry)
                    continue
                self.add_document(document)
                restored += 1
            else:
                self.autosave.discard(entry)
        if restored:
            self.statusBar().showMessage(f"{restored} Projekt(e) wiederhergestellt – bitte speichern.", 8000)
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
            self._error("Anordnen nicht möglich", "Beim automatischen Anordnen ist ein Fehler aufgetreten.")
            return
        if apply_layout(scene, plan):
            view.fit_diagram()
            self.statusBar().showMessage("Plan automatisch angeordnet (Rückgängig mit Strg+Z).", 5000)
        else:
            self.statusBar().showMessage("Der Plan ist bereits angeordnet.", 4000)

    def _sync_theme_actions(self) -> None:
        name = theme_module.theme_name_of(styles.current_theme())
        self.actions["theme_dark"].setChecked(name == "dark")
        self.actions["theme_light"].setChecked(name == "light")

    def set_theme(self, name: str) -> None:
        """Farbschema zur Laufzeit umschalten (wird gespeichert)."""
        app = QApplication.instance()
        theme = theme_module.apply_ui_theme(app, name)
        theme_module.save_theme_name(name)
        for view in self.views():
            scene = view.document.scene
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
        self.diagnostics_panel.refresh()
        self._sync_theme_actions()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self.settings_store.recent_files()
        if not files:
            empty = self.recent_menu.addAction("(keine)")
            empty.setEnabled(False)
        for index, path in enumerate(files, start=1):
            action = self.recent_menu.addAction(f"&{index}  {os.path.basename(path)}")
            action.setStatusTip(path)
            action.setToolTip(path)
            action.triggered.connect(lambda _=False, p=path: self.open_file(p))
        if files:
            self.recent_menu.addSeparator()
            clear = self.recent_menu.addAction("Liste leeren")
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
        scene = self.current_scene()
        if scene is not None:
            scene.prepare_for_command()
        self.undo_group.undo()

    def _redo(self) -> None:
        scene = self.current_scene()
        if scene is not None:
            scene.prepare_for_command()
        self.undo_group.redo()

    def _update_undo_texts(self) -> None:
        undo_text = self.undo_group.undoText()
        redo_text = self.undo_group.redoText()
        self.actions["undo"].setText(f"&Rückgängig: {undo_text}" if undo_text else "&Rückgängig")
        self.actions["redo"].setText(f"&Wiederholen: {redo_text}" if redo_text else "&Wiederholen")

    def copy(self) -> None:
        scene = self.current_scene()
        if scene is not None and clipboard.copy_selection(scene):
            self.paste_tracker.reset()
            self.statusBar().showMessage("In die Zwischenablage kopiert.", 2500)

    def cut(self) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        payload = clipboard.selection_payload(scene)
        if payload is not None and clipboard.cut_selection(scene):
            self.paste_tracker.prime_after_cut(payload)

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
                                      text="Duplizieren")
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

    def insert_element(self, element_type: ElementType) -> None:
        view = self.current_view()
        if view is None:
            self.new_document()
            view = self.current_view()
        element_id = view.document.scene.insert_element_smart(ElementType(element_type), view.visible_center())
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
        scene.apply_moves(moves, alignment.LABELS.get(mode, "Ausrichten"))

    def toggle_loop_part(self) -> None:
        scene = self.current_scene()
        if scene is not None and scene.single_selected is not None:
            scene.toggle_loop_part(scene.single_selected)

    def reset_routing(self) -> None:
        scene = self.current_scene()
        if scene is None:
            return
        for conn in scene.selected_connections():
            scene.reset_routing(conn)

    def _set_grid_visible(self, visible: bool) -> None:
        document = self.current_document()
        if document is not None:
            document.set_grid_visible(visible)
        self._update_status()

    def _set_snap(self, enabled: bool) -> None:
        document = self.current_document()
        if document is not None:
            document.set_snap_to_grid(enabled)
        self._update_status()

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
            menu.addSeparator()
            for name in ("cut", "copy", "duplicate", "delete"):
                menu.addAction(a[name])
            menu.addSeparator()
            menu.addAction(a["bring_front"])
            menu.addAction(a["send_back"])
            if item.element_type is ElementType.LOOP:
                menu.addSeparator()
                is_end = item.data.properties.get("part") == "end"
                toggle = menu.addAction("In Schleifenbeginn umwandeln" if is_end else "In Schleifenende umwandeln")
                toggle.triggered.connect(lambda: scene.toggle_loop_part(item))
            menu.addSeparator()
            if len(scene.selected_elements()) >= 2:
                align_menu = menu.addMenu("Ausrichten")
                for name in ALIGN_ACTIONS:
                    align_menu.addAction(a[name])
            menu.addAction(a[alignment.SNAP_TO_GRID])
        elif isinstance(item, ConnectionItem):
            label = menu.addAction("Beschriftung bearbeiten")
            label.setShortcut(QKeySequence("F2"))
            label.setEnabled(not item.is_annotation)
            label.triggered.connect(lambda: scene.begin_label_edit(item))
            reset = menu.addAction("Linienführung zurücksetzen")
            reset.setEnabled(item.has_manual_routing())
            reset.triggered.connect(lambda: scene.reset_routing(item))
            menu.addSeparator()
            menu.addAction(a["delete"])
        else:
            new_menu = menu.addMenu(icons.icon("new"), "Neu")
            for element_type in PALETTE_ORDER + FLOW_TERMINALS:
                action = new_menu.addAction(icons.element_icon(element_type), a[insert_action_name(element_type)].text())
                action.triggered.connect(lambda _=False, t=element_type, p=QPointF(scene_pos):
                                         self._insert_at(view, t, p))
                if element_type is PALETTE_ORDER[-1]:
                    new_menu.addSeparator()
            paste = menu.addAction(icons.icon("paste"), "Einfügen")
            paste.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
            paste.setEnabled(clipboard.can_paste())
            paste.triggered.connect(lambda _=False, p=QPointF(scene_pos): self.paste(at=p))
            menu.addAction(a["select_all"])
            menu.addSeparator()
            grid_menu = menu.addMenu(icons.icon("grid"), "Raster")
            grid_menu.addAction(a["toggle_grid"])
            grid_menu.addAction(a["toggle_snap"])
            view_menu = menu.addMenu(icons.icon("zoom_fit"), "Ansicht")
            for name in ("zoom_in", "zoom_out", "zoom_reset", "zoom_fit"):
                view_menu.addAction(a[name])
        menu.exec(global_pos)

    def _insert_at(self, view: DiagramView, element_type: ElementType, pos: QPointF) -> None:
        element_id = view.document.scene.insert_element(element_type, pos)
        self._reveal([element_id] if element_id else [])

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

    def _export_options(self, fmt: str) -> export.ExportOptions | None:
        current = self.export_options.get(fmt, export.ExportOptions())
        dialog = ExportOptionsDialog(fmt, current, self)
        if dialog.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return None
        options = dialog.options()
        self.export_options[fmt] = options
        return options

    def export_diagram(self, fmt: str) -> None:
        document = self.current_document()
        if document is None:
            return
        if not document.scene.elements():
            self._error("Export nicht möglich", "Das Diagramm ist leer – es gibt nichts zu exportieren.")
            return
        options = self._export_options(fmt)
        if options is None:
            return
        extension = {"PNG": ".png", "SVG": ".svg", "PDF": ".pdf"}[fmt]
        filters = {"PNG": "PNG-Bild (*.png)", "SVG": "SVG-Grafik (*.svg)", "PDF": "PDF-Dokument (*.pdf)"}
        base_dir = os.path.dirname(document.file_path) if document.file_path else self.settings_store.last_directory()
        suggestion = os.path.join(base_dir, _safe_filename(document.display_name) + extension)
        path, _ = QFileDialog.getSaveFileName(self, f"Als {fmt} exportieren", suggestion, filters[fmt])
        if not path:
            return
        path = export.ensure_extension(path, extension)
        exporter = {"PNG": export.export_png, "SVG": export.export_svg, "PDF": export.export_pdf}[fmt]
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                exporter(document.scene, path, options)
            finally:
                QApplication.restoreOverrideCursor()
        except export.ExportError as exc:
            self._error("Export nicht möglich", str(exc))
            return
        except Exception:
            log.exception("Export fehlgeschlagen")
            self._error("Export nicht möglich", "Beim Export ist ein unerwarteter Fehler aufgetreten.")
            return
        self.statusBar().showMessage(f"Exportiert: {path}", 5000)

    def _create_printer(self, document: DiagramDocument):
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(document.display_name)
        bounds = document.scene.diagram_bounds()
        if bounds.width() > bounds.height():
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        return printer

    def print_diagram(self) -> None:
        document = self.current_document()
        if document is None:
            return
        if not document.scene.elements():
            self._error("Drucken nicht möglich", "Das Diagramm ist leer.")
            return
        try:
            from PySide6.QtPrintSupport import QPrintDialog
        except ImportError:
            self._error("Drucken nicht möglich", "Die Druckunterstützung ist nicht verfügbar.")
            return
        printer = self._create_printer(document)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Drucken")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        try:
            export.print_scene(document.scene, printer, export.ExportOptions(theme_name="light"))
        except export.ExportError as exc:
            self._error("Drucken nicht möglich", str(exc))

    def print_preview(self) -> None:
        document = self.current_document()
        if document is None:
            return
        if not document.scene.elements():
            self._error("Druckvorschau nicht möglich", "Das Diagramm ist leer.")
            return
        try:
            from PySide6.QtPrintSupport import QPrintPreviewDialog
        except ImportError:
            self._error("Druckvorschau nicht möglich", "Die Druckunterstützung ist nicht verfügbar.")
            return
        printer = self._create_printer(document)
        dialog = QPrintPreviewDialog(printer, self)
        dialog.setWindowTitle("Druckvorschau")
        dialog.resize(900, 700)
        options = export.ExportOptions(theme_name="light")

        def paint(p):
            try:
                export.print_scene(document.scene, p, options)
            except export.ExportError as exc:
                log.warning("Druckvorschau: %s", exc)

        dialog.paintRequested.connect(paint)
        dialog.exec()

    def register_file_type(self) -> None:
        answer = QMessageBox.question(
            self, "Dateityp registrieren",
            f"Sollen Dateien mit der Endung „{config.FILE_EXTENSION}“ für Ihr Benutzerkonto mit "
            f"{config.APP_NAME} geöffnet werden?\n\n"
            "Die Zuordnung wird nur für den aktuellen Windows-Benutzer eingetragen. Eine bestehende "
            "Zuordnung zu einem anderen Programm (z. B. dem PapDesigner) wird dabei ersetzt.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            file_association.register()
        except OSError as exc:
            self._error("Registrierung fehlgeschlagen", f"Die Dateizuordnung konnte nicht eingetragen werden.\n\n{exc}")
            return
        QMessageBox.information(self, "Dateityp registriert",
                                f"„{config.FILE_EXTENSION}“-Dateien werden jetzt mit {config.APP_NAME} geöffnet.")

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
        self.stack.setCurrentWidget(self.tabs if has_document else self.empty_state)
        document = self.current_document()
        for name, attr in (("toggle_grid", "grid_visible"), ("toggle_snap", "snap_to_grid")):
            action = self.actions[name]
            action.blockSignals(True)
            action.setChecked(bool(getattr(document.settings, attr)) if document else True)
            action.blockSignals(False)
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
        for name in ("save", "save_as", "export_png", "export_svg", "export_pdf", "print", "print_preview",
                     "properties", "close", "select_all", "deselect", "zoom_in", "zoom_out", "zoom_reset",
                     "zoom_fit", "toggle_grid", "toggle_snap", "generate_code", "structogram", "auto_layout"):
            a[name].setEnabled(has_doc)
        a["undo"].setEnabled(has_doc and self.undo_group.canUndo())
        a["redo"].setEnabled(has_doc and self.undo_group.canRedo())
        self._update_undo_texts()
        a["cut"].setEnabled(bool(elements))
        a["copy"].setEnabled(bool(elements))
        a["duplicate"].setEnabled(bool(elements))
        a["delete"].setEnabled(bool(elements or connections))
        a["paste"].setEnabled(has_doc and clipboard.can_paste())
        a["edit_text"].setEnabled(has_doc and (scene.single_selected is not None or len(connections) == 1))
        for name in ALIGN_ACTIONS:
            a[name].setEnabled(len(elements) >= alignment.MIN_ITEMS[name])
        a[alignment.SNAP_TO_GRID].setEnabled(bool(elements))
        a["bring_front"].setEnabled(bool(elements))
        a["send_back"].setEnabled(bool(elements))
        single = scene.single_selected if has_doc else None
        a["toggle_loop_part"].setEnabled(single is not None and single.element_type is ElementType.LOOP)
        a["reset_routing"].setEnabled(any(c.has_manual_routing() for c in connections))
        self.palette.set_entries_enabled(True)
        self.zoom_button.setEnabled(has_doc)

    def _update_status(self) -> None:
        view = self.current_view()
        if view is None:
            for label in (self.count_label, self.selection_label, self.position_label, self.grid_label,
                          self.zoom_label):
                label.setText("")
            self.zoom_button.setText("100 %")
            return
        scene = view.document.scene
        settings = view.document.settings
        elements = len(scene.elements())
        connections = len(scene.connections())
        self.count_label.setText(f"{elements} Bausteine · {connections} Verbindungen")
        selected = len(scene.selectedItems())
        self.selection_label.setText(f"{selected} ausgewählt" if selected else "")
        grid_state = f"Raster {settings.grid_size}" + ("" if settings.grid_visible else " (aus)")
        grid_state += " · Einrasten " + ("an" if settings.snap_to_grid else "aus")
        self.grid_label.setText(grid_state)
        zoom_text = f"{round(view.zoom * 100)} %"
        self.zoom_label.setText(zoom_text)
        self.zoom_button.setText(zoom_text)

    def _update_position(self, pos: QPointF) -> None:
        self.position_label.setText(f"X {pos.x():.0f}  Y {pos.y():.0f}")


def _interactive_item_at(scene, pos: QPointF):
    for item in scene.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder):
        if isinstance(item, FlowItem) or isinstance(item, ConnectionItem):
            return item
        if isinstance(item, ConnectionLabel):
            return item.connection
    hit = scene._port_hit(pos)
    return hit[0] if hit else None


def _has_project_extension(path: str) -> bool:
    return path.lower().endswith(config.FILE_EXTENSION.lower())


def _safe_filename(name: str) -> str:
    cleaned = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip().rstrip(".")
    return cleaned or config.DEFAULT_PROJECT_NAME
