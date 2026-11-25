"""Free local models through Ollama's native API.

Preferred over openai_compat for Ollama: only the native API lets us set the context window
(Ollama's default is 4096 tokens, which silently truncates prompt + abstract) and switch a
model's thinking mode off (slow on CPU).

Small local models under constrained decoding tend to answer with the emptiest valid JSON
(`{"statements": []}`) unless the prompt shows the schema, so the schema is appended to the
system prompt as Ollama recommends.
"""
from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from .base import LLMError, T


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", num_ctx: int = 16384,
                 think: bool = False, timeout: float = 1800.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.think = think
        self.timeout = timeout

    def config(self) -> dict:
        return {"num_ctx": self.num_ctx, "think": self.think, "temperature": 0, "schema_in_prompt": True}

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> T:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system + _schema_hint(schema)},
                         {"role": "user", "content": user}],
            "format": schema.model_json_schema(),
            "think": self.think,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": max_tokens},
        }
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"ollama request failed ({self.base_url}): {e}") from e
        body = r.json()
        if body.get("done_reason") == "length":
            raise LLMError(f"output truncated at num_predict={max_tokens}")
        if body.get("prompt_eval_count", 0) >= self.num_ctx:
            raise LLMError(f"prompt filled the context window (num_ctx={self.num_ctx})")
        try:
            return schema.model_validate_json(body["message"]["content"])
        except ValidationError as e:
            raise LLMError(f"{self.model} returned invalid JSON for {schema.__name__}: {e}") from e


def _schema_hint(schema: type[T]) -> str:
    return "\n\nRespond with JSON only, matching this schema:\n" + json.dumps(schema.model_json_schema())
