"""Zentrale Definition aller Befehle (QActions) mit Text, Icon und Tastenkürzel."""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence

from app import icons
from app.alignment import (ALIGN_BOTTOM, ALIGN_CENTER_X, ALIGN_CENTER_Y, ALIGN_LEFT, ALIGN_RIGHT,
                           ALIGN_TOP, DISTRIBUTE_H, DISTRIBUTE_V, LABELS, SNAP_TO_GRID)
from app.model.element_types import FLOW_TERMINALS, PALETTE_ORDER, spec_for

K = QKeySequence.StandardKey

# name: (Text, Icon, Tastenkürzel, Statuszeilen-Hinweis)
_DEFINITIONS = {
    # Datei
    "new": ("&Neu", "new", [K.New], "Neues, leeres Projekt anlegen"),
    "open": ("Ö&ffnen …", "open", [K.Open], "Projektdatei öffnen"),
    "save": ("&Speichern", "save", [K.Save], "Projekt speichern"),
    "save_as": ("Speichern &unter …", "save_as", ["Ctrl+Shift+S"], "Projekt unter neuem Namen speichern"),
    "auto_save": ("&Automatisch speichern", None, [],
                  "Bereits gespeicherte Projekte nach jeder Änderung von selbst speichern"),
    "export_png": ("Als &PNG-Bild …", None, [], "Diagramm als PNG-Bild exportieren"),
    "export_svg": ("Als &SVG-Grafik …", None, [], "Diagramm als SVG-Vektorgrafik exportieren"),
    "export_pdf": ("Als P&DF-Dokument …", None, [], "Diagramm als PDF exportieren"),
    "print": ("&Drucken …", "print", [K.Print], "Diagramm drucken"),
    "print_preview": ("Druck&vorschau …", None, [], "Druckvorschau anzeigen"),
    "properties": ("Projekt&eigenschaften …", "properties", [], "Projektname, Autor, Beschreibung und Raster"),
    "close": ("S&chließen", "close", [K.Close], "Aktuelles Projekt schließen"),
    "quit": ("&Beenden", None, ["Ctrl+Q"], "Programm beenden"),
    # Bearbeiten
    "undo": ("&Rückgängig", "undo", [K.Undo], "Letzte Aktion rückgängig machen"),
    "redo": ("&Wiederholen", "redo", ["Ctrl+Y", "Ctrl+Shift+Z"], "Rückgängig gemachte Aktion wiederholen"),
    "cut": ("&Ausschneiden", "cut", [K.Cut], "Auswahl ausschneiden"),
    "copy": ("&Kopieren", "copy", [K.Copy], "Auswahl kopieren"),
    "paste": ("&Einfügen", "paste", [K.Paste], "Aus der Zwischenablage einfügen"),
    "duplicate": ("&Duplizieren", "duplicate", ["Ctrl+D"], "Auswahl duplizieren"),
    "delete": ("&Löschen", "delete", [K.Delete], "Auswahl löschen"),
    "select_all": ("Alles au&swählen", "select_all", [K.SelectAll], "Alle Elemente auswählen"),
    "deselect": ("Auswahl au&fheben", None, ["Esc"], "Auswahl aufheben bzw. Aktion abbrechen"),
    "edit_text": ("&Text bearbeiten", None, ["F2"], "Text des ausgewählten Bausteins bearbeiten"),
    # Ansicht
    "zoom_in": ("Zoom &+", "zoom_in", [K.ZoomIn, "Ctrl+="], "Hineinzoomen"),
    "zoom_out": ("Zoom &−", "zoom_out", [K.ZoomOut], "Herauszoomen"),
    "zoom_reset": ("Auf &100 %", "zoom_reset", ["Ctrl+0"], "Zoom auf 100 % setzen"),
    "zoom_fit": ("Diagramm &einpassen", "zoom_fit", ["Ctrl+1"], "Ganzes Diagramm anzeigen"),
    "toggle_grid": ("&Raster anzeigen", "grid", ["Ctrl+G"], "Punktraster ein-/ausblenden"),
    "toggle_snap": ("Am Raster &einrasten", "snap", ["Ctrl+Shift+G"], "Bausteine beim Verschieben einrasten"),
    # Anordnen
    ALIGN_LEFT: (LABELS[ALIGN_LEFT], "align_left", [], "Linke Kanten ausrichten"),
    ALIGN_RIGHT: (LABELS[ALIGN_RIGHT], "align_right", [], "Rechte Kanten ausrichten"),
    ALIGN_TOP: (LABELS[ALIGN_TOP], "align_top", [], "Obere Kanten ausrichten"),
    ALIGN_BOTTOM: (LABELS[ALIGN_BOTTOM], "align_bottom", [], "Untere Kanten ausrichten"),
    ALIGN_CENTER_X: (LABELS[ALIGN_CENTER_X], "align_center_x", [], "Auf gemeinsame senkrechte Mittelachse"),
    ALIGN_CENTER_Y: (LABELS[ALIGN_CENTER_Y], "align_center_y", [], "Auf gemeinsame waagerechte Mittelachse"),
    DISTRIBUTE_H: (LABELS[DISTRIBUTE_H], "distribute_h", [], "Gleiche horizontale Abstände"),
    DISTRIBUTE_V: (LABELS[DISTRIBUTE_V], "distribute_v", [], "Gleiche vertikale Abstände"),
    SNAP_TO_GRID: (LABELS[SNAP_TO_GRID], "snap", [], "Ausgewählte Bausteine auf das Raster setzen"),
    "bring_front": ("Nach &vorne", "front", ["Ctrl+Shift+Up"], "In den Vordergrund"),
    "send_back": ("Nach &hinten", "back", ["Ctrl+Shift+Down"], "In den Hintergrund"),
    "toggle_loop_part": ("Schleifenbeginn/-ende &umschalten", None, [], "Teil der Schleifenbegrenzung wechseln"),
    "reset_routing": ("Linienführung &zurücksetzen", None, [], "Automatische Linienführung wiederherstellen"),
    # Extras
    "generate_code": ("&Code erzeugen …", "code", ["Ctrl+Shift+C"], "Pseudocode, Python oder Java aus dem PAP erzeugen"),
    "structogram": ("&Struktogramm …", "structogram", ["Ctrl+Shift+N"], "Ablauf als Struktogramm (Nassi-Shneiderman)"),
    "auto_layout": ("&Automatisch anordnen", "layout", ["Ctrl+L"], "Bausteine übersichtlich neu anordnen"),
    "theme_dark": ("&Dunkel", None, [], "Dunkles Farbschema"),
    "theme_light": ("&Hell", None, [], "Helles Farbschema (z. B. für Beamer)"),
    # Hilfe
    "shortcuts": ("&Tastenkürzel und Bedienung", "keyboard", [K.HelpContents], "Übersicht der Bedienung"),
    "register_filetype": (f"Dateityp registrieren …", "register", [], "Projektdateien mit diesem Programm öffnen"),
    "check_updates": ("Nach &Updates suchen …", None, [], "Prüfen, ob eine neuere Version veröffentlicht wurde"),
    "about": ("Ü&ber das Programm", "info", [], "Version, Urheber und Informationen über das Programm"),
}

