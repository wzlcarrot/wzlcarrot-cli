"""Conversation compaction, adapted from Clawd-Code / Claude Code.

Two layers, cheapest first:

1. ``microcompact`` — truncate old tool results in place (no LLM call).
2. ``compact`` — summarize everything older than the recent window into a single
   system message, keeping only one summary (boundary) at a time.

Messages are OpenAI-style dicts (``role`` / ``content`` / ``tool_calls``).
"""

from __future__ import annotations

from typing import Any

# Rough threshold: DeepSeek/OpenAI style contexts are 64k+; we stay conservative.
DEFAULT_MAX_TOKENS = 24_000
DEFAULT_KEEP_RECENT = 6
DEFAULT_KEEP_RECENT_TOOLS = 4
_TRANSCRIPT_LIMIT = 20_000

SUMMARY_PROMPT = """请把下面的多轮对话压缩成一份中文摘要，供后续对话继续使用。
只输出纯文本，不要调用任何工具，不要输出 XML 标签。

摘要需包含：
1. 用户的目标与意图
2. 已查看/操作过的知乎内容（标题、ID、链接等关键标识）
3. 已经完成的事情与结论
4. 遇到的错误与解决办法
5. 用户明确提出但尚未完成的任务
6. 当前正在进行的工作与下一步

对话记录：
"""


def estimate_tokens(text: str) -> int:
    """Approximate token count (chars/4); good enough for a trigger threshold."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _message_tokens(message: dict[str, Any]) -> int:
    total = estimate_tokens(str(message.get("content") or ""))
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        total += estimate_tokens(str(function.get("name") or ""))
        total += estimate_tokens(str(function.get("arguments") or ""))
    return total + 4  # per-message overhead


def count_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(_message_tokens(m) for m in messages)


def microcompact(
    messages: list[dict[str, Any]], keep_recent_tools: int = DEFAULT_KEEP_RECENT_TOOLS
) -> tuple[list[dict[str, Any]], int]:
    """Truncate the content of older tool results, keeping the most recent ones."""
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(tool_indices) <= keep_recent_tools:
        return messages, 0
    stale = set(tool_indices[:-keep_recent_tools])
    saved = 0
    result: list[dict[str, Any]] = []
    for i, message in enumerate(messages):
        content = str(message.get("content") or "")
        if i in stale and len(content) > 200:
            saved += estimate_tokens(content) - 50
            result.append({**message, "content": content[:200] + "\n…[旧工具结果已压缩]"})
        else:
            result.append(message)
    return result, max(0, saved)


def render_transcript(messages: list[dict[str, Any]]) -> str:
    """Flatten messages into plain text for the summarizer (avoids tool-message quirks)."""
    lines: list[str] = []
    for message in messages:
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role == "user":
            lines.append(f"用户: {content}")
        elif role == "assistant":
            if content:
                lines.append(f"助手: {content}")
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                lines.append(f"[调用工具 {function.get('name')}({function.get('arguments')})]")
        elif role == "tool":
            lines.append(f"工具结果: {content[:500]}")
        elif role == "system" and message.get("_compact_summary"):
            lines.append(f"既往摘要: {content}")
    return "\n".join(lines)


def _safe_recent_start(body: list[dict[str, Any]], keep_recent: int) -> int:
    index = max(0, len(body) - keep_recent)
    while index < len(body) and body[index].get("role") != "user":
        index += 1
    return index if index < len(body) else max(0, len(body) - keep_recent)


def compact(
    messages: list[dict[str, Any]],
    llm,
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
    instructions: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Summarize older messages into one system summary; returns (messages, info)."""
    if len(messages) <= keep_recent + 1:
        return messages, {"compacted": False, "reason": "too few messages"}

    system = messages[0] if messages and messages[0].get("role") == "system" else None
    body = messages[1:] if system else list(messages)
    start = _safe_recent_start(body, keep_recent)
    older, recent = body[:start], body[start:]
    if not older:
        return messages, {"compacted": False, "reason": "nothing to summarize"}

    transcript = render_transcript(older)
    if len(transcript) > _TRANSCRIPT_LIMIT:
        transcript = "…（更早内容已省略）\n" + transcript[-_TRANSCRIPT_LIMIT:]

    pre_tokens = count_messages_tokens(messages)
    prompt = SUMMARY_PROMPT + transcript
    if instructions:
        prompt += f"\n\n额外要求：{instructions}"
    try:
        response = llm.chat([{"role": "user", "content": prompt}], None)
        summary_text = str(response.get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001 - fall back to a truncated transcript
        summary_text = f"（摘要生成失败：{exc}）\n" + transcript[-2000:]

    summary_message = {
        "role": "system",
        "content": "以下是此前对话的摘要：\n" + summary_text,
        "_compact_summary": True,
    }
    new_messages = ([system] if system else []) + [summary_message] + recent
    info = {
        "compacted": True,
        "pre_tokens": pre_tokens,
        "post_tokens": count_messages_tokens(new_messages),
        "summarized": len(older),
    }
    return new_messages, info
