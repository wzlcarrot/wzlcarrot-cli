from __future__ import annotations

import threading

import httpx
import pytest

from wzlcarrot_cli.commands.chat import ChatAgent
from wzlcarrot_cli.llm import LLMClient, LLMConfig

SSE = (
    b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
    b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
    b"data: [DONE]\n\n"
)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    return tmp_path


def _llm() -> LLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=SSE, headers={"content-type": "text/event-stream"}
        )

    client = LLMClient(LLMConfig(api_key="k", base_url="http://test"))
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_chat_stream_done_without_cancel():
    with _llm() as llm:
        events = list(llm.chat_stream([{"role": "user", "content": "hi"}]))
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["content"] == "hello world"


def test_chat_stream_cancel_mid_stream():
    cancel = threading.Event()
    with _llm() as llm:
        it = llm.chat_stream([{"role": "user", "content": "hi"}], cancel_event=cancel)
        first = next(it)
        assert first == {"type": "delta", "text": "hello"}
        cancel.set()
        rest = list(it)
    assert rest[-1] == {"type": "cancelled"}
    assert all(event["type"] != "done" for event in rest)


class _StubLLM:
    """LLM double that would happily finish a full round."""

    def __init__(self) -> None:
        self.calls = 0

    def chat_stream(self, messages, tools=None, cancel_event=None):
        self.calls += 1
        yield {"type": "delta", "text": "partial"}
        yield {"type": "done", "message": {"role": "assistant", "content": "full"}}

    def chat(self, messages, tools=None):
        return {"role": "assistant", "content": "full"}


def test_agent_send_stream_completes_without_cancel(home):
    agent = ChatAgent(object(), _StubLLM())
    events = list(agent.send_stream("hi"))
    assert events[-1] == ("done", "full")


def test_agent_send_stream_cancelled_before_start(home):
    agent = ChatAgent(object(), _StubLLM())
    cancel = threading.Event()
    cancel.set()
    events = list(agent.send_stream("hi", cancel_event=cancel))
    assert events == [("cancelled",)]
    assert agent.llm.calls == 0  # never reached the model
    assert agent.messages[-1]["role"] == "user"  # no partial message appended
