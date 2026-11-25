"""Pluggable LLM providers. Spec strings: 'ollama:<model>', 'openai_compat:<model>', 'anthropic:<model>'."""
from __future__ import annotations

import os

from .base import LLMError, LLMProvider, LLMRefusal


def ollama_base_url() -> str:
    """Ollama's address from OLLAMA_HOST, usable by a client.

    OLLAMA_HOST is also Ollama's own listen address, often "0.0.0.0" or "localhost". Connecting
    to 0.0.0.0 fails on Windows, and "localhost" costs ~2 s per request there (IPv6 is tried
    first, Ollama listens on IPv4 only), so both become 127.0.0.1.
    """
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if "://" not in host:
        host = "http://" + host
    scheme, _, rest = host.partition("://")
    hostport = rest.split("/", 1)[0]
    name, _, port = hostport.rpartition(":") if ":" in hostport else (hostport, "", "")
    name = name or hostport
    if name in ("0.0.0.0", "localhost", "[::]", "::"):
        name = "127.0.0.1"
    return f"{scheme}://{name}:{port or '11434'}"


def make_provider(spec: str, **kwargs) -> LLMProvider:
    kind, _, model = spec.partition(":")
    if kind == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=model or "claude-opus-5-5", **kwargs)
    if kind == "ollama":
        from .ollama_provider import OllamaProvider

        if not model:
            raise ValueError("ollama needs a model, e.g. ollama:qwen3:8b")
        base_url = kwargs.pop("base_url", None) or ollama_base_url()
        return OllamaProvider(model=model, base_url=base_url, **kwargs)
    if kind == "openai_compat":
        from .openai_compat import OpenAICompatProvider

        if not model:
            raise ValueError("openai_compat needs a model, e.g. openai_compat:qwen3:8b")
        base_url = kwargs.pop("base_url", None) or os.environ.get(
            "LINKED_PUBS_OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"
        )
        return OpenAICompatProvider(model=model, base_url=base_url, **kwargs)
    raise ValueError(f"unknown provider '{kind}' in '{spec}'")


__all__ = ["LLMError", "LLMProvider", "LLMRefusal", "make_provider", "ollama_base_url"]
