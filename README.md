# BS Technik PAP Designer

Moderner Desktop-Editor für **Programmablaufpläne (PAP)** unter Windows – als
Nachfolger des PapDesigners. Die klassische PAP-Notation (Bedeutung und Form
der Bausteine) bleibt unverändert; Bedienung, Optik und Technik sind neu.

Ein Programm von **Are Schäfer** und **Linus Twardzik** für die BS Technik.

Arbeitstitel, Version und alle zentralen Namen/Standardwerte stehen in
[`app/config.py`](app/config.py) und lassen sich dort an einer Stelle ändern.

---

## Funktionsumfang

| Bereich | Umsetzung |
|---|---|
| Bausteine | Start, Ende, Eingabe, Ausgabe, Vorgang, Unterprogramm, Verzweigung, Schleife, Kommentar |
| Formen | Start/Ende = abgerundet · Eingabe/Ausgabe = Parallelogramm · Vorgang = Rechteck · Unterprogramm = Rechteck mit doppelten Seitenlinien · Verzweigung = Raute · Schleife = Schleifenbegrenzung (Beginn oben / Ende unten abgeschrägt, DIN 66001) · Kommentar = Text mit offener Klammer |
| Arbeitsfläche | praktisch unbegrenzt, dunkles Punktraster (adaptiv je Zoomstufe), präzises Einrasten |
| Zoom / Schwenken | Mausrad zoomt am Mauszeiger (25 % – 400 %), rechte oder mittlere Maustaste bzw. Leertaste + linke Maustaste schwenkt |
| Einfügen | Drag & Drop aus der Werkzeugpalette (mit eingerasteter Vorschau), Klick in der Palette, Menü „Einfügen“, Kontextmenü „Neu“ |
| Einfügen in den Ablauf | Baustein auf eine bestehende Verbindung ziehen → wird automatisch dazwischen eingefügt |
| Verbindungen | echte Objekte mit Quelle/Ziel, Anschlusspunkte je Bausteintyp, Pfeilspitzen, rechtwinklige Linienführung um Bausteine herum, Rückwärtsverbindungen/Zyklen, beschriftbar („ja“/„nein“ automatisch an Verzweigungen), mittleres Segment verschiebbar |
| Anschluss an Pfeile | Verbindungen können an bestehenden Pfeilen beginnen oder enden; der Pfeil wird dort mit einem Verbindungspunkt aufgetrennt (A → ● → B), die Richtung des Pfeils bleibt erhalten |
| Prüfung | fachlich fragwürdige Verbindungen werden **rot markiert, aber nicht verhindert**; nur technisch unmögliche Verbindungen werden abgelehnt |
| Text | Inline-Editor direkt im Baustein, **Enter = bestätigen**, **Umschalt+Enter = neue Zeile**, Esc = abbrechen; automatische Größenanpassung in festen Schritten |
| Bearbeiten | Mehrfachauswahl (Strg+Klick, Auswahlrechteck), Verschieben mit Einrasten, Pfeiltasten, Kopieren/Ausschneiden/Einfügen/Duplizieren (neue IDs, nur interne Verbindungen), Löschen inkl. Verbindungen |
| Rückgängig | vollständiges Undo/Redo über das Qt Undo Framework für alle Änderungen |
| Anordnen | links/rechts/oben/unten, mittig (Spalte/Zeile), horizontal/vertikal verteilen, am Raster ausrichten, nach vorne/hinten |
| Projekte | mehrere Projekte in Tabs, Änderungsmarkierung `*`, Nachfrage beim Schließen (Speichern / Verwerfen / Abbrechen), zuletzt geöffnete Dateien, Projekteigenschaften |
| Dateiformat | ausschließlich `.pap` (XML im Aufbau des PapDesigners, ergänzt um genaue Positionen, Anschlüsse und Ansicht; atomares Speichern, saubere Ablehnung zukünftiger Versionen, Reparatur fehlerhafter Einträge mit Hinweis) |
| Export / Druck | PNG (1×–4×), SVG, PDF, Drucken und Druckvorschau – ohne UI-Elemente, wahlweise hell (Druck) oder dunkel |
| Code erzeugen | **Extras → Code erzeugen** (Strg+Umschalt+C): Pseudocode, Python oder Java aus dem Plan; erkannte Zuweisungen, Bedingungen und Schleifenköpfe werden übersetzt, der Rest als TODO übernommen; nicht auswertbare Bedingungen werden zur Laufzeit erfragt. Die Programme rechnen wie der Schreibtischtest: echte Division, `mod`/`div`, `x^2`, kaufmännisches Runden (`round(x, 2)`), Text- und Wahrheitswert-Variablen (Java: `String`/`boolean` werden automatisch erkannt). Erkannt werden auch Schleifen mit der Prüfung in der Mitte (Eingabe → Prüfung → Meldung → zurück), das Verlassen einer Schleife aus dem Rumpf, Menüschleifen und Bausteine, in die mehrere Zweige münden; lässt sich ein Sprung nicht darstellen, hält das erzeugte Programm dort mit einer klaren Meldung an |
| Struktogramm | **Extras → Struktogramm** (Strg+Umschalt+N): derselbe Ablauf als Nassi-Shneiderman-Diagramm, Export als PNG/SVG/PDF |
| Schreibtischtest | **Extras → Schreibtischtest** (F9): Plan Schritt für Schritt ausführen (F10) oder bis zur nächsten Eingabe laufen lassen (F5); aktueller Baustein wird hervorgehoben; Variablen, Ausgaben und Schreibtischtest-Tabelle; Unterprogramme werden mit ausgeführt, Verzweigungen mit mehreren Ausgängen („1“, „2“, „sonst“ oder „< 0“, „= 0“, „> 0“) ausgewertet |
| Automatisch anordnen | **Extras → Automatisch anordnen** (Strg+L): Plan nach PAP-Konventionen ordnen (ja nach unten, nein nach rechts), ein Rückgängig-Schritt |
| Hinweise | **Extras → Hinweise** (Strg+Umschalt+H) oder Klick auf die Anzeige in der Statusleiste: rote Verbindungen, fehlender Start/Ende, unerreichbare Bausteine, Sackgassen, unbeschriftete Verzweigungsausgänge, Schleifen ohne Gegenstück, Standardtexte; Klick springt zur Stelle |
| Automatisch speichern | ein Projekt, das einmal gespeichert wurde, wird rund 2 Sekunden nach jeder Änderung von selbst in seine Datei geschrieben (spätestens nach 10 Sekunden, nie mitten in einer Texteingabe); abschaltbar unter **Datei → Automatisch speichern** |
| Sichern | noch nie gespeicherte Projekte werden jede Minute gesichert; nach einem Absturz bietet das Programm beim nächsten Start die Wiederherstellung an („Später“ behält die Sicherungen für den nächsten Start) |
| Updates | das fertige Programm prüft beim Start, ob eine neuere Version veröffentlicht wurde, und aktualisiert sich nach Rückfrage selbst (auch über **Hilfe → Nach Updates suchen**) |
| Ladebildschirm / Über | beim Start erscheint als Erstes für 6 Sekunden das Schullogo mit Urheberzeile und Version; **Hilfe → Über das Programm** nennt Urheber, Version und Erscheinungsmonat |
| Farbschema | **Ansicht → Farbschema**: dunkel oder hell (z. B. für Beamer), wird gespeichert |
| PapDesigner-Dateien | `.pap`-Dateien aus dem alten PapDesigner werden wie jedes andere Projekt geöffnet (**Datei → Öffnen** oder ins Fenster ziehen), auch mit mehreren Diagrammen/Unterprogrammen; die Anordnung wird aus dem Raster der Datei übernommen. Vor dem ersten Überschreiben einer solchen Datei fragt das Programm nach |
| Robustheit | verständliche Fehlermeldungen statt Tracebacks, Fehlerprotokoll unter `%LOCALAPPDATA%\BSTechnik\PAPDesigner\logs` |

