import asyncio

from wzlcarrot_cli.tui import ChatTUI


class FakeAgent:
    def __init__(self) -> None:
        self._confirm_fn = None

    def stats(self) -> dict:
        return {
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "tool_calls": 0,
            "compactions": 0,
            "context_tokens": 0,
        }

    def send_stream(self, text, cancel_event=None):
        yield ("tool", "hot", '{"limit": 3}')
        yield ("tool_done", "hot")
        yield ("delta", "热榜：")
        yield ("delta", "1. 测试标题")
        yield ("done", "热榜：1. 测试标题")


def test_tui_mounts_and_runs_a_turn():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.value = "热榜前3"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause(0.1)
                if not app._busy:
                    break
            from textual.widgets import Markdown

            markdowns = app.query(Markdown)
            assert markdowns, "assistant markdown should be mounted"
            assert "测试标题" in markdowns.first().source
            assert app._busy is False

    asyncio.run(main())


def test_tui_command_menu_and_tab_completion():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            panel = app.query_one("#commands")
            prompt.value = "/co"
            await pilot.pause(0.05)
            assert panel.display is True
            await pilot.press("tab")
            assert prompt.value == "/connect"

    asyncio.run(main())


def test_tui_connect_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))

    from types import SimpleNamespace

    from textual.widgets import Input

    from wzlcarrot_cli.llm import LLMConfig
    from wzlcarrot_cli.tui import ConnectScreen

    class AgentWithLLM(FakeAgent):
        def __init__(self):
            super().__init__()
            self.llm = SimpleNamespace(
                config=LLMConfig(api_key="old", base_url="http://old", model="old")
            )

    async def main():
        agent = AgentWithLLM()
        app = ChatTUI(agent, subtitle="old")
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.value = "/connect"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert isinstance(app.screen, ConnectScreen)

            option_list = app.screen.query_one("#provider-list")
            option_list.highlighted = 0
            option_list.focus()
            await pilot.press("enter")
            await pilot.pause(0.05)
            app.screen.query_one("#c-key", Input).value = "sk-new"
            await pilot.press("enter")  # Enter on the key field confirms
            await pilot.pause(0.1)

        assert (tmp_path / "llm.json").exists()
        assert agent.llm.config.model == "deepseek-chat"
        assert agent.llm.config.api_key == "sk-new"

    asyncio.run(main())


def test_tui_command_menu_highlight_and_enter():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.value = "/"
            await pilot.pause(0.05)
            assert app.query_one("#commands").display is True
            assert app._command_index == 0

            await pilot.press("down")
            assert app._command_index == 1
            await pilot.press("up")
            assert app._command_index == 0

            # Enter runs the highlighted command (/stats at index 2), not the raw text.
            await pilot.press("down")
            await pilot.press("down")
            before = len(app.query(".tool"))
            await pilot.press("enter")
            await pilot.pause(0.1)
            assert len(app.query(".tool")) > before
            assert prompt.value == ""

    asyncio.run(main())


def test_tui_ctrl_c_double_press_exits():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test():
            app.action_interrupt()
            assert app._exit is False  # first press only warns
            app.action_interrupt()
            assert app._exit is True  # second press exits

    asyncio.run(main())


def test_tui_shift_tab_toggles_mode():
    class Agent(FakeAgent):
        def __init__(self):
            super().__init__()
            self.plan_mode = False
            self.messages = [{"role": "system", "content": "base"}]

        def _system_prompt(self):
            return "base+" + ("plan" if self.plan_mode else "build")

    async def main():
        agent = Agent()
        app = ChatTUI(agent, subtitle="test-model")
        async with app.run_test() as pilot:
            assert app._mode == "build"
            await pilot.press("shift+tab")
            await pilot.pause(0.05)
            assert app._mode == "plan"
            assert agent.plan_mode is True
            assert "plan" in agent.messages[0]["content"]
            await pilot.press("shift+tab")
            await pilot.pause(0.05)
            assert app._mode == "build"
            assert agent.plan_mode is False

    asyncio.run(main())


def test_tui_connect_filter_and_two_steps():
    async def main():
        from textual.widgets import Input

        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test(size=(80, 24)) as pilot:
            prompt = app.query_one("#prompt")
            prompt.value = "/connect"
            await pilot.press("enter")
            await pilot.pause(0.05)

            screen = app.screen
            from wzlcarrot_cli.tui import ConnectScreen

            assert isinstance(screen, ConnectScreen)
            assert screen.query_one("#connect-step1").display is True
            assert screen.query_one("#connect-step2").display is False

            screen.query_one("#c-filter", Input).value = "deepseek"
            await pilot.pause(0.05)
            option_list = screen.query_one("#provider-list")
            assert option_list.option_count == 1

            option_list.focus()
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert screen.query_one("#connect-step2").display is True
            assert screen.query_one("#c-model", Input).value == "deepseek-chat"

    asyncio.run(main())


def test_tui_connect_keyboard_selection():
    async def main():
        from textual.widgets import Input, OptionList

        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test(size=(90, 30)) as pilot:
            prompt = app.query_one("#prompt")
            prompt.value = "/connect"
            await pilot.press("enter")
            await pilot.pause(0.05)

            screen = app.screen
            option_list = screen.query_one("#provider-list", OptionList)
            assert app.focused is option_list  # cursor is on the list
            assert option_list.highlighted == 0

            await pilot.press("down")
            assert option_list.highlighted == 1
            await pilot.press("up")
            assert option_list.highlighted == 0

            await pilot.press("enter")  # keyboard select (no mouse)
            await pilot.pause(0.05)
            assert screen.query_one("#connect-step2").display is True
            assert screen.query_one("#c-model", Input).value.startswith("deepseek")

    asyncio.run(main())


def test_tui_copy_command_copies_last_reply():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test() as pilot:
            app._last_reply = "要复制的回答内容"
            prompt = app.query_one("#prompt")
            prompt.value = "/copy"
            await pilot.press("enter")
            await pilot.pause(0.05)
            assert app.clipboard == "要复制的回答内容"

    asyncio.run(main())


def test_tui_ctrl_c_copies_selection_without_exiting():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test():
            app.screen.get_selected_text = lambda: "选中的文字"
            app.action_interrupt()
            assert app.clipboard == "选中的文字"
            assert app._exit is False  # copying must not exit

    asyncio.run(main())


def test_tui_smart_escape_logic():
    async def main():
        app = ChatTUI(FakeAgent(), subtitle="test-model")
        async with app.run_test():
            prompt = app.query_one("#prompt")
            app.action_smart_escape()  # idle -> focus input
            assert prompt.has_focus
            assert app._cancel_event.is_set() is False

            app._busy = True
            app.action_smart_escape()  # busy -> request cancel
            assert app._cancel_event.is_set() is True

    asyncio.run(main())


def test_tui_escape_cancels_in_flight_turn():
    import time

    class BlockingAgent(FakeAgent):
        def send_stream(self, text, cancel_event=None):
            yield ("delta", "部分输出")
            for _ in range(500):
                if cancel_event is not None and cancel_event.is_set():
                    return
                time.sleep(0.005)
            yield ("done", "完整输出")

    async def main():
        app = ChatTUI(BlockingAgent(), subtitle="test-model")
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.value = "开始一个长任务"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.01)
                if app._busy:
                    break
            assert app._busy is True

            await pilot.press("escape")
            for _ in range(200):
                await pilot.pause(0.01)
                if not app._busy:
                    break
            assert app._busy is False  # cancelled and finished

    asyncio.run(main())
