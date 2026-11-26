"""Experiment graphs from the visual builder, compiled into runnable arms.

The canvas holds blocks (dataset, documents, extractor, verifier, metrics) joined by edges.
Every path from a data block to a metrics block is one arm:

    dataset   -> verifier -> metrics               verify claims against raw abstracts
    dataset   -> extractor -> verifier -> metrics  verify against extracted statements only
    dataset   -> extractor -> metrics              extraction quality only
    documents -> extractor -> metrics              extract statements from uploaded PDFs

An extractor or verifier block may hold several models and prompts: every combination
becomes its own arm, so one block can compare models. A statements arm and an abstract arm
on the same dataset with the same verifier model and prompt are paired, and their macro-F1
difference is reported as the extraction loss. When a statements arm has no such abstract
arm, one is added automatically (auto=True), so every extractor gets its loss measured.
"""
from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Literal

from pydantic import BaseModel, Field

from .prompts import BUILTIN, DEFAULT, Prompt

NodeType = Literal["dataset", "documents", "extractor", "verifier", "metrics"]
PAID_PROVIDERS = ("anthropic",)
MAX_ARMS = 40


class Node(BaseModel):
    id: str
    type: NodeType
    data: dict = Field(default_factory=dict)
    position: dict | None = None  # canvas layout only


class Edge(BaseModel):
    source: str
    target: str


class Graph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


class DataSpec(BaseModel):
    kind: Literal["scifact", "documents"]
    split: str = "dev"
    limit: int = 20
    docset_id: str | None = None

    def label(self) -> str:
        if self.kind == "scifact":
            if not self.limit:
                return f"SciFact {self.split} (all claims)"
            return f"SciFact {self.split} ({self.limit} claim{'' if self.limit == 1 else 's'})"
        return f"documents {self.docset_id}"


class Arm(BaseModel):
    id: str
    data: DataSpec
    mode: Literal["abstract", "statements", "extraction"]
    extractor: str | None = None
    extractor_prompt: str = "extract-v1"
    verifier: str | None = None
    verifier_prompt: str = "verify-v1"
    path: list[str]
    auto: bool = False  # added by the compiler as the baseline for a statements arm

    def label(self) -> str:
        parts = [self.data.label()]
        if self.extractor:
            prompt = "" if self.extractor_prompt == DEFAULT["extract"] else f" ({self.extractor_prompt})"
            parts.append(f"extract {self.extractor}{prompt}")
        if self.verifier:
            prompt = "" if self.verifier_prompt == DEFAULT["verify"] else f" ({self.verifier_prompt})"
            parts.append(f"verify {self.verifier}{prompt}")
        return " → ".join(parts)

    def abstract_key(self) -> tuple:
        return (self.data.model_dump_json(), self.verifier, self.verifier_prompt)


class CompileResult(BaseModel):
    arms: list[Arm]
    errors: list[str]


SHAPES = {
    ("dataset", "verifier", "metrics"): "abstract",
    ("dataset", "extractor", "verifier", "metrics"): "statements",
    ("dataset", "extractor", "metrics"): "extraction",
    ("documents", "extractor", "metrics"): "extraction",
}


def block_options(node: Node) -> tuple[list[str], list[str]]:
    """Models and prompts chosen on an extractor or verifier block (older graphs: one each)."""
    d = node.data
    models = d.get("models") if isinstance(d.get("models"), list) else [d.get("model")]
    prompts = d.get("prompts") if isinstance(d.get("prompts"), list) else [d.get("prompt")]
    kind = "extract" if node.type == "extractor" else "verify"
    models = list(dict.fromkeys(m.strip() for m in models if isinstance(m, str) and m.strip()))
    prompts = list(dict.fromkeys(p for p in prompts if isinstance(p, str) and p)) or [DEFAULT[kind]]
    return models, prompts


