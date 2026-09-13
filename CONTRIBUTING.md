# 贡献指南

感谢参与 zhihu-cli 开发。开始之前请先阅读 [README](README.md) 与
[架构文档](docs/ARCHITECTURE.md)。

## 开发环境

要求：Python 3.10 – 3.13，推荐使用 [uv](https://docs.astral.sh/uv/) 管理环境
（与 CI 一致）。

```bash
# 克隆后安装依赖（含开发依赖）
uv sync --extra dev

# 不用 uv 的话
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 常用命令

```bash
# 运行单元测试（集成测试默认跳过，见 pyproject.toml 的 addopts）
uv run pytest -q

# 运行集成测试（需要有效登录态，会访问真实知乎 API）
uv run pytest -m integration

# Lint
uv run ruff check .

# 构建 sdist 与 wheel（输出到 dist/）
uv build
```

## 提交变更

1. **测试**：新增功能需附带单元测试；涉及网络的行为不得依赖真实知乎接口
   （用 mock 或集成 marker 隔离）。
2. **Lint**：提交前保证 `uv run ruff check .` 通过（line-length 100）。
3. **Changelog**：面向用户的变更（新命令、行为变化、修复）必须在
   [CHANGELOG.md](CHANGELOG.md) 的 `[Unreleased]` 区块追加条目。
4. **提交信息**：使用祈使句、一行说明变更内容，例如
   `Add topic filter to search command`；一次提交聚焦一件事。
5. **版本发布**：由维护者执行 —— 更新 `pyproject.toml` 版本号、
   把 `[Unreleased]` 改为版本号并注明日期、提交后打 `vX.Y.Z` tag 并推送。
   `.github/workflows/release.yml` 会在 tag 上自动构建并发布到 PyPI
   （Trusted Publishing：需在 PyPI 项目设置里为该仓库和工作流配置一次
   pending publisher，GitHub 侧不保存任何 token）。

## 代码约定

- 命令层（`commands/`）不做网络请求，一切走 `client.py`；
- 签名相关的改动只改 `signing.py`，并同步更新其单测；
- 写操作（发布/删除）保留二次确认行为，不要默认跳过；
- 用户可见文案使用中文，代码标识符使用英文。

## CI

推送后 GitHub Actions 会自动执行：ruff lint → pytest（3.10–3.13 矩阵）→
构建并校验包元数据。PR 需要全部通过才能合并。
