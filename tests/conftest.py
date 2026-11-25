from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel


class FakeProvider:
    """LLM stand-in: `respond(system, user, schema)` returns the schema instance."""

    name = "fake"
    model = "fake-1"

    def __init__(self, respond: Callable[[str, str, type[BaseModel]], BaseModel]):
        self.respond = respond
        self.calls: list[str] = []

    def config(self) -> dict:
        return {}

    def generate(self, system, user, schema, max_tokens=16000):
        self.calls.append(user)
        return self.respond(system, user, schema)
