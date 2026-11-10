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
# Feste Versionen von appimagetool und der AppImage-Laufzeit (mit Prüfsumme). Die Laufzeit ist statisch gebaut:
# Das AppImage braucht auf dem Zielsystem keine libfuse2 mehr, nur FUSE selbst (fusermount, fast überall da).
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64"
RUNTIME_SHA256="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
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

# Startskript: prüft die wenigen Systembibliotheken und startet das Programm (installer/linux/AppRun)
tr -d '\r' < installer/linux/AppRun > "$APPDIR/AppRun"
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
download() {  # download <URL> <Ziel> <SHA-256>: lädt nur einmal und prüft die Prüfsumme
    if [ ! -f "$2" ] || ! echo "$3  $2" | sha256sum -c --status; then
        echo "Lade $1"
        curl -fsSL -o "$2.part" "$1"
        echo "$3  $2.part" | sha256sum -c --quiet || { echo "Prüfsumme falsch: $1"; exit 1; }
        mv "$2.part" "$2"
    fi
    chmod 755 "$2"
}

TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
    TOOL="$BUILD/appimagetool-x86_64.AppImage"
    download "$APPIMAGETOOL_URL" "$TOOL" "$APPIMAGETOOL_SHA256"
fi
RUNTIME="$BUILD/runtime-x86_64"
download "$RUNTIME_URL" "$RUNTIME" "$RUNTIME_SHA256"

mkdir -p dist
rm -f "dist/$PACKAGE"
# APPIMAGE_EXTRACT_AND_RUN: appimagetool selbst ohne FUSE starten (z. B. in Containern und CI)
ARCH=x86_64 VERSION="$VERSION" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream --runtime-file "$RUNTIME" \
    "$APPDIR" "dist/$PACKAGE"
chmod 755 "dist/$PACKAGE"
echo
echo "Fertig: dist/$PACKAGE ($(du -h "dist/$PACKAGE" | cut -f1))"
