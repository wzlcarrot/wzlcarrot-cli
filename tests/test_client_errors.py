from __future__ import annotations

import httpx
import pytest

from wzlcarrot_cli.client import ZhihuClient
from wzlcarrot_cli.doctor import run_checks
from wzlcarrot_cli.exceptions import (
    ApiError,
    NotLoggedInError,
    SignatureError,
)
from wzlcarrot_cli.session import Credentials


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    return tmp_path


def _client(handler) -> ZhihuClient:
    creds = Credentials(cookies={"d_c0": "d", "z_c0": "z"})
    client = ZhihuClient(creds, min_delay=0, max_delay=0, min_gap=0)
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        headers={"x-requested-with": "fetch"},
    )
    return client


def test_403_code_100_raises_signature_error(home):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": 100, "message": "请求参数异常"}})

    with _client(handler) as client, pytest.raises(SignatureError):
        client.me()


def test_code_100_on_other_status_is_not_logged_in(home):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 100, "message": "请求参数异常"}})

    with _client(handler) as client, pytest.raises(NotLoggedInError):
        client.me()


def test_zerr_not_login_raises_not_logged_in(home):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "ZERR_NOT_LOGIN", "message": "未登录"}})

    with _client(handler) as client, pytest.raises(NotLoggedInError):
        client.me()


def test_401_raises_not_logged_in(home):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with _client(handler) as client, pytest.raises(NotLoggedInError):
        client.me()


def test_other_error_payload_raises_api_error(home):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 999, "message": "bad request"}})

    with _client(handler) as client, pytest.raises(ApiError):
        client.me()


def test_success_returns_payload(home):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "tester"})

    with _client(handler) as client:
        assert client.me() == {"name": "tester"}


def _patch_client(monkeypatch, *, me_result=None, error=None) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def me(self):
            if error is not None:
                raise error
            return me_result or {}

        def close(self):
            pass

    monkeypatch.setattr("wzlcarrot_cli.client.ZhihuClient", FakeClient)


def test_doctor_signature_ok(home, monkeypatch):
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    _patch_client(monkeypatch, me_result={"name": "tester"})

    labels = {label: (ok, detail) for label, ok, detail in run_checks(check_network=True)}

    assert labels["知乎连通"][0] is True
    assert labels["签名自检"][0] is True


def test_doctor_reports_signature_failure(home, monkeypatch):
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    _patch_client(monkeypatch, error=SignatureError("签名可能已失效（知乎或已更新 x-zse-96 算法）"))

    labels = {label: (ok, detail) for label, ok, detail in run_checks(check_network=True)}

    assert labels["知乎连通"][0] is False
    assert labels["签名自检"][0] is False
    assert "签名" in labels["签名自检"][1]


def test_doctor_signature_unverifiable_when_logged_out(home, monkeypatch):
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    _patch_client(monkeypatch, error=NotLoggedInError("session expired (HTTP 401)"))

    labels = {label: (ok, detail) for label, ok, detail in run_checks(check_network=True)}

    assert labels["知乎连通"][0] is False
    assert labels["签名自检"][0] is False
    assert "无法验证" in labels["签名自检"][1]
