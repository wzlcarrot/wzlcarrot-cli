from __future__ import annotations

import json

from typer.testing import CliRunner

from wzlcarrot_cli.cli import app
from wzlcarrot_cli.llm import resolve_llm_config, save_llm_config
from wzlcarrot_cli.providers import PROVIDERS, get_provider

runner = CliRunner()


def test_provider_registry_has_common_models():
    ids = {p.id for p in PROVIDERS}
    assert {"deepseek", "openai", "zhipu", "moonshot", "qwen", "custom"} <= ids
    assert get_provider("deepseek").base_url == "https://api.deepseek.com/v1"
    assert get_provider("nope") is None


def test_save_llm_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    for key in ("ZHIHU_CLI_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    save_llm_config("sk-test", "https://api.example.com/v1", "model-x")
    config = resolve_llm_config()
    assert config.api_key == "sk-test"
    assert config.model == "model-x"


def test_connect_noninteractive_writes_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    result = runner.invoke(
        app,
        ["connect", "--provider", "deepseek", "--api-key", "sk-x", "--model", "deepseek-chat"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / "llm.json").read_text(encoding="utf-8"))
    assert data["base_url"] == "https://api.deepseek.com/v1"
    assert data["model"] == "deepseek-chat"


def test_connect_list():
    result = runner.invoke(app, ["connect", "--list"])
    assert result.exit_code == 0
    assert "deepseek" in result.output
    assert "openai" in result.output
