# Changelog

本项目所有显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **历史说明**：git 仓库于 v0.17.3 时才初始化，此前版本（0.2.0 – 0.17.2）在无版本控制的
> 状态下快速迭代，未逐版记录变更，仅保留发布时间线（依据 `dist/` 构建产物日期）。
> 自 v0.17.3 起，所有面向用户的变更必须逐版记录在本文件中。

## [Unreleased]

## [0.17.3] - 2026-09-13

首个纳入版本控制的版本（git 初始提交 `19ae7f3`）。以下为当前功能快照：

### 新增

- **登录与账号**：扫码登录（`login`/`logout`/`status`）、纯 Python 实现的请求签名，
  无需浏览器或 JS 运行时
- **浏览与采集**：热榜（`hot`）、推荐流（`feed`）、话题（`topic`）、搜索（`search`）、
  问题/回答/文章/评论（`question`/`answer`/`article`/`comments`）
- **用户数据**：用户主页（`user`）、自己的资料（`me`）、关注/粉丝列表、收藏夹、通知
- **创作**：发布回答/文章/评论，支持 HTML 富文本与图片上传；Markdown 编辑器创作（`--edit`）
- **自然语言 Agent 模式**：`ask`/`chat`/`tui` 三种交互形态，多 provider 接入
  （`~/.config/zhihu-cli/llm.json`），会话持久化、上下文压缩（compaction）与溢出落盘（spill）
- **扩展机制**：插件系统（"Everything is a plugin"）与 Hook 守卫式工具管线
- **运维**：`doctor` 自诊断、`version`、`connect`、会话管理（`sessions`）
- **工程化**：GitHub Actions CI（Python 3.10–3.13 矩阵测试 + ruff lint + 构建校验），
  单元测试与集成测试分离（`integration` marker 默认跳过）

### 历史版本发布时间线

| 版本 | 发布日期 |
|------|----------|
| 0.2.0 – 0.13.1 | 2026-09-12 |
| 0.14.0 – 0.17.2 | 2026-09-13 |

[Unreleased]: https://example.invalid/compare/v0.17.3...HEAD
[0.17.3]: https://example.invalid/releases/tag/v0.17.3
