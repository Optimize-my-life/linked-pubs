"""SciFact evaluation: verification against raw abstracts vs. against extracted statements.

Setting: oracle abstracts (each claim is judged against the abstracts it cites), so retrieval
is not tested yet. The gap between the two modes measures what extraction loses or distorts.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..data.scifact import Pair
from ..extract.base import Extractor
from ..llm.base import LLMError
from ..models import Document, Label, Statement
from ..resolve.base import Verifier
from .metrics import label_metrics, set_metrics

LABELS = [Label.SUPPORT, Label.CONTRADICT, Label.NEI]


class StatementStore:
    """JSONL cache of extracted statements per extractor run, so reruns cost nothing."""

    def __init__(self, root: Path, run_id: str):
        self.path = root / "statements" / f"{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.by_doc: dict[str, list[Statement]] = {}
        if self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    self.by_doc[rec["doc_id"]] = [Statement(**s) for s in rec["statements"]]

    def add(self, doc_id: str, statements: list[Statement]) -> None:
        self.by_doc[doc_id] = statements
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"doc_id": doc_id, "statements": [s.model_dump(mode="json") for s in statements]}) + "\n")


def sentences_of(doc: Document) -> list[str]:
    return [doc.text[a:b] for a, b in doc.sentence_spans]


def sentences_covered(doc: Document, statements: list[Statement]) -> set[int]:
    """Sentence ids overlapped by the evidence quotes of grounded statements."""
    hit = set()
    for s in statements:
        if s.quote_start is None or s.quote_end is None:
            continue
        for i, (a, b) in enumerate(doc.sentence_spans):
            if s.quote_start < b and s.quote_end > a:
                hit.add(i)
    return hit


@dataclass
class Prediction:
    pair: Pair
    label: Label | None
    rationale: set[int]
    explanation: str = ""
    error: str = ""


def extract_all(doc_ids: list[str], corpus: dict[str, Document], extractor: Extractor,
                store: StatementStore, workers: int) -> list[str]:
    """Extract statements for docs not in the cache. Returns error messages."""
    todo = [d for d in dict.fromkeys(doc_ids) if d not in store.by_doc]
    errors = []

    def work(doc_id: str):
        try:
            return doc_id, extractor.extract(corpus[doc_id]), None
        except LLMError as e:
            return doc_id, None, str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for doc_id, statements, err in pool.map(work, todo):
            if err:
                errors.append(f"extract {doc_id}: {err}")
            else:
                store.add(doc_id, statements)
    return errors


def predict(pairs: list[Pair], corpus: dict[str, Document], verifier: Verifier, mode: str,
            store: StatementStore | None, workers: int) -> list[Prediction]:
    def work(pair: Pair) -> Prediction:
        doc = corpus[pair.doc_id]
        if mode == "abstract":
            evidence_units = sentences_of(doc)
        else:
            if store is None or pair.doc_id not in store.by_doc:
                return Prediction(pair, None, set(), error="no statements extracted")
            stmts = [s for s in store.by_doc[pair.doc_id] if s.grounded]
            evidence_units = [s.text for s in stmts]
        try:
            v = verifier.verify(pair.claim, evidence_units)
        except LLMError as e:
            return Prediction(pair, None, set(), error=str(e))
        if mode == "abstract":
            rationale = set(v.evidence_ids)
        else:
            rationale = sentences_covered(doc, [stmts[i] for i in v.evidence_ids])
        if v.label == Label.NEI:
            rationale = set()
        return Prediction(pair, v.label, rationale, explanation=v.explanation)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(work, pairs))


def summarize(preds: list[Prediction], mode: str, corpus: dict[str, Document],
              store: StatementStore | None) -> dict:
    ok = [p for p in preds if p.label is not None]
    with_evidence = [p for p in ok if p.pair.gold != Label.NEI]
    summary = {
        "mode": mode,
        "pairs": len(preds),
        "errors": len(preds) - len(ok),
        "label": label_metrics([p.pair.gold for p in ok], [p.label for p in ok], LABELS),
        "rationale": set_metrics([p.pair.rationale for p in with_evidence], [p.rationale for p in with_evidence]),
    }
    if mode == "statements" and store is not None:
        summary["extraction"] = extraction_stats([p.pair for p in preds], corpus, store)
    return summary


def extraction_stats(pairs: list[Pair], corpus: dict[str, Document], store: StatementStore) -> dict:
    """Statement counts, quote-check pass rate, and share of gold rationale sentences covered."""
    doc_ids = {p.doc_id for p in pairs if p.doc_id in store.by_doc}
    all_stmts = [s for d in doc_ids for s in store.by_doc[d]]
    grounded = [s for s in all_stmts if s.grounded]
    with_gold = [p for p in pairs if p.rationale and p.doc_id in store.by_doc]
    gold = [p.rationale for p in with_gold]
    covered = [sentences_covered(corpus[p.doc_id], [s for s in store.by_doc[p.doc_id] if s.grounded])
               for p in with_gold]
    return {
        "documents": len(doc_ids),
        "statements": len(all_stmts),
        "grounded_rate": round(len(grounded) / len(all_stmts), 4) if all_stmts else 0.0,
        # None when no pair has gold evidence (all NEI): nothing to cover.
        "rationale_coverage": set_metrics(gold, covered)["recall"] if gold else None,
    }


def write_run(out_dir: Path, summaries: list[dict], preds: dict[str, list[Prediction]], runs: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"runs": runs, "summaries": summaries}
    if len(summaries) == 2:
        result["extraction_loss_macro_f1"] = round(
            summaries[0]["label"]["macro_f1"] - summaries[1]["label"]["macro_f1"], 4)
    (out_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for mode, ps in preds.items():
        with (out_dir / f"predictions_{mode}.jsonl").open("w", encoding="utf-8") as f:
            for p in ps:
                f.write(json.dumps({
                    "claim_id": p.pair.claim_id, "doc_id": p.pair.doc_id, "gold": p.pair.gold.value,
                    "pred": p.label.value if p.label else None, "gold_rationale": sorted(p.pair.rationale),
                    "pred_rationale": sorted(p.rationale), "explanation": p.explanation, "error": p.error,
                }) + "\n")
