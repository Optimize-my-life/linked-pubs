#!/usr/bin/env bash
# Starts the experiment builder in the background (survives SSH logout). Log: data/serve.log.
# Stop: kill "$(cat data/serve.pid)"
set -euo pipefail
PORT="${1:-8000}"
mkdir -p data
if [ -f data/serve.pid ] && kill -0 "$(cat data/serve.pid)" 2>/dev/null; then
  echo "Already running (pid $(cat data/serve.pid)) on port $PORT."; exit 0
fi
nohup .venv/bin/linked-pubs serve --port "$PORT" > data/serve.log 2>&1 &
echo $! > data/serve.pid
sleep 3
curl -fsS "http://127.0.0.1:$PORT/api/health" && echo || echo "Started but not answering yet; see data/serve.log"
