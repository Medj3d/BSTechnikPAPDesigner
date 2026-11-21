# QA-Bericht (Claude) – BS Technik PAP Designer 1.15.3

Stand: 21.11.2026 · geprüft: Commit `c502ec8` (Version 1.15.3) unter Windows 11 und Linux (WSL Ubuntu 22.04).
Am Produktivcode wurde nichts geändert. Neue Tests liegen nur unter `tests/qa/test_claude_*.py` (+ `claude_qa_helpers.py`),
Bildschirmfotos unter `tests/qa/screenshots_claude/`.

Kennzeichnung in allen Tabellen: **[getestet]** = mit Test oder Versuch nachgestellt · **[Code]** = nur aus dem Code
geschlossen · **[vermutet]** = plausibel, aber hier nicht prüfbar.

---

## 1. Kurzfazit

1. Die App ist im Kern robust und schnell: 1050 kaputte oder veränderte Dateien und 46 Zufallsläufe durch das ganze Fenster
   lösten keinen Absturz aus, und bei 600 Bausteinen dauern Öffnen, Code und Schreibtischtest unter einer Sekunde.
2. Das größte Risiko ist das **ab Werk eingeschaltete automatische Speichern**: Es überschreibt Aufgabendateien der Lehrkraft
   in gemeinsamen Ordnern still (B15), speichert ein beschädigt geöffnetes Projekt als leeres Projekt zurück (B14), und beim
   Schließen eines Reiters erscheint eine Fehlermeldung (B13).
3. Der Schreibtischtest rechnet in einigen Fällen anders als der erzeugte Code oder als der Plan gemeint ist (Schleife mit
   Kopf- und Fußbedingung, Text × Kommazahl, Runden) – im Unterricht führt das zu falschen Rückmeldungen.
4. Bei großen Plänen friert „Automatisch anordnen“ ein (600 Bausteine: 26 s), und der Druck verkleinert alles auf eine Seite;
   dazu kommen Bedienmängel wie Esc in der Präsentation, Tab ohne Wirkung und zu schwache Kontraste im dunklen Schema.
5. Gegenüber dem Original-PapDesigner ist die App klar überlegen (Schreibtischtest, Code, Struktogramm, Prüfung, Lehrermodus);
   vor einer breiten Einführung sollten die Fehler B13–B15 behoben werden.

---

## 2. Bug-Tabelle

