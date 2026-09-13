from __future__ import annotations

import textwrap

from zhihu_cli import plugins
from zhihu_cli.commands.chat import ChatAgent
from zhihu_cli.plugins import ToolDef


def test_plugin_api_collects_contributions():
    api = plugins.PluginAPI()
    api.command("x", lambda: None)
    api.tool("t", "d", {"type": "object", "properties": {}}, lambda client: {})
    api.prompt_section("style", "be brief", priority=3)
    assert "x" in api.commands
    assert api.tools["t"].spec()["function"]["name"] == "t"
    assert api.prompts == [(3, "be brief")]


def test_build_prompt_sections_order():
    from zhihu_cli.prompt import build_prompt_sections

    out = build_prompt_sections("BASE", "MEM", [(10, "P10"), (0, "P0")])
    assert out.index("BASE") < out.index("MEM") < out.index("P0") < out.index("P10")


def test_load_local_plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "demo.py").write_text(
        textwrap.dedent(
            """
            def register(api):
                api.command("demo", lambda: None)
                api.tool(
                    "demo_tool", "d",
                    {"type": "object", "properties": {}},
                    lambda client: {"ok": True},
                )
            """
        ),
        encoding="utf-8",
    )
    api = plugins.load_plugins()
    assert "demo" in api.commands
    assert "demo_tool" in api.tools
    assert any(info.name == "demo" for info in api.plugins)


def test_bad_plugin_does_not_break_good_one(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "bad.py").write_text(
        "def register(api):\n    raise RuntimeError('boom')\n", encoding="utf-8"
    )
    (plugin_dir / "good.py").write_text(
        "def register(api):\n    api.command('good', lambda: None)\n", encoding="utf-8"
    )
    api = plugins.load_plugins()
    assert "good" in api.commands


def test_env_disables_plugins(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    monkeypatch.setenv("ZHIHU_CLI_NO_PLUGINS", "1")
    api = plugins.load_plugins()
    assert api.commands == {}
    assert api.plugins == []


class FakeClient:
    pass


def test_agent_dispatches_plugin_tool():
    def handler(client, text):
        assert isinstance(client, FakeClient)
        return {"echo": text}

    tool = ToolDef(
        "echo",
        "d",
        {"type": "object", "properties": {"text": {"type": "string"}}},
        handler,
    )

    class FakeLLM:
        config = None

    agent = ChatAgent(FakeClient(), llm=FakeLLM(), plugin_tools={"echo": tool})
    assert any(spec["function"]["name"] == "echo" for spec in agent._all_tools())
    assert agent._dispatch("echo", {"text": "hi"}) == {"echo": "hi"}
