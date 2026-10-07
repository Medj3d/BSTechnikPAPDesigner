; Setup für den BS Technik PAP Designer (Inno Setup 6, https://jrsoftware.org/isinfo.php).
;
; Wird von tools\make_release.py übersetzt (release.bat). Von Hand:
;   ISCC /DAppVersion=<Versionsnummer> installer\BSTechnikPAPDesigner.iss
; Ergebnis: dist\BSTechnikPAPDesigner-Setup.exe
;
; Installiert wird ohne Administratorrechte in das Benutzerprofil. Dort darf das
; Programm seinen Ordner selbst beschreiben, sodass die automatischen Updates
; funktionieren. Wer im Setup „für alle Benutzer“ wählt (Administrator),
; installiert nach C:\Programme; neue Versionen spielt dann der Administrator
; mit dem nächsten Setup ein.

#define AppName "BS Technik PAP Designer"
#define AppExe "BSTechnikPAPDesigner.exe"
#define ProgId "BSTechnik.PAPDesigner.Project"
; Version, Quelle und Ziel gibt tools\make_release.py vor
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\BSTechnikPAPDesigner"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{8C5E2B55-4F0B-4B6E-9B5B-3C0B8E6B2D41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Are Schäfer und Linus Twardzik
DefaultDirName={autopf}\BS Technik PAP Designer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=BSTechnikPAPDesigner-Setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
ChangesAssociations=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop erstellen"; GroupDescription: "Verknüpfungen:"
Name: "associate"; Description: ".pap-Dateien mit diesem Programm öffnen"; GroupDescription: "Dateityp:"

[InstallDelete]
; Programmteile einer älteren Version vollständig ersetzen
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_update"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pap"; ValueType: string; ValueName: ""; ValueData: "{#ProgId}"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "Programmablaufplan"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\_internal\assets\file_icon.ico"""; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: associate

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Auch das entfernen, was das Programm bei einem eigenen Update nachgeladen hat
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_update"
Type: filesandordirs; Name: "{app}\_internal.alt"
Type: files; Name: "{app}\{#AppExe}.alt"
; Neuere Programmkopien, die das Programm bei einem Update im Benutzerordner abgelegt hat
Type: filesandordirs; Name: "{localappdata}\BSTechnik\PAPDesigner\update"
