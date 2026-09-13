from __future__ import annotations

from zhihu_cli.doctor import run_checks


def test_doctor_offline_reports_core_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    for key in ("ZHIHU_CLI_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    checks = run_checks(check_network=False)
    labels = {label: (ok, detail) for label, ok, detail in checks}

    assert labels["版本"][0] is True
    assert labels["登录凭证"][0] is False  # no credentials in a fresh home
    assert labels["模型配置"][0] is False  # no key configured
    assert "知乎连通" not in labels  # network skipped
    assert labels["插件"][0] is True
    assert labels["溢出文件"][0] is True