Alle Grafiken (Bausteine, Icons, Programmsymbol) werden programmatisch mit
`QPainter` gezeichnet – es werden keine externen Bilder oder Icon-Pakete verwendet.

---

## Voraussetzungen und Start

* Windows 10/11
* Python **3.10 oder neuer** (getestet mit Python 3.14 und PySide6 6.11)

```bat
cd BSTechnikPAPDesigner
python -m pip install -r requirements.txt
python main.py
```

Eine Projektdatei direkt öffnen:

```bat
python main.py "C:\Pfad\mein_programm.pap"
```

---

## Bedienung (Kurzreferenz)

Eine vollständige Übersicht gibt es im Programm unter **Hilfe → Tastenkürzel und Bedienung** (F1).

| Aktion | Bedienung |
|---|---|
| Baustein einfügen | aus der Palette auf die Arbeitsfläche ziehen · Palette anklicken · Menü „Einfügen“ · Rechtsklick → Neu |
| Nächsten Baustein anhängen | Baustein auswählen, dann in Palette/Menü einen Typ wählen → wird darunter eingefügt und verbunden. Bei einer Verzweigung wird der nächste freie Ausgang (unten, rechts, links) genutzt; ist der Ausgang schon belegt (z. B. Schleifenbeginn), wird in den bestehenden Ablauf eingefügt und die Nachfolger rücken auf |
| In den Ablauf einfügen | Baustein aus der Palette auf eine Verbindung ziehen – nachfolgende Bausteine rücken bei Bedarf automatisch weiter |
| Verbinden | Maus über einen Baustein → Anschlusspunkte erscheinen → von einem Punkt auf den Zielbaustein **oder auf einen bestehenden Pfeil** ziehen (Ziel wird hervorgehoben, der Anschlusspunkt auf dem Pfeil als Kreis markiert) |
| An einem Pfeil beginnen | **Umschalt** gedrückt halten und am Pfeil ziehen (beim Überfahren mit Umschalt zeigt ein Kreis die Ansatzstelle) · oder vom vorhandenen Verbindungspunkt ● ziehen |
| Text bearbeiten | Doppelklick, F2, Enter oder einfach lostippen |
| Zeilenumbruch | Umschalt+Enter |
| Beschriftung einer Verbindung | Doppelklick auf Linie oder Beschriftung |
| Linienverlauf anpassen | Verbindung auswählen, mittleres Segment ziehen (Rechtsklick → „Linienführung zurücksetzen“) |
| Schwenken | rechte/mittlere Maustaste ziehen oder Leertaste + linke Maustaste |
| Zoomen | Mausrad · Strg++ / Strg+- · Strg+0 (100 %) · Strg+1 (einpassen) |
| Auswahl aufheben / Aktion abbrechen | Esc (bricht auch laufendes Verschieben, Verbinden und Texteingabe ab) |
| Kontextmenü | Rechtsklick oder Kontextmenü-Taste / Umschalt+F10 |

