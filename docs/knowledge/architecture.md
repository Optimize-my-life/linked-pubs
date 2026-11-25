# Architecture

```
PDFs ──► Ingest ──► Chunks ──► Extractor(s) ──► Statements ──► Linker(s) ──► Fact graph
                                                    │                          │
                                     new statement ─┴──► Verifier(s) ◄─────────┘
                                                          └─► verdict + citations
```

## Pipeline
1. **Ingest**: deduplicate by file hash, parse PDF (parser plugin) into sections and
   paragraphs with page numbers and character offsets; store metadata (title, DOI, type:
   paper / guideline).
2. **Extract** (`Extractor` plugin): chunk → list of statements. Each statement has
   the claim text, optional structure (subject, relation, object, qualifiers such as
   population, conditions, units), evidence quote, page, confidence.
   Guard: the evidence quote must be found in the source text, otherwise reject (catches
   hallucinated facts).
3. **Embed**: embedding per statement (embedder plugin) into pgvector.
4. **Link** (`Resolver` plugin, corpus mode): for each statement, retrieve candidates
   (vector + keyword search), then classify pairs: equivalent / entails / contradicts /
   related / unrelated. Equivalent statements form clusters ("facts"); other labels are
   edges.
5. **Verify** (`Resolver` plugin, query mode): the same retrieve + classify for a user
   statement, then aggregate into supported / contradicted / not enough info, with the
   evidence statements and their source quotes.

## Statement types (nutrition)
Statements feed optimisation models, so they are typed:
| Type | Example | Use in model |
|---|---|---|
| reference value | PRI iron 16 mg/day, women 19–50 | lower bound (value, unit, population, AR/PRI/AI/UL) |
| upper limit | UL vitamin D 100 µg/day, adults | upper bound |
| effect | +10 g fibre/day → −x % CVD risk | objective coefficient / soft constraint (+ study design, evidence grade) |
| recommendation | free sugars < 10 % of energy | (soft) constraint |
| food composition | 100 g lentils: 7.5 mg iron | model matrix (prefer databases over PDFs) |

## Plugin interfaces (sketch)
- `Parser.parse(pdf) -> Document`
- `Extractor.extract(chunk, context) -> list[Statement]`
- `Embedder.embed(texts) -> vectors`
- `Resolver.classify(pairs) -> list[Relation]`, with implementations such as
  embedding threshold, NLI cross-encoder, LLM judge (any LLM provider).
- `LLMProvider.complete(prompt, schema)`: Claude API, OpenAI-compatible local endpoint.

Every run stores plugin name, version, model, prompt hash and config (`runs` table), and
every statement/relation points to its run.

## Data model (core tables)
`sources`, `chunks`, `runs`, `statements`, `facts` (clusters), `relations`
(statement–statement edges with label and score), `verifications`, `annotations`
(human labels for evaluation).

## Web UI
Sources (upload, status of processing), statement browser per source with highlighted
evidence, fact graph view, "check a statement" page, and a review/annotation view that
produces gold data for evaluating extractors and resolvers.

## Current state (milestone 1, 2026-11-25)
Implemented as a Python package (`src/linked_pubs/`, see README): typed statements, quote
grounding, Claude and OpenAI-compatible providers, LLM extractor, LLM verifier, SciFact
evaluation. No database yet: extracted statements are cached as JSONL per extractor run
(`data/cache/statements/<run_id>.jsonl`) and results go to `data/runs/`. Postgres, ingest of
PDFs, linking and review screens come with later milestones.

Experiment builder (2026-11-25): `linked-pubs serve` starts a FastAPI app (`server/`) that
serves the React Flow UI (`web/`). The canvas graph is compiled into arms (`server/graph.py`,
one per path from a data block to a metrics block) and run one experiment at a time by a
background thread (`server/runner.py`), stored in `data/experiments/<id>/`. Dropped PDFs
become document sets in `data/docsets/` (text via pypdf; a proper parser comes later).
Each arm records seconds per model call by step and model (`timings`), which the plan uses to
estimate time on that machine. `/api/experiments/{id}/compare/{a}/{s}` lists the pairs where an
abstract arm and a statements arm disagree; `/api/leaderboard` lists all finished arms. The
explanatory texts of the UI live in `web/src/explain.ts` (tested in `explain.test.ts`).
Extraction prompts are versioned in `extract/llm_extractor.py` (`PROMPTS`, `PROMPT_NOTES`); an
Extractor block (or `--extract-prompt`) picks one. The prompt text is part of the run id, so
each version has its own statement cache. Add a version instead of editing one that has results. `run_id` = hash of component,
provider, model, prompt hash and config, so any change to these starts a fresh cache.
