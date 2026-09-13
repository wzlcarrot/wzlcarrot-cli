"""Login through Microsoft Edge by opening a browser window.

Launches Edge (its own dedicated profile, so your normal Edge is untouched) with
a DevTools debugging port, opens the Zhihu sign-in page, and waits until you log
in — then reads the cookies over CDP (Edge decrypts them itself).

The dedicated profile persists, so after the first login subsequent runs are
effectively instant.  No need to close your normal Edge.
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

_PS_EDGE_PROFILE = r"""
param([int]$Port = __PORT__, [int]$TimeoutSec = 240)
$ErrorActionPreference = 'Stop'
$exe = 'EDGE_EXE_PLACEHOLDER'
if (-not (Test-Path $exe)) { Write-Output 'ERR:edge-not-found'; exit 1 }
$ud = Join-Path $env:LOCALAPPDATA 'wzlcarrot-cli\edge-profile'
New-Item -ItemType Directory -Force -Path $ud | Out-Null
$p = Start-Process -FilePath $exe -PassThru -ArgumentList @(
  "--remote-debugging-port=$Port", "--user-data-dir=$ud", '--no-first-run',
  'https://www.zhihu.com/signin?next=%2F')
function Cleanup {
  Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like '*wzlcarrot-cli*edge-profile*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
$wsUrl = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try { $wsUrl = (Invoke-RestMethod "http://127.0.0.1:$Port/json/version").webSocketDebuggerUrl; break } catch {}
}
if (-not $wsUrl) { Cleanup; Write-Output 'ERR:no-debug-endpoint'; exit 1 }
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync([Uri]$wsUrl, [Threading.CancellationToken]::None).Wait()
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$id = 0
$found = $null
while ((Get-Date) -lt $deadline) {
  $id++
  $bytes = [Text.Encoding]::UTF8.GetBytes('{"id":' + $id + ',"method":"Storage.getCookies"}')
  $seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$bytes)
  $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).Wait()
  $buf = New-Object byte[] 4194304
  $sb = New-Object System.Text.StringBuilder
  do {
    $rseg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buf)
    $res = $ws.ReceiveAsync($rseg, [Threading.CancellationToken]::None).Result
    [void]$sb.Append([Text.Encoding]::UTF8.GetString($buf, 0, $res.Count))
  } while (-not $res.EndOfMessage)
  $text = $sb.ToString()
  if ($text -match 'z_c0') { $found = $text; break }
  Start-Sleep -Seconds 2
}
$ws.Dispose()
Cleanup
if ($found) { Write-Output $found } else { Write-Output 'ERR:timeout' }
"""

_PS_REUSE_PROFILE = r"""
param([int]$Port = __PORT__)
$ErrorActionPreference = 'Stop'
$exe = 'EDGE_EXE_PLACEHOLDER'
if (-not (Test-Path $exe)) { Write-Output 'ERR:edge-not-found'; exit 1 }
if (Get-Process msedge -ErrorAction SilentlyContinue) { Write-Output 'ERR:edge-running'; exit 1 }
$ud = Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data'
$p = Start-Process -FilePath $exe -PassThru -ArgumentList @(
  "--remote-debugging-port=$Port", "--user-data-dir=$ud", '--no-first-run', '--headless=new', 'about:blank')
function Cleanup {
  Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like '*--remote-debugging-port=__PORT__*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
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


def _run_powershell(script: str, timeout: float) -> str:
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


def _cookies_from_output(output: str) -> dict[str, str] | None:
    try:
        payload = json.loads(output)
        cookies = payload.get("result", {}).get("cookies", [])
    except (ValueError, AttributeError):
        return None
    return {
        c["name"]: c["value"]
        for c in cookies
        if "zhihu" in str(c.get("domain", "")) and c.get("value")
    }


def edge_login(*, timeout: int = 240, reuse_profile: bool = False) -> Credentials:
    """Open Edge, let the user log in, and capture the Zhihu cookies.

    By default a dedicated Edge profile is used (your normal Edge is untouched
    and can stay open).  With ``reuse_profile=True`` the real Edge profile is
    used instead, which requires Edge to be closed.
    """
    if reuse_profile:
        script = _PS_REUSE_PROFILE.replace("EDGE_EXE_PLACEHOLDER", EDGE_EXE).replace(
            "__PORT__", str(DEBUG_PORT)
        )
        output = _run_powershell(script, timeout=120).strip()
    else:
        script = (
            _PS_EDGE_PROFILE.replace("EDGE_EXE_PLACEHOLDER", EDGE_EXE)
            .replace("__PORT__", str(DEBUG_PORT))
            .replace("[int]$TimeoutSec = 240", f"[int]$TimeoutSec = {timeout}")
        )
        output = _run_powershell(script, timeout=timeout + 30).strip()

    if output.startswith("ERR:edge-running"):
        raise ZhihuError(
            "检测到 Edge 正在运行：复用现有配置需先完全关闭 Edge；"
            "直接 `zhihu login --edge`（不加 --reuse）会另开独立窗口，无需关闭。"
        )
    if output.startswith("ERR:edge-not-found"):
        raise ZhihuError("未找到 Microsoft Edge（默认路径 Program Files (x86)）")
    if output.startswith("ERR:timeout"):
        raise ZhihuError("等待登录超时：请在打开的 Edge 窗口内登录知乎后重试")
    if output.startswith("ERR:"):
        raise ZhihuError(f"Edge 登录失败：{output}")

    cookies = _cookies_from_output(output)
    if cookies is None:
        raise ZhihuError(f"解析 Edge Cookie 失败：{output[:200]}")
    if not cookies.get("z_c0"):
        raise ZhihuError("Edge 中未找到知乎登录态（z_c0）；请在打开的窗口里登录知乎后重试")
    return Credentials(cookies=cookies)
