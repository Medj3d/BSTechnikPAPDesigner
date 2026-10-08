"""Zentrale Definition aller Befehle (QActions) mit Text, Icon und Tastenkürzel."""

from __future__ import annotations

import re

from PySide6.QtGui import QAction, QKeySequence

from app import icons
from app.alignment import (ALIGN_BOTTOM, ALIGN_CENTER_X, ALIGN_CENTER_Y, ALIGN_LEFT, ALIGN_RIGHT,
                           ALIGN_TOP, DISTRIBUTE_H, DISTRIBUTE_V, LABELS, SNAP_TO_GRID)
from app.i18n import N_, tr
from app.model.element_types import FLOW_TERMINALS, PALETTE_ORDER, description_for, display_name_for

K = QKeySequence.StandardKey

# Kurzschreibung der Mnemonik in ostasiatischen Sprachen: „ファイル(&F)“, „文件（&F）“
_EAST_ASIAN_MNEMONIC = re.compile(r"\s*[(（]&[^)）&][)）]")
# Auslassungspunkte am Ende („Öffnen …“, „Open...“, „开(&O)…“) – mit oder ohne Leerzeichen davor
_TRAILING_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)+\s*$")
# „&x“ markiert den Mnemonik-Buchstaben, „&&“ ist ein echtes „&“
_MNEMONIC_AMPERSAND = re.compile(r"&(&?)")

