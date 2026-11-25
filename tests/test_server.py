import io
import time

from conftest import FakeProvider
from fastapi.testclient import TestClient
from test_scifact_eval import _fake_extract, _fake_verify, _write_fixture

from linked_pubs.models import ExtractionOutput, Label, VerifierOutput
from linked_pubs.server.app import create_app
from linked_pubs.server.graph import Graph, compile_graph


def _graph(*chains, data=None):
    """Build a graph from chains like [('d', 'dataset'), ('v', 'verifier'), ('m', 'metrics')]."""
    nodes, edges = {}, []
    for chain in chains:
        for (a, ta), (b, tb) in zip(chain, chain[1:]):
            edges.append({"source": a, "target": b})
        for nid, t in chain:
            nodes[nid] = {"id": nid, "type": t, "data": (data or {}).get(nid, {})}
    return Graph(nodes=list(nodes.values()), edges=edges)


BASELINE = [
    [("d", "dataset"), ("v", "verifier"), ("m", "metrics")],
    [("d", "dataset"), ("x", "extractor"), ("v", "verifier"), ("m", "metrics")],
]
MODELS = {"d": {"split": "dev", "limit": 1}, "x": {"model": "ollama:fake"}, "v": {"model": "ollama:fake"}}


def test_compile_baseline_gives_abstract_and_statements_arms():
    r = compile_graph(_graph(*BASELINE, data=MODELS))
    assert r.errors == []
    assert [(a.mode, a.extractor, a.verifier) for a in r.arms] == [
        ("abstract", None, "ollama:fake"), ("statements", "ollama:fake", "ollama:fake")]


def test_compile_reports_problems():
    r = compile_graph(_graph([("d", "dataset"), ("m", "metrics")], [("v", "verifier"), ("m", "metrics")]))
    assert any("unsupported chain" in e for e in r.errors)
    assert any("verifier block is not on a path" in e for e in r.errors)
    r = compile_graph(_graph(*BASELINE, data={"d": {"split": "test"}}))
    assert any("no public labels" in e for e in r.errors)
    r = compile_graph(_graph(BASELINE[0], data={"v": {"model": "anthropic:claude-opus-5-5"}}))
    assert any("paid API" in e for e in r.errors)
    r = compile_graph(_graph(BASELINE[0]))
    assert any("no model selected" in e for e in r.errors)


def _fake_factory(spec):
    return FakeProvider(lambda s, u, schema: (_fake_extract if schema is ExtractionOutput else _fake_verify)(s, u, schema))


def _client(tmp_path):
    scifact = tmp_path / "data" / "scifact"
    scifact.mkdir(parents=True)
    _write_fixture(scifact)
    return TestClient(create_app(tmp_path / "data", provider_factory=_fake_factory, web_dir=tmp_path / "noweb",
                                 allow_paid=False))


