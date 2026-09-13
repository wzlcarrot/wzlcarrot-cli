"""A small, platform-agnostic tool descriptor.

Platforms contribute tools (name + schema + handler) to both the built-in agent
and the MCP server.  A handler is either a bound method (platform tools, called
as ``handler(**arguments)``) or a free function taking the client first
(``handler(client, **arguments)``, used by plugins).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    write: bool = False

    def spec(self) -> dict[str, Any]:
        """OpenAI-function / MCP-tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def mcp_spec(self) -> dict[str, Any]:
        """MCP ``tools/list`` entry (same shape minus the ``function`` wrapper)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }
