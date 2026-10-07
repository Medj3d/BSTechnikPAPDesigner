@echo off
rem Erzeugt die Windows-Anwendung mit PyInstaller.
rem Ergebnis: dist\BSTechnikPAPDesigner\BSTechnikPAPDesigner.exe
rem Zwischendateien landen im Temp-Ordner, nicht im Projektordner.
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt || goto :error
python tools\generate_icons.py || goto :error
python -m PyInstaller --noconfirm --workpath "%TEMP%\BSTechnikPAPDesigner-build" BSTechnikPAPDesigner.spec || goto :error
echo.
echo Fertig: dist\BSTechnikPAPDesigner\BSTechnikPAPDesigner.exe
goto :eof

:error
echo.
echo Beim Erstellen ist ein Fehler aufgetreten.
exit /b 1
