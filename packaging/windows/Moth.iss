; Build after PyInstaller: ISCC /DAppVersion=0.2.0 packaging\windows\Moth.iss
#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef RepoRoot
  #define RepoRoot "..\.."
#endif

[Setup]
AppId={{FE27827B-13AC-46F2-87E4-257B831017AB}
AppName=Moth
AppVersion={#AppVersion}
AppPublisher=MothKernel
AppPublisherURL=https://github.com/MothKernel/Moth
AppSupportURL=https://github.com/MothKernel/Moth/issues
DefaultDirName={localappdata}\Programs\Moth
DefaultGroupName=Moth
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#RepoRoot}\release
OutputBaseFilename=Moth-{#AppVersion}-Windows-x64-Setup
SetupIconFile={#RepoRoot}\moth\resources\moth.ico
UninstallDisplayIcon={app}\Moth.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\Moth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Moth"; Filename: "{app}\Moth.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Moth"; Filename: "{app}\Moth.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Moth.exe"; Description: "Open Moth"; Flags: nowait postinstall skipifsilent

; Assessment data is outside {app}; uninstall never removes history or managed tools.
