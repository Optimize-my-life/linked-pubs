# Gotchas

- Claude Opus 5.5 / Sonnet 5.5 reject forced tool choice and disabled thinking; structured
  output goes through `beta.messages.parse(output_format=...)`. Effort default on Opus 5.5 is
  `medium`, so the provider always sets it explicitly (`--effort`, default `high`).
- Server-side refusal fallbacks (`fallbacks="default"`) are only sent for models that accept
  them (see `_FALLBACK_MODELS` in `llm/anthropic_provider.py`); Haiku has none.
- SciFact test split has no public labels: evaluate on dev.
- `py` launcher: the default `python` on the dev PC is 3.9; create the venv with `py -3.11`.
- No AI budget: the CLI defaults to a free local model (`ollama:qwen3:8b` via Ollama).
  Paid APIs (`anthropic:...`) are refused unless `--allow-paid` is passed, because
  `ANTHROPIC_API_KEY` may be set and a forgotten flag would otherwise bill.
- Local models run one request at a time (Ollama queues the rest), so keep `--workers 1`;
  parallel requests just wait and can hit the HTTP timeout.
- Use `ollama:<model>`, not `openai_compat:` for Ollama: its default context is 4096 tokens
  and the OpenAI endpoint can't raise it, so prompt + abstract get silently truncated (the
  first test returned zero statements). The native provider sets `num_ctx` (16384) and turns
  thinking off (`think: false`), which is far slower on CPU.