| ID | Schwere | Bereich | Schritte | Erwartet | Tatsächlich | Ursache (Datei:Zeile) | Fix-Vorschlag |
|---|---|---|---|---|---|---|---|
| B01 | mittel | Tastatur / Präsentation | Plan öffnen, nichts auswählen, F11, dann Esc | Präsentation endet (Kurzinfo: „F11 oder Esc beendet“) | nichts passiert; Qt meldet `Ambiguous shortcut overload: Esc` **[getestet, echte Tastendrücke, Windows nativ und offscreen]** | Zwei aktive Befehle auf Esc: `_exit_presentation` (`app/main_window.py:689-693`) und „Auswahl aufheben“ (`app/actions.py:58`), das über `addActions` (`app/main_window.py:695`) am Fenster hängt | `_exit_presentation` entfernen; im Slot von „deselect“ bei laufender Präsentation `_on_presentation_escape()` aufrufen |
| B02 | mittel | Leistung | Plan mit 600 Bausteinen → „Automatisch anordnen“ | höchstens 1–2 s | 100 Bausteine 0,3 s · 400 → 3,5–4 s · 600 → 26 s · 1200 → 73 s, Fenster eingefroren; „Alles löschen + Rückgängig“ bei 1200 Bausteinen 4,2 s **[getestet]** | 79 % der Zeit in `app/connections/routing.py:137` (`line_penalty`, aus `score_path` :157): jede Kandidatenlinie wird gegen **alle** Linien der Seite geprüft (`app/scene.py:415` `routing_lines` ohne räumliche Vorauswahl); `app/commands/connection_commands.py:51` führt alle Pfeile neu | Linien nach Bounding-Box vorfiltern (Raster/Index), Ergebnis je Stapel zwischenspeichern; Fortschrittsanzeige bei großen Plänen |
| B03 | mittel | Druck | Plan mit 600 Bausteinen (oder Kette mit 200) drucken | lesbarer Ausdruck, ggf. auf mehreren Seiten | alles auf **eine** A4-Seite verkleinert: Schrift 0,65 mm bzw. 0,16 mm hoch (Schulplan mit 16 Bausteinen: 3,8 mm, gut) **[getestet, aus dem Druckpfad berechnet]** | `app/export.py:239` `print_scene` skaliert seitenfüllend, keine Aufteilung, kein Maßstab | „Auf mehrere Seiten verteilen“ bzw. Mindestmaßstab; das Original hat „Seite einrichten“ und „Druckseiten individuell skalieren“ |
| B04 | niedrig | PDF | Lange Kette (200 Bausteine) als PDF exportieren | übliche Seitengröße (A4) oder Aufteilung | PDF-Seite = Plangröße: 6 × 635 cm (18 000 pt) **[getestet]**; über der PDF-Grenze von 14 400 pt – Adobe Reader zeigt das vermutlich nicht richtig an **[vermutet]** | `app/export.py:209` `_pdf_layout` | Wahl „A4 (verkleinert/aufgeteilt)“ neben „Plangröße“ |
| B05 | mittel | Layout / kleine Bildschirme | 1366×768 bei 125 % oder 150 %, Schreibtischtest + Hinweise + Code-Ansicht öffnen | Fenster passt auf den Bildschirm | Mindestgröße 829×649 (150 %) bzw. 840×643 (100 %): passt bei 125 %/150 % nicht auf 1366×768; bei 100 % bleibt ein ca. 230 px hoher Zeichenstreifen, Code-Ansicht und Statuszeile werden abgeschnitten (Bilder 02, 03) **[getestet: minimumSizeHint, Bildschirmfotos]** | Mindesthöhen der Bedienfelder (`app/main_window.py` `_make_dock`, `app/simulation/panel.py`) | Bedienfelder als Reiter zusammenlegen, Mindesthöhen senken, Schreibtischtest einklappbar |
| B06 | niedrig | Speicher | Projekt öffnen, Reiter schließen, neues Projekt | Bausteine des geschlossenen Projekts werden freigegeben | ein geschlossenes Projekt (alle Bausteine) bleibt im Speicher; es wird nicht mehr (4 Runden: 116→119 MB) **[getestet]** | Ansicht und Minikarte halten sich gegenseitig (`app/main_window.py:1042`, `app/minimap.py:27`, `:75`) | in `close_tab` `view.minimap` lösen (`_scene`/`_view` = `None`, Signale trennen) |
| B07 | niedrig | Texte | Kurzinfo/Statuszeile von „Code erzeugen“ | nennt auch PIC-Assembler (der Standard!) | „Pseudocode, Python oder Java …“ **[getestet: Inventar]** | `app/actions.py:115`, `app/preferences.py` (`TOOL_GENERATE_CODE`) | Text um „PIC-Assembler“ ergänzen |
| B08 | niedrig | Texte | Maus über Knopf „Schreibtischtest“ | „Schreibtischtest (Strg+T)“ wie bei den anderen Knöpfen | ohne Tastenkürzel **[getestet: Inventar]** | `ActionRegistry.adopt` (`app/actions.py:253`) setzt die Kurzinfo nicht neu | in `adopt` `_refresh_tooltip(name)` aufrufen |
| B09 | niedrig | Lernbeispiele | Hilfe → Lernbeispiele → 3 | saubere Kommentartexte | Zeilen doppelt umbrochen („geprüft“ / „wird“ einzeln, Bild 01) **[getestet]** | feste Zeilenumbrüche im Beispiel + automatischer Umbruch bei 260 px | Umbrüche im Beispiel entfernen oder Kommentarbreite erhöhen |
| B10 | mittel | Barrierefreiheit | Dunkles Farbschema, markierte Listenzeile / Standardknopf / blau hinterlegter Text | Kontrast ≥ 4,5 : 1 (WCAG 1.4.3) | weiß `#F2F5F9` auf Akzent `#5B96E8` = **2,75 : 1**; gedämpfter Text auf erhöhtem Feld 4,39 : 1; Fehlerfarbe auf Feld 4,33 : 1 **[getestet: berechnet aus den Farbwerten]** | `app/styles.py` `DARK` (accent, accent_text, text_muted, danger) | Akzent dunkler, z. B. `#3B78D8` (≈ 4,6 : 1), `text_muted` `#959CA6`, `danger` `#DE7676` |
| B11 | niedrig | Barrierefreiheit | Eingabefelder (Suche, Einstellungen) in beiden Schemata | Feldgrenze ≥ 3 : 1 (WCAG 1.4.11) | Rahmen zu blass: dunkel 1,20 : 1, hell 1,31 : 1 **[getestet: berechnet]** | `app/styles.py` `border` in `DARK`/`LIGHT_UI` | für Eingabefelder `border_strong` dunkler wählen (≥ 3 : 1) |
| B12 | mittel | Verteilung (Windows) | Setup bzw. Update aus dem Internet laden und starten | kein Warnhinweis | Programm und Setup sind **nicht signiert** (`Get-AuthenticodeSignature` = NotSigned) **[getestet]**; SmartScreen warnt dann vor „unbekanntem Herausgeber“, Schul-IT blockt solche Dateien oft **[vermutet]**. Defender findet nichts **[getestet]** | Build/Release ohne Code-Signatur (`tools/make_release.py`, `installer/*.iss`) | Code-Signatur-Zertifikat (z. B. für Open-Source-Projekte) oder Hinweis im README, wie man die Warnung bestätigt |
| B13 | hoch | Reiter schließen | Projekt speichern, einen Baustein einfügen (automatisches Speichern ist ab Werk an, `app/config.py:88`), Reiter schließen | Reiter schließt still | `RuntimeError: Internal C++ object (QUndoStack) already deleted` in einem Slot; im fertigen Programm zeigt der Fehler-Hook „Es ist ein unerwarteter Fehler aufgetreten“ **[getestet, Standardeinstellungen; auch Codex QA-05]** | Lambda `undo_stack.indexChanged → _schedule_auto_save` (`app/main_window.py:1059`) läuft noch beim Abbau; `_schedule_auto_save` (`:1505`) ruft `document.is_modified` (`app/document.py:431`) auf der gelöschten Liste | in `close_tab` die Verbindung trennen bzw. `shiboken6.isValid()` prüfen, offenes automatisches Speichern stoppen |
| B14 | hoch | Datenverlust | In einer eigenen `.pap` die Tags `DIAGRAMS` zu `DIAGRMAS` beschädigen, öffnen, einen Baustein einfügen | Fehlermeldung oder Warnung, Datei bleibt unangetastet | öffnet als **leeres** Projekt ohne jeden Hinweis (`load_warnings` leer) **[getestet; auch Codex QA-03]**; das automatische Speichern schreibt danach das leere Projekt über die noch rettbare Datei **[Code]** | `app/fileformat/serializer.py:1071-1085`: eigene Dateien dürfen leer sein, fehlende Behälter fallen nicht auf | fehlt `DIAGRAMS`/`DIAGRAM`, Fehler melden; Dateien mit Ladehinweisen nie automatisch überschreiben |
| B15 | hoch | Lehrermodus / Datenverlust | Lehrkraft legt `Aufgabe3.pap` (mit Aufgabe und Passwort) in einen gemeinsamen Ordner mit Schreibrecht; Schüler 1 öffnet direkt und fügt einen Baustein ein; danach Schüler 2 ebenso | Original der Lehrkraft bleibt erhalten | Datei wird nach 2 s still überschrieben; die `.pap-backup` hält nur den Stand beim letzten Öffnen, nach dem zweiten Schüler ist das Original weg; Schüler 2 sieht die Lösung von Schüler 1 **[getestet durch Prüfer; Standardwerte von mir bestätigt]** | automatisches Speichern gilt für jede gespeicherte `.pap` (`app/main_window.py:1498`, `:1517`), Sicherung nur einmal je Öffnen (`app/document.py:504`) | Projekte mit Aufgabe als unbenannte Kopie öffnen („Vorlage“) oder dort nicht automatisch speichern; erste Sicherung nicht überschreiben |
| B16 | mittel | Schreibtischtest / Code | Schleife: Beginn „3-mal“, Ende „bis code = 1234“, im Rumpf Eingabe; Schreibtischtest mit falschem Code | nach 3 Versuchen Ende (oder Hinweis, dass der Kopf nicht zählt) | Kopf wird still übergangen, die Schleife fragt endlos; Python (`while True`) und Java (`do … while`) ebenso, PIC-Assembler anders **[getestet durch Prüfer; Code von mir bestätigt]** | `app/simulation/engine.py:448-450` („fußgesteuert: Kopf wird nicht geprüft“), `app/codegen/generators.py:666-671`, `:1378-1382` | beide Bedingungen auswerten oder als Hinweis melden; alle Ausgaben gleich behandeln |
| B17 | mittel | Zwischenablage | Baustein markieren, Strg+X, Strg+Z, Strg+V | Kopie versetzt (40/40) wie beim normalen Kopieren | Kopie liegt **deckungsgleich** auf dem Original – sieht aus wie „Einfügen geht nicht“, versteckte Doppelbausteine **[getestet]** | `clipboard.prime_after_cut` (`app/clipboard.py:234-237`) bleibt nach Rückgängig gesetzt (`app/main_window.py:1802-1822`) | Versatz-Merker beim Rückgängig des Ausschneidens zurücksetzen |
| B18 | mittel | Rückgängig | Neues Projekt, Projekteigenschaften: Autor ändern, „Speichern unter“ `Kreis.pap`, Strg+Z, Strg+Y | Name „Kreis“ bleibt | Name springt auf „Unbenannt 3“ zurück, das Projekt gilt trotzdem als gespeichert; beim nächsten Speichern steht „Unbenannt 3“ in der Datei und im erzeugten Code **[getestet]** | `ProjectPropertiesCommand` merkt sich die ganzen Metadaten (`app/commands/properties.py:50-56`), `save()` setzt den Namen ohne Rückgängig-Schritt (`app/document.py:489-490`) | Befehl überträgt nur geänderte Felder |
| B19 | mittel | Tastatur | Arbeitsfläche anklicken, Tab drücken | nächster Baustein wird ausgewählt (laut Version 1.15.2) | Fokus springt zu einem Knopf der Werkzeugleiste, kein Baustein wird gewählt; Pfeile lassen sich nur mit der Maus ziehen **[getestet; auch Codex QA-11]** | Qt verbraucht Tab in der Fokuskette, bevor `DiagramScene.keyPressEvent` (`app/scene.py:2096-2100`) es sieht | in `DiagramView` `focusNextPrevChild` überschreiben bzw. Tab im `event()` abfangen |
| B20 | mittel | Dateien | Eine Datei einmal über den Kurzpfad (`C:\Users\ABC~1\…`) und einmal über den Langpfad öffnen (ebenso Netzlaufwerk/`subst`); „Speichern unter“ auf eine schon offene Datei | ein Reiter; Warnung vor dem Überschreiben einer offenen Datei | zwei Reiter für dieselbe Datei; „Speichern unter“ überschreibt die offene Datei ohne Hinweis **[getestet]** | Vergleich nur mit `normcase(abspath())` (`app/main_window.py:1156`) | `os.path.samefile` bzw. `os.path.realpath` vergleichen |
| B21 | mittel | Lehrermodus | Aufgabe stellen mit Titel „Prüfe, ob a<b und b>c gilt“ und Lösung „Bei a<b … Bei a>b …“ | Text wie eingegeben | angezeigt: „Prüfe, ob ac gilt“ bzw. „Bei ab wird "größer" ausgegeben.“ – Teile fehlen, Rest fett **[getestet]** | `QLabel`/`QMessageBox` deuten Text als HTML (`app/task_panel.py:189`, `:216`, Format AutoText) | `setTextFormat(Qt.PlainText)` |
| B22 | mittel | Schul-IT | `policy.ini` mit `[Updates] Disabled=1` so schreiben, wie Windows-Werkzeuge es tun: PowerShell 5.1 (UTF-16), ANSI mit Umlaut im Kommentar oder `[updates]` klein | Updates abgeschaltet | Datei wird still übergangen, Updates bleiben an **[getestet]** | nur UTF-8 gelesen, Fehler = „keine Datei“ (`app/policy.py:59-71`), Abschnittsname groß/klein-genau (`:106`) | Kodierung erkennen (BOM, cp1252), Abschnitt ohne Groß/Klein suchen, Lesefehler protokollieren |
| B23 | mittel | Code | Vorgang `linie = "*" * (n / 2)`, Eingabe 6; Python-Code erzeugen und ausführen | „***“ wie im Schreibtischtest | Python bricht ab: `TypeError: can't multiply sequence by non-int of type 'float'` (Java schneidet ab) **[getestet durch Prüfer; ebenso Codex QA-10]** | Python-Erzeuger übernimmt den Ausdruck unverändert (`app/codegen/generators.py:317-332`, `:561-586`) | Anzahl wie Schreibtischtest/Java mit `int()` umwandeln |
| B24 | mittel | Update | Update „nur für mich“ installiert; beim Ersetzen scheitert ein Kopierschritt und gleichzeitig hält ein Virenscanner eine neue Datei fest | sauberer Rückweg, ehrliche Meldung | Rückweg bricht ab (kein neuer Versuch), Programm bleibt gemischt alt/neu, Meldung „Die bisherige Version bleibt erhalten“, die Sicherung `_internal.alt` wird beim nächsten Start gelöscht **[getestet durch Prüfer; Code von mir bestätigt]** – selten | `app/updater.py:710-721` (Rückweg ohne Wiederholung), `:443-466` | Rückweg wie Hinweg mit Wiederholung; Sicherung nur löschen, wenn der Rückweg gelang; Meldung je nach Ergebnis |
| B25 | niedrig | Schreibtischtest / Code | Vorgang `r = runden(1,005; 2)` (ebenso 0,285 oder 2,675) | 1,01 (kaufmännisch) | 1 bzw. 0,28 – in 68 von 1000 Fällen der Form x,xx5 **[getestet]** | Gleitkomma: `math.floor(abs(x) * faktor + 0.5)` (`app/simulation/evaluator.py:60`, Python/Java-Hilfen `generators.py:468`, `:1286`) | über `Decimal(str(x))` runden, in allen Ausgaben gleich |
| B26 | niedrig | Wiederherstellung | Projekt ändern, Absturz/Stromausfall, Neustart – ein anderes Programm bekommt zufällig die alte Prozessnummer | Wiederherstellung wird angeboten | wird erst nach 1 Tag angeboten **[getestet durch Prüfer; Code von mir bestätigt]** | nur „läuft irgendein Prozess mit dieser Nummer“ (`app/autosave.py:238`) | zusätzlich Startzeit/Programmname prüfen oder gesperrte Sitzungsdatei |
| B27 | niedrig | Schreibtischtest | Unterprogramm mit einem Weg ohne Ende (Sackgasse), danach im Hauptprogramm „Ausgabe weiter“ | wie der erzeugte Code: zurück zum Aufrufer | Schreibtischtest endet ganz, „weiter“ fehlt; Python/Java/PIC kehren zurück **[getestet durch Prüfer; Code von mir bestätigt]** | `_advance` beendet immer (`app/simulation/engine.py:140-147`) | bei leerem Nachfolger erst den Aufrufstapel abbauen |
| B28 | niedrig | Einzelinstanz | Während „Update wird heruntergeladen …“ eine `.pap` doppelklicken | Datei öffnet sich nach dem Update | zweiter Start meldet „übergeben“, die Datei wird nie geöffnet **[getestet durch Prüfer; Code von mir bestätigt]** | Server bestätigt sofort (`app/single_instance.py:255-259`), Öffnen hängt an einem Zeitgeber (`main.py:140-151`), Neustart nach Update ohne Dateien | erst nach dem Öffnen bestätigen bzw. Dateien an den Neustart übergeben |
| B29 | niedrig | Unterprogramme | Start eines Unterprogramms zweizeilig beschriften, Aufruf `ergebnis :=`⏎`summe(x, y)`, dann umbenennen | Zeilenumbrüche bleiben | Start und Aufruf werden einzeilig **[getestet durch Prüfer]** | `app/document.py:203-206`, `app/subprograms.py:119-141`, `:151` | Namen im Originaltext ersetzen |
| B30 | niedrig | Unterprogramme | Reiter „Hauptprogramm“ → Seite kopieren → Seite einfügen | neuer, eindeutiger Name | zweiter Reiter „Hauptprogramm“ **[getestet durch Prüfer]** | `app/subprograms.py:244`, `:44-68` | festen Namen der Hauptseite bei der Namensprüfung berücksichtigen |
| B31 | niedrig | Start | Update liegt im Benutzerordner; Programm mit relativem Dateinamen starten (`BSTechnikPAPDesigner.exe "aufgabe 1.pap"`) | Datei öffnet sich | leeres Projekt, ohne Hinweis **[getestet durch Prüfer; Code von mir bestätigt]** | Argumente unverändert, aber `cwd` der Kopie (`app/updater.py:337-340`) | Pfade vor der Weitergabe absolut machen |

