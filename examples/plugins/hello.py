"""Example wzlcarrot-cli plugin.

Enable it by copying this file into ``~/.config/zhihu-cli/plugins/``, or ship a
distribution that exposes the ``wzlcarrot_cli.plugins`` entry point.

A plugin is any module with ``register(api)``; ``api`` lets it contribute CLI
commands and agent tools.
"""

from __future__ import annotations

import typer

from wzlcarrot_cli.hooks import PRE_EXECUTE, HookResult


def register(api) -> None:
    def hello(name: str = typer.Argument("world")) -> None:
        """打个招呼（示例插件命令）。"""
        typer.echo(f"hello, {name}")

    api.command("hello", hello)

    def echo(client, text: str) -> dict:
        return {"echo": text, "length": len(text)}

    api.tool(
        name="echo",
        description="回显一段文本并返回其长度（示例插件工具）",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "要回显的文本"}},
            "required": ["text"],
        },
        handler=echo,
        write=False,
    )

    api.prompt_section("hello-style", "回答时保持简短、口语化。", priority=10)

    def shout(name, args):
        if isinstance(args, dict) and "text" in args:
            return HookResult(args={**args, "text": str(args["text"]).upper()})
        return None

    api.hook(PRE_EXECUTE, shout, matcher="echo")
