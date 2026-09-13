# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)；版本号一路快进，功能分组如下。

## [Unreleased]
### Added
- **多平台入口**：所有平台同时挂在 `wzlcarrot` 下（`wzlcarrot zhihu hot`、`wzlcarrot weibo ...`），并保留各自的独立命令（`zhihu hot`）。`wzlcarrot platforms` 列出全部平台。
- **规划中平台**：注册 `weibo`（微博）与 `xiaohongshu`（小红书）占位平台，命令已就位，实现待补。
- **TUI 像素 banner**：对话 TUI 顶部加入像素萝卜 logo（Claude Code 风格），标题与状态栏显示当前平台。
- **版本检查**：每天首次使用时查询一次 PyPI 公开版本信息（仅此查询，无遥测），发现新版在命令前提示一行；`WZLCARROT_CLI_NO_UPDATE_CHECK=1` 可关闭。
- **`zhihu upgrade` 命令**：自动识别安装方式（uv tool / pipx / pip）并执行对应升级；源码 editable 安装时提示 `git pull && uv sync`。
- **发布工作流**：`.github/workflows/release.yml` 在 `v*` tag 上自动构建并发布到 PyPI（Trusted Publishing，GitHub 侧不存 token）。
- **提示词注入防护**：Agent 模式的工具结果（知乎标题/回答/评论等第三方内容）统一包裹为「不可信数据」标记，系统提示词明确约束不得执行其中出现的指令；包裹标签可防逃逸（内容中的闭合标记会被剥离）。
### Fixed
- 更新检查此前查询的是 PyPI 上**同名但非本项目**的 `zhihu-cli`，导致误报新版本；现改为按真实发行名查询，并在缓存中记录包名（旧缓存自动失效）。
### Changed
- 命名约定：知乎专属的命令 / 文件 / 目录一律沿用 `zhihu`（如 `zhihu` 命令、`platforms/zhihu_tools.py`、skill `zhihu-cli`）；只有**通用（App 级）**的东西才用 `wzlcarrot`（发行包名、配置文件目录、环境变量、通用命令、记忆文件）。
- 应用配置目录由 `~/.config/zhihu-cli/` 改为 **`~/.config/wzlcarrot-cli/`**；环境变量前缀 `ZHIHU_CLI_*` 改为 **`WZLCARROT_CLI_*`**（旧名仍兼容）；项目记忆文件 `ZHIHU.md` 改为 **`WZLCARROT.md`**（旧名仍兼容）。
- PyPI 发行包名由 `zhihu-cli` 改为 **`wzlcarrot-cli`**（`zhihu-cli` 已被他人占用）；命令行仍为 `zhihu`，使用方式不变。

## [0.18.0] - 2026-09-13
### Added
- **签名失效自检**：`zhihu doctor` 新增独立的「签名自检」检查项；客户端把「HTTP 403 + 错误码 100」从「未登录」中区分出来，抛出明确的签名失效错误（提示知乎可能已更新 x-zse-96 算法），不再与登录过期混淆。
- **请求取消**：TUI 中按 `Esc` 可取消正在进行的生成（空闲时仍是聚焦输入框）；终端 `chat` 模式中 `Ctrl+C` 只取消当前一轮回答并保留会话，不再直接退出。
### Removed
- 删除未被引用的死代码 `wzlcarrot_cli/models.py`，并从依赖中移除 pydantic。

## [0.17.3]
### Changed
- Ctrl+C 退出确认弹窗改为右上角、更小（宽度自适应、去掉标题与竖向内边距）。

## [0.17.0]
### Added
- 剪贴板复制：**Ctrl+C 复制选中文字**（无选区时才走双击退出）；新增 `/copy` 复制上一条回答（OSC 52）。

## [0.16.0]
### Added
- **plan / build 模式**：左下角显示当前模式，`Shift+Tab` 切换。plan 模式下系统提示词与工具执行双重限制，所有写操作被拒。