**Hinweise zur Code-Ebene (keine Nutzerfehler):**

| ID | Art | Befund | Ort |
|---|---|---|---|
| C1 | – | **entfällt, ist jetzt B13.** Ich hatte den Fehler zuerst als „nur im Test“ eingestuft, weil mein Nachbau ein nie gespeichertes Projekt benutzte; mit gespeichertem Projekt tritt er bei jedem Schließen eines Reiters auf (Codex QA-05 hatte den richtigen Ablauf) | – |
| C2 | Windows 10 | `_safe_filename` lässt reservierte Namen (CON, AUX, NUL …) durch; unter Windows 11 problemlos **[getestet]**, unter Windows 10 nicht speicherbar **[vermutet]** | `app/main_window.py:2599` |
| C3 | toter Code | nie benutzt (geprüft gegen app/, main.py, tools/, tests/; Aufrufe über `getattr` ausgenommen): `config.FILE_TYPE_DESCRIPTION`, `errors.log_path()`, `graph.YES_LABELS/NO_LABELS/ELSE_LABELS`, `generators.collect_all_variables`, `pic_asm._SIMPLE`, `label.text_rect_size`, `routing.Rect.from_xywh`, `routing.interior_segments`, `base_item.port_direction`, `base_item.nearest_port`, `factory.snapped`, `Diagram.all_connections`, `Diagram.element_by_id`, `element_types.all_specs` **[getestet: Namenssuche]** | jeweils Definitionsstelle |
| C4 | Testumgebung | Nach vollständig grünen Läufen endete der Python-Prozess unter Windows zweimal mit einem Absturz beim Aufräumen von PySide6 (Exitcode 139 bzw. 127: 40 Zufallsläufe offscreen; Gesamtsuite mit allen QA-Tests). Einzelläufe (alte Suite allein, alle QA-Tests allein) enden mit 0. Unter Linux fängt `tests/conftest.py` das bereits mit `os._exit` ab; unter Windows nicht | Testlauf, nicht die App; Abhilfe wie unter Linux auch unter Windows |

