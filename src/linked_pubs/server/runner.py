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
        self._pairs_cache: dict[tuple, list] = {}
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
            exp = json.loads(path.read_text(encoding="utf-8"))
        exp["name"] = _display_name(exp)
        return exp

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
                       | {"arms": len(e.get("arms", [])), "name": _display_name(e)})
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
            "id": exp_id, "name": name or auto_name(compiled.arms), "status": "queued",
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
                timings: dict = {}
                try:
                    summary = self._run_arm(exp_id, i, len(arms), arm, cancelled, timings)
                    results.append({"arm": arm.id, "label": arm.label(), "mode": arm.mode, "summary": summary,
                                    "error": None, "seconds": round(time.monotonic() - started, 1),
                                    "timings": timings})
                except Cancelled:
                    raise
                except Exception as e:  # one failing arm must not lose the others
                    results.append({"arm": arm.id, "label": arm.label(), "mode": arm.mode, "summary": None,
                                    "error": f"{type(e).__name__}: {e}", "seconds": round(time.monotonic() - started, 1),
                                    "timings": timings, "trace": traceback.format_exc(limit=5)})
                self._update(exp_id, results=results)
            status = "done" if all(r["error"] is None for r in results) else "failed"
            return self._update(exp_id, status=status, progress=None, finished_at=_now(),
                                comparisons=_comparisons(arms, results))
        except Cancelled:
            return self._update(exp_id, status="cancelled", progress=None, results=results, finished_at=_now())

    def _run_arm(self, exp_id: str, index: int, n_arms: int, arm: Arm, cancelled: threading.Event,
                 timings: dict) -> dict:
        out_dir = self.root / exp_id / arm.id
        progress = {"arm": arm.id, "arm_index": index + 1, "arms": n_arms, "mode": arm.mode, "step": "",
                    "done": 0, "total": 0, "model": None, "active_node": None, "path": arm.path, "step_started": None}

        def close_step() -> None:
            # Seconds per model call, used to estimate the time of future experiments.
            if progress["step"] and progress["done"]:
                timings[progress["step"]] = {"model": progress["model"], "calls": progress["done"],
                                             "seconds": round(time.time() - progress["step_started"], 2)}

        def step(name: str, total: int) -> None:
            # The UI shows which block is working and estimates the time left from step_started.
            close_step()
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
            pairs = self._pairs(arm)

        store, errors, runs = None, [], {}
        if arm.extractor:
            extractor = LLMExtractor(self.provider_factory(arm.extractor), prompt=arm.extractor_prompt)
            info = extractor.run_info()
            runs["extractor"] = info.model_dump() | {"run_id": info.run_id}
            store = StatementStore(self.cache_dir, info.run_id)
            doc_ids = list(corpus) if arm.data.kind == "documents" else [p.doc_id for p in pairs]
            step("extract", len(set(doc_ids) - set(store.by_doc)))
            errors = extract_all(doc_ids, corpus, _Tracked(extractor, tick, cancelled), store, workers=1)
            close_step()
            out_dir.mkdir(parents=True, exist_ok=True)
            with (out_dir / "statements.jsonl").open("w", encoding="utf-8") as f:
                for d in dict.fromkeys(doc_ids):
                    for st in store.by_doc.get(d, []):
                        f.write(st.model_dump_json() + "\n")

        if arm.mode == "extraction":
            if arm.data.kind == "documents":
                stmts = [s for d in corpus for s in store.by_doc.get(d, [])]
                summary = {"mode": "extraction", "extraction": {
                    "documents": len(corpus), "statements": len(stmts),
                    "grounded_rate": round(sum(s.grounded for s in stmts) / len(stmts), 4) if stmts else 0.0}}
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
        close_step()
        summary = summarize(preds, arm.mode, corpus, store)
        summary["error_messages"] = (errors + [p.error for p in preds if p.error])[:20]
        write_run(out_dir, [summary], {arm.mode: preds}, runs)
        return summary

    def _pairs(self, arm: Arm):
        key = (arm.data.split, arm.data.limit)
        if key not in self._pairs_cache:
            path = self.scifact_dir / f"claims_{arm.data.split}.jsonl"
            if not path.exists():
                raise FileNotFoundError(f"SciFact not found in {self.scifact_dir}: run `linked-pubs scifact-download`")
            claims = load_claims(path)
            self._pairs_cache[key] = gold_pairs(claims[: arm.data.limit] if arm.data.limit else claims)
        return self._pairs_cache[key]

    def seconds_per_call(self) -> dict[tuple[str, str], float]:
        """Average seconds per model call by (step, model), from experiments on this machine."""
        totals: dict[tuple[str, str], list[float]] = {}
        for p in self.root.glob("*/experiment.json"):
            try:
                e = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            for r in e.get("results", []):
                for step, t in (r.get("timings") or {}).items():
                    acc = totals.setdefault((step, t["model"]), [0.0, 0])
                    acc[0] += t["seconds"]
                    acc[1] += t["calls"]
        return {k: v[0] / v[1] for k, v in totals.items() if v[1]}

    def estimate(self, arms: list[Arm]) -> list[dict]:
        """Model calls each arm will make (cached extractions excluded) and the expected time."""
        speed = self.seconds_per_call()
        planned: set[tuple[str, str]] = set()  # (extractor run id, doc) already counted in this plan
        out = []
        for arm in arms:
            try:
                if arm.data.kind == "documents":
                    doc_ids, n_pairs = [d.id for d in self.docsets.documents(arm.data.docset_id)], 0
                else:
                    pairs = self._pairs(arm)
                    doc_ids, n_pairs = list(dict.fromkeys(p.doc_id for p in pairs)), len(pairs)
            except (FileNotFoundError, KeyError) as e:
                out.append({"arm": arm.id, "error": str(e)})
                continue
            extract_calls = cached = 0
            if arm.extractor:
                run_id = LLMExtractor(self.provider_factory(arm.extractor), prompt=arm.extractor_prompt).run_info().run_id
                done = set(_cached_doc_ids(self.cache_dir, run_id))
                for d in doc_ids:
                    if d in done or (run_id, d) in planned:
                        cached += 1
                    else:
                        extract_calls += 1
                        planned.add((run_id, d))
            verify_calls = n_pairs if arm.verifier else 0
            seconds, unknown = 0.0, []
            for step, calls, model in (("extract", extract_calls, arm.extractor),
                                       ("verify", verify_calls, arm.verifier)):
                if not calls:
                    continue
                if (step, model) in speed:
                    seconds += calls * speed[(step, model)]
                else:
                    unknown.append(model)
            out.append({"arm": arm.id, "pairs": n_pairs, "texts": len(doc_ids), "cached": cached,
                        "extract_calls": extract_calls, "verify_calls": verify_calls,
                        "seconds": None if unknown else round(seconds), "unknown": sorted(set(unknown))})
        return out

    def compare(self, exp_id: str, abstract_arm: str, statements_arm: str) -> dict:
        """Pairs where the two arms disagree, with the claim, the gold evidence and the statements used."""
        exp = self.get(exp_id)
        arms = {a["id"]: Arm(**a) for a in exp["arms"]}
        if abstract_arm not in arms or statements_arm not in arms:
            raise KeyError("arm")
        s_files = self.predictions(exp_id, statements_arm)
        a_rows = {(r["claim_id"], r["doc_id"]): r for r in self.predictions(exp_id, abstract_arm)["predictions"]}
        s_rows = {(r["claim_id"], r["doc_id"]): r for r in s_files["predictions"]}
        statements: dict[str, list[dict]] = {}
        for st in s_files["statements"]:
            statements.setdefault(st["source_id"], []).append(st)
        if not statements:
            # Runs from before statements.jsonl existed: read the cache via the extractor run id.
            summary_path = self.root / exp_id / statements_arm / "summary.json"
            if summary_path.exists():
                run_id = json.loads(summary_path.read_text(encoding="utf-8"))["runs"].get("extractor", {}).get("run_id")
                if run_id:
                    store = StatementStore(self.cache_dir, run_id)
                    statements = {d: [st.model_dump(mode="json") for st in sts] for d, sts in store.by_doc.items()}
        corpus = self._scifact_corpus()
        pairs = {(p.claim_id, p.doc_id): p for p in self._pairs(arms[statements_arm])}
        items, counts = [], {"lost": 0, "gained": 0, "both_wrong": 0, "same": 0}
        for key, ar in a_rows.items():
            sr = s_rows.get(key)
            if not sr:
                continue
            a_ok, s_ok = ar["pred"] == ar["gold"], sr["pred"] == sr["gold"]
            kind = ("same" if ar["pred"] == sr["pred"] else "lost" if a_ok and not s_ok
                    else "gained" if s_ok and not a_ok else "both_wrong")
            counts[kind] += 1
            if kind == "same":
                continue
            pair, doc = pairs.get(key), corpus.get(str(key[1]))
            gold_sents = ([doc.text[a:b] for i, (a, b) in enumerate(doc.sentence_spans) if i in pair.rationale]
                          if pair and doc else [])
            used = [st for st in statements.get(str(key[1]), []) if st.get("grounded")]
            covered = set()
            if pair and doc:
                for st in used:
                    for i, (a, b) in enumerate(doc.sentence_spans):
                        if st.get("quote_start") is not None and st["quote_start"] < b and st["quote_end"] > a:
                            covered.add(i)
            items.append({
                "kind": kind, "claim_id": key[0], "doc_id": key[1],
                "claim": pair.claim if pair else ar.get("claim", ""), "title": doc.title if doc else "",
                "gold": ar["gold"], "abstract_pred": ar["pred"], "statements_pred": sr["pred"],
                "abstract_explanation": ar["explanation"], "statements_explanation": sr["explanation"],
                "gold_evidence": gold_sents,
                "gold_evidence_quoted": bool(pair and pair.rationale and pair.rationale <= covered),
                "statements": [{"text": st["text"], "type": st["type"]} for st in used],
            })
        order = {"lost": 0, "both_wrong": 1, "gained": 2}
        items.sort(key=lambda x: order[x["kind"]])
        return {"counts": counts, "items": items}

    def leaderboard(self) -> list[dict]:
        """One row per finished arm across all experiments, for comparing models over time."""
        rows = []
        for p in self.root.glob("*/experiment.json"):
            e = json.loads(p.read_text(encoding="utf-8"))
            arms = {a["id"]: Arm(**a) for a in e.get("arms", [])}
            for r in e.get("results", []):
                s, arm = r.get("summary"), arms.get(r["arm"])
                if not s or not arm:
                    continue
                label, rat, ext = s.get("label") or {}, s.get("rationale") or {}, s.get("extraction") or {}
                rows.append({
                    "experiment": e["id"], "experiment_name": e.get("name"), "date": e.get("created_at"),
                    "arm": r["arm"], "data": arm.data.label(), "mode": arm.mode,
                    "extractor": arm.extractor, "extractor_prompt": arm.extractor_prompt,
                    "verifier": arm.verifier, "pairs": s.get("pairs"),
                    "macro_f1": label.get("macro_f1"), "accuracy": label.get("accuracy"),
                    "rationale_f1": rat.get("f1"), "statements": ext.get("statements"),
                    "grounded_rate": ext.get("grounded_rate"), "rationale_coverage": ext.get("rationale_coverage"),
                    "seconds": r.get("seconds"),
                })
        rows.sort(key=lambda x: x["date"] or "", reverse=True)
        return rows

    def _scifact_corpus(self) -> dict[str, Document]:
        if self._corpus is None:
            path = self.scifact_dir / "corpus.jsonl"
            if not path.exists():
                raise FileNotFoundError(f"SciFact not found in {self.scifact_dir}: run `linked-pubs scifact-download`")
            self._corpus = load_corpus(path)
        return self._corpus

    def predictions(self, exp_id: str, arm_id: str) -> dict:
        self.get(exp_id)
        d = self.root / exp_id / arm_id
        if not arm_id.isalnum() or not d.is_dir():
            raise KeyError(arm_id)
        def read(files):
            return [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines() if line]
        return {"predictions": read(sorted(d.glob("predictions_*.jsonl"))),
                "statements": read(sorted(d.glob("statements.jsonl")))}


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


