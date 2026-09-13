"""Typer application entry point."""

from __future__ import annotations

import sys

import typer

from . import __version__
from .commands import actions, chat, connect, content, download, feed, login, publish, search
from .commands import user as user_cmd
from .commands._common import Settings
from .config import DIST_NAME
from .exceptions import ZhihuError
from .output import error_console
from .plugins import load_plugins, plugins_dir

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="知乎命令行客户端（所有命令均需先 `zhihu login`）。",
)

_GROUPS = {
    "download": download.download_app,
    "action": actions.actions_app,
    "publish": publish.publish_app,
}


_update_notified = False


def _notify_update() -> None:
    """One-line notice when PyPI has a newer release; never raises, never blocks."""
    global _update_notified
    if _update_notified:
        return
    _update_notified = True
    try:
        from .updates import check_for_update

        latest = check_for_update(__version__)
    except Exception:  # noqa: BLE001 - cosmetic path, must never fail a command
        return
    if latest:
        from .output import console

        console.print(
            f"[yellow]有新版本：zhihu-cli {latest}（当前 {__version__}）,"
            "运行 zhihu upgrade 升级；设置 ZHIHU_CLI_NO_UPDATE_CHECK=1 可关闭检查[/yellow]"
        )


@app.callback(invoke_without_command=True)
def configure(
    ctx: typer.Context,
    min_delay: float = typer.Option(1.5, "--min-delay", help="请求最小间隔（秒）"),
    max_delay: float = typer.Option(3.5, "--max-delay", help="请求最大间隔（秒）"),
    write_delay: float = typer.Option(8.0, "--write-delay", help="写操作最小间隔（秒）"),
    min_gap: float = typer.Option(3.0, "--min-gap", help="任意两次请求的最小间隔（跨命令生效，秒）"),
    json_output: bool = typer.Option(False, "--json", help="输出原始 JSON"),
) -> None:
    """设置全局选项（限速、JSON 输出）。"""
    ctx.obj = Settings(
        min_delay=min_delay,
        max_delay=max_delay,
        write_min_delay=write_delay,
        min_gap=min_gap,
        as_json=json_output,
    )
    _notify_update()
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty():
            chat.run_tui(ctx)
        else:
            typer.echo(ctx.get_help())


# account
app.command("login")(login.login)
app.command("logout")(login.logout)
app.command("status")(login.status)
app.command("connect")(connect.connect)


def show_version() -> None:
    """显示版本号。"""
    typer.echo(f"zhihu-cli {__version__}")


app.command("version")(show_version)


