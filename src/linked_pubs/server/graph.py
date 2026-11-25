"""Experiment graphs from the visual builder, compiled into runnable arms.

The canvas holds blocks (dataset, documents, extractor, verifier, metrics) joined by edges.
Every path from a data block to a metrics block is one arm:

    dataset   -> verifier -> metrics               verify claims against raw abstracts
    dataset   -> extractor -> verifier -> metrics  verify against extracted statements only
    dataset   -> extractor -> metrics              extraction quality only
    documents -> extractor -> metrics              extract statements from uploaded PDFs

A statements arm and an abstract arm on the same dataset with the same verifier model are
paired, and their macro-F1 difference is reported as the extraction loss.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal["dataset", "documents", "extractor", "verifier", "metrics"]
PAID_PROVIDERS = ("anthropic",)


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
            return f"SciFact {self.split}" + (f" ({self.limit} claims)" if self.limit else " (all)")
        return f"documents {self.docset_id}"


class Arm(BaseModel):
    id: str
    data: DataSpec
    mode: Literal["abstract", "statements", "extraction"]
    extractor: str | None = None
    verifier: str | None = None
    path: list[str]

    def label(self) -> str:
        parts = [self.data.label()]
        if self.extractor:
            parts.append(f"extract {self.extractor}")
        if self.verifier:
            parts.append(f"verify {self.verifier}")
        return " → ".join(parts)


class CompileResult(BaseModel):
    arms: list[Arm]
    errors: list[str]


SHAPES = {
    ("dataset", "verifier", "metrics"): "abstract",
    ("dataset", "extractor", "verifier", "metrics"): "statements",
    ("dataset", "extractor", "metrics"): "extraction",
    ("documents", "extractor", "metrics"): "extraction",
}


def compile_graph(graph: Graph, allow_paid: bool = False) -> CompileResult:
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

    arms: list[Arm] = []
    seen: set[tuple] = set()
    for path in paths:
        shape = tuple(nodes[i].type for i in path)
        mode = SHAPES.get(shape)
        if mode is None:
            errors.append("unsupported chain: " + " → ".join(shape))
            continue
        src = nodes[path[0]]
        try:
            data = _data_spec(src)
        except ValueError as e:
            errors.append(str(e))
            continue
        extractor = verifier = None
        for i in path[1:-1]:
            node = nodes[i]
            model = (node.data.get("model") or "").strip()
            if not model:
                errors.append(f"{node.type} block has no model selected")
                break
            if model.split(":", 1)[0] in PAID_PROVIDERS and not allow_paid:
                errors.append(f"{model} is a paid API; the server only allows it with LINKED_PUBS_ALLOW_PAID=1")
                break
            if node.type == "extractor":
                extractor = model
            else:
                verifier = model
        else:
            key = (data.model_dump_json(), mode, extractor, verifier)
            if key in seen:
                continue
            seen.add(key)
            arms.append(Arm(id=f"arm{len(arms) + 1}", data=data, mode=mode, extractor=extractor,
                            verifier=verifier, path=path))

    connected = {i for p in paths for i in p}
    for n in graph.nodes:
        if n.id not in connected:
            errors.append(f"{n.type} block is not on a path to a metrics block")
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
