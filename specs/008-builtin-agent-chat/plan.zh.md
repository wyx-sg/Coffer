# 实现计划：008 — Built-in Agent & Chat

> English: [plan.md](./plan.md)

**Branch**: `feature/008-builtin-agent-chat`（构建于 spec 001 Resource 框架 +
spec 004 agent registry 之上）
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## 概要

给 Coffer 自己一个 agent 和一个 chat 界面。加一个**增量**的 `builtin_agent`
Resource kind —— 一个用 LangGraph 实现的真正 LLM 循环，于是任何主流 provider 都
能跑 —— 接到 Coffer 自己的 MCP 网关上，于是它能用 vault 管理的每一个 MCP server /
skill / knowledge base / memory。加一个 chat 界面，其中一个会话或针对内置 agent，
或针对一个由 Coffer 管理、作为本地无头子进程驱动的外部 agent（`claude_code` /
`codex`）。会话与消息在本地持久化；streaming 经 SSE 实时；敏感工具调用可暂停等人
在环确认；会话会自动生成标题。出厂带 REST 路由、CLI 子命令、桌面 Chat 页。
Channels（spec 009）以后把外部消息桥接进这个 chat。

## 技术上下文

| 维度             | 取值                                                                                                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **语言 / 版本**  | Python 3.12+、TypeScript 5.x                                                                                                                                             |
| **新运行时依赖** | `langgraph`、`langchain`、`langchain-core`、`langchain-anthropic`、`langchain-openai`、`langchain-ollama`、`langchain-mcp-adapters` —— 全部限制在 `infrastructure/chat/` |
| **存储**         | SQLite（`conversations`、`messages`）；内置 agent 的 config 复用 `resources`。                                                                                           |
| **测试**         | 4 层；acceptance 标记绑定场景。LangGraph 适配器的真模型路径推迟到 e2e 层；port 契约用一个 fake runtime 验证。                                                            |
| **目标平台**     | macOS arm64+x64、Windows x64、Linux x64+arm64                                                                                                                            |
| **性能目标**     | 打开 Chat 后 10 秒内出现首段流式回复（SC-001）。Stop 在 1 秒内停止输出（SC-004）。                                                                                       |
| **约束**         | Local-first（用户数据留在本地；调用云端 LLM provider 允许）；引擎隔离由 importlinter 强制；仅 loopback API；保持分层架构。                                               |
| **规模**         | 单用户；每个会话一轮进行中的 streaming。                                                                                                                                 |

## Constitution 检查

| 条款                       | 合规 | 备注                                                                                                            |
| -------------------------- | ---- | --------------------------------------------------------------------------------------------------------------- |
| I. Local-First             | ✅   | 会话 + 消息本地存于 SQLite。与云端 LLM provider 通信是明确允许的（用户数据留在本地）。                          |
| II. Spec-as-Truth          | ✅   | 代码前先提交 spec；配套文档与已实现的契约一致。                                                                 |
| III. Open-Source-Readiness | ✅   | LangGraph / LangChain 都是 OSS（MIT）。                                                                         |
| 语言                       | ✅   | Python + TypeScript。                                                                                           |
| 架构：分层                 | ✅   | 引擎在 `AgentRuntime` port 背后；LangChain/LangGraph 限制在 `infrastructure/chat/`（importlinter Contract 7）。 |
| 持久化                     | ✅   | 控制面在 SQLite；无大块内容表。                                                                                 |
| 凭据                       | ✅   | provider key 通过 keychain 经 `credential_ref` 解析；绝不存进 config 或 DB。                                    |
| 网络默认                   | ✅   | 仅 loopback HTTP API；内置 runtime 用 daemon token 经 `127.0.0.1` 触及网关。                                    |

## 项目结构

### 文档

```
specs/008-builtin-agent-chat/
  spec.md
  plan.md              (本文件)
  data-model.md
  research.md
  contracts/api.openapi.yaml
  quickstart.md
  tasks.md
```

### 后端模块

```
backend/coffer/domain/builtin_agent/
  __init__.py
  config.py            # BuiltinAgentConfig（Pydantic；纯，无引擎 import）

backend/coffer/domain/chat/
  __init__.py
  conversation.py      # Conversation / Message / ToolCall + status 枚举
  runtime.py           # RuntimeEvent 联合 + ChatTurnRequest + event_payload

backend/coffer/application/builtin_agent/
  __init__.py
  kind.py              # make_builtin_agent_kind + ensure_default_builtin_agent + 最后一个 agent 守卫

backend/coffer/application/chat/
  __init__.py
  ports.py             # ConversationRepo / MessageRepo / AgentRuntime / RuntimeFactory / TitleGenerator（Protocol）
  service.py           # ChatService —— 生命周期 + streaming 一轮的编排

backend/coffer/infrastructure/chat/
  __init__.py
  persistence.py       # SQLAlchemy ConversationRepo / MessageRepo
  runtime_factory.py   # CompositeRuntimeFactory（惰性引擎 import）
  builtin_runtime.py   # BuiltinRuntime（LangGraph）—— 唯一 import LangChain 的模块
  external_runtime.py  # ExternalAgentRuntime（子进程：claude / codex）

backend/coffer/infrastructure/persistence/migrations/versions/
  20260601_0006_chat_tables.py   # conversations + messages（revision 0006，down 0005）

backend/coffer/surfaces/http/chat/
  __init__.py
  routes.py            # /api/v1/conversations/*（send 时 SSE）
  schemas.py           # request/response Pydantic 模型 + 映射器
backend/coffer/surfaces/http/chat_composition.py   # 默认 runtime factory（网关 endpoint + keyring）
backend/coffer/surfaces/cli/chat_cmd.py            # coffer chat ...
```

