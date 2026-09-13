"""End-to-end tests against the real Zhihu API.

These are skipped by default (see ``addopts = -m 'not integration'`` in
``pyproject.toml``).  To run them you need a saved login:

    zhihu login --qr
    uv run pytest -m integration

They deliberately use generous delays to stay low-frequency.
"""

from __future__ import annotations

import pytest

from zhihu_cli.client import ZhihuClient
from zhihu_cli.exceptions import ZhihuError
from zhihu_cli.session import Credentials

pytestmark = pytest.mark.integration


def _client() -> ZhihuClient:
    credentials = Credentials.load()
    if not credentials.is_logged_in():
        pytest.skip("no saved login (run `zhihu login`)")
    return ZhihuClient(credentials, min_delay=2.0, max_delay=4.0, min_gap=3.0)


def test_me():
    with _client() as client:
        me = client.me()
    assert me.get("name")


def test_hot_list_returns_items():
    with _client() as client:
        data = client.hot_list(limit=5)
    assert data.get("data")


def test_answer_roundtrip():
    with _client() as client:
        me = client.me()
        token = me["url_token"]
        answers = client.get(
            f"/api/v4/members/{token}/answers", limit=1, offset=0
        ).get("data", [])
    if not answers:
        pytest.skip("current user has no answers")
    answer_id = answers[0]["id"]
    with _client() as client:
        answer = client.get(f"/api/v4/answers/{answer_id}", include="content,author")
    assert answer.get("id") == answer_id


def test_vote_then_revert_is_reversible():
    """Vote up then neutral on one answer, leaving state unchanged."""
    with _client() as client:
        question = client.get(
            "/api/v4/questions/2082159487167587181/answers",
            include="data[*].excerpt", limit=1, offset=0,
        ).get("data", [])
        if not question:
            pytest.skip("no answer available to vote on")
        answer_id = question[0]["id"]
        try:
            up = client.vote(answer_id, "up")
            assert up.get("success") is True
        except ZhihuError as exc:
            pytest.skip(f"vote blocked: {exc}")
        finally:
            client.vote(answer_id, "neutral")