def auto_name(arms: list[Arm]) -> str:
    """Readable default name, e.g. "qwen3:8b · SciFact dev (20 claims) · abstracts vs statements"."""
    def short(spec):
        return spec.split(":", 1)[1] if spec and ":" in spec else spec
    models = list(dict.fromkeys(short(m) for a in arms for m in (a.extractor, a.verifier) if m))
    prompts = list(dict.fromkeys(a.extractor_prompt for a in arms if a.extractor))
    if len(prompts) > 1:
        models.append(" vs ".join(p.replace("extract-", "prompt ") for p in prompts))
    data = " + ".join(dict.fromkeys(a.data.label() for a in arms))
    modes = {a.mode for a in arms}
    what = ("abstracts vs statements" if {"abstract", "statements"} <= modes else
            "statements" if "statements" in modes else "abstracts" if "abstract" in modes else "extraction")
    return f"{' vs '.join(models)} · {data} · {what}"


def _display_name(exp: dict) -> str:
    # Runs submitted without a name used to get their id as name.
    if exp.get("name") and exp["name"] != exp["id"]:
        return exp["name"]
    try:
        return auto_name([Arm(**a) for a in exp.get("arms", [])]) or exp["id"]
    except Exception:
        return exp["id"]


def _cached_doc_ids(cache_dir: Path, run_id: str) -> list[str]:
    """Doc ids in the statement cache of one extractor run."""
    path = cache_dir / "statements" / f"{run_id}.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line)["doc_id"] for line in f if line.strip()]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
