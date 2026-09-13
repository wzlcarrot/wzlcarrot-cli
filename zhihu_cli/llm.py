"""Minimal OpenAI-compatible chat client used by the natural-language mode."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import config_dir
from .exceptions import ZhihuError

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL

    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


def llm_config_file() -> Path:
    return config_dir() / "llm.json"


def save_llm_config(api_key: str, base_url: str, model: str) -> Path:
    path = llm_config_file()
    path.write_text(
        json.dumps({"api_key": api_key, "base_url": base_url, "model": model},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def resolve_llm_config(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LLMConfig:
    """Resolve config from CLI args, env vars, then ``llm.json``."""
    data: dict[str, Any] = {}
    path = llm_config_file()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ZhihuError(f"无法解析 {path}: {exc}") from exc

    resolved = LLMConfig(
        api_key=(
            api_key
            or os.environ.get("ZHIHU_CLI_LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or data.get("api_key", "")
        ),
        base_url=(
            base_url
            or os.environ.get("ZHIHU_CLI_LLM_BASE_URL")
            or data.get("base_url", DEFAULT_BASE_URL)
        ),
        model=(
            model
            or os.environ.get("ZHIHU_CLI_LLM_MODEL")
            or data.get("model", DEFAULT_MODEL)
        ),
    )
    if not resolved.api_key:
        raise ZhihuError(
            "未配置模型 API Key。任选其一：\n"
            "  export ZHIHU_CLI_LLM_API_KEY=sk-xxx\n"
            f'  写入 {llm_config_file()}：'
            '{"api_key":"sk-xxx","base_url":"https://api.deepseek.com/v1","model":"deepseek-chat"}\n'
            "  或运行时传 --api-key"
        )
    return resolved


class LLMClient:
    def __init__(self, config: LLMConfig, *, timeout: float = 120.0) -> None:
        self.config = config
        self._http = httpx.Client(timeout=timeout)
        self._headers = {
            "authorization": f"Bearer {config.api_key}",
            "content-type": "application/json",
        }
        # Accumulated provider-reported usage across the session.
        self.usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
        }

    def _record_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self.usage[key] += int(usage.get(key) or 0)
        self.usage["requests"] += 1

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = None
        for attempt in range(1, 4):
            resp = self._http.post(self.config.endpoint(), headers=self._headers, json=payload)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(3.0 * attempt)
                continue
            break
        assert resp is not None
        if resp.status_code >= 400:
            raise ZhihuError(f"模型接口错误 {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        self._record_usage(data.get("usage"))
        choices = data.get("choices") or []
        if not choices:
            raise ZhihuError(f"模型返回为空: {data}")
        return choices[0].get("message", {})

    def chat_stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        """Yield ``{"type": "delta"|"done", ...}`` events from a streaming call."""
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        content_parts: list[str] = []
        tool_buf: dict[int, dict[str, str]] = {}
        with self._http.stream(
            "POST", self.config.endpoint(), headers=self._headers, json=payload
        ) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", "replace")
                raise ZhihuError(f"模型接口错误 {resp.status_code}: {body[:500]}")
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("usage"):
                    self._record_usage(obj["usage"])
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    content_parts.append(text)
                    yield {"type": "delta", "text": text}
                for tool_call in delta.get("tool_calls") or []:
                    index = tool_call.get("index", 0)
                    slot = tool_buf.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if tool_call.get("id"):
                        slot["id"] = tool_call["id"]
                    function = tool_call.get("function") or {}
                    slot["name"] += function.get("name") or ""
                    slot["arguments"] += function.get("arguments") or ""

        message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
        if tool_buf:
            message["tool_calls"] = [
                {
                    "id": tool_buf[i]["id"],
                    "type": "function",
                    "function": {"name": tool_buf[i]["name"], "arguments": tool_buf[i]["arguments"]},
                }
                for i in sorted(tool_buf)
            ]
        yield {"type": "done", "message": message}
