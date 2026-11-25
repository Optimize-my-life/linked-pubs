import json

from conftest import FakeProvider

from linked_pubs.data.scifact import gold_pairs, load_claims, load_corpus
from linked_pubs.eval.metrics import label_metrics
from linked_pubs.eval.scifact_eval import StatementStore, extract_all, predict, summarize, write_run
from linked_pubs.extract.llm_extractor import LLMExtractor
from linked_pubs.models import (ExtractedStatement, ExtractionOutput, Label, StatementType,
                                VerifierOutput)
from linked_pubs.resolve.llm_verifier import LLMVerifier


def _write_fixture(tmp_path):
    corpus = [
        {"doc_id": 1, "title": "Fibre", "abstract": ["We studied adults.", "Fibre intake lowered LDL cholesterol."]},
        {"doc_id": 2, "title": "Salt", "abstract": ["Salt intake was not related to mortality."]},
    ]
    claims = [
        {"id": 7, "claim": "Fibre lowers LDL cholesterol.",
         "evidence": {"1": [{"sentences": [1], "label": "SUPPORT"}]}, "cited_doc_ids": [1, 2]},
    ]
    (tmp_path / "corpus.jsonl").write_text("\n".join(json.dumps(d) for d in corpus))
    (tmp_path / "claims_dev.jsonl").write_text("\n".join(json.dumps(c) for c in claims))


def test_gold_pairs_include_nei_for_cited_docs_without_evidence(tmp_path):
    _write_fixture(tmp_path)
    pairs = gold_pairs(load_claims(tmp_path / "claims_dev.jsonl"))
    assert [(p.doc_id, p.gold, p.rationale) for p in pairs] == [("1", Label.SUPPORT, {1}), ("2", Label.NEI, set())]


def _fake_extract(system, user, schema):
    if "Fibre intake" in user:
        return ExtractionOutput(statements=[ExtractedStatement(
            text="Fibre intake lowered LDL cholesterol in adults.", evidence_quote="Fibre intake lowered LDL cholesterol",
            type=StatementType.EFFECT, subject="fibre")])
    return ExtractionOutput(statements=[])


def _fake_verify(system, user, schema):
    if "Fibre intake" in user or "Fibre intake lowered" in user:
        evidence_lines = [l for l in user.splitlines() if l.startswith("[")]
        idx = next(i for i, l in enumerate(evidence_lines) if "Fibre intake" in l)
        return VerifierOutput(explanation="direct", label=Label.SUPPORT, evidence_ids=[idx])
    return VerifierOutput(explanation="unrelated", label=Label.NEI, evidence_ids=[])


def test_end_to_end_both_modes(tmp_path):
    _write_fixture(tmp_path)
    corpus = load_corpus(tmp_path / "corpus.jsonl")
    pairs = gold_pairs(load_claims(tmp_path / "claims_dev.jsonl"))
    extractor = LLMExtractor(FakeProvider(_fake_extract))
    verifier = LLMVerifier(FakeProvider(_fake_verify))
    store = StatementStore(tmp_path / "cache", extractor.run_info().run_id)
    assert extract_all([p.doc_id for p in pairs], corpus, extractor, store, workers=2) == []

    summaries, preds = [], {}
    for mode in ["abstract", "statements"]:
        preds[mode] = predict(pairs, corpus, verifier, mode, store, workers=2)
        summaries.append(summarize(preds[mode], mode, corpus, store))

    for s in summaries:
        assert s["label"]["accuracy"] == 1.0
        assert s["rationale"]["f1"] == 1.0
    assert summaries[1]["extraction"]["grounded_rate"] == 1.0
    assert summaries[1]["extraction"]["rationale_coverage"] == 1.0

    write_run(tmp_path / "run", summaries, preds, runs={})
    assert json.loads((tmp_path / "run" / "summary.json").read_text())["extraction_loss_macro_f1"] == 0.0

    # Cache: a second store with the same run id loads the statements, so nothing is re-extracted.
    again = StatementStore(tmp_path / "cache", extractor.run_info().run_id)
    assert set(again.by_doc) == {"1", "2"}


def test_label_metrics_macro_f1():
    m = label_metrics(["a", "a", "b", "c"], ["a", "b", "b", "c"], ["a", "b", "c"])
    assert m["accuracy"] == 0.75
    assert m["per_class"]["a"]["f1"] == round(2 * 1 * 0.5 / 1.5, 4)
    assert m["macro_f1"] == round((0.6667 + 0.6667 + 1.0) / 3, 4)
