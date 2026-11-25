# Scope and pluggable extraction/resolution

Status: accepted
Date: 2026-11-25

## Context
PhD research tool. Input: thousands+ of PDFs (scientific papers, guidelines).
Methods are part of the research, so we need to compare approaches, not hard-code one.

## Decision
1. **Extraction**: turn each source into atomic factual statements, each tied to a
   verbatim evidence quote and page in the source.
2. **Resolution**, both modes:
   - *Linking*: match statements across sources (equivalent / entails / contradicts /
     related) → a graph of facts across publications.
   - *Verification*: judge a new statement as supported / contradicted / not enough
     info against the fact base, with citations.
3. **Extractors and resolvers are plugins** behind small interfaces. LLM providers are
   also pluggable (Claude API, local models via an OpenAI-compatible endpoint such as
   Ollama/vLLM). Non-LLM resolvers (embedding similarity, NLI cross-encoder) are
   first-class too.
4. Every output records which plugin, model, prompt version and config produced it.
5. Web UI as the main interface.

## Why
Comparing methods is a research result in itself; provenance makes runs reproducible
and lets the thesis report metrics per approach on the same corpus.

## Alternatives
- Single fixed LLM pipeline: faster to build, but no way to compare methods.
- CLI/notebooks only: rejected; a UI is wanted for browsing and reviewing facts.
