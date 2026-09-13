"""Environment self-check used by ``zhihu doctor``."""

from __future__ import annotations

from . import __version__
from .exceptions import ZhihuError
from .hooks import load_hooks
from .llm import resolve_llm_config
from .plugins import load_plugins
from .session import Credentials
from .sessions import list_sessions
from .spill import list_spills

Check = tuple[str, bool, str]


def run_checks(*, check_network: bool = True) -> list[Check]:
    checks: list[Check] = [("版本", True, __version__)]

    credentials = Credentials.load()
    logged_in = credentials.is_logged_in()
    checks.append(("登录凭证", logged_in, "已保存" if logged_in else "运行 zhihu login --qr"))

    try:
        config = resolve_llm_config()
        checks.append(("模型配置", True, f"{config.model} @ {config.base_url}"))
    except ZhihuError as exc:
        checks.append(("模型配置", False, str(exc).splitlines()[0]))

    api = load_plugins()
    checks.append(("插件", True, str(len(api.plugins))))
    checks.append(("钩子", True, str(len(load_hooks(api.hooks).entries()))))
    checks.append(("溢出文件", True, str(len(list_spills()))))
    checks.append(("会话", True, str(len(list_sessions()))))

    if check_network and logged_in:
        from .client import ZhihuClient
        from .exceptions import (
            AntiAbuseError,
            NotLoggedInError,
            SignatureError,
        )

        try:
            client = ZhihuClient(credentials, min_delay=0, max_delay=0, min_gap=0)
            try:
                me = client.me()
                checks.append(("知乎连通", True, str(me.get("name", ""))))
                checks.append(("签名自检", True, "x-zse-96 签名被服务端接受"))
            finally:
                client.close()
        except SignatureError as exc:
            checks.append(("知乎连通", False, "请求被拒绝"))
            checks.append(("签名自检", False, str(exc).splitlines()[0][:80]))
        except NotLoggedInError as exc:
            checks.append(("知乎连通", False, str(exc)[:60]))
            checks.append(("签名自检", False, f"无法验证（{str(exc).splitlines()[0][:40]}）"))
        except AntiAbuseError:
            checks.append(("知乎连通", False, "触发反爬限制"))
            checks.append(("签名自检", False, "无法验证（反爬冷却中，请稍后再试）"))
        except ZhihuError as exc:
            checks.append(("知乎连通", False, str(exc)[:60]))
            checks.append(("签名自检", False, f"无法验证（{str(exc)[:40]}）"))

    return checks
