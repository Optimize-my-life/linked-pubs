from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The provider returned no usable result (truncated, unparsable, ...)."""


class LLMRefusal(LLMError):
    """The model declined the request."""


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str, schema: type[T], max_tokens: int = 16000) -> T:
        """Return an instance of `schema` produced by the model."""
        ...

    def config(self) -> dict:
        """Settings that affect output (recorded in RunInfo)."""
        ...