# name: (Text, Icon, Tastenkürzel, Statuszeilen-Hinweis)
# Text und Hinweis sind deutscher Quelltext (mit N_ markiert); übersetzt wird beim Anlegen der QActions.
_DEFINITIONS = {
    # Datei
    "new": (N_("&Neu"), "new", [K.New], N_("Neues, leeres Projekt anlegen")),
    "open": (N_("Ö&ffnen …"), "open", [K.Open], N_("Projektdatei öffnen")),
    "save": (N_("&Speichern"), "save", [K.Save], N_("Projekt speichern")),
    "save_as": (N_("Speichern &unter …"), "save_as", ["Ctrl+Shift+S"], N_("Projekt unter neuem Namen speichern")),
    "auto_save": (N_("&Automatisch speichern"), None, [],
                  N_("Bereits gespeicherte Projekte nach jeder Änderung von selbst speichern")),
    "export_png": (N_("Als &PNG-Bild …"), None, [], N_("Diagramm als PNG-Bild exportieren")),
    "export_svg": (N_("Als &SVG-Grafik …"), None, [], N_("Diagramm als SVG-Vektorgrafik exportieren")),
    "export_pdf": (N_("Als P&DF-Dokument …"), None, [], N_("Diagramm als PDF exportieren")),
    "print": (N_("&Drucken …"), "print", [K.Print], N_("Diagramm drucken")),
    "print_preview": (N_("Druck&vorschau …"), None, [], N_("Druckvorschau anzeigen")),
    "properties": (N_("Projekt&eigenschaften …"), "properties", [],
                   N_("Projektname, Autor, Beschreibung und Raster")),
    "close": (N_("S&chließen"), "close", [K.Close], N_("Aktuelles Projekt schließen")),
    "quit": (N_("&Beenden"), None, ["Ctrl+Q"], N_("Programm beenden")),
    # Bearbeiten
    "undo": (N_("&Rückgängig"), "undo", [K.Undo], N_("Letzte Aktion rückgängig machen")),
    "redo": (N_("&Wiederholen"), "redo", ["Ctrl+Y", "Ctrl+Shift+Z"], N_("Rückgängig gemachte Aktion wiederholen")),
    "cut": (N_("&Ausschneiden"), "cut", [K.Cut], N_("Auswahl ausschneiden")),
    "copy": (N_("&Kopieren"), "copy", [K.Copy], N_("Auswahl kopieren")),
    "paste": (N_("&Einfügen"), "paste", [K.Paste], N_("Aus der Zwischenablage einfügen")),
    "duplicate": (N_("&Duplizieren"), "duplicate", ["Ctrl+D"], N_("Auswahl duplizieren")),
    "delete": (N_("&Löschen"), "delete", [K.Delete], N_("Auswahl löschen")),
    "select_all": (N_("Alles au&swählen"), "select_all", [K.SelectAll], N_("Alle Elemente auswählen")),
    "deselect": (N_("Auswahl au&fheben"), None, ["Esc"], N_("Auswahl aufheben bzw. Aktion abbrechen")),
    "edit_text": (N_("&Text bearbeiten"), None, ["F2"], N_("Text des ausgewählten Bausteins bearbeiten")),
    # Ansicht
    "zoom_in": (N_("Zoom &+"), "zoom_in", [K.ZoomIn, "Ctrl+="], N_("Hineinzoomen")),
    "zoom_out": (N_("Zoom &−"), "zoom_out", [K.ZoomOut], N_("Herauszoomen")),
    "zoom_reset": (N_("Auf &100 %"), "zoom_reset", ["Ctrl+0"], N_("Zoom auf 100 % setzen")),
    "zoom_fit": (N_("Diagramm &einpassen"), "zoom_fit", ["Ctrl+1"], N_("Ganzes Diagramm anzeigen")),
    "toggle_grid": (N_("&Raster anzeigen"), "grid", ["Ctrl+G"], N_("Punktraster ein-/ausblenden")),
    "toggle_snap": (N_("Am Raster &einrasten"), "snap", ["Ctrl+Shift+G"], N_("Bausteine beim Verschieben einrasten")),
    # Anordnen (die Texte stehen in app/alignment.py und sind dort mit N_ markiert)
    ALIGN_LEFT: (LABELS[ALIGN_LEFT], "align_left", [], N_("Linke Kanten ausrichten")),
    ALIGN_RIGHT: (LABELS[ALIGN_RIGHT], "align_right", [], N_("Rechte Kanten ausrichten")),
    ALIGN_TOP: (LABELS[ALIGN_TOP], "align_top", [], N_("Obere Kanten ausrichten")),
    ALIGN_BOTTOM: (LABELS[ALIGN_BOTTOM], "align_bottom", [], N_("Untere Kanten ausrichten")),
    ALIGN_CENTER_X: (LABELS[ALIGN_CENTER_X], "align_center_x", [], N_("Auf gemeinsame senkrechte Mittelachse")),
    ALIGN_CENTER_Y: (LABELS[ALIGN_CENTER_Y], "align_center_y", [], N_("Auf gemeinsame waagerechte Mittelachse")),
    DISTRIBUTE_H: (LABELS[DISTRIBUTE_H], "distribute_h", [], N_("Gleiche horizontale Abstände")),
    DISTRIBUTE_V: (LABELS[DISTRIBUTE_V], "distribute_v", [], N_("Gleiche vertikale Abstände")),
    SNAP_TO_GRID: (LABELS[SNAP_TO_GRID], "snap", [], N_("Ausgewählte Bausteine auf das Raster setzen")),
    "bring_front": (N_("Nach &vorne"), "front", ["Ctrl+Shift+Up"], N_("In den Vordergrund")),
    "send_back": (N_("Nach &hinten"), "back", ["Ctrl+Shift+Down"], N_("In den Hintergrund")),
    "toggle_loop_part": (N_("Schleifenbeginn/-ende &umschalten"), None, [],
                         N_("Teil der Schleifenbegrenzung wechseln")),
    "reset_routing": (N_("Linienführung &zurücksetzen"), None, [], N_("Automatische Linienführung wiederherstellen")),
    # Extras
    "generate_code": (N_("&Code erzeugen …"), "code", ["Ctrl+Shift+C"],
                      N_("Pseudocode, Python oder Java aus dem PAP erzeugen")),
    "structogram": (N_("&Struktogramm …"), "structogram", ["Ctrl+Shift+N"],
                    N_("Ablauf als Struktogramm (Nassi-Shneiderman)")),
    "auto_layout": (N_("&Automatisch anordnen"), "layout", ["Ctrl+L"], N_("Bausteine übersichtlich neu anordnen")),
    "theme_dark": (N_("&Dunkel"), None, [], N_("Dunkles Farbschema")),
    "theme_light": (N_("&Hell"), None, [], N_("Helles Farbschema (z. B. für Beamer)")),
    # Hilfe
    "shortcuts": (N_("&Tastenkürzel und Bedienung"), "keyboard", [K.HelpContents], N_("Übersicht der Bedienung")),
    "register_filetype": (N_("Dateityp registrieren …"), "register", [],
                          N_("Projektdateien mit diesem Programm öffnen")),
    "check_updates": (N_("Nach &Updates suchen …"), None, [],
                      N_("Prüfen, ob eine neuere Version veröffentlicht wurde")),
    "about": (N_("Ü&ber das Programm"), "info", [], N_("Version, Urheber und Informationen über das Programm")),
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
        for name, (text_source, icon_name, shortcuts, tip_source) in _DEFINITIONS.items():
            text = tr(text_source)
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
            action.setStatusTip(tr(tip_source))
            action.setToolTip(self._tooltip(text, sequences))
            self._actions[name] = action
        for element_type in PALETTE_ORDER + FLOW_TERMINALS:
            block_name = display_name_for(element_type)
            action = QAction(block_name, parent)
            action.setIcon(icons.element_icon(element_type))
            action.setStatusTip(tr("{name} einfügen – {description}", name=block_name,
                                   description=description_for(element_type)))
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
        """Menütext ohne Mnemonik und ohne Auslassungspunkte, ggf. mit Tastenkürzel: „Speichern (Strg+S)“.

        Erkennt auch die ostasiatische Schreibweise der Mnemonik („保存(&S)…“) und Auslassungspunkte ohne
        Leerzeichen davor, damit auch übersetzte Menütexte saubere Kurzinfos ergeben.
        """
        clean = _EAST_ASIAN_MNEMONIC.sub("", text)
        clean = _TRAILING_ELLIPSIS.sub("", clean)
        clean = _MNEMONIC_AMPERSAND.sub(r"\1", clean)
        if sequences:
            return f"{clean} ({sequences[0].toString(QKeySequence.SequenceFormat.NativeText)})"
        return clean

    def __getitem__(self, name: str) -> QAction:
        return self._actions[name]

    def get(self, name: str) -> QAction | None:
        return self._actions.get(name)

    def all(self) -> dict[str, QAction]:
        return dict(self._actions)
