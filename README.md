# BS Technik PAP Designer

Moderner Desktop-Editor für **Programmablaufpläne (PAP)** unter Windows – als
Nachfolger des PapDesigners. Die klassische PAP-Notation (Bedeutung und Form
der Bausteine) bleibt unverändert;  Bedienung, Optik und Technik sind neu.

Ein Programm von **Are Schäfer** und **Linus Twardzik** für die BS Technik.

Arbeitstitel, Version und alle zentralen Namen/Standardwerte stehen in
[`app/config.py`](app/config.py) und lassen sich dort an einer Stelle ändern.

---

## Funktionsumfang

| Bereich | Umsetzung |
|---|---|
| Bausteine | Start, Ende, Eingabe, Ausgabe, Vorgang, Unterprogramm, Verzweigung, Schleife, Kommentar |
| Unterprogramme | jedes Projekt hat neben dem **Hauptprogramm** beliebig viele **Unterprogramme auf eigenen Seiten** (Reiter unter der Arbeitsfläche, wie im PapDesigner). **„+ Unterprogramm“** bzw. **Einfügen → Neues Unterprogramm** (Strg+Umschalt+U) legt eine Seite mit Start „Name“ → Ende an. Ein Unterprogramm-Baustein mit diesem Namen ruft es auf (auch mit Argumenten, z. B. `berechne(x, y)`); **Strg+Doppelklick** oder Rechtsklick auf den Baustein öffnet das Unterprogramm bzw. legt es an. Doppelklick auf einen Seitenreiter benennt um – alle Aufrufe werden mit angepasst. Rechtsklick auf den Reiter: **Duplizieren, Kopieren, Ausschneiden, Einfügen** (auch in ein anderes Projekt), **Verschieben** (oder Reiter ziehen), **„Aufgerufen von“** (springt zu jedem Aufruf) und Löschen. **Bearbeiten → Auswahl in Unterprogramm auslagern** (Strg+Alt+U) verschiebt markierte Bausteine auf eine eigene Seite und setzt an ihre Stelle den Aufruf. **Alt+← / Alt+→** wechselt zurück und vorwärts zwischen den zuletzt gezeigten Seiten. Schreibtischtest, Code, Struktogramm, Hinweise, PDF und Druck umfassen alle Seiten |
| Formen | Start/Ende = abgerundet · Eingabe/Ausgabe = Parallelogramm · Vorgang = Rechteck · Unterprogramm = Rechteck mit doppelten Seitenlinien · Verzweigung = Raute · Schleife = Schleifenbegrenzung (Beginn oben / Ende unten abgeschrägt, DIN 66001) · Kommentar = Text mit offener Klammer |
| Arbeitsfläche | praktisch unbegrenzt, dunkles Punktraster (adaptiv je Zoomstufe), präzises Einrasten |
| Zoom / Schwenken | Mausrad zoomt am Mauszeiger (25 % – 400 %), rechte oder mittlere Maustaste bzw. Leertaste + linke Maustaste schwenkt |
| Einfügen | Drag & Drop aus der Werkzeugpalette (mit eingerasteter Vorschau), Klick in der Palette, Menü „Einfügen“, Kontextmenü „Neu“, **Tasten 1–9** (in der Reihenfolge der Palette, dort angezeigt) |
| Neue Projekte | beginnen mit Start → Ende; neue Bausteine kommen dazwischen (ohne Auswahl vor das Ende). Beides bleibt löschbar, abschaltbar in den Einstellungen |
| Suchleiste | oben rechts (Strg+K): findet Funktionen, Einstellungen und Bausteine aller Seiten, unabhängig von Groß-/Kleinschreibung und Umlauten; Enter führt aus bzw. springt hin |
| Einstellungen | **Extras → Einstellungen** (Strg+,): Ein/Aus-Schalter und alle Tastenkürzel frei belegbar, je Funktion zwei Tasten, durchsuchbar; eine schon vergebene Taste wechselt zur neuen Funktion, „Zurücksetzen“ stellt den Standard wieder her |
| Einfügen in den Ablauf | Baustein auf eine bestehende Verbindung ziehen → wird automatisch dazwischen eingefügt |
| Schleifen | **Einfügen → Schleife mit Kopfbedingung** („solange …“) bzw. **mit Fußbedingung** („wiederhole … bis …“) legt beide Teile mit passenden Platzhaltern an; außerdem Zählschleifen („für i = 1 bis n“), „n mal“ und Schleifen aus Verzweigung und Pfeil zurück |
| Verbindungspunkte | Rechtsklick auf eine Verbindung → **Verbindungspunkt hier einfügen** (als Eckpunkt zum Führen der Linie oder als Abzweig für weitere Pfeile) |
| Verbindungen | echte Objekte mit Quelle/Ziel, Anschlusspunkte je Bausteintyp, Pfeilspitzen, rechtwinklige Linienführung um Bausteine herum, Rückwärtsverbindungen/Zyklen, beschriftbar („ja“/„nein“ automatisch an Verzweigungen), abgerundete Ecken, mehr Abstand zu Bausteinen und anderen Linien |
| Pfeile frei führen | jedes Linienstück und jede Ecke lässt sich ziehen, auch eine gerade Linie; Rechtsklick → **Knick hier einfügen**. Die Linie bleibt rechtwinklig, nur das Aussehen ändert sich, nie der Ablauf. **Linienführung zurücksetzen** führt sie wieder automatisch |
| Pfeile umhängen | ausgewählten Pfeil am Punkt an seinem Ende auf einen anderen Baustein oder Pfeil ziehen; die Beschriftung bleibt |
| Pfeil ins Leere | beim Loslassen im Leeren fragt ein **Schnellmenü**, welcher Baustein dort entstehen soll. Mit dem Schalter **Pfeil bleibt im Leeren stehen** (Standard: aus) bleibt der Pfeil stattdessen mit losem Ende stehen und ist rot, bis er angeschlossen ist |
| Anschluss an Pfeile | Verbindungen können an bestehenden Pfeilen beginnen oder enden; der Pfeil wird dort mit einem Verbindungspunkt aufgetrennt (A → ● → B), die Richtung des Pfeils bleibt erhalten |
| Prüfung | sicher falsche Verbindungen werden **rot**, auffällige **gelb** markiert, aber nicht verhindert; ein Warnzeichen auf dem Pfeil nennt beim Überfahren den Grund. Eine Warteschleife an einer Verzweigung oder zwei Ausgänge zum selben Ziel sind kein Fehler. Die **erweiterte Prüfung** (Standard: aus) markiert zusätzlich unbeschriftete Ausgänge, doppelte Beschriftungen und Wege ohne Ende. Nur technisch unmögliche Verbindungen werden abgelehnt |
| Text | Inline-Editor direkt im Baustein, **Enter = bestätigen**, **Umschalt+Enter oder Strg+Enter = neue Zeile**, Esc = abbrechen; automatische Größenanpassung in festen Schritten. **Sonderzeichen** (≤ ≥ ≠ ← × √ π ∧ ∨ ¬ „“ …) über Rechtsklick in der Texteingabe oder **Bearbeiten → Sonderzeichen**; **~** markiert einen bedingten Trennstrich (dort darf ein langes Wort umbrochen werden, wie im PapDesigner) |
| Bearbeiten | Mehrfachauswahl (Strg+Klick, Auswahlrechteck), Verschieben mit Einrasten, Pfeiltasten, Kopieren/Ausschneiden/Einfügen/Duplizieren (neue IDs, nur interne Verbindungen), **Kopieren per Strg+Ziehen**, **Baustein umwandeln** (Rechtsklick → „Ändern in“, Text und Verbindungen bleiben), Löschen inkl. Verbindungen; beschriftet man einen Ausgang einer Verzweigung mit ja/nein (wahr/falsch, yes/no …), bekommt der andere das Gegenwort |
| Rückgängig | vollständiges Undo/Redo über das Qt Undo Framework für alle Änderungen |
| Anordnen | links/rechts/oben/unten, mittig (Spalte/Zeile), horizontal/vertikal verteilen, am Raster ausrichten, nach vorne/hinten |
| Projekte | mehrere Projekte in Tabs, Änderungsmarkierung `*`, Nachfrage beim Schließen (Speichern / Verwerfen / Abbrechen), zuletzt geöffnete Dateien, Projekteigenschaften |
| Dateiformat | ausschließlich `.pap` (XML im Aufbau des PapDesigners, ergänzt um genaue Positionen, Anschlüsse und Ansicht; atomares Speichern, saubere Ablehnung zukünftiger Versionen, Reparatur fehlerhafter Einträge mit Hinweis) |
| Export / Druck | PNG (1×–4×), SVG, PDF, Drucken und Druckvorschau – ohne UI-Elemente, wahlweise hell (Druck) oder dunkel |
| Als Bild kopieren | **Strg+C** legt die Auswahl zusätzlich als Bild in die Zwischenablage; **Bearbeiten → Als Bild kopieren** (Strg+Umschalt+B) kopiert nur das Bild – der Auswahl oder ohne Auswahl der ganzen Seite –, hell und ohne Raster, zum direkten Einfügen in Word, OneNote oder PowerPoint. Auch das Struktogramm lässt sich als Bild kopieren |
| Code erzeugen | **Extras → Code erzeugen** (Strg+Umschalt+C): Pseudocode, Python oder Java aus dem Plan; erkannte Zuweisungen, Bedingungen und Schleifenköpfe werden übersetzt, der Rest als TODO übernommen; nicht auswertbare Bedingungen werden zur Laufzeit erfragt. Die Programme rechnen wie der Schreibtischtest: echte Division, `mod`/`div`, `x^2`, kaufmännisches Runden (`round(x, 2)`), Text- und Wahrheitswert-Variablen (Java: `String`/`boolean` werden automatisch erkannt). Erkannt werden auch Schleifen mit der Prüfung in der Mitte (Eingabe → Prüfung → Meldung → zurück), das Verlassen einer Schleife aus dem Rumpf, Menüschleifen und Bausteine, in die mehrere Zweige münden; lässt sich ein Sprung nicht darstellen, hält das erzeugte Programm dort mit einer klaren Meldung an |
| Struktogramm | **Extras → Struktogramm** (Strg+Umschalt+N): derselbe Ablauf als Nassi-Shneiderman-Diagramm, Export als PNG/SVG/PDF |
| Schreibtischtest | **Extras → Schreibtischtest** (F9): Plan Schritt für Schritt ausführen (F10), **Schritt zurück** (Strg+F10), **automatisch abspielen** mit einstellbarem Tempo (F6, hält bei Eingaben an) oder bis zur nächsten Eingabe laufen lassen (F5); aktueller Baustein wird hervorgehoben; Variablen, Ausgaben und Schreibtischtest-Tabelle mit den Spalten Bedingung (ja/nein bzw. gewählter Ausgang) und Ausgabe – kopierbar für Word/Excel und als CSV speicherbar; Unterprogramme werden mit ausgeführt, Verzweigungen mit mehreren Ausgängen („1“, „2“, „sonst“ oder „< 0“, „= 0“, „> 0“) ausgewertet |
| Automatisch anordnen | **Extras → Automatisch anordnen** (Strg+L): Plan nach PAP-Konventionen ordnen (ja nach unten, nein nach rechts), ein Rückgängig-Schritt. Reine Eckpunkte fallen weg, Zusammenführungen stehen über ihrem Ziel, die Anschlüsse passen zur neuen Lage, Kommentare ohne Linie wandern mit dem nächsten Baustein; der Ablauf bleibt unverändert |
| Hinweise | **Extras → Hinweise** (Strg+Umschalt+H) oder Klick auf die Anzeige in der Statusleiste: rote Verbindungen, fehlender Start/Ende, unerreichbare Bausteine, Sackgassen, unbeschriftete Verzweigungsausgänge, Schleifen ohne Gegenstück, Standardtexte; Klick springt zur Stelle |
| Automatisch speichern | ein Projekt, das einmal gespeichert wurde, wird rund 2 Sekunden nach jeder Änderung von selbst in seine Datei geschrieben (spätestens nach 10 Sekunden, nie mitten in einer Texteingabe); abschaltbar unter **Datei → Automatisch speichern** |
| Sichern | noch nie gespeicherte Projekte werden jede Minute gesichert; nach einem Absturz bietet das Programm beim nächsten Start die Wiederherstellung an („Später“ behält die Sicherungen für den nächsten Start) |
| Sicherungskopie | vor dem ersten Überschreiben einer Datei in einer Sitzung bleibt ihr bisheriger Stand als `Name.pap-backup` daneben erhalten – auch beim automatischen Speichern und für Dateien aus dem PapDesigner; abschaltbar unter **Datei → Sicherungskopie anlegen**. Eine Sicherungskopie öffnet sich über **Datei → Öffnen** (Dateityp „Sicherungskopien“) als unbenannte Kopie |
| Standard-Autor | der zuletzt in den Projekteigenschaften eingetragene Autor wird für neue Projekte übernommen |
| Updates | das fertige Programm prüft beim Start, ob eine neuere Version veröffentlicht wurde, und aktualisiert sich nach Rückfrage selbst, auch ohne Schreibrechte im Programmordner (z. B. bei Installation für alle Benutzer); auch über **Hilfe → Nach Updates suchen**. Die Prüfung beim Start lässt sich unter **Hilfe → Beim Start nach Updates suchen** abschalten; Administratoren schalten Updates zentral ab (siehe „Schulbetrieb“) |
| Ladebildschirm / Über | beim Start erscheint als Erstes für 6 Sekunden das Schullogo mit Urheberzeile und Version; **Hilfe → Über das Programm** nennt Urheber, Version und Erscheinungsmonat |
| Farbschema | **Ansicht → Farbschema**: dunkel oder hell (z. B. für Beamer), wird gespeichert |
| Präsentationsansicht | **Ansicht → Präsentationsansicht** (F11): nur der Plan mit Seitenleiste im Vollbild, ohne Menüs und Fenster; Esc oder F11 beendet und stellt alles wieder her |
| Lernbeispiele | **Hilfe → Lernbeispiele**: fünf aufeinander aufbauende Projekte wie die Tutorials des PapDesigners (Ablaufplan, Verzweigungen, Schleifen, Unterprogramme, Programmierung), mit erklärenden Kommentaren; sie öffnen sich als unbenannte Kopie und laufen im Schreibtischtest durch |
| Sprachen | **Ansicht → Sprache / Language**: Deutsch, English, Français, Español, Português (Brasil), Русский, العربية, 中文 und 日本語; „Automatisch“ richtet sich nach der Sprache von Windows. Die Sprache gilt nach einem Neustart, den das Programm gleich anbietet (gespeicherte Projekte werden danach wieder geöffnet). Arabisch wird von rechts nach links dargestellt. Pläne aus jeder Sprache lassen sich in jeder Sprache öffnen: Standardtexte und die Beschriftungen ja/nein/sonst werden in allen Sprachen erkannt |
| Ein Fenster | wird eine weitere Datei geöffnet (Doppelklick im Explorer, „Öffnen mit“), erscheint sie als neuer Reiter im schon laufenden Programm statt in einem zweiten Fenster; das Fenster kommt dabei nach vorne |
| PapDesigner-Dateien | `.pap`-Dateien aus dem alten PapDesigner werden wie jedes andere Projekt geöffnet (**Datei → Öffnen** oder ins Fenster ziehen), weitere Diagramme der Datei werden zu Unterprogramm-Seiten. Wie im PapDesigner heißt ein Unterprogramm wie sein Diagramm (dessen Start darf einfach „Start“ heißen), und ein Aufruf passt über den Namen vor der Klammer: „bool ok := isLeapYear(jahr)“ ruft das Diagramm „bool isLeapYear(int year)“; Leerzeichen und Bindestriche zählen dabei nicht. Rechtsklick auf einen Unterprogramm-Baustein → „Ruft auf“ wählt ein vorhandenes Unterprogramm. Die Anordnung wird aus dem Raster der Datei übernommen. Vor dem ersten Überschreiben einer solchen Datei fragt das Programm nach |
| Robustheit | verständliche Fehlermeldungen statt Tracebacks, Fehlerprotokoll unter `%LOCALAPPDATA%\BSTechnik\PAPDesigner\logs` |

