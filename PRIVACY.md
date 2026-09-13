# 隐私政策（Privacy Policy）

> 本文件为**模板**，正式发布前请按发布主体与司法辖区补全。
> 最后更新：2026-09-13

## 核心承诺

**本软件不收集、不上传、不出售你的任何个人数据。** 它是一个在你的设备上本地运行的工具。

## 数据存储位置

所有数据都保存在你本机的配置目录（默认 `~/.config/wzlcarrot-cli/`，可用 `WZLCARROT_CLI_HOME` 覆盖）：

| 数据 | 文件 | 说明 |
|------|------|------|
| 登录凭证（Cookie） | `credentials.json` | **Fernet 加密**存储，权限 0600；密钥 `.credentials.key`（0600） |
| 对话会话 | `sessions/` | 仅本地 |
| 大工具结果溢出 | `spill/` | 私有目录 0700、文件 0600 |
| 模型配置 | `llm.json` | 含你的模型 API Key，权限 0600 |

## 网络请求

本软件的网络请求**仅限以下三类**：

1. **第三方平台 API**（如知乎）：用于你发起的读/写操作。
2. **你配置的模型服务**（OpenAI 兼容接口）：仅在你使用自然语言功能时。
3. **可选的版本检查**：每天最多一次查询 PyPI 公开版本信息，无任何标识信息；可用 `WZLCARROT_CLI_NO_UPDATE_CHECK=1` 关闭。

**本软件没有遥测、没有崩溃上报、没有使用统计。**

## 你的权利（PIPL / GDPR 对应）

- **访问与导出**：所有数据都在你本机，随时可查看。
- **删除**：运行 `wzlcarrot zhihu logout` 或直接删除配置目录即可，删除即彻底。
- **可携**：会话与导出均为明文 Markdown/JSON。

## 第三方

你与第三方平台、模型服务商之间的数据处理受其各自隐私政策约束，本软件不在其中转存或中转你的数据。

---

# Privacy Policy (summary)

Everything runs locally. No telemetry, no uploads, no analytics. Credentials are
encrypted at rest. The only network calls are to the platform(s) you use, your
configured model endpoint, and an optional opt-out PyPI version check.
