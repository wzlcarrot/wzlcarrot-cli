from __future__ import annotations

from zhihu_cli import todo
from zhihu_cli.commands.chat import ChatAgent


def test_normalize_filters_and_coerces():
    items = todo.normalize([
        {"content": "第一步", "status": "completed"},
        {"content": "  ", "status": "pending"},  # dropped: empty content
        {"content": "第二步", "status": "weird"},  # coerced to pending
        "not-a-dict",  # dropped
    ])
    assert items == [
        {"content": "第一步", "status": "completed"},
        {"content": "第二步", "status": "pending"},
    ]


def test_render_plain_icons():
    text = todo.render_plain([
        {"content": "A", "status": "completed"},
        {"content": "B", "status": "in_progress"},
        {"content": "C", "status": "pending"},
    ])
    assert "☑ A" in text
    assert "◐ B" in text
    assert "☐ C" in text


class FakeClient:
    pass


class FakeLLM:
    config = None


def test_agent_todo_write_tool():
    agent = ChatAgent(FakeClient(), llm=FakeLLM())
    result = agent._dispatch("todo_write", {
        "todos": [{"content": "看热榜", "status": "in_progress"}]
    })
    assert agent.todos == [{"content": "看热榜", "status": "in_progress"}]
    assert "看热榜" in result["rendered"]
