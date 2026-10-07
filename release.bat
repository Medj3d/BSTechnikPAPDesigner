@echo off
rem Veroeffentlicht die aktuelle Version als Update:
rem   1. Programm bauen (build_exe.bat)
rem   2. Paket und version.json erzeugen und bei GitHub hochladen
rem Vorher in app\config.py die Versionsnummer erhoehen!
rem Aufruf:  release.bat ["Was ist neu in dieser Version"]
cd /d "%~dp0"
call build_exe.bat || goto :error
python tools\make_release.py %1 || goto :error
goto :eof

:error
echo.
echo Die Veroeffentlichung wurde nicht abgeschlossen.
exit /b 1
