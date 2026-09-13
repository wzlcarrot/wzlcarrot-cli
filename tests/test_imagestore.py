from __future__ import annotations

from wzlcarrot_cli import imagestore


def test_localize_images_downloads_and_rewrites(tmp_path, monkeypatch):
    monkeypatch.setattr(imagestore, "_fetch", lambda url, **kw: ("image/png", b"\x89PNG"))

    html = '<p><img src="https://picx.zhimg.com/a.jpg"></p><img src="//picx.zhimg.com/b.png">'
    rewritten, count = imagestore.localize_images(html, tmp_path / "files", "files", delay=0)

    assert count == 2
    assert "files/" in rewritten
    files = list((tmp_path / "files").iterdir())
    assert len(files) == 2
    assert {f.suffix for f in files} == {".jpg", ".png"}


def test_localize_images_ignores_data_uri(tmp_path, monkeypatch):
    monkeypatch.setattr(imagestore, "_fetch", lambda url, **kw: ("image/png", b"x"))
    html = '<img src="data:image/png;base64,AAAA">'
    rewritten, count = imagestore.localize_images(html, tmp_path / "files", "files", delay=0)
    assert count == 0
    assert "data:image/png" in rewritten


def test_localize_images_keeps_remote_url_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(imagestore, "_fetch", lambda url, **kw: None)
    html = '<img src="https://x.example/y.jpg">'
    rewritten, count = imagestore.localize_images(html, tmp_path / "files", "files", delay=0)
    assert count == 0
    assert "https://x.example/y.jpg" in rewritten


def test_localize_images_dedupes_same_url(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(url, **kw):
        calls.append(url)
        return ("image/jpeg", b"j")

    monkeypatch.setattr(imagestore, "_fetch", fake_fetch)
    html = '<img src="https://x/a.jpg"><img src="https://x/a.jpg">'
    _, count = imagestore.localize_images(html, tmp_path / "f", "f", delay=0)
    assert count == 1
    assert len(calls) == 1
