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
- Windows: Python's default file encoding is cp1252, so `Path.write_text(s)` with "→" or other
  non-Latin-1 text raises *after* truncating the file. Always pass `encoding="utf-8"`.
- Windows: `http://localhost:11434` costs ~2.4 s per request (IPv6 is tried first, Ollama
  listens on IPv4 only). Use 127.0.0.1; `llm.ollama_base_url()` also maps OLLAMA_HOST values
  like `0.0.0.0` (Ollama's own listen setting) to a connectable address.
- qwen3:8b sometimes answers an abstract with no statements at all (2 of 19 in the first
  baseline, half of the extraction loss). The extractor retries once with a nudge when a text of
  300+ chars comes back empty (`retry_empty_chars`, part of the run id, so caches stay apart).
