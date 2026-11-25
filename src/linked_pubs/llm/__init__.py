"""Pluggable LLM providers. Spec strings: 'anthropic:<model>' or 'openai_compat:<model>'."""
from __future__ import annotations

import os

from .base import LLMError, LLMProvider, LLMRefusal


def make_provider(spec: str, **kwargs) -> LLMProvider:
    kind, _, model = spec.partition(":")
    if kind == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=model or "claude-opus-5-5", **kwargs)
    if kind == "openai_compat":
        from .openai_compat import OpenAICompatProvider

        if not model:
            raise ValueError("openai_compat needs a model, e.g. openai_compat:qwen3:8b")
        base_url = kwargs.pop("base_url", None) or os.environ.get(
            "LINKED_PUBS_OPENAI_BASE_URL", "http://localhost:11434/v1"
        )
        return OpenAICompatProvider(model=model, base_url=base_url, **kwargs)
    raise ValueError(f"unknown provider '{kind}' in '{spec}'")


__all__ = ["LLMError", "LLMProvider", "LLMRefusal", "make_provider"]
