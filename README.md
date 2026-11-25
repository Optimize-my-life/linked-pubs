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

Claude models need credentials in the environment (`ANTHROPIC_API_KEY`). Local models run
through any OpenAI-compatible endpoint (Ollama by default at `http://localhost:11434/v1`;
override with `LINKED_PUBS_OPENAI_BASE_URL`).

## Use

```powershell
# Download SciFact (data/scifact, not committed)
.venv\Scripts\linked-pubs scifact-download

# Verify claims against raw abstracts and against extracted statements (costs API calls)
.venv\Scripts\linked-pubs scifact-eval --limit 20 --mode both --llm anthropic:claude-opus-5-5

# Same with a local model for extraction
.venv\Scripts\linked-pubs scifact-eval --limit 20 --extract-llm openai_compat:qwen3:8b

# Extract statements from a text file
.venv\Scripts\linked-pubs extract notes.txt --llm anthropic:claude-opus-5-5
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
