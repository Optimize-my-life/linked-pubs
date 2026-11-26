# Knowledge index

- `README.md`: format and rules of this knowledge base.
- `architecture.md`: pipeline (ingest → extract → link → verify), data model, components.
- `decisions/2026-11-25-scope-and-pluggability.md`: what the tool does; extractors and resolvers are plugins.
- `evaluation.md`: evaluation layers, datasets, SciFact as milestone 1, open solvability question.
- `decisions/2026-11-25-domain-nutrition-optimisation.md`: nutrition as application; facts feed optimisation.
- `decisions/2026-11-25-stack.md`: Python/FastAPI, Postgres+pgvector, worker queue, React UI (proposed).
- `decisions/2026-11-26-prompt-library-and-model-matrix.md`: several models/prompts per block, auto baselines, immutable UI prompts, model downloads.
- `gotchas.md`: API and dataset traps (Claude structured output, fallbacks, SciFact test labels, Python version, Ollama context/thinking, free-by-default).
- `decisions/2026-11-25-experiment-builder-ui.md`: visual pipeline builder (React Flow), runs on the GPU PC behind an SSH tunnel.
- `problems/`: open and solved problems.
  - `2026-11-25-run-on-big-pc.md` (open): set up the app on the GPU PC and the SSH tunnel.
