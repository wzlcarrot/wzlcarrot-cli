"""System-prompt assembly.

The system prompt is composed from ordered sections instead of one hardcoded
string: a base section, an optional user memory file, and any sections plugins
contributed.  Mirrors DeepSeek Harness's ``system-prompt/assemble`` waterfall.

Plugins add sections via ``api.prompt_section(name, text, priority=0)`` (higher
priority sorts later, i.e. closer to the end).
"""

from __future__ import annotations

from pathlib import Path

from .config import config_dir

MEMORY_LIMIT = 4000


def load_memory() -> str:
    """Read user memory.

    Sources: the config-dir ``AGENTS.md`` (global preferences) and a
    ``WZLCARROT.md`` in the current working directory (project-specific; the
    legacy ``ZHIHU.md`` is still honored).  We avoid a bare ``AGENTS.md`` in the
    cwd so an unrelated one is never injected.
    """
    chunks: list[str] = []
    candidates = (config_dir() / "AGENTS.md", Path.cwd() / "WZLCARROT.md", Path.cwd() / "ZHIHU.md")
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    chunks.append(text)
        except OSError:
            continue
    memory = "\n\n".join(chunks)
    if len(memory) > MEMORY_LIMIT:
        memory = memory[:MEMORY_LIMIT] + "\n…（记忆已截断）"
    return memory


def build_prompt_sections(
    base: str, memory: str, sections: list[tuple[int, str]]
) -> str:
    parts = [base.strip()]
    if memory.strip():
        parts.append("【用户记忆 / 偏好】\n" + memory.strip())
    for _, text in sorted(sections, key=lambda item: item[0]):
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)
