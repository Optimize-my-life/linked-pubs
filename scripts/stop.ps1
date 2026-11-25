# Stops the experiment builder started by scripts\start.ps1. A running experiment is marked
# "interrupted" on the next start; its finished arms are kept.
$pidFile = "data\serve.pid"
if (-not (Test-Path $pidFile)) { Write-Host "Not running (no data\serve.pid)."; exit 0 }
$p = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
if ($p) { Stop-Process -Id $p.Id -Confirm:$false; Write-Host "Stopped (pid $($p.Id))." } else { Write-Host "Not running." }
Remove-Item $pidFile -Confirm:$false
