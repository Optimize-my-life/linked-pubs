"""Local or self-hosted open models through an OpenAI-compatible endpoint (Ollama, vLLM, ...).

This is for non-Claude models only; Claude goes through AnthropicProvider.
"""
from __future__ import annotations

import httpx
from pydantic import ValidationError

from .base import LLMError, T


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, model: str, base_url: str, api_key: str | None = None, timeout: float = 600.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.timeout = timeout

    def config(self) -> dict:
        return {"base_url": self.base_url, "temperature": 0}

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> T:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
            },
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        r = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        choice = r.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError(f"output truncated at max_tokens={max_tokens}")
        try:
            return schema.model_validate_json(choice["message"]["content"])
        except ValidationError as e:
            raise LLMError(f"{self.model} returned invalid JSON for {schema.__name__}: {e}") from e
