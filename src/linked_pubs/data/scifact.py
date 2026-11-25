"""SciFact (Wadden et al. 2020): claims, abstracts and gold labels.

Files after download: corpus.jsonl, claims_train.jsonl, claims_dev.jsonl, claims_test.jsonl.
Note: the BioNLP 2026 audit (aclanthology.org/2026.bionlp-1.9) found label errors in train/dev;
apply its corrections once available (see docs/knowledge/evaluation.md).
"""
from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..models import Document, Label

SCIFACT_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"

_LABELS = {"SUPPORT": Label.SUPPORT, "CONTRADICT": Label.CONTRADICT}


@dataclass
class Claim:
    id: int
    text: str
    evidence: dict[str, list[dict]]
    cited_doc_ids: list[str]


@dataclass
class Pair:
    """One (claim, cited abstract) pair with its gold label and rationale sentence ids."""

    claim_id: int
    claim: str
    doc_id: str
    gold: Label
    rationale: set[int] = field(default_factory=set)


def download(dest: Path) -> Path:
    """Download and unpack the SciFact release into `dest` (only the .jsonl files)."""
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "data.tar.gz"
    if not archive.exists():
        with httpx.stream("GET", SCIFACT_URL, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with archive.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if member.isfile() and name.endswith(".jsonl"):
                src = tar.extractfile(member)
                if src is not None:
                    (dest / name).write_bytes(src.read())
    return dest


def load_corpus(path: Path) -> dict[str, Document]:
    corpus = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            doc = Document.from_sentences(str(d["doc_id"]), d["title"], d["abstract"])
            corpus[doc.id] = doc
    return corpus


def load_claims(path: Path) -> list[Claim]:
    claims = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            claims.append(Claim(
                id=d["id"],
                text=d["claim"],
                evidence={str(k): v for k, v in d.get("evidence", {}).items()},
                cited_doc_ids=[str(x) for x in d.get("cited_doc_ids", [])],
            ))
    return claims


def gold_pairs(claims: list[Claim]) -> list[Pair]:
    """Every (claim, cited doc) pair. Cited docs without annotated evidence are NOT_ENOUGH_INFO."""
    pairs = []
    for c in claims:
        for doc_id in c.cited_doc_ids:
            sets = c.evidence.get(doc_id, [])
            if sets:
                label = _LABELS[sets[0]["label"]]
                rationale = {i for s in sets for i in s["sentences"]}
            else:
                label, rationale = Label.NEI, set()
            pairs.append(Pair(c.id, c.text, doc_id, label, rationale))
    return pairs
