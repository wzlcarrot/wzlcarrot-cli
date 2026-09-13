from __future__ import annotations

import json

from wzlcarrot_cli import hooks
from wzlcarrot_cli.commands.chat import ChatAgent
from wzlcarrot_cli.hooks import POST_EXECUTE, PRE_EXECUTE, HookRegistry, HookResult


def test_matches():
    assert hooks.matches("*", "vote")
    assert hooks.matches("vote", "vote")
    assert hooks.matches("delete_*", "delete_content")
    assert not hooks.matches("vote", "hot")


def test_pre_deny_short_circuits():
    registry = HookRegistry()
    registry.add(PRE_EXECUTE, lambda n, a: HookResult(decision="deny", reason="no"), "v*")
    out = registry.run_pre("vote", {})
    assert out is not None and out.decision == "deny"
    assert out.reason == "no"


def test_pre_transforms_args():
    registry = HookRegistry()
    registry.add(PRE_EXECUTE, lambda n, a: HookResult(args={**a, "x": 2}), "*")
    out = registry.run_pre("hot", {"x": 1})
    assert out is not None and out.args == {"x": 2}


def test_pre_ask_decision():
    registry = HookRegistry()
    registry.add(PRE_EXECUTE, lambda n, a: HookResult(decision="ask", reason="careful"), "*")
    out = registry.run_pre("delete_content", {})
    assert out is not None and out.decision == "ask"


def test_post_replaces_and_annotates():
    registry = HookRegistry()
    registry.add(POST_EXECUTE, lambda n, a, r: HookResult(context="note"), "*")
    out = registry.run_post("hot", {}, {"ok": True})
    assert out["ok"] is True
    assert out["_hook_context"] == "note"


def test_bad_hook_is_contained():
    registry = HookRegistry()

    def boom(n, a):
        raise RuntimeError("x")

    registry.add(PRE_EXECUTE, boom, "*")
    assert registry.run_pre("hot", {}) is None  # did not raise


def test_load_rules_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    (tmp_path / "hooks.json").write_text(
        json.dumps({
            "hooks": [
                {"event": "pre_execute", "tools": ["delete_content"], "action": "ask"},
                {
                    "event": "pre_execute",
                    "tools": ["vote"],
                    "field": "direction",
                    "pattern": "^down$",
                    "action": "deny",
                    "message": "no down",
                },
            ]
        }),
        encoding="utf-8",
    )
    registry = hooks.load_hooks()
    assert registry.run_pre("delete_content", {}).decision == "ask"
    denied = registry.run_pre("vote", {"direction": "down"})
    assert denied is not None and denied.decision == "deny"
    assert registry.run_pre("vote", {"direction": "up"}) is None


class FakeClient:
    pass


class FakeLLM:
    config = None


def test_agent_dispatch_honors_deny_hook():
    registry = HookRegistry()
    registry.add(PRE_EXECUTE, lambda n, a: HookResult(decision="deny", reason="blocked"), "hot")
    agent = ChatAgent(FakeClient(), llm=FakeLLM(), hooks=registry)
    out = agent._dispatch("hot", {"limit": 3})
    assert out["denied"] is True
    assert out["message"] == "blocked"


def test_agent_dispatch_applies_post_hook():
    registry = HookRegistry()
    registry.add(POST_EXECUTE, lambda n, a, r: HookResult(context="post"), "me")

    class Client:
        def get(self, *a, **k):
            return {"name": "tester"}

    from wzlcarrot_cli.platforms.zhihu_tools import build_tools

    client = Client()
    agent = ChatAgent(client, llm=FakeLLM(), hooks=registry, tools=build_tools(client))
    out = agent._dispatch("me", {})
    assert out["name"] == "tester"
    assert out["_hook_context"] == "post"
