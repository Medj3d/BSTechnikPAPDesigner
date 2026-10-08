"""Dock-Panel „Schreibtischtest“.

Führt den Plan Schritt für Schritt aus, hebt den aktuellen Baustein hervor
und zeigt Variablen, Ausgaben und die Schreibtischtest-Tabelle.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGraphicsItem, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from app import icons, styles
from app.analysis.graph import FlowGraph
from app.i18n import tr
from app.items.base_item import LAYER_OVERLAY
from app.labels import no_label, yes_label
from app.model.element_types import ElementType, default_text_for
from app.simulation.engine import NEEDS_DECISION, NEEDS_INPUT, Simulator
from app.simulation.evaluator import format_value

RUN_BATCH = 500


class SimulationHighlight(QGraphicsItem):
    """Hervorhebung des aktuellen Bausteins (nicht auswählbar, nicht im Export)."""

    def __init__(self):
        super().__init__()
        self._rect = QRectF()
        self.setZValue(LAYER_OVERLAY - 1)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect).adjusted(-7, -7, 7, 7)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-4, -4, 4, 4)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        scene = self.scene()
        if scene is not None and getattr(scene, "exporting", False):
            return
        theme = styles.current_theme()
        color = QColor(theme.element_accents[ElementType.DECISION])
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fill = QColor(color)
        fill.setAlphaF(0.12)
        pen = QPen(color, 3.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(self._rect, 8, 8)


class SimulationPanel(QWidget):
    element_focus_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document = None
        self._simulator: Simulator | None = None
        self._highlight: SimulationHighlight | None = None
        self._stale = False

        self.program_combo = QComboBox()
        self.program_combo.setToolTip(tr("Ablauf (Start-Element)"))
        self.restart_button = self._tool("restart", tr("Neu starten"), self.restart)
        self.step_button = self._tool("step", tr("Einen Schritt ausführen (F10)"), self.step)
        self.step_button.setShortcut(QKeySequence("F10"))
        self.run_button = self._tool("play", tr("Ausführen bis zur nächsten Eingabe (F5)"), self.run)
        self.run_button.setShortcut(QKeySequence("F5"))
        self.stop_button = self._tool("stop", tr("Beenden", ctx="Schreibtischtest"), self.stop)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 4, 6, 0)
        toolbar.addWidget(self.program_combo, 1)
        for button in (self.restart_button, self.step_button, self.run_button, self.stop_button):
            toolbar.addWidget(button)
        # hält die Schaltflächen zusammen, wenn die Ablaufauswahl ausgeblendet ist
        self._toolbar_stretch = QWidget()
        toolbar.addWidget(self._toolbar_stretch, 1)

        self.status = QLabel(tr("Starten Sie den Schreibtischtest mit ▶ oder „Schritt“."))
        self.status.setWordWrap(True)
        self.status.setContentsMargins(8, 2, 8, 2)

        # Eingabe
        self.input_label = QLabel("")
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(tr("Wert(e) eingeben, mehrere durch Leerzeichen trennen"))
        self.input_field.returnPressed.connect(self.submit_input)
        ok = QPushButton(tr("OK"))
        ok.clicked.connect(self.submit_input)
        self.input_row = QWidget()
        row = QHBoxLayout(self.input_row)
        row.setContentsMargins(8, 0, 8, 0)
        row.addWidget(self.input_label)
        row.addWidget(self.input_field, 1)
        row.addWidget(ok)

        # Entscheidung (ja/nein oder – bei Mehrfachverzweigungen – ein Knopf je Ausgang)
        self.decision_label = QLabel("")
        self.decision_label.setWordWrap(True)
        self.decision_row = QWidget()
        self._decision_layout = QHBoxLayout(self.decision_row)
        self._decision_layout.setContentsMargins(8, 0, 8, 0)
        self._decision_layout.addWidget(self.decision_label, 1)
        self._decision_buttons: list[QPushButton] = []
        self._decision_options: list[str] | None = None
        self._set_decision_options([])

        # Tabellen
        self.variables_table = QTableWidget(0, 2)
        self.variables_table.setHorizontalHeaderLabels([tr("Variable"), tr("Wert")])
        self.trace_table = QTableWidget(0, 2)
        self.outputs = QPlainTextEdit()
        self.outputs.setReadOnly(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        for table in (self.variables_table, self.trace_table):
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.horizontalHeader().setStretchLastSection(True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.variables_table, tr("Variablen"))
        self.tabs.addTab(self.trace_table, tr("Schreibtischtest"))
        self.tabs.addTab(self.outputs, tr("Ausgaben"))
        self.tabs.addTab(self.log, tr("Protokoll"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(toolbar)
        layout.addWidget(self.status)
        layout.addWidget(self.input_row)
        layout.addWidget(self.decision_row)
        layout.addWidget(self.tabs, 1)
        self._update_controls()

    def _set_decision_options(self, options: list[str]) -> None:
        """Knöpfe der Entscheidungszeile: ja/nein oder die Beschriftungen der Ausgänge."""
        if options == self._decision_options:
            return
        self._decision_options = list(options)
        for button in self._decision_buttons:
            self._decision_layout.removeWidget(button)
            button.deleteLater()
        self._decision_buttons = []
        choices = [(label, index) for index, label in enumerate(options)] if options \
            else [(yes_label(), True), (no_label(), False)]
        for label, answer in choices:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, a=answer: self.decide(a))
            self._decision_layout.addWidget(button)
            self._decision_buttons.append(button)

    def _tool(self, icon_name: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setIcon(icons.icon(icon_name))
        button.setToolTip(tip)
        button.setProperty("icon_name", icon_name)
        button.clicked.connect(slot)
        return button

    def refresh_theme(self) -> None:
        for button in (self.restart_button, self.step_button, self.run_button, self.stop_button):
            button.setIcon(icons.icon(button.property("icon_name")))
        if self._highlight is not None:
            self._highlight.update()

    # ------------------------------------------------------------ Dokument
    def set_document(self, document) -> None:
        if document is self._document:
            return
        self.stop(silent=True)
        if self._document is not None:
            try:
                self._document.undo_stack.indexChanged.disconnect(self._on_document_changed)
                self._document.scene.content_changed.disconnect(self._refresh_programs)
            except (RuntimeError, TypeError):
                pass
        self._document = document
        if document is not None:
            document.undo_stack.indexChanged.connect(self._on_document_changed)
            document.scene.content_changed.connect(self._refresh_programs)
        self._refresh_programs()

    def _refresh_programs(self, *_args) -> None:
        current = self.program_combo.currentData()
        self.program_combo.blockSignals(True)
        self.program_combo.clear()
        if self._document is not None:
            # gleiche Reihenfolge wie die Analyse: Hauptprogramm zuerst
            for node in FlowGraph.from_scene(self._document.scene).starts():
                self.program_combo.addItem(" ".join(node.text.split()) or default_text_for(ElementType.START),
                                           node.id)
        index = self.program_combo.findData(current)
        self.program_combo.setCurrentIndex(max(0, index))
        self.program_combo.blockSignals(False)
        self._update_controls()

    def _on_document_changed(self, *_args) -> None:
        if self._simulator is None:
            return
        if self._simulator.finished:
            self._show_current(focus=False)  # Hervorhebung nachführen (Baustein verschoben/gelöscht)
            return
        # Der laufende Test gehört zum alten Plan: keine Eingaben mehr annehmen,
        # ▶/Schritt starten neu.
        self._stale = True
        self.input_row.hide()
        self.decision_row.hide()
        self._remove_highlight()
        self.status.setText(tr("Der Plan wurde geändert. Bitte den Schreibtischtest neu starten."))
        self._update_controls()

    # ------------------------------------------------------------ Ablauf
    @property
    def simulator(self) -> Simulator | None:
        return self._simulator

    def restart(self) -> None:
        self.stop(silent=True)
        if self._document is None:
            return
        self._document.scene.commit_edit()
        start_id = self.program_combo.currentData()
        graph = FlowGraph.from_scene(self._document.scene)
        if not graph.starts():
            self.status.setText(tr("Der Plan enthält kein Start-Element."))
            return
        self._simulator = Simulator(graph, start_id)
        self._stale = False
        self.log.clear()
        self.outputs.clear()
        self.status.setText(tr("Bereit. „Schritt“ führt den nächsten Baustein aus."))
        self._show_current()
        self._update_tables()
        self._update_controls()

    def _ensure_running(self) -> bool:
        if self._simulator is None or self._simulator.finished or self._stale:
            self.restart()
        return self._simulator is not None

    def step(self) -> None:
        if not self._ensure_running():
            return
        if self._simulator.pending is not None:
            self._show_result(self._simulator.pending)
            return
        self._show_result(self._simulator.step())

    def run(self) -> None:
        if not self._ensure_running():
            return
        for _ in range(RUN_BATCH):
            if self._simulator.pending is not None or self._simulator.finished:
                break
            result = self._simulator.step()
            self._log(result)
            if result.needs or result.finished:
                break
        else:
            self.status.setText(tr("Nach {count} Schritten angehalten – mit ▶ fortsetzen.", count=RUN_BATCH))
        self._show_result(self._simulator.pending or None, logged=True)

    def stop(self, silent: bool = False) -> None:
        self._simulator = None
        self._stale = False
        self._remove_highlight()
        self.input_row.hide()
        self.decision_row.hide()
        if not silent:
            self.status.setText(tr("Schreibtischtest beendet."))
        self._update_controls()

    def submit_input(self) -> None:
        if self._simulator is None or self._simulator.pending is None or self._stale:
            return
        result = self._simulator.provide_input(self.input_field.text())
        if result.needs is None:
            self.input_field.clear()
        self._show_result(result)

    def decide(self, answer) -> None:
        """``True``/``False`` für ja/nein oder die Nummer des gewählten Ausgangs."""
        if self._simulator is None or self._simulator.pending is None or self._stale:
            return
        self._show_result(self._simulator.provide_decision(answer))

    # ------------------------------------------------------------ Anzeige
    def _log(self, result) -> None:
        if result is not None and result.message and not result.needs:
            self.log.appendPlainText(result.message)
            if result.output is not None:
                self.outputs.appendPlainText(result.output)

    def _show_result(self, result, logged: bool = False) -> None:
        simulator = self._simulator
        if simulator is None:
            return
        if result is not None and not logged:
            self._log(result)
        pending = simulator.pending
        self.input_row.setVisible(pending is not None and pending.needs == NEEDS_INPUT)
        self.decision_row.setVisible(pending is not None and pending.needs == NEEDS_DECISION)
        if pending is not None and pending.needs == NEEDS_INPUT:
            names = ", ".join(pending.variables)
            self.input_label.setText(f"{pending.prompt} → {names}:")
            # abgelehnte Eingabe („Bitte eine Zahl …“): die Rückmeldung zeigen, nicht die alte Aufforderung
            rejected = result is not None and result is not pending and result.needs == NEEDS_INPUT
            self.status.setText(result.message if rejected else pending.message)
            self.input_field.setFocus()
            if rejected:
                self.input_field.selectAll()
        elif pending is not None and pending.needs == NEEDS_DECISION:
            self._set_decision_options(pending.options)
            self.decision_label.setText(pending.prompt)
            self.status.setText(pending.message)
        elif simulator.finished:
            if result is not None and result.message:
                self.status.setText(tr("{message} – Schreibtischtest beendet.", message=result.message))
            else:
                self.status.setText(tr("Schreibtischtest beendet."))
        elif result is not None:
            self.status.setText(result.message)
        self._show_current()
        self._update_tables()
        self._update_controls()

    def _show_current(self, focus: bool = True) -> None:
        simulator = self._simulator
        if simulator is None or self._document is None:
            self._remove_highlight()
            return
        element_id = simulator.pending.element_id if simulator.pending else simulator.current
        if simulator.finished and simulator.trace:
            element_id = simulator.trace[-1].element_id
        item = self._document.scene.element(element_id) if element_id else None
        if item is None:
            self._remove_highlight()
            return
        scene = self._document.scene
        if self._highlight is None or self._highlight.scene() is not scene:
            self._remove_highlight()
            self._highlight = SimulationHighlight()
            scene.addItem(self._highlight)
        self._highlight.set_rect(item.scene_rect())
        if focus:
            self.element_focus_requested.emit(element_id)

    def _remove_highlight(self) -> None:
        if self._highlight is not None:
            scene = self._highlight.scene()
            if scene is not None:
                scene.removeItem(self._highlight)
            self._highlight = None

    def _update_tables(self) -> None:
        simulator = self._simulator
        variables = simulator.variables if simulator else {}
        self.variables_table.setRowCount(len(variables))
        for row, (name, value) in enumerate(variables.items()):
            self.variables_table.setItem(row, 0, QTableWidgetItem(name))
            self.variables_table.setItem(row, 1, QTableWidgetItem(format_value(value)))
        trace = simulator.trace if simulator else []
        names = list(variables)
        self.trace_table.setColumnCount(2 + len(names))
        self.trace_table.setHorizontalHeaderLabels([tr("Schritt"), tr("Baustein")] + names)
        self.trace_table.setRowCount(len(trace))
        for row, entry in enumerate(trace):
            self.trace_table.setItem(row, 0, QTableWidgetItem(str(entry.step)))
            self.trace_table.setItem(row, 1, QTableWidgetItem(entry.element_text))
            for column, name in enumerate(names, start=2):
                previous = trace[row - 1].variables.get(name) if row else None
                value = entry.variables.get(name)
                text = format_value(value) if name in entry.variables else ""
                # nur Änderungen eintragen – wie beim Schreibtischtest auf Papier
                if row and name in trace[row - 1].variables and previous == value:
                    text = ""
                self.trace_table.setItem(row, column, QTableWidgetItem(text))
        self.trace_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if trace:
            self.trace_table.scrollToBottom()

    def _update_controls(self) -> None:
        has_document = self._document is not None
        running = self._simulator is not None and not self._simulator.finished
        self.program_combo.setEnabled(has_document and not running)
        several = self.program_combo.count() > 1
        self.program_combo.setVisible(several)
        self._toolbar_stretch.setVisible(not several)
        for button in (self.restart_button, self.step_button, self.run_button):
            button.setEnabled(has_document)
        self.stop_button.setEnabled(self._simulator is not None)