### PAP-Regeln und Warnungen

Das Programm prüft Verbindungen nach den PAP-Regeln, **verhindert aber keine
Verbindung aus fachlichen Gründen**. Eine möglicherweise falsche Verbindung
wird erstellt, gespeichert und **rot** dargestellt (Grund im Tooltip und in der
Statusleiste). Der Benutzer entscheidet selbst. Abgelehnt wird nur, was
technisch unmöglich ist (z. B. Anfang und Ende am selben Anschluss).

Als Warnung markiert werden:

* ein Baustein, der mit sich selbst verbunden ist,
* eingehende Verbindungen zu einem Start-, ausgehende von einem Ende-Element,
* doppelte Verbindungen zwischen denselben Bausteinen,
* ein zweiter Ausgang bei Bausteinen, die nur einen Nachfolger haben (nur die
  **Verzweigung** hat mehrere Ausgänge) – auch eine Abzweigung an einem
  Verbindungspunkt ohne Bedingung,
* Kommentar-mit-Kommentar-Verbindungen und doppelte Kommentarzuordnungen.

Bei Konflikten wird die jeweils später erstellte Verbindung markiert. Die
Markierung wird laufend neu berechnet (z. B. verschwindet sie, wenn die
erste Verbindung gelöscht wird).

Weitere Regeln:

