"""Bausteinliste und „Verbinden mit …“: den Plan ohne Maus lesen und Pfeile mit der Tastatur anlegen.

* ``flow_order`` ordnet die Bausteine einer Seite wie der Ablauf: vom Start aus, an einer Verzweigung zuerst der
  Ja-Zweig, dann der Nein-Zweig; was nicht erreicht wird (z. B. Kommentare, lose Teile), folgt von oben nach unten.
  Verbindungspunkte erscheinen nicht, Pfeile werden durch sie hindurch bis zum nächsten Baustein verfolgt.
* ``BlockListPanel`` zeigt diese Reihenfolge mit den Pfeilen jedes Bausteins („→ Verzweigung „i >= 3“ (ja)“) –
  für Bildschirmleser und alle, die den Plan mit der Tastatur durchgehen. Enter zeigt den Baustein im Plan.
* ``ConnectDialog`` fragt nach dem Ziel eines neuen Pfeils (durchsuchbare Liste, bei einer Verzweigung auch die
  Beschriftung ja/nein); angelegt wird er von ``DiagramScene.connect_blocks``.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget)

from app import labels
from app.connections.follow import line_end
from app.i18n import tr
from app.model import rules
from app.model.element_types import LOOSE_END_KEY, ElementType, default_text_for, display_name_for
from app.search_text import matches

# Reihenfolge der Ausgänge eines Bausteins (wie im Schreibtischtest: „ja“ vor „nein“, „sonst“ zuletzt)
_PORT_ORDER = {"bottom": 0, "right": 1, "left": 2, "top": 3}
ELEMENT_ID_ROLE = Qt.ItemDataRole.UserRole


# ================================================================== Texte
def _label_rank(label: str) -> int:
    if labels.is_yes(label):
        return 0
    if labels.is_no(label):
        return 1
    if labels.is_else(label):
        return 3
    return 2


def _line_order(conn) -> tuple:
    return _label_rank(conn.data.label), _PORT_ORDER.get(conn.data.source_port, 9), conn.order or 0


def is_loose_end(item) -> bool:
    return item.is_junction and bool(item.data.properties.get(LOOSE_END_KEY))


def item_title(item) -> str:
    """„Verzweigung „i >= 3““ – Bausteintyp und Text in einer Zeile (ohne Text nur der Typ)."""
    if is_loose_end(item):
        return tr("offenes Ende")
    if item.element_type is ElementType.LOOP:
        kind = default_text_for(ElementType.LOOP, item.data.properties)   # Schleifenbeginn / Schleifenende
    else:
        kind = display_name_for(item.element_type)
    text = " ".join((item.data.text or "").split())
    if not text or item.is_junction:
        return kind
    return tr("{block} „{text}“", block=kind, text=text)


def _flow_lines(item) -> list:
    """Ausgehende Ablaufpfeile, in der Reihenfolge des Ablaufs."""
    lines = [c for c in item.connections if c.source is item and not c.is_annotation]
    return sorted(lines, key=_line_order)


def line_text(conn) -> str:
    """„→ Verzweigung „i >= 3“ (ja)“ – wohin ein Pfeil führt (durch Verbindungspunkte hindurch)."""
    target = line_end(conn, True)
    name = item_title(target) if target is not None else tr("offenes Ende")
    label = " ".join((conn.data.label or "").split())
    if label:
        return tr("→ {target} ({label})", target=name, label=label)
    return tr("→ {target}", target=name)


def item_lines(item) -> list[str]:
    """Was von einem Baustein ausgeht: seine Pfeile bzw. bei einem Kommentar, wozu er gehört."""
    if item.is_comment:
        partners = []
        for conn in item.connections:
            if conn.is_annotation:
                other = conn.target if conn.source is item else conn.source
                if other is not None and other is not item:
                    partners.append(tr("gehört zu {target}", target=item_title(other)))
        return partners
    lines = [line_text(conn) for conn in _flow_lines(item)]
    if not lines and item.spec.can_be_source:
        lines.append(tr("kein Pfeil heraus"))
    return lines


def item_summary(item) -> str:
    """Eine Zeile der Bausteinliste: Baustein und alle seine Pfeile."""
    lines = item_lines(item)
    title = item_title(item)
    return f"{title}  {'; '.join(lines)}" if lines else title


def item_display(item) -> str:
    """Anzeige in der Bausteinliste: der Baustein, darunter je Pfeil eine eingerückte Zeile (lesbar auch in einer
    schmalen Spalte – umgebrochen wird an Wortgrenzen statt mitten im Text)."""
    lines = item_lines(item)
    return "\n".join([item_title(item), *("   " + line for line in lines)])


# ================================================================== Reihenfolge
def listed_items(scene) -> list:
    """Die Bausteine einer Seite, die in den Listen erscheinen (ohne Verbindungspunkte)."""
    return [item for item in scene.elements() if not item.is_junction]


def _position(item) -> tuple:
    return item.data.y, item.data.x


def flow_order(scene) -> list:
    """Alle Bausteine der Seite in Ablaufreihenfolge (siehe Moduldoku)."""
    items = listed_items(scene)
    ordered, seen = [], set()

    def walk(root) -> None:
        stack = [root]
        while stack:
            item = stack.pop()
            if id(item) in seen:
                continue
            seen.add(id(item))
            if not item.is_junction:
                ordered.append(item)
            following = [conn.target for conn in _flow_lines(item) if conn.target is not None]
            stack.extend(reversed(following))   # der erste Ausgang (ja) kommt zuerst dran

    starts = sorted((item for item in items if item.element_type is ElementType.START), key=_position)
    for item in starts + sorted(items, key=_position):
        if id(item) not in seen:
            walk(item)
    return ordered


# ================================================================== Verbinden mit …
def can_start_line(item) -> bool:
    """Kann an diesem Baustein ein Pfeil beginnen? (Ende und Verbindungspunkte nicht)"""
    return item is not None and not item.is_junction and (item.spec.can_be_source or item.is_comment)


def _is_target(source, item) -> bool:
    if item is source or item.is_junction:
        return False
    return not item.is_comment if source.is_comment else item.spec.can_be_target


def connect_targets(scene, source) -> list:
    """Mögliche Ziele für einen Pfeil von ``source``: alle anderen Bausteine der Seite, in Ablaufreihenfolge."""
    return [item for item in flow_order(scene) if _is_target(source, item)]


def can_connect(scene, source) -> bool:
    """Gibt es für „Verbinden mit …“ eine Quelle und mindestens ein Ziel? (schnell, für das Menü)"""
    return can_start_line(source) and any(_is_target(source, item) for item in scene.elements())


def suggested_label(source) -> str:
    """Die Beschriftung, die ein weiterer Ausgang der Verzweigung bekäme (erst „ja“, dann „nein“)."""
    existing = [c.data.label for c in source.connections if c.source is source and not c.is_annotation]
    return rules.suggest_decision_label(existing)


class ConnectDialog(QDialog):
    """Ziel eines neuen Pfeils wählen: Suchfeld, Liste der Bausteine und bei einer Verzweigung die Beschriftung."""

    def __init__(self, source, targets: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Verbinden mit"))
        self.setMinimumWidth(460)
        self._source = source
        self._targets = list(targets)
        source_title = item_title(source)
        self.setAccessibleName(tr("Pfeil von {source} zu einem anderen Baustein", source=source_title))

        heading = QLabel(tr("Pfeil von {source}", source=source_title))
        heading.setObjectName("DialogTitle")
        heading.setWordWrap(True)
        hint = QLabel(tr("Ziel wählen und mit Enter verbinden. Die Anschlüsse und die Linienführung sucht das "
                         "Programm selbst aus."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        search_label = QLabel(tr("Ziel &suchen:"))
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(tr("Text oder Bausteintyp …"))
        self.search.setAccessibleName(tr("Ziel suchen"))
        self.search.setAccessibleDescription(tr("Filtert die Liste; Pfeil nach oben/unten wählt in der Liste"))
        search_label.setBuddy(self.search)
        self.search.textChanged.connect(self._filter)
        self.search.installEventFilter(self)

        list_label = QLabel(tr("&Ziel des Pfeils:"))
        self.list = QListWidget()
        self.list.setAccessibleName(tr("Ziel des Pfeils"))
        self.list.setAccessibleDescription(tr("Alle anderen Bausteine der Seite in der Reihenfolge des Ablaufs"))
        self.list.setUniformItemSizes(True)
        list_label.setBuddy(self.list)
        # auch über Verbindungspunkte hinweg: verbunden ist, wo der Pfeil am Ende ankommt
        connected = {id(line_end(c, True)) for c in source.connections if c.source is source}
        for target in self._targets:
            text = item_title(target)
            if id(target) in connected:
                text = tr("{name} – schon verbunden", name=text)
            entry = QListWidgetItem(text)
            entry.setData(Qt.ItemDataRole.AccessibleTextRole, text)
            entry.setData(ELEMENT_ID_ROLE, target.element_id)
            self.list.addItem(entry)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.list.currentRowChanged.connect(lambda _row: self._update_ok())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addWidget(search_label)
        layout.addWidget(self.search)
        layout.addWidget(list_label)
        layout.addWidget(self.list, 1)

        self.label_combo: QComboBox | None = None
        if source.element_type is ElementType.DECISION:
            label_label = QLabel(tr("&Beschriftung des Pfeils:"))
            combo = QComboBox()
            combo.setAccessibleName(tr("Beschriftung des Pfeils"))
            combo.setAccessibleDescription(tr("Welcher Ausgang der Verzweigung der neue Pfeil ist"))
            used = [c.data.label for c in source.connections if c.source is source and not c.is_annotation]
            for text, test in ((labels.yes_label(), labels.is_yes), (labels.no_label(), labels.is_no)):
                taken = any(test(label) for label in used)
                # schon vergeben: wählbar (z. B. vor dem Löschen des alten Pfeils), aber sichtbar gekennzeichnet
                combo.addItem(tr("{label} – schon vergeben", label=text) if taken else text, text)
            combo.addItem(tr("ohne Beschriftung"), "")
            suggestion = suggested_label(source)
            combo.setCurrentIndex(max(0, combo.findData(suggestion)))
            label_label.setBuddy(combo)
            layout.addWidget(label_label)
            layout.addWidget(combo)
            self.label_combo = combo
        else:
            outgoing = [c for c in source.connections if c.source is source and not c.is_annotation]
            limit = source.spec.max_outgoing
            if not source.is_comment and limit is not None and len(outgoing) >= limit:
                full = QLabel(tr("Von diesem Baustein geht schon ein Pfeil aus – ein zweiter wird als Fehler "
                                 "markiert."))
                full.setObjectName("Muted")
                full.setWordWrap(True)
                layout.addWidget(full)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText(tr("Verbinden"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._update_ok()
        self.search.setFocus()

    # ------------------------------------------------------------ Auswahl
    def target(self):
        """Der gewählte Zielbaustein (``None``, wenn keiner gewählt ist)."""
        entry = self.list.currentItem()
        if entry is None or entry.isHidden():
            return None
        element_id = entry.data(ELEMENT_ID_ROLE)
        for target in self._targets:
            if shiboken6.isValid(target) and target.element_id == element_id:
                return target
        return None

    def label(self) -> str | None:
        """Beschriftung des neuen Pfeils (nur bei einer Verzweigung, sonst ``None``)."""
        return self.label_combo.currentData() if self.label_combo is not None else None

    def select_target(self, element_id: str) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(ELEMENT_ID_ROLE) == element_id:
                self.list.setCurrentRow(row)
                return

    def accept(self) -> None:
        if self.target() is not None:
            super().accept()

    # ------------------------------------------------------------ Suchen
    def _filter(self, text: str) -> None:
        first = None
        for row in range(self.list.count()):
            entry = self.list.item(row)
            hidden = not matches(text, entry.text())
            entry.setHidden(hidden)
            if not hidden and first is None:
                first = row
        current = self.list.currentItem()
        if current is None or current.isHidden():
            if first is None:
                self.list.setCurrentRow(-1)
            else:
                self.list.setCurrentRow(first)
        self._update_ok()

    def _update_ok(self) -> None:
        self.ok_button.setEnabled(self.target() is not None)

    def eventFilter(self, watched, event) -> bool:
        # im Suchfeld wählen die Pfeiltasten in der Liste (wie in der Suchleiste)
        if watched is self.search and event.type() == QEvent.Type.KeyPress \
                and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self._step(event.key())
            return True
        return super().eventFilter(watched, event)

    def _step(self, key) -> None:
        visible = [row for row in range(self.list.count()) if not self.list.item(row).isHidden()]
        if not visible:
            return
        row = self.list.currentRow()
        position = visible.index(row) if row in visible else -1
        step = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1, Qt.Key.Key_PageUp: -10, Qt.Key.Key_PageDown: 10}[key]
        position = max(0, min(len(visible) - 1, position + step if position >= 0 else 0))
        self.list.setCurrentRow(visible[position])


# ================================================================== Bausteinliste (Dock)
class BlockListPanel(QWidget):
    """Alle Bausteine der angezeigten Seite mit ihren Pfeilen – lesbar für Bildschirmleser, bedienbar per Tastatur.

    Enter oder Doppelklick wählt den Baustein im Plan aus und holt ihn in die Mitte; Esc geht zurück in den Plan.
    Die Liste folgt jeder Änderung (auch Rückgängig) und dem Seitenwechsel, solange sie sichtbar ist.
    """

    element_activated = Signal(str)   # Element-ID
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document = None
        self._stale = False   # verborgen geändert: beim nächsten Zeigen neu aufbauen
        self._pending_selection = None   # im Plan ausgewählt, während ein Neuaufbau anstand
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)

        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.list = QListWidget()
        self.list.setObjectName("BlockList")
        self.list.setAccessibleName(tr("Bausteinliste"))
        self.list.setAccessibleDescription(tr("Alle Bausteine der Seite in der Reihenfolge des Ablaufs, mit ihren "
                                              "Pfeilen. Enter zeigt den Baustein im Plan, Esc geht zurück in den "
                                              "Plan."))
        self.list.setWordWrap(True)
        self.list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list.setAlternatingRowColors(True)   # Einträge klar voneinander getrennt
        self.list.setSpacing(1)
        self.list.itemDoubleClicked.connect(self._activate)
        self.list.installEventFilter(self)
        self.summary.setBuddy(self.list)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        self.setFocusProxy(self.list)

    # Eigene Spalte neben dem Feld „Bausteine“ (das Hauptfenster gibt ihr beim ersten Zeigen 300 Pixel); wer mehr
    # sehen will, zieht den Rand.
    def sizeHint(self) -> QSize:
        return QSize(300, 320)

    def minimumSizeHint(self) -> QSize:
        return QSize(80, 120)

    # ------------------------------------------------------------ Projekt
    def set_document(self, document) -> None:
        if document is self._document:
            return
        if self._document is not None and shiboken6.isValid(self._document):
            for signal in (self._document.content_changed, self._document.pages_changed,
                           self._document.undo_stack.indexChanged, self._document.current_page_changed):
                try:
                    signal.disconnect(self.schedule_refresh)
                except (RuntimeError, TypeError):
                    pass
        self._document = document
        if document is not None:
            for signal in (document.content_changed, document.pages_changed, document.undo_stack.indexChanged,
                           document.current_page_changed):
                signal.connect(self.schedule_refresh)
        if self.isVisible():
            self.refresh()
        else:
            self._stale = True   # verborgen wird nichts gerechnet (Reiterwechsel bleibt schnell)

    def schedule_refresh(self, *_args) -> None:
        if self.isVisible():
            self._timer.start()
        else:
            self._stale = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()   # während sie verborgen war, wurde nicht mitgezählt

    def _scene(self):
        document = self._document
        if document is None or not shiboken6.isValid(document):
            return None
        return document.scene

    def refresh(self) -> None:
        """Baut die Liste nach dem Plan auf.

        Die Zeilen werden an Ort und Stelle geändert, nicht geleert und neu angelegt: Ein Bildschirmleser liest so
        nur vor, was sich wirklich geändert hat, und die aktuelle Zeile (der Fokus) bleibt beim selben Baustein.
        """
        self._timer.stop()
        self._stale = False
        scene = self._scene()
        current = self.list.currentItem()
        current_id = current.data(ELEMENT_ID_ROLE) if current is not None else None
        if self._pending_selection is not None:
            current_id, self._pending_selection = self._pending_selection, None
        if scene is None:
            self.list.clear()
            self.summary.setText(tr("Kein Projekt geöffnet."))
            return
        items = flow_order(scene)
        page = self._document.current_page.display_name
        count = tr("1 Baustein") if len(items) == 1 else tr("{n} Bausteine", n=len(items))
        summary = tr("Seite „{page}“: {count}", page=page, count=count)
        if self.summary.text() != summary:
            self.summary.setText(summary)
        total = len(items)
        rows = []
        for number, item in enumerate(items, start=1):
            rows.append((item.element_id, item_display(item), item_summary(item),
                         tr("Baustein {n} von {total}", n=number, total=total)))
        blocked = self.list.blockSignals(True)   # Zwischenschritte nicht als Auswahlwechsel melden
        try:
            while self.list.count() > len(rows):
                self.list.takeItem(self.list.count() - 1)
            for row, (element_id, display, spoken, position) in enumerate(rows):
                entry = self.list.item(row)
                if entry is None:
                    entry = QListWidgetItem()
                    self.list.addItem(entry)
                if entry.data(ELEMENT_ID_ROLE) != element_id:
                    entry.setData(ELEMENT_ID_ROLE, element_id)
                if entry.text() != display:
                    entry.setText(display)
                    entry.setToolTip(display)
                if entry.data(Qt.ItemDataRole.AccessibleTextRole) != spoken:
                    entry.setData(Qt.ItemDataRole.AccessibleTextRole, spoken)
                if entry.data(Qt.ItemDataRole.AccessibleDescriptionRole) != position:
                    entry.setData(Qt.ItemDataRole.AccessibleDescriptionRole, position)
            target = next((row for row, values in enumerate(rows) if values[0] == current_id), -1)
            if target < 0 and rows:
                target = min(max(self.list.currentRow(), 0), len(rows) - 1)
        finally:
            self.list.blockSignals(blocked)
        if target >= 0 and self.list.currentRow() != target:
            self.list.setCurrentRow(target)

    def show_element(self, element_id: str | None) -> None:
        """Markiert die Zeile eines Bausteins (z. B. weil er im Plan ausgewählt wurde), ohne den Fokus zu nehmen."""
        if not self.isVisible():
            return
        if self._timer.isActive() or self._stale:
            # Die Liste wird gleich neu aufgebaut (z. B. mitten in Rückgängig, wenn der Plan noch nicht fertig
            # ist): nicht jetzt einen halben Stand zeigen – die Zeile wählt der nächste Aufbau
            self._pending_selection = element_id
            if not self._timer.isActive():
                self._timer.start()
            return
        for row in range(self.list.count()):
            if self.list.item(row).data(ELEMENT_ID_ROLE) == element_id:
                if self.list.currentRow() != row:
                    self.list.setCurrentRow(row)
                return

    def element_ids(self) -> list[str]:
        return [self.list.item(row).data(ELEMENT_ID_ROLE) for row in range(self.list.count())]

    # ------------------------------------------------------------ Tastatur
    def _activate(self, entry: QListWidgetItem | None = None) -> None:
        entry = entry or self.list.currentItem()
        if entry is not None:
            self.element_activated.emit(entry.data(ELEMENT_ID_ROLE))

    def eventFilter(self, watched, event) -> bool:
        if watched is not self.list or event.type() not in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            return super().eventFilter(watched, event)
        plain = not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        keys = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape)
        if event.type() == QEvent.Type.ShortcutOverride:
            # Esc gehört sonst dem Fensterbefehl „Auswahl aufheben“ – in der Liste heißt es „zurück in den Plan“
            if plain and event.key() in keys:
                event.accept()
                return True
            return super().eventFilter(watched, event)
        if plain:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.back_requested.emit()
                return True
        return super().eventFilter(watched, event)