def upgrade(
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """升级 wzlcarrot-cli（自动识别 uv tool / pipx / pip 安装方式）。"""
    from .upgrade import upgrade as run_upgrade

    code = run_upgrade(assume_yes=yes)
    raise SystemExit(code)


app.command("upgrade")(upgrade)

# read
app.command("hot")(feed.hot)
app.command("feed")(feed.feed)
app.command("topic")(feed.topic)
app.command("search")(search.search)
app.command("question")(content.question)
app.command("answer")(content.answer)
app.command("article")(content.article)
app.command("comments")(content.comments)
app.command("user")(user_cmd.user)
app.command("me")(user_cmd.me)
app.command("following")(user_cmd.following)
app.command("followers")(user_cmd.followers)
app.command("collections")(user_cmd.collections)
app.command("notifications")(user_cmd.notifications)

# natural language
app.command("tui")(chat.tui)
app.command("chat")(chat.chat)
app.command("ask")(chat.ask)


def show_sessions() -> None:
    """列出已保存的对话会话（最近的在前）。"""
    from . import sessions as sessions_mod

    rows = sessions_mod.list_sessions()
    if not rows:
        typer.echo("暂无会话。")
        return
    for index, info in enumerate(rows):
        mark = "●" if index == 0 else " "
        typer.echo(f"{mark} {info.id}  {info.messages:>3} 条  {info.model}  {info.title}")


app.command("sessions")(show_sessions)

# groups
for name, sub in _GROUPS.items():
    app.add_typer(sub, name=name)

# plugins: contribution surface ("everything is a plugin")
_PLUGINS = load_plugins()
for plugin_command_name, plugin_command_fn in _PLUGINS.commands.items():
    app.command(plugin_command_name)(plugin_command_fn)


def show_plugins() -> None:
    """列出已加载的插件及其贡献。"""
    if not _PLUGINS.plugins:
        typer.echo(f"未加载任何插件。\n可放到：{plugins_dir()}/，或用入口点组 zhihu_cli.plugins 分发。")
        return
    for info in _PLUGINS.plugins:
        parts = []
        if info.commands:
            parts.append("命令: " + ", ".join(info.commands))
        if info.tools:
            parts.append("工具: " + ", ".join(info.tools))
        typer.echo(f"● {info.name}  " + "  ".join(parts))


app.command("plugins")(show_plugins)


def show_spill(
    clean: bool = typer.Option(False, "--clean", help="删除所有溢出文件"),
) -> None:
    """查看或清理工具结果溢出文件（大结果落盘目录）。"""
    from . import spill

    if clean:
        removed = spill.clean_spills()
        typer.echo(f"已删除 {removed} 个溢出文件。")
        return
    files = spill.list_spills()
    typer.echo(f"溢出目录：{spill.spill_root()}")
    typer.echo(f"共 {len(files)} 个文件")
    for path in files[:20]:
        typer.echo(f"  {path.name}  {path.stat().st_size} B")


app.command("spill")(show_spill)


def show_prompt() -> None:
    """打印当前组装后的系统提示词（基础段 + 记忆 + 插件段）。"""
    from .commands.chat import base_system_prompt
    from .prompt import build_prompt_sections, load_memory

    api = load_plugins()
    typer.echo(build_prompt_sections(base_system_prompt(), load_memory(), api.prompts))


app.command("prompt")(show_prompt)


def show_hooks() -> None:
    """列出已加载的工具管线钩子（插件 + hooks.json 规则）。"""
    from .hooks import load_hooks

    registry = load_hooks(load_plugins().hooks)
    entries = registry.entries()
    if not entries:
        typer.echo("未加载任何钩子。")
        return
    for event, matcher, fn, source in entries:
        name = getattr(fn, "__name__", fn.__class__.__name__)
        typer.echo(f"● [{event}] {matcher}  ({source}:{name})")


app.command("hooks")(show_hooks)


def doctor(
    offline: bool = typer.Option(False, "--offline", help="跳过联网检查"),
) -> None:
    """自检：登录、模型、插件、钩子、溢出、会话、连通性。"""
    from .doctor import run_checks
    from .output import console

    for label, ok, detail in run_checks(check_network=not offline):
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"{mark} {label}：{detail}")


app.command("doctor")(doctor)


def main() -> None:
    try:
        app()
    except ZhihuError as exc:
        error_console.print(f"[bold red]错误[/bold red] {exc}")
        raise SystemExit(1) from exc


# ---- umbrella CLI: ``wzlcarrot [platform] <command>`` ----------------------

root_app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="wzlcarrot 多平台 CLI（当前内置：知乎）。",
)
root_app.add_typer(app, name="zhihu", help="知乎：热榜 / 搜索 / 问答 / 评论 / 发布 / 导出 / Agent")


def root_version() -> None:
    """显示版本号。"""
    typer.echo(f"wzlcarrot {__version__}（发行名 {DIST_NAME}）")


root_app.command("version")(root_version)

# Generic, platform-agnostic commands live at the top level. Platform-specific
# operations (hot/search/comment/publish/login/...) stay under `wzlcarrot zhihu`.
_GENERIC_COMMANDS = {
    "connect": connect.connect,
    "doctor": doctor,
    "plugins": show_plugins,
    "hooks": show_hooks,
    "spill": show_spill,
    "prompt": show_prompt,
    "upgrade": upgrade,
    "sessions": show_sessions,
    "tui": chat.tui,
    "chat": chat.chat,
    "ask": chat.ask,
}
for _generic_name, _generic_fn in _GENERIC_COMMANDS.items():
    root_app.command(_generic_name)(_generic_fn)


@root_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    min_delay: float = typer.Option(1.5, "--min-delay", help="请求最小间隔（秒）"),
    max_delay: float = typer.Option(3.5, "--max-delay", help="请求最大间隔（秒）"),
) -> None:
    """wzlcarrot 入口；不带子命令时进入 TUI（当前为知乎）。"""
    ctx.obj = Settings(min_delay=min_delay, max_delay=max_delay)
    _notify_update()
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty():
            chat.run_tui(ctx)
        else:
            typer.echo(ctx.get_help())


def root_main() -> None:
    try:
        root_app()
    except ZhihuError as exc:
        error_console.print(f"[bold red]错误[/bold red] {exc}")
        raise SystemExit(1) from exc
