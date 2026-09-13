"""Project exceptions."""

from __future__ import annotations


class ZhihuError(Exception):
    """Base error for the client."""


class NotLoggedInError(ZhihuError):
    """Raised when a command needs credentials but none are stored."""


class ApiError(ZhihuError):
    """Raised when the API returns an error payload or an unexpected status."""

    def __init__(self, message: str, status: int | None = None, payload: object | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class AntiAbuseError(ZhihuError):
    """Raised when Zhihu's anti-crawler protection throttles us.

    A cooling-off timestamp is written so subsequent processes also back off.
    """


class SignatureError(ZhihuError):
    """Raised when Zhihu rejects the request signature (HTTP 403, code 100).

    Distinct from login problems: it usually means Zhihu changed the
    x-zse-96 algorithm and this build of wzlcarrot-cli is outdated.
    """
