; Script de Instalación para StreamDesk Pro (Aplicación de Escritorio Nativa)
#define MyAppName "StreamDesk Pro"
#define MyAppVersion "2.14.0"
#define MyAppPublisher "Zak208"
#define MyAppURL "https://github.com/Zak208/streamdeck"
#define MyAppExeName "StreamDesk.exe"
#ifndef DistDir
  #define DistDir "..\dist\StreamDesk"
#endif

[Setup]
AppId={{5E97D453-6523-49A3-97BA-912A8F349580}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=license.txt
OutputDir=..\
OutputBaseFilename=instalador_streamdeck
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\static\icons\icon.ico
WizardImageFile=wizard_large_1x.bmp,wizard_large_2x.bmp
WizardSmallImageFile=wizard_small_1x.bmp,wizard_small_2x.bmp
; Tells Explorer to refresh its icons when the install ends, so the shortcuts and the taskbar show the new one.
ChangesAssociations=yes
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "Zak208.StreamDesk.Pro"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "Zak208.StreamDesk.Pro"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall
