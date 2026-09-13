"""小红书平台（规划中，尚未实现）。

Registered so `wzlcarrot xiaohongshu ...` and `wzlcarrot platforms` already
work; the real client, login flow and tools will be added here later.
"""

from __future__ import annotations

import typer

from . import Platform


def _xiaohongshu_app() -> typer.Typer:
    app = typer.Typer(
        add_completion=False,
        no_args_is_help=True,
        help="小红书（规划中，尚未实现）。",
    )

    @app.command("status")
    def status() -> None:
        """查看小红书平台状态。"""
        typer.echo("小红书平台尚在规划中，暂未实现。可用 `wzlcarrot platforms` 查看已注册平台。")

    return app


def build_platform() -> Platform:
    return Platform(
        name="xiaohongshu",
        title="小红书（规划中）",
        builder=_xiaohongshu_app,
        source="planned",
    )
