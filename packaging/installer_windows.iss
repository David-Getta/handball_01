; Sport Machine — Windows telepítő (Inno Setup).
; EGY dupla kattintással telepíthető .exe-t készít, ami a Flutter-appot ÉS a
; beépített motort (backend) is telepíti, parancssor nélkül.
;
; Előfeltételek a BUILDER gépén:
;   1) Flutter desktop build:   flutter build windows --release   (a client/ mappában)
;   2) Motor becsomagolva:      packaging\build_backend.ps1
;   3) Inno Setup telepítve:    https://jrsoftware.org/isdl.php
; Fordítás:  iscc packaging\installer_windows.iss
;
; A motor a telepített app melletti "engine\" mappába kerül — pontosan oda, ahol a
; backend_launcher.dart keresi.

#define AppName "Sport Machine"
#define AppExe "handball_client.exe"
; A build kimenetek a repo gyökeréhez képest:
#define FlutterRelease "..\client\build\windows\x64\runner\Release"
#define EngineDir "..\dist\handball_backend"

[Setup]
AppName={#AppName}
AppVersion=0.1.0
DefaultDirName={autopf}\SportMachine
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=SportMachine-Setup
Compression=lzma2
SolidCompression=yes
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64
; Nem kell rendszergazda, ha felhasználói mappába telepít:
PrivilegesRequiredOverridesAllowed=dialog commandline

[Languages]
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Files]
; A Flutter-app teljes kimenete.
Source: "{#FlutterRelease}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
; A motor (backend) — az "engine\" almappába, ahol az app keresi.
Source: "{#EngineDir}\*"; DestDir: "{app}\engine"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Parancsikon az asztalra"; GroupDescription: "További:"

[Run]
; Telepítés után rögtön indíthatja.
Filename: "{app}\{#AppExe}"; Description: "{#AppName} indítása"; Flags: nowait postinstall skipifsilent
