; RemoteDesk — Inno Setup installer script.
; Build: iscc setup.iss  (requires dist\RemoteDesk.exe from PyInstaller first)
; Or push a version tag and let GitHub Actions build it.
; Version is read from the app at build time — update app/version.py, then rebuild.

#define MyAppName "RemoteDesk"
#define MyAppVersion "1.0.10"
#define MyAppPublisher "Shoaib Azeez"
#define MyAppExeName "RemoteDesk.exe"

[Setup]
AppId={{A1B2C3D4-1111-2222-3333-444455556666}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=release
OutputBaseFilename=Setup-RemoteDesk-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
WizardImageFile=assets\installer_banner.bmp
WizardSmallImageFile=assets\installer_small.bmp
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
; v1.0.9 — INSTALLER LICENSE AGREEMENT: the installer now shows the
; RemoteDesk EULA (LICENSE.txt) on the license page before installing.
LicenseFile=LICENSE.txt
; v1.0.9 — IN-PLACE UPGRADE: DefaultDirName ({autopf}\RemoteDesk) and
; PrivilegesRequired=lowest are UNCHANGED since v1.0.5, so every
; version installs to the SAME folder and upgrades replace files in
; place — no uninstall-first dance. (The v1.0.5–v1.0.8 upgrade failures
; were the running app locking RemoteDesk.exe, NOT a changed folder;
; v1.0.9 fixes that by closing the app before the installer runs.)
; v1.0.6 — UPGRADE FIX: the old RemoteDesk.exe was often still RUNNING when
; the user installed the new version, so Windows locked the file and the
; installer failed with "DeleteFile failed; code 5. Access is denied."
; (and the old UI stayed because the new EXE never replaced it).
; CloseApplications asks the Windows Restart Manager to close the running
; RemoteDesk app before files are replaced; RestartApplications restarts
; it afterwards when possible.
CloseApplications=yes
CloseApplicationsFilter=RemoteDesk.exe
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; NOTE: Inno Setup [Tasks] has NO "checked" flag — tasks are checked by
; default unless "unchecked" is given. "checkedonce" = checked on first
; install, then remembers the user's choice. ("checked" here broke the
; v1.0.5 build with: Parameter "Flags" includes an unknown flag.)
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; v1.0.7 — DESKTOP ICON FIX (bulletproof): ship our own icon.ico as a file
; inside {app}, so the desktop + Start Menu shortcuts can point at it
; DIRECTLY (IconFilename below). If the EXE's embedded icon ever fails,
; the desktop icon still shows our logo instead of the generic default.
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Code]
// v1.0.7 — INSTALL WHILE APP IS RUNNING (fully automatic):
// CloseApplications / RestartApplications (above, v1.0.6) use the Windows
// Restart Manager, which can STILL pop up the "unable to close
// applications" dialog on some systems. Belt + suspenders: right before
// the files are replaced, force-close any running RemoteDesk.exe
// silently (no window, no prompt). Errors are ignored — e.g. the app
// simply wasn't running — so the install never fails because of this.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    try
      Exec('taskkill.exe', '/F /IM RemoteDesk.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
  end;
end;

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
