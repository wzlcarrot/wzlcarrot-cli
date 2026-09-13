from wzlcarrot_cli.session import Credentials
from wzlcarrot_cli.signing import sign_zse96


def test_sign_shape_and_stability():
    value = sign_zse96("/api/v4/me", "abc")
    assert value.startswith("2.0_")
    assert value == sign_zse96("/api/v4/me", "abc")


def test_sign_depends_on_path_and_body():
    base = sign_zse96("/api/v4/me", "abc")
    assert sign_zse96("/api/v4/me?limit=1", "abc") != base
    assert sign_zse96("/api/v4/me", "abc", "{}") != base


def test_cookie_parsing():
    raw = "d_c0=xyz; z_c0=token; _zap=abc"
    creds = Credentials.from_cookie_string(raw)
    assert creds.d_c0 == "xyz"
    assert creds.z_c0 == "token"
    assert creds.is_logged_in()
    assert "d_c0=xyz" in creds.cookie_header()


def test_cookie_missing_login():
    creds = Credentials.from_cookie_string("d_c0=only")
    assert not creds.is_logged_in()


def test_client_sets_csrf_and_browser_headers():
    from wzlcarrot_cli.client import ZhihuClient

    creds = Credentials(cookies={"d_c0": "a", "z_c0": "b", "_xsrf": "xyz"})
    client = ZhihuClient(creds, min_delay=0, max_delay=0)
    try:
        assert client._http.headers["x-xsrftoken"] == "xyz"
        assert "sec-ch-ua" in client._http.headers
        assert client.write_min_delay >= 5
    finally:
        client.close()


def test_anti_abuse_response_is_detected(tmp_path, monkeypatch):
    import httpx

    from wzlcarrot_cli.client import ZhihuClient
    from wzlcarrot_cli.exceptions import AntiAbuseError

    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    creds = Credentials(cookies={"d_c0": "a", "z_c0": "b"})
    client = ZhihuClient(creds, min_delay=0, max_delay=0, min_gap=0)
    resp = httpx.Response(
        403, json={"error": {"message": "您当前请求存在异常，暂时限制本次访问"}}
    )
    try:
        try:
            client._handle(resp)
        except AntiAbuseError:
            pass
        else:
            raise AssertionError("expected AntiAbuseError")
    finally:
        client.close()
