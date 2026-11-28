"""Dialog „Schreibweisen im Plan“: was Schreibtischtest und Code-Erzeugung in den Bausteintexten verstehen.

Die Einträge stehen in ``app/notation.py``; jedes Beispiel wird in ``tests/test_feature_notation_help.py``
wirklich ausgeführt.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QLineEdit,
                               QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout)

from app import icons, notation
from app.codegen.dialog import monospace_font
from app.i18n import tr
from app.search_text import matches


class LeftToRightDelegate(QStyledItemDelegate):
    """Schreibweisen immer von links nach rechts – auch in der arabischen Oberfläche (sonst sprängen etwa die
    Anführungszeichen in ``name = "Anna"`` an den Anfang). Der Text selbst bleibt unverändert: Strg+C kopiert ihn
    genau so, wie er in den Baustein gehört."""

    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        option.direction = Qt.LayoutDirection.LeftToRight


class NotationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Schreibweisen im Plan"))
        self.resize(760, 640)
        title = QLabel(tr("Schreibweisen im Plan"))
        title.setObjectName("DialogTitle")
        intro = QLabel(tr("So geschrieben rechnet der Schreibtischtest mit dem Text, und die Code-Erzeugung macht "
                          "daraus echte Befehle. Anderer Text ist erlaubt: Er wird dann nur angezeigt (im Code "
                          "steht ein TODO)."))
        intro.setWordWrap(True)
        # ehrlich bleiben: Der PIC hat nur 8 Bit (siehe README, PIC-Assembler)
        scope = QLabel(tr("Geprüft für Schreibtischtest, Pseudocode, Python und Java. Der PIC-Assembler rechnet nur mit "
                          "ganzen Zahlen von 0 bis 255 und kennt keinen Text."))
        scope.setObjectName("Muted")
        scope.setWordWrap(True)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Schreibweise oder Baustein suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        rows: list[tuple[str, notation.Notation | None]] = []
        for heading, entries in notation.SECTIONS:
            rows.append((heading, None))
            rows += [(heading, entry) for entry in entries]
        self._rows = rows
        table = QTableWidget(len(rows), 3)
        self.table = table
        table.setHorizontalHeaderLabels([tr("Baustein"), tr("Schreibweise"), tr("Bedeutung")])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setObjectName("NotationTable")
        # Innenabstand: Baustein, Beispiel und Bedeutung stoßen sonst direkt aneinander
        table.setStyleSheet("QTableWidget#NotationTable::item { padding: 3px 10px; }")
        self._example_delegate = LeftToRightDelegate(table)
        table.setItemDelegateForColumn(1, self._example_delegate)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Beispiele lassen sich markieren und kopieren (Strg+C), um sie in einen Baustein zu übernehmen
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for row, (heading, entry) in enumerate(rows):
            if entry is None:
                item = QTableWidgetItem(tr(heading))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                table.setItem(row, 0, item)
                table.setItem(row, 1, QTableWidgetItem(""))
                table.setItem(row, 2, QTableWidgetItem(""))
                table.setSpan(row, 0, 1, 3)
                continue
            block = QTableWidgetItem(icons.element_icon(entry.block), entry.block_text())
            block.setFlags(Qt.ItemFlag.ItemIsEnabled)
            example = QTableWidgetItem(entry.example)
            # wie im Baustein und in der Code-Ansicht: in der Programmierschrift
            font = monospace_font()
            font.setBold(True)
            example.setFont(font)
            # Schreibweisen stehen immer von links nach rechts – auch in der arabischen Oberfläche
            example.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute
                                     | Qt.AlignmentFlag.AlignVCenter)
            example.setToolTip(tr("Markieren und mit Strg+C kopieren"))
            meaning = QTableWidgetItem(entry.meaning_text())
            meaning.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row, 0, block)
            table.setItem(row, 1, example)
            table.setItem(row, 2, meaning)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Schließen"))
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(scope)
        layout.addWidget(self.search)
        layout.addWidget(table, 1)
        layout.addWidget(buttons)

    def _filter(self, text: str) -> None:
        """Zeigt nur passende Zeilen; eine Überschrift bleibt, solange unter ihr etwas passt (oder sie selbst)."""
        heading_row, heading_hit, visible_below = None, False, False

        def close_section() -> None:
            if heading_row is not None:
                self.table.setRowHidden(heading_row, not (visible_below or heading_hit))

        for row, (heading, entry) in enumerate(self._rows):
            if entry is None:
                close_section()
                heading_row, visible_below = row, False
                heading_hit = bool(text.strip()) and matches(text, tr(heading))
                continue
            texts = [self.table.item(row, column).text() for column in range(3)]
            hidden = not (heading_hit or matches(text, *texts))
            self.table.setRowHidden(row, hidden)
            visible_below = visible_below or not hidden
        close_section()
