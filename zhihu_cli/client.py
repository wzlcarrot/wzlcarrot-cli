"""HTTP client with x-zse-96 signing, throttling and pagination."""

from __future__ import annotations

import base64
import email.utils
import hashlib
import hmac
import json as jsonlib
import random
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import (
    ANTI_ABUSE_COOLDOWN,
    API_BASE,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MIN_GAP,
    DEFAULT_WRITE_MIN_DELAY,
    SENSITIVE_EXTRA_DELAY,
    SENSITIVE_PATH_MARKERS,
    browser_headers,
    read_last_request,
    write_last_request,
)
from .exceptions import AntiAbuseError, ApiError, NotLoggedInError, SignatureError
from .session import Credentials
from .signing import ZSE93, sign_zse96

DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3

_RETRY_STATUS = {429, 500, 502, 503, 504}

# Bodies Zhihu returns when its anti-crawler protection kicks in.
_ABUSE_HINTS = ("请求存在异常", "暂时限制", "系统繁忙，请稍后", "安全验证")

# Hosts used by the rich-content publishing pipeline.
IMAGE_API = "https://api.zhihu.com/images"
OSS_UPLOAD = "https://zhihu-pics-upload.zhimg.com"
ZHUANLAN_API = "https://zhuanlan.zhihu.com/api"
CONTENT_DRAFTS = "/api/v4/content/drafts"
CONTENT_PUBLISH = "/api/v4/content/publish"


