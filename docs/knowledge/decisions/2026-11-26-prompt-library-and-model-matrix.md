# Prompt library and model comparisons in the builder

Status: accepted
Date: 2026-11-26

## Context
We want to compare many free models and prompt wordings without wiring one block per
variant, and to write prompts in the UI. Results must stay tied to the exact prompt text.

## Decision
- Extractor and verifier blocks hold lists of models and prompts; every combination is an
  arm (max 40). Missing abstract baselines are added automatically (`auto: true`), so
  every statements arm gets an extraction loss.
- Prompts written in the UI are saved as new, immutable prompts (`data/prompts/`), with
  `base` naming the prompt they were copied from. Experiments store the texts they used.
- The Models tab offers a short list of free models, with sizes checked against the
  Ollama registry, plus a download button (Ollama `/api/pull`), and builds comparison canvases
  (as extractors, as judges, or end to end).

## Why
Immutable prompts keep every result reproducible and every cache separate (the text is in the
run id). Lists on blocks keep the canvas readable however many variants run.

## Alternatives
Editable prompts with version history: more UI and easy to mix up results. One block per
model: unreadable canvases beyond a few models.