### 前端模块

```
frontend/src/pages/ChatPage.tsx
frontend/src/components/chat/         # 会话列表、消息流、tool-call 行、确认卡片、目标选择器、Stop
frontend/src/lib/api/chat.ts          # REST 客户端 + SSE 读取
frontend/src/i18n/locales/{en,zh}.json  # 追加 chat 文案
```

## 架构

### 分层

- **Domain**（`domain/builtin_agent`、`domain/chat`）：纯值对象 ——
  `BuiltinAgentConfig`、`Conversation` / `Message` / `ToolCall`、`RuntimeEvent`
  联合、`ChatTurnRequest`。无引擎、无 I/O。
- **Application**（`application/builtin_agent`、`application/chat`）：
  `builtin_agent` Kind + seeding + 最后一个 agent 守卫，以及 `ChatService` 加它
  依赖的 ports。只依赖它自己定义的 Protocol。
- **Infrastructure**（`infrastructure/chat`）：持久化 repo 和两个 runtime。
  LangGraph 引擎只住在这里。
- **Surfaces**（`surfaces/http/chat`、`surfaces/cli/chat_cmd.py`）：REST（send
  时 SSE）和 CLI。composition 装上默认 runtime factory。

### `AgentRuntime` port + 两个 runtime

`ChatService` 只通过 `AgentRuntime` port（`stream`、`resolve_confirmation`、
`stop`）跟 agent 打交道，所以它对两个 runtime 的一轮编排是同一套。
`RuntimeFactory.build(target, config)` 按 `target.kind` 选实现：

- `builtin_agent` → `BuiltinRuntime`（LangGraph）。用 `init_chat_model` 解析
  model（与 provider 无关），`use_gateway` 时通过 `langchain-mcp-adapters` 从
  Coffer 自己的 `/mcp` endpoint 加载网关工具，把需确认的工具包一层使其暂停等人决
  定，跑一个 `create_react_agent` 循环，并把 `astream_events` 映射成 runtime 事件。
- `agent` → `ExternalAgentRuntime`（子进程）。在 agent 的 `config_dir` 下以无头
  streaming 模式拉起 `claude` / `codex`，把 stdout 映射成事件，并始终回收子进程。

### 引擎隔离

LangChain/LangGraph 限制在 `infrastructure/chat/builtin_runtime.py` —— 那里的
import 也是惰性的（在 `stream` 内），于是启动时装 factory 永远不需要装上引擎。
importlinter **Contract 7**（`forbidden`，源 `coffer.domain` + `coffer.application`，
禁止 `langgraph` / `langchain*` 包）强制这一点并支撑 SC-006。

### Streaming + 一轮的控制

`send` 校验文本和目标，**在持久化任何东西之前**构建 runtime（于是缺 provider key
会抛 `LlmNotConfigured` → 503 且不写半截），持久化 user 消息和一条
streaming-assistant 消息，然后返回这一轮的流。HTTP 界面把每个事件以
`data: {json}\n\n` 经 `text/event-stream` 发出；pre-stream 校验
（404/409/422/503）在提交 streaming body 之前被 await，于是它映射到正常的错误信
封。单飞由内存里的 active-turn 映射强制（冲突时 409）。Stop 设一个标志并请 runtime
停止；assistant 消息被最终定为 `canceled`，保留部分内容。

### 确认

对内置 runtime，Coffer 控制工具执行：名字匹配 `confirm_tools` 的工具被包一层，于
是它发出一个 `ConfirmationRequest`、await 一个决定 future，然后或运行（并返回结
果）或向 agent 返回一个「declined」字符串。`ChatService.resolve_confirmation` 把
决定路由给进行中的 runtime。v1 的外部 agent 在它们自己的权限策略下运行（那里的
`resolve_confirmation` 是 no-op；它们的 `confirm_tools` 为空）。

### 错误码 → HTTP 状态

