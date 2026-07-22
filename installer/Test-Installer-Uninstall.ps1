$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$build=Join-Path $repo 'build\setup-exe'
$payload=Join-Path $build 'payload'
$output=Join-Path $build 'test-output'
$iscc="$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if(!(Test-Path $iscc)){throw 'Inno Setup 6 compiler not found.'}
if(!(Test-Path (Join-Path $payload 'bin\PrintGuard.Server.exe'))){throw 'Run Build-Installer.ps1 first.'}
New-Item -ItemType Directory -Force -Path $output|Out-Null
& $iscc "/DSourceRoot=$payload" "/DOutputDir=$output" '/DAppVersion=0.12.1-test' '/DTestMode=1' (Join-Path $PSScriptRoot 'PrintGuard.iss')
if($LASTEXITCODE-ne0){throw 'Test installer compilation failed.'}

$setup=Join-Path $output 'PrintGuard-Setup-Test.exe'
$root=Join-Path $env:LOCALAPPDATA 'PrintGuard-Installer-Test'
$install=Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/LOG=$build\test-install.log") -WindowStyle Hidden -Wait -PassThru
if($install.ExitCode-ne0){throw "Test installation failed: $($install.ExitCode)"}
$required=@('bin\PrintGuard.Server.exe','bin\PrintGuard.NativeAgent.exe','bin\PrintGuard.ServiceHost.exe','docs\INSTALLATION_AND_UNINSTALL_GUIDE.md','unins000.exe')
$missing=$required|Where-Object{!(Test-Path (Join-Path $root $_))}
if($missing){throw "Missing installed files: $($missing -join ', ')"}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'data'),(Join-Path $root 'logs'),(Join-Path $root 'imports')|Out-Null
Set-Content -LiteralPath (Join-Path $root 'data\printguard.db') -Value 'uninstall-test'
Set-Content -LiteralPath (Join-Path $root 'runtime-leftover.tmp') -Value 'uninstall-test'

$uninstall=Start-Process -FilePath (Join-Path $root 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/PURGEDATA',"/LOG=$build\test-uninstall.log") -WindowStyle Hidden -Wait -PassThru
Start-Sleep -Seconds 2
if($uninstall.ExitCode-ne0){throw "Test uninstallation failed: $($uninstall.ExitCode)"}
if(Test-Path $root){throw "Uninstall left files behind: $root"}
Write-Host 'Installer/uninstaller file lifecycle test passed.' -ForegroundColor Green
