"""Full-screen Textual TUI, styled after Claude Code's coding-agent interface."""

from __future__ import annotations

import json
import threading
import time
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from . import sessions as sessions_mod
from . import todo as todo_store
from .composer import EditorSession
from .llm import LLMConfig, save_llm_config
from .providers import PROVIDERS, get_provider

COMMANDS: list[tuple[str, str]] = [
    ("/connect", "配置模型供应商与 API Key"),
    ("/platform", "切换平台（知乎 / 微博 / 小红书…）"),
    ("/model", "查看当前模型"),
    ("/stats", "本次会话 token 用量与统计"),
    ("/todos", "查看任务清单"),
    ("/compact", "压缩上下文"),
    ("/copy", "复制上一条回答到剪贴板"),
    ("/sessions", "列出已保存的会话"),
    ("/new", "开始新会话"),
    ("/help", "显示全部命令"),
    ("/clear", "清屏"),
    ("/quit", "退出"),
]

# Claude's warm palette
ACCENT = "#d97757"
ACCENT_SOFT = "#cc785c"
BG = "#1f1e1d"
BG_PANEL = "#262624"
BG_INPUT = "#2a2927"
TEXT = "#e8e6e3"
MUTED = "#8a877f"
GREEN = "#7fb069"
RED = "#e06c75"

# 5x5 pixel glyphs used to draw the "WZLCARROT" wordmark.
PIXEL_FONT: dict[str, tuple[str, ...]] = {
    "W": ("█   █", "█   █", "█ █ █", "█ █ █", " █ █ "),
    "Z": ("█████", "   █ ", "  █  ", " █   ", "█████"),
    "L": ("█    ", "█    ", "█    ", "█    ", "█████"),
    "C": (" ███ ", "█   █", "█    ", "█   █", " ███ "),
    "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
    "R": ("████ ", "█   █", "████ ", "█ █  ", "█  █ "),
    "O": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
}


