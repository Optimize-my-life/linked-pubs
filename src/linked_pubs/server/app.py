"""FastAPI app for the experiment builder: JSON API under /api, built web UI at /.

No authentication: bind to 127.0.0.1 and reach it through an SSH tunnel.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..llm import make_provider, ollama_base_url
from .graph import Graph, compile_graph
from .runner import ProviderFactory, Runner

REPO_ROOT = Path(__file__).resolve().parents[3]


class ExperimentIn(BaseModel):
    name: str = ""
    graph: Graph


def ollama_host() -> str:
    return ollama_base_url()


def default_provider_factory(spec: str):
    kwargs = {"effort": os.environ.get("LINKED_PUBS_EFFORT", "high")} if spec.startswith("anthropic:") else {}
    return make_provider(spec, **kwargs)


def create_app(data_dir: Path = Path("data"), provider_factory: ProviderFactory = default_provider_factory,
               web_dir: Path | None = None, allow_paid: bool | None = None) -> FastAPI:
    if allow_paid is None:
        allow_paid = os.environ.get("LINKED_PUBS_ALLOW_PAID") == "1"
    runner = Runner(data_dir, scifact_dir=data_dir / "scifact", cache_dir=data_dir / "cache",
                    provider_factory=provider_factory, allow_paid=allow_paid)
    app = FastAPI(title="linked-pubs")
    app.state.runner = runner

    @app.get("/api/health")
    def health():
        try:
            version = httpx.get(f"{ollama_host()}/api/version", timeout=8).json().get("version")
        except (httpx.HTTPError, ValueError):
            version = None
        return {"ollama_host": ollama_host(), "ollama_version": version, "allow_paid": allow_paid,
                "scifact": (data_dir / "scifact" / "corpus.jsonl").exists()}

    @app.get("/api/models")
    def models():
        out = []
        try:
            tags = httpx.get(f"{ollama_host()}/api/tags", timeout=8).json().get("models", [])
        except (httpx.HTTPError, ValueError):
            tags = []
        for m in sorted(tags, key=lambda m: m.get("size", 0)):
            details = m.get("details") or {}
            out.append({"spec": f"ollama:{m['name']}", "name": m["name"], "free": True,
                        "size_gb": round(m.get("size", 0) / 1e9, 1),
                        "params": details.get("parameter_size"), "quant": details.get("quantization_level")})
        if allow_paid:
            for name in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
                out.append({"spec": f"anthropic:{name}", "name": name, "free": False})
        return out

    @app.get("/api/prompts")
    def prompts():
        from ..extract.llm_extractor import PROMPT_NOTES, PROMPTS
        return [{"id": k, "note": PROMPT_NOTES.get(k, ""), "text": v} for k, v in PROMPTS.items()]

    @app.post("/api/compile")
    def compile_(graph: Graph):
        result = compile_graph(graph, allow_paid)
        estimates = runner.estimate(result.arms) if result.arms and not result.errors else []
        return {"errors": result.errors, "estimates": estimates,
                "arms": [a.model_dump() | {"label": a.label()} for a in result.arms]}

    @app.get("/api/experiments")
    def list_experiments():
        return runner.list_all()

    @app.post("/api/experiments")
    def submit(body: ExperimentIn):
        try:
            return runner.submit(body.name, body.graph)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/experiments/{exp_id}")
    def get_experiment(exp_id: str):
        try:
            return runner.get(exp_id)
        except KeyError:
            raise HTTPException(404, "no such experiment")

    @app.post("/api/experiments/{exp_id}/cancel")
    def cancel(exp_id: str):
        try:
            runner.cancel(exp_id)
            return runner.get(exp_id)
        except KeyError:
            raise HTTPException(404, "no such experiment")

    @app.get("/api/experiments/{exp_id}/arms/{arm_id}/rows")
    def rows(exp_id: str, arm_id: str):
        try:
            return runner.predictions(exp_id, arm_id)
        except KeyError:
            raise HTTPException(404, "no such arm")

    @app.get("/api/experiments/{exp_id}/compare/{abstract_arm}/{statements_arm}")
    def compare(exp_id: str, abstract_arm: str, statements_arm: str):
        try:
            return runner.compare(exp_id, abstract_arm, statements_arm)
        except KeyError:
            raise HTTPException(404, "no such experiment or arm")

    @app.get("/api/leaderboard")
    def leaderboard():
        return runner.leaderboard()

    @app.post("/api/docsets")
    def create_docset():
        return runner.docsets.summary(runner.docsets.create())

    @app.post("/api/docsets/{docset_id}/files")
    async def upload(docset_id: str, files: list[UploadFile] = File(...)):
        errors = []
        for f in files:
            try:
                runner.docsets.add_file(docset_id, f.filename or "upload", await f.read())
            except KeyError:
                raise HTTPException(404, "no such document set")
            except Exception as e:  # unreadable PDF etc.: report, keep the rest
                errors.append(f"{f.filename}: {e}" if not str(e).startswith(f.filename or "") else str(e))
        return runner.docsets.summary(docset_id) | {"errors": errors}

    @app.get("/api/docsets/{docset_id}")
    def get_docset(docset_id: str):
        try:
            return runner.docsets.summary(docset_id)
        except KeyError:
            raise HTTPException(404, "no such document set")

    web = web_dir or REPO_ROOT / "web" / "dist"
    if (web / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            return FileResponse(web / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_ui():
            return {"message": "Web UI not built: run `npm ci && npm run build` in web/. API docs at /docs."}

    return app
