#Requires -RunAsAdministrator
param([string]$InstallRoot="$env:ProgramData\PrintGuard")
$ErrorActionPreference='Stop'
$serviceName='PrintGuard'
$firewallRuleName='PrintGuard Dashboard - Domain TCP 8080'
$displayName='PrintGuard '+(-join [char[]](0x5217,0x5370,0x6CBB,0x7406,0x670D,0x52D9))
$packageRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
$expected=[IO.Path]::GetFullPath((Join-Path $env:ProgramData 'PrintGuard'))
$InstallRoot=[IO.Path]::GetFullPath($InstallRoot)
if($InstallRoot-ne$expected){throw "This package only installs to $expected"}
$required=@('PrintGuard.ServiceHost.exe','PrintGuard.Server.exe','PrintGuard.NativeAgent.exe')|ForEach-Object{Join-Path $packageRoot "bin\$_"}
foreach($file in $required){if(!(Test-Path -LiteralPath $file)){throw "Package file missing: $file"}}
if((Get-Service Spooler).Status-ne'Running'){Start-Service Spooler}

# Remove the previous Task Scheduler deployment without touching data.
foreach($name in @('PrintGuard Agent','PrintGuard Server','PrintGuard Log Cleanup','PrintGuard Test Agent','PrintGuard Test Server')){
    $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if($task){Stop-ScheduledTask -InputObject $task -ErrorAction SilentlyContinue;Unregister-ScheduledTask -InputObject $task -Confirm:$false}
}

$existing=Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if($existing){
    if($existing.Status-ne'Stopped'){
        try{Stop-Service -Name $serviceName -Force -ErrorAction Stop}catch{Write-Warning "Graceful service stop failed: $($_.Exception.Message)"}
        try{$existing.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))}catch{}
        $existing.Refresh()
        if($existing.Status-ne'Stopped'){
            $serviceInfo=Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
            Write-Warning "Service did not stop in 30 seconds; terminating PrintGuard PID $($serviceInfo.ProcessId)."
            if($serviceInfo.ProcessId){Stop-Process -Id $serviceInfo.ProcessId -Force -ErrorAction SilentlyContinue}
            Get-Process -Name 'PrintGuard.Server','PrintGuard.NativeAgent' -ErrorAction SilentlyContinue|Stop-Process -Force -ErrorAction SilentlyContinue
            for($i=0;$i-lt20;$i++){Start-Sleep -Milliseconds 500;$existing.Refresh();if($existing.Status-eq'Stopped'){break}}
            if($existing.Status-ne'Stopped'){throw 'Unable to stop the existing PrintGuard service even after terminating its process. Reboot the server once, then run this installer again.'}
        }
    }
    $deleteOutput=& sc.exe delete $serviceName 2>&1
    if($LASTEXITCODE-ne0){throw "Existing service deletion failed: $($deleteOutput -join ' ')"}
    $existing.Dispose();$existing=$null
    for($i=0;$i-lt60-and(Get-Service -Name $serviceName -ErrorAction SilentlyContinue);$i++){Start-Sleep -Milliseconds 500}
    if(Get-Service -Name $serviceName -ErrorAction SilentlyContinue){throw 'The old PrintGuard service is still marked for deletion. Close services.msc and retry; reboot once if Windows keeps the service handle open.'}
}

# A service may report Stopped before its supervised child processes have exited.
# End only PrintGuard executables so the installed binaries can be replaced safely.
Get-Process -Name 'PrintGuard.ServiceHost','PrintGuard.Server','PrintGuard.NativeAgent' -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
for($i=0;$i-lt30;$i++){
    $left=Get-Process -Name 'PrintGuard.ServiceHost','PrintGuard.Server','PrintGuard.NativeAgent' -ErrorAction SilentlyContinue
    if(!$left){break}
    Start-Sleep -Seconds 1
}
if(Get-Process -Name 'PrintGuard.ServiceHost','PrintGuard.Server','PrintGuard.NativeAgent' -ErrorAction SilentlyContinue){
    throw 'A PrintGuard process is still using the installed files. Reboot the server once, then run this installer again.'
}

