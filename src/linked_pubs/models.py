"""Core data model shared by all plugins."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StatementType(str, Enum):
    REFERENCE_VALUE = "reference_value"
    UPPER_LIMIT = "upper_limit"
    EFFECT = "effect"
    RECOMMENDATION = "recommendation"
    COMPOSITION = "composition"
    FINDING = "finding"


class Direction(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NO_EFFECT = "no_effect"


class ExtractedStatement(BaseModel):
    """What an extractor returns for one statement (the LLM output schema)."""

    text: str = Field(description="One atomic, self-contained factual statement.")
    evidence_quote: str = Field(description="Verbatim span of the source that supports the statement.")
    type: StatementType
    subject: str = Field(description="Nutrient, food, exposure or intervention the statement is about.")
    outcome: Optional[str] = Field(default=None, description="Health outcome or measured quantity, if any.")
    direction: Optional[Direction] = Field(default=None, description="Effect direction of subject on outcome.")
    value: Optional[float] = Field(default=None, description="Numeric value exactly as stated, if any.")
    unit: Optional[str] = Field(default=None, description="Unit of the value, e.g. mg/day.")
    value_type: Optional[str] = Field(default=None, description="Kind of reference value: AR, PRI, RDA, AI, UL, ...")
    population: Optional[str] = Field(default=None, description="Population the statement applies to.")


class ExtractionOutput(BaseModel):
    statements: list[ExtractedStatement]


class Statement(ExtractedStatement):
    """A stored statement: extractor output plus provenance and grounding."""

    id: str
    source_id: str
    run_id: str
    grounded: bool
    grounding_score: float
    quote_start: Optional[int] = None
    quote_end: Optional[int] = None


class Document(BaseModel):
    id: str
    title: str
    text: str
    # (start, end) character spans of sentences in `text`, when known (e.g. SciFact).
    sentence_spans: list[tuple[int, int]] = Field(default_factory=list)

    @classmethod
    def from_sentences(cls, id: str, title: str, sentences: list[str]) -> "Document":
        spans, parts, pos = [], [], 0
        for s in sentences:
            s = s.strip()
            spans.append((pos, pos + len(s)))
            parts.append(s)
            pos += len(s) + 1
        return cls(id=id, title=title, text=" ".join(parts), sentence_spans=spans)


class Label(str, Enum):
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    NEI = "NOT_ENOUGH_INFO"


class VerifierOutput(BaseModel):
    """What a verifier returns (the LLM output schema)."""

    explanation: str = Field(description="Short reasoning: which evidence matters and why.")
    label: Label
    evidence_ids: list[int] = Field(description="Numbers of the evidence items relied on; empty for NOT_ENOUGH_INFO.")


class Verdict(VerifierOutput):
    run_id: str


class RunInfo(BaseModel):
    """Provenance of a component run: enough to reproduce and compare results."""

    component: str
    provider: str
    model: str
    prompt_hash: str
    config: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def run_id(self) -> str:
        key = f"{self.component}|{self.provider}|{self.model}|{self.prompt_hash}|{sorted(self.config.items())}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]


def text_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:12]
