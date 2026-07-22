$service=Get-Service -Name 'PrintGuard' -ErrorAction SilentlyContinue
if(!$service){Write-Host 'PrintGuard service is not installed.' -ForegroundColor Yellow;exit 1}
$service|Select-Object Name,DisplayName,Status,StartType|Format-Table -AutoSize
Get-CimInstance Win32_Service -Filter "Name='PrintGuard'"|Select-Object Name,StartName,State,ProcessId,PathName|Format-List
Get-Process -Name 'PrintGuard.ServiceHost','PrintGuard.Server','PrintGuard.NativeAgent' -ErrorAction SilentlyContinue|Select-Object ProcessName,Id,StartTime|Format-Table -AutoSize
try{Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 3|Out-Null;Write-Host 'API: healthy' -ForegroundColor Green}catch{Write-Host "API: unavailable ($($_.Exception.Message))" -ForegroundColor Red}
$rule=Get-NetFirewallRule -DisplayName 'PrintGuard Dashboard - Domain TCP 8080' -ErrorAction SilentlyContinue
Write-Host "Domain firewall rule: $(if($rule.Enabled-eq'True'){'enabled'}else{'missing or disabled'})"
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue|Where-Object{$_.IPAddress-ne'127.0.0.1'-and$_.AddressState-eq'Preferred'}|ForEach-Object{Write-Host "LAN dashboard: http://$($_.IPAddress):8080"}
