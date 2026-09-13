"""Self-upgrade: detect how zhihu-cli was installed and run the matching command."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from .exceptions import ZhihuError


def _run(cmd: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str] | None:
    """Run a command, returning ``None`` if the tool is missing or failed to run."""
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        return subprocess.run(
            [exe, *cmd[1:]], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def is_editable_install() -> bool:
    try:
        from importlib.metadata import distribution

        direct_url = distribution("zhihu-cli").read_text("direct_url.json")
        if direct_url:
            return bool(json.loads(direct_url).get("dir_info", {}).get("editable", False))
    except Exception:  # noqa: BLE001, S110 - missing metadata simply means "not editable"
        pass
    return False


def detect_upgrade_command() -> list[str] | None:
    """Return the upgrade command matching the installation method."""
    uv = _run(["uv", "tool", "list"])
    if uv is not None and uv.returncode == 0 and "zhihu-cli" in (uv.stdout or ""):
        return ["uv", "tool", "upgrade", "zhihu-cli"]
    pipx = _run(["pipx", "list"])
    if pipx is not None and pipx.returncode == 0 and "zhihu-cli" in (pipx.stdout or ""):
        return ["pipx", "upgrade", "zhihu-cli"]
    if shutil.which("pip") is not None or shutil.which("pip3") is not None:
        return [sys.executable, "-m", "pip", "install", "--upgrade", "zhihu-cli"]
    return None


def upgrade(*, assume_yes: bool = False) -> int:
    """Run the upgrade command; returns the subprocess exit code."""
    if is_editable_install():
        raise ZhihuError(
            "当前为源码（editable）安装：请 git pull 后运行 uv sync 完成升级"
        )
    cmd = detect_upgrade_command()
    if cmd is None:
        raise ZhihuError(
            "无法识别安装方式（未找到 uv tool / pipx）；"
            "请手动运行 pip install --upgrade zhihu-cli"
        )
    if not assume_yes:
        answer = input(f"运行 {' '.join(cmd)} ？[y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消。")
            return 0
    # Inherit stdio so the installer's own progress output streams through.
    proc = subprocess.run(cmd, check=False)
    return proc.returncode
