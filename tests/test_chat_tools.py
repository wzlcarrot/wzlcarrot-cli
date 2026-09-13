"""Tests for the agent's compose_publish tool (no network, no real editor)."""

from __future__ import annotations

from wzlcarrot_cli.commands.chat import ChatAgent
from wzlcarrot_cli.composer import ASK_TEMPLATE


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    @staticmethod
    def _build_img_html(infos):
        return "".join(f'<img src="{i["src"]}"/>' for i in infos)

    def create_pin(self, title, content, image_infos=None):
        self.calls.append(("pin", title, content))
        return {"id": "pin-1"}

    def create_article(self, title, content, topic_ids=None, image_infos=None):
        self.calls.append(("article", title, content))
        return {"id": "article-1"}

    def create_question(self, title, detail="", topic_ids=None, image_infos=None):
        self.calls.append(("question", title, detail))
        return {"id": "question-1"}

    def post(self, path, json_body=None, **params):
        self.calls.append(("post", path, json_body))
        return {"ok": True}


def make_agent(client, compose):
    return ChatAgent(client, llm=object(), compose=compose)


def test_compose_publish_pin_splits_title_and_body():
    client = FakeClient()
    agent = make_agent(client, lambda tpl: "# 我的标题\n\n这是正文 **加粗**")
    result = agent._compose_publish("pin")
    assert result == {"id": "pin-1"}
    kind, title, content = client.calls[0]
    assert kind == "pin"
    assert title == "我的标题"
    assert "这是正文" in content
    assert "<strong>加粗</strong>" in content


def test_compose_publish_article():
    client = FakeClient()
    agent = make_agent(client, lambda tpl: "# 文章标题\n\n段落一")
    agent._compose_publish("article")
    assert client.calls[0][0] == "article"
    assert client.calls[0][1] == "文章标题"


def test_compose_publish_answer_posts_to_question():
    client = FakeClient()
    agent = make_agent(client, lambda tpl: "我的回答正文")
    agent._compose_publish("answer", question_id=123)
    assert client.calls[0][0] == "post"
    assert client.calls[0][1] == "/api/v4/questions/123/answers"
    assert client.calls[0][2]["resume"] is False


def test_compose_publish_cancelled_when_template_untouched():
    client = FakeClient()
    agent = make_agent(client, lambda tpl: tpl)  # user changed nothing
    result = agent._compose_publish("pin")
    assert result.get("cancelled") is True
    assert client.calls == []


def test_compose_publish_cancelled_when_empty():
    client = FakeClient()
    agent = make_agent(client, lambda tpl: "   \n")
    result = agent._compose_publish("article")
    assert result.get("cancelled") is True
    assert client.calls == []


def test_compose_uses_ask_template_for_rich_targets():
    seen = {}

    def compose(template):
        seen["template"] = template
        return "# T\n\nB"

    agent = make_agent(FakeClient(), compose)
    agent._compose_publish("question")
    assert seen["template"] == ASK_TEMPLATE


def test_agent_stats_reports_usage():
    class LLM:
        config = None

        def __init__(self):
            self.usage = {
                "requests": 2,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }

    agent = ChatAgent(FakeClient(), llm=LLM())
    stats = agent.stats()
    assert stats["requests"] == 2
    assert stats["total_tokens"] == 120
    assert "context_tokens" in stats


def test_llm_client_records_usage_offline():
    from wzlcarrot_cli.llm import LLMClient, LLMConfig

    client = LLMClient(LLMConfig(api_key="x"))
    try:
        client._record_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        client._record_usage({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        assert client.usage == {
            "prompt_tokens": 11,
            "completion_tokens": 6,
            "total_tokens": 17,
            "requests": 2,
        }
    finally:
        client.close()


def test_plan_mode_blocks_write_tools_but_allows_reads():
    agent = ChatAgent(FakeClient(), llm=object(), plan_mode=True)
    denied = agent._dispatch("vote", {"answer_id": 1, "direction": "up"})
    assert denied["denied"] is True
    # internal planning tool still allowed
    allowed = agent._dispatch("todo_write", {"todos": [{"content": "规划", "status": "pending"}]})
    assert "denied" not in allowed
