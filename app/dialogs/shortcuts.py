"""Dialog: Übersicht der Tastenkürzel und Mausbedienung."""

from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

SHORTCUTS = [
    ("Datei", ""),
    ("Strg+N", "Neues Projekt"),
    ("Strg+O", "Projekt öffnen"),
    ("Strg+S", "Speichern"),
    ("Strg+Umschalt+S", "Speichern unter"),
    ("Strg+P", "Drucken"),
    ("Strg+W", "Projekt schließen"),
    ("Bearbeiten", ""),
    ("Strg+Z", "Rückgängig"),
    ("Strg+Y", "Wiederholen"),
    ("Strg+X / Strg+C / Strg+V", "Ausschneiden / Kopieren / Einfügen"),
    ("Strg+D", "Duplizieren"),
    ("Entf", "Löschen"),
    ("Strg+A", "Alles auswählen"),
    ("Esc", "Auswahl aufheben / Verschieben, Verbinden oder Eingabe abbrechen"),
    ("Kontextmenü-Taste / Umschalt+F10", "Kontextmenü"),
    ("Pfeiltasten", "Auswahl um ein Rasterfeld verschieben (mit Umschalt: 5 Felder)"),
    ("Text", ""),
    ("Doppelklick, F2 oder Enter", "Text des ausgewählten Bausteins bearbeiten"),
    ("Tippen", "Ausgewählten Baustein direkt neu beschriften"),
    ("Enter", "Texteingabe bestätigen"),
    ("Umschalt+Enter", "Zeilenumbruch"),
    ("Esc", "Texteingabe abbrechen"),
    ("Extras", ""),
    ("Strg+Umschalt+C", "Code erzeugen (Pseudocode, Python, Java)"),
    ("Strg+Umschalt+N", "Struktogramm"),
    ("Strg+L", "Automatisch anordnen"),
    ("F9", "Schreibtischtest ein-/ausblenden"),
    ("F10 / F5", "Schreibtischtest: ein Schritt / bis zur nächsten Eingabe"),
    ("Strg+Umschalt+H", "Hinweisliste ein-/ausblenden"),
    ("Ansicht", ""),
    ("Mausrad", "Zoomen (am Mauszeiger)"),
    ("Rechte / mittlere Maustaste ziehen", "Arbeitsfläche verschieben"),
    ("Leertaste + linke Maustaste", "Arbeitsfläche verschieben"),
    ("Strg++ / Strg+-", "Zoom + / Zoom -"),
    ("Strg+0", "Zoom 100 %"),
    ("Strg+1", "Diagramm einpassen"),
    ("Strg+G", "Raster ein/aus"),
    ("Maus", ""),
    ("Linke Maustaste ziehen (frei)", "Auswahlrechteck"),
    ("Strg+Klick", "Mehrfachauswahl"),
    ("Anschlusspunkt ziehen", "Verbindung erstellen (Ziel: Baustein, Verbindungspunkt oder Pfeil)"),
    ("Anschlusspunkt auf einen Pfeil ziehen", "Verbindung an den Pfeil anschließen (Verbindungspunkt entsteht)"),
    ("Umschalt + Pfeil ziehen", "Neue Verbindung an einem bestehenden Pfeil beginnen"),
    ("Rote Verbindung", "Hinweis: Verbindung ist möglicherweise falsch (bleibt erhalten)"),
    ("Mittleres Liniensegment ziehen", "Linienführung anpassen"),
    ("Baustein auf eine Verbindung ziehen", "Baustein in den Ablauf einfügen"),
    ("Rechtsklick", "Kontextmenü"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tastenkürzel und Bedienung")
        self.resize(560, 640)
        title = QLabel("Tastenkürzel und Bedienung")
        title.setObjectName("DialogTitle")

        table = QTableWidget(len(SHORTCUTS), 2)
        table.setHorizontalHeaderLabels(["Taste / Aktion", "Funktion"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, (key, text) in enumerate(SHORTCUTS):
            key_item = QTableWidgetItem(key)
            text_item = QTableWidgetItem(text)
            if not text:
                font = key_item.font()
                font.setBold(True)
                key_item.setFont(font)
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, text_item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(table, 1)
        layout.addWidget(buttons)