ALIGN_ACTIONS = [ALIGN_LEFT, ALIGN_RIGHT, ALIGN_TOP, ALIGN_BOTTOM, ALIGN_CENTER_X, ALIGN_CENTER_Y,
                 DISTRIBUTE_H, DISTRIBUTE_V]


def insert_action_name(element_type) -> str:
    return f"insert_{element_type.value}"


class ActionRegistry:
    """Erzeugt und hält alle QActions eines Hauptfensters."""

    def __init__(self, parent):
        self._actions: dict[str, QAction] = {}
        self._icon_names: dict[str, str] = {}
        for name, (text, icon_name, shortcuts, tip) in _DEFINITIONS.items():
            action = QAction(text, parent)
            if icon_name:
                action.setIcon(icons.icon(icon_name))
                self._icon_names[name] = icon_name
            sequences = []
            for shortcut in shortcuts:
                if isinstance(shortcut, str):
                    sequences.append(QKeySequence(shortcut))
                else:
                    sequences.extend(QKeySequence.keyBindings(shortcut))
            if sequences:
                action.setShortcuts(sequences)
            action.setStatusTip(tip)
            action.setToolTip(self._tooltip(text, sequences))
            self._actions[name] = action
        for element_type in PALETTE_ORDER + FLOW_TERMINALS:
            spec = spec_for(element_type)
            action = QAction(spec.display_name, parent)
            action.setIcon(icons.element_icon(element_type))
            action.setStatusTip(f"{spec.display_name} einfügen – {spec.description}")
            action.setData(element_type)
            self._actions[insert_action_name(element_type)] = action
        for name in ("toggle_grid", "toggle_snap"):
            self._actions[name].setCheckable(True)
            self._actions[name].setChecked(True)
        for name in ("theme_dark", "theme_light", "auto_save"):
            self._actions[name].setCheckable(True)

    def refresh_icons(self) -> None:
        """Icons nach einem Wechsel des Farbschemas neu setzen."""
        for name, icon_name in self._icon_names.items():
            self._actions[name].setIcon(icons.icon(icon_name))
        for element_type in PALETTE_ORDER + FLOW_TERMINALS:
            self._actions[insert_action_name(element_type)].setIcon(icons.element_icon(element_type))

    @staticmethod
    def _tooltip(text: str, sequences) -> str:
        clean = text.replace("&", "").replace(" …", "")
        if sequences:
            return f"{clean} ({sequences[0].toString(QKeySequence.SequenceFormat.NativeText)})"
        return clean

    def __getitem__(self, name: str) -> QAction:
        return self._actions[name]

    def get(self, name: str) -> QAction | None:
        return self._actions.get(name)

    def all(self) -> dict[str, QAction]:
        return dict(self._actions)
