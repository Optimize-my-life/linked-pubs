# Gotchas

- Claude Opus 5.5 / Sonnet 5.5 reject forced tool choice and disabled thinking; structured
  output goes through `beta.messages.parse(output_format=...)`. Effort default on Opus 5.5 is
  `medium`, so the provider always sets it explicitly (`--effort`, default `high`).
- Server-side refusal fallbacks (`fallbacks="default"`) are only sent for models that accept
  them (see `_FALLBACK_MODELS` in `llm/anthropic_provider.py`); Haiku has none.
- SciFact test split has no public labels: evaluate on dev.
- `py` launcher: the default `python` on the dev PC is 3.9; create the venv with `py -3.11`.
