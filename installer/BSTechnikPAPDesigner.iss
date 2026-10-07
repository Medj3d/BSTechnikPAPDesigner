; Inno-Setup-Skript (optional) für den BS Technik PAP Designer.
; Voraussetzung: vorher build_exe.bat ausführen.
; Übersetzen mit Inno Setup 6 (https://jrsoftware.org/isinfo.php).
; Das Setup registriert die Dateiendung .pap als Projektdateityp.

#define AppName "BS Technik PAP Designer"
#define AppVersion "1.5.1"
#define AppExe "BSTechnikPAPDesigner.exe"
#define ProgId "BSTechnik.PAPDesigner.Project"

[Setup]
AppId={{8C5E2B55-4F0B-4B6E-9B5B-3C0B8E6B2D41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BS Technik
DefaultDirName={autopf}\BS Technik\PAP Designer
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=BSTechnikPAPDesigner-Setup-{#AppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
ChangesAssociations=yes
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; Flags: unchecked

[Files]
Source: "..\dist\BSTechnikPAPDesigner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\file_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pap"; ValueType: string; ValueName: ""; ValueData: "{#ProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "Programmablaufplan"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\file_icon.ico"""
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} starten"; Flags: nowait postinstall skipifsilent
