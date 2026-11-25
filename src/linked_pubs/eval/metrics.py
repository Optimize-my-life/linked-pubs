from __future__ import annotations

from collections.abc import Hashable, Sequence


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}


def label_metrics(gold: Sequence[Hashable], pred: Sequence[Hashable], labels: Sequence[Hashable]) -> dict:
    """Accuracy, per-class P/R/F1 and macro-F1 over the given label set."""
    assert len(gold) == len(pred)
    per_class = {}
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(gold, pred))
        fp = sum(g != lab and p == lab for g, p in zip(gold, pred))
        fn = sum(g == lab and p != lab for g, p in zip(gold, pred))
        per_class[str(getattr(lab, "value", lab))] = prf(tp, fp, fn)
    n = len(gold)
    return {
        "n": n,
        "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / n, 4) if n else 0.0,
        "macro_f1": round(sum(c["f1"] for c in per_class.values()) / len(labels), 4) if labels else 0.0,
        "per_class": per_class,
    }


def set_metrics(gold_sets: Sequence[set], pred_sets: Sequence[set]) -> dict[str, float]:
    """Micro P/R/F1 over items in paired sets (e.g. rationale sentence ids per pair)."""
    tp = sum(len(g & p) for g, p in zip(gold_sets, pred_sets))
    fp = sum(len(p - g) for g, p in zip(gold_sets, pred_sets))
    fn = sum(len(g - p) for g, p in zip(gold_sets, pred_sets))
    return prf(tp, fp, fn)
