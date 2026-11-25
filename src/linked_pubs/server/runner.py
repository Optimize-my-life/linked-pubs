"""Runs compiled experiments one at a time (one GPU) and keeps them on disk.

Each experiment lives in data/experiments/<id>/: experiment.json (graph, arms, status,
progress, results) plus one folder per arm with predictions or statements. Extracted
statements go through the shared StatementStore cache, so an extractor configuration that
already ran is not paid for (in time) again.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ..data.scifact import gold_pairs, load_claims, load_corpus
from ..eval.scifact_eval import StatementStore, extract_all, extraction_stats, predict, summarize, write_run
from ..extract import LLMExtractor
from ..llm.base import LLMProvider
from ..models import Document
from ..resolve import LLMVerifier
from .docsets import DocsetStore
from .graph import Arm, Graph, compile_graph

ProviderFactory = Callable[[str], LLMProvider]
ACTIVE = ("queued", "running")


class Cancelled(Exception):
    pass


class _Tracked:
    """Wraps an extractor or verifier: counts finished calls and stops on cancel."""

    def __init__(self, inner, tick: Callable[[], None], cancelled: threading.Event):
        self.inner, self.tick, self.cancelled = inner, tick, cancelled

    def run_info(self):
        return self.inner.run_info()

    def _call(self, fn, *args):
        if self.cancelled.is_set():
            raise Cancelled()
        result = fn(*args)
        self.tick()
        return result

    def extract(self, doc):
        return self._call(self.inner.extract, doc)

    def verify(self, claim, evidence):
        return self._call(self.inner.verify, claim, evidence)


class Runner:
    def __init__(self, data_dir: Path, scifact_dir: Path, cache_dir: Path, provider_factory: ProviderFactory,
                 allow_paid: bool = False):
        self.root = data_dir / "experiments"
        self.root.mkdir(parents=True, exist_ok=True)
        self.scifact_dir, self.cache_dir = scifact_dir, cache_dir
        self.provider_factory = provider_factory
        self.allow_paid = allow_paid
        self.docsets = DocsetStore(data_dir)
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._cancel: dict[str, threading.Event] = {}
        self._corpus: dict[str, Document] | None = None
        self._mark_interrupted()
        self._thread: threading.Thread | None = None

    # ---- storage -------------------------------------------------------------------------
    def _path(self, exp_id: str) -> Path:
        return self.root / exp_id / "experiment.json"

    def get(self, exp_id: str) -> dict:
        path = self._path(exp_id)
        if not exp_id.isalnum() or not path.exists():
            raise KeyError(exp_id)
        with self._lock:
            return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, exp: dict) -> None:
        path = self._path(exp["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(exp, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)

    def _update(self, exp_id: str, **fields) -> dict:
        exp = self.get(exp_id)
        exp.update(fields)
        self._save(exp)
        return exp

    def list_all(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*/experiment.json"), reverse=True):
            e = json.loads(p.read_text(encoding="utf-8"))
            out.append({k: e.get(k) for k in ("id", "name", "status", "created_at", "progress", "error")}
                       | {"arms": len(e.get("arms", []))})
        return out

    def _mark_interrupted(self) -> None:
        for p in self.root.glob("*/experiment.json"):
            e = json.loads(p.read_text(encoding="utf-8"))
            if e.get("status") in ACTIVE:
                e["status"], e["error"] = "interrupted", "server stopped before the experiment finished"
                p.write_text(json.dumps(e, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- submitting ----------------------------------------------------------------------
    def submit(self, name: str, graph: Graph) -> dict:
        compiled = compile_graph(graph, self.allow_paid)
        if compiled.errors:
            raise ValueError("; ".join(compiled.errors))
        exp_id = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
        exp = {
            "id": exp_id, "name": name or exp_id, "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "graph": graph.model_dump(), "arms": [a.model_dump() for a in compiled.arms],
            "progress": None, "results": [], "comparisons": [], "error": None,
        }
        self._save(exp)
        self._cancel[exp_id] = threading.Event()
        self._queue.put(exp_id)
        self._ensure_worker()
        return exp

    def cancel(self, exp_id: str) -> None:
        exp = self.get(exp_id)
        if exp["status"] not in ACTIVE:
            return
        self._cancel.setdefault(exp_id, threading.Event()).set()
        if exp["status"] == "queued":
            self._update(exp_id, status="cancelled")

    def _ensure_worker(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._work, daemon=True, name="experiment-runner")
            self._thread.start()

    def _work(self) -> None:
        while True:
            exp_id = self._queue.get()
            try:
                if self.get(exp_id)["status"] == "queued":
                    self.run(exp_id)
            finally:
                self._queue.task_done()

    # ---- running -------------------------------------------------------------------------
    def run(self, exp_id: str) -> dict:
        cancelled = self._cancel.setdefault(exp_id, threading.Event())
        exp = self._update(exp_id, status="running", started_at=_now())
        arms = [Arm(**a) for a in exp["arms"]]
        results = []
        try:
            for i, arm in enumerate(arms):
                started = time.monotonic()
                try:
                    summary = self._run_arm(exp_id, i, len(arms), arm, cancelled)
                    results.append({"arm": arm.id, "label": arm.label(), "mode": arm.mode, "summary": summary,
                                    "error": None, "seconds": round(time.monotonic() - started, 1)})
                except Cancelled:
                    raise
                except Exception as e:  # one failing arm must not lose the others
                    results.append({"arm": arm.id, "label": arm.label(), "mode": arm.mode, "summary": None,
                                    "error": f"{type(e).__name__}: {e}", "seconds": round(time.monotonic() - started, 1),
                                    "trace": traceback.format_exc(limit=5)})
                self._update(exp_id, results=results)
            status = "done" if all(r["error"] is None for r in results) else "failed"
            return self._update(exp_id, status=status, progress=None, finished_at=_now(),
                                comparisons=_comparisons(arms, results))
        except Cancelled:
            return self._update(exp_id, status="cancelled", progress=None, results=results, finished_at=_now())

    def _run_arm(self, exp_id: str, index: int, n_arms: int, arm: Arm, cancelled: threading.Event) -> dict:
        out_dir = self.root / exp_id / arm.id
        progress = {"arm": arm.id, "arm_index": index + 1, "arms": n_arms, "mode": arm.mode, "step": "",
                    "done": 0, "total": 0, "model": None, "active_node": None, "path": arm.path, "step_started": None}

        def step(name: str, total: int) -> None:
            # The UI shows which block is working and estimates the time left from step_started.
            model = arm.extractor if name == "extract" else arm.verifier
            active = arm.path[1] if name == "extract" else arm.path[-2]
            progress.update(step=name, done=0, total=total, model=model, active_node=active, step_started=time.time())
            self._update(exp_id, progress=dict(progress))

        def tick() -> None:
            progress["done"] += 1
            self._update(exp_id, progress=dict(progress))

        if arm.data.kind == "documents":
            corpus = {d.id: d for d in self.docsets.documents(arm.data.docset_id)}
            pairs = []
        else:
            corpus = self._scifact_corpus()
            claims = load_claims(self.scifact_dir / f"claims_{arm.data.split}.jsonl")
            pairs = gold_pairs(claims[: arm.data.limit] if arm.data.limit else claims)

        store, errors, runs = None, [], {}
        if arm.extractor:
            extractor = LLMExtractor(self.provider_factory(arm.extractor))
            info = extractor.run_info()
            runs["extractor"] = info.model_dump() | {"run_id": info.run_id}
            store = StatementStore(self.cache_dir, info.run_id)
            doc_ids = list(corpus) if arm.data.kind == "documents" else [p.doc_id for p in pairs]
            step("extract", len(set(doc_ids) - set(store.by_doc)))
            errors = extract_all(doc_ids, corpus, _Tracked(extractor, tick, cancelled), store, workers=1)

        if arm.mode == "extraction":
            if arm.data.kind == "documents":
                stmts = [s for d in corpus for s in store.by_doc.get(d, [])]
                summary = {"mode": "extraction", "extraction": {
                    "documents": len(corpus), "statements": len(stmts),
                    "grounded_rate": round(sum(s.grounded for s in stmts) / len(stmts), 4) if stmts else 0.0}}
                out_dir.mkdir(parents=True, exist_ok=True)
                with (out_dir / "statements.jsonl").open("w", encoding="utf-8") as f:
                    for s in stmts:
                        f.write(s.model_dump_json() + "\n")
            else:
                summary = {"mode": "extraction", "extraction": extraction_stats(pairs, corpus, store)}
            summary["errors"] = len(errors)
            summary["error_messages"] = errors[:20]
            return summary

        verifier = LLMVerifier(self.provider_factory(arm.verifier))
        info = verifier.run_info()
        runs["verifier"] = info.model_dump() | {"run_id": info.run_id}
        step("verify", len(pairs))
        preds = predict(pairs, corpus, _Tracked(verifier, tick, cancelled), arm.mode, store, workers=1)
        summary = summarize(preds, arm.mode, corpus, store)
        summary["error_messages"] = (errors + [p.error for p in preds if p.error])[:20]
        write_run(out_dir, [summary], {arm.mode: preds}, runs)
        return summary

    def _scifact_corpus(self) -> dict[str, Document]:
        if self._corpus is None:
            path = self.scifact_dir / "corpus.jsonl"
            if not path.exists():
                raise FileNotFoundError(f"SciFact not found in {self.scifact_dir}: run `linked-pubs scifact-download`")
            self._corpus = load_corpus(path)
        return self._corpus

    def predictions(self, exp_id: str, arm_id: str) -> list[dict]:
        self.get(exp_id)
        d = self.root / exp_id / arm_id
        if not arm_id.isalnum() or not d.is_dir():
            raise KeyError(arm_id)
        files = sorted(d.glob("predictions_*.jsonl")) + sorted(d.glob("statements.jsonl"))
        return [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines() if line]


def _comparisons(arms: list[Arm], results: list[dict]) -> list[dict]:
    """Pair each statements arm with the abstract arm on the same data and verifier."""
    by_id = {r["arm"]: r for r in results if r["summary"]}
    out = []
    for s in arms:
        if s.mode != "statements" or s.id not in by_id:
            continue
        for a in arms:
            if a.mode == "abstract" and a.data == s.data and a.verifier == s.verifier and a.id in by_id:
                fa = by_id[a.id]["summary"]["label"]["macro_f1"]
                fs = by_id[s.id]["summary"]["label"]["macro_f1"]
                out.append({"abstract_arm": a.id, "statements_arm": s.id, "verifier": s.verifier,
                            "extractor": s.extractor, "extraction_loss_macro_f1": round(fa - fs, 4)})
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
