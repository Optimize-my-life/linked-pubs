# Starts the experiment builder in the background, so it keeps running after an SSH
# session closes. Log: data\serve.log. Stop with scripts\stop.ps1.
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
$pidFile = "data\serve.pid"
New-Item -ItemType Directory -Force data | Out-Null

if (Test-Path $pidFile) {
    $old = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($old) { Write-Host "Already running (pid $($old.Id)) on port $Port."; exit 0 }
}
$p = Start-Process -FilePath ".venv\Scripts\linked-pubs.exe" -ArgumentList "serve", "--port", $Port `
    -RedirectStandardOutput "data\serve.log" -RedirectStandardError "data\serve.err.log" `
    -WindowStyle Hidden -PassThru
$p.Id | Set-Content $pidFile
Start-Sleep -Seconds 3
try {
    $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 10
    Write-Host "Running (pid $($p.Id)): http://127.0.0.1:$Port  Ollama: $($h.ollama_version)"
} catch {
    Write-Host "Started (pid $($p.Id)) but not answering yet; see data\serve.err.log" -ForegroundColor Yellow
}
