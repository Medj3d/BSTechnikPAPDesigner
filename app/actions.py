"""Zentrale Definition aller Befehle (QActions) mit Text, Icon und Tastenkürzel."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from app import icons, preferences
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
    "backup_on_save": (N_("Sicherungs&kopie anlegen"), None, [],
                       N_("Vor dem ersten Speichern den Stand beim Öffnen als „.pap-backup“ neben der Datei "
                          "aufheben")),
    "export_png": (N_("Als &PNG-Bild …"), None, [], N_("Diagramm als PNG-Bild exportieren")),
    "export_svg": (N_("Als &SVG-Grafik …"), None, [], N_("Diagramm als SVG-Vektorgrafik exportieren")),
    "export_pdf": (N_("Als P&DF-Dokument …"), "export", ["Ctrl+E"], N_("Diagramm als PDF exportieren")),
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
    "copy_image": (N_("Als &Bild kopieren"), None, ["Ctrl+Shift+B"],
                   N_("Auswahl bzw. ganze Seite als Bild in die Zwischenablage (zum Einfügen in Word, OneNote …)")),
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
    # Schleife mit Kopf- bzw. Fußbedingung (wie im PapDesigner)
    "insert_loop_head": (N_("Schleife mit &Kopfbedingung"), None, [],
                         N_("Schleife einfügen, deren Bedingung am Anfang geprüft wird (solange …)")),
    "insert_loop_foot": (N_("Schleife mit &Fußbedingung"), None, [],
                         N_("Schleife einfügen, deren Bedingung am Ende geprüft wird (wiederhole … bis …)")),
    # Unterprogramme (eigene Seiten des Projekts)
    "new_subprogram": (N_("Neues &Unterprogramm …"), None, ["Ctrl+Shift+U"],
                       N_("Ein Unterprogramm auf einer eigenen Seite anlegen")),
    "open_subprogram": (N_("&Unterprogramm öffnen"), None, [],
                        N_("Die Seite des Unterprogramms anzeigen, das der ausgewählte Baustein aufruft")),
    "next_page": (N_("&Nächste Seite"), None, ["Ctrl+PgDown"], N_("Nächstes Unterprogramm anzeigen")),
    "previous_page": (N_("&Vorherige Seite"), None, ["Ctrl+PgUp"],
                      N_("Vorheriges Unterprogramm bzw. das Hauptprogramm anzeigen")),
    "go_back": (N_("&Zurück"), None, ["Alt+Left"],
                N_("Zur zuletzt angezeigten Seite zurück (z. B. vom Unterprogramm zum Aufruf)")),
    "go_forward": (N_("V&orwärts"), None, ["Alt+Right"],
                   N_("Wieder zu der Seite, von der aus „Zurück“ gewählt wurde")),
    "extract_subprogram": (N_("Auswahl in Unterprogramm &auslagern …"), None, ["Ctrl+Alt+U"],
                           N_("Die markierten Bausteine auf eine eigene Seite verschieben; an ihrer Stelle ruft "
                              "ein Unterprogramm-Baustein sie auf")),
    "duplicate_page": (N_("Seite d&uplizieren"), None, [], N_("Eine Kopie des angezeigten Unterprogramms anlegen")),
    "copy_page": (N_("Seite &kopieren"), None, [],
                  N_("Die angezeigte Seite in die Zwischenablage legen – zum Einfügen als Unterprogramm, auch in "
                     "einem anderen Projekt")),
    "cut_page": (N_("Seite aus&schneiden"), None, [],
                 N_("Das angezeigte Unterprogramm in die Zwischenablage legen und entfernen")),
    "paste_page": (N_("Seite &einfügen"), None, [], N_("Eine kopierte Seite als neues Unterprogramm einfügen")),
    "move_page_left": (N_("Seite nach &links verschieben"), None, ["Ctrl+Shift+PgUp"],
                       N_("Das angezeigte Unterprogramm in der Seitenleiste eine Stelle nach links verschieben")),
    "move_page_right": (N_("Seite nach &rechts verschieben"), None, ["Ctrl+Shift+PgDown"],
                        N_("Das angezeigte Unterprogramm in der Seitenleiste eine Stelle nach rechts verschieben")),
    # Extras
    "generate_code": (N_("&Code erzeugen …"), "code", ["Ctrl+Shift+C"],
                      N_("Pseudocode, Python oder Java aus dem PAP erzeugen")),
    "structogram": (N_("&Struktogramm …"), "structogram", ["Ctrl+Shift+N"],
                    N_("Ablauf als Struktogramm (Nassi-Shneiderman)")),
    "auto_layout": (N_("&Automatisch anordnen"), "layout", ["Ctrl+L"], N_("Bausteine übersichtlich neu anordnen")),
    "presentation": (N_("&Präsentationsansicht"), None, ["F11"],
                     N_("Nur den Plan im Vollbild zeigen – z. B. für den Beamer (F11 oder Esc beendet)")),
    "theme_dark": (N_("&Dunkel"), None, [], N_("Dunkles Farbschema")),
    "theme_light": (N_("&Hell"), None, [], N_("Helles Farbschema (z. B. für Beamer)")),
    "settings": (N_("&Einstellungen …"), "properties", ["Ctrl+,"],
                 N_("Schalter und frei belegbare Tastenkürzel")),
    "search": (N_("&Suchen …"), None, ["Ctrl+K"], N_("Funktionen, Einstellungen und Bausteine im Plan finden")),
    "edit_task": (N_("&Aufgabe stellen …"), "task", [],
                  N_("Lehrkraft: Aufgabenstellung und verschlüsselte Musterlösung in das Projekt schreiben")),
    "toggle_minimap": (N_("&Minikarte"), "minimap", ["Ctrl+M"],
                       N_("Kleine Übersicht des ganzen Plans am rechten Rand ein-/ausblenden")),
    "toggle_breakpoint": (N_("&Haltepunkt setzen/entfernen"), "breakpoint", ["F9"],
                          N_("Der Schreibtischtest hält vor dem ausgewählten Baustein an")),
    "clear_breakpoints": (N_("Alle Haltepunkte &entfernen"), None, [], N_("Alle Haltepunkte des Projekts entfernen")),
    "add_bend": (N_("&Knick einfügen"), None, [],
                 N_("In die ausgewählte Verbindung eine Stufe einfügen (ändert nur das Aussehen)")),
    # Hilfe
    "shortcuts": (N_("&Tastenkürzel und Bedienung"), "keyboard", [K.HelpContents], N_("Übersicht der Bedienung")),
    "register_filetype": (N_("Dateityp registrieren …"), "register", [],
                          N_("Projektdateien mit diesem Programm öffnen")),
    "check_updates_on_start": (N_("Beim &Start nach Updates suchen"), None, [],
                               N_("Bei jedem Programmstart nachsehen, ob eine neuere Version veröffentlicht wurde")),
    "check_updates": (N_("Nach &Updates suchen …"), None, [],
                      N_("Prüfen, ob eine neuere Version veröffentlicht wurde")),
    "about": (N_("Ü&ber das Programm"), "info", [], N_("Version, Urheber und Informationen über das Programm")),
    # Schreibtischtest (die Knöpfe stehen im Bedienfeld; die Tasten gelten im ganzen Fenster)
    "simulation_back": (N_("Schreibtischtest: Schritt zurück"), None, ["Ctrl+F10"], N_("Einen Schritt zurück")),
    "simulation_step": (N_("Schreibtischtest: Schritt ausführen"), None, ["F10"], N_("Einen Schritt ausführen")),
    "simulation_run": (N_("Schreibtischtest: Ausführen"), None, ["F5"], N_("Ausführen bis zur nächsten Eingabe")),
    "simulation_play": (N_("Schreibtischtest: Abspielen"), None, ["F6"], N_("Automatisch abspielen bzw. anhalten")),
}

# Bausteine liegen auf den Zifferntasten, in der Reihenfolge der Werkzeugpalette
BLOCK_KEYS = dict(zip(PALETTE_ORDER + FLOW_TERMINALS, "123456789"))

ALIGN_ACTIONS = [ALIGN_LEFT, ALIGN_RIGHT, ALIGN_TOP, ALIGN_BOTTOM, ALIGN_CENTER_X, ALIGN_CENTER_Y,
                 DISTRIBUTE_H, DISTRIBUTE_V]


def insert_action_name(element_type) -> str:
    return f"insert_{element_type.value}"


def _is_media_key(sequence: QKeySequence) -> bool:
    """Sondertaste wie „Save“ auf Multimedia-Tastaturen: Sie würde einen der beiden Plätze belegen."""
    return sequence.count() == 1 and sequence[0].key().value >= Qt.Key.Key_Back.value


def clean_text(text: str) -> str:
    """Menütext ohne Mnemonik und ohne Auslassungspunkte."""
    clean = _EAST_ASIAN_MNEMONIC.sub("", text)
    clean = _TRAILING_ELLIPSIS.sub("", clean)
    return _MNEMONIC_AMPERSAND.sub(r"\1", clean)


def sequence_text(sequence: QKeySequence) -> str:
    """Tastenkürzel, wie es im Menü steht („Strg+S“)."""
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)


class ActionRegistry:
    """Erzeugt und hält alle QActions eines Hauptfensters."""

    def __init__(self, parent):
        self._actions: dict[str, QAction] = {}
        self._icon_names: dict[str, str] = {}
        self._default_shortcuts: dict[str, list[QKeySequence]] = {}
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
                    sequences.extend(s for s in QKeySequence.keyBindings(shortcut) if not _is_media_key(s))
            if sequences:
                action.setShortcuts(sequences)
            action.setStatusTip(tr(tip_source))
            action.setToolTip(self._tooltip(text, sequences))
            self._actions[name] = action
            self._default_shortcuts[name] = sequences
        for element_type in PALETTE_ORDER + FLOW_TERMINALS:
            block_name = display_name_for(element_type)
            action = QAction(block_name, parent)
            action.setIcon(icons.element_icon(element_type))
            action.setStatusTip(tr("{name} einfügen – {description}", name=block_name,
                                   description=description_for(element_type)))
            action.setData(element_type)
            name = insert_action_name(element_type)
            sequences = [QKeySequence(BLOCK_KEYS[element_type])]
            action.setShortcuts(sequences)
            action.setToolTip(self._tooltip(block_name, sequences))
            self._actions[name] = action
            self._default_shortcuts[name] = sequences
        for preference in preferences.PREFERENCES:
            name = preferences.action_name(preference.name)
            action = QAction(tr(preference.text), parent)
            action.setStatusTip(tr(preference.tip))
            action.setCheckable(True)
            action.setChecked(preferences.enabled(preference.name))
            action.setData(preference.name)
            self._actions[name] = action
            self._default_shortcuts[name] = []
        for name in ("toggle_grid", "toggle_snap"):
            self._actions[name].setCheckable(True)
            self._actions[name].setChecked(True)
        for name in ("theme_dark", "theme_light", "auto_save", "backup_on_save", "check_updates_on_start",
                     "presentation", "toggle_minimap", "toggle_breakpoint"):
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
        clean = clean_text(text)
        if sequences:
            return f"{clean} ({sequence_text(sequences[0])})"
        return clean

    # ------------------------------------------------------- Tastenkürzel
    def adopt(self, name: str, action: QAction, shortcuts: list[str]) -> None:
        """Nimmt eine fremde QAction (z. B. den Schalter eines Docks) in die Tastenbelegung auf."""
        sequences = [QKeySequence(shortcut) for shortcut in shortcuts]
        action.setShortcuts(sequences)
        self._actions[name] = action
        self._default_shortcuts[name] = sequences

    def bindable(self) -> list[str]:
        """Namen aller Funktionen, die auf einer Taste liegen können (Menüreihenfolge)."""
        return list(self._actions)

    def default_shortcuts(self, name: str) -> list[QKeySequence]:
        return list(self._default_shortcuts.get(name, []))[:2]

    def assign(self, name: str, sequences: list[QKeySequence]) -> list[tuple[QKeySequence, str]]:
        """Legt eine Funktion auf bis zu zwei Tasten. Gibt zurück, welche Tasten woanders weichen mussten."""
        moved = []
        for sequence in sequences:
            for other, action in self._actions.items():
                if other != name and sequence in action.shortcuts():
                    action.setShortcuts([s for s in action.shortcuts() if s != sequence])
                    self._refresh_tooltip(other)
                    moved.append((sequence, other))
        self._actions[name].setShortcuts(sequences[:2])
        self._refresh_tooltip(name)
        return moved

    def _refresh_tooltip(self, name: str) -> None:
        action = self._actions[name]
        action.setToolTip(self._tooltip(action.text(), action.shortcuts()))

    def reset_shortcuts(self) -> None:
        for name, sequences in self._default_shortcuts.items():
            self._actions[name].setShortcuts(sequences)
            self._refresh_tooltip(name)

    def custom_shortcuts(self) -> dict[str, list[str]]:
        """Alle Belegungen, die vom Standard abweichen (zum Speichern)."""
        custom = {}
        for name, action in self._actions.items():
            current = [s.toString(QKeySequence.SequenceFormat.PortableText) for s in action.shortcuts()]
            default = [s.toString(QKeySequence.SequenceFormat.PortableText) for s in self.default_shortcuts(name)]
            if current[:2] != default:
                custom[name] = current[:2]
        return custom

    def apply_custom_shortcuts(self, custom: dict) -> None:
        """Stellt eine gespeicherte Belegung wieder her; Unbekanntes wird übergangen."""
        for name, keys in custom.items():
            if name in self._actions and isinstance(keys, list):
                self.assign(name, [QKeySequence(str(key)) for key in keys if str(key)])

    def __getitem__(self, name: str) -> QAction:
        return self._actions[name]

    def get(self, name: str) -> QAction | None:
        return self._actions.get(name)

    def all(self) -> dict[str, QAction]:
        return dict(self._actions)