## [0.15.0]
### Added
- TUI `/connect` 两步向导：**可搜索的供应商列表 → 选中 → 填 API Key**，保存即生效。
### Changed
- 供应商列表只显示名称（去掉 id 与模型名）。
- 去掉「取消」按钮：`Esc` 返回/关闭、`Enter` 确定；内置供应商隐藏 base_url 字段。

## [0.14.0]
### Added
- 在 TUI 内完成 `/connect` 全流程（选供应商 → 填 Key → 立即切换模型）。
- 命令面板默认高亮光标，`↑↓` 移动、`Enter` 执行高亮项、`Tab` 补全。
- Ctrl+C 双击退出（第一次弹提示）。

## [0.12.0]
### Added
- `zhihu connect`：交互式配置模型供应商，内置 10 家（DeepSeek / OpenAI / 智谱 / Kimi / 通义 / MiniMax / 硅基流动 / OpenRouter / Agnes / 自定义），支持 `--list`、`--test`。

## [0.11.0]
### Added
- `zhihu doctor` 自检：版本 / 登录 / 模型 / 插件 / 钩子 / 溢出 / 会话 / 连通性，一屏看清。

## [0.10.0]
### Added
- `todo_write` 工具 + TUI 实时任务面板 + `/todos`，支持多步任务规划。

## [0.9.0]
### Added
- 守卫式工具管线（pre/post hooks）：可拒绝/询问/改写参数/注解结果；支持 `~/.config/wzlcarrot-cli/hooks.json` 声明式规则与插件钩子；`zhihu hooks`。
- 钩子异常隔离。

## [0.8.0]
### Added
- 系统提示词分段组装（基础段 + 记忆 + 插件段）；记忆来自 `~/.config/wzlcarrot-cli/AGENTS.md` 与项目 `WZLCARROT.md`（兼容 `ZHIHU.md`）；`zhihu prompt`。
- 插件可贡献提示词段（`api.prompt_section`）。

## [0.7.0]
### Added
- 采集 provider 真实 token 用量（非流式 + 流式 `include_usage`）；TUI 状态栏显示、`/stats`。

## [0.6.0]
### Added
- 超大工具结果落盘（私有 0700 目录 / `O_EXCL` 0600），模型可用 `read_spill` 分段回读；`zhihu spill [--clean]`。

## [0.5.0]
### Added
- 插件系统：命令与 Agent 工具由注册表贡献，支持入口点组 `wzlcarrot_cli.plugins` 与本地 `~/.config/wzlcarrot-cli/plugins/`；`zhihu plugins`。

## [0.4.0]
### Added
- 对话会话持久化 + `zhihu chat/tui --continue` / `--session`；`zhihu sessions`。

## [0.3.0]
### Added
- 上下文压缩：旧工具结果截断 + 超阈值 LLM 摘要；`/compact`。

## [0.2.0]
### Added
- 打包发布准备：classifiers、LICENSE、`markdown-it-py` 依赖、integration 测试标记；可构建 sdist/wheel。

## [0.1.0]
### Added
- 纯 Python `x-zse-96` v2 签名（移植自 `zly2006/zhihu-plus-plus`）。
- 扫码登录（纯 API，终端渲染二维码）/ Cookie 导入；CSRF `x-xsrftoken`；统一浏览器指纹。
- 三层限速：请求随机间隔、写操作 ≥8s、跨进程最小间隔、敏感接口加成、反爬自动冷却。
- 读：热榜 / 推荐 / 话题 / 搜索 / 问题 / 回答 / 文章 / 评论 / 用户 / 关注 / 粉丝 / 收藏 / 通知。
- 写：投票·取消 / 关注·取关 / 收藏·取消 / 评论·删评论 / 发布回答 / 提问 / 想法 / 文章 / 删除（全部实测可逆）。
- 创作：`--edit` 调用本地 MarkText（Markdown + 本地图片自动上传）。
- 导出 Markdown，`--images` 图片本地归档。
- 自然语言 Agent + Claude Code 风格 TUI（流式、工具可视化、写操作确认）。
