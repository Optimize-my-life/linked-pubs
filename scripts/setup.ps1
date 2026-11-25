# Sets up linked-pubs on this PC. Safe to run again (skips what is done).
# From the repo root:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Other models:        ... -File scripts\setup.ps1 -Models qwen3:14b,gemma3:12b
param([string[]]$Models = @("qwen3:8b", "qwen3:14b"))
$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Missing: $cmd. $hint" -ForegroundColor Red
        exit 1
    }
}

Step "Checking tools"
Need py "Install Python 3.11+: winget install Python.Python.3.11"
Need node "Install Node.js 20+: winget install OpenJS.NodeJS.LTS"
Need ollama "Install Ollama: winget install Ollama.Ollama"
py -3.11 --version
node --version
ollama --version

Step "Python environment (.venv)"
if (-not (Test-Path .venv)) { py -3.11 -m venv .venv }
.venv\Scripts\python -m pip install -q -e ".[dev]"
.venv\Scripts\python -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "Tests failed: stop here and check." -ForegroundColor Red; exit 1 }

Step "Web UI (web/dist)"
Push-Location web
npm ci --no-audit --no-fund
npm run build
Pop-Location

Step "SciFact dataset (data/scifact)"
if (-not (Test-Path data\scifact\corpus.jsonl)) { .venv\Scripts\linked-pubs scifact-download } else { "already there" }

Step "Models"
foreach ($m in $Models) { ollama pull $m }
ollama list

Step "GPU"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
} else {
    Write-Host "nvidia-smi not found: Ollama will run on the CPU (slow)." -ForegroundColor Yellow
}

Step "Done"
Write-Host "Start the UI here:      .venv\Scripts\linked-pubs serve"
Write-Host "From the laptop:        ssh -N -L 8000:127.0.0.1:8000 <host-alias>"
Write-Host "Then open:              http://localhost:8000"