def _wait(client, exp_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        exp = client.get(f"/api/experiments/{exp_id}").json()
        if exp["status"] not in ("queued", "running"):
            return exp
        time.sleep(0.05)
    raise AssertionError("experiment did not finish")


def test_run_baseline_experiment_through_api(tmp_path):
    client = _client(tmp_path)
    graph = _graph(*BASELINE, data=MODELS).model_dump()
    assert client.post("/api/compile", json=graph).json()["errors"] == []

    exp = client.post("/api/experiments", json={"name": "baseline", "graph": graph}).json()
    exp = _wait(client, exp["id"])
    assert exp["status"] == "done", exp
    by_mode = {r["mode"]: r for r in exp["results"]}
    assert by_mode["abstract"]["summary"]["label"]["accuracy"] == 1.0
    assert by_mode["statements"]["summary"]["extraction"]["grounded_rate"] == 1.0
    assert exp["comparisons"][0]["extraction_loss_macro_f1"] == 0.0
    rows = client.get(f"/api/experiments/{exp['id']}/arms/arm1/rows").json()
    assert {r["pred"] for r in rows["predictions"]} == {"SUPPORT", "NOT_ENOUGH_INFO"}
    assert rows["predictions"][0]["claim"] == "Fibre lowers LDL cholesterol."
    assert client.get(f"/api/experiments/{exp['id']}/arms/arm2/rows").json()["statements"][0]["grounded"] is True
    assert [e["name"] for e in client.get("/api/experiments").json()] == ["baseline"]

    # Timings feed the estimate of the next run: extraction is cached now, verification is timed.
    timings = {r["arm"]: r["timings"] for r in exp["results"]}
    assert timings["arm2"]["extract"]["calls"] == 2 and timings["arm1"]["verify"]["calls"] == 2
    est = {e["arm"]: e for e in client.post("/api/compile", json=graph).json()["estimates"]}
    assert est["arm2"]["extract_calls"] == 0 and est["arm2"]["cached"] == 2
    assert est["arm1"]["verify_calls"] == 2 and est["arm1"]["seconds"] is not None

    # Both arms agree on every pair here, so the comparison lists nothing.
    cmp = client.get(f"/api/experiments/{exp['id']}/compare/arm1/arm2").json()
    assert cmp["counts"]["same"] == 2 and cmp["items"] == []

    board = client.get("/api/leaderboard").json()
    assert {(r["mode"], r["accuracy"]) for r in board} == {("abstract", 1.0), ("statements", 1.0)}


def test_compare_lists_pairs_lost_by_extraction(tmp_path):
    client = _client(tmp_path)

    def verify_abstract_only(s, u, schema):
        # Right on the raw abstract, wrong ("not enough info") on extracted statements.
        if schema is ExtractionOutput:
            return _fake_extract(s, u, schema)
        if "We studied adults." in u:
            return _fake_verify(s, u, schema)
        return VerifierOutput(explanation="statements too vague", label=Label.NEI, evidence_ids=[])

    client.app.state.runner.provider_factory = lambda spec: FakeProvider(verify_abstract_only)
    graph = _graph(*BASELINE, data=MODELS).model_dump()
    exp = _wait(client, client.post("/api/experiments", json={"graph": graph}).json()["id"])
    cmp = client.get(f"/api/experiments/{exp['id']}/compare/arm1/arm2").json()
    assert cmp["counts"]["lost"] == 1
    item = cmp["items"][0]
    assert item["kind"] == "lost" and item["claim"] == "Fibre lowers LDL cholesterol."
    assert item["gold_evidence"] == ["Fibre intake lowered LDL cholesterol."]
    assert item["gold_evidence_quoted"] is True
    assert item["statements"][0]["text"].startswith("Fibre intake lowered")


def test_paid_model_rejected_by_api(tmp_path):
    client = _client(tmp_path)
    graph = _graph(BASELINE[0], data={"d": {}, "v": {"model": "anthropic:claude-opus-5-5"}}).model_dump()
    r = client.post("/api/experiments", json={"graph": graph})
    assert r.status_code == 400 and "paid API" in r.json()["detail"]


def _tiny_pdf(text: str) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    w = PdfWriter()
    page = w.add_blank_page(300, 200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 10 Tf 20 100 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = w._add_object(stream)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_upload_pdf_and_run_extraction_arm(tmp_path):
    client = _client(tmp_path)
    ds = client.post("/api/docsets").json()["id"]
    up = client.post(f"/api/docsets/{ds}/files", files=[
        ("files", ("fibre.pdf", _tiny_pdf("Fibre intake lowered LDL cholesterol in adults."), "application/pdf")),
        ("files", ("notes.docx", b"x", "application/octet-stream")),
    ]).json()
    assert [d["title"] for d in up["documents"]] == ["fibre"]
    assert "only .pdf" in up["errors"][0]

    graph = _graph([("p", "documents"), ("x", "extractor"), ("m", "metrics")],
                   data={"p": {"docset_id": ds}, "x": {"model": "ollama:fake"}}).model_dump()
    exp = _wait(client, client.post("/api/experiments", json={"graph": graph}).json()["id"])
    assert exp["status"] == "done", exp
    assert exp["results"][0]["summary"]["extraction"]["statements"] == 1
    rows = client.get(f"/api/experiments/{exp['id']}/arms/arm1/rows").json()
    assert rows["statements"][0]["grounded"] is True and rows["predictions"] == []


def test_two_extraction_prompts_are_two_arms_with_separate_caches(tmp_path):
    client = _client(tmp_path)
    data = dict(MODELS, x2={"model": "ollama:fake", "prompt": "extract-v2"})
    graph = _graph([("d", "dataset"), ("x", "extractor"), ("v", "verifier"), ("m", "metrics")],
                   [("d", "dataset"), ("x2", "extractor"), ("v", "verifier"), ("m", "metrics")], data=data)
    r = compile_graph(graph)
    assert r.errors == [] and [a.extractor_prompt for a in r.arms] == ["extract-v1", "extract-v2"]
    est = client.post("/api/compile", json=graph.model_dump()).json()["estimates"]
    assert [e["extract_calls"] for e in est] == [2, 2]  # different prompts share no cache
    assert {p["id"] for p in client.get("/api/prompts").json()} >= {"extract-v1", "extract-v2"}
    bad = _graph(BASELINE[1], data=dict(MODELS, x={"model": "ollama:fake", "prompt": "nope"}))
    assert any("unknown prompt" in e for e in compile_graph(bad).errors)
