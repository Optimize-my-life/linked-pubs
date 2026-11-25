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

# v2: v1 lost verdicts by rephrasing ("all X segregate randomly" -> "X do not segregate
# asymmetrically", misread as a contradiction) and by dropping CIs and sample sizes
# (see docs/knowledge/evaluation.md). v2 asks to keep the source's polarity and wording and
# the numbers that qualify a result.
SYSTEM_PROMPT_V2 = SYSTEM_PROMPT.replace(
    "- text: one self-contained statement. Resolve pronouns and abbreviations from the context, and keep \
the qualifiers that change whether it is true (population, dose, duration, study design, conditions). \
One fact per statement: split sentences that combine several.",
    "- text: one self-contained statement. Resolve pronouns and abbreviations from the context. Stay \
close to the source's wording and keep its polarity: never turn an affirmative finding into a negated \
one or the reverse. Keep every qualifier that changes whether it is true or how certain it is: \
population, dose, duration, study design, conditions, and the numbers that come with a result \
(effect sizes, confidence intervals, p-values, sample sizes). One fact per statement: split sentences \
that combine several.")
assert SYSTEM_PROMPT_V2 != SYSTEM_PROMPT

PROMPTS = {"extract-v1": SYSTEM_PROMPT, "extract-v2": SYSTEM_PROMPT_V2}
PROMPT_NOTES = {
    "extract-v1": "baseline",
    "extract-v2": "keeps the source's polarity and wording, and CIs, p-values, sample sizes",
}


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


# Small local models sometimes answer a factual text with an empty list (the cheapest valid
# JSON). One retry with this nudge recovers most of them; texts shorter than
# retry_empty_chars are taken at their word.
RETRY_NUDGE = ("\n\nThis text contains factual statements (results or background facts). "
               "Extract them; an empty list is only right for text without any factual claim.")


class LLMExtractor:
    def __init__(self, provider: LLMProvider, grounding_threshold: float = 0.9, max_chars: int = 60000,
                 retry_empty_chars: int = 300, prompt: str = PROMPT_VERSION):
        if prompt not in PROMPTS:
            raise ValueError(f"unknown extraction prompt '{prompt}' (known: {', '.join(PROMPTS)})")
        self.provider = provider
        self.grounding_threshold = grounding_threshold
        self.max_chars = max_chars
        self.retry_empty_chars = retry_empty_chars
        self.prompt = prompt
        self.system_prompt = PROMPTS[prompt]

    def run_info(self) -> RunInfo:
        return RunInfo(
            component="llm_extractor",
            provider=self.provider.name,
            model=self.provider.model,
            prompt_hash=text_hash(self.prompt, self.system_prompt),
            config={**self.provider.config(), "grounding_threshold": self.grounding_threshold,
                    "max_chars": self.max_chars, "retry_empty_chars": self.retry_empty_chars},
        )

    def extract(self, doc: Document) -> list[Statement]:
        run_id = self.run_info().run_id
        statements: list[Statement] = []
        for _, chunk in chunk_text(doc.text, self.max_chars):
            user = f"Source: {doc.title}\n\n<text>\n{chunk}\n</text>"
            out = self.provider.generate(self.system_prompt, user, ExtractionOutput)
            if not out.statements and self.retry_empty_chars and len(chunk) >= self.retry_empty_chars:
                out = self.provider.generate(self.system_prompt, user + RETRY_NUDGE, ExtractionOutput)
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