* Verbindungen sind gerichtet; Rückwärtsverbindungen und Zyklen (Schleifen) sind unproblematisch.
* Mehrere Start-/Ende-Elemente sind möglich.
* **Verbindungspunkte** (●) entstehen beim Anschließen an einen Pfeil. Der
  aufgetrennte Pfeil läuft optisch durch; wird die Abzweigung oder der
  Verbindungspunkt gelöscht, wird der Pfeil automatisch wieder zusammengefügt.
* **Schleife**: Beim Einfügen entstehen Schleifenbeginn und Schleifenende (DIN 66001), der Schleifenrumpf wird dazwischen gesetzt. Über „Anordnen → Schleifenbeginn/-ende umschalten“ lässt sich ein Teil umwandeln.
* **Kommentare** gehören nicht zum Ablauf. Sie können frei platziert und optional per gestrichelter Linie einem Baustein zugeordnet werden.

---

## Dateiformat `.pap`

`.pap` ist das einzige Projektformat: Speichern, Öffnen, automatisches
Sichern und die Zwischenablage verwenden dieselbe Darstellung. Die Datei ist
UTF-8-kodiertes XML im Aufbau des PapDesigners:

```xml
<?xml version="1.0" encoding="utf-8"?>
<FRAME GUID="2FB25471-B62C-4EE6-BD43-F819C095ACF8" FORMAT="0000" APP_VERSION="2.2.0.8" CHECKSUM="UNSIGNED"
       xmlns:bst="urn:bstechnik:pap-designer" bst:VERSION="1" bst:APP="BS Technik PAP Designer" bst:APP_VERSION="1.5.0">
  <PROJECT FORMAT="1.00" NAME="…" AUTHOR="…" CREATED="2026.09.24 21:55:01" MODIFIED="…"
           bst:DESCRIPTION="…" bst:CREATED="2026-09-24T21:55:01+02:00" bst:MODIFIED="…">
    <DIAGRAMS>
      <DIAGRAM FORMAT="1.00" ID="0" NAME="…" CREATED="…" MODIFIED="…">
        <LAYOUT FORMAT="1.00" COLUMNS="2" ROWS="12" bst:GRID_SIZE="20" bst:GRID_VISIBLE="True"
                bst:SNAP_TO_GRID="True" bst:ZOOM="1" bst:VIEW_X="0" bst:VIEW_Y="0">
          <ENTRIES>
            <ENTRY COLUMN="0" ROW="0" ANCHOR="True" bst:GENERATED="True">
              <FIGURE SUBTYPE="PapTitle" FORMAT="1.00" ID="0"><TEXT><![CDATA[…]]></TEXT></FIGURE>
            </ENTRY>
            <ENTRY COLUMN="0" ROW="1" bst:X="0" bst:Y="120" bst:WIDTH="160" bst:HEIGHT="60">
              <FIGURE SUBTYPE="PapActivity" FORMAT="1.00" ID="1" bst:UID="…">
                <TEXT><![CDATA[Berechne Mittelwert]]></TEXT>
              </FIGURE>
            </ENTRY>
            <ENTRY COLUMN="0" ROW="2" bst:X="0" bst:Y="240" bst:WIDTH="160" bst:HEIGHT="60">
              <FIGURE SUBTYPE="PapOutput" FORMAT="1.00" ID="2" bst:UID="…">
                <TEXT><![CDATA[Mittelwert ausgeben]]></TEXT>
              </FIGURE>
            </ENTRY>
          </ENTRIES>
        </LAYOUT>
        <CONNECTIONS>
          <CONNECTION FORMAT="1.00" ID="3" FROM="1" TO="2" TEXT="" bst:UID="…"
                      bst:SOURCE_PORT="bottom" bst:TARGET_PORT="top" bst:PATH="0,150 0,210" />
        </CONNECTIONS>
      </DIAGRAM>
    </DIAGRAMS>
  </PROJECT>
</FRAME>
```

