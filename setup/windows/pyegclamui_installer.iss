; ==============================================================================
; pyEGClamUI - Inno Setup Compiler Script
; 100% Free & Open-Source (GPL-3.0) Antivirus Desktop Interface
; ==============================================================================

#ifndef AppVersion
  #define AppVersion "3.1.0"
#endif

#define AppName "pyEGClamUI"
#define AppPublisher "EG1"
#define AppURL "https://eg1.in"
#define AppRepoURL "https://github.com/EG1DOTIN/pyEGClamUI"
#define AppExeName "main.py"

[Setup]
AppId={{8B75F8A2-E40B-4D1C-8A19-9B2F0B9AC4D1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppRepoURL}
AppUpdatesURL={#AppRepoURL}/releases
DefaultDirName={autopf}\pyEGClamUI
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=pyEGClamUI-v{#AppVersion}-Windows-Setup
SetupIconFile=..\..\src\pyegclamui\assets\egav.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UsedUserAreasWarning=no
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
DisableWelcomePage=no
CloseApplications=force
UninstallDisplayIcon={app}\src\pyegclamui\assets\egav.ico
UninstallDisplayName={#AppName} Antivirus Desktop Interface

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "clamdservice"; Description: "Configure and activate ClamD resident memory daemon service on TCP 3310 (Recommended for 15ms scans)"; GroupDescription: "Security & Daemon Configuration:"
Name: "autostart"; Description: "Start pyEGClamUI minimized to system tray on Windows boot"; GroupDescription: "System Startup:"; Flags: unchecked

[Files]
Source: "..\..\build\windows_installer_staging\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\{#AppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\pyegclamui\assets\egav.ico"; Comment: "{#AppName} Antivirus Interface"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\{#AppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\pyegclamui\assets\egav.ico"; Comment: "{#AppName} Antivirus Interface"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "pyEGClamUI"; ValueData: """{app}\python\pythonw.exe"" ""{app}\{#AppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Post-install launch option
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\{#AppExeName}"""; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Cleanly stop and delete the Windows background service (100% silent and hidden)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""Stop-Service -Name clamd -Force -ErrorAction SilentlyContinue; sc.exe delete clamd"""; Flags: runhidden
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'pyEGClamUI' -ErrorAction SilentlyContinue"""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\pyEGClamUI\logs"
Type: filesandordirs; Name: "{app}\build"

[Code]
function IsClamAVInstalled(): Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf}\ClamAV\clamscan.exe')) or
            FileExists(ExpandConstant('{commonpf32}\ClamAV\clamscan.exe')) or
            FileExists('C:\Program Files\ClamAV\clamscan.exe') or
            FileExists('C:\Program Files\ClamAV\clamd.exe');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Params: String;
begin
  if CurStep = ssPostInstall then
  begin
    // 1. Provision ClamAV via winget if not detected on machine
    if not IsClamAVInstalled() then
    begin
      WizardForm.StatusLabel.Caption := 'Checking and provisioning ClamAV antivirus engine via winget...';
      WizardForm.StatusLabel.Update;
      Params := '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\setup\install_clamav.ps1') + '"';
      Exec('powershell.exe', Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    // 2. Configure and start ClamD resident service if selected by user
    if WizardIsTaskSelected('clamdservice') then
    begin
      WizardForm.StatusLabel.Caption := 'Configuring and activating ClamD resident service (initializing signatures)...';
      WizardForm.StatusLabel.Update;
      Params := '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\setup\setup_clamd_service.ps1') + '"';
      Exec('powershell.exe', Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
      if ResultCode <> 0 then
      begin
        Log('Notice: ClamD service configuration returned exit code: ' + IntToStr(ResultCode));
      end;
    end;
  end;
end;
