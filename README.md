# linked-pubs

Research tool (PhD project): extract factual statements from scientific sources and
guidelines on human nutrition, link them across sources, check claims against them, and
turn them into inputs for optimisation models. Background, hypotheses and the evaluation
plan are in [docs/knowledge/](docs/knowledge/INDEX.md).

Status: milestone 1. Pluggable LLM providers, statement extraction with a quote check,
claim verification, and the SciFact evaluation harness. No database or web UI yet.

## Setup

Needs Python 3.11+.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

By default everything runs for free on a local model through any OpenAI-compatible endpoint
(Ollama by default at `http://localhost:11434/v1`; override with `LINKED_PUBS_OPENAI_BASE_URL`):

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
