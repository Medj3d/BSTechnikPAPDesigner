; Setup für den BS Technik PAP Designer (Inno Setup 6, https://jrsoftware.org/isinfo.php).
;
; Wird von tools\make_release.py übersetzt (release.bat). Von Hand:
;   ISCC /DAppVersion=<Versionsnummer> installer\BSTechnikPAPDesigner.iss
; Ergebnis: dist\BSTechnikPAPDesigner-Setup.exe
;
; Installiert wird ohne Administratorrechte in das Benutzerprofil. Dort darf das
; Programm seinen Ordner selbst beschreiben, sodass die automatischen Updates
; funktionieren. Wer im Setup „für alle Benutzer“ wählt (Administrator),
; installiert nach C:\Programme; das Programm legt neuere Versionen dann im
; Benutzerprofil ab und startet sie von dort.
;
; Sprachen: Das Setup zeigt sich in der Sprache von Windows (Deutsch, Englisch, Französisch, Spanisch,
; Portugiesisch, Russisch, Japanisch, Arabisch). Für Chinesisch bringt Inno Setup keine offizielle
; Übersetzung mit: dort erscheint das Setup auf Englisch. Das installierte Programm selbst kennt alle
; neun Sprachen. Die Texte der eigenen Aufgaben stehen unten unter [CustomMessages].

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
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.AssociatePap=Open .pap files with this program
german.AssociatePap=.pap-Dateien mit diesem Programm öffnen
french.AssociatePap=Ouvrir les fichiers .pap avec ce programme
spanish.AssociatePap=Abrir los archivos .pap con este programa
brazilianportuguese.AssociatePap=Abrir arquivos .pap com este programa
russian.AssociatePap=Открывать файлы .pap в этой программе
japanese.AssociatePap=.pap ファイルをこのプログラムで開く
arabic.AssociatePap=فتح ملفات PAP بهذا البرنامج
english.TaskGroupFileType=File type:
german.TaskGroupFileType=Dateityp:
french.TaskGroupFileType=Type de fichier :
spanish.TaskGroupFileType=Tipo de archivo:
brazilianportuguese.TaskGroupFileType=Tipo de arquivo:
russian.TaskGroupFileType=Тип файлов:
japanese.TaskGroupFileType=ファイルの種類:
arabic.TaskGroupFileType=نوع الملف:
english.FileTypeName=Flowchart
german.FileTypeName=Programmablaufplan
french.FileTypeName=Organigramme
spanish.FileTypeName=Diagrama de flujo
brazilianportuguese.FileTypeName=Fluxograma
russian.FileTypeName=Блок-схема
japanese.FileTypeName=フローチャート
arabic.FileTypeName=مخطط انسيابي

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associate"; Description: "{cm:AssociatePap}"; GroupDescription: "{cm:TaskGroupFileType}"

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
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "{cm:FileTypeName}"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\_internal\assets\file_icon.ico"""; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: associate

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Auch das entfernen, was das Programm bei einem eigenen Update nachgeladen hat
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_update"
Type: filesandordirs; Name: "{app}\_internal.alt"
Type: files; Name: "{app}\{#AppExe}.alt"
; Neuere Programmkopien, die das Programm bei einem Update im Benutzerordner abgelegt hat
Type: filesandordirs; Name: "{localappdata}\BSTechnik\PAPDesigner\update"
