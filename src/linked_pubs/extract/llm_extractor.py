"""Statement extraction with an LLM plus a quote-grounding check."""
from __future__ import annotations

from ..grounding import locate_quote
from ..llm.base import LLMProvider
from ..models import Document, ExtractionOutput, RunInfo, Statement, text_hash

PROMPT_VERSION = "extract-v1"

SYSTEM_PROMPT = """\
You turn scientific papers, abstracts and dietary guidelines into atomic factual statements \
for a research knowledge base on human nutrition. The statements are later linked across \
sources, checked against new claims, and turned into constraints for diet optimisation models. \
So each statement must stand on its own and carry its numbers exactly.

For each factual claim the text makes, return:
- text: one self-contained statement. Resolve pronouns and abbreviations from the context, and keep \
the qualifiers that change whether it is true (population, dose, duration, study design, conditions). \
One fact per statement: split sentences that combine several.
- evidence_quote: the shortest span of the source that supports the statement, copied character \
for character. Do not paraphrase, shorten with ellipses, or join text from different places; if the \
support is spread out, quote the most important span.
- type: reference_value (an intake reference such as AR, PRI, RDA or AI), upper_limit (tolerable \
upper intake level), effect (an exposure changes an outcome), recommendation (advice to eat more, \
less or limit something), composition (nutrient content of a food), finding (any other empirical result).
- subject, outcome, direction, value, unit, value_type, population: fill these when the text states \
them and leave them null otherwise. Never supply a number the text does not give.

Include facts the text presents as established background as well as the study's own results. \
Skip aims, methods descriptions and speculation. If the text contains no factual statements, \
return an empty list."""


def chunk_text(text: str, max_chars: int) -> list[tuple[int, str]]:
    """Split on paragraph (else sentence) boundaries into chunks of at most max_chars.

    Returns (offset, chunk) pairs whose chunks concatenate back to `text`.
    """
    if len(text) <= max_chars:
        return [(0, text)]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = text.rfind("\n\n", start, end)
            if cut <= start:
                cut = text.rfind(". ", start, end)
            if cut > start:
                end = cut + 1
        chunks.append((start, text[start:end]))
        start = end
    return chunks


class LLMExtractor:
    def __init__(self, provider: LLMProvider, grounding_threshold: float = 0.9, max_chars: int = 60000):
        self.provider = provider
        self.grounding_threshold = grounding_threshold
        self.max_chars = max_chars

    def run_info(self) -> RunInfo:
        return RunInfo(
            component="llm_extractor",
            provider=self.provider.name,
            model=self.provider.model,
            prompt_hash=text_hash(PROMPT_VERSION, SYSTEM_PROMPT),
            config={**self.provider.config(), "grounding_threshold": self.grounding_threshold,
                    "max_chars": self.max_chars},
        )

    def extract(self, doc: Document) -> list[Statement]:
        run_id = self.run_info().run_id
        statements: list[Statement] = []
        for _, chunk in chunk_text(doc.text, self.max_chars):
            user = f"Source: {doc.title}\n\n<text>\n{chunk}\n</text>"
            out = self.provider.generate(SYSTEM_PROMPT, user, ExtractionOutput)
            for s in out.statements:
                m = locate_quote(s.evidence_quote, doc.text, self.grounding_threshold)
                statements.append(Statement(
                    **s.model_dump(),
                    id=f"{doc.id}:{run_id}:{len(statements)}",
                    source_id=doc.id,
                    run_id=run_id,
                    grounded=m is not None,
                    grounding_score=m.score if m else 0.0,
                    quote_start=m.start if m else None,
                    quote_end=m.end if m else None,
                ))
        return statements