* Elemente und Attribute **ohne Präfix** sind die des PapDesigners: Bausteine
  liegen auf einem Raster (`COLUMN`/`ROW`), tragen fortlaufende Nummern (`ID`)
  und einen Typ (`SUBTYPE`); Verbindungen verweisen mit `FROM`/`TO` auf diese
  Nummern und tragen ihre Beschriftung in `TEXT`.
* Attribute mit dem Präfix **`bst:`** ergänzen, was das Raster nicht ausdrücken
  kann: Mittelpunkt und Größe (`X`, `Y`, `WIDTH`, `HEIGHT`), Ebene (`Z`),
  eindeutige IDs (`UID`), Anschlüsse (`SOURCE_PORT`, `TARGET_PORT`), manuelle
  Linienführung (`ROUTE_AXIS`, `ROUTE_VALUE`), den angezeigten Linienverlauf
  (`PATH` = Eckpunkte `x,y`; damit verläuft jede Linie nach dem Öffnen genau
  wie beim Speichern), Verbindungspunkte (`TRUNK_IN`, `TRUNK_OUT` = IDs der
  beiden Teile des aufgetrennten Pfeils), Beschreibung, genaue Zeitpunkte,
  Raster- und Ansichtseinstellungen. `PROPERTIES` nimmt weitere Eigenschaften
  eines Bausteins als JSON-Objekt auf; das Programm selbst setzt derzeit keine.
* `SUBTYPE` ∈ `PapStart, PapEnd, PapInput, PapOutput, PapActivity` (Vorgang),
  `PapModule` (Unterprogramm), `PapCondition` (Verzweigung), `PapLoopStart`,
  `PapLoopEnd`, `PapConnector` (Verbindungspunkt), `PapComment`.
* Enthält eine Datei die `bst:`-Angaben, wird das Projekt exakt
  wiederhergestellt (Bausteine, Verbindungen und ihre Reihenfolge, Positionen,
  Eigenschaften). Fehlen sie – Datei direkt aus dem PapDesigner –, wird die
  Anordnung aus dem Raster abgeleitet; beim nächsten Speichern kommen die
  Angaben dazu. Vor dem ersten Überschreiben einer solchen Datei fragt das
  Programm nach (Überschreiben / Speichern unter / Abbrechen), weil die Datei
  dabei neu geschrieben wird und mehrere Diagramme zu einem Plan werden.
* Geöffnet werden ausschließlich Dateien mit der Endung `.pap` (Dialog,
  Befehlszeile, Hineinziehen, „Zuletzt geöffnet“); gespeichert wird immer als
  `.pap`.
* Fehlerhafte Angaben einer Datei (Position, Größe, Ebene, Anschlüsse,
  Linienführung, IDs, Rastergröße) werden beim Öffnen korrigiert und gemeldet;
  ungültige Ansichtsangaben (Zoom, Bildmitte) werden ohne Meldung ersetzt.
* Der Titel in Zeile 0 (`bst:GENERATED`) ist die Ankerzelle, die der
  PapDesigner je Diagramm erwartet; er ist kein Baustein des Projekts.
* Warnungen (rote Verbindungen) werden nicht gespeichert, sondern beim Öffnen
  aus den gespeicherten Bausteinen und Verbindungen neu berechnet – sie sind
  nach dem Laden dieselben wie vor dem Speichern.
* Zeichen, die XML nicht darstellen kann (Steuerzeichen aus eingefügtem
  Text), übernimmt schon die Texteingabe nicht: weiche Zeilenumbrüche werden
  zu normalen, der Rest entfällt. Angezeigt wird nur, was auch gespeichert wird.