**Ohne Fehler geprüft [getestet]:**

* **Build und Start:** frischer PyInstaller-Build (51 s, 127 MB). Die EXE startet isoliert in 2,7 s (118 MB Arbeitsspeicher, 14 Threads), schließt mit Exitcode 0, Protokoll leer. Deine Einstellungen wurden vorher gesichert und danach exakt zurückgespielt.
* **Bestehende Tests:** 1366 grün (der einzige Fehlschlag war die Zwischenablage, weil ein zweiter Testlauf gleichzeitig lief; einzeln grün).
* **Gesamtsuite am Ende (Windows, mit allen QA-Tests beider KIs):** 1426 bestanden, 10 übersprungen, 42 erwartete Fehlschläge (markierte bekannte Fehler), 0 Fehlschläge. Dazu 8 neue Fehlertests in `test_claude_verified_bugs.py` (alle schlagen wie erwartet fehl).
* **Dateien:** 1050 veränderte Dateien → 687 voll nutzbar (Prüfung, Code in allen Sprachen, Schreibtischtest, Bild, Speichern/Laden identisch), 363 mit verständlicher Meldung abgelehnt; kein Hänger. Auch XML-Bombe, externe Entitäten und PNG/ZIP/UTF-16/HTML als `.pap` werden sauber abgelehnt. Einschränkung: „lädt ohne Absturz“ habe ich als Erfolg gezählt – dass eine Datei mit kaputtem Behälter **leer und ohne Hinweis** geöffnet wird, ist aber selbst ein Fehler (B14, erst durch den Codex-Bericht aufgefallen).
* **Bedienung:** 46 Zufallsläufe à 140 Schritte über Menüs, Kontextmenüs, Seitenleiste, Tasten, Maus, Reiter, Dialoge, danach Speichern/Laden identisch. Alle Tastenkürzel wurden mit echten Tastendrücken geprüft und wirken (außer B01).
* **Speichern:** Umlaute, Emoji, Doppel-Leerzeichen und 120-Zeichen-Namen; schreibgeschützte Datei (verständliche Meldung, alte Datei unverändert, keine Zwischendatei); Datei von einem anderen Programm gesperrt; fehlender Ordner; Rückfrage beim Schließen (Abbrechen/Verwerfen/Speichern).
* **Einstellungen über einen Neustart:** Schalter, Werkzeugknöpfe, Minikarte, Farbschema, eigenes Tastenkürzel, automatisches Speichern.
* **Linux (WSL Ubuntu 22.04, offscreen):** alle QA-Tests laufen ohne Fehlschlag (meine: 36 bestanden, 5 übersprungen, 2 bekannte Fehler; alle zusammen inkl. der anderen KI: 67 bestanden, 40 als bekannte Fehler markiert).

**600 Bausteine [getestet]:** Öffnen 1,0 s · Prüfung 0,06 s · alles verschieben 0,3 s · Rückgängig/Wiederholen 0,6 s ·
Kopieren+Einfügen 1,7 s · einen Baustein einfügen bei 1200 Bausteinen 0,01 s · Code (alle Sprachen) 0,6 s ·
Struktogramm 0,2 s · Schreibtischtest 3000 Schritte 0,3 s · PNG 0,3 s · PDF 0,1 s · Speichern 0,1 s.

---

## 3. UX-Funde mit Verbesserungsvorschlag

**Nielsens 10 Heuristiken**

| Heuristik | Bewertung | Befund | Vorschlag |
|---|---|---|---|
| 1 Sichtbarkeit des Systemzustands | gut | Statuszeile (Bausteine, Pfeile, Auswahl, Raster, Zoom), Hinweis-Zähler, Tempo und Abdeckung im Schreibtischtest | bei langen Aktionen (B02) Fortschritt oder Wartezeiger |
| 2 Sprache der Nutzer | gut | DIN-Begriffe (Vorgang, Verzweigung, Schleifenbeginn), Systemsprache | „Werkzeugpalette“ (Menü) und „Bausteine“ (Feld) vereinheitlichen |
| 3 Kontrolle und Freiheit | mittel | Rückgängig/Wiederholen, Abbrechen in Dialogen | Esc in der Präsentation (B01) |
| 4 Konsistenz | mittel | doppelte Menüeinträge (s. u.), Kurzinfos teils ohne Kürzel (B08), veraltete Kurzinfo (B07) | ein fester Ort je Befehl |
| 5 Fehlervermeidung | gut | Warnzeichen auf Pfeilen, Prüfung, Schutz vor Überschreiben fremd geänderter Dateien, Rückfrage beim Schließen | – |
| 6 Wiedererkennen statt Erinnern | gut | Zifferntasten stehen in der Palette, Suche (Strg+K) findet Befehle und Einstellungen, Kontextmenüs | – |
| 7 Flexibilität und Effizienz | gut | frei belegbare Kürzel, Werkzeugleiste anpassbar, Schnellmenü beim Ziehen ins Leere | – |
| 8 Ästhetik, wenig Ballast | mittel | klare Oberfläche (Bild 01); mit Bedienfeldern wird die Arbeitsfläche winzig (B05); doppelte Überschrift „Bausteine / BAUSTEINE“ | Bedienfelder als Reiter, Überschrift streichen |
| 9 Hilfe bei Fehlern | gut | deutsche Meldungen mit Ursache und meist Lösung („Keine Schreibberechtigung (ist die Datei schreibgeschützt oder in einem anderen Programm geöffnet?)“) | – |
| 10 Hilfe und Doku | gut | F1-Übersicht, 5 Lernbeispiele, Kurzinfos | Lernbeispiel 3 reparieren (B09) |

**Erreichbarkeit:** Alle häufigen Befehle liegen in der Werkzeugleiste (1 Klick) oder direkt im Menü (2 Klicks).
3 Klicks brauchen die Untermenüs Exportieren (PNG/SVG), Farbschema, Sprache, Lernbeispiele, Seite, Pfeile und Prüfung.
**Ohne Kürzel:** Code-Ansicht, Bausteine-Feld, Druckvorschau, Projekteigenschaften, Aufgabe stellen, PNG/SVG-Export,
Schleife mit Kopf-/Fußbedingung, Alle Haltepunkte entfernen. Vorschlag: mindestens Code-Ansicht und PNG-Export belegen.

