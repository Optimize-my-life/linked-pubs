import httpx
import pytest

from linked_pubs.llm import LLMError, make_provider
from linked_pubs.models import VerifierOutput


def _fake_post(response):
    sent = {}

    def post(url, json, timeout):
        sent.update(url=url, json=json)
        return httpx.Response(200, json=response, request=httpx.Request("POST", url))
    return post, sent


def test_ollama_sets_context_thinking_and_schema_hint(monkeypatch):
    post, sent = _fake_post({"message": {"content": '{"explanation": "x", "label": "SUPPORT", "evidence_ids": [0]}'},
                             "done_reason": "stop", "prompt_eval_count": 100})
    monkeypatch.setattr(httpx, "post", post)
    out = make_provider("ollama:qwen3:8b").generate("sys", "user", VerifierOutput)
    assert out.label.value == "SUPPORT"
    assert sent["url"].endswith("/api/chat")
    assert sent["json"]["think"] is False and sent["json"]["options"]["num_ctx"] == 16384
    assert '"evidence_ids"' in sent["json"]["messages"][0]["content"]


def test_ollama_flags_truncated_prompt(monkeypatch):
    post, _ = _fake_post({"message": {"content": "{}"}, "done_reason": "stop", "prompt_eval_count": 16384})
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(LLMError, match="context window"):
        make_provider("ollama:qwen3:8b").generate("sys", "user", VerifierOutput)


@pytest.mark.parametrize("env,expected", [
    (None, "http://127.0.0.1:11434"),
    ("0.0.0.0", "http://127.0.0.1:11434"),
    ("localhost:11434", "http://127.0.0.1:11434"),
    ("http://gpu-box:11500", "http://gpu-box:11500"),
    ("0.0.0.0:11500", "http://127.0.0.1:11500"),
])
def test_ollama_base_url_normalises_listen_addresses(monkeypatch, env, expected):
    from linked_pubs.llm import ollama_base_url
    if env is None:
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_HOST", env)
    assert ollama_base_url() == expected
