from __future__ import annotations

import os

from wzlcarrot_cli import composer


class FakeClient:
    @staticmethod
    def _build_img_html(infos):
        return "".join(f'<img src="{i["src"]}"/>' for i in infos)

    def upload_image(self, path, source):
        return {
            "src": f"https://pic.example/{path}",
            "original_src": "o",
            "watermark": "watermark",
            "watermark_src": "w",
            "width": 1,
            "height": 1,
        }


def test_split_title():
    title, body = composer.split_title("# 标题\n\n正文")
    assert title == "标题"
    assert body == "正文"


def test_has_local_images():
    assert composer.has_local_images("![](/tmp/a.png)")
    assert not composer.has_local_images("![](https://x/y.png)")


def test_markdown_to_html_uploads_local_images():
    html = composer.markdown_to_html("正文 ![](/tmp/a.png)", FakeClient(), "article")
    assert "<p>" in html
    assert "https://pic.example//tmp/a.png" in html


def test_remote_image_untouched():
    html = composer.markdown_to_html("![](https://x/y.png)", FakeClient(), "article")
    assert "https://x/y.png" in html


def test_to_plain_text_strips_markup_and_images():
    text = composer.to_plain_text("# 标题\n\n**加粗** ![](/tmp/a.png) 结束")
    assert "标题" in text
    assert "加粗" in text
    assert "![" not in text


def test_is_cancelled():
    assert composer.is_cancelled(composer.ASK_TEMPLATE, composer.ASK_TEMPLATE)
    assert composer.is_cancelled("   \n", composer.ASK_TEMPLATE)
    assert not composer.is_cancelled("# 标题\n\n真实内容", composer.ASK_TEMPLATE)


def test_edit_text_with_env_editor(tmp_path, monkeypatch):
    script = tmp_path / "ed.sh"
    script.write_text('#!/bin/bash\nprintf "# 编辑器标题\\n\\n正文" > "$1"\n', encoding="utf-8")
    os.chmod(script, 0o755)
    monkeypatch.setenv("WZLCARROT_CLI_EDITOR", f"{script} {{file}}")
    result = composer.edit_text(composer.ASK_TEMPLATE)
    assert "编辑器标题" in result
    assert "正文" in result


def test_launch_windows_editor_builds_cmd_start(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(argv, *args, **kwargs):
        captured["argv"] = argv

    monkeypatch.setattr(composer.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        composer, "_wslpath", lambda flag, value: r"C:\Temp\zhihu-x.md" if flag == "-w" else None
    )
    monkeypatch.setattr(composer, "_windows_temp_dir", lambda: tmp_path)
    monkeypatch.setattr(
        composer,
        "resolve_editor",
        lambda: composer.Editor(
            argv=[r"D:\markText\MarkText.exe", "{file}"], gui=True, windows_path=True
        ),
    )
    session = composer.EditorSession("template")
    session.open()
    argv = captured["argv"]
    assert argv[:3] == ["cmd.exe", "/c", "start"]
    assert r"D:\markText\MarkText.exe" in argv
    assert r"C:\Temp\zhihu-x.md" in argv
    session.close()
