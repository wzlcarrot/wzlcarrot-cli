"""Curated list of OpenAI-compatible providers for ``zhihu connect``.

Users can pick one, enter an API key, and choose a model; custom endpoints are
supported too.  Base URLs are the providers' public OpenAI-compatible
endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Provider:
    id: str
    name: str
    base_url: str
    models: list[str] = field(default_factory=list)
    key_env: str = ""


PROVIDERS: list[Provider] = [
    Provider(
        id="deepseek",
        name="DeepSeek 深度求索",
        base_url="https://api.deepseek.com/v1",
        models=["deepseek-chat", "deepseek-reasoner"],
        key_env="DEEPSEEK_API_KEY",
    ),
    Provider(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        models=["gpt-4o", "gpt-4o-mini", "o3-mini"],
        key_env="OPENAI_API_KEY",
    ),
    Provider(
        id="zhipu",
        name="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        models=["glm-4-plus", "glm-4-flash", "glm-4.5-air"],
        key_env="ZHIPUAI_API_KEY",
    ),
    Provider(
        id="moonshot",
        name="月之暗面 Kimi",
        base_url="https://api.moonshot.cn/v1",
        models=["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0711-preview"],
        key_env="MOONSHOT_API_KEY",
    ),
    Provider(
        id="qwen",
        name="阿里通义千问 DashScope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=["qwen-max", "qwen-plus", "qwen-turbo"],
        key_env="DASHSCOPE_API_KEY",
    ),
    Provider(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimax.chat/v1",
        models=["MiniMax-Text-01", "abab6.5s-chat"],
        key_env="MINIMAX_API_KEY",
    ),
    Provider(
        id="siliconflow",
        name="硅基流动 SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        models=["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
        key_env="SILICONFLOW_API_KEY",
    ),
    Provider(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        models=["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat"],
        key_env="OPENROUTER_API_KEY",
    ),
    Provider(
        id="agnes",
        name="Agnes AI (免费,限流)",
        base_url="https://apihub.agnes-ai.com/v1",
        models=["agnes-2.0-flash"],
        key_env="AGNES_API_KEY",
    ),
    Provider(
        id="custom",
        name="自定义（OpenAI 兼容）",
        base_url="",
        models=[],
    ),
]


def get_provider(provider_id: str) -> Provider | None:
    for provider in PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None
