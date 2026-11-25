#!/usr/bin/env bash
# Sets up linked-pubs on this PC (Linux/macOS). Safe to run again (skips what is done).
# From the repo root:  bash scripts/setup.sh [model ...]     default models: qwen3:8b qwen3:14b
set -euo pipefail
MODELS=("${@:-qwen3:8b qwen3:14b}")
# shellcheck disable=SC2206
MODELS=(${MODELS[*]})

step() { printf '\n== %s\n' "$1"; }
need() { command -v "$1" >/dev/null || { echo "Missing: $1. $2" >&2; exit 1; }; }

step "Checking tools"
need python3.11 "Install Python 3.11+ (e.g. apt install python3.11 python3.11-venv)"
need node "Install Node.js 20+"
need ollama "Install Ollama: https://ollama.com/download"
python3.11 --version; node --version; ollama --version

step "Python environment (.venv)"
[ -d .venv ] || python3.11 -m venv .venv
.venv/bin/python -m pip install -q -e ".[dev]"
.venv/bin/python -m pytest -q

step "Web UI (web/dist)"
(cd web && npm ci --no-audit --no-fund && npm run build)

step "SciFact dataset (data/scifact)"
[ -f data/scifact/corpus.jsonl ] && echo "already there" || .venv/bin/linked-pubs scifact-download

step "Models"
for m in "${MODELS[@]}"; do ollama pull "$m"; done
ollama list

step "GPU"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
else
  echo "nvidia-smi not found: Ollama will run on the CPU (slow)."
fi

step "Done"
echo "Start the UI here:      .venv/bin/linked-pubs serve"
echo "From the laptop:        ssh -N -L 8000:127.0.0.1:8000 <host-alias>"
echo "Then open:              http://localhost:8000"