* Neue Formatversionen: `CURRENT_FORMAT_VERSION` in `app/fileformat/project.py`
  erhöhen; Dateien mit einer höheren `bst:VERSION` werden mit einer
  verständlichen Meldung abgelehnt.

---

## Architektur

```
main.py                      Startpunkt
app/
  config.py                  zentrale Konstanten (Programmname, Dateiendung, Raster, Zoom …)
  styles.py                  Farbschemata (dunkel/hell) und Stylesheet
  icons.py                   selbst gezeichnete Vektor-Icons
  main_window.py             Hauptfenster: Menüs, Werkzeugleiste, Tabs, Statusleiste, Dateioperationen
  actions.py                 alle Befehle mit Text, Icon und Tastenkürzel
  canvas.py                  Arbeitsfläche (QGraphicsView): Raster, Zoom, Schwenken, Drag & Drop
  scene.py                   Diagrammszene (QGraphicsScene): Registry, Snap, Verbinden, Inline-Editor
  document.py                ein Projekt (Szene + Undo-Stapel + Metadaten + Dateipfad)
  palette.py                 Werkzeugpalette mit Formvorschau
  inline_editor.py           Inline-Texteditor
  clipboard.py               Kopieren/Einfügen/Duplizieren
  alignment.py               Ausrichten/Verteilen
  export.py                  PNG/SVG/PDF-Export und Druck
  errors.py                  Fehlerbehandlung und Protokoll
  file_association.py        optionale Registrierung von .pap (Benutzerebene)
  settings_store.py          zuletzt geöffnete Dateien, Fensterzustand
  model/                     grafikunabhängiges Datenmodell, Bausteintypen, Verbindungsregeln
                             (rules.py: Warnungen vs. technisch blockierende Fehler)
  analysis/                  Ablaufgraph (graph.py), Strukturbaum (ast.py, structure.py:
                             Folge/Verzweigung/Schleifen erkennen), Deutung der Bausteintexte (text.py),
                             Variablen und ihre Typen (variables.py – gemeinsam für Schreibtischtest und Code)
  codegen/                   Code-Erzeugung (Pseudocode, Python, Java) und Dialog
  nsd/                       Struktogramm (Nassi-Shneiderman): Darstellung, Export, Dialog
  simulation/                Schreibtischtest: sicherer Ausdrucksauswerter, Ablauf-Engine, Panel
  layout/                    automatisches Anordnen
  diagnostics/               Hinweisliste: Prüfungen und Panel
  autosave.py                automatisches Sichern und Wiederherstellen
  splash.py                  Ladebildschirm (Schullogo, Urheberzeile, Version)
  updater.py                 Update: Version prüfen, Paket laden und prüfen, Programmordner ersetzen
  update_dialogs.py          Oberfläche dazu (Nachfrage, Fortschritt)
  resources.py               Zugriff auf mitgelieferte Dateien (assets)
  theme.py                   Umschalten des Farbschemas
  items/                     Bausteine (eine Klasse je Typ, inkl. Verbindungspunkt), Formen, Drop-Vorschau
  connections/               Verbindung, Beschriftung, Linienführung (routing.py),
                             Verbindungsziele Block/Knoten/Pfeil (endpoints.py)
  commands/                  Undo/Redo-Befehle
  dialogs/                   Projekteigenschaften, Über, Tastenkürzel, Exportoptionen
  fileformat/                Lesen und Schreiben von .pap (serializer.py), Kennungen und Version (project.py)
assets/                      erzeugte Programm-/Dateisymbole (.ico/.png), Schullogo
tools/generate_icons.py      erzeugt die Symbole in assets/
tools/make_release.py        erzeugt Setup-Datei und Update-Paket und lädt sie bei GitHub hoch
build_exe.bat                baut das Programm (dist\BSTechnikPAPDesigner)
release.bat                  baut und veröffentlicht eine neue Version als Update
tests/                       automatische Tests (pytest)
installer/                   Inno-Setup-Skript für die Setup-Datei (inkl. Dateizuordnung)
```

