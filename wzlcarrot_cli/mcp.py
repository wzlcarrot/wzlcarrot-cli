"""Minimal stdio MCP (Model Context Protocol) server.

Exposes every registered platform's tools as standard MCP tools, so external
agents (Claude Code, opencode, Cursor, ...) can call ``wzlcarrot``.  Uses
newline-delimited JSON-RPC 2.0 over stdio.

Tools come from the platform registry (``Platform.build_tools``), so a new
platform (e.g. weibo) automatically shows up here.  Write tools are opt-in via
``--allow-writes``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any, TextIO

from .exceptions import ZhihuError
from .tools import Tool

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "wzlcarrot-cli"


def _default_platforms() -> list:
    from .platforms import discover

    return discover()


class MCPServer:
    def __init__(self, *, allow_writes: bool = False, platforms: list | None = None) -> None:
        self._allow_writes = allow_writes
        self._platforms = platforms if platforms is not None else _default_platforms()
        self._tools: dict[str, tuple[Tool, Any]] = {}
        self._specs: list[dict[str, Any]] = []
        self._build()

    def _build(self) -> None:
        from .commands._common import Settings

        for platform in self._platforms:
            if platform.build_tools is None:
                continue
            client = None
            if platform.credentials_factory is not None and platform.client_factory is not None:
                try:
                    client = platform.client_factory(platform.credentials_factory(), Settings())
                except Exception:  # noqa: BLE001 - not logged in is fine for listing
                    client = None
            for tool in platform.build_tools(client):
                name = f"{platform.name}_{tool.name}"
                self._tools[name] = (tool, client)
                self._specs.append({
                    "name": name,
                    "description": tool.description,
                    "inputSchema": tool.parameters,
                })

    def list_tools(self) -> list[dict[str, Any]]:
        return self._specs

    def call(self, name: str, args: dict[str, Any]) -> str:
        entry = self._tools.get(name)
        if entry is None:
            raise ZhihuError(f"未知工具：{name}")
        tool, client = entry
        if tool.write and not self._allow_writes:
            raise ZhihuError(f"写工具 {name} 未启用（用 --allow-writes 开启）")
        if client is None:
            raise ZhihuError("未登录：请先运行 `zhihu login`")
        result = tool.handler(**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            return _result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.18.0"},
            })
        if method in ("notifications/initialized", "initialized"):
            return None
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": self.list_tools()})
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                text = self.call(str(params.get("name", "")), params.get("arguments") or {})
            except Exception as exc:  # noqa: BLE001 - report tool errors to the client
                return _error(request_id, -32000, str(exc))
            return _result(request_id, {"content": [{"type": "text", "text": text}]})
        return _error(request_id, -32601, f"method not found: {method}")


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(
    *,
    allow_writes: bool = False,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    lines: Iterable[str] | None = None,
) -> None:
    server = MCPServer(allow_writes=allow_writes)
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    for raw in lines if lines is not None else input_stream:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        response = server.handle(request)
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
