"""FastAPI app for the experiment builder: JSON API under /api, built web UI at /.

No authentication: bind to 127.0.0.1 and reach it through an SSH tunnel.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..llm import make_provider, ollama_base_url
from .graph import Graph, compile_graph
from .prompts import Kind
from .runner import ProviderFactory, Runner

REPO_ROOT = Path(__file__).resolve().parents[3]


class ExperimentIn(BaseModel):
    name: str = ""
    graph: Graph


class PromptIn(BaseModel):
    kind: Kind
    name: str
    text: str
    note: str = ""
    base: str | None = None


class PullIn(BaseModel):
    name: str


# Free models worth trying, with their approximate download size (default 4-bit quantisation).
# With 16 GB of GPU memory, models up to ~14 GB run fully on the GPU; larger ones spill to the
# CPU and get much slower. Any other model from ollama.com/library can be pulled by name.
CATALOG = [  # sizes checked against registry.ollama.ai on 2026-11-26
    {"name": "qwen3:4b", "gb": 2.5, "note": "small and fast; a floor to compare against"},
    {"name": "llama3.1:8b", "gb": 4.9, "note": "widely used baseline"},
    {"name": "granite3.3:8b", "gb": 4.9, "note": "IBM, tuned for structured output"},
    {"name": "qwen3:8b", "gb": 5.2, "note": "current default"},
    {"name": "qwen3.5:9b", "gb": 6.6, "note": "newer Qwen generation, same size class"},
    {"name": "gemma4:12b", "gb": 8.0, "note": "Google, newest Gemma"},
    {"name": "gemma3:12b", "gb": 8.2, "note": "Google, previous Gemma"},
    {"name": "olmo2:13b", "gb": 8.4, "note": "fully open training data (citable in papers)"},
    {"name": "deepseek-r1:14b", "gb": 9.0, "note": "reasoning model; slow, thinks before answering"},
    {"name": "phi4:14b", "gb": 9.1, "note": "Microsoft, good at reasoning over text"},
    {"name": "qwen3:14b", "gb": 9.3, "note": "next step up from the default"},
    {"name": "mistral-small3.2:24b", "gb": 15.2, "note": "just fits 16 GB; slower"},
    {"name": "gemma3:27b", "gb": 17.4, "note": "spills past 16 GB; slow"},
    {"name": "qwen3.5:27b", "gb": 17.5, "note": "spills past 16 GB; slow"},
    {"name": "qwen3:30b", "gb": 18.6, "note": "mixture of experts: fast for its size, spills past 16 GB"},
]
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*(:[A-Za-z0-9._-]+)?")


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
    pulls: dict[str, dict] = {}  # model name -> download status, for the Models tab

    def installed() -> list[dict]:
        try:
            return httpx.get(f"{ollama_host()}/api/tags", timeout=8).json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return []

    def pull(name: str) -> None:
        state = pulls[name]
        try:
            with httpx.stream("POST", f"{ollama_host()}/api/pull", json={"model": name, "stream": True},
                              timeout=httpx.Timeout(30, read=600)) as r:
                for line in r.iter_lines():
                    if not line:
                        continue
                    msg = httpx.Response(200, content=line).json()
                    if msg.get("error"):
                        raise RuntimeError(msg["error"])
                    state["status"] = msg.get("status", state["status"])
                    if msg.get("total"):
                        state["completed"], state["total"] = msg.get("completed", 0), msg["total"]
            state["status"] = "done"
        except Exception as e:  # network, unknown model, disk full: show it in the UI
            state["status"], state["error"] = "failed", str(e) or type(e).__name__

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
        for m in sorted(installed(), key=lambda m: m.get("size", 0)):
            details = m.get("details") or {}
            out.append({"spec": f"ollama:{m['name']}", "name": m["name"], "free": True,
                        "size_gb": round(m.get("size", 0) / 1e9, 1),
                        "params": details.get("parameter_size"), "quant": details.get("quantization_level")})
        if allow_paid:
            for name in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
                out.append({"spec": f"anthropic:{name}", "name": name, "free": False})
        return out

    @app.get("/api/models/catalog")
    def catalog():
        have = {m["name"] for m in installed()}
        have |= {n.removesuffix(":latest") for n in have}
        return [c | {"installed": c["name"] in have, "pull": pulls.get(c["name"])} for c in CATALOG] + [
            {"name": n, "gb": None, "note": "", "installed": n in have, "pull": st}
            for n, st in pulls.items() if n not in {c["name"] for c in CATALOG}]

    @app.post("/api/models/pull")
    def start_pull(body: PullIn):
        name = body.name.strip()
        if not MODEL_NAME.fullmatch(name):
            raise HTTPException(400, f"'{name}' is not a model name like qwen3:14b")
        if pulls.get(name, {}).get("status") not in (None, "done", "failed"):
            return pulls[name]
        pulls[name] = {"name": name, "status": "starting", "completed": 0, "total": 0, "error": None}
        threading.Thread(target=pull, args=(name,), daemon=True, name=f"pull-{name}").start()
        return pulls[name]

    @app.get("/api/prompts")
    def prompts():
        return [p.model_dump() for p in runner.prompts.all().values()]

    @app.post("/api/prompts")
    def create_prompt(body: PromptIn):
        try:
            return runner.prompts.create(body.kind, body.name, body.text, body.note, body.base).model_dump()
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/prompts/{prompt_id}")
    def delete_prompt(prompt_id: str):
        try:
            runner.prompts.delete(prompt_id)
            return {"deleted": prompt_id}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except KeyError:
            raise HTTPException(404, "no such prompt")

    @app.post("/api/compile")
    def compile_(graph: Graph):
        result = compile_graph(graph, allow_paid, runner.prompts.all())
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
