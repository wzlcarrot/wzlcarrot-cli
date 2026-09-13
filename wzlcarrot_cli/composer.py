"""Markdown composition workflow.

``--edit`` opens a Markdown editor so the user can write text and reference
local images (``![](/path/to.png)``).  On save we upload the images and convert
the Markdown to the rich HTML Zhihu expects.

Editor resolution order:
  1. ``$WZLCARROT_CLI_EDITOR``  — a shell command template containing ``{file}``
  2. Auto-detected MarkText (Windows GUI, launched from WSL)
  3. ``$EDITOR`` / ``$VISUAL`` / ``nano`` (terminal editor)
"""

from __future__ import annotations

import functools
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import env
from .exceptions import ZhihuError
from .output import console

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_REMOTE = ("http://", "https://")
MARKTEXT_SHORTCUT = r"C:\Users\Public\Desktop\MarkText.lnk"

ASK_TEMPLATE = """# 在这里写标题（提问/想法/文章）

在这里写正文，支持 Markdown：**加粗**、`代码`、列表、> 引用。

插入本地图片（路径可以是绝对或相对当前目录）：
![](/absolute/path/to/image.png)

保存并退出编辑器即可发布；把整段内容删空可取消。
"""

BODY_TEMPLATE = """在这里写正文，支持 Markdown。

插入本地图片（路径可以是绝对或相对当前目录）：
![](/absolute/path/to/image.png)

保存后回到终端按回车提交；把内容删空可取消。
"""


@dataclass
class Editor:
    argv: list[str]  # may contain the literal "{file}"
    gui: bool = False
    windows_path: bool = False


def _wslpath(flag: str, value: str) -> str | None:
    try:
        out = subprocess.run(
            ["wslpath", flag, value], capture_output=True, text=True, check=False, timeout=10
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@functools.lru_cache(maxsize=1)
def _resolve_marktext() -> Editor | None:
    target = None
    try:
        ps = (
            "(New-Object -ComObject WScript.Shell)"
            f".CreateShortcut('{MARKTEXT_SHORTCUT}').TargetPath"
        )
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, check=False, timeout=20,
        )
        target = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        target = None

    win_exe = target or r"D:\markText\MarkText.exe"
    linux_exe = _wslpath("-u", win_exe) if target else "/mnt/d/markText/MarkText.exe"
    if not linux_exe or not Path(linux_exe).exists():
        return None
    return Editor(argv=[win_exe, "{file}"], gui=True, windows_path=True)


@functools.lru_cache(maxsize=1)
def _windows_temp_dir() -> Path | None:
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "Write-Output $env:TEMP"],
            capture_output=True, text=True, check=False, timeout=15,
        )
        win_temp = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not win_temp:
        return None
    linux_temp = _wslpath("-u", win_temp)
    if not linux_temp:
        return None
    try:
        Path(linux_temp).mkdir(parents=True, exist_ok=True)
        return Path(linux_temp)
    except OSError:
        return None


def resolve_editor() -> Editor:
    template = env("EDITOR")
    if template:
        argv = shlex.split(template)
        is_windows = argv and argv[0].lower().endswith(".exe")
        if not any("{file}" in part for part in argv):
            argv.append("{file}")
        return Editor(
            argv=argv, gui=is_windows or "marktext" in template.lower(), windows_path=is_windows
        )
    marktext = _resolve_marktext()
    if marktext:
        return marktext
    return Editor(argv=[os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano", "{file}"])


class EditorSession:
    """A temporary Markdown file opened in the resolved editor.

    ``open()`` returns immediately for GUI editors (MarkText) and blocks for
    terminal editors.  Callers decide how to wait (Enter prompt or a TUI modal).
    """

    def __init__(self, template: str) -> None:
        self.editor = resolve_editor()
        work_dir = _windows_temp_dir() if self.editor.windows_path else None
        fd, name = tempfile.mkstemp(
            suffix=".md", prefix="zhihu-", dir=str(work_dir) if work_dir else None
        )
        os.close(fd)
        self.path = Path(name)
        self.path.write_text(template, encoding="utf-8")

    @property
    def is_gui(self) -> bool:
        return self.editor.gui

    def open(self) -> None:
        if self.editor.windows_path:
            win_file = _wslpath("-w", str(self.path)) or str(self.path)
            argv = [part.replace("{file}", win_file) for part in self.editor.argv]
            subprocess.Popen(["cmd.exe", "/c", "start", "", *argv])
        else:
            argv = [part.replace("{file}", str(self.path)) for part in self.editor.argv]
            try:
                subprocess.run(argv, check=False)
            except FileNotFoundError as exc:
                raise ZhihuError(f"找不到编辑器 {argv[0]!r}，请设置 $WZLCARROT_CLI_EDITOR") from exc

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def close(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def edit_text(template: str) -> str:
    """Open the editor and block until the user is done (terminal flow)."""
    session = EditorSession(template)
    try:
        session.open()
        if session.is_gui:
            console.print("已在 MarkText 打开。编辑并保存后，回到终端按回车继续…")
            input()
        return session.read()
    finally:
        session.close()


def split_title(markdown: str) -> tuple[str, str]:
    """Split a leading ``# title`` heading from the body."""
    match = _TITLE_RE.search(markdown)
    if not match:
        return "", markdown.strip()
    title = match.group(1).strip()
    body = _TITLE_RE.sub("", markdown, count=1).strip()
    return title, body


def has_local_images(markdown: str) -> bool:
    return any(not url.startswith(_REMOTE) for _, url in _IMG_RE.findall(markdown))


def is_blank(markdown: str) -> bool:
    cleaned = re.sub(r"^#.*$", "", markdown, flags=re.MULTILINE)
    return not cleaned.strip()


def is_cancelled(markdown: str, template: str) -> bool:
    """True when the user left the template untouched or emptied it."""
    return is_blank(markdown) or markdown.strip() == template.strip()


def markdown_to_html(markdown: str, client, source: str) -> str:
    """Upload local images and render Markdown to Zhihu-compatible HTML."""

    def replace(match: re.Match[str]) -> str:
        target = match.group(2)
        if target.startswith(_REMOTE):
            return match.group(0)
        console.print(f"[dim]上传图片 {target} …[/dim]")
        info = client.upload_image(target, source=source)
        return client._build_img_html([info])

    markdown = _IMG_RE.sub(replace, markdown)
    from markdown_it import MarkdownIt

    return MarkdownIt("commonmark", {"html": True}).render(markdown).strip()


def to_plain_text(markdown: str) -> str:
    """Best-effort strip of Markdown for text-only targets (comments)."""
    text = _IMG_RE.sub("", markdown)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`>~]", "", text)
    return re.sub(r"\n{2,}", "\n", text).strip()
