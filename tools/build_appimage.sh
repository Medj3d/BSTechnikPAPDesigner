#!/usr/bin/env bash
# Baut die Linux-Version als AppImage: eine einzige Datei, die auf fast allen Distributionen läuft.
#
#   tools/build_appimage.sh
#
# Ergebnis: dist/BSTechnikPAPDesigner-x86_64.AppImage
#
# Ablauf: PyInstaller baut den Programmordner (dist/BSTechnikPAPDesigner), der kommt mit Startskript (AppRun),
# Desktop-Eintrag und Symbol in einen AppDir-Ordner, und appimagetool packt daraus das AppImage.
# Gebaut wird am besten auf einem älteren System (z. B. Ubuntu 22.04): Das AppImage läuft dann auch auf allen
# neueren (glibc ist abwärts-, aber nicht aufwärtskompatibel). Der GitHub-Workflow
# .github/workflows/linux-appimage.yml macht genau das.
#
# Umgebungsvariablen (alle optional):
#   PYTHON        Python-Interpreter (Standard: python3)
#   SKIP_PIP=1    Abhängigkeiten nicht installieren (schon vorhanden)
#   APPIMAGETOOL  Pfad zu appimagetool (sonst aus PATH oder heruntergeladen)
#   BUILD_DIR     Ordner für Zwischendateien (Standard: ein neuer Temp-Ordner)
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
NAME="BSTechnikPAPDesigner"
DESKTOP_ID="bstechnik-papdesigner"
# Feste Version von appimagetool (AppImageKit 13); das AppImage braucht damit auf dem Zielsystem libfuse2
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage"
BUILD="${BUILD_DIR:-$(mktemp -d -t bstechnik-appimage-XXXXXX)}"
mkdir -p "$BUILD"

if [ "${SKIP_PIP:-0}" != "1" ]; then
    "$PYTHON" -m pip install -r requirements-dev.txt
fi

VERSION="$("$PYTHON" -c 'from app import config; print(config.APP_VERSION)')"
PACKAGE="$("$PYTHON" -c 'from app import config; print(config.LINUX_PACKAGE_NAME)')"
echo "Baue $NAME $VERSION als $PACKAGE"

# Die Symbole (assets/*.png) kommen fertig aus dem Repository – unter Linux nicht neu zeichnen (andere Schriften)
"$PYTHON" -m PyInstaller --noconfirm --workpath "$BUILD/pyinstaller" BSTechnikPAPDesigner.spec

# ------------------------------------------------------------------ AppDir
APPDIR="$BUILD/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a "dist/$NAME" "$APPDIR/usr/lib/$NAME"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# Startskript des AppImage: startet das gebündelte Programm mit allen Argumenten (z. B. Projektdateien).
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/BSTechnikPAPDesigner/BSTechnikPAPDesigner" "$@"
APPRUN
chmod 755 "$APPDIR/AppRun"

cat > "$APPDIR/$DESKTOP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=BS Technik PAP Designer
Comment=Programmablaufpläne
Exec=$NAME %F
Icon=$DESKTOP_ID
Terminal=false
Categories=Education;Development;
MimeType=application/x-bstechnik-pap;
StartupWMClass=$NAME
X-AppImage-Version=$VERSION
DESKTOP

cp assets/app_icon.png "$APPDIR/$DESKTOP_ID.png"
ln -sf "$DESKTOP_ID.png" "$APPDIR/.DirIcon"

# ------------------------------------------------------------- appimagetool
TOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [ -z "$TOOL" ]; then
    TOOL="$BUILD/appimagetool-x86_64.AppImage"
    if [ ! -x "$TOOL" ]; then
        echo "Lade appimagetool: $APPIMAGETOOL_URL"
        curl -fsSL -o "$TOOL" "$APPIMAGETOOL_URL"
        chmod 755 "$TOOL"
    fi
fi

mkdir -p dist
rm -f "dist/$PACKAGE"
# APPIMAGE_EXTRACT_AND_RUN: appimagetool selbst ohne FUSE starten (z. B. in Containern und CI)
ARCH=x86_64 VERSION="$VERSION" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "dist/$PACKAGE"
chmod 755 "dist/$PACKAGE"
echo
echo "Fertig: dist/$PACKAGE ($(du -h "dist/$PACKAGE" | cut -f1))"
