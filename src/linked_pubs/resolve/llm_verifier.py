"""Claim verification with an LLM judge."""
from __future__ import annotations

from ..llm.base import LLMProvider
from ..models import Label, RunInfo, Verdict, VerifierOutput, text_hash

PROMPT_VERSION = "verify-v1"

SYSTEM_PROMPT = """\
You judge whether evidence from scientific sources supports or contradicts a claim.

Labels:
- SUPPORT: the evidence, read as a whole, shows the claim is true.
- CONTRADICT: the evidence shows the claim is false.
- NOT_ENOUGH_INFO: neither, including when the evidence concerns a related but different \
population, dose, exposure or outcome.

Judge only from the evidence given, not from background knowledge. List the numbers of the \
evidence items you relied on; leave the list empty for NOT_ENOUGH_INFO."""


class LLMVerifier:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def run_info(self) -> RunInfo:
        return RunInfo(
            component="llm_verifier",
            provider=self.provider.name,
            model=self.provider.model,
            prompt_hash=text_hash(PROMPT_VERSION, SYSTEM_PROMPT),
            config=self.provider.config(),
        )

    def verify(self, claim: str, evidence: list[str]) -> Verdict:
        run_id = self.run_info().run_id
        if not evidence:
            return Verdict(explanation="No evidence given.", label=Label.NEI, evidence_ids=[], run_id=run_id)
        items = "\n".join(f"[{i}] {e}" for i, e in enumerate(evidence))
        user = f"Claim: {claim}\n\nEvidence:\n{items}"
        out = self.provider.generate(SYSTEM_PROMPT, user, VerifierOutput, max_tokens=4000)
        ids = [i for i in out.evidence_ids if 0 <= i < len(evidence)]
        return Verdict(explanation=out.explanation, label=out.label, evidence_ids=ids, run_id=run_id)
