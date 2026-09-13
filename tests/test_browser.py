from __future__ import annotations

import httpx
import pytest

from wzlcarrot_cli import browser
from wzlcarrot_cli.client import ZhihuClient
from wzlcarrot_cli.exceptions import SignatureError
from wzlcarrot_cli.session import Credentials


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    return tmp_path


def test_is_enabled_reads_env(monkeypatch):
    monkeypatch.delenv(browser.ENABLE_ENV, raising=False)
    assert browser.is_enabled() is False
    monkeypatch.setenv(browser.ENABLE_ENV, "1")
    assert browser.is_enabled() is True
    monkeypatch.setenv(browser.ENABLE_ENV, "0")
    assert browser.is_enabled() is False


def test_make_fallback_none_when_disabled(monkeypatch):
    monkeypatch.delenv(browser.ENABLE_ENV, raising=False)
    assert browser.make_fallback("d_c0=a; z_c0=b") is None


def _client(fallback):
    creds = Credentials(cookies={"d_c0": "a", "z_c0": "b"})
    client = ZhihuClient(
        creds, min_delay=0, max_delay=0, min_gap=0, write_min_delay=0,
        signature_fallback=fallback,
    )
    client._http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403, json={"error": {"code": 100, "message": "请求参数异常"}}
            )
        )
    )
    return client


def test_get_uses_browser_fallback_on_signature_error(home):
    calls = []

    def fallback(url):
        calls.append(url)
        return {"ok": True, "url": url}

    with _client(fallback) as client:
        result = client.get("/api/v4/me")
    assert result["ok"] is True
    assert calls == ["https://www.zhihu.com/api/v4/me"]


def test_post_does_not_use_fallback(home):
    calls = []

    def fallback(url):
        calls.append(url)
        return {"ok": True}

    with _client(fallback) as client, pytest.raises(SignatureError):
        client.post("/api/v4/answers/1/voters", {"type": "up"})
    assert calls == []  # writes never go through the browser fallback


def test_fallback_returning_none_preserves_error(home):
    with _client(lambda url: None) as client, pytest.raises(SignatureError):
        client.get("/api/v4/me")
