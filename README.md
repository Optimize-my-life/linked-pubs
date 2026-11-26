# linked-pubs

Research tool (PhD project): extract factual statements from scientific sources and
guidelines on human nutrition, link them across sources, check claims against them, and
turn them into inputs for optimisation models. Background, hypotheses and the evaluation
plan are in [docs/knowledge/](docs/knowledge/INDEX.md).

Status: milestone 1. Pluggable LLM providers, statement extraction with a quote check,
claim verification, the SciFact evaluation harness, and a visual experiment builder (web UI).
No database yet.

## Setup

One step on a new PC (Windows; `scripts/setup.sh` on Linux): checks tools, creates the venv,
runs the tests, builds the UI, downloads SciFact and pulls models.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

By hand: needs Python 3.11+.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

By default everything runs for free on a local model through any OpenAI-compatible endpoint
(Ollama by default at `http://127.0.0.1:11434/v1`; override with `LINKED_PUBS_OPENAI_BASE_URL`):

```powershell
winget install Ollama.Ollama
ollama pull qwen3:8b
```

Paid Claude models are off unless you pass `--allow-paid` (and set `ANTHROPIC_API_KEY`).

## Use

```powershell
# Download SciFact (data/scifact, not committed)
.venv\Scripts\linked-pubs scifact-download

# Verify claims against raw abstracts and against extracted statements (local model, free)
.venv\Scripts\linked-pubs scifact-eval --limit 20 --mode both

# Another local model
.venv\Scripts\linked-pubs scifact-eval --limit 20 --llm ollama:gemma3:12b

# Claude (paid, only with --allow-paid)
.venv\Scripts\linked-pubs scifact-eval --limit 20 --llm anthropic:claude-opus-5-5 --allow-paid

# Extract statements from a text file
.venv\Scripts\linked-pubs extract notes.txt
```

Model specs: `anthropic:<model>` or `openai_compat:<model>`. `--effort` sets the effort
level for Claude models (default `high`). Each run writes `summary.json` and per-pair
predictions to `data/runs/<timestamp>-scifact-<split>/`. Extracted statements are cached per
extractor configuration in `data/cache/statements/`, so reruns don't pay for extraction again.

## Experiment builder (web UI)

Drag blocks onto a canvas and connect them: SciFact dataset or dropped PDFs → extractor →
verifier → metrics. Each path to a metrics block is one arm. A block can hold several models
and prompts: every combination becomes an arm, and the abstract baselines needed for the
extraction loss are added automatically. Runs queue up (one at a time), show progress, and
keep their results.

- **Models tab:** tick models and choose what they do (extract, judge, or both end to end):
  the canvas is built for you. Also downloads free models through Ollama.
- **Prompts tab:** read every prompt, copy one, edit it, save it as a new version (with the
  changes highlighted), and add it to the blocks to compare it with the others.

```powershell
cd web; npm ci; npm run build; cd ..     # once, and after UI changes
.venv\Scripts\linked-pubs serve           # http://127.0.0.1:8000
```

On the GPU PC, `scripts\start.ps1` (or `scripts/start.sh`) runs it in the background so it
survives the SSH session; `scripts\stop.ps1` stops it. Only one server per data folder can run.

The server has no login and binds to 127.0.0.1. Open it from the laptop through an SSH tunnel:

```powershell
ssh -N -L 8000:127.0.0.1:8000 <host-alias>  # then open http://localhost:8000
```

What the UI shows: in the Plan tab, what each arm does, how many model calls it needs and
how long it will take (measured from earlier runs on that machine). While running: the
current step and time left in the header, and the working block pulses on the canvas.
Results: plain verdicts, scores on the blocks, "Why?" (pairs that extraction lost, with the
claim, gold evidence and the statements the verifier saw) and a Compare tab across runs.

UI development: `linked-pubs serve` plus `npm run dev` in `web/` (http://localhost:5173,
proxies `/api`). UI tests: `npm test`; screenshots: `node scripts/screenshot.mjs` and `node scripts/screenshot-tabs.mjs` (needs
`npx playwright install chromium` once). Paid APIs only with `LINKED_PUBS_ALLOW_PAID=1`. Ollama elsewhere: set
`OLLAMA_HOST`.

## Layout

| Path | What |
|---|---|
| `src/linked_pubs/models.py` | Typed statements, documents, verdicts, run provenance |
| `src/linked_pubs/grounding.py` | Checks that an evidence quote really occurs in the source |
| `src/linked_pubs/llm/` | LLM providers: Claude (Anthropic SDK), OpenAI-compatible local models |
| `src/linked_pubs/extract/` | Extractor interface and LLM extractor |
| `src/linked_pubs/resolve/` | Verifier interface and LLM verifier |
| `src/linked_pubs/data/scifact.py` | SciFact download and loaders |
| `src/linked_pubs/eval/` | Metrics and the SciFact evaluation |
| `src/linked_pubs/server/` | Web API: graph → arms, experiment runner, PDF uploads |
| `web/` | Experiment builder UI (React, React Flow) |
