param([Parameter(Mandatory)][string]$Simplex,[Parameter(Mandatory)][string]$Duplex)
$a=[IO.File]::ReadAllBytes((Resolve-Path $Simplex));$b=[IO.File]::ReadAllBytes((Resolve-Path $Duplex))
$count=[Math]::Min($a.Length,$b.Length)
$diff=for($i=0;$i -lt $count;$i++){if($a[$i]-ne$b[$i]){[pscustomobject]@{Offset=('0x{0:X4}'-f$i);Decimal=$i;Simplex=('0x{0:X2}'-f$a[$i]);Duplex=('0x{0:X2}'-f$b[$i])}}}
$diff|Format-Table -AutoSize
"Differences: $(@($diff).Count); lengths: $($a.Length)/$($b.Length)"
