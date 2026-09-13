from __future__ import annotations

import time
from types import SimpleNamespace

from zhihu_cli import sessions


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "帮我看看热榜"},
        {"role": "assistant", "content": "好的"},
    ]
    sessions.save_session("20260101-120000", messages, model="deepseek-v4-flash")
    session_id, loaded = sessions.load_session("20260101-120000")
    assert session_id == "20260101-120000"
    assert loaded[1]["content"] == "帮我看看热榜"
    assert len(loaded) == 3


def test_latest_and_list_order(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    sessions.save_session("a", [{"role": "user", "content": "第一个会话"}], model="m")
    time.sleep(0.02)
    sessions.save_session("b", [{"role": "user", "content": "第二个会话"}], model="m")

    session_id, _ = sessions.load_session(None)
    assert session_id == "b"
    assert [row.id for row in sessions.list_sessions()] == ["b", "a"]


def test_title_from_first_user_message(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    sessions.save_session("t", [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "导出收藏夹里的所有回答到本地"},
    ])
    row = sessions.list_sessions()[0]
    assert "导出收藏夹" in row.title


def test_load_missing_session_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    from zhihu_cli.exceptions import ZhihuError

    try:
        sessions.load_session(None)
    except ZhihuError as exc:
        assert "没有可恢复的会话" in str(exc)
    else:
        raise AssertionError("expected ZhihuError")


def test_agent_persists_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    from zhihu_cli.commands.chat import ChatAgent

    class FakeLLM:
        config = SimpleNamespace(model="m")

        def chat(self, messages, tools=None):
            return {"role": "assistant", "content": "好的"}

    class FakeClient:
        pass

    agent = ChatAgent(FakeClient(), llm=FakeLLM(), session_id="s1")
    agent.send("你好")
    assert any(row.id == "s1" for row in sessions.list_sessions())
