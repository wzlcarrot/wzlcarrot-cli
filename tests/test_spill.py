from __future__ import annotations

import pytest

from wzlcarrot_cli import spill
from wzlcarrot_cli.commands.chat import ChatAgent
from wzlcarrot_cli.exceptions import ZhihuError


@pytest.fixture()
def spill_home(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    return tmp_path


def test_save_and_read_roundtrip(spill_home):
    ref = spill.save_text("s1", "hot", "call-1", "result", "hello world")
    assert ref.bytes == len(b"hello world")
    assert spill.read_spill(ref.locator) == "hello world"
    assert spill.read_spill(ref.locator, offset=6, limit=5) == "world"
    assert spill.read_spill(ref.locator, offset=6, limit=0) == "world"


def test_spill_file_is_private_and_unique(spill_home):
    ref1 = spill.save_text("s1", "hot", "c", "result", "a")
    ref2 = spill.save_text("s1", "hot", "c", "result", "a")
    assert ref1.locator != ref2.locator  # exclusive creation, no collisions


def test_read_spill_rejects_outside_root(spill_home):
    outside = spill_home / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ZhihuError):
        spill.read_spill(str(outside))


def test_preview_truncates_middle():
    text = "A" * 3000 + "B" * 3000
    out = spill.preview(text, head=100, tail=100)
    assert out.startswith("A" * 100)
    assert out.endswith("B" * 100)
    assert "省略" in out


class FakeClient:
    pass


class FakeLLM:
    config = None


def _agent(**kwargs):
    return ChatAgent(FakeClient(), llm=FakeLLM(), **kwargs)


def test_small_tool_result_inline(spill_home):
    agent = _agent()
    content = agent._tool_content({"ok": True}, "me", None)
    # Tool results are wrapped as untrusted data (prompt-injection containment).
    assert '{"ok": true}' in content
    assert content.startswith("<zhihu_untrusted_content>")
    assert content.endswith("</zhihu_untrusted_content>")


def test_large_tool_result_spills_and_reads_back(spill_home):
    agent = _agent(max_inline_chars=50)
    content = agent._tool_content({"big": "x" * 500}, "hot", "call-9")
    assert "溢出" in content
    assert "read_spill" in content

    files = spill.list_spills()
    assert len(files) == 1
    read = agent._read_spill(str(files[0]), offset=0, limit=100000)
    assert read["content"].startswith('{"big"')