**Einsteiger:** Neue Projekte beginnen mit Start → Ende, die Zifferntasten stehen sichtbar an den Bausteinen, Lernbeispiele
sind im Hilfe-Menü. Ein Schüler findet sich ohne Anleitung zurecht. Was fehlt, ist ein Hinweis in der leeren Arbeitsfläche,
welche Schreibweisen der Schreibtischtest versteht (z. B. `x = x + 1`, `solange i < 10`).

**Kontrast und Dark Mode:** siehe B10/B11 und Anhang C. Text in allen Bausteinen und alle Pfeile erfüllen WCAG AA in
beiden Schemata (Text 10 : 1 und besser).

**Kleine Bildschirme:** siehe B05 und die Bilder 02/03 (Code-Ansicht abgeschnitten, Palette mit Rollbalken, Statusmeldung
überlappt).

---

## 4. Vorschlag für die neue Menü- und Einstellungsstruktur

**Probleme heute:** „Automatisch anordnen“ steht in Anordnen **und** Extras; „Schreibtischtest“, „Hinweise“ und
„Aufgabe anzeigen“ stehen in Ansicht **und** Extras; „Auswahl in Unterprogramm auslagern“ steht in Bearbeiten **und**
Einfügen; „Sprache“ steckt in Ansicht; die Pfeil- und Prüfschalter liegen in Extras **und** in den Einstellungen.

```
Datei        Neu · Öffnen · Zuletzt geöffnet ▸ · Speichern · Speichern unter
             Exportieren ▸ (PNG · SVG · PDF) · Seite einrichten … (neu, B03) · Druckvorschau · Drucken
             Projekteigenschaften · Schließen · Beenden
Bearbeiten   Rückgängig · Wiederholen · Ausschneiden · Kopieren · Als Bild kopieren · Einfügen · Duplizieren · Löschen
             Alles auswählen · Text bearbeiten · Sonderzeichen ▸ · Suchen (Strg+K)
Einfügen     9 Bausteine · Schleife mit Kopf-/Fußbedingung · Neues Unterprogramm · Auswahl in Unterprogramm auslagern
             Seite ▸ (duplizieren, kopieren, einfügen, verschieben)
Anordnen     Ausrichten ▸ · Verteilen ▸ · Am Raster ausrichten · Nach vorne/hinten · Linienführung ▸ · Automatisch anordnen
Ansicht      Zoom ▸ · Raster · Einrasten · Minikarte · Präsentation
             Bedienfelder ▸ (Bausteine · Schreibtischtest · Hinweise · Code · Aufgabe)
             Seiten ▸ (nächste, vorige, zurück, vorwärts)
Werkzeuge    Schreibtischtest starten (F5) · Haltepunkt (F9) · Alle Haltepunkte entfernen
             Code erzeugen · Struktogramm · Plan prüfen
             Lehrer ▸ (Aufgabe stellen · Aufgabe anzeigen)
             Einstellungen … (Strg+,)
Hilfe        Bedienung (F1) · Lernbeispiele ▸ · Sprache / Language ▸ · Farbschema ▸
             Nach Updates suchen · Dateityp registrieren · Über das Programm
```

**Einstellungen** (bleibt mit Suche): *Allgemein* (Sprache, Farbschema, automatisch speichern, Sicherungskopie,
Updates) · *Zeichnen* (Start/Ende vorgeben, Pfeil-Schalter) · *Prüfung* · *Werkzeugleiste* · *Tastenkürzel*.
**Standardwerte für die Schule** (Einstellungen werden bei jeder Anmeldung zurückgesetzt): die heutigen Standards
passen, mit zwei Ausnahmen: „Automatisch speichern“ ist ab Werk **an** – gut gegen Datenverlust bei eigenen Dateien, für fremde Aufgabendateien aber gefährlich (B15), dort sollte immer eine Kopie entstehen; und das Farbschema ist ab Werk **dunkel**, für den Beamer ist „Hell“ besser (eine Wahl beim ersten Start wäre hilfreich). Zusätzlich empfehle ich „Erweiterte Prüfung“ standardmäßig **an** (Schüler sehen unbeschriftete Ausgänge
und Wege ohne Ende sofort) und den Knopf „Als PDF exportieren“ in der Standard-Werkzeugleiste (Abgabe).

---

## 5. Paritäts-Tabelle mit dem Original (PapDesigner 2.2.0.8, F. Folkmann)

Quelle Original: Oberflächentexte aus der installierten `PapDesigner.exe` ausgelesen, das Programm wurde **nicht bedient**.
„laut Programmtext“ = belegt, aber nicht ausprobiert.

| Funktion | Original | diese App | Bewertung |
|---|---|---|---|
| Symbole Start/Ende, Vorgang, Ein-/Ausgabe, Verzweigung, Unterprogramm, Schleifenbegrenzung, Kommentar, Verbindungspunkt | ja (Dateiformat) | ja, DIN-gerecht (Anhang D) | gleich |
| Schleife mit Kopf-/Fußbedingung als Vorlage | ja (laut Programmtext) | ja | gleich |
| Symbol umwandeln | Vorgang/Eingabe/Ausgabe/Unterprogramm | alle Ablauf-Bausteine | besser |
| Unterprogramme als eigene Diagramme, auslagern, Diagramme kopieren/einfügen | ja | ja (Seiten, Reiter, „Ruft auf“) | gleich |
| Unterprogrammaufruf mit Parametern (`b = Sin(a) + c`) | ja (laut Programmtext) | Aufrufe mit Zuweisung/Argumenten werden zugeordnet (README 1.9) | gleich |
| Bedingter Trennstrich `~`, Zeilenumbruch Strg+Enter | ja | ja | gleich |
| Rückgängig/Wiederholen, Zoom, Raster | ja | ja | gleich |
| Präsentationsansicht | ja | ja (Esc defekt, B01) | gleich |
| Bildexport | BMP, JPG, PNG, TIF; Pixelgröße, transparent, JPG-Qualität, „im Grafikprogramm öffnen“ | PNG, SVG, PDF; Maßstab, transparent, Namenszeile | besser (SVG/PDF), fehlt: JPG/BMP/TIF, Öffnen nach Export |
| Drucken | „Seite einrichten“, „Druckseiten individuell skalieren“ | eine Seite, seitenfüllend, Druckvorschau | schlechter (B03) |
| Prüfung | „Diagramm prüfen … auf logische Fehler“ | laufende Hinweise, Warnzeichen, erweiterte Prüfung | besser |
| Schutz | Dokumentenschutz mit Passwort | Lehrermodus: Aufgabe offen, Lösung verschlüsselt | anders, eher besser |
| Mehrere Projekte gleichzeitig | Option | immer (Reiter) | gleich |
| „Alle speichern“, „Alle schließen“, „Projektdatei löschen“ | ja (laut Programmtext) | nein | fehlt (niedrig) |
| Englische Symboltexte, schmale Schrift | ja | 9 Oberflächensprachen, eine Schrift überall | anders |
| Verbindungslinie bis zum Quellsymbol verfolgen | ja (laut Programmtext) | nein | fehlt (niedrig) |
| Tutorials / Beispiele | eingebaute Tutorials | 5 Lernbeispiele | gleich |
| Schreibtischtest, Codeerzeugung (inkl. PIC-Assembler), Struktogramm, Code-Ansicht, Minikarte, Suche | in den Programmtexten nicht gefunden | ja | besser |
| Dateien des Originals öffnen | – | ja; laut README 1.10.1 auch umgekehrt mit 44 echten Dateien im Original geprüft (hier **nicht** wiederholt, weil das Werkzeug ein laufendes Original beendet) | gleich |
| Plattformen | Windows (.NET) | Windows + Linux (AppImage), Updates ohne Adminrechte | besser |

