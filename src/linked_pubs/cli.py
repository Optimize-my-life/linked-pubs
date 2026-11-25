"""Command line: linked-pubs <command> [...]."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .extract import LLMExtractor
from .llm import make_provider
from .models import Document
from .resolve import LLMVerifier


def _provider(spec: str, effort: str):
    kwargs = {"effort": effort} if spec.startswith("anthropic") else {}
    return make_provider(spec, **kwargs)


def cmd_scifact_download(args) -> int:
    from .data.scifact import download

    path = download(Path(args.dest))
    print(f"SciFact files in {path}")
    return 0


def cmd_scifact_eval(args) -> int:
    from .data.scifact import gold_pairs, load_claims, load_corpus
    from .eval.scifact_eval import StatementStore, extract_all, predict, summarize, write_run

    data = Path(args.data)
    corpus = load_corpus(data / "corpus.jsonl")
    claims = load_claims(data / f"claims_{args.split}.jsonl")
    if args.limit:
        claims = claims[: args.limit]
    pairs = gold_pairs(claims)
    if not pairs:
        print("No labelled claim/abstract pairs (test split has no public labels?).", file=sys.stderr)
        return 1

    verifier = LLMVerifier(_provider(args.llm, args.effort))
    modes = ["abstract", "statements"] if args.mode == "both" else [args.mode]
    runs = {"verifier": verifier.run_info().model_dump() | {"run_id": verifier.run_info().run_id}}
    store, errors = None, []
    if "statements" in modes:
        extractor = LLMExtractor(_provider(args.extract_llm or args.llm, args.effort))
        info = extractor.run_info()
        runs["extractor"] = info.model_dump() | {"run_id": info.run_id}
        store = StatementStore(Path(args.cache), info.run_id)
        docs = [p.doc_id for p in pairs]
        print(f"Extracting statements from {len(set(docs) - set(store.by_doc))} abstracts "
              f"({len(set(docs) & set(store.by_doc))} cached)...")
        errors = extract_all(docs, corpus, extractor, store, args.workers)

    summaries, preds = [], {}
    for mode in modes:
        print(f"Verifying {len(pairs)} claim/abstract pairs against {mode}...")
        preds[mode] = predict(pairs, corpus, verifier, mode, store, args.workers)
        summaries.append(summarize(preds[mode], mode, corpus, store))

    out = Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}-scifact-{args.split}"
    write_run(out, summaries, preds, runs)
    for s in summaries:
        print(f"[{s['mode']}] macro-F1 {s['label']['macro_f1']}  acc {s['label']['accuracy']}  "
              f"rationale F1 {s['rationale']['f1']}  errors {s['errors']}/{s['pairs']}")
        if "extraction" in s:
            print(f"  extraction: {s['extraction']}")
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    print(f"Results: {out}")
    return 0


def cmd_extract(args) -> int:
    path = Path(args.file)
    doc = Document(id=path.stem, title=args.title or path.stem, text=path.read_text(encoding="utf-8"))
    statements = LLMExtractor(_provider(args.llm, args.effort)).extract(doc)
    print(json.dumps([s.model_dump(mode="json") for s in statements], indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="linked-pubs")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("scifact-download", help="download the SciFact dataset")
    d.add_argument("--dest", default="data/scifact")
    d.set_defaults(func=cmd_scifact_download)

    e = sub.add_parser("scifact-eval", help="evaluate verification on SciFact (abstracts vs. statements)")
    e.add_argument("--data", default="data/scifact")
    e.add_argument("--split", default="dev", choices=["train", "dev", "test"])
    e.add_argument("--limit", type=int, default=20, help="number of claims (0 = all); each costs API calls")
    e.add_argument("--mode", default="both", choices=["abstract", "statements", "both"])
    e.add_argument("--llm", default="anthropic:claude-opus-5-5", help="verifier model spec")
    e.add_argument("--extract-llm", default=None, help="extractor model spec (default: --llm)")
    e.add_argument("--effort", default="high", help="effort for Claude models")
    e.add_argument("--workers", type=int, default=4)
    e.add_argument("--cache", default="data/cache")
    e.add_argument("--out", default="data/runs")
    e.set_defaults(func=cmd_scifact_eval)

    x = sub.add_parser("extract", help="extract statements from a text file")
    x.add_argument("file")
    x.add_argument("--title", default=None)
    x.add_argument("--llm", default="anthropic:claude-opus-5-5")
    x.add_argument("--effort", default="high")
    x.set_defaults(func=cmd_extract)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
