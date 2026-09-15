; Inno Setup script. Run by tools/build_exe.py after PyInstaller:
;   ISCC /DAppVersion=1.2.3 installer\appy.iss   ->   dist\AppySetup.exe
;
; Installs per user (no admin prompt) into %LocalAppData%\Programs\Appy, which
; matches the app's own promise of needing no elevated rights.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B7A1C4E2-5D3F-4A8B-9C1E-2F6D8A0B3C5E}
AppName=Appy
AppVersion={#AppVersion}
AppPublisher=jaym-01
AppPublisherURL=https://github.com/jaym-01/Appy
DefaultDirName={autopf}\Appy
DefaultGroupName=Appy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=AppySetup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Appy.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; An in-app update runs this installer while Appy may still be open.
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Appy.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Appy"; Filename: "{app}\Appy.exe"
Name: "{autodesktop}\Appy"; Filename: "{app}\Appy.exe"; Tasks: desktopicon

[Run]
; No skipifsilent: after a silent in-app update the app comes straight back.
Filename: "{app}\Appy.exe"; Description: "{cm:LaunchProgram,Appy}"; Flags: nowait postinstall
