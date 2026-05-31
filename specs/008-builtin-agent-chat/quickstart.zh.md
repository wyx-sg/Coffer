# 快速上手 — Coffer Built-in Agent & Chat

> English: [quickstart.md](./quickstart.md)

跟 Coffer 自己的内置 agent 对话，或跟一个由 Coffer 管理的外部 agent
（`claude_code` / `codex`）对话 —— 从桌面 app 或命令行。内置 agent 能通过
Coffer 的 MCP 网关触及 vault 管理的一切。

## 前置条件

- Coffer 的 daemon 正在运行（启动桌面 app 或 `coffer daemon`）。
- 首次启动时会自动 seed 一个名为 `coffer` 的内置 agent。
- 对**内置** agent：需要一个 LLM provider key。seed 出来的默认 model 是
  `anthropic:claude-sonnet-4-6`，所以配一个 Anthropic key —— 把它存进 keychain 并
  让 agent 的 `credential_ref` 指向它，或在 daemon 环境里 export
  `ANTHROPIC_API_KEY`。本地 model 无需 key（例如把 model 换成 `ollama:llama3`）。
- 对**外部** agent：注册 `claude_code` 和/或 `codex`（spec 004），并安装好该 agent
  的 CLI（`claude` / `codex`）且在 `PATH` 上。

## 配置内置 agent 的 model 和 key

内置 agent 是一个普通的 kind 为 `builtin_agent` 的 Resource，通过正常的
config 编辑路径修改。它的 config 字段：

| 字段             | 示例                          | 含义                                          |
| ---------------- | ----------------------------- | --------------------------------------------- |
| `model`          | `anthropic:claude-sonnet-4-6` | provider 限定的 model id                      |
| `system_prompt`  | `"You are Coffer's agent…"`   | 可选引导 prompt                               |
| `temperature`    | `0.7`                         | 可选，`0.0`–`2.0`                             |
| `max_tokens`     | `2048`                        | 可选，`> 0`                                   |
| `credential_ref` | `anthropic-key`               | provider key 的 keychain ref（云端 provider） |
| `use_gateway`    | `true`                        | 把 Coffer 的 MCP 网关工具给到 agent           |
| `confirm_tools`  | `["*delete*", "*write*"]`     | 暂停等人工确认的工具名 glob                   |

要改用本地 provider，把 `model` 设成例如 `ollama:llama3` 并清空 `credential_ref`
—— 无需 key。如果一个云端 provider 既没有存好的凭据也没有环境 key，下一次 `send`
会返回 `503 LLM_NOT_CONFIGURED`（读路径仍工作）。

## 从桌面 app 对话

1. 打开 **Chat**。
2. 点 **New**，在选择器里选一个目标 —— 内置的 `coffer` agent，或任何已启用、支持
   chat 的被管理 agent（`claude_code` / `codex`）。
3. 输入一条消息并发送。回复逐 token 流式吐出。tool call 显示为行；一个需确认的工
   具显示一张卡片，写明工具名和参数。
4. 用 **Stop** 停止一段流式回复（已有的部分回复被保留，标记为 canceled）。
5. 在列表里重命名、归档、恢复或删除会话。

## 从命令行对话

```bash
# 开一个会话（默认内置 agent）
coffer chat new
# => <conversation-id>

# …或针对一个被管理的 agent
coffer chat new --agent agent:claude-code

# 发一条消息并在终端里看它流式吐出
coffer chat send <conversation-id> "search my memory for branch naming, then list my MCP servers"

# 打印会话 + 消息历史（JSON 便于管道）
coffer chat show <conversation-id> --json

# 列出会话
coffer chat list
coffer chat list --json

# 重命名 / 归档 / 恢复 / 删除
coffer chat rename <conversation-id> "MCP audit"
coffer chat archive <conversation-id>
coffer chat restore <conversation-id>
coffer chat rm <conversation-id>            # 加 --force 跳过确认提示
```

目标 ref 是 `builtin_agent:<name>` 或 `agent:<name>`；`coffer chat new` 默认
`builtin_agent:coffer`。

## 使用确认

当内置 agent 提议调用一个名字匹配该 agent `confirm_tools` 策略的工具时（seed 出
来的默认值对 `*delete*`、`*clear*`、`*remove*`、`*write*` 设门禁），这一轮暂停并
发出一个 `confirmation` 事件、写明工具名和参数。

在桌面 app 里，点确认卡片上的 **Approve** 或 **Deny**。

在 CLI 里，`send` 流会打印 request id；用它来处理：

```bash
coffer chat confirm <conversation-id> <request-id> --approve
coffer chat confirm <conversation-id> <request-id> --deny
```

批准会运行工具并恢复这一轮；拒绝会跳过它并告知 agent 该调用被拒。一个一直没被回应
的确认不会破坏会话 —— 这一轮只是以工具被拒结束。

## 停止一轮进行中的对话

```bash
coffer chat stop <conversation-id>
```

streaming 停止，assistant 消息被标记为 `canceled` 并保留其部分内容，任何被拉起的
子进程（外部 agent）被终止。

## REST 等价物

所有操作都可经 loopback REST API 在 `/api/v1/conversations` 下使用（见
[contracts/api.openapi.yaml](./contracts/api.openapi.yaml)）。
`POST /{id}/messages` 返回一个由 SSE 事件组成的 `text/event-stream`：

```bash
curl -N http://127.0.0.1:8000/api/v1/conversations/<id>/messages \
  -H "X-Coffer-Token: $COFFER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

```
data: {"type":"text_delta","text":"Hi"}
data: {"type":"tool_call","id":"…","tool":"coffer__memory_search","args":{…}}
data: {"type":"tool_result","id":"…","tool":"coffer__memory_search","ok":true,"summary":"…"}
data: {"type":"done"}
```

事件类型：`text_delta`、`tool_call`、`tool_result`、`confirmation`、`error`、`done`。

## 排障

**send 时 `503 LLM_NOT_CONFIGURED`** —— 内置 agent 的 provider 没有可用 key。把
`credential_ref` 设成一个装着 provider key 的 keychain 条目，export provider 的环
境 key（例如 `ANTHROPIC_API_KEY`），或把 `model` 换成一个无需 key 的本地 provider。

**外部 agent「binary not found on PATH」** —— 安装该 agent 的 CLI（`claude` /
`codex`）并确保它在 daemon 的 `PATH` 上，或把 `COFFER_CHAT_BIN_CLAUDE_CODE` /
`COFFER_CHAT_BIN_CODEX` 设成它的绝对路径。

**`409 CONVERSATION_BUSY`** —— 该会话已经有一轮在 streaming。等它结束（或
`coffer chat stop`）再发。

**`409 CANNOT_DELETE_LAST_BUILTIN_AGENT`** —— Coffer 至少保留一个内置 agent，于是
chat 界面始终有目标。删这个之前先加另一个 `builtin_agent`（或干脆改它而不是删）。
