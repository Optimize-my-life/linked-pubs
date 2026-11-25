from conftest import FakeProvider

from linked_pubs.extract.llm_extractor import LLMExtractor, chunk_text
from linked_pubs.models import (Document, ExtractedStatement, ExtractionOutput, Label, StatementType,
                                VerifierOutput)
from linked_pubs.resolve.llm_verifier import LLMVerifier

DOC = Document(id="d1", title="Iron", text="The PRI for iron is 16 mg/day in women. Men need less.")


def _stmt(text, quote, **kw):
    return ExtractedStatement(text=text, evidence_quote=quote, type=StatementType.REFERENCE_VALUE,
                              subject="iron", **kw)


def test_extractor_flags_ungrounded_statements():
    out = ExtractionOutput(statements=[
        _stmt("The PRI for iron for women is 16 mg/day.", "PRI for iron is 16 mg/day in women",
              value=16, unit="mg/day", value_type="PRI", population="women"),
        _stmt("Men need 11 mg/day of iron.", "Men need 11 mg/day"),
    ])
    ex = LLMExtractor(FakeProvider(lambda s, u, schema: out))
    stmts = ex.extract(DOC)
    assert [s.grounded for s in stmts] == [True, False]
    assert DOC.text[stmts[0].quote_start:stmts[0].quote_end] == "PRI for iron is 16 mg/day in women"
    assert stmts[0].run_id == ex.run_info().run_id
    assert stmts[0].value == 16


def test_run_id_changes_with_config():
    p = FakeProvider(lambda *a: None)
    assert LLMExtractor(p, grounding_threshold=0.9).run_info().run_id != \
        LLMExtractor(p, grounding_threshold=0.8).run_info().run_id


def test_chunk_text_round_trips():
    text = "\n\n".join(f"Paragraph {i}. " + "x" * 50 for i in range(20))
    chunks = chunk_text(text, 200)
    assert len(chunks) > 1
    assert "".join(c for _, c in chunks) == text
    assert all(len(c) <= 200 for _, c in chunks)


def test_verifier_drops_out_of_range_evidence_ids():
    out = VerifierOutput(explanation="item 0 states it", label=Label.SUPPORT, evidence_ids=[0, 7])
    v = LLMVerifier(FakeProvider(lambda *a: out)).verify("claim", ["evidence"])
    assert v.label == Label.SUPPORT and v.evidence_ids == [0]


def test_verifier_without_evidence_is_nei_without_call():
    p = FakeProvider(lambda *a: None)
    assert LLMVerifier(p).verify("claim", []).label == Label.NEI
    assert p.calls == []


def test_extractor_retries_once_when_a_long_text_yields_nothing():
    long_doc = Document(id="d2", title="Iron", text=DOC.text + " " + "Background sentence. " * 20)
    answers = [ExtractionOutput(statements=[]), ExtractionOutput(statements=[
        _stmt("The PRI for iron for women is 16 mg/day.", "PRI for iron is 16 mg/day in women")])]
    p = FakeProvider(lambda s, u, schema: answers.pop(0))
    stmts = LLMExtractor(p).extract(long_doc)
    assert len(p.calls) == 2 and "contains factual statements" in p.calls[1]
    assert len(stmts) == 1


def test_extractor_accepts_empty_answer_for_short_text():
    p = FakeProvider(lambda s, u, schema: ExtractionOutput(statements=[]))
    assert LLMExtractor(p).extract(DOC) == [] and len(p.calls) == 1
