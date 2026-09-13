# wzlcarrot-cli 架构文档

wzlcarrot-cli 是一个纯 Python 的多平台命令行客户端（当前内置知乎）：不依赖浏览器或 JS 运行时，
请求签名在本地实现；同时提供浏览/采集、创作发布、自然语言 Agent 三类能力。
顶层命令为 `wzlcarrot`（通用命令）；平台命令是各自独立的入口（`zhihu ...`，不带 `wzlcarrot` 前缀），共享同一套核心。

## 总体分层

```
┌─────────────────────────────────────────────────────────┐
│  入口层   cli.py (Typer) ── root_app(wzlcarrot) / app(zhihu)│
├─────────────────────────────────────────────────────────┤
│  命令层   commands/ ── 每个功能域一个模块，只做参数解析和编排 │
├──────────────┬──────────────────────┬───────────────────┤
│  API 核心     │  创作                 │  自然语言 Agent     │
│  client.py   │  composer.py         │  llm.py           │
│  signing.py  │  imagestore.py       │  sessions.py      │
│  qrlogin.py  │                      │  compaction.py    │
│              │                      │  spill.py / tui.py│
├──────────────┴──────────────────────┴───────────────────┤
│  基础设施  output.py · config.py · plugins.py · hooks.py  │
│           todo.py · prompt.py · exceptions.py · doctor.py │
│           updates.py · upgrade.py                         │
└─────────────────────────────────────────────────────────┘
```

## 模块职责

### 入口与命令层

- **`cli.py`** —— Typer 应用入口。`root_app`（`wzlcarrot = wzlcarrot_cli.cli:root_main`）承载**通用命令**
  （connect/doctor/tui/chat/ask/plugins/...）；平台命令是各自独立的入口 `app`
  （`zhihu = wzlcarrot_cli.cli:main`），**不带 `wzlcarrot` 前缀**。全局回调处理无子命令时的默认行为。
- **`commands/`** —— 按功能域拆分，每个模块只负责参数解析、调用核心层、格式化展示：
  - `login.py`：登录/登出/状态
  - `feed.py`：热榜、推荐流、话题
  - `search.py`：关键词搜索
  - `content.py`：问题、回答、文章、评论
  - `user.py`：用户主页、关注/粉丝、收藏夹、通知
  - `publish.py`：发布回答/文章/评论
  - `chat.py`：`tui`/`chat`/`ask` 自然语言交互入口
  - `download.py`、`connect.py`、`actions.py`、`_common.py`（命令层公共工具）

### API 核心

- **`client.py`**（约 580 行）—— 知乎 API 客户端：维护登录态、组装请求、
  处理响应与重试，是所有命令层唯一的网络出口。
- **`signing.py`** —— 请求签名算法的纯 Python 实现（对应 Web 端 x-zse 系列 header）。
  签名逻辑独立成模块，便于知乎算法更新时单独维护和单测。
- **`qrlogin.py`** —— 扫码登录流程：生成二维码（qrcode + pillow）、轮询扫码结果、
  持久化会话。

### 创作链路

- **`composer.py`** —— 内容创作：HTML 富文本与 Markdown 的转换
  （markdownify / markdown-it-py），`--edit` 本地编辑器工作流。
- **`imagestore.py`** —— 创作涉及的图片上传与本地暂存。

### 自然语言 Agent 链路

- **`llm.py`** —— LLM provider 抽象与配置（`~/.config/wzlcarrot-cli/llm.json` 或环境变量），
  把自然语言请求映射为工具调用。
- **`sessions.py` / `compaction.py` / `spill.py`** —— 会话持久化、历史压缩、
  超长上下文落盘，支撑多轮对话。
- **`tui.py`**（约 750 行，最大单模块）—— 基于 Textual 的终端交互界面。
- **`todo.py` / `prompt.py`** —— Agent 的任务清单工具与提示词组装。

### 扩展机制

- **`plugins.py`** —— "Everything is a plugin"：插件从
  `~/.config/wzlcarrot-cli/plugins/` 动态加载，`plugins` 子命令可查看。
- **`hooks.py`** —— 守卫式工具管线：在 Agent 工具调用前后执行
  `hooks.json` 中声明的检查逻辑。

### 基础设施

- **`models.py`** —— Pydantic 数据模型（回答、用户、评论等领域对象）。
- **`output.py`** —— Rich 终端渲染（表格、面板、进度）。
- **`config.py`** —— 配置读取（`~/.config/wzlcarrot-cli/`）。
- **`doctor.py`** —— 自诊断：检查 Python 版本、依赖、登录态、配置文件。
- **`exceptions.py`** —— 统一异常层次。

## 测试与质量

- `tests/` 按模块一一对应（`test_client`、`test_hooks`、`test_compaction`…）；
  `snapshots/` 存放 TUI 快照测试基线。
- 需要真实登录态的用例打 `integration` marker，`pyproject.toml` 中默认
  `-m 'not integration'` 跳过，保证离线可跑。
- Lint：ruff（line-length 100，忽略 B008/PYI034，原因见 pyproject 注释）。
- CI：`.github/workflows/ci.yml`，Python 3.10–3.13 矩阵执行 lint + pytest，
  另有构建 job（uv build + twine check）。

## 设计约定

1. **命令层不碰网络**：所有 HTTP 都走 `client.py`，便于统一加签名、限速与重试。
2. **签名算法隔离**：知乎签名若失效，只需修 `signing.py` 及其单测。
3. **默认保守限速**：采集类命令内置随机间隔，避免触发风控；用户只被允许调慢。
4. **写操作默认二次确认**：发布/删除类命令需确认或显式 `-y`。
5. **离线可测**：单测不得依赖真实网络，网络相关逻辑以集成 marker 隔离。
