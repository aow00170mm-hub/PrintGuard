#Requires -RunAsAdministrator
param([string]$InstallRoot="$env:ProgramData\PrintGuard",[switch]$RemoveData)
$ErrorActionPreference='Stop'
$firewallRuleName='PrintGuard Dashboard - Domain TCP 8080'
$service=Get-Service -Name 'PrintGuard' -ErrorAction SilentlyContinue
if($service){
    if($service.Status-ne'Stopped'){Stop-Service -Name 'PrintGuard' -Force;$service.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))}
    & sc.exe delete PrintGuard|Out-Null
    Write-Host 'PrintGuard Windows service removed.' -ForegroundColor Green
}else{Write-Host 'PrintGuard Windows service was already absent.'}
foreach($name in @('PrintGuard Agent','PrintGuard Server','PrintGuard Log Cleanup','PrintGuard Test Agent','PrintGuard Test Server')){
    $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if($task){Stop-ScheduledTask -InputObject $task -ErrorAction SilentlyContinue;Unregister-ScheduledTask -InputObject $task -Confirm:$false}
}
Get-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue|Remove-NetFirewallRule
Write-Host 'PrintGuard Domain firewall rule removed.'
if($RemoveData){
    $expected=[IO.Path]::GetFullPath((Join-Path $env:ProgramData 'PrintGuard'));$actual=[IO.Path]::GetFullPath($InstallRoot)
    if($actual-ne$expected){throw 'Refusing to remove an unexpected path.'}
    [IO.Directory]::Delete($actual,$true);Write-Host "Program and data removed: $actual" -ForegroundColor Yellow
}else{Write-Host "Database, logs and imports were preserved at: $InstallRoot"}