---

## 6. Feature-Vorschläge nach Priorität

| Vorschlag | Nutzen | Aufwand |
|---|---|---|
| Druck: Maßstab wählbar / auf mehrere Seiten verteilen (B03) | hoch | M |
| Schnellere Linienführung großer Pläne (B02) | mittel | M |
| Bedienfelder für kleine Bildschirme (Reiter, einklappbar) (B05) | mittel | M |
| PDF wahlweise in A4 (B04) | mittel | S |
| Kontraste im dunklen Schema anheben (B10/B11) | mittel | S |
| Code-Signatur für EXE und Setup (B12) | mittel | M (Zertifikat) |
| Kurze Syntax-Hilfe für Bausteintexte (was der Schreibtischtest versteht) | mittel | S |
| JPG-Export (Schulplattformen) und „Bild nach dem Export öffnen“ | niedrig | S |
| „Alle speichern“ / „Alle schließen“ | niedrig | S |
| Linie bis zum Quellbaustein verfolgen | niedrig | S |
| Aufgabendateien als „Vorlage“ öffnen (immer als unbenannte Kopie) | hoch | S |
| Gemeinsame Referenzfälle: Schreibtischtest, Python, Java, PIC mit gleichen Eingaben vergleichen | hoch | M |
| Pfeile per Tastatur anlegen (Quelle → Ziel wählen), Bausteinliste für Bildschirmleser | mittel | L |
| Sichtbare Anzeige „Wird automatisch gespeichert in …“ in der Statuszeile | mittel | S |

---

## 7. Top 10 nächste Schritte

1. **Automatisches Speichern absichern (B13–B15):** Fehlermeldung beim Schließen eines Reiters beheben, beschädigte Dateien
   nicht leer öffnen und nie automatisch überschreiben, Aufgabendateien als unbenannte Kopie öffnen. (Datenverlust zuerst.)
2. **Schreibtischtest und Code gleich rechnen lassen (B16, B23, B25, B27):** gemeinsame Referenzfälle, die Schreibtischtest,
   Python, Java und PIC mit denselben Eingaben vergleichen (deckt auch Codex QA-06 bis QA-10 ab).
3. **Tastatur:** Esc in der Präsentation (B01), Tab zu den Bausteinen (B19).
4. **Kleine, schnelle Fehler:** Ausschneiden/Rückgängig/Einfügen (B17), Name nach Rückgängig (B18), Datei doppelt offen (B20),
   Aufgabentext als HTML (B21).
5. **Druck und PDF:** Maßstab bzw. mehrere Seiten, PDF in A4 (B03, B04).
6. **Großer Plan:** räumlicher Filter in `routing.py`/`scene.py` (B02; der `xfail`-Test in `test_claude_load.py` misst es).
7. **Schul-IT:** `policy.ini` in jeder Kodierung lesen (B22), Update-Rückweg mit Wiederholung (B24).
8. **Kleine Bildschirme und Kontraste** (B05, B10, B11).
9. **Codex-Funde nachstellen**, die ich nicht geprüft habe (Anhang B), besonders QA-01, QA-07, QA-08, QA-12, QA-16.
10. **Kleinigkeiten:** B06–B09, B12 (Signatur), B26–B31, C2, C3 (toter Code).

---

## Anhang A – Wie geprüft wurde

* **Inventar** direkt aus dem laufenden Hauptfenster ausgelesen (Menüs, Kontextmenüs, Kürzel, Docks, Einstellungen) → Anhang E.
* **Neue Tests** (`tests/qa/`):
  `test_claude_shortcuts.py` (jedes Kürzel mit echtem Tastendruck) ·
  `test_claude_monkey.py` (Zufallsbedienung des Fensters, `PAP_QA_MONKEY=40` für mehr Läufe) ·
  `test_claude_file_fuzz.py` (veränderte und fremde Dateien, `PAP_QA_FUZZ=300` für mehr Fälle) ·
  `test_claude_load.py` (600 Bausteine, Zeiten, Speicher) ·
  `test_claude_files_and_settings.py` (Pfade, Schreibschutz, Sperre, Schließen-Rückfrage, Einstellungen über Neustart).
  `test_claude_verified_bugs.py` (B13, B14, B17–B22 als Tests, damit eine Reparatur sie direkt nutzen kann).
  Bekannte Fehler sind als `xfail(strict=True)` mit Bug-ID markiert: Wird ein Fehler behoben, meldet sich der Test.
* **Build und Start** der EXE isoliert (eigenes `LOCALAPPDATA`, Registry vorher gesichert und zurückgespielt), Defender-Scan, Signaturprüfung.
* **Bildschirmfotos** in `tests/qa/screenshots_claude/`: 01 hell 1366×768 · 02 dunkel mit allen Bedienfeldern ·
  03 hell 150 % · 04 hell 200 % · 05 1024×600.
* **Kontraste** aus den Farbwerten in `app/styles.py` nach der WCAG-Formel berechnet (99 Paare) → Anhang C.
* **Linux:** alle QA-Tests in WSL Ubuntu 22.04 (Python 3.13, PySide6 6.12, offscreen).
* **Original-PapDesigner:** Oberflächentexte aus der EXE ausgelesen (nicht bedient).
* **Codesuche:** 4 Prüfer haben die riskantesten Bereiche vollständig gelesen (Bearbeiten/Pfeile, Hauptfenster/Dateien/Lehrermodus,
  Schreibtischtest/Codeerzeugung, Start/Updates/Linux) und 16 Funde mit eigenen Skripten nachgestellt. Die wichtigsten habe ich mit eigenen Skripten wiederholt (**[getestet]**); bei den übrigen steht in der Tabelle, ob ich die Ursache im Code bestätigt habe (**[getestet durch Prüfer]**).
* **Panne während der Prüfung (behoben):** Mein Zufallstest hat zwischen dem 20.11. nachmittags und dem 21.11. um 00:11 die Datei `examples/Beispiel_Mittelwert.pap` im Projekt mehrfach überschrieben (er öffnete sie und drückte Strg+S) und daneben eine `.pap-backup` angelegt. Ich habe die Datei mit `git checkout` auf den Stand im Repository zurückgesetzt und die Sicherung gelöscht. Seitdem arbeiten alle meine Tests nur mit Kopien und prüfen am Ende per Prüfsumme, dass keine Beispieldatei verändert wurde. Testläufe der anderen KI in diesem Zeitraum könnten das veränderte Beispiel gesehen haben.

**Nicht geprüft:** echte Mehrmonitor-Systeme mit verschiedener Skalierung, Windows 10, Wayland/X11 mit echtem
Bildschirm, das fertige AppImage auf einem Linux ohne Bibliotheken (nur die Tests unter Linux), SmartScreen-Dialog
selbst, Ausdruck auf echtem Drucker, OneDrive mit „Dateien bei Bedarf“.

## Anhang B – Abgleich mit dem Codex-Bericht (`QA-BERICHT-CODEX.md`)

