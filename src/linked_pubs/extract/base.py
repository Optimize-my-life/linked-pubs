from __future__ import annotations

from typing import Protocol

from ..models import Document, RunInfo, Statement


class Extractor(Protocol):
    def run_info(self) -> RunInfo: ...

    def extract(self, doc: Document) -> list[Statement]: ...
