from __future__ import annotations

from wzlcarrot_cli import compaction as cp
from wzlcarrot_cli.commands.chat import ChatAgent


class FakeLLM:
    def __init__(self, reply: str = "这是摘要") -> None:
        self.reply = reply
        self.calls: list = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return {"role": "assistant", "content": self.reply}


def _conversation(turns: int = 10) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": "系统提示"}]
    for i in range(turns):
        messages.append({"role": "user", "content": f"问题{i} " * 40})
        messages.append({"role": "assistant", "content": f"回答{i} " * 40})
    return messages


def test_estimate_tokens():
    assert cp.estimate_tokens("") == 0
    assert cp.estimate_tokens("abcd") >= 1
    assert cp.estimate_tokens("a" * 400) > cp.estimate_tokens("a" * 40)


def test_count_messages_tokens_includes_tool_calls():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "hot", "arguments": '{"limit": 5}'}}
        ]}
    ]
    assert cp.count_messages_tokens(messages) > 0


def test_microcompact_truncates_old_tool_results_only():
    messages = [
        {"role": "tool", "tool_call_id": str(i), "content": "x" * 1000} for i in range(6)
    ]
    result, saved = cp.microcompact(messages, keep_recent_tools=2)
    assert saved > 0
    assert result[0]["content"].endswith("[旧工具结果已压缩]")
    assert result[-1]["content"] == "x" * 1000


def test_compact_reduces_and_keeps_recent():
    messages = _conversation(10)
    llm = FakeLLM("要点摘要")
    new, info = cp.compact(messages, llm, keep_recent=4)
    assert info["compacted"] is True
    assert len(new) < len(messages)
    summaries = [m for m in new if m.get("_compact_summary")]
    assert len(summaries) == 1
    assert "要点摘要" in summaries[0]["content"]
    # the very last messages are preserved
    assert new[-1]["content"] == messages[-1]["content"]
    # system prompt kept first
    assert new[0]["role"] == "system" and not new[0].get("_compact_summary")


def test_compact_twice_keeps_single_summary():
    messages = _conversation(10)
    llm = FakeLLM("摘要A")
    once, _ = cp.compact(messages, llm, keep_recent=4)
    once.append({"role": "user", "content": "新问题" * 40})
    once.append({"role": "assistant", "content": "新回答" * 40})
    twice, info = cp.compact(once, FakeLLM("摘要B"), keep_recent=4)
    assert info["compacted"] is True
    assert len([m for m in twice if m.get("_compact_summary")]) == 1


def test_compact_too_few_messages():
    _new, info = cp.compact([{"role": "system", "content": "s"}], FakeLLM())
    assert info["compacted"] is False


class FakeClient:
    pass


def test_agent_auto_compacts_over_threshold():
    agent = ChatAgent(FakeClient(), llm=FakeLLM("自动摘要"), max_tokens=10, keep_recent=2)
    # pad the history past the tiny budget
    agent.messages = _conversation(10)
    info = agent._maybe_compact()
    assert info is not None and info["compacted"] is True
    assert any(m.get("_compact_summary") for m in agent.messages)
