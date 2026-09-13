from __future__ import annotations

from wzlcarrot_cli.mcp import MCPServer
from wzlcarrot_cli.platforms import Platform
from wzlcarrot_cli.tools import Tool


class _Box:
    def hot(self, limit: int = 3):
        return [{"title": "端到端标题"}]

    def vote(self, answer_id: int):
        return {"ok": True, "answer_id": answer_id}


def _demo_platform() -> Platform:
    box = _Box()
    tools = [
        Tool("hot", "热榜", {"type": "object", "properties": {}}, box.hot),
        Tool(
            "vote",
            "赞同",
            {"type": "object", "properties": {"answer_id": {"type": "integer"}}, "required": ["answer_id"]},
            box.vote,
            write=True,
        ),
    ]
    return Platform(
        name="demo",
        title="Demo",
        builder=lambda: None,
        credentials_factory=lambda: object(),
        client_factory=lambda creds, settings: object(),
        build_tools=lambda client: tools,
    )


def _call(server: MCPServer, rid: int, method: str, params: dict | None = None) -> dict:
    request = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        request["params"] = params
    return server.handle(request)


def test_mcp_initialize_and_list():
    server = MCPServer(platforms=[_demo_platform()])
    init = _call(server, 1, "initialize")["result"]
    assert init["serverInfo"]["name"] == "wzlcarrot-cli"
    tools = _call(server, 2, "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"demo_hot", "demo_vote"} <= names


def test_mcp_read_tool_call():
    server = MCPServer(platforms=[_demo_platform()])
    resp = _call(server, 1, "tools/call", {"name": "demo_hot", "arguments": {}})
    text = resp["result"]["content"][0]["text"]
    assert "端到端标题" in text


def test_mcp_write_tool_gated():
    server = MCPServer(platforms=[_demo_platform()])
    resp = _call(server, 1, "tools/call", {"name": "demo_vote", "arguments": {"answer_id": 1}})
    assert "allow-writes" in resp["error"]["message"]

    server2 = MCPServer(allow_writes=True, platforms=[_demo_platform()])
    resp2 = _call(server2, 1, "tools/call", {"name": "demo_vote", "arguments": {"answer_id": 7}})
    assert '"answer_id": 7' in resp2["result"]["content"][0]["text"]


def test_mcp_unknown_method():
    server = MCPServer(platforms=[_demo_platform()])
    assert _call(server, 1, "no/such")["error"]["code"] == -32601