def compile_graph(graph: Graph, allow_paid: bool = False, prompts: Mapping[str, Prompt] | None = None) -> CompileResult:
    library = BUILTIN if prompts is None else prompts
    nodes = {n.id: n for n in graph.nodes}
    out: dict[str, list[str]] = {n: [] for n in nodes}
    errors: list[str] = []
    for e in graph.edges:
        if e.source in nodes and e.target in nodes:
            out[e.source].append(e.target)

    paths: list[list[str]] = []

    def walk(path: list[str]) -> None:
        node = nodes[path[-1]]
        if node.type == "metrics":
            paths.append(path)
            return
        for nxt in out[node.id]:
            if nxt not in path and len(path) < 6:
                walk(path + [nxt])

    for n in graph.nodes:
        if n.type in ("dataset", "documents"):
            walk([n.id])

    # Check each model block once, so a problem is reported once however many paths use it.
    options: dict[str, list[tuple[str, str]]] = {}
    for n in graph.nodes:
        if n.type not in ("extractor", "verifier"):
            continue
        models, chosen = block_options(n)
        kind = "extract" if n.type == "extractor" else "verify"
        bad = False
        if not models:
            errors.append(f"{n.type} block has no model selected")
            bad = True
        for m in models:
            if m.split(":", 1)[0] in PAID_PROVIDERS and not allow_paid:
                errors.append(f"{m} is a paid API; the server only allows it with LINKED_PUBS_ALLOW_PAID=1")
                bad = True
        for p in chosen:
            if p not in library or library[p].kind != kind:
                errors.append(f"{n.type} block has an unknown prompt '{p}'")
                bad = True
        if not bad:
            options[n.id] = list(product(models, chosen))

    arms: list[Arm] = []
    seen: set[tuple] = set()

    def add(arm: Arm) -> None:
        key = (arm.data.model_dump_json(), arm.mode, arm.extractor, arm.extractor_prompt, arm.verifier,
               arm.verifier_prompt)
        if key not in seen:
            seen.add(key)
            arms.append(arm.model_copy(update={"id": f"arm{len(arms) + 1}"}))

    for path in paths:
        shape = tuple(nodes[i].type for i in path)
        mode = SHAPES.get(shape)
        if mode is None:
            errors.append("unsupported chain: " + " → ".join(shape))
            continue
        try:
            data = _data_spec(nodes[path[0]])
        except ValueError as e:
            errors.append(str(e))
            continue
        middle = path[1:-1]
        if any(i not in options for i in middle):
            continue
        for combo in product(*(options[i] for i in middle)):
            fields: dict = {}
            for node_id, (m, p) in zip(middle, combo):
                if nodes[node_id].type == "extractor":
                    fields |= {"extractor": m, "extractor_prompt": p}
                else:
                    fields |= {"verifier": m, "verifier_prompt": p}
            add(Arm(id="", data=data, mode=mode, path=path, **fields))

    # Every statements arm needs an abstract arm with the same data and verifier to measure
    # what extraction loses. Add the missing ones.
    have = {a.abstract_key() for a in arms if a.mode == "abstract"}
    for s in [a for a in arms if a.mode == "statements"]:
        if s.abstract_key() not in have:
            have.add(s.abstract_key())
            add(Arm(id="", data=s.data, mode="abstract", verifier=s.verifier, verifier_prompt=s.verifier_prompt,
                    path=[s.path[0], s.path[-2], s.path[-1]], auto=True))

    connected = {i for p in paths for i in p}
    for n in graph.nodes:
        if n.id not in connected:
            errors.append(f"{n.type} block is not on a path to a metrics block")
    if len(arms) > MAX_ARMS:
        errors.append(f"{len(arms)} arms is too many for one experiment (max {MAX_ARMS}): pick fewer models or prompts")
    if not arms and not errors:
        errors.append("connect a dataset to a metrics block to define an experiment")
    return CompileResult(arms=arms, errors=list(dict.fromkeys(errors)))


def _data_spec(node: Node) -> DataSpec:
    if node.type == "documents":
        docset = node.data.get("docset_id")
        if not docset:
            raise ValueError("documents block has no files yet: drop PDFs onto it")
        return DataSpec(kind="documents", docset_id=docset, limit=0)
    split = node.data.get("split", "dev")
    if split == "test":
        raise ValueError("SciFact test split has no public labels: use dev or train")
    return DataSpec(kind="scifact", split=split, limit=int(node.data.get("limit", 20) or 0))