def _mix(c1: str, c2: str, t: float) -> str:
    """Blend two ``#rrggbb`` colors by ``t`` in [0, 1]."""
    a = tuple(int(c1[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _word_art(word: str, start: str = GREEN, end: str = ACCENT) -> str:
    """Draw ``word`` with the block pixel font, gradient from ``start`` to ``end``."""
    shape = [PIXEL_FONT[ch.upper()] for ch in word]
    colors = [_mix(start, end, i / max(len(shape) - 1, 1)) for i in range(len(shape))]
    lines = []
    for row in range(5):
        lines.append(" ".join(f"[{color}]{glyph[row]}[/]" for glyph, color in zip(shape, colors)))
    return "\n".join(lines)


def _compact_welcome(platform: str = "", accent: str = ACCENT) -> str:
    """One-line header used on narrow terminals and after the first message."""
    tool = f" [{MUTED}]· {platform}[/]" if platform else ""
    return f"[bold {accent}]WZLCARROT[/]{tool}  [{MUTED}]多平台 AI CLI · 输入 / 查看命令[/]"


def _welcome_text(platform: str = "", accent: str = ACCENT, tagline: str = "") -> str:
    """Pixel wordmark + hints, in the spirit of Claude Code's start screen."""
    tool = f"[{accent}]· {platform}[/]\n" if platform else ""
    text = tagline or "用中文对话，自动调用平台接口取真实数据"
    return (
        f"{_word_art('WZLCARROT', end=accent)}\n"
        f"[bold {MUTED}]多平台 AI CLI[/]\n"
        f"{tool}"
        f"[{MUTED}]{text}[/]\n\n"
        f"[{MUTED}]试着说：[/]\n"
        f"[{MUTED}]  › 看看今天热榜前5[/]\n"
        f"[{MUTED}]  › 搜一下 transformers 有哪些高赞回答[/]\n"
        f"[{MUTED}]  › 把第2条问题的回答导出成 markdown[/]"
    )


WELCOME = _welcome_text()

CSS = f"""
Screen {{ background: {BG}; color: {TEXT}; }}
#chat {{ height: 1fr; padding: 1 2 0 2; scrollbar-size-vertical: 1; }}

#welcome {{
    border: round $wz_accent;
    background: {BG_PANEL};
    padding: 1 2;
    margin: 1 0 0 0;
}}

#welcome.compact {{
    border: none;
    background: transparent;
    padding: 0;
    margin: 1 0 0 0;
}}

.user {{
    color: {TEXT};
    background: {BG_PANEL};
    border-left: thick $wz_accent;
    padding: 0 1;
    margin: 1 0 0 0;
}}

.assistant {{ margin: 1 0 0 0; }}

.tool {{ color: {TEXT}; margin: 0 0 0 2; }}
.error {{ color: {RED}; margin: 0 0 0 2; }}
.thinking {{ color: {MUTED}; margin: 0 0 0 2; }}

#input-area {{ height: auto; padding: 0 2; }}
#todos {{ height: auto; max-height: 6; color: {MUTED}; padding: 0 2 0 3; display: none; }}
#commands {{ height: auto; max-height: 12; border: round $wz_accent_soft; background: {BG_PANEL}; padding: 0 1; margin: 0 2; display: none; }}
#input-row {{
    height: 3;
    border: round $wz_accent_soft;
    background: {BG_INPUT};
}}
#input-row:focus-within {{ border: round $wz_accent; }}
#prompt-mark {{
    width: 3;
    content-align: center middle;
    color: $wz_accent;
    text-style: bold;
}}
#prompt {{ border: none; background: {BG_INPUT}; padding: 0 0; height: 1; }}
#bottom {{ height: 1; }}
#mode {{ width: 1fr; color: {MUTED}; padding: 0 0 0 2; }}
#status {{ width: 1fr; text-align: right; color: {MUTED}; padding: 0 2 0 0; }}

ConfirmScreen {{ align: center middle; background: {BG} 60%; }}
#confirm-box {{
    width: 72;
    border: round $wz_accent;
    background: {BG_PANEL};
    padding: 1 2;
}}
#confirm-title {{ color: $wz_accent; text-style: bold; }}
#confirm-body {{ color: {TEXT}; margin: 1 0; }}
#confirm-buttons {{ height: auto; align: center middle; }}
Button {{ margin: 0 1; }}

ConnectScreen {{ align: center middle; background: {BG} 60%; }}
#connect-box {{
    width: 84;
    max-height: 90%;
    border: round $wz_accent;
    background: {BG_PANEL};
    padding: 1 2;
}}
#connect-step1, #connect-step2 {{ height: auto; }}
#provider-list {{ height: auto; max-height: 10; margin: 1 0; background: {BG_PANEL}; }}
#provider-list > .option-list--option-highlighted {{ background: $wz_accent; color: {BG}; text-style: bold; }}
#connect-box Input {{ border: round $wz_accent_soft; background: {BG_INPUT}; margin: 0 0 1 0; }}

PlatformScreen {{ align: center middle; background: {BG} 60%; }}
#platform-box {{
    width: 72;
    height: auto;
    max-height: 90%;
    border: round $wz_accent;
    background: {BG_PANEL};
    padding: 1 2;
}}
#platform-list {{ height: auto; max-height: 12; margin: 1 0; background: {BG_PANEL}; }}
#platform-list > .option-list--option-highlighted {{ background: $wz_accent; color: {BG}; text-style: bold; }}

ToastRack {{ dock: top; align: right top; margin: 0 1 0 0; }}
Toast {{ width: auto; max-width: 60%; padding: 0 1; }}
"""


def _format_args(args_json: str) -> str:
    try:
        data = json.loads(args_json)
    except ValueError:
        return args_json
    if not isinstance(data, dict) or not data:
        return ""
    return "(" + ", ".join(f"{k}={v}" for k, v in data.items()) + ")"


class Thinking(Static):
    """Animated 'thinking' indicator shown while the model is working."""

    FRAMES = ("·  ", "·· ", "···")

    def __init__(self, accent: str = ACCENT) -> None:
        super().__init__(classes="thinking")
        self._accent = accent
        self._index = 0

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.35, self._tick)
        self._tick()

    def _tick(self) -> None:
        dots = self.FRAMES[self._index % len(self.FRAMES)]
        self.update(f"[{self._accent}]✻[/] [{MUTED}]思考中 {dots.strip() or '.'}[/]")
        self._index += 1


class ToolLine(Static):
    """One tool invocation, with a spinner that becomes a check mark."""

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, name: str, args: str, accent: str = ACCENT) -> None:
        super().__init__(classes="tool")
        self._name = name
        self._args = args
        self._accent = accent
        self._index = 0
        self._done = False

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.08, self._tick)
        self._tick()

    def _paint(self, glyph: str, color: str, trail: str = "") -> None:
        text = f"[{color}]{glyph}[/] [{TEXT}]{self._name}[/] [{MUTED}]{self._args}[/]"
        if trail:
            text += f"  [{MUTED}]· {trail}[/]"
        self.update(text)

    def _tick(self) -> None:
        if self._done:
            return
        self._paint(self.SPINNER[self._index % len(self.SPINNER)], self._accent)
        self._index += 1

    def finish(self, ok: bool = True, note: str = "") -> None:
        self._done = True
        if getattr(self, "_timer", None) is not None:
            self._timer.stop()
        self._paint("✓" if ok else "✗", GREEN if ok else RED, note)