class ZhihuClient:
    def __init__(
        self,
        credentials: Credentials,
        *,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        write_min_delay: float = DEFAULT_WRITE_MIN_DELAY,
        min_gap: float = DEFAULT_MIN_GAP,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
    ) -> None:
        if not credentials.is_logged_in():
            raise NotLoggedInError(
                "not logged in: run `zhihu login` (needs valid d_c0 and z_c0 cookies)"
            )
        if min_delay > max_delay:
            min_delay, max_delay = max_delay, min_delay
        self.credentials = credentials
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.write_min_delay = write_min_delay
        self.min_gap = min_gap
        self.max_retries = max_retries
        headers = browser_headers()
        headers["x-requested-with"] = "fetch"
        xsrf = credentials.cookies.get("_xsrf")
        if xsrf:
            headers["x-xsrftoken"] = xsrf
        self._http = httpx.Client(timeout=timeout, follow_redirects=True, headers=headers)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ZhihuClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low level ---------------------------------------------------------

    def _throttle(self, *, write: bool = False, path: str = "") -> None:
        low, high = self.min_delay, self.max_delay
        if write:  # extra-cautious spacing for mutations
            low = max(low, self.write_min_delay)
            high = max(high, low + 2.0)
        if any(marker in path for marker in SENSITIVE_PATH_MARKERS):
            low += SENSITIVE_EXTRA_DELAY
            high += SENSITIVE_EXTRA_DELAY

        wait = random.uniform(low, high)
        # Cross-process floor: even separate CLI invocations can't burst.
        last = read_last_request()
        if last:
            wait = max(wait, self.min_gap - (time.time() - last))
        if wait > 0:
            time.sleep(max(0.0, wait))
        write_last_request(time.time())

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        if params:
            query = urlencode(params, doseq=True)
            path_and_query = f"{path}?{query}"
        else:
            path_and_query = path
        url = f"{API_BASE}{path_and_query}"

        content: bytes | None = None
        body_str: str | None = None
        headers: dict[str, str] = {
            "x-zse-93": ZSE93,
            "x-zse-96": sign_zse96(path_and_query, self.credentials.d_c0, None),
            "cookie": self.credentials.cookie_header(),
        }
        if json_body is not None:
            body_str = jsonlib.dumps(json_body, ensure_ascii=False, separators=(",", ":"))
            content = body_str.encode("utf-8")
            headers["content-type"] = "application/json; charset=utf-8"
            headers["x-zse-96"] = sign_zse96(path_and_query, self.credentials.d_c0, body_str)

        last_exc: Exception | None = None
        is_write = method.upper() != "GET"
        for attempt in range(1, self.max_retries + 1):
            self._throttle(write=is_write, path=path)
            try:
                resp = self._http.request(method, url, content=content, headers=headers)
            except httpx.TransportError as exc:  # network hiccup
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2.0 * attempt)
                    continue
                raise ApiError(f"network error: {exc}") from exc

            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                time.sleep(2.0 * attempt)
                continue
            return self._handle(resp)
        raise ApiError(f"request failed: {last_exc}")

    @staticmethod
    def _error_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err.get("code") or fallback)
            if isinstance(err, str) and err:
                return err
        return fallback

    def _handle(self, resp: httpx.Response) -> Any:
        if resp.status_code == 401:
            raise NotLoggedInError("session expired (HTTP 401): run `zhihu login` again")
        try:
            payload = resp.json()
        except ValueError:
            if resp.status_code < 400:
                return {}  # empty body (e.g. 204) is a valid success
            snippet = resp.text[:500]
            raise ApiError(f"HTTP {resp.status_code}: {snippet}", resp.status_code, snippet)

        if isinstance(payload, dict):
            blob = jsonlib.dumps(payload, ensure_ascii=False)
            if any(hint in blob for hint in _ABUSE_HINTS):
                write_last_request(time.time() + ANTI_ABUSE_COOLDOWN)
                raise AntiAbuseError(
                    f"触发了知乎反爬限制，已自动冷却 {int(ANTI_ABUSE_COOLDOWN)} 秒；"
                    "请稍后再试，并避免连续调用敏感接口"
                )

        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict) and err:
                message = self._error_message(payload, f"HTTP {resp.status_code}")
                code = err.get("code")
                if code == "ZERR_NOT_LOGIN":
                    raise NotLoggedInError(f"not logged in: {message}")
                # 403 + code 100 ("请求参数异常") is how Zhihu rejects a stale
                # x-zse-96 signature; same code on other statuses stays a
                # login/parameter problem as before.
                if code == 100 and resp.status_code == 403:
                    raise SignatureError(
                        f"{message}：签名可能已失效（知乎或已更新 x-zse-96 算法），"
                        "请运行 zhihu doctor 检查，或升级 wzlcarrot-cli"
                    )
                if code == 100:
                    raise NotLoggedInError(f"not logged in: {message}")
                raise ApiError(message, resp.status_code, payload)

        if resp.status_code >= 400:
            raise ApiError(
                self._error_message(payload, f"HTTP {resp.status_code}"),
                resp.status_code,
                payload,
            )
        return payload

    # -- convenience -------------------------------------------------------

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params or None)

    def post(self, path: str, json_body: Any | None = None, **params: Any) -> Any:
        return self.request("POST", path, params=params or None, json_body=json_body)

    def delete(self, path: str, **params: Any) -> Any:
        return self.request("DELETE", path, params=params or None)

    def paginate(
        self,
        path: str,
        params: dict[str, Any],
        *,
        limit: int = 20,
        max_items: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        offset = int(params.get("offset", 0))
        collected = 0
        while True:
            page_params = {**params, "offset": offset, "limit": limit}
            data = self.request("GET", path, params=page_params)
            items = data.get("data", []) if isinstance(data, dict) else []
            if not items:
                return
            for item in items:
                yield item
                collected += 1
                if max_items is not None and collected >= max_items:
                    return
            paging = data.get("paging", {}) if isinstance(data, dict) else {}
            if paging.get("is_end"):
                return
            offset += len(items)

    # -- read API ----------------------------------------------------------

    def me(self) -> dict:
        return self.get("/api/v4/me")

    def hot_list(self, limit: int = 50) -> dict:
        try:  # creators endpoint first, billboard as fallback
            return self.get("/api/v4/creators/rank/hot", domain=0, limit=limit)
        except ApiError:
            return self.get("/api/v3/feed/topstory/hot-lists/total", limit=limit, desktop="true")

    def recommend_feed(self, limit: int = 20) -> dict:
        return self.get("/api/v3/feed/topstory/recommend", page_number=1, limit=limit, action="down")

    def topic(self, topic_id: str) -> dict:
        return self.get(f"/api/v4/topics/{topic_id}")

    def topic_hot_questions(self, topic_id: str, limit: int = 10, offset: int = 0) -> dict:
        return self.get(f"/api/v4/topics/{topic_id}/feeds/essence", offset=offset, limit=limit)

    def answer_comments(self, answer_id: int, limit: int = 20, offset: int = 0,
                        order: str = "normal") -> dict:
        return self.get(
            f"/api/v4/answers/{answer_id}/comments",
            offset=offset, limit=limit, order=order, status="open",
        )

    def article_comments(self, article_id: int, limit: int = 20, offset: int = 0,
                         order: str = "normal") -> dict:
        return self.get(
            f"/api/v4/articles/{article_id}/comments",
            offset=offset, limit=limit, order=order, status="open",
        )

    def followers(self, token: str, limit: int = 20, offset: int = 0) -> dict:
        return self.get(
            f"/api/v4/members/{token}/followers",
            include="data[*].answer_count,articles_count,follower_count",
            offset=offset, limit=limit,
        )

    def following(self, token: str, limit: int = 20, offset: int = 0) -> dict:
        return self.get(
            f"/api/v4/members/{token}/followees",
            include="data[*].answer_count,articles_count,follower_count",
            offset=offset, limit=limit,
        )

    def favlists(self, token: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        if not token:
            token = self.me().get("url_token", "")
        return self.get(f"/api/v4/members/{token}/favlists", offset=offset, limit=limit)

    def notifications(self, limit: int = 10, offset: int = 0, entry_name: str = "all") -> dict:
        return self.get(
            "/api/v4/notifications/v2/recent",
            limit=limit, offset=offset, entry_name=entry_name,
        )

    # -- writes ------------------------------------------------------------

    def vote(self, answer_id: int, kind: str = "up") -> dict:
        return self.post(f"/api/v4/answers/{answer_id}/voters", {"type": kind})

    def follow_question(self, question_id: int) -> dict:
        return self.post(f"/api/v4/questions/{question_id}/followers", {})

    def unfollow_question(self, question_id: int) -> dict:
        return self.delete(f"/api/v4/questions/{question_id}/followers")

    def collection_contents(self, collection_id: int, limit: int = 20, offset: int = 0) -> dict:
        return self.get(
            f"/api/v4/collections/{collection_id}/contents", offset=offset, limit=limit
        )

    def collection_add(self, collection_id: int, content_id: int,
                       content_type: str = "answer") -> dict:
        return self.post(
            f"/api/v4/collections/{collection_id}/contents",
            content_id=content_id, content_type=content_type,
        )

    def collection_remove(self, collection_id: int, content_id: int,
                          content_type: str = "answer") -> dict:
        return self.delete(
            f"/api/v4/collections/{collection_id}/contents/{content_id}",
            content_type=content_type,
        )

    def comment_answer(self, answer_id: int, content: str) -> dict:
        return self.post(
            f"/api/v4/answers/{answer_id}/comments",
            {"content": content, "type": "comment"},
        )

    def comment_article(self, article_id: int, content: str) -> dict:
        return self.post(
            f"/api/v4/articles/{article_id}/comments",
            {"content": content, "type": "comment"},
        )

    def delete_comment(self, comment_id: int) -> dict:
        return self.delete(f"/api/v4/comments/{comment_id}")

    # -- non-signed requests (image host / zhuanlan) -----------------------

    def _raw(self, method: str, url: str, *, json_body: Any | None = None,
             content: bytes | None = None, headers: dict[str, str] | None = None,
             write: bool = True) -> Any:
        request_headers = dict(headers or {})
        request_headers.setdefault("cookie", self.credentials.cookie_header())
        body = content
        if json_body is not None:
            body = jsonlib.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers["content-type"] = "application/json; charset=utf-8"
        for attempt in range(1, self.max_retries + 1):
            self._throttle(write=write, path=url)
            try:
                resp = self._http.request(method, url, content=body, headers=request_headers)
            except httpx.TransportError as exc:
                if attempt < self.max_retries:
                    time.sleep(2.0 * attempt)
                    continue
                raise ApiError(f"network error: {exc}") from exc
            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                time.sleep(2.0 * attempt)
                continue
            return self._handle(resp)
        raise ApiError("request failed")

    # -- image upload pipeline ---------------------------------------------

    def upload_image(self, file_path: str | Path, source: str = "article") -> dict:
        path = Path(file_path)
        if not path.is_file():
            raise ApiError(f"image file not found: {file_path}")
        data = path.read_bytes()
        md5_hex = hashlib.md5(data).hexdigest()

        reg = self._raw("POST", IMAGE_API, json_body={"image_hash": md5_hex, "source": source})
        upload_file = reg.get("upload_file", {})
        image_id = upload_file.get("image_id")
        state = upload_file.get("state")
        if state == 2:
            self._upload_to_oss(upload_file["object_key"], data, reg["upload_token"], path.suffix)
        elif state != 1:
            raise ApiError(f"unexpected image state: {state}")

        info = self._poll_image(str(image_id))
        try:
            from PIL import Image

            with Image.open(path) as img:
                info["width"], info["height"] = img.size
        except Exception:  # noqa: BLE001 - dimensions are optional metadata
            info.setdefault("width", 0)
            info.setdefault("height", 0)
        return info

    def _upload_to_oss(self, obj_key: str, data: bytes, token: dict, suffix: str = "") -> None:
        if suffix.lower() == ".png":
            content_type = "image/png"
        else:
            content_type = "image/jpeg"
        date = email.utils.formatdate(usegmt=True)
        security_token = token["access_token"]
        string_to_sign = (
            f"PUT\n\n{content_type}\n{date}\n"
            f"x-oss-security-token:{security_token}\n/zhihu-pics/{obj_key}"
        )
        signature = base64.b64encode(
            hmac.new(token["access_key"].encode(), string_to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        headers = {
            "Content-Type": content_type,
            "Date": date,
            "x-oss-security-token": security_token,
            "Authorization": f"OSS {token['access_id']}:{signature}",
        }
        self._throttle(write=True)
        resp = self._http.put(f"{OSS_UPLOAD}/{obj_key}", content=data, headers=headers)
        if resp.status_code != 200:
            raise ApiError(f"OSS upload failed ({resp.status_code}): {resp.text[:200]}")

    def _poll_image(self, image_id: str, max_attempts: int = 15, interval: float = 2.0) -> dict:
        for _ in range(max_attempts):
            data = self._raw("GET", f"{IMAGE_API}/{image_id}", write=False)
            if data.get("status") == "success":
                return {
                    "src": data["src"],
                    "original_src": data.get("original_src", data["src"]),
                    "watermark": data.get("watermark", "watermark"),
                    "watermark_src": data.get("watermark_src", ""),
                }
            time.sleep(interval)
        raise ApiError("image processing timed out")

    @staticmethod
    def _build_img_html(image_infos: list[dict]) -> str:
        tags = []
        for info in image_infos:
            src = info["src"]
            original = info.get("original_src", src)
            tags.append(
                f'<img src="{src}" data-caption="" data-size="normal"'
                f' data-rawwidth="{info.get("width", 0)}" data-rawheight="{info.get("height", 0)}"'
                f' data-watermark="{info.get("watermark", "watermark")}"'
                f' data-original-src="{original}"'
                f' data-watermark-src="{info.get("watermark_src", "")}"'
                f' data-private-watermark-src=""/>'
            )
        return "".join(tags)

    # -- publish pipeline --------------------------------------------------

    def _content_draft(self, action: str) -> str:
        data = self.post(CONTENT_DRAFTS, {"action": action})
        content_id = (data.get("data") or {}).get("content_id")
        if not content_id:
            raise ApiError("draft created but no content_id returned")
        return str(content_id)

    def _content_publish(self, payload: dict) -> dict:
        data = self.post(CONTENT_PUBLISH, payload)
        code = data.get("code")
        if code not in (None, 0):
            raise ApiError(data.get("message") or data.get("toast_message") or "publish failed")
        result = (data.get("data") or {}).get("result")
        if result:
            try:
                return jsonlib.loads(result)
            except (ValueError, TypeError):
                pass
        return data

    def create_question(self, title: str, detail: str = "",
                        topic_ids: list[str] | None = None,
                        image_infos: list[dict] | None = None) -> dict:
        title = title.strip()
        if not title.endswith(("？", "?")):  # Zhihu rejects titles without a question mark
            title += "？"
        if image_infos:
            html = detail + self._build_img_html(image_infos)
            return self._content_publish({
                "action": "question",
                "data": {
                    "title": {"title": title},
                    "topic": {"topics": list(topic_ids) if topic_ids else []},
                    "hybrid": {"html": html, "textLength": len(detail)},
                    "extra_info": {"publisher": "pc"},
                    "questionConfig": {"type": "0"},
                    "draft": {"disabled": 1},
                },
            })
        payload: dict[str, Any] = {"title": title, "detail": detail}
        if topic_ids:
            payload["topic_url_tokens"] = topic_ids
        return self.post("/api/v4/questions", payload)

    def create_pin(self, title: str, content: str = "",
                   image_infos: list[dict] | None = None) -> dict:
        draft_id = self._content_draft("pin")
        body_html = content.strip()
        data: dict[str, Any] = {
            "publish": {"traceId": f"{int(time.time() * 1000)},{uuid.uuid4()}"},
            "commentsPermission": {"comment_permission": "all"},
            "extra_info": {"view_permission": "all", "publisher": "pc"},
            "draft": {"disabled": 1, "id": draft_id},
            "title": {"title": title},
            "hybrid": {"html": body_html, "textLength": len(content)},
        }
        if image_infos:
            data["media"] = {
                "medias": [
                    {
                        "image": {
                            "width": info.get("width", 0),
                            "height": info.get("height", 0),
                            "url": info["src"],
                            "originalUrl": info.get("original_src", info["src"]),
                            "watermark": info.get("watermark", "watermark"),
                            "watermarkUrl": info.get("watermark_src", ""),
                        }
                    }
                    for info in image_infos
                ]
            }
            data["hybrid"]["html"] = (content + self._build_img_html(image_infos)) if content \
                else self._build_img_html(image_infos)
        return self._content_publish({"action": "pin", "data": data})

    def create_article(self, title: str, content: str,
                       topic_ids: list[str] | None = None,
                       image_infos: list[dict] | None = None) -> dict:
        if image_infos:
            html = content + self._build_img_html(image_infos)
            draft_id = self._content_draft("article")
            return self._content_publish({
                "action": "article",
                "data": {
                    "title": {"title": title},
                    "hybrid": {"html": html, "textLength": len(content)},
                    "extra_info": {"publisher": "pc"},
                    "draft": {"disabled": 1, "id": draft_id},
                    "commentsPermission": {"comment_permission": "anyone"},
                },
            })
        draft = self._raw("POST", f"{ZHUANLAN_API}/articles/drafts", json_body={})
        draft_id = draft.get("id", "")
        if not draft_id:
            raise ApiError("article draft created but no ID returned")
        patch = {"title": title, "content": content}
        if topic_ids:
            patch["topics"] = topic_ids
        self._raw("PATCH", f"{ZHUANLAN_API}/articles/{draft_id}/draft", json_body=patch)
        return self._raw(
            "PUT",
            f"{ZHUANLAN_API}/articles/{draft_id}/publish",
            json_body={"column": None, "commentPermission": "anyone"},
        )

    def delete_question(self, question_id: int) -> dict:
        return self.delete(f"/api/v4/questions/{question_id}")

    def delete_pin(self, pin_id: int) -> dict:
        return self.delete(f"/api/v4/pins/{pin_id}")

    def delete_article(self, article_id: int) -> dict:
        return self._raw("DELETE", f"{ZHUANLAN_API}/articles/{article_id}")


def client_from_credentials(
    credentials: Credentials,
    *,
    min_delay: float = DEFAULT_MIN_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> ZhihuClient:
    return ZhihuClient(credentials, min_delay=min_delay, max_delay=max_delay)
