"""Login by reusing the user's existing Microsoft Edge session.

Modern Edge encrypts cookies with app-bound encryption, so reading the cookie
database offline (or from a *copy* of the profile) does not work.  Instead we
launch Edge with the **real** profile and a CDP debugging port; Edge decrypts
its own cookies, and we read the Zhihu ones over the DevTools protocol.

This requires Edge to be closed while we run (otherwise the new process is
forwarded to the running instance and never opens the debug port).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .exceptions import ZhihuError
from .session import Credentials

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT = 9345

_PS_SCRIPT = r"""
param([int]$Port = __PORT__)
$ErrorActionPreference = 'Stop'
$exe = 'EDGE_EXE_PLACEHOLDER'
$ud = Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data'
if (-not (Test-Path $exe)) { Write-Output 'ERR:edge-not-found'; exit 1 }
if (Get-Process msedge -ErrorAction SilentlyContinue) { Write-Output 'ERR:edge-running'; exit 1 }
$p = Start-Process -FilePath $exe -PassThru -ArgumentList @(
  "--remote-debugging-port=$Port", "--user-data-dir=$ud",
  '--no-first-run', '--headless=new', 'about:blank')
function Cleanup { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
$wsUrl = $null
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 500
  try { $wsUrl = (Invoke-RestMethod "http://127.0.0.1:$Port/json/version").webSocketDebuggerUrl; break } catch {}
}
if (-not $wsUrl) { Cleanup; Write-Output 'ERR:no-debug-endpoint'; exit 1 }
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync([Uri]$wsUrl, [Threading.CancellationToken]::None).Wait()
$bytes = [Text.Encoding]::UTF8.GetBytes('{"id":1,"method":"Storage.getCookies"}')
$seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$bytes)
$ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).Wait()
$buf = New-Object byte[] 4194304
$sb = New-Object System.Text.StringBuilder
do {
  $rseg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buf)
  $res = $ws.ReceiveAsync($rseg, [Threading.CancellationToken]::None).Result
  [void]$sb.Append([Text.Encoding]::UTF8.GetString($buf, 0, $res.Count))
} while (-not $res.EndOfMessage)
$ws.Dispose()
Cleanup
Write-Output $sb.ToString()
"""


def _run_powershell(script: str, timeout: float = 120.0) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        path = handle.name
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _to_windows(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ZhihuError(f"调用 PowerShell 失败：{exc}") from exc
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass


def _to_windows(linux_path: str) -> str:
    try:
        out = subprocess.run(
            ["wslpath", "-w", linux_path], capture_output=True, text=True, check=False, timeout=10
        )
        return out.stdout.strip() or linux_path
    except (OSError, subprocess.SubprocessError):
        return linux_path


def edge_login(timeout: float = 120.0) -> Credentials:
    """Read Zhihu cookies from a debug-launched Edge using the user's real profile."""
    script = _PS_SCRIPT.replace("EDGE_EXE_PLACEHOLDER", EDGE_EXE).replace("__PORT__", str(DEBUG_PORT))
    output = _run_powershell(script, timeout=timeout).strip()
    if output.startswith("ERR:edge-running"):
        raise ZhihuError("检测到 Edge 正在运行：请先完全关闭 Edge，再执行 `zhihu login --edge`")
    if output.startswith("ERR:edge-not-found"):
        raise ZhihuError("未找到 Microsoft Edge（默认路径 Program Files (x86)）")
    if output.startswith("ERR:"):
        raise ZhihuError(f"Edge 登录失败：{output}")

    try:
        payload = json.loads(output)
        cookies = payload.get("result", {}).get("cookies", [])
    except ValueError as exc:
        raise ZhihuError(f"解析 Edge Cookie 失败：{output[:200]}") from exc

    cookies = {
        c["name"]: c["value"]
        for c in cookies
        if "zhihu" in str(c.get("domain", "")) and c.get("value")
    }
    if not cookies.get("z_c0"):
        raise ZhihuError("Edge 中未找到知乎登录态（z_c0）；请先在 Edge 登录知乎后重试")
    return Credentials(cookies=cookies)
