"""End-to-end tests against the real Zhihu API.

These are skipped by default (see ``addopts = -m 'not integration'`` in
``pyproject.toml``).  To run them you need a saved login:

    zhihu login
    uv run pytest -m integration

They deliberately use generous delays to stay low-frequency.
"""

from __future__ import annotations

import pytest

from wzlcarrot_cli.client import ZhihuClient
from wzlcarrot_cli.exceptions import ZhihuError
from wzlcarrot_cli.session import Credentials

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


def test_search_returns_results():
    params = {
        "t": "general",
        "q": "Python",
        "correction": 1,
        "offset": 0,
        "limit": 5,
        "lc_idx": 0,
        "show_all_topics": 0,
        "search_hash_id": "",
        "vertical_info": "0,0,0,0,0,0,0,0,0,0",
    }
    with _client() as client:
        data = client.request("GET", "/api/v4/search_v3", params=params)
    assert data.get("data")


def test_question_answers_returns_items():
    with _client() as client:
        answers = client.get(
            "/api/v4/questions/2082159487167587181/answers",
            include="data[*].excerpt", limit=3, offset=0,
        ).get("data", [])
    assert answers
    assert answers[0].get("id")


def test_own_user_profile():
    with _client() as client:
        me = client.me()
        profile = client.get(f"/api/v4/members/{me['url_token']}")
    assert profile.get("url_token") == me["url_token"]


def test_recommend_feed_returns_items():
    with _client() as client:
        data = client.recommend_feed(limit=5)
    assert data.get("data")


def test_own_followers_endpoint():
    with _client() as client:
        me = client.me()
        data = client.followers(me["url_token"], limit=1, offset=0)
    assert isinstance(data.get("data"), list)


def test_notifications_endpoint():
    with _client() as client:
        data = client.notifications(limit=5)
    assert isinstance(data, dict)


def test_favlists_endpoint():
    with _client() as client:
        data = client.favlists(limit=5)
    assert isinstance(data, dict)
