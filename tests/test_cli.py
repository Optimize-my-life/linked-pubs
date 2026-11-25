import pytest

from linked_pubs.cli import DEFAULT_LLM, _provider, main


def test_default_model_is_local():
    assert DEFAULT_LLM.startswith("ollama:")


def test_paid_provider_needs_allow_paid():
    with pytest.raises(SystemExit, match="--allow-paid"):
        _provider("anthropic:claude-opus-5-5", "high")


def test_cli_refuses_paid_model_without_flag(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("x")
    with pytest.raises(SystemExit, match="paid API"):
        main(["extract", str(f), "--llm", "anthropic:claude-opus-5-5"])
