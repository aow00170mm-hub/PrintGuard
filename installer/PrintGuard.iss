#ifndef SourceRoot
  #error SourceRoot must point to the staged installer payload.
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef AppVersion
  #define AppVersion "0.12.1"
#endif

[Setup]
#ifdef TestMode
AppId={{AF06C113-2BB1-4A55-A28C-6B3EBA9659DE}
#else
AppId={{4CBA408B-41D8-48B8-86B8-A16E4D786750}
#endif
AppName=PrintGuard
AppVersion={#AppVersion}
AppPublisher=PrintGuard
AppPublisherURL=https://github.com/aow00170mm-hub/PrintGuard
AppSupportURL=https://github.com/aow00170mm-hub/PrintGuard/issues
#ifdef TestMode
DefaultDirName={localappdata}\PrintGuard-Installer-Test
PrivilegesRequired=lowest
OutputBaseFilename=PrintGuard-Setup-Test
#else
DefaultDirName={commonappdata}\PrintGuard
PrivilegesRequired=admin
OutputBaseFilename=PrintGuard-Setup
#endif
DisableDirPage=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName=PrintGuard 列印治理服務
UninstallDisplayIcon={app}\bin\PrintGuard.ServiceHost.exe
CloseApplications=no
RestartApplications=no

[Files]
Source: "{#SourceRoot}\bin\PrintGuard.Server.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#SourceRoot}\bin\PrintGuard.NativeAgent.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#SourceRoot}\bin\PrintGuard.ServiceHost.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#SourceRoot}\docs\INSTALLATION_AND_UNINSTALL_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#SourceRoot}\docs\SYSTEM_ARCHITECTURE_AND_CODE_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#SourceRoot}\docs\SERVICE_DEPLOYMENT.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"
Name: "{app}\logs"
Name: "{app}\imports"

[Icons]
#ifndef TestMode
Name: "{commonprograms}\PrintGuard\開啟管理介面"; Filename: "http://127.0.0.1:8080"
Name: "{commonprograms}\PrintGuard\安裝與移除說明"; Filename: "notepad.exe"; Parameters: """{app}\docs\INSTALLATION_AND_UNINSTALL_GUIDE.md"""
Name: "{commonprograms}\PrintGuard\解除安裝 PrintGuard"; Filename: "{uninstallexe}"
#endif

[Run]
#ifndef TestMode
Filename: "http://127.0.0.1:8080"; Description: "開啟 PrintGuard 管理介面"; Flags: postinstall shellexec skipifsilent nowait
#endif

[Code]
const
  ServiceName = 'PrintGuard';
  FirewallRule = 'PrintGuard Dashboard - Domain TCP 8080';

function RunHidden(const FileName, Params: String; var ResultCode: Integer): Boolean;
begin
  Log('Execute: ' + FileName + ' ' + Params);
  Result := Exec(FileName, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Result then Log('Exit code: ' + IntToStr(ResultCode)) else Log('Execution failed.');
end;

procedure StopAndDeleteService;
var
  ResultCode, I: Integer;
begin
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'stop ' + ServiceName, ResultCode);
  for I := 1 to 20 do begin
    Sleep(500);
    if not FileExists(ExpandConstant('{app}\bin\PrintGuard.ServiceHost.exe')) then Break;
  end;
  RunHidden(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM PrintGuard.ServiceHost.exe', ResultCode);
  RunHidden(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM PrintGuard.Server.exe', ResultCode);
  RunHidden(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM PrintGuard.NativeAgent.exe', ResultCode);
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'delete ' + ServiceName, ResultCode);
  Sleep(1200);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
#ifndef TestMode
  StopAndDeleteService;
#endif
  Result := '';
end;

procedure InstallService;
var
  ResultCode: Integer;
  HostExe, ServerExe, BinPath, Params: String;
begin
  HostExe := ExpandConstant('{app}\bin\PrintGuard.ServiceHost.exe');
  ServerExe := ExpandConstant('{app}\bin\PrintGuard.Server.exe');
  BinPath := AddQuotes(HostExe) + ' --root=' + AddQuotes(ExpandConstant('{app}'));
  Params := 'create ' + ServiceName + ' binPath= ' + AddQuotes(BinPath) +
    ' start= delayed-auto depend= Spooler DisplayName= ' + AddQuotes('PrintGuard 列印治理服務');
  if (not RunHidden(ExpandConstant('{sys}\sc.exe'), Params, ResultCode)) or (ResultCode <> 0) then
    RaiseException('無法建立 PrintGuard Windows Service，錯誤碼：' + IntToStr(ResultCode));
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'description ' + ServiceName + ' ' + AddQuotes('PrintGuard 列印監控、政策、報表與管理員認證服務'), ResultCode);
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'failure ' + ServiceName + ' reset= 86400 actions= restart/5000/restart/15000/restart/60000', ResultCode);
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'failureflag ' + ServiceName + ' 1', ResultCode);
  RunHidden(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name=' + AddQuotes(FirewallRule), ResultCode);
  Params := 'advfirewall firewall add rule name=' + AddQuotes(FirewallRule) +
    ' dir=in action=allow protocol=TCP localport=8080 profile=domain program=' + AddQuotes(ServerExe) + ' enable=yes';
  if (not RunHidden(ExpandConstant('{sys}\netsh.exe'), Params, ResultCode)) or (ResultCode <> 0) then
    RaiseException('無法建立 PrintGuard 防火牆規則，錯誤碼：' + IntToStr(ResultCode));
  if (not RunHidden(ExpandConstant('{sys}\sc.exe'), 'start ' + ServiceName, ResultCode)) or (ResultCode <> 0) then
    RaiseException('PrintGuard Service 無法啟動，錯誤碼：' + IntToStr(ResultCode));
  Sleep(3000);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
#ifndef TestMode
  if CurStep = ssPostInstall then InstallService;
#endif
end;

function InitializeUninstall(): Boolean;
begin
  if Pos('/PURGEDATA', Uppercase(GetCmdTail)) > 0 then begin
    Result := True;
    exit;
  end;
  Result := MsgBox(
    '解除安裝將停止 PrintGuard，並永久刪除所有程式、資料庫、列印紀錄、Log 與匯入檔案。' + #13#10 + #13#10 +
    '資料位置：' + ExpandConstant('{app}') + #13#10 + #13#10 +
    '若需要保留資料，請先取消並完成備份。確定要完整移除嗎？',
    mbConfirmation, MB_YESNO) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then begin
#ifndef TestMode
    StopAndDeleteService;
    RunHidden(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name=' + AddQuotes(FirewallRule), ResultCode);
#endif
  end;
  if CurUninstallStep = usPostUninstall then begin
    { Remove the complete product root, including databases, logs, imports,
      diagnostics, and any runtime files not listed in the installer manifest. }
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