class ConfirmScreen(ModalScreen[bool]):
    """Yes/no modal used to confirm write operations."""

    def __init__(self, name: str, args: str) -> None:
        super().__init__()
        self._name = name
        self._args = args

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static("⚠ 确认执行写操作？", id="confirm-title")
            yield Static(f"[bold {TEXT}]{self._name}[/]\n[{MUTED}]{self._args}[/]", id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Button("取消", variant="default", id="no")
                yield Button("确认", variant="error", id="yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class ComposeScreen(ModalScreen[bool]):
    """Shown while the user writes in MarkText."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static("✍ 在 MarkText 中撰写", id="confirm-title")
            yield Static(
                f"[{MUTED}]文件：{self._path}[/]\n\n"
                f"[{TEXT}]编辑并保存后，点击「完成」提交；点击「取消」放弃。[/]",
                id="confirm-body",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("取消", variant="default", id="no")
                yield Button("完成", variant="success", id="yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class ConnectScreen(ModalScreen[tuple[str, str, str] | None]):
    """Two-step wizard: search & pick a provider, then enter the API key."""

    def __init__(self) -> None:
        super().__init__()
        self._provider_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="connect-box"):
            yield Static("连接模型供应商", id="confirm-title")
            with Vertical(id="connect-step1"):
                yield Static(f"[{MUTED}]↑↓ 选择 · 回车确定 · Esc 关闭 · Tab 搜索[/]", id="confirm-body")
                yield Input(placeholder="搜索供应商…", id="c-filter")
                yield OptionList(id="provider-list")
            with Vertical(id="connect-step2"):
                yield Static("", id="c-chosen")
                yield Input(placeholder="OpenAI 兼容 base_url", id="c-base")
                yield Input(placeholder="模型名", id="c-model")
                yield Input(placeholder="API Key", password=True, id="c-key")
                yield Static(f"[{MUTED}]回车确定 · Esc 返回[/]", id="c-tip")

    def on_mount(self) -> None:
        self.query_one("#connect-step2").display = False
        self._fill_providers("")
        self.query_one("#provider-list", OptionList).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "c-filter":
            # Enter in the search box returns focus to the list for keyboard selection.
            self.query_one("#provider-list", OptionList).focus()
        elif event.input.id in ("c-base", "c-model", "c-key"):
            self._save()

    def on_key(self, event) -> None:
        if event.key == "escape":
            if self.query_one("#connect-step2").display:
                self._back_to_list()
            else:
                self.dismiss(None)
            event.stop()
            event.prevent_default()

    def _fill_providers(self, keyword: str) -> None:
        keyword = keyword.strip().lower()
        option_list = self.query_one("#provider-list", OptionList)
        option_list.clear_options()
        options = []
        for provider in PROVIDERS:
            haystack = f"{provider.id} {provider.name}".lower()
            if keyword and keyword not in haystack:
                continue
            options.append(Option(provider.name, id=provider.id))
        option_list.add_options(options)
        if options:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "c-filter":
            self._fill_providers(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._choose(str(event.option.id))

    def _choose(self, provider_id: str) -> None:
        provider = get_provider(provider_id)
        self._provider_id = provider_id
        self.query_one("#connect-step1").display = False
        self.query_one("#connect-step2").display = True
        self.query_one("#c-chosen", Static).update(
            f"已选：[bold]{provider.name if provider else provider_id}[/]"
        )
        is_custom = provider is None or not provider.base_url
        base = self.query_one("#c-base", Input)
        base.display = is_custom  # base_url is hidden for built-in providers
        base.value = provider.base_url if provider else ""
        self.query_one("#c-model", Input).value = (
            provider.models[0] if provider and provider.models else ""
        )
        self.query_one("#c-key", Input).focus()

    def _back_to_list(self) -> None:
        self.query_one("#connect-step2").display = False
        self.query_one("#connect-step1").display = True
        self.query_one("#provider-list", OptionList).focus()

    def _save(self) -> None:
        base_url = self.query_one("#c-base", Input).value.strip()
        model = self.query_one("#c-model", Input).value.strip()
        api_key = self.query_one("#c-key", Input).value.strip()
        if not (base_url and model and api_key):
            self.query_one("#c-tip", Static).update(
                "[red]base_url / 模型 / API Key 不能为空[/]"
            )
            return
        self.dismiss((api_key, base_url, model))


class PlatformScreen(ModalScreen[str | None]):
    """Picker for switching the active platform (implemented ones are enabled)."""

    def __init__(self, platforms=None) -> None:
        super().__init__()
        self._platforms = platforms

    def compose(self) -> ComposeResult:
        with Vertical(id="platform-box"):
            yield Static("切换平台", id="confirm-title")
            yield Static(f"[{MUTED}]↑↓ 选择 · 回车切换 · Esc 关闭[/]", id="confirm-body")
            yield OptionList(id="platform-list")

    def on_mount(self) -> None:
        platforms = self._platforms
        if platforms is None:
            from .platforms import all_platforms

            platforms = all_platforms()
        option_list = self.query_one("#platform-list", OptionList)
        options = []
        for platform in platforms:
            options.append(Option(f"{platform.name}  —  {platform.title}", id=platform.name))
        option_list.add_options(options)
        if options:
            option_list.highlighted = 0
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.id))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
            event.prevent_default()


class ChatTUI(App):
    CSS = CSS
    # Class-level defaults so get_css_variables() works during App.__init__.
    _accent = ACCENT
    _accent_soft = ACCENT_SOFT
    BINDINGS: ClassVar = [
        Binding("ctrl+c", "interrupt", "退出", show=False, priority=True),
        Binding("shift+tab", "toggle_mode", "模式", show=False, priority=True),
        Binding("ctrl+l", "clear", "清屏"),
        Binding("escape", "smart_escape", "取消/输入", show=False),
    ]

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        variables["wz_accent"] = self._accent
        variables["wz_accent_soft"] = self._accent_soft
        return variables

    def on_key(self, event) -> None:
        # Command-menu navigation only while typing in the prompt; otherwise
        # let keys reach whatever has focus (e.g. the connect modal's list).
        prompt = self.query_one("#prompt", Input)
        if not (prompt.has_focus and self._command_matches and not self._busy):
            return
        if event.key == "up":
            self.action_command_up()
        elif event.key == "down":
            self.action_command_down()
        elif event.key == "tab":
            self.action_complete_command()
        else:
            return
        event.stop()
        event.prevent_default()

    def __init__(
        self,
        agent,
        subtitle: str = "",
        user: str = "",
        platform: str = "",
        platform_name: str = "",
        accent: str = ACCENT,
        tagline: str = "",
        switch=None,
        platforms=None,
    ) -> None:
        self._accent = accent or ACCENT
        self._accent_soft = _mix(self._accent, BG, 0.45)
        super().__init__()
        self._agent = agent
        self._subtitle = subtitle
        self._user = user
        self._platform = platform
        self._platform_name = platform_name or platform
        self._tagline = tagline
        self._switch = switch
        self._platforms = platforms
        self._assistant: Markdown | None = None
        self._assistant_text = ""
        self._thinking: Thinking | None = None
        self._tools: list[ToolLine] = []
        self._busy = False
        self._cancel_event = threading.Event()
        self._command_matches: list[tuple[str, str]] = []
        self._command_index = 0
        self._last_ctrl_c = 0.0
        self._mode = "build"
        self._last_reply = ""
        agent._confirm_fn = self._confirm  # let the agent ask through the UI
        agent._compose_fn = self._compose  # let the agent open MarkText

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="chat"):
            yield Static(
                _welcome_text(self._platform, self._accent, self._tagline), id="welcome"
            )
        yield Static("", id="todos")
        yield Static("", id="commands")
        with Vertical(id="input-area"), Horizontal(id="input-row"):
            yield Static("›", id="prompt-mark")
            yield Input(placeholder="给 WZLCARROT 下达指令…  (输入 / 查看命令)", id="prompt")
        with Horizontal(id="bottom"):
            yield Static(self._mode_text(), id="mode")
            yield Static(self._status_text(), id="status")

    def _status_text(self) -> str:
        who = f" · @{self._user}" if self._user else ""
        stats = self._agent.stats()
        tokens = stats.get("total_tokens") or stats.get("context_tokens") or 0
        return f"{self._subtitle}{who} · {tokens} tokens"

    def _mode_text(self) -> str:
        mode = "[#7fb069]● build[/]" if self._mode == "build" else f"[{self._accent}]● plan[/]"
        who = f"  [{MUTED}]· {self._platform}[/]" if self._platform else ""
        return mode + who

    def action_toggle_mode(self) -> None:
        if len(self.screen_stack) > 1:  # ignore while a modal is open
            return
        self._mode = "plan" if self._mode == "build" else "build"
        self._agent.plan_mode = self._mode == "plan"
        if self._agent.messages:
            self._agent.messages[0] = {
                "role": "system",
                "content": self._agent._system_prompt(),
            }
        self.query_one("#mode", Static).update(self._mode_text())

    def on_mount(self) -> None:
        self.title = f"WZLCARROT · {self._platform}" if self._platform else "WZLCARROT"
        if self.size.width and self.size.width < 66:  # keep the art from wrapping
            self._collapse_welcome()
        self.query_one("#prompt", Input).focus()

    def _collapse_welcome(self) -> None:
        """Shrink the start banner to one line (narrow screen or first message)."""
        try:
            welcome = self.query_one("#welcome", Static)
        except Exception:  # noqa: BLE001 - welcome may already be gone
            return
        welcome.update(_compact_welcome(self._platform, self._accent))
        welcome.add_class("compact")

    def action_focus_input(self) -> None:
        self.query_one("#prompt", Input).focus()

    def action_smart_escape(self) -> None:
        # Esc cancels an in-flight generation; otherwise it refocuses the input.
        if self._busy and not self._cancel_event.is_set():
            self._cancel_event.set()
            self.notify("正在取消…（等待模型停止输出）", timeout=2, severity="warning")
            return
        self.action_focus_input()

    def action_interrupt(self) -> None:
        # Ctrl+C first copies a text selection; only with no selection does it
        # fall back to the double-press exit gesture.
        selection = self.screen.get_selected_text()
        if selection:
            self.copy_to_clipboard(selection)
            self.screen.clear_selection()
            self._last_ctrl_c = 0.0
            return
        now = time.time()
        if now - self._last_ctrl_c <= 2.0:
            self.exit()
            return
        self._last_ctrl_c = now
        self.notify("再按一次 Ctrl+C 退出", timeout=2, severity="warning")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_command_menu(event.value)

    def _update_command_menu(self, value: str) -> None:
        if not value.startswith("/"):
            self._command_matches = []
            self.query_one("#commands", Static).display = False
            return
        prefix = value[1:].strip().lower()
        self._command_matches = [(c, d) for c, d in COMMANDS if c[1:].lower().startswith(prefix)]
        self._command_index = 0
        self._render_command_menu()

    def _render_command_menu(self) -> None:
        panel = self.query_one("#commands", Static)
        if not self._command_matches:
            panel.display = False
            return
        self._command_index %= len(self._command_matches)
        lines = []
        for index, (command, desc) in enumerate(self._command_matches):
            if index == self._command_index:
                lines.append(f"[reverse] ▶ {command}  {desc} [/reverse]")
            else:
                lines.append(f"   [bold {self._accent}]{command}[/]  [{MUTED}]{desc}[/]")
        panel.update("\n".join(lines))
        panel.display = True

    def action_command_up(self) -> None:
        if not self._command_matches:
            return
        self._command_index = (self._command_index - 1) % len(self._command_matches)
        self._render_command_menu()

    def action_command_down(self) -> None:
        if not self._command_matches:
            return
        self._command_index = (self._command_index + 1) % len(self._command_matches)
        self._render_command_menu()

    def action_complete_command(self) -> None:
        if not self._command_matches:
            return
        prompt = self.query_one("#prompt", Input)
        prompt.value = self._command_matches[self._command_index][0]
        prompt.cursor_position = len(prompt.value)

    def action_clear(self) -> None:
        self.query_one("#chat", VerticalScroll).remove_children()
        self._assistant = None
        self._assistant_text = ""
        self._thinking = None
        self._tools = []

    @staticmethod
    def _help_text() -> str:
        return "可用命令：\n" + "\n".join(f"{command}  {desc}" for command, desc in COMMANDS)

    def _new_session(self) -> None:
        self._agent.messages = [self._agent.messages[0]]
        self._agent.session_id = sessions_mod.new_session_id()
        self._agent.todos = []
        self._agent.tool_calls = 0
        self._agent.compactions = 0
        self.action_clear()
        self.query_one("#todos", Static).display = False
        self._add_message("tool", f"已开始新会话 {self._agent.session_id}")

    def _open_connect(self) -> None:
        def handle(result: tuple[str, str, str] | None) -> None:
            if result:
                self._apply_connect(*result)

        self.push_screen(ConnectScreen(), handle)

    def _open_platform(self) -> None:
        self.push_screen(PlatformScreen(self._platforms), self._apply_platform)

    def _apply_platform(self, name: str | None) -> None:
        if not name or name == self._platform_name:
            return
        if self._switch is None:
            self.notify("当前无法切换平台", severity="warning")
            return
        try:
            agent, label, accent, tagline, user = self._switch(name)
        except Exception as exc:  # noqa: BLE001 - surface the failure in the UI
            self.notify(f"切换失败：{exc}", severity="error", timeout=6)
            return
        old = self._agent
        self._agent = agent
        agent._confirm_fn = self._confirm
        agent._compose_fn = self._compose
        try:
            old.client.close()
        except Exception:  # noqa: BLE001, S110 - best effort cleanup
            pass
        self._platform_name = name
        self._platform = label
        self._tagline = tagline
        self._user = user
        self._accent = accent or ACCENT
        self._accent_soft = _mix(self._accent, BG, 0.45)
        self.title = f"WZLCARROT · {label}" if label else "WZLCARROT"
        self.refresh_css(animate=False)
        # Fresh conversation: tool sets and prompts differ per platform.
        self._agent.messages = [self._agent.messages[0]]
        self._agent.session_id = sessions_mod.new_session_id()
        self._agent.todos = []
        self._agent.tool_calls = 0
        self._agent.compactions = 0
        self.action_clear()
        self.query_one("#todos", Static).display = False
        self.query_one("#mode", Static).update(self._mode_text())
        self.query_one("#status", Static).update(self._status_text())
        self._add_message("tool", f"✓ 已切换到 {label}（{name}），开始新会话")

    def _apply_connect(self, api_key: str, base_url: str, model: str) -> None:
        save_llm_config(api_key, base_url, model)
        self._agent.llm.config = LLMConfig(api_key=api_key, base_url=base_url, model=model)
        self._subtitle = model
        self.query_one("#status", Static).update(self._status_text())
        self._add_message("tool", f"✓ 已连接模型：{model} @ {base_url}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if self._command_matches and text.startswith("/"):
            text = self._command_matches[self._command_index][0]
        self._command_matches = []
        self.query_one(Input).value = ""
        self.query_one("#commands", Static).display = False
        if not text or self._busy:
            return
        if text in {"exit", "quit", "退出", "/quit", "/exit"}:
            self.exit()
            return
        if text in {"/help", "/?"}:
            self._add_message("tool", self._help_text())
            return
        if text == "/model":
            self._add_message("tool", f"当前模型：{self._subtitle}")
            return
        if text == "/copy":
            if self._last_reply:
                self.copy_to_clipboard(self._last_reply)
                self._add_message("tool", "已复制上一条回答到剪贴板")
            else:
                self._add_message("tool", "还没有可复制的内容。")
            return
        if text == "/sessions":
            rows = sessions_mod.list_sessions()
            if not rows:
                self._add_message("tool", "暂无已保存会话。")
            else:
                body = "\n".join(f"● {s.id}  {s.messages} 条  {s.title}" for s in rows[:10])
                self._add_message("tool", body)
            return
        if text == "/new":
            self._new_session()
            return
        if text == "/clear":
            self.action_clear()
            return
        if text == "/compact":
            self._busy = True
            self.query_one("#prompt", Input).disabled = True
            self._run_compact()
            return
        if text == "/stats":
            stats = self._agent.stats()
            self._add_message(
                "tool",
                f"✻ 请求 {stats['requests']} · 输入 {stats['prompt_tokens']} · "
                f"输出 {stats['completion_tokens']} · 合计 {stats['total_tokens']} tokens · "
                f"工具 {stats['tool_calls']} · 压缩 {stats['compactions']} · "
                f"上下文 ~{stats['context_tokens']} tokens",
            )
            return
        if text == "/todos":
            todos = getattr(self._agent, "todos", [])
            if todos:
                self._add_message("tool", "任务清单：\n" + todo_store.render_plain(todos))
            else:
                self._add_message("tool", "当前无任务清单。")
            return
        if text == "/connect":
            self._open_connect()
            return
        if text == "/platform":
            self._open_platform()
            return
        self._add_message("user", f"› {text}")
        self._start(text)

    # -- UI helpers --------------------------------------------------------

    def _chat(self) -> VerticalScroll:
        return self.query_one("#chat", VerticalScroll)

    def _add_message(self, kind: str, text: str) -> None:
        self._chat().mount(Static(text, classes=kind))
        self._scroll_end()

    def _scroll_end(self) -> None:
        self._chat().scroll_end(animate=False)

    def _show_thinking(self) -> None:
        if self._thinking is None:
            self._thinking = Thinking(self._accent)
            self._chat().mount(self._thinking)
            self._scroll_end()

    def _hide_thinking(self) -> None:
        if self._thinking is not None:
            self._thinking.remove()
            self._thinking = None

    def _start(self, text: str) -> None:
        self._collapse_welcome()
        self._busy = True
        self._cancel_event.clear()
        self._assistant = None
        self._assistant_text = ""
        self._tools = []
        self.query_one("#prompt", Input).disabled = True
        self._show_thinking()
        self._run_agent(text)

    def _confirm(self, name: str, args: str) -> bool:
        result = {"ok": False}
        done = threading.Event()

        def show() -> None:
            def handle(ok: bool | None) -> None:
                result["ok"] = bool(ok)
                done.set()

            self.push_screen(ConfirmScreen(name, args), handle)

        self.call_from_thread(show)
        done.wait()
        return result["ok"]

    def _compose(self, template: str) -> str:
        """Open MarkText and wait for the user to finish inside the TUI."""
        session = EditorSession(template)
        outcome = {"ok": False}
        done = threading.Event()
        try:
            session.open()
            if session.is_gui:

                def show() -> None:
                    def handle(ok: bool | None) -> None:
                        outcome["ok"] = bool(ok)
                        done.set()

                    self.push_screen(ComposeScreen(str(session.path)), handle)

                self.call_from_thread(show)
                done.wait()
            else:  # terminal editor already completed during open()
                outcome["ok"] = True
            return session.read() if outcome["ok"] else ""
        finally:
            session.close()

    @work(thread=True, exclusive=True)
    def _run_compact(self) -> None:
        try:
            info = self._agent.force_compact()
        except Exception as exc:  # noqa: BLE001 - show errors in the UI
            self.call_from_thread(self._on_event, ("error", str(exc)))
            self.call_from_thread(self._finish)
            return
        if info.get("compacted"):
            self.call_from_thread(self._on_event, ("compact", info))
        else:
            self.call_from_thread(
                self._add_message, "tool", f"无需压缩（{info.get('reason', '')}）"
            )
        self.call_from_thread(self._finish)

    @work(thread=True, exclusive=True)
    def _run_agent(self, text: str) -> None:
        try:
            for event in self._agent.send_stream(text, cancel_event=self._cancel_event):
                if self._cancel_event.is_set():
                    break
                self.call_from_thread(self._on_event, event)
        except Exception as exc:  # noqa: BLE001 - show errors in the UI
            self.call_from_thread(self._on_event, ("error", str(exc)))
        finally:
            if self._cancel_event.is_set():
                self.call_from_thread(self._on_event, ("cancelled",))
            self.call_from_thread(self._finish)

    def _on_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "delta":
            if self._cancel_event.is_set():
                return
            self._hide_thinking()
            self._append_delta(event[1])
        elif kind == "cancelled":
            self._hide_thinking()
            self.notify("已取消本次生成", timeout=2, severity="warning")
        elif kind == "tool":
            self._hide_thinking()
            if event[1] == "todo_write":
                self._update_todos(event[2])
            line = ToolLine(event[1], _format_args(event[2]), self._accent)
            self._tools.append(line)
            self._chat().mount(line)
            self._scroll_end()
        elif kind == "tool_done":
            note = event[2] if len(event) > 2 else ""
            if self._tools:
                self._tools.pop().finish(note=note)
            self._show_thinking()
        elif kind == "compact":
            info = event[1]
            self._add_message(
                "tool",
                f"✻ 已压缩上下文：{info.get('pre_tokens')} → {info.get('post_tokens')} tokens",
            )
        elif kind == "done":
            self._hide_thinking()
            self._last_reply = event[1] or self._assistant_text
            if not self._assistant_text and event[1]:
                self._add_message("assistant", event[1])
        elif kind == "error":
            self._hide_thinking()
            self._add_message("error", f"✗ {event[1]}")

    def _update_todos(self, args_json: str) -> None:
        try:
            args = json.loads(args_json)
        except ValueError:
            return
        items = todo_store.normalize(args.get("todos"))
        panel = self.query_one("#todos", Static)
        if not items:
            panel.display = False
            panel.update("")
            return
        lines = ["[bold]任务清单[/bold]"]
        lines.extend(
            f"{todo_store.ICONS.get(item['status'], '☐')} {item['content']}" for item in items
        )
        panel.update("\n".join(lines))
        panel.display = True

    def _append_delta(self, text: str) -> None:
        if self._assistant is None:
            self._assistant = Markdown("", classes="assistant")
            self._chat().mount(self._assistant)
        self._assistant_text += text
        self._assistant.update(self._assistant_text)
        self._scroll_end()

    def _finish(self) -> None:
        self._busy = False
        self._hide_thinking()
        self._assistant = None
        self._assistant_text = ""
        self._tools = []
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()
        self.query_one("#status", Static).update(self._status_text())