Alle Grafiken (Bausteine, Icons, Programmsymbol) werden programmatisch mit
`QPainter` gezeichnet – es werden keine externen Bilder oder Icon-Pakete verwendet.

---

## Voraussetzungen und Start

* Windows 10/11 oder Linux (fertiges Programm als AppImage, siehe [Linux-Version](#linux-version-appimage))
* Python **3.12 oder neuer** (getestet mit Python 3.15 unter Windows und 3.13 unter Linux, PySide6 6.12).
  Mit PySide6 6.12 stürzt Python 3.10 ab – unter Ubuntu 22.04 deshalb Python 3.13 nehmen, etwa aus dem
  deadsnakes-PPA.

```bat
cd BSTechnikPAPDesigner
python -m pip install -r requirements.txt
python main.py
```

Eine Projektdatei direkt öffnen:

```bat
python main.py "C:\Pfad\mein_programm.pap"
```

Läuft das Programm schon, öffnet dieser Aufruf die Datei dort als weiteren
Reiter. Startoptionen (auch für die fertige `BSTechnikPAPDesigner.exe`):

| Option | Wirkung |
|---|---|
| `--neues-fenster` | startet ein zweites, eigenständiges Fenster |
| `--sprache <Code>` | Sprache nur für diesen Start: `de`, `en`, `fr`, `es`, `pt`, `ru`, `ar`, `zh`, `ja` |

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
| Zeilenumbruch | Umschalt+Enter oder Strg+Enter |
| Beschriftung einer Verbindung | Doppelklick auf Linie oder Beschriftung |
| Linienverlauf anpassen | Verbindung auswählen, mittleres Segment ziehen (Rechtsklick → „Linienführung zurücksetzen“) |
| Schwenken | rechte/mittlere Maustaste ziehen oder Leertaste + linke Maustaste |
| Zoomen | Mausrad · Strg++ / Strg+- · Strg+0 (100 %) · Strg+1 (einpassen) |
| Auswahl aufheben / Aktion abbrechen | Esc (bricht auch laufendes Verschieben, Verbinden und Texteingabe ab) |
| Kontextmenü | Rechtsklick oder Kontextmenü-Taste / Umschalt+F10 |
| Unterprogramm anlegen | „+ Unterprogramm“ unter der Arbeitsfläche · Strg+Umschalt+U · Rechtsklick auf einen Unterprogramm-Baustein → „Unterprogramm … anlegen“ |
| Unterprogramm öffnen | Seitenreiter anklicken · Strg+Doppelklick auf den Unterprogramm-Baustein · Strg+Bild ab / Strg+Bild auf blättert durch die Seiten |
| Unterprogramm umbenennen / löschen | Doppelklick bzw. Rechtsklick auf den Seitenreiter (Umbenennen passt auch alle Aufrufe an) |
| Seiten kopieren / verschieben | Rechtsklick auf den Seitenreiter → Duplizieren, Kopieren, Ausschneiden, Einfügen, nach links/rechts · Reiter ziehen |
| Auswahl auslagern | Bausteine markieren → Strg+Alt+U (oder Rechtsklick → „Auswahl in Unterprogramm auslagern …“) |
| Zurück / vorwärts | Alt+← / Alt+→ (z. B. vom geöffneten Unterprogramm zurück zum Aufruf) |
| Präsentationsansicht | F11 (Esc beendet) |

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
  Linienführung (`ROUTE_AXES`, in älteren Dateien `ROUTE_AXIS` und `ROUTE_VALUE`), den angezeigten Linienverlauf
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
  dabei neu geschrieben wird.
* **Unterprogramme**: Das erste `DIAGRAM` ist das Hauptprogramm, jedes weitere
  eine Unterprogramm-Seite (wie im PapDesigner); `NAME` ist der Name der Seite,
  aufgerufen wird ein Unterprogramm über den Text seines Start-Elements. Die
  Nummern (`ID`) sind in der ganzen Datei eindeutig, Zoom und Bildmitte
  (`bst:ZOOM`, `bst:VIEW_X`, `bst:VIEW_Y`) gelten je Seite. Projekte mit
  Unterprogramm-Seiten tragen `bst:VERSION="2"` – ältere Programmversionen
  bitten dann um ein Update, statt die Seiten übereinanderzulegen; Projekte
  ohne Unterprogramm-Seiten bleiben bei Version 1.
* **Verträglich mit dem PapDesigner** (am Original 2.2.0.8 geprüft): Der
  PapDesigner verbindet nur waagerecht oder senkrecht von Rasterzelle zu
  Rasterzelle, jede Ecke ist ein eigener Verbindungspunkt; verlässt eine
  Verbindung eine Verzweigung schräg oder nach oben, öffnet er die ganze Datei
  nicht. Beim Speichern bekommt deshalb jede Verbindung, die nicht frei und
  gerade in Richtung ihres Anschlusses läuft, **Eckpunkte** in freien Zellen
  (`PapConnector` mit `bst:CORNER="True"`), so dass keine Strecke über einen
  Baustein führt (nur wo ein Ziel ringsum zugebaut ist, läuft sie notfalls
  darüber – das nimmt der PapDesigner an). Die erste Teilstrecke trägt die
  Angaben der Verbindung, ihr eigentliches Ziel steht in `bst:TO`, Zielanschluss
  und Linienverlauf in `bst:FULL_TARGET_PORT`, `bst:FULL_PATH` und
  `bst:FULL_ROUTE_…`; die weiteren Teilstrecken sind mit `bst:CORNER`
  markiert. Dieses Programm setzt sie beim Öffnen wieder zu einer Verbindung
  zusammen; ältere Versionen lesen Eckpunkte als gewöhnliche Verbindungspunkte
  (gleicher Ablauf, nichts geht verloren). Die Prüfsumme `CHECKSUM` wertet der
  PapDesigner nicht aus.
* **Kommentarlinien** kennt der PapDesigner nicht (in seinen Dateien ist kein
  Kommentar verbunden; eine Linie wäre dort ein Ablaufpfeil). Sie stehen
  deshalb nur in `bst:ANNOTATIONS` am `CONNECTIONS`-Element (JSON mit ihrer
  Stelle in der Reihenfolge aller Verbindungen) – eigene XML-Elemente lehnt
  der PapDesigner ab, Attribute übergeht er. Dateien mit Kommentarlinien tragen
  `bst:VERSION="3"`: Ältere Programmversionen sähen die Linien nicht und
  bitten deshalb um ein Update, statt sie beim Speichern zu verlieren.
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
  page_bar.py                Seitenleiste: Hauptprogramm und Unterprogramme eines Projekts
  subprograms.py             Unterprogramme anlegen, umbenennen (samt Aufrufen), löschen, Namen prüfen
  actions.py                 alle Befehle mit Text, Icon und Tastenkürzel
  canvas.py                  Arbeitsfläche (QGraphicsView): Raster, Zoom, Schwenken, Drag & Drop
  scene.py                   Diagrammszene (QGraphicsScene): Registry, Snap, Verbinden, Inline-Editor
  document.py                ein Projekt: Seiten (je eine Szene), Undo-Stapel, Metadaten, Dateipfad
  palette.py                 Werkzeugpalette mit Formvorschau
  inline_editor.py           Inline-Texteditor
  clipboard.py               Kopieren/Einfügen/Duplizieren
  alignment.py               Ausrichten/Verteilen
  export.py                  PNG/SVG/PDF-Export und Druck
  errors.py                  Fehlerbehandlung und Protokoll
  file_association.py        optionale Registrierung von .pap (Benutzerebene)
  settings_store.py          zuletzt geöffnete Dateien, Fensterzustand, Sprache
  i18n.py                    Mehrsprachigkeit: tr()/N_()/tr_code(), Sprachwahl, Schreibrichtung, Schriften
  labels.py                  ja/nein/sonst und allgemeine Programmnamen in allen Sprachen erkennen
  single_instance.py         ein Fenster für alles: weitere Starts übergeben ihre Dateien dem laufenden Programm
  restart.py                 Neustart des Programms (z. B. nach dem Wechsel der Sprache)
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
  commands/                  Undo/Redo-Befehle (auch Seiten anlegen, löschen, umbenennen)
  dialogs/                   Projekteigenschaften, Über, Tastenkürzel, Exportoptionen, Name eines Unterprogramms
  fileformat/                Lesen und Schreiben von .pap (serializer.py), Kennungen und Version (project.py)
assets/                      erzeugte Programm-/Dateisymbole (.ico/.png), Schullogo
assets/translations/         Übersetzungen (eine JSON-Datei je Sprache: deutscher Text → Übersetzung)
tools/generate_icons.py      erzeugt die Symbole in assets/
tools/extract_strings.py     listet alle übersetzbaren Texte des Quelltexts
tools/check_translations.py  prüft die Übersetzungen (Vollständigkeit, Platzhalter, Tastenkürzel)
tools/translation_batch.py   ergänzt fehlende Übersetzungen portionsweise
tools/make_release.py        erzeugt Setup-Datei und Update-Paket und lädt sie bei GitHub hoch
build_exe.bat                baut das Programm (dist\BSTechnikPAPDesigner)
release.bat                  baut und veröffentlicht eine neue Version als Update
tests/                       automatische Tests (pytest)
installer/                   Inno-Setup-Skript für die Setup-Datei (inkl. Dateizuordnung)
```

Grafik und Daten sind getrennt: Jedes grafische Objekt hält eine Referenz
auf seine Modelldaten (`ElementData`, `ConnectionData`) und hält diese aktuell.
Der Serializer arbeitet ausschließlich mit dem Modell.

### Mehrsprachigkeit

Der deutsche Text im Quelltext ist zugleich der Schlüssel der Übersetzung:
`tr("Datei speichern")` liefert den Text in der eingestellten Sprache,
`tr("{n} Bausteine", n=3)` füllt Platzhalter. Texte in Tabellen und Konstanten
werden mit `N_("…")` nur markiert und erst bei der Anzeige mit `tr(variable)`
übersetzt. Dasselbe deutsche Wort mit anderer Bedeutung bekommt einen
Zusammenhang: `tr("Ende", ctx="Baustein")`. Texte in erzeugten Programmen
(Pseudocode, Kommentare) laufen über `tr_code()`: Deutsch bleibt Deutsch, jede
andere Sprache erzeugt englischen Programmtext.

Neue Texte übersetzen:

```bat
python tools\translation_batch.py status
python tools\translation_batch.py next fr --out teil.json
python tools\translation_batch.py merge fr uebersetzt.json
python tools\check_translations.py --warnings
```

Was in Projektdateien steht (Standardtexte der Bausteine, ja/nein/sonst), wird
in allen Sprachen wiedererkannt (`is_default_text`, `app/labels.py`); die
Schlüsselwörter in den Texten eines Plans (z. B. `für i von 1 bis 10`,
`solange`, `Eingabe:`) gehören zur Sprache des Plans und bleiben, wie sie sind.

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

`tests/test_papdesigner_corpus.py` erzeugt mit `tests/papdesigner_corpus.py`
reproduzierbar viele komplexe Pläne im Dateiformat des PapDesigners
(verschachtelte und mehrfache Verzweigungen, alle Schleifenarten, Schleifen mit
Pfeil zurück, vorzeitiges Ende, bis zu 15 Diagramme mit Parametern und
Zuweisungen im Aufruf, Kommentare, Sonderzeichen) und rechnet selbst aus, was
jeder Plan ausgeben muss. Geprüft wird, dass jede Datei ohne Hinweise und
Verluste geöffnet, genau so ausgeführt, gespeichert und wieder geöffnet wird
und übersetzbaren Code ergibt. Die Lernbeispiele (`assets/examples`) erzeugt
`python tools/make_examples.py`.

Ist der PapDesigner installiert, prüft `python tools/papdesigner_gegenprobe.py
--unser examples\*.pap` direkt im Original, ob er Dateien aus diesem Programm
öffnet (`--unser` speichert sie vorher mit diesem Programm neu; ohne die Option
werden die Dateien unverändert geprüft). Ein laufender PapDesigner wird dabei
beendet; Tasten oder Klicks sendet das Werkzeug nicht.

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
der Schule), installiert nach `C:\Programme`. Dort darf das Programm seinen
Ordner nicht ändern; Updates legt es deshalb im Benutzerprofil ab
(`%LOCALAPPDATA%\BSTechnik\PAPDesigner\update\<Version>`) und startet sie von
dort. Das installierte Programm gibt beim Start automatisch an die neuere Kopie
ab (rund 0,2 Sekunden). Sperrt der Rechner den Start von Programmen aus dem
Benutzerprofil, läuft das installierte Programm unverändert weiter und weist
nur in der Statuszeile auf neue Versionen hin; der Administrator installiert
sie dann mit dem nächsten Setup.

### Schulbetrieb: Updates zentral abschalten

Damit alle Rechner einer Schule dieselbe Version behalten (z. B. während einer
Prüfungsphase) und das Programm nicht bei jedem Start bei GitHub nachfragt,
schaltet der Administrator die Updates auf einem dieser Wege ab:

* **Still installieren ohne Updates:**
  `BSTechnikPAPDesigner-Setup.exe /VERYSILENT /ALLUSERS /NOUPDATES`
  (legt `policy.ini` im Programmordner an)
* **Gruppenrichtlinie / Registry:** unter
  `HKEY_LOCAL_MACHINE\Software\Policies\BSTechnik\PAPDesigner` den DWORD-Wert
  `DisableUpdates` = `1` setzen (für einzelne Benutzer auch unter
  `HKEY_CURRENT_USER`)
* **Datei `policy.ini`** neben `BSTechnikPAPDesigner.exe`:

      [Updates]
      Disabled=1

Dann prüft das Programm nicht mehr, „Nach Updates suchen“ verweist auf den
Administrator, und es gibt auch nicht mehr an eine früher in den Benutzerordner
geladene neuere Version ab. Neue Versionen installiert die Schule mit dem
nächsten Setup. Benutzer können die Prüfung beim Start nur für sich selbst
abschalten (**Hilfe → Beim Start nach Updates suchen**).

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

Voraussetzung auf dem Zielrechner ist Internetzugang zu `github.com`; fehlt er,
läuft das Programm unverändert weiter. Wie das Update installiert wird, hängt
vom Programmordner ab:

* **Programmordner beschreibbar** (Setup „nur für mich“): Das Programm ersetzt
  seinen Ordner selbst und startet neu; schlägt das fehl, bleibt die bisherige
  Version erhalten.
* **Programmordner nicht beschreibbar** (Setup „für alle Benutzer“, z. B. unter
  `C:\Programme`): Die neue Version kommt in den Benutzerordner
  (`%LOCALAPPDATA%\BSTechnik\PAPDesigner\update\<Version>`) und wird von dort
  gestartet. Ältere Kopien dort werden aufgeräumt. Das Update gilt dabei nur
  für den Benutzer, der es geladen hat; andere Benutzer desselben Rechners
  laden es bei ihrem eigenen Start. Ein neueres Setup bleibt jederzeit
  möglich und hat Vorrang, sobald seine Version neuer ist.
* **Auch das nicht möglich** (Start aus dem Benutzerordner gesperrt, z. B. durch
  eine Schulrichtlinie): Das Programm stellt keine Frage, die sich nicht
  erfüllen lässt. Beim Start steht nur ein ruhiger Hinweis in der Statuszeile
  („Neue Version … verfügbar – bitte beim Administrator melden“); **Hilfe →
  Nach Updates suchen** nennt zusätzlich den Link zur neuen Setup-Datei.

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

## Linux-Version (AppImage)

Die Linux-Version kann dasselbe wie die Windows-Version und kommt als eine
einzige Datei: `BSTechnikPAPDesigner-x86_64.AppImage`. Sie läuft auf allen gängigen
64-Bit-Distributionen ohne zusätzliche Werkzeuge (kein Gear Lever, kein
AppImageLauncher nötig – beide funktionieren aber auch). Die neueste Fassung steht immer unter

    https://github.com/Medj3d/BSTechnikPAPDesigner/releases/latest/download/BSTechnikPAPDesigner-x86_64.AppImage

Geprüft (November 2026, jeweils frisch installiert, mit Start, Fenster, Startmenü-Eintrag,
`.pap`-Doppelklick und zweitem Start):

| Distribution | geprüft | gilt auch für |
|---|---|---|
| Ubuntu 22.04, 24.04, 26.04 | ✓ | Linux Mint 21/22, Pop!_OS, Zorin OS, elementary OS, Kubuntu … |
| Debian 13 | ✓ | Debian 12, MX Linux, LMDE |
| Fedora 45 | ✓ | Fedora 43/44, Nobara |
| Arch Linux | ✓ | Manjaro, EndeavourOS, CachyOS |
| openSUSE Tumbleweed, Leap 16.1 | ✓ | |

Voraussetzung ist nur glibc ab 2.35 (alle aktuell unterstützten Distributionen;
nicht mehr Ubuntu 20.04 oder Linux Mint 20) und eine Bildschirmoberfläche (X11 oder
Wayland). Fehlen auf einer Minimalinstallation die Grafikbibliotheken (libGL,
libEGL, libxcb), meldet das Programm das beim Start und nennt den passenden Befehl,
z. B. `sudo apt install libgl1 libegl1 libxcb1`.

### Installieren

1. Die Datei herunterladen und an einen festen Ort legen, z. B. `~/Programme/`
   (danach nicht mehr verschieben – sonst einfach einmal von der neuen Stelle starten).
2. Ausführbar machen: Rechtsklick → Eigenschaften → „Als Programm ausführen“, oder

   ```bash
   chmod +x ~/Programme/BSTechnikPAPDesigner-x86_64.AppImage
   ```

3. Per Doppelklick starten. Beim ersten Start richtet das Programm von selbst
   einen Eintrag im Startmenü und den Dateityp `.pap` ein (Doppelklick auf eine
   `.pap`-Datei öffnet sie dann im Programm). Das geschieht nur im eigenen
   Benutzerordner, ohne Administratorrechte; erneuern lässt es sich mit
   **Hilfe → Dateityp registrieren …**.

**libfuse2 wird nicht gebraucht:** Das AppImage nutzt die neue, statisch
gebaute AppImage-Laufzeit. Ältere Anleitungen im Netz, die `libfuse2`
verlangen, gelten dafür nicht. Ist FUSE vorhanden (fast überall), wird das
AppImage eingehängt; fehlt es, entpackt es sich beim Start von selbst in einen
Temp-Ordner (etwas langsamerer Start) – in beiden Fällen ohne Zutun.

Die übrigen Bibliotheken, die Qt für die Anzeige braucht (z. B. `libxcb-cursor0`),
bringt das AppImage selbst mit.

**Eine Schrift auf allen Systemen:** Das Programm bringt die Programmierschrift
„JetBrains Mono NL“ mit (SIL Open Font License, `assets/fonts`; NL = ohne
Ligaturen, `<=` bleibt `<=`) und nutzt sie unter Windows und Linux für Bausteine,
Menüs und Dialoge. Pläne sehen deshalb überall gleich aus: Mit 132 Testdateien
sind geöffnete Pläne, gespeicherte Dateien (Byte für Byte), „Automatisch
anordnen“, Schreibtischtest und Prüfung unter Windows und Linux identisch.
Nur für Arabisch, Chinesisch und Japanisch nimmt das Programm die Schriften des
Systems (unter Linux z. B. Noto Sans CJK, bei Fedora, Ubuntu und Mint vorhanden).

### Wo die Linux-Version ihre Daten ablegt

| Was | Wo |
|---|---|
| Einstellungen | `~/.config/BS Technik/PAPDesigner.conf` |
| Fehlerprotokoll, Sicherungskopien | `~/.local/share/BSTechnik/PAPDesigner/` (`logs`, `autosave`) |
| Startmenü-Eintrag und Dateityp | `~/.local/share/applications/bstechnik-papdesigner.desktop`, `~/.local/share/mime/packages/bstechnik-papdesigner.xml`, Standardprogramm in `~/.config/mimeapps.list` |

### Updates unter Linux

Das AppImage prüft beim Start wie die Windows-Version auf eine neue Version
(in `version-linux.json` der neuesten Veröffentlichung – Windows-Programme
lesen weiter nur `version.json`). Nach Zustimmung lädt es das neue AppImage
neben das alte, prüft die Prüfsumme, ersetzt die Datei in einem Schritt und
startet neu. Liegt das AppImage in einem schreibgeschützten Ordner, gibt es nur
einen Hinweis mit dem Link zur neuen Datei.

**Schulbetrieb:** Updates schaltet der Administrator für alle Benutzer mit der
Datei `/etc/bstechnik-pap/policy.ini` ab (gleicher Inhalt wie unter Windows,
`[Updates]` / `Disabled=1`); eine `policy.ini` neben der AppImage-Datei wirkt
ebenso.

### Bauen und veröffentlichen

Die Linux-Version entsteht von selbst: Sobald unter Windows mit `release.bat`
eine neue Version veröffentlicht ist, baut der GitHub-Workflow
[`.github/workflows/linux-appimage.yml`](.github/workflows/linux-appimage.yml)
auf Ubuntu 22.04 das AppImage, lässt alle Tests laufen, startet es probehalber
und hängt `BSTechnikPAPDesigner-x86_64.AppImage` und `version-linux.json` an
dieselbe Veröffentlichung (dauert rund 10 Minuten). Von Hand lässt er sich
unter **Actions → Linux-AppImage → Run workflow** mit der Version starten.

Lokal auf einem Linux-Rechner (am besten einem älteren System wie Ubuntu 22.04,
damit das AppImage auch dort läuft; Python 3.13 aus dem deadsnakes-PPA):

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.13 python3.13-venv curl libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxkbcommon-x11-0
python3.13 -m venv ~/venv-pap && ~/venv-pap/bin/pip install -r requirements-dev.txt
PYTHON=~/venv-pap/bin/python bash tools/build_appimage.sh   # → dist/BSTechnikPAPDesigner-x86_64.AppImage
~/venv-pap/bin/python tools/make_release.py --ohne-upload   # → dist/version-linux.json
```

Getestet unter WSL (Ubuntu 22.04 mit WSLg): Start, Öffnen und Speichern,
Doppelklick auf `.pap`-Dateien über den Startmenü-Eintrag, Kopieren als Bild,
Einstellungen nach Neustart und das Update (AppImage wird ersetzt und neu gestartet).

Ohne `--ohne-upload` hängt `make_release.py` beides an die bestehende
Veröffentlichung `v<Version>`.

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
| 1.6 | 08.10.2026 | Updates funktionieren auch ohne Schreibrechte im Programmordner: Die neue Version wird im Benutzerordner abgelegt und von dort gestartet |
| 1.7 | 08.10.2026 | neun Sprachen (Deutsch, Englisch, Französisch, Spanisch, Portugiesisch, Russisch, Arabisch, Chinesisch, Japanisch); weitere Dateien öffnen sich als Reiter im laufenden Programm; Schullogo im Ladebildschirm vollständig und mittig |
| 1.8 | 26.10.2026 | Unterprogramme auf eigenen Seiten (Hauptprogramm + Unterprogramme als Reiter, anlegen, öffnen per Strg+Doppelklick, umbenennen samt Aufrufen); Schreibtischtest springt ins Unterprogramm; PDF und Druck mit allen Seiten |
| 1.9 | 27.10.2026 | Bild in die Zwischenablage (Strg+C bzw. „Als Bild kopieren“, auch Struktogramm); Schreibtischtest mit Schritt zurück, automatischem Abspielen und Spalten Bedingung/Ausgabe, Tabelle kopieren und als CSV speichern; Updates zentral abschaltbar (Setup /NOUPDATES, Richtlinie, policy.ini) und für sich selbst beim Start; Link zu medjed.net im Über-Dialog; PapDesigner-Kompatibilität mit echten Dateien geprüft: Unterprogramme heißen wie ihr Diagramm (auch mit Start „Start“ und Namen wie „bool isLeapYear(int year)“), Aufrufe mit Zuweisung und Argumenten werden zugeordnet, Nummerierung je Diagramm wie im Original, Kopieren per Strg+Ziehen, Baustein umwandeln, Gegenwort ja/nein, Unterprogramm-Auswahl „Ruft auf“ |
| 1.14 | 10.11.2026 | Schlichte Werkzeugleiste; weitere Knöpfe in den Einstellungen unter „Zusatzknöpfe“ zuschaltbar (Zwischenablage, Raster, Ausrichten, Code-Ansicht, Minikarte, Haltepunkte, Lehrermodus), „Alle Schalter zurücksetzen“. Code-Ansicht neben dem Plan (Klick auf eine Zeile markiert den Baustein). Lehrermodus: Aufgabe in der Datei, Musterlösung mit Passwort verschlüsselt, Aufgabe erscheint beim Öffnen oben. Haltepunkte (F9) im Schreibtischtest, geänderte Variablen hervorgehoben mit altem Wert. Minikarte wie in VS Code. Name, Klasse und Datum klein auf PNG, SVG, PDF und Ausdruck. Tastenkürzel: Strg+T Schreibtischtest (F5/F10 öffnen ihn auch), F9 Haltepunkt, Strg+E PDF, Strg+M Minikarte |
| 1.13.1 | 10.11.2026 | Ladebildschirm: Namenszeile wird nicht mehr abgeschnitten. Hinweise beim Start immer zu, Knopf in der Statusleiste mit Zähler am Symbol, Hinweisfeld lässt sich bis auf die Kopfzeile verkleinern. Lupen-Knöpfe springen auf runde Werte (bis 200 % in Zehner-, darüber in 25er-Schritten). Rastergröße in den Projekteigenschaften mit deutlichen Knöpfen „−“ und „+“ |
| 1.13 | 10.11.2026 | Eine Schrift auf allen Systemen: die Programmierschrift JetBrains Mono NL (mitgeliefert, ohne Ligaturen) für Bausteine und Oberfläche – Pläne sehen unter Windows und Linux gleich aus (132 Testdateien identisch, auch die gespeicherten Dateien). Linux-Version geprüft auf Ubuntu 22.04/24.04/26.04 (Mint), Debian 13, Fedora 45, Arch und openSUSE; fehlen Grafikbibliotheken, nennt sie den Befehl zum Nachinstallieren; mit Gear Lever kein doppelter Startmenü-Eintrag mehr. Suche (Strg+K) auch bei schmalem Fenster erreichbar (dann in der Menüzeile); arabische Palette richtig gespiegelt; unter Linux gespeicherte Dateien mit normalen Dateirechten |
| 1.12 | 09.11.2026 | Linux-Version als AppImage mit allen Funktionen: eine Datei für fast alle Distributionen, richtet beim ersten Start Startmenü-Eintrag und `.pap`-Dateityp ein, aktualisiert sich selbst (eigene Update-Angaben, Windows-Programme bleiben unberührt), Updates zentral abschaltbar über `/etc/bstechnik-pap/policy.ini`; mitgelieferte Schrift mit den Maßen von Segoe UI, damit Pläne unter Linux genauso aussehen wie unter Windows. Gebaut und angehängt von einem GitHub-Workflow auf Ubuntu 22.04; geprüft unter WSL mit 1269 Tests, Öffnen, Speichern, Doppelklick, Kopieren als Bild und Update |
| 1.11 | 03.11.2026 | Einstellungen mit Schaltern und frei belegbaren Tastenkürzeln (je zwei Tasten), Suchleiste für Funktionen, Einstellungen und Bausteine, Bausteine auf den Tasten 1–9, neue Projekte beginnen mit Start → Ende. Pfeile: abgerundet, mit mehr Abstand, jedes Stück und jede Ecke frei verschiebbar (rechtwinklig, nur Aussehen), Enden umhängbar, Schnellmenü im Leeren, Pfeile mit losem Ende (Schalter). Ist die Zwischenablage belegt, meldet das Programm das, und Ausschneiden löscht nichts mehr. Prüfung: keine falschen roten Pfeile mehr beim Einfügen neben Ende und Start, Stufe „gelb“ für Auffälliges, Warnzeichen mit Grund am Pfeil, erweiterte Prüfung (Schalter). Automatisch anordnen neu: gemessen an 260 Plänen 92 % weniger Linien durch Bausteine, keine Punkte mehr in Bausteinen, nur noch ein Fünftel der Kreuzungen; der Ablauf bleibt nachweislich gleich |
| 1.10.1 | 28.10.2026 | Gegenprobe im Original-PapDesigner: Dateien aus diesem Programm öffnen sich jetzt dort – Verbindungen werden rechtwinklig mit Eckpunkten gespeichert (das Original lehnte Dateien mit schräg abgehenden Verzweigungen ab), Kommentarlinien stehen nur noch in den Zusatzangaben; die Verbindung eines Bausteins mit sich selbst bleibt auch im Original erhalten; erzeugte Testpläne sind wie Originaldateien aufgebaut. Geprüft mit allen 44 echten PapDesigner-Dateien, den Lernbeispielen und 60 komplexen Plänen direkt im Original |
| 1.10 | 28.10.2026 | alle Bau-Funktionen des PapDesigners: Schleife mit Kopf- bzw. Fußbedingung, Verbindungspunkt auf einer Verbindung, Sonderzeichen, Strg+Enter, bedingter Trennstrich „~“; Seiten duplizieren, kopieren, ausschneiden, einfügen (auch zwischen Projekten) und verschieben (auch per Ziehen), „Aufgerufen von“, Auswahl in Unterprogramm auslagern, Zurück/Vorwärts zwischen Seiten; Präsentationsansicht (F11), Sicherungskopie `.pap-backup`, Standard-Autor, fünf Lernbeispiele; „Ausgabe von "Text" x“ gibt wie im PapDesigner auch den Wert aus; geprüft mit Hunderten erzeugter komplexer Pläne im Format des PapDesigners |

---

## Hinweise

* Die Spezifikation endete bei Abschnitt 58 („Drucken“). Umgesetzt wurden
  Drucken und Druckvorschau: jedes Diagramm (Hauptprogramm und jedes
  Unterprogramm) wird seitenfüllend auf eine eigene Seite gedruckt
  (Hoch-/Querformat nach dem Hauptprogramm).
* Einstellungen wie „Raster anzeigen“ und „Einrasten“ werden mit dem Projekt
  gespeichert, gelten aber als Ansichtseinstellung und markieren das Projekt
  nicht als geändert.