Beide Berichte sind unabhängig voneinander entstanden (gleicher Auftrag, gleicher Stand 1.15.3).

**Von beiden gefunden:** B01 = QA-21 (Esc) · B10 = QA-23 (Kontrast 2,75 : 1) · B11 ≈ Codex 1.4.11 (Feldränder) ·
B12 = OFF-03 (unsigniert) · B13 = QA-05 (Fehler beim Schließen eines Reiters) · B14 = QA-03 (beschädigte Datei öffnet leer) ·
B19 = QA-11 (Tab) · B23 ≈ QA-10 (Text × Kommazahl).
**Von mir nachgeprüft und bestätigt:** QA-03, QA-05, QA-11 (dabei habe ich meine Einstufung von C1 korrigiert, s. B13).

**Nur in meinem Bericht:** B02–B09 (große Pläne, Druck, PDF, kleine Bildschirme, Speicher, Texte), B15 (Aufgabendatei
überschrieben), B16–B18, B20–B22, B24–B31, C2, C3, die Lastwerte mit 600 Bausteinen und die Datei-/Bedien-Zufallstests.

**Nur bei Codex, von mir nicht nachgeprüft** (meine Einschätzung in Klammern):
QA-01 Export hängt die Endung nach dem Dialog an und überschreibt dabei still eine vorhandene Datei (realistisch bei Namen mit
Punkt wie „Aufgabe 1.2“; ich würde „mittel“ statt „kritisch“ wählen) · QA-02 Datei zwischen Lesen und Zeitstempel ersetzt
(sehr enges Zeitfenster, niedrig) · QA-04 fremde `icuuc.dll` im Build-PATH (hängt vom Build-Rechner ab; mein frischer Build
lief) · QA-06 Zählschleife mit Schritt 0 läuft endlos · QA-07 Parameter und Rückgabe bei Unterprogrammaufrufen werden still
ignoriert (wichtig für den Unterricht, ähnlich B16) · QA-08 Mehrfachverzweigung ohne passenden Fall nimmt die letzte Kante ·
QA-09 maskierte Anführungszeichen · QA-12 gelöschte Datei wird vom automatischen Speichern neu angelegt (gehört zu B13–B15) ·
QA-13 Druckbereich wird ignoriert · QA-14 Namenszeile beim Druck verschoben · QA-15 Selbstverbindung per Maus blockiert ·
QA-16 „Diagramm einpassen“ endet bei 25 %, große Pläne passen nicht ganz hinein · QA-17 Titel ändert sich beim Austausch mit
dem Original · QA-18 Java zählt Emoji doppelt · QA-19 Struktogramm-Titel abgeschnitten · QA-20 japanische
Unterprogrammnamen · QA-22 gleiches Kürzel in beiden Feldern macht die Aktion wirkungslos · QA-24 Bildschirmleser finden
keine Namen/Rollen (Palette, Arbeitsfläche, Minikarte) · QA-25 bis QA-31 Kleinigkeiten · OFF-02 Speicherbedarf der
Strukturanalyse wächst quadratisch.

**Unterschiede im Vorgehen:** Codex hat den Original-PapDesigner bedient (Dateien in beide Richtungen, frische Originaldatei),
die Screenreader-Schnittstelle abgefragt und das AppImage unter WSLg gestartet; ich habe das Original nur über seine
Programmtexte verglichen, dafür Last, Speicher, Zufallsbedienung, Datei-Mutationen und vier Code-Bereiche vollständig geprüft.
Zusammen ergeben beide Berichte das vollständigere Bild.

## Anhang C – Kontraste (WCAG 2.1 AA, Auszug)

| Schema | Element | Vordergrund | Hintergrund | Verhältnis | nötig | ok? |
|---|---|---|---|---|---|---|
| dunkel | Knopftext auf Akzent / markierte Zeile | #F2F5F9 | #5B96E8 | 2,75 | 4,5 | **nein** |
| dunkel | gedämpfter Text auf erhöhtem Feld | #8D949E | #2B2F36 | 4,39 | 4,5 | **nein** |
| dunkel | Fehlerfarbe auf Feld | #D46A6A | #24272D | 4,33 | 4,5 | **nein** |
| dunkel | Feldrahmen | #30343B | #24272D | 1,20 | 3,0 | **nein** |
| hell | Feldrahmen | #D6DAE0 | #F6F7F9 | 1,31 | 3,0 | **nein** |
| dunkel | gedämpfter Text auf Fenster / Feld | #8D949E | #1F2227 / #24272D | 5,21 / 4,89 | 4,5 | ja |
| hell | gedämpfter Text auf Fenster / Feld | #5B6370 | #ECEEF1 / #F6F7F9 | 5,22 / 5,66 | 4,5 | ja |
| beide | Text in allen 8 Bausteintypen | – | – | ≥ 10,0 (dunkel) | 4,5 | ja |
| dunkel / hell | Pfeil, roter Pfeil, gelber Pfeil auf Arbeitsfläche | – | – | 5,59 / 4,88 / 7,50 · 6,36 / 4,62 / 3,48 | 3,0 | ja |
| dunkel / hell | Pfeilbeschriftung | – | – | 10,56 / 12,90 | 4,5 | ja |

Insgesamt 99 Paare (dunkel, hell, Export), 6 Verstöße (der sechste: Rahmen im Export-Schema, ohne Bedeutung für den Druck).

## Anhang D – DIN 66001

| Symbol | Norm | App | ok? |
|---|---|---|---|
| Grenzstelle (Start/Ende) | Oval bzw. abgerundetes Rechteck | abgerundet (Stadion) | ja |
| Operation (Vorgang) | Rechteck | Rechteck | ja |
| Verzweigung | Raute, Ausgänge beschriftet | Raute, Beschriftung ja/nein, auch mehrere Ausgänge | ja |
| Unterprogramm | Rechteck mit doppelten senkrechten Linien | so | ja |
| Ein-/Ausgabe | Parallelogramm (ein Symbol) | Parallelogramm, als Eingabe und Ausgabe getrennt (nur Farbe/Name) | ja |
| Schleifenbegrenzung | Anfang: oben abgeschrägte Ecken, Ende: unten abgeschrägt | so (Bild 01) | ja |
| Bemerkung | eckige Klammer mit gestrichelter Linie | so | ja |
| Ablauflinie | Linie, Richtung mit Pfeilspitze | Pfeilspitze an jeder Linie | ja |
| Zusammenführung / Verbindungspunkt | Linien treffen sich | Verbindungspunkt (Punkt) | ja |
| Übergangsstelle (Konnektor, Kreis mit Kennzeichen) | Kreis | **fehlt** – bei Plänen über mehrere Seiten nützlich | fehlt (**unsicher**, ob in der Schule verlangt) |
| Operation von Hand (Trapez) | in der Norm enthalten (**unsicher**) | fehlt | für Schul-PAPs unüblich |

## Anhang E – Inventar (aus dem laufenden Programm ausgelesen)

**Menüs** (Kürzel in Klammern, [an]/[aus] = Schalter und Standard)

