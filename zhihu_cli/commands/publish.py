"""Publishing and deleting content (rich text + images)."""

from __future__ import annotations

from pathlib import Path

import typer

from ..composer import ASK_TEMPLATE, edit_text, is_cancelled, markdown_to_html, split_title
from ..output import console
from ._common import emit, require_client

publish_app = typer.Typer(help="发布/删除内容（提问、想法、文章），支持 HTML 与图片")


def _confirm(yes: bool, action: str) -> None:
    if not yes:
        typer.confirm(f"确认执行：{action}？", abort=True)


def _upload_images(client, images: list[Path] | None, source: str) -> list[dict] | None:
    if not images:
        return None
    infos = []
    for image_path in images:
        console.print(f"[dim]上传图片 {image_path} …[/dim]")
        infos.append(client.upload_image(image_path, source=source))
    return infos


def _report(ctx: typer.Context, data: dict) -> None:
    if emit(ctx, data):
        return
    ref = data.get("id") or data.get("url") or data
    console.print(f"[green]完成[/green] {ref}")


@publish_app.command("ask")
def ask(
    ctx: typer.Context,
    title: str = typer.Argument(None, help="问题标题（使用 --edit 时可省略）"),
    detail: str = typer.Option("", "--detail", "-d", help="问题描述（支持 HTML）"),
    topic: list[str] = typer.Option(None, "--topic", "-t", help="话题 ID，可重复"),
    image: list[Path] = typer.Option(None, "--image", "-i", help="图片路径，可重复"),
    edit: bool = typer.Option(False, "--edit", "-e", help="用 Markdown 编辑器（优先 MarkText）写内容，支持本地图片"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """发布提问。"""
    client = require_client(ctx)
    with client:
        if edit:
            markdown = edit_text(ASK_TEMPLATE)
            if is_cancelled(markdown, ASK_TEMPLATE):
                console.print("已取消。")
                return
            file_title, body = split_title(markdown)
            title = title or file_title
            detail = markdown_to_html(body, client, "question")
            infos = None
        else:
            infos = _upload_images(client, image, "question")
        if not title:
            raise typer.BadParameter("缺少标题（写在 `# 标题` 行或用参数传入）")
        _confirm(yes, f"发布提问：{title}")
        data = client.create_question(title, detail, topic, infos)
    _report(ctx, data)


@publish_app.command("pin")
def pin(
    ctx: typer.Context,
    title: str = typer.Argument(None, help="想法标题（使用 --edit 时可省略）"),
    content: str = typer.Option("", "--content", "-c", help="正文（支持 HTML）"),
    image: list[Path] = typer.Option(None, "--image", "-i", help="图片路径，可重复"),
    edit: bool = typer.Option(False, "--edit", "-e", help="用 Markdown 编辑器（优先 MarkText）写内容，支持本地图片"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """发布想法。"""
    client = require_client(ctx)
    with client:
        if edit:
            markdown = edit_text(ASK_TEMPLATE)
            if is_cancelled(markdown, ASK_TEMPLATE):
                console.print("已取消。")
                return
            file_title, body = split_title(markdown)
            title = title or file_title
            content = markdown_to_html(body, client, "pin")
            infos = None
        else:
            infos = _upload_images(client, image, "pin")
        if not title:
            raise typer.BadParameter("缺少标题（写在 `# 标题` 行或用参数传入）")
        _confirm(yes, f"发布想法：{title}")
        data = client.create_pin(title, content, infos)
    _report(ctx, data)


@publish_app.command("article")
def article(
    ctx: typer.Context,
    title: str = typer.Argument(None, help="文章标题（使用 --edit 时可省略）"),
    content: str = typer.Argument(None, help="正文（支持 HTML）"),
    topic: list[str] = typer.Option(None, "--topic", "-t", help="话题 ID，可重复"),
    image: list[Path] = typer.Option(None, "--image", "-i", help="图片路径，可重复"),
    edit: bool = typer.Option(False, "--edit", "-e", help="用 Markdown 编辑器（优先 MarkText）写内容，支持本地图片"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """发布专栏文章。"""
    client = require_client(ctx)
    with client:
        if edit:
            markdown = edit_text(ASK_TEMPLATE)
            if is_cancelled(markdown, ASK_TEMPLATE):
                console.print("已取消。")
                return
            file_title, body = split_title(markdown)
            title = title or file_title
            content = markdown_to_html(body, client, "article")
            infos = None
        else:
            infos = _upload_images(client, image, "article")
        if not title or content is None:
            raise typer.BadParameter("缺少标题或正文（用 --edit，或传参数）")
        _confirm(yes, f"发布文章：{title}")
        data = client.create_article(title, content, topic, infos)
    _report(ctx, data)


@publish_app.command("delete-question")
def delete_question(
    ctx: typer.Context,
    question_id: int = typer.Argument(..., help="问题 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除自己发布的提问。"""
    _confirm(yes, f"删除提问 {question_id}")
    client = require_client(ctx)
    with client:
        data = client.delete_question(question_id)
    console.print(f"[green]完成[/green] {data}")


@publish_app.command("delete-pin")
def delete_pin(
    ctx: typer.Context,
    pin_id: int = typer.Argument(..., help="想法 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除自己发布的想法。"""
    _confirm(yes, f"删除想法 {pin_id}")
    client = require_client(ctx)
    with client:
        data = client.delete_pin(pin_id)
    console.print(f"[green]完成[/green] {data}")


@publish_app.command("delete-article")
def delete_article(
    ctx: typer.Context,
    article_id: int = typer.Argument(..., help="文章 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除自己发布的文章。"""
    _confirm(yes, f"删除文章 {article_id}")
    client = require_client(ctx)
    with client:
        data = client.delete_article(article_id)
    console.print(f"[green]完成[/green] {data}")