Grafik und Daten sind getrennt: Jedes grafische Objekt hält eine Referenz
auf seine Modelldaten (`ElementData`, `ConnectionData`) und hält diese aktuell.
Der Serializer arbeitet ausschließlich mit dem Modell.

---

## Tests

```bat
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Ist ein JDK installiert (`javac` im PATH, unter `JAVA_HOME` oder im üblichen
Installationsordner), wird der erzeugte Java-Code in den Tests wirklich
übersetzt und ausgeführt: `tests/test_three_way.py` und
`tests/test_structure_flows.py` vergleichen für viele Pläne die Ausgabe von
Schreibtischtest, erzeugtem Python und erzeugtem Java. Ohne JDK werden diese
Java-Läufe übersprungen.

Die Tests laufen unter Windows mit der nativen Qt-Plattform (echte
Schriftmetriken), öffnen dabei aber keine sichtbaren Fenster. Neben gezielten
Tests für Dateiformat, Regeln, Linienführung, Zwischenablage und Bedienung
enthält `tests/test_fuzz_undo.py` einen Zufallstest, der hunderte gemischte
Operationen ausführt, nach jedem Schritt die Konsistenz prüft, alles
vollständig rückgängig macht und wiederholt und das Ergebnis per
Speichern/Laden vergleicht.

---

## EXE erstellen

```bat
build_exe.bat
```

oder manuell:

```bat
python -m pip install -r requirements-dev.txt
python tools\generate_icons.py
python -m PyInstaller --noconfirm BSTechnikPAPDesigner.spec
```

Ergebnis: `dist\BSTechnikPAPDesigner\BSTechnikPAPDesigner.exe`
(der gesamte Ordner `dist\BSTechnikPAPDesigner` gehört zur Anwendung, ca. 110 MB).
Die Konfiguration wurde mit PyInstaller 6.22 und PySide6 6.11 unter Python 3.14 erfolgreich getestet.

Die Zwischendateien des Baus landen im Temp-Ordner, nicht im Projektordner.

### Weitergeben: die Setup-Datei

Weitergegeben wird eine einzige Datei, `BSTechnikPAPDesigner-Setup.exe`. Sie
installiert das Programm ohne Administratorrechte in das Benutzerprofil, legt
einen Eintrag im Startmenü an und verknüpft auf Wunsch `.pap`-Dateien mit dem
Programm. Die jeweils neueste Fassung steht immer unter

    https://github.com/Medj3d/BSTechnikPAPDesigner/releases/latest/download/BSTechnikPAPDesigner-Setup.exe

Die Setup-Datei entsteht mit `release.bat` (siehe unten) und braucht dafür
[Inno Setup 6](https://jrsoftware.org/isdl.php) auf dem Rechner, auf dem
gebaut wird. Wer im Setup „für alle Benutzer“ wählt (Administrator, z. B. in
der Schule), installiert nach `C:\Programme`; dort kann sich das Programm
nicht selbst aktualisieren und weist nur in der Statuszeile auf neue Versionen
hin. Der Administrator installiert sie dann mit dem nächsten Setup.

### Neue Version als Update veröffentlichen

Das fertige Programm sieht beim Start in den Veröffentlichungen („Releases“)
des GitHub-Projekts nach, ob es eine höhere Version gibt, und bietet dann an,
sich zu aktualisieren. Eigene Dateien im Programmordner bleiben dabei
erhalten; schlägt etwas fehl, bleibt die bisherige Version bestehen.

Einmalig einrichten:

1. In [`app/config.py`](app/config.py) unter `UPDATE_REPOSITORY` das
   GitHub-Projekt eintragen (`"Besitzer/Name"`). Das Projekt muss öffentlich
   sein, damit Schulrechner die Veröffentlichungen ohne Anmeldung lesen können.
2. Die GitHub-Befehlszeile installieren und einmal `gh auth login` ausführen.

Für jede neue Version:

1. In `app/config.py` `APP_VERSION` erhöhen (z. B. `1.5.0` → `1.6.0`) und
   `APP_RELEASE_DATE` anpassen.
2. `release.bat "Was ist neu"` ausführen. Das baut das Programm, erzeugt in
   `dist` die Setup-Datei, das Update-Paket `BSTechnikPAPDesigner.zip` und
   `version.json` und lädt alles als Version `v…` hoch. (Nur bauen, ohne
   Hochladen: `python tools\make_release.py --ohne-upload`.)

Voraussetzungen auf dem Zielrechner: Internetzugang zu `github.com` und
Schreibrechte im Programmordner (also nicht unter `C:\Programme` ohne
Administratorrechte). Fehlt der Internetzugang, läuft das Programm unverändert
weiter. Fehlen die Schreibrechte, stellt es keine Frage, die sich nicht erfüllen
lässt: Beim Start steht nur ein ruhiger Hinweis in der Statuszeile („Neue Version
… verfügbar – bitte beim Administrator melden“); **Hilfe → Nach Updates suchen**
nennt zusätzlich den Link zur neuen Setup-Datei.

### Dateiendung `.pap` im System registrieren

Ist der alte PapDesigner noch installiert, übernimmt die Registrierung dessen
Zuordnung: `.pap`-Dateien öffnen sich danach mit diesem Programm.

* **Mit der Setup-Datei (empfohlen):** Im Setup ist „.pap-Dateien mit diesem
  Programm öffnen“ vorausgewählt; es trägt die Zuordnung inklusive Dateisymbol
  ein und entfernt sie bei der Deinstallation wieder.
* **Ohne Installer:** im Programm **Hilfe → Dateityp registrieren …** wählen.
  Die Zuordnung wird nur für den aktuellen Windows-Benutzer eingetragen
  (`HKEY_CURRENT_USER\Software\Classes`, keine Administratorrechte nötig).

---

## Versionen

Die Zahl nach dem Punkt zählt die Erweiterungen seit dem Grundprogramm, die
dritte Zahl kleine Nachbesserungen.

| Version | Zeitraum | Inhalt |
|---|---|---|
| 1.0 | September 2026 | Grundprogramm: Editor für Programmablaufpläne |
| 1.1 | 30.09.2026 | fragwürdige Verbindungen werden rot markiert statt verhindert; Verbindungen können an bestehenden Pfeilen ansetzen |
| 1.2 | 30.09.–01.10.2026 | PapDesigner-Dateien lesen, Code erzeugen, Schreibtischtest, automatisch anordnen, Hinweisliste, automatisches Sichern, Struktogramm, helles Farbschema |
| 1.3 | 01.–06.10.2026 | erzeugter Java-Code wird übersetzt, ausgeführt und mit Schreibtischtest und Python verglichen; rund 75 Fehler behoben |
| 1.4 | 07.10.2026 | `.pap` als einziges Projektformat |
| 1.5 | 07.10.2026 | Urheber und Version im Über-Dialog, Ladebildschirm, automatisches Speichern, Updates |
| 1.5.1 | 07.10.2026 | Ladebildschirm erscheint früher und bleibt 6 Sekunden stehen |
| 1.5.2 | 08.10.2026 | Setup-Datei zum Weitergeben und Installieren |
| 1.5.3 | 08.10.2026 | ohne Schreibrechte im Programmordner (z. B. Installation für alle Benutzer) nur noch ein Hinweis in der Statuszeile statt einer Update-Frage |

---

## Hinweise

* Die Spezifikation endete bei Abschnitt 58 („Drucken“). Umgesetzt wurden
  Drucken und Druckvorschau: das Diagramm wird seitenfüllend auf eine Seite
  gedruckt (automatisch Hoch-/Querformat).
* Einstellungen wie „Raster anzeigen“ und „Einrasten“ werden mit dem Projekt
  gespeichert, gelten aber als Ansichtseinstellung und markieren das Projekt
  nicht als geändert.