$bin=Join-Path $InstallRoot 'bin';$scripts=Join-Path $InstallRoot 'scripts';$data=Join-Path $InstallRoot 'data';$logs=Join-Path $InstallRoot 'logs';$imports=Join-Path $InstallRoot 'imports'
New-Item -ItemType Directory -Force -Path $bin,$scripts,$data,$logs,$imports|Out-Null
foreach($file in $required){
    $copied=$false
    for($i=0;$i-lt30;$i++){
        try{Copy-Item -LiteralPath $file -Destination $bin -Force;$copied=$true;break}
        catch [IO.IOException]{Start-Sleep -Seconds 1}
    }
    if(!$copied){throw "Unable to replace $(Split-Path -Leaf $file) because it is still locked. Reboot the server once, then run this installer again."}
}
Copy-Item -LiteralPath (Join-Path $packageRoot 'Status-PrintGuard-Service.ps1'),(Join-Path $packageRoot 'Uninstall-PrintGuard-Service.ps1') -Destination $scripts -Force
$hostExe=Join-Path $bin 'PrintGuard.ServiceHost.exe'
& $hostExe "--root=$InstallRoot" --check
if($LASTEXITCODE-ne0){throw 'Service Host self-check failed.'}

# Expose the dashboard only while the Print Server network is using the
# Windows Domain firewall profile. Private/Public profiles remain closed.
Get-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue|Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $firewallRuleName -Description 'PrintGuard dashboard for the internal Windows domain network.' `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Domain -Program (Join-Path $bin 'PrintGuard.Server.exe')|Out-Null

$serviceCommand='"{0}" --root="{1}"'-f $hostExe,$InstallRoot
try{
    New-Service -Name $serviceName -BinaryPathName $serviceCommand -DisplayName $displayName -Description 'PrintGuard dashboard, printer monitoring, policy enforcement, reports, and device CSV import.' -StartupType Automatic -DependsOn Spooler|Out-Null
}catch{throw "Windows service creation failed: $($_.Exception.Message)"}
$configOutput=& sc.exe config $serviceName 'start=' 'delayed-auto' 2>&1
if($LASTEXITCODE-ne0){Write-Warning "Delayed-auto was not accepted; keeping Automatic startup. SC output: $($configOutput -join ' ')"}
$failureOutput=& sc.exe failure $serviceName 'reset=' '86400' 'actions=' 'restart/5000/restart/15000/restart/60000' 2>&1
if($LASTEXITCODE-ne0){Write-Warning "Service recovery configuration failed: $($failureOutput -join ' ')"}
$flagOutput=& sc.exe failureflag $serviceName 1 2>&1
if($LASTEXITCODE-ne0){Write-Warning "Failure-action flag configuration failed: $($flagOutput -join ' ')"}
Start-Service $serviceName
$service=Get-Service $serviceName;$service.WaitForStatus('Running',[TimeSpan]::FromSeconds(30))
$ready=$false
for($i=0;$i-lt30;$i++){Start-Sleep -Seconds 1;try{Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 2|Out-Null;$ready=$true;break}catch{}}
if(!$ready){throw "Service is running but API did not become ready. Check $logs\service"}
Write-Host 'PrintGuard Windows Service installed and running.' -ForegroundColor Green
$installed=Get-CimInstance Win32_Service -Filter "Name='PrintGuard'"
Write-Host "Service: PrintGuard ($($installed.StartMode), LocalSystem)"
Write-Host 'Dashboard: http://127.0.0.1:8080'
$lanAddresses=Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue|Where-Object{$_.IPAddress-ne'127.0.0.1'-and$_.AddressState-eq'Preferred'}|Select-Object -ExpandProperty IPAddress -Unique
foreach($address in $lanAddresses){Write-Host "Domain LAN: http://$address`:8080"}
Write-Host 'Firewall: Domain profile TCP 8080 allowed; Private/Public remain blocked.'
Write-Host "Data preserved at: $data"
Write-Host "Automatic CSV import folder: $imports"
