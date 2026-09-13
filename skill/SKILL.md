---
name: zhihu-cli
description: 知乎 CLI 技能。用户想在知乎搜索、看热榜/推荐/话题、读问题/回答/文章/评论、查用户/关注/粉丝/收藏/通知、导出 Markdown、点赞/关注/收藏/评论/发布/删除，或用自然语言对话操作知乎时使用。通过执行本机的 `zhihu` 命令完成，登录态仅存本地，访问频率已强制限制为低频。
---

# zhihu-cli 技能

## 前提

- **已安装**：`zhihu`（或 `wzlcarrot zhihu`）在 PATH 中（`uv tool install wzlcarrot-cli` 或 `pip install wzlcarrot-cli`）。
- **配置目录**：`~/.config/zhihu-cli/`（可用环境变量 `ZHIHU_CLI_HOME` 覆盖）
  - 登录态：`credentials.json`（权限 0600）
  - 扫码登录二维码：`qrcode.png`
  - 会话：`sessions/`
- **登录方式**：扫码 `zhihu login --qr`、粘贴 Cookie `zhihu login --cookie "d_c0=...; z_c0=...; _xsrf=..."`。
- **安全**：Cookie 仅存本地，**不得上传、转发或写入对话/日志**。

## Agent 规则（务必遵守）

1. **低频访问**：本工具默认已限速（读 1.5–3.5s、写 ≥8s、跨进程最小间隔 3s）。**不要**用脚本批量调用；连续多条命令也会被强制间隔。若需更慢，把全局参数放在子命令之前：
   `zhihu --min-delay 4 --max-delay 8 --min-gap 10 --write-delay 30 <子命令>`。
2. **`--json` 是全局参数，必须放在子命令之前**：数据查询用 `zhihu --json hot`、`zhihu --json search 关键词`。命令默认输出人类可读表格，解析请用 `--json`。
3. **需登录**：先 `zhihu status`；未登录则 `zhihu login --qr`（终端渲染二维码）或 `--cookie`。
4. **写操作会二次确认**：赞同/关注/收藏/评论/发布/删除等默认询问，Agent 场景加 `-y`。仍建议变更类操作先向用户确认意图。
5. **发布正文**：`publish`/`action publish` 的正文支持 HTML；用 `--edit` 会调用本地 Markdown 编辑器（MarkText）。
6. **反爬**：命中知乎限制会报 `AntiAbuseError` 并自动冷却 120 秒，稍后重试即可，切勿高频重试。

## 诉求 → 命令

| 诉求 | 命令 |
|------|------|
| 登录（扫码 / Cookie） | `zhihu login --qr` / `zhihu login --cookie "d_c0=...; z_c0=...; _xsrf=..."` |
| 登录状态 / 我的资料 | `zhihu status` / `zhihu me` |
| 热榜 | `zhihu --json hot -n 10` |
| 推荐流 | `zhihu --json feed -n 10` |
| 话题 | `zhihu --json topic <id> -q` |
| 搜索 | `zhihu --json search 关键词 -n 10` |
| 问题 / 回答列表 | `zhihu --json question <id> -a -n 5` |
| 回答全文（可带评论） | `zhihu --json answer <id>` / `zhihu answer <id> --comments` |
| 文章全文（可带评论） | `zhihu --json article <id>` / `zhihu article <id> --comments` |
| 评论 | `zhihu --json comments --answer <id>` / `--article <id>` |
| 用户主页 | `zhihu --json user <url_token>` |
| 关注 / 粉丝 / 收藏 / 通知 | `zhihu --json following` / `followers` / `collections` / `notifications` |
| 导出 Markdown | `zhihu download answer\|article\|question <id> -o ./downloads [--images]` |
| 赞同 / 取消 | `zhihu action vote --answer <id> -y` / `zhihu action unvote --answer <id> -y` |
| 关注 / 取关（用户或问题） | `zhihu action follow --user <token>\|--question <id> -y` / `unfollow ...` |
| 收藏 / 取消收藏 | `zhihu action collect <content_id> -c <collection_id> -y` / `uncollect ...` |
| 评论 / 删自己的评论 | `zhihu action comment --answer <id> -m "..." -y` / `zhihu action delete-comment <comment_id> -y` |
| 发布回答 | `zhihu action publish <question_id> -m "<p>正文</p>" -y`（或 `--edit`） |
| 发布提问 / 想法 / 文章 | `zhihu publish ask "标题？" -d "描述" -y` / `zhihu publish pin "标题" -c "正文" -y` / `zhihu publish article "标题" "正文" -y` |
| 删除自己的内容 | `zhihu publish delete-question\|delete-pin\|delete-article <id> -y` |
| Markdown 编辑器创作 | 上述发布命令加 `--edit`（弹本地 MarkText） |
| 自然语言对话 / 续聊 / 列出会话 | `zhihu tui` / `zhihu chat` / `zhihu chat --continue` / `zhihu sessions` |

## 执行流程

```
用户诉求
  → zhihu status（未登录 → zhihu login --qr 或 --cookie）
  → 查上表得命令
  → 数据查询：加全局 --json（放子命令前）执行并解析
  → 写操作：先确认意图，加 -y 执行
  → 整理结果；命中反爬则说明已冷却、稍后再试
```

## 常见示例

```bash
zhihu status
zhihu --json hot -n 10
zhihu --json search "大模型" -n 10
zhihu --json question 12345678 -a -n 5
zhihu --json answer 87654321
zhihu --json user wzlcsdn
zhihu download article 12345678 --images -o ./downloads
zhihu action vote --answer 87654321 -y
zhihu publish pin "今天天气真好" -c "<p>正文</p>" -y
zhihu publish article --edit
zhihu chat --continue
```

## 错误处理

- **未登录 / 401 / 403**：`zhihu login --qr` 或 `--cookie` 后重试。
- **AntiAbuseError（请求存在异常/暂时限制）**：已自动冷却 120 秒，稍后再试，降低频率。
- **签名失效（403 持续）**：知乎前端更新了 `x-zse-96`，需更新 `zhihu_cli/signing.py`。
- **其他**：检查 ID / url_token 是否正确；网络超时重试。
