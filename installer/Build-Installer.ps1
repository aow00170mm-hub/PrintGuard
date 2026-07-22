param(
    [string]$Version='0.12.1',
    [string]$OutputDirectory=''
)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$build=Join-Path $repo 'build\setup-exe'
$payload=Join-Path $build 'payload'
if(!$OutputDirectory){$OutputDirectory=Join-Path $build 'output'}
$iscc=@(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)|Where-Object{Test-Path $_}|Select-Object -First 1
if(!$iscc){throw 'Inno Setup 6 compiler not found. Install package JRSoftware.InnoSetup first.'}
New-Item -ItemType Directory -Force -Path (Join-Path $payload 'bin'),(Join-Path $payload 'docs'),$OutputDirectory|Out-Null

python -m PyInstaller --noconfirm --clean --onefile --name PrintGuard.Server `
    --add-data "$repo\web;web" --distpath (Join-Path $build 'server') `
    --workpath (Join-Path $build 'server-work') --specpath (Join-Path $build 'spec') `
    (Join-Path $repo 'server.py')
if($LASTEXITCODE-ne0){throw 'PrintGuard.Server build failed.'}

dotnet publish (Join-Path $repo 'native-agent\PrintGuard.NativeAgent.csproj') -c Release -r win-x64 `
    --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
    -o (Join-Path $build 'agent')
if($LASTEXITCODE-ne0){throw 'PrintGuard.NativeAgent build failed.'}
dotnet publish (Join-Path $repo 'service-host\PrintGuard.ServiceHost.csproj') -c Release -r win-x64 `
    --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
    -o (Join-Path $build 'host')
if($LASTEXITCODE-ne0){throw 'PrintGuard.ServiceHost build failed.'}

Copy-Item (Join-Path $build 'server\PrintGuard.Server.exe') (Join-Path $payload 'bin') -Force
Copy-Item (Join-Path $build 'agent\PrintGuard.NativeAgent.exe') (Join-Path $payload 'bin') -Force
Copy-Item (Join-Path $build 'host\PrintGuard.ServiceHost.exe') (Join-Path $payload 'bin') -Force
Copy-Item (Join-Path $repo 'INSTALLATION_AND_UNINSTALL_GUIDE.md'),(Join-Path $repo 'SYSTEM_ARCHITECTURE_AND_CODE_GUIDE.md'),(Join-Path $repo 'SERVICE_DEPLOYMENT.md') (Join-Path $payload 'docs') -Force

& $iscc "/DSourceRoot=$payload" "/DOutputDir=$OutputDirectory" "/DAppVersion=$Version" (Join-Path $PSScriptRoot 'PrintGuard.iss')
if($LASTEXITCODE-ne0){throw 'Inno Setup compilation failed.'}
$setup=Join-Path $OutputDirectory 'PrintGuard-Setup.exe'
Write-Host "Created: $setup" -ForegroundColor Green
Get-FileHash $setup -Algorithm SHA256
