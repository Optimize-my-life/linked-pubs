from __future__ import annotations

from typing import Protocol

from ..models import RunInfo, Verdict


class Verifier(Protocol):
    def run_info(self) -> RunInfo: ...

    def verify(self, claim: str, evidence: list[str]) -> Verdict:
        """Judge `claim` against numbered evidence items (0-based ids in the verdict)."""
        ...
