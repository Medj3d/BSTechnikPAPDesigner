"""Zentrale Konfiguration der Anwendung.

Der Programmname, die Dateiendung und alle Standardwerte werden ausschließlich
hier definiert, damit sie später an genau einer Stelle geändert werden können.
"""

APP_NAME = "BS Technik PAP Designer"
# Version und Erscheinungsmonat: bei jeder neuen Veröffentlichung beide anpassen.
# Die Versionsnummer muss dabei steigen – daran erkennt das Programm ein Update.
APP_VERSION = "1.5.2"
APP_RELEASE_DATE = "Oktober 2026"
APP_AUTHORS = ("Are Schäfer", "Linus Twardzik")
# Text auf dem Ladebildschirm
SPLASH_CREDIT = "A product for BS Technik from Are Schäfer and Linus Twardzik"
# So lange bleibt der Ladebildschirm mindestens sichtbar (Millisekunden)
SPLASH_MIN_DURATION_MS = 6000
ORGANIZATION_NAME = "BS Technik"
ORGANIZATION_DOMAIN = "bstechnik.local"
# Kennung für QSettings (Registry-Schlüssel unter HKCU\Software\<ORG>\<SETTINGS_APP>)
SETTINGS_APP_NAME = "PAPDesigner"
# Kennung für die Windows-Taskleiste (AppUserModelID)
WINDOWS_APP_ID = "BSTechnik.PAPDesigner.1"

# Dateiformat: ".pap" ist das einzige Projektformat
FILE_EXTENSION = ".pap"
FILE_TYPE_DESCRIPTION = "Programmablaufplan"
FILE_DIALOG_FILTER = f"Programmablaufpläne (*{FILE_EXTENSION})"
# ProgID für die Windows-Dateizuordnung
FILE_PROG_ID = "BSTechnik.PAPDesigner.Project"

DEFAULT_PROJECT_NAME = "Unbenannt"

# Automatisches Speichern: Ein bereits gespeichertes Projekt wird so lange nach
# der letzten Änderung von selbst in seine Datei geschrieben (Millisekunden).
AUTO_SAVE_DELAY_MS = 2000
# … spätestens aber nach dieser Zeit, auch wenn ununterbrochen weitergearbeitet wird
AUTO_SAVE_MAX_WAIT_MS = 10000
AUTO_SAVE_DEFAULT = True

# Updates: GitHub-Projekt ("Besitzer/Name"), dessen neueste Veröffentlichung das
# fertige Programm beim Start prüft. Leer = keine Update-Prüfung.
UPDATE_REPOSITORY = "Medj3d/BSTechnikPAPDesigner"
UPDATE_MANIFEST_NAME = "version.json"
UPDATE_PACKAGE_NAME = "BSTechnikPAPDesigner.zip"
EXECUTABLE_NAME = "BSTechnikPAPDesigner.exe"
# Setup-Datei zum Weitergeben (installiert das Programm; entsteht mit release.bat)
SETUP_FILE_NAME = "BSTechnikPAPDesigner-Setup.exe"
# Mit diesem Aufruf installiert die neue Programmdatei ein Update (siehe app/updater.py)
UPDATE_APPLY_FLAG = "--apply-update"

# Raster
DEFAULT_GRID_SIZE = 20
MIN_GRID_SIZE = 10
MAX_GRID_SIZE = 100
DEFAULT_GRID_VISIBLE = True
DEFAULT_SNAP_TO_GRID = True

# Zoom
MIN_ZOOM = 0.25
MAX_ZOOM = 4.0
ZOOM_STEP = 1.15  # Faktor pro Mausrad-Raste bzw. Menübefehl

# Größe der (praktisch unbegrenzten) Szene in Szeneneinheiten
SCENE_HALF_EXTENT = 50000

# Bausteingrößen werden in diesen Schritten quantisiert, damit Bausteine
# nicht bei jedem Zeichen unkontrolliert wachsen und Kanten auf dem Raster liegen.
SIZE_STEP_WIDTH = 40
SIZE_STEP_HEIGHT = 20

# Schrift innerhalb der Bausteine (Pixelgröße in Szeneneinheiten)
ITEM_FONT_FAMILIES = ["Segoe UI", "Inter", "Helvetica Neue", "Arial"]
ITEM_FONT_PIXEL_SIZE = 13
LABEL_FONT_PIXEL_SIZE = 12

# Einfügeversatz beim wiederholten Einfügen aus der Zwischenablage
PASTE_OFFSET = 40

# Export
EXPORT_MARGIN = 40
EXPORT_DEFAULT_PNG_SCALE = 2.0

# Maximale Anzahl zuletzt geöffneter Dateien
MAX_RECENT_FILES = 8
