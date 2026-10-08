"""Dialog: Übersicht der Tastenkürzel und Mausbedienung."""

from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from app.i18n import N_, tr

# (Taste bzw. Aktion, Funktion); eine Zeile ohne Funktion ist eine Überschrift.
# Beides ist deutscher Quelltext (mit N_ markiert) und wird beim Aufbau der Tabelle mit tr() übersetzt:
# Die Tastennamen („Strg“, „Umschalt“, „Entf“ …) gehören zum Text, denn sie heißen je nach Sprache anders.
SHORTCUTS = [
    (N_("Datei"), ""),
    (N_("Strg+N"), N_("Neues Projekt")),
    (N_("Strg+O"), N_("Projekt öffnen")),
    (N_("Strg+S"), N_("Speichern")),
    (N_("Strg+Umschalt+S"), N_("Speichern unter")),
    (N_("Strg+P"), N_("Drucken")),
    (N_("Strg+W"), N_("Projekt schließen")),
    (N_("Bearbeiten"), ""),
    (N_("Strg+Z"), N_("Rückgängig")),
    (N_("Strg+Y"), N_("Wiederholen")),
    (N_("Strg+X / Strg+C / Strg+V"), N_("Ausschneiden / Kopieren / Einfügen")),
    (N_("Strg+D"), N_("Duplizieren")),
    (N_("Entf"), N_("Löschen")),
    (N_("Strg+A"), N_("Alles auswählen")),
    (N_("Esc"), N_("Auswahl aufheben / Verschieben, Verbinden oder Eingabe abbrechen")),
    (N_("Kontextmenü-Taste / Umschalt+F10"), N_("Kontextmenü")),
    (N_("Pfeiltasten"), N_("Auswahl um ein Rasterfeld verschieben (mit Umschalt: 5 Felder)")),
    (N_("Text"), ""),
    (N_("Doppelklick, F2 oder Enter"), N_("Text des ausgewählten Bausteins bearbeiten")),
    (N_("Tippen"), N_("Ausgewählten Baustein direkt neu beschriften")),
    (N_("Enter"), N_("Texteingabe bestätigen")),
    (N_("Umschalt+Enter"), N_("Zeilenumbruch")),
    (N_("Esc"), N_("Texteingabe abbrechen")),
    (N_("Extras"), ""),
    (N_("Strg+Umschalt+C"), N_("Code erzeugen (Pseudocode, Python, Java)")),
    (N_("Strg+Umschalt+N"), N_("Struktogramm")),
    (N_("Strg+L"), N_("Automatisch anordnen")),
    (N_("F9"), N_("Schreibtischtest ein-/ausblenden")),
    (N_("F10 / F5"), N_("Schreibtischtest: ein Schritt / bis zur nächsten Eingabe")),
    (N_("Strg+Umschalt+H"), N_("Hinweisliste ein-/ausblenden")),
    (N_("Ansicht"), ""),
    (N_("Mausrad"), N_("Zoomen (am Mauszeiger)")),
    (N_("Rechte / mittlere Maustaste ziehen"), N_("Arbeitsfläche verschieben")),
    (N_("Leertaste + linke Maustaste"), N_("Arbeitsfläche verschieben")),
    (N_("Strg++ / Strg+-"), N_("Zoom + / Zoom -")),
    (N_("Strg+0"), N_("Zoom 100 %")),
    (N_("Strg+1"), N_("Diagramm einpassen")),
    (N_("Strg+G"), N_("Raster ein/aus")),
    (N_("Maus"), ""),
    (N_("Linke Maustaste ziehen (frei)"), N_("Auswahlrechteck")),
    (N_("Strg+Klick"), N_("Mehrfachauswahl")),
    (N_("Anschlusspunkt ziehen"), N_("Verbindung erstellen (Ziel: Baustein, Verbindungspunkt oder Pfeil)")),
    (N_("Anschlusspunkt auf einen Pfeil ziehen"),
     N_("Verbindung an den Pfeil anschließen (Verbindungspunkt entsteht)")),
    (N_("Umschalt + Pfeil ziehen"), N_("Neue Verbindung an einem bestehenden Pfeil beginnen")),
    (N_("Rote Verbindung"), N_("Hinweis: Verbindung ist möglicherweise falsch (bleibt erhalten)")),
    (N_("Mittleres Liniensegment ziehen"), N_("Linienführung anpassen")),
    (N_("Baustein auf eine Verbindung ziehen"), N_("Baustein in den Ablauf einfügen")),
    (N_("Rechtsklick"), N_("Kontextmenü")),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Tastenkürzel und Bedienung"))
        self.resize(560, 640)
        title = QLabel(tr("Tastenkürzel und Bedienung"))
        title.setObjectName("DialogTitle")

        table = QTableWidget(len(SHORTCUTS), 2)
        table.setHorizontalHeaderLabels([tr("Taste / Aktion"), tr("Funktion")])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, (key, text) in enumerate(SHORTCUTS):
            key_item = QTableWidgetItem(tr(key))
            text_item = QTableWidgetItem(tr(text) if text else "")
            if not text:
                font = key_item.font()
                font.setBold(True)
                key_item.setFont(font)
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, text_item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Schließen"))
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(table, 1)
        layout.addWidget(buttons)
