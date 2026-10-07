"""Dock-Panel „Hinweise“: listet Auffälligkeiten im Plan auf.

Die Liste aktualisiert sich automatisch (verzögert) bei jeder Änderung.
Ein Klick auf einen Eintrag wählt die betroffenen Elemente im Plan aus.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from app import icons, styles
from app.diagnostics.checks import WARNING, Issue, run_checks


def severity_icon(severity: str) -> QIcon:
    theme = styles.current_theme()
    color = QColor(theme.connection_invalid if severity == WARNING else theme.accent)
    pixmap = QPixmap(28, 28)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(3, 3, 8, 8)
    painter.end()
    return QIcon(pixmap)


class DiagnosticsPanel(QWidget):
    navigate_requested = Signal(list, list)   # Element-IDs, Verbindungs-IDs
    issues_changed = Signal(int, int)          # Warnungen, Hinweise

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document = None
        self._issues: list[Issue] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)

        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        refresh = QToolButton()
        refresh.setIcon(icons.icon("restart"))
        refresh.setToolTip("Aktualisieren")
        refresh.clicked.connect(self.refresh)
        self._refresh_button = refresh
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 4, 0)
        header.addWidget(self.summary, 1)
        header.addWidget(refresh)

        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        self.list.setWordWrap(True)
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemActivated.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(self.list, 1)
        self.refresh()

    # ------------------------------------------------------------ Dokument
    def set_debounce(self, milliseconds: int) -> None:
        self._timer.setInterval(max(0, int(milliseconds)))

    def set_document(self, document) -> None:
        if document is self._document:
            return
        if self._document is not None:
            try:
                self._document.scene.content_changed.disconnect(self.schedule_refresh)
                self._document.undo_stack.indexChanged.disconnect(self.schedule_refresh)
            except (RuntimeError, TypeError):
                pass
        self._document = document
        if document is not None:
            document.scene.content_changed.connect(self.schedule_refresh)
            document.undo_stack.indexChanged.connect(self.schedule_refresh)
        self.refresh()

    def schedule_refresh(self, *_args) -> None:
        self._timer.start()

    @property
    def issues(self) -> list[Issue]:
        return list(self._issues)

    def refresh(self) -> None:
        self._timer.stop()
        self.list.clear()
        document = self._document
        if document is None:
            self._issues = []
            self.summary.setText("Kein Projekt geöffnet.")
            self.issues_changed.emit(0, 0)
            return
        try:
            self._issues = run_checks(document.scene)
        except Exception:  # Hinweise dürfen die Bedienung nie stören
            self._issues = []
        warnings = sum(1 for issue in self._issues if issue.severity == WARNING)
        infos = len(self._issues) - warnings
        if not self._issues:
            self.summary.setText("Keine Auffälligkeiten.")
        else:
            parts = []
            if warnings:
                parts.append(f"{warnings} Warnung" + ("en" if warnings != 1 else ""))
            if infos:
                parts.append(f"{infos} Hinweis" + ("e" if infos != 1 else ""))
            self.summary.setText(" · ".join(parts))
        warning_icon = severity_icon(WARNING)
        info_icon = severity_icon("info")
        for index, issue in enumerate(self._issues):
            item = QListWidgetItem(warning_icon if issue.severity == WARNING else info_icon, issue.message)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(issue.message)
            self.list.addItem(item)
        self.issues_changed.emit(warnings, infos)

    def refresh_theme(self) -> None:
        self._refresh_button.setIcon(icons.icon("restart"))
        self.refresh()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None or not (0 <= index < len(self._issues)):
            return
        issue = self._issues[index]
        if issue.element_ids or issue.connection_ids:
            self.navigate_requested.emit(list(issue.element_ids), list(issue.connection_ids))
