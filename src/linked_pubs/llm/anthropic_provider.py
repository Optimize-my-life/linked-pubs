"""Claude via the official Anthropic SDK, with structured outputs."""
from __future__ import annotations

import anthropic

from .base import LLMError, LLMRefusal, T

# Models that accept server-side refusal fallbacks (fallbacks="default").
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high",
                 fallbacks: bool | None = None, client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.fallbacks = model.startswith(_FALLBACK_MODELS) if fallbacks is None else fallbacks
        # Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
        self.client = client or anthropic.Anthropic()

    def config(self) -> dict:
        return {"effort": self.effort, "fallbacks": self.fallbacks}

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> T:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self.effort},
        )
        if self.fallbacks:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        response = self.client.beta.messages.parse(**kwargs)
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise LLMRefusal(f"{self.model} declined (category={category}), request {response._request_id}")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"output truncated at max_tokens={max_tokens}, request {response._request_id}")
        if response.parsed_output is None:
            raise LLMError(f"no parsed output, request {response._request_id}")
        return response.parsed_output
