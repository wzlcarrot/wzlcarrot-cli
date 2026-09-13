"""Interactive model-provider setup (like opencode's ``/connect``)."""

from __future__ import annotations

import typer
from rich.table import Table

from ..llm import LLMClient, LLMConfig, save_llm_config
from ..output import console, error_console
from ..providers import PROVIDERS, get_provider


def _print_providers() -> None:
    table = Table(title="可选模型供应商", header_style="bold cyan")
    table.add_column("#", justify="right", width=3)
    table.add_column("ID", style="magenta", width=12)
    table.add_column("名称")
    for index, provider in enumerate(PROVIDERS, start=1):
        table.add_row(str(index), provider.id, provider.name)
    console.print(table)


def _test_config(api_key: str, base_url: str, model: str) -> bool:
    client = LLMClient(LLMConfig(api_key=api_key, base_url=base_url, model=model), timeout=30)
    try:
        client.chat([{"role": "user", "content": "只回复：OK"}])
        return True
    finally:
        client.close()


def connect(
    provider: str = typer.Option(None, "--provider", "-p", help="供应商 ID（见 --list）"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API Key"),
    model: str = typer.Option(None, "--model", "-m", help="模型名"),
    base_url: str = typer.Option(None, "--base-url", help="自定义兼容接口地址"),
    list_providers: bool = typer.Option(False, "--list", help="列出内置供应商与模型"),
    test: bool = typer.Option(False, "--test", help="保存后做一次连通性测试"),
) -> None:
    """配置模型供应商与 API Key（写入 ~/.config/wzlcarrot-cli/llm.json）。"""
    if list_providers:
        _print_providers()
        return

    selected = get_provider(provider) if provider else None
    if provider and selected is None:
        error_console.print(f"[red]未知供应商：{provider}[/red]（用 --list 查看）")
        raise typer.Exit(code=1)

    if selected is None and not provider:
        _print_providers()
        choice = typer.prompt("选择供应商编号", type=int)
        if not 1 <= choice <= len(PROVIDERS):
            raise typer.BadParameter("编号超出范围")
        selected = PROVIDERS[choice - 1]

    if selected is not None and selected.id == "custom":
        selected = None  # custom needs an explicit base_url

    if base_url is None and selected is not None:
        base_url = selected.base_url
    if base_url is None:
        base_url = typer.prompt("接口地址（OpenAI 兼容 base_url）")

    if model is None:
        if selected is not None and selected.models:
            model = selected.models[0]  # use the provider's default silently
        else:
            model = typer.prompt("模型名")

    if api_key is None:
        api_key = typer.prompt("API Key", hide_input=True)

    if not api_key or not base_url or not model:
        error_console.print("[red]API Key / base_url / model 都不能为空[/red]")
        raise typer.Exit(code=1)

    if test:
        with console.status("测试连通性…"):
            try:
                _test_config(api_key, base_url, model)
                console.print("[green]连接成功[/green]")
            except Exception as exc:
                error_console.print(f"[red]测试失败[/red] {exc}")
                raise typer.Exit(code=1) from exc

    path = save_llm_config(api_key, base_url, model)
    console.print(f"[green]已保存[/green] {model} @ {base_url}")
    console.print(f"[dim]{path}[/dim]")