* **Datei:** Neu (Strg+N) · Öffnen … (Strg+O) · Zuletzt geöffnet ▸ · Speichern (Strg+S) · Speichern unter … (Strg+Umschalt+S) · Automatisch speichern [an] · Sicherungskopie anlegen [an] · Exportieren ▸ PNG / SVG / PDF (Strg+E) · Druckvorschau … · Drucken … (Strg+P) · Projekteigenschaften … · Schließen (Strg+F4, Strg+W) · Beenden (Strg+Q)
* **Bearbeiten:** Rückgängig (Strg+Z, Alt+Rücktaste) · Wiederholen (Strg+Y, Strg+Umschalt+Z) · Ausschneiden (Strg+X, Umschalt+Entf) · Kopieren (Strg+C, Strg+Einfg) · Als Bild kopieren (Strg+Umschalt+B) · Einfügen (Strg+V, Umschalt+Einfg) · Duplizieren (Strg+D) · Löschen (Entf) · Alles auswählen (Strg+A) · Auswahl aufheben (Esc) · Text bearbeiten (F2) · Sonderzeichen ▸ (23 Zeichen: ≤ ≥ ≠ ≈ ← → × · ÷ ± ² ³ √ π ∞ ∑ ∧ ∨ ¬ ° „…“ … ~) · Auswahl in Unterprogramm auslagern … (Strg+Alt+U) · Seite ▸ (duplizieren, kopieren, ausschneiden, einfügen, nach links Strg+Umschalt+Bild↑, nach rechts Strg+Umschalt+Bild↓)
* **Ansicht:** Zoom + (Strg++, Strg+=) · Zoom − (Strg+-) · Auf 100 % (Strg+0) · Diagramm einpassen (Strg+1) · Raster anzeigen (Strg+G) [an] · Am Raster einrasten (Strg+Umschalt+G) [an] · Präsentationsansicht (F11) · Farbschema ▸ Dunkel/Hell · Sprache / Language ▸ Automatisch + 9 Sprachen · Unterprogramm öffnen · Nächste/Vorherige Seite (Strg+Bild↓/↑) · Zurück/Vorwärts (Alt+Links/Rechts) · Werkzeugleiste · Werkzeugpalette · Schreibtischtest (Strg+T) · Hinweise (Strg+Umschalt+H) · Aufgabe anzeigen (Strg+Umschalt+A) · Code-Ansicht · Minikarte (Strg+M) [an]
* **Einfügen:** Eingabe 1 · Ausgabe 2 · Vorgang 3 · Unterprogramm 4 · Verzweigung 5 · Schleife 6 · Schleife mit Kopfbedingung · Schleife mit Fußbedingung · Kommentar 7 · Start 8 · Ende 9 · Neues Unterprogramm … (Strg+Umschalt+U) · Auswahl in Unterprogramm auslagern … (Strg+Alt+U)
* **Anordnen:** Links/Rechts/Oben/Unten ausrichten · Mittig (Spalte/Zeile) · Horizontal/Vertikal verteilen · Am Raster ausrichten · Nach vorne/hinten (Strg+Umschalt+↑/↓) · Schleifenbeginn/-ende umschalten · Knick einfügen · Linienführung zurücksetzen · Automatisch anordnen (Strg+L)
* **Extras:** Code erzeugen … (Strg+Umschalt+C) · Struktogramm … (Strg+Umschalt+N) · Automatisch anordnen (Strg+L) · Pfeile ▸ (Pfeil bleibt im Leeren stehen [aus], Schnellmenü im Leeren [an], Abgerundete Ecken [an]) · Prüfung ▸ (Warnzeichen auf Pfeilen [an], Erweiterte Prüfung [aus]) · Schreibtischtest (Strg+T) · Hinweise (Strg+Umschalt+H) · Haltepunkt setzen/entfernen (F9) · Alle Haltepunkte entfernen · Aufgabe stellen … · Aufgabe anzeigen (Strg+Umschalt+A) · Suchen … (Strg+K) · Einstellungen … (Strg+,)
* **Hilfe:** Tastenkürzel und Bedienung (F1) · Lernbeispiele ▸ (5) · Dateityp registrieren … · Nach Updates suchen … · Beim Start nach Updates suchen [an] · Über das Programm

**Werkzeugleiste (Standard):** Neu, Öffnen, Speichern │ Rückgängig, Wiederholen, Löschen │ Zoom −, 100 %, Zoom +, Einpassen │ Automatisch anordnen, Schreibtischtest, Struktogramm │ Drucken │ „Mehr“ ▾ (Code-Ansicht, Minikarte, Aufgabe, Haltepunkte, Raster, Ausrichten, Als Bild kopieren, Präsentation, Einstellungen) │ Suchfeld. 17 Knopfgruppen sind in den Einstellungen einzeln zuschaltbar.

**Bedienfelder:** Bausteine (rechts, sichtbar) · Schreibtischtest (unten, Strg+T) · Hinweise (unten, Strg+Umschalt+H) · Code (links) · Aufgabe (oben, Strg+Umschalt+A) · Minikarte (in der Arbeitsfläche, Strg+M) · Seitenleiste der Unterprogramme (unten).

**Kontextmenüs:** leere Fläche (Neu ▸ 9 Bausteine, Einfügen, Alles auswählen, Als Bild kopieren, Neues Unterprogramm, Raster ▸, Ansicht ▸) · Baustein (Text bearbeiten, Ausschneiden, Kopieren, Als Bild kopieren, Duplizieren, Löschen, Nach vorne/hinten, Schleife: in Beginn/Ende umwandeln, Unterprogramm: anlegen/öffnen + „Ruft auf“ ▸, Ändern in ▸, Auslagern, Haltepunkt, bei Mehrfachauswahl Ausrichten ▸, Am Raster ausrichten) · Pfeil (Beschriftung bearbeiten F2, Knick hier einfügen, Linienführung zurücksetzen, Verbindungspunkt hier einfügen, Löschen) · Seitenleiste (Neues Unterprogramm, Seite einfügen, je Seite weitere Befehle).

**Einstellungsfenster:** Abschnitte Allgemein │ Zeichnen │ Prüfung │ Werkzeugleiste │ Tastenkürzel, Suchfeld; 26 Schalter (Automatisch speichern [an], Sicherungskopie [an], Updates beim Start [an], Mit Start und Ende beginnen [an], 3 Pfeil-Schalter, 2 Prüf-Schalter, 17 Werkzeugknöpfe); „Alle zurücksetzen“ (Kürzel), „Alle Schalter zurücksetzen“; jedes Kürzel frei belegbar (2 Tasten je Funktion).

**Bausteine:** Start, Ende, Eingabe, Ausgabe, Vorgang, Unterprogramm, Verzweigung (auch mehrere Ausgänge), Schleife (Beginn/Ende), Kommentar, Verbindungspunkt.

**Weitere Funktionen:** Schreibtischtest (Schritt F10, zurück Strg+F10, Ausführen F5, Abspielen F6, Tempo, Haltepunkte, Variablen mit „vorher“, Ausgaben, Protokoll, Abdeckung, Tabelle kopieren/CSV) · Code: PIC16F887-Assembler (Standard), Pseudocode, Python, Java, Code-Ansicht mit Zeilen↔Baustein · Struktogramm (Bild, Zwischenablage) · Lehrermodus (Aufgabe offen, Lösung verschlüsselt) · Namenszeile (Name/Klasse/Datum) auf PNG/PDF/Druck · Suche nach Funktionen, Einstellungen und Bausteinen · 9 Sprachen, Systemsprache · Updates mit Benutzerkopie ohne Adminrechte · ein Fenster mit Reitern (weitere Starts übergeben ihre Dateien) · Wiederherstellung nach Absturz · Warnung, wenn die Datei außerhalb geändert wurde · Linux-AppImage.