| 码                                 | 状态 | 何时抛                                    |
| ---------------------------------- | ---- | ----------------------------------------- |
| `LLM_NOT_CONFIGURED`               | 503  | 内置目标的 provider 没有可用 key/endpoint |
| `CONVERSATION_NOT_FOUND`           | 404  | 未知会话 id                               |
| `CONVERSATION_BUSY`                | 409  | 一轮 streaming 时第二次 send              |
| `MESSAGE_REJECTED`                 | 422  | 空 / 仅空白 / 超长的消息文本              |
| `TARGET_AGENT_MISSING`             | 404  | 会话的目标 agent resource 没了            |
| `NOT_A_CHAT_TARGET`                | 400  | 针对一个非 chat resource kind 创建        |
| `CANNOT_DELETE_LAST_BUILTIN_AGENT` | 409  | 删除唯一剩下的 `builtin_agent`            |

## 分阶段

### Phase 0 — Research（见 [research.md](./research.md)）

- 引擎：LangGraph 在 port 背后（ADR-013）。被拒：裸 provider SDK、LlamaIndex agents。
- 通过对一个 provider 限定的 `model` 字符串用 `init_chat_model` 做与 provider 无关的 model 解析。
- 按 agent 类型的外部 agent 无头调用（`claude -p … --output-format stream-json`、`codex exec --json`）。
- 确认：内置 runtime 由 Coffer 控制的工具门禁；外部 runtime 用 agent 原生的权限策略。

### Phase 1 — 数据模型 + 契约

- 写 data-model.md 和 contracts/api.openapi.yaml。
- Alembic 迁移 `20260601_0006_chat_tables.py`（revision `0006`，down_revision
  `0005`），建 `conversations` + `messages`。

> **迁移重排注记**：本分支是从 `main@0005` 切出来的，早于 specs 006/007（它们也在
> 那附近分叉）。当 008 被 rebase 到一个已经带着它们迁移的 main 上时，把本
> revision + down_revision 重新编号、串到彼时 head 之后。这是一次例行的多 feature
> Alembic 调和 —— 不改 schema，只是重新指向 revision 链。

### Phase 2 — 后端实现

1. Domain：`BuiltinAgentConfig`、`Conversation`/`Message`/`ToolCall`、
   `RuntimeEvent` 联合 + `event_payload`。
2. Application：`make_builtin_agent_kind`、`ensure_default_builtin_agent`、
   最后一个 agent 的删除守卫；`ChatService` + ports。
3. Infrastructure：持久化 repo；`CompositeRuntimeFactory`；`BuiltinRuntime`
   （LangGraph）；`ExternalAgentRuntime`（子进程）。
4. Surfaces：`chat/routes.py`（+ SSE）、`chat/schemas.py`、`chat_cmd.py`；
   `chat_composition.py` 做默认 factory；启动时注册 `builtin_agent` kind 并 seed
   默认 agent。
5. importlinter Contract 7；对那个无类型引擎模块的 mypy override。

### Phase 3 — 测试

- 单元：`BuiltinAgentConfig` 校验（空白 model、temperature/max_tokens 边界、
  `requires_confirmation` globbing）；`event_payload` 形状。
- 用一个产出脚本化事件的 **fake runtime** 做集成：流式回复；tool-call → 确认 →
  批准/拒绝；stream 中途 stop；运行时错误 → 消息 `failed`；并发 send → 409；缺
  provider key → 503；第一轮往返后自动标题；模拟重启的持久化往返。
- 外部 runtime：经 `COFFER_CHAT_BIN_<TYPE>` 的 stub 二进制；缺二进制 → 结构化错
  误；stop 后不留孤儿子进程。
- 引擎隔离：importlinter 契约测试（SC-006）。
- acceptance 标记 `@pytest.mark.acceptance(spec="008-builtin-agent-chat", scenario="…")`，覆盖每个未推迟的场景。

### Phase 4 — 前端

- React `ChatPage`：会话列表、目标选择器（内置 + 支持 chat 的被管理 agent）、带
  tool-call 行 + 确认卡片的 streaming 消息视图、输入框、Stop 按钮。SSE 读取器把事
  件 `type` 映射到 UI。
- i18n 英文 + 简体中文。

## 风险 / 未知

- **LangChain/LangGraph API 变动**只在 `infrastructure/chat/` 里消化；port 挡住代
  码库其余部分。
- **外部 agent CLI 输出格式**随版本不同；行映射器刻意宽容（JSON `text` / Claude
  `stream-json` assistant 块 / 纯文本回退）。外部 agent 的确认钩子推迟。
- **provider 凭据发现**：云端 provider 需要一个 keychain ref 或一个环境变量 key；
  runtime 快速失败（503）而不是挂起。

## 推迟到未来规范的开放项

- Channels：把外部消息平台桥接进这个 chat（spec 009）。
- 在 CLI 暴露 permission-prompt 钩子的地方，对 external-agent runtime 强制确认。
- 把 `cursor` 以及其他没有文档化无头 streaming 模式的 agent 类型作为 chat 目标。
- 每个会话的 token 级成本 / 用量记账。
