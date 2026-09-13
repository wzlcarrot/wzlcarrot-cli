"""Write operations (vote / collect / follow / comment / publish).

These endpoints are reverse-engineered and carry a higher risk of account
restrictions.  Every command asks for confirmation and the whole tool throttles
requests by default, so use sparingly.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..composer import (
    BODY_TEMPLATE,
    edit_text,
    has_local_images,
    is_cancelled,
    markdown_to_html,
    to_plain_text,
)
from ..output import console
from ._common import require_client

actions_app = typer.Typer(help="写操作（点赞/收藏/关注/评论/发布），有风控风险，低频使用")


def _confirm(yes: bool, action: str) -> None:
    if not yes:
        typer.confirm(f"确认执行：{action}？", abort=True)


@actions_app.command("vote")
def vote(
    ctx: typer.Context,
    answer_id: int = typer.Option(None, "--answer", help="回答 ID"),
    article_id: int = typer.Option(None, "--article", help="文章 ID"),
    down: bool = typer.Option(False, "--down", help="反对（默认赞同）"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """赞同 / 反对 回答或文章。"""
    if bool(answer_id) == bool(article_id):
        raise typer.BadParameter("请且仅请指定 --answer 或 --article")
    kind = "answers" if answer_id else "articles"
    content_id = answer_id or article_id
    _confirm(yes, f"{'反对' if down else '赞同'} {kind[:-1]} {content_id}")
    client = require_client(ctx)
    with client:
        data = client.post(f"/api/v4/{kind}/{content_id}/voters",
                           json_body={"type": "down" if down else "up"})
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("unvote")
def unvote(
    ctx: typer.Context,
    answer_id: int = typer.Option(None, "--answer", help="回答 ID"),
    article_id: int = typer.Option(None, "--article", help="文章 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """取消赞同。"""
    if bool(answer_id) == bool(article_id):
        raise typer.BadParameter("请且仅请指定 --answer 或 --article")
    kind = "answers" if answer_id else "articles"
    content_id = answer_id or article_id
    _confirm(yes, f"取消投票 {kind[:-1]} {content_id}")
    client = require_client(ctx)
    with client:
        data = client.post(f"/api/v4/{kind}/{content_id}/voters", json_body={"type": "neutral"})
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("collect")
def collect(
    ctx: typer.Context,
    content_id: int = typer.Argument(..., help="内容 ID"),
    collection: int = typer.Option(..., "--collection", "-c", help="收藏夹 ID"),
    content_type: str = typer.Option("answer", "--type", help="answer / article"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """收藏回答或文章到指定收藏夹。"""
    _confirm(yes, f"收藏 {content_type} {content_id} 到收藏夹 {collection}")
    client = require_client(ctx)
    with client:
        data = client.collection_add(collection, content_id, content_type)
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("uncollect")
def uncollect(
    ctx: typer.Context,
    content_id: int = typer.Argument(..., help="内容 ID"),
    collection: int = typer.Option(..., "--collection", "-c", help="收藏夹 ID"),
    content_type: str = typer.Option("answer", "--type", help="answer / article"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """从收藏夹移除回答或文章。"""
    _confirm(yes, f"从收藏夹 {collection} 移除 {content_type} {content_id}")
    client = require_client(ctx)
    with client:
        data = client.collection_remove(collection, content_id, content_type)
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("delete-comment")
def delete_comment(
    ctx: typer.Context,
    comment_id: int = typer.Argument(..., help="评论 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除自己发表的评论。"""
    _confirm(yes, f"删除评论 {comment_id}")
    client = require_client(ctx)
    with client:
        data = client.delete_comment(comment_id)
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("follow")
def follow(
    ctx: typer.Context,
    member: str = typer.Option(None, "--user", help="用户 url_token"),
    question_id: int = typer.Option(None, "--question", help="问题 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """关注用户或问题。"""
    if bool(member) == bool(question_id):
        raise typer.BadParameter("请且仅请指定 --user 或 --question")
    path = f"/api/v4/members/{member}/followers" if member else f"/api/v4/questions/{question_id}/followers"
    _confirm(yes, f"关注 {'用户 ' + member if member else '问题 ' + str(question_id)}")
    client = require_client(ctx)
    with client:
        data = client.post(path, json_body={})
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("unfollow")
def unfollow(
    ctx: typer.Context,
    member: str = typer.Option(None, "--user", help="用户 url_token"),
    question_id: int = typer.Option(None, "--question", help="问题 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """取消关注用户或问题。"""
    if bool(member) == bool(question_id):
        raise typer.BadParameter("请且仅请指定 --user 或 --question")
    path = f"/api/v4/members/{member}/followers" if member else f"/api/v4/questions/{question_id}/followers"
    _confirm(yes, "取消关注")
    client = require_client(ctx)
    with client:
        data = client.delete(path)
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("comment")
def comment(
    ctx: typer.Context,
    content: str = typer.Option(None, "--content", "-m", help="评论内容"),
    answer_id: int = typer.Option(None, "--answer", help="回答 ID"),
    article_id: int = typer.Option(None, "--article", help="文章 ID"),
    edit: bool = typer.Option(False, "--edit", "-e", help="用 Markdown 编辑器写评论"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """在回答或文章下发表评论（评论不支持图片）。"""
    if bool(answer_id) == bool(article_id):
        raise typer.BadParameter("请且仅请指定 --answer 或 --article")
    if edit:
        markdown = edit_text(BODY_TEMPLATE)
        if is_cancelled(markdown, BODY_TEMPLATE):
            console.print("已取消。")
            return
        if has_local_images(markdown):
            console.print("[yellow]提示[/yellow] 知乎评论不支持图片，图片已被忽略。")
        content = to_plain_text(markdown)
    if not content:
        raise typer.BadParameter("需要 --content 或 --edit")
    kind = "answers" if answer_id else "articles"
    content_id = answer_id or article_id
    _confirm(yes, f"评论 {kind[:-1]} {content_id}：{content[:20]}…")
    client = require_client(ctx)
    with client:
        data = client.post(
            f"/api/v4/{kind}/{content_id}/comments",
            json_body={"content": content, "type": "comment"},
        )
    console.print(f"[green]完成[/green] {data}")


@actions_app.command("publish")
def publish(
    ctx: typer.Context,
    question_id: int = typer.Argument(..., help="问题 ID"),
    content: str = typer.Option(None, "--content", "-m", help="回答正文（HTML）"),
    content_file: Path = typer.Option(None, "--file", "-f", help="从文件读取回答正文"),
    edit: bool = typer.Option(False, "--edit", "-e", help="用 Markdown 编辑器写回答（支持图片）"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """在问题下发布回答（正文为知乎 HTML）。"""
    client = require_client(ctx)
    with client:
        if edit:
            markdown = edit_text(BODY_TEMPLATE)
            if is_cancelled(markdown, BODY_TEMPLATE):
                console.print("已取消。")
                return
            content = markdown_to_html(markdown, client, "answer")
        elif content_file:
            content = content_file.read_text(encoding="utf-8")
        if not content:
            raise typer.BadParameter("需要 --content、--file 或 --edit")
        _confirm(yes, f"在问题 {question_id} 发布回答（{len(content)} 字）")
        data = client.post(
            f"/api/v4/questions/{question_id}/answers",
            json_body={"content": content, "resume": False},
        )
    console.print(f"[green]完成[/green] {data}")
