"""Render the TUI with a stub agent and export an SVG screenshot for the README.

    uv run python scripts/screenshot.py

Output: docs/img/tui.svg (no network, no login required).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from zhihu_cli.tui import ChatTUI


class FakeAgent:
    def __init__(self) -> None:
        self._confirm_fn = None

    def stats(self) -> dict:
        return {
            "requests": 1,
            "prompt_tokens": 842,
            "completion_tokens": 173,
            "total_tokens": 1015,
            "tool_calls": 1,
            "compactions": 0,
            "context_tokens": 1897,
        }

    def send_stream(self, text, cancel_event=None):
        yield ("tool", "hot", '{"limit": 3}')
        yield ("tool_done", "hot", "3 条")
        yield ("delta", "今天的知乎热榜前 3 名：\n\n")
        yield ("delta", "1. 如何评价 9 月新发布的开源模型？\n")
        yield ("delta", "2. 长期使用命令行工具是种怎样的体验？\n")
        yield ("delta", "3. 有哪些值得坚持的小习惯？\n")
        yield ("done", (
            "今天的知乎热榜前 3 名：\n\n1. 如何评价 9 月新发布的开源模型？\n"
            "2. 长期使用命令行工具是种怎样的体验？\n3. 有哪些值得坚持的小习惯？\n"
        ))


async def main() -> None:
    app = ChatTUI(FakeAgent(), subtitle="deepseek-chat")
    async with app.run_test(size=(100, 32)) as pilot:
        prompt = app.query_one("#prompt")
        prompt.value = "帮我看看今天热榜前3"
        await pilot.press("enter")
        for _ in range(40):
            await pilot.pause(0.1)
            if not app._busy:
                break
        await pilot.pause(0.2)
        svg = app.export_screenshot()
    out = Path(__file__).resolve().parent.parent / "docs" / "img" / "tui.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    asyncio.run(main())
