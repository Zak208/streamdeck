; Script de Instalación para StreamDesk Pro con Inno Setup
#define MyAppName "StreamDesk Pro"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "Zak208"
#define MyAppURL "https://github.com/Zak208/streamdeck"
#define MyAppExeName "start.bat"

[Setup]
AppId={{5E97D453-6523-49A3-97BA-912A8F349580}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=license.txt
OutputDir=..\
OutputBaseFilename=instalador_streamdeck
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\static\icons\icon.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".venv\*,.git\*,*.pyc,__pycache__\*,installer\*,dist\*,instalador_streamdeck.exe"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: shellexec postinstall nowait skipifsilent
