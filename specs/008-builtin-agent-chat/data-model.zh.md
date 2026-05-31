# 数据模型 — 008 Built-in Agent & Chat

> English: [data-model.md](./data-model.md)

内置 agent 与 chat 界面的实体、字段、关系，以及 SQLite 新增。构建于与 kind
无关的 Resource 框架（spec 001）之上，并把外部 `agent` kind（spec 004）作为
chat 目标取并集。`builtin_agent` kind 是**增量**的 —— 它是它自己独立的 kind，
不是既有 `agent` kind 上的某个 `type`，并且复用 `resources` 表（agent 本身不新
增表）。

## Domain 实体

### `BuiltinAgentConfig`（`domain/builtin_agent/config.py`）

Pydantic v2 `BaseModel`，当 `kind == "builtin_agent"` 时存在 `Resource.config`
上。只做纯值级校验 —— `model` 字符串在这里是不透明的，由 infrastructure 里的
LangGraph runtime（`init_chat_model`）解析，所以 domain 不带任何引擎依赖。
`model_config = ConfigDict(extra="forbid")`。

| 字段             | 类型            | 备注                                                                                                            |
| ---------------- | --------------- | --------------------------------------------------------------------------------------------------------------- |
| `model`          | `str`           | provider 限定，`min_length=1`，不可为空白，例如 `anthropic:claude-sonnet-4-6`、`openai:gpt-4o`、`ollama:llama3` |
| `system_prompt`  | `str \| None`   | 可选引导 prompt；`None` = 无                                                                                    |
| `temperature`    | `float \| None` | 可选采样温度；`0.0 ≤ x ≤ 2.0`；`None` = provider 默认                                                           |
| `max_tokens`     | `int \| None`   | 可选输出上限；`> 0`；`None` = provider 默认                                                                     |
| `credential_ref` | `str \| None`   | provider API key 的 keychain ref（云端）；本地 provider（Ollama）或 key 来自环境变量时为 `None`                 |
| `use_gateway`    | `bool`          | 默认 `True`；为 true 时把 Coffer 自己的 MCP 网关工具给到 agent                                                  |
| `confirm_tools`  | `list[str]`     | 默认 `[]`；运行前需要人工确认的工具名 glob 模式                                                                 |

方法 `requires_confirmation(tool_name) -> bool`：当 `tool_name` 匹配任一
`confirm_tools` glob（通过 `fnmatch`）时返回 true。

seed 出来的默认 agent（`coffer`）出厂带
`model = "anthropic:claude-sonnet-4-6"`、一段简洁的 system prompt，以及一个保守
的破坏性操作确认策略：`["*delete*", "*clear*", "*remove*", "*write*"]`。

### `Conversation`（`domain/chat/conversation.py`）

Dataclass；`conversations` 表一行的内存表示。

| 字段             | 类型                 | 备注                                                        |
| ---------------- | -------------------- | ----------------------------------------------------------- |
| `id`             | `str`                | 不透明 id（默认 hex uuid）                                  |
| `target_ref`     | `str`                | `<kind>:<name>` —— `builtin_agent:<name>` 或 `agent:<name>` |
| `title`          | `str \| None`        | 占位符为 `"New chat"`，直到自动标题替换它                   |
| `status`         | `ConversationStatus` | `active` \| `archived`                                      |
| `model_snapshot` | `dict[str, Any]`     | 创建时记录的 model/config 快照（见下）                      |
| `created_at`     | `datetime`           | UTC                                                         |
| `updated_at`     | `datetime`           | UTC；每完成一轮、以及生命周期变更时被 touch                 |

属性：`target -> ResourceRef`（解析 `target_ref`）；`is_active -> bool`。

**model 快照**很小，按目标成形：

- 内置目标：`{"target": "builtin_agent:<name>", "model": "<model 字符串>"}`
- 外部目标：`{"target": "agent:<name>", "agent_type": "<claude_code|codex>"}`

### `Message`（`domain/chat/conversation.py`）

Dataclass；会话里的一条记录。

| 字段              | 类型                     | 备注                                                |
| ----------------- | ------------------------ | --------------------------------------------------- |
| `id`              | `str`                    | 持久化为 `messages.mid`（唯一）；不是行主键         |
| `conversation_id` | `str`                    | FK → `conversations.id`                             |
| `role`            | `MessageRole`            | `user` \| `assistant` \| `tool`                     |
| `content`         | `str`                    | 最终确定的文本（streaming delta 是瞬态的，不存）    |
| `status`          | `MessageStatus`          | `streaming` \| `complete` \| `failed` \| `canceled` |
| `created_at`      | `datetime`               | UTC                                                 |
| `tool_calls`      | `list[ToolCall]`         | 内嵌；默认 `[]`                                     |
| `error`           | `dict[str, Any] \| None` | failed 轮次的 `{"code", "message"}`；否则 `None`    |

### `ToolCall`（`domain/chat/conversation.py`）

内嵌在一条消息里的 dataclass。参数/结果只存**短摘要** —— 绝不存完整 payload ——
对齐网关 invocation-logging 的纪律（不泄露 secret）。

| 字段             | 类型           | 备注                                                                |
| ---------------- | -------------- | ------------------------------------------------------------------- |
| `id`             | `str`          | runtime 分配的 id；与 SSE `tool_call` / `confirmation` 事件 id 对齐 |
| `tool`           | `str`          | 工具名                                                              |
| `args_summary`   | `str`          | JSON 风格摘要，截断到 200 字符                                      |
| `result_summary` | `str \| None`  | 结果摘要，截断到 200 字符；工具结束前为 `None`                      |
| `confirmed`      | `bool \| None` | `None` = 不涉及确认；`True`/`False` = 批准/拒绝                     |

### Runtime 值对象（`domain/chat/runtime.py`）

纯的、与引擎无关的单元。`AgentRuntime` **port** 是 application 层
（`application/chat/ports.py`）里的一个 Protocol；这些值对象放在 domain，于是
每一层都能引用它们。

- `TurnMessage(role, content)` —— 作为历史交给 runtime 的一条先前消息。
- `ChatTurnRequest(history, user_message, confirm_tools)` —— runtime 工作一轮所需的一切。
- **Runtime 事件**（`RuntimeEvent` 联合），每个都有一个 `KIND` 类变量，同时充当 SSE 的 `type`：

| 事件                  | `KIND` / SSE `type` | payload 字段                  |
| --------------------- | ------------------- | ----------------------------- |
| `TextDelta`           | `text_delta`        | `text`                        |
| `ToolCallStarted`     | `tool_call`         | `id`、`tool`、`args`          |
| `ToolResultEvent`     | `tool_result`       | `id`、`tool`、`ok`、`summary` |
| `ConfirmationRequest` | `confirmation`      | `id`、`tool`、`args`          |
| `ErrorEvent`          | `error`             | `code`、`message`             |
| `DoneEvent`           | `done`              | （无）                        |

`event_payload(ev)` 把一个事件映射成经 SSE 流出的 JSON dict；wire 形状只定义一
次，就放在事件旁边。

## SQLite schema 新增

迁移 `20260601_0006_chat_tables.py`（revision `0006`，down_revision `0005`）新增
两张表。`builtin_agent` kind 复用既有 `resources` 表，所以 agent config 本身不
新增表。

> **迁移重排注记**：本分支是从 `main@0005` 切出来的，早于 specs 006/007（它们也
> 在那附近分叉）。当 008 被 rebase 到一个已经带着它们迁移的 main 上时，把本
> revision + down_revision 重新编号、串到彼时的 head 之后 —— 这是一次例行的多
> feature Alembic 调和，不改 schema。

### `conversations`

| 列                    | 类型              | 约束                                              |
| --------------------- | ----------------- | ------------------------------------------------- |
| `id`                  | `TEXT`            | 主键（`pk_conversations`）                        |
| `target_ref`          | `TEXT`            | not null；`<kind>:<name>`                         |
| `title`               | `TEXT`            | 可空                                              |
| `status`              | `TEXT`            | not null，默认 `active`（`active` \| `archived`） |
| `model_snapshot_json` | `TEXT`            | not null，默认 `{}`；JSON                         |
| `created_at`          | `TIMESTAMP`（tz） | not null                                          |
| `updated_at`          | `TIMESTAMP`（tz） | not null                                          |

索引：`idx_conversations_status_updated` on `(status, updated_at)` —— 支撑按
status 列举、按最近时间排序的查询。

### `messages`

| 列                | 类型              | 约束                                                            |
| ----------------- | ----------------- | --------------------------------------------------------------- |
| `seq`             | `INTEGER`         | 主键（`pk_messages`），autoincrement —— 在会话内排序消息        |
| `mid`             | `TEXT`            | 唯一（`uq_messages_mid`）；domain 里的 `Message.id`             |
| `conversation_id` | `TEXT`            | FK → `conversations.id` **ON DELETE CASCADE**                   |
| `role`            | `TEXT`            | not null（`user` \| `assistant` \| `tool`）                     |
| `content`         | `TEXT`            | not null，默认 `""`                                             |
| `tool_calls_json` | `TEXT`            | not null，默认 `[]`；tool-call dict 的 JSON 数组                |
| `status`          | `TEXT`            | not null（`streaming` \| `complete` \| `failed` \| `canceled`） |
| `error_json`      | `TEXT`            | 可空；JSON `{"code", "message"}`                                |
| `created_at`      | `TIMESTAMP`（tz） | not null                                                        |

索引：`idx_messages_conversation_seq` on `(conversation_id, seq)` —— 支撑按会话
有序拉取历史。

### 既有表的复用

- `resources`：`kind='builtin_agent'` 的新行。无 schema 变更。
- `audit_log`：写入新的事件类型（见下）。

## 新增 audit 事件类型

加入 `AuditEventType`（`domain/audit.py`）：

| 值                      | 何时发出                             |
| ----------------------- | ------------------------------------ |
| `conversation_created`  | 创建一个会话（details 记录目标 ref） |
| `conversation_renamed`  | 重命名一个会话（手动或由自动标题）   |
| `conversation_archived` | 归档一个会话                         |
| `conversation_restored` | 把一个已归档会话恢复为 active        |
| `conversation_deleted`  | 删除一个会话（及其级联的消息）       |

built-in-agent 的生命周期（create / update / enable / disable / delete /
重新 seed）复用既有的、与 kind 无关的 Resource audit 事件（`resource_created`、
…）；seeding helper 为默认 agent 记一条 `resource_created`。内置 runtime 通过网
关发起的工具调用共用既有的网关 invocation-logging 界面（仅工具名）。

## 关系

```
Resource (kind=builtin_agent)  ──< 被目标指向 >──  Conversation (target_ref="builtin_agent:<name>")
Resource (kind=agent)          ──< 被目标指向 >──  Conversation (target_ref="agent:<name>")
Conversation 1 ───< 拥有多个 >─── Message            (ON DELETE CASCADE)
Message      1 ───< 内嵌     >─── ToolCall           (在 tool_calls_json 里)
```

- 一个会话精确针对一个 agent resource，在创建时选定。
- 目标不是硬 FK（它是一个 `<kind>:<name>` ref 字符串）；目标被删后会话对新一轮
  变只读（下次 `send` 返回 `TARGET_AGENT_MISSING`），读路径仍可用。

## Application 服务契约（`application/chat/service.py`）

`ChatService` 只通过 `AgentRuntime` port 跟 agent 打交道，所以它对内置
（LangGraph）和外部（子进程）runtime 是同一套。它在内存里**每个会话持有一轮进
行中的对话**，以强制单飞（409）、路由确认决定、并支持 stop。

| 方法                                                     | 用途                                                                                                                                                                                                       |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `create_conversation(target_ref, actor) -> Conversation` | 解析 + 校验目标（非 chat kind 则 `NotAChatTarget`，`ResourceNotFound`→404），记 model 快照、审计。                                                                                                         |
| `list_conversations(status, limit, offset) -> list`      | 分页列举，可按 status 过滤。                                                                                                                                                                               |
| `get_conversation(id) -> Conversation`                   | 不存在则 `ConversationNotFound`（404）。                                                                                                                                                                   |
| `get_messages(id) -> list[Message]`                      | 有序消息历史。                                                                                                                                                                                             |
| `rename(id, title, actor) -> Conversation`               | 设标题；审计 `conversation_renamed`。                                                                                                                                                                      |
| `archive / restore(id, actor) -> Conversation`           | 切换 status；审计。                                                                                                                                                                                        |
| `delete(id, actor) -> None`                              | 删除会话（消息级联）；审计 `conversation_deleted`。                                                                                                                                                        |
| `send(id, text, actor) -> AsyncIterator[RuntimeEvent]`   | 校验文本（`MessageRejected`），忙则拒绝（`ConversationBusy`→409），**在持久化之前**构建 runtime（缺 key 则抛 `LlmNotConfigured`→503 且不写半截），持久化 user + streaming-assistant 消息，返回这一轮的流。 |
| `resolve_confirmation(id, request_id, approve) -> None`  | 把一个批准/拒绝决定路由给进行中的 runtime。                                                                                                                                                                |
| `stop(id) -> None`                                       | 标记为已停止并请 runtime 停止；没有进行中的一轮时为 no-op。                                                                                                                                                |

一轮完成时 `_finalize` 持久化最终确定的 assistant 内容、tool-call 元数据、status
（`complete`/`failed`/`canceled`）以及任何结构化错误；然后，对一个占位标题会话
的第一轮往返，应用自动标题（生成器或截断首条消息的回退）。finalize 期间的持久化
失败被吞掉，于是一个 streaming 错误绝不破坏 store。

## Ports（`application/chat/ports.py`）

- `ConversationRepo`、`MessageRepo` —— 持久化（→ `infrastructure/chat/persistence.py`）。
- `AgentRuntime` —— 一轮的执行；`stream`、`resolve_confirmation`、`stop`。
- `RuntimeFactory` —— `build(target, config) -> AgentRuntime`；`target.kind` 选
  实现（`builtin_agent` → LangGraph；`agent` → 子进程）。
- `TitleGenerator` —— 可选；`generate(user, assistant) -> str | None`。

## Infrastructure 适配器（`infrastructure/chat/`）

- `persistence.py` —— SQLAlchemy `ConversationRepo` / `MessageRepo`。
- `runtime_factory.py` —— `CompositeRuntimeFactory`；在 `build` 内部惰性 import
  那些重的 runtime 模块，于是启动时的 wiring 永远不需要 LangChain。
- `builtin_runtime.py` —— `BuiltinRuntime`；**唯一**一个 import LangChain/LangGraph
  的模块（importlinter Contract 7），且即便如此 import 也是惰性的（在 `stream`
  内）。用 `init_chat_model` 解析 model，通过 `langchain-mcp-adapters` 从 Coffer
  自己的 `/mcp` endpoint 加载网关工具，把需确认的工具包一层使其暂停等人决定，跑
  一个 `create_react_agent` 循环，并把 `astream_events` 映射成 runtime 事件。
- `external_runtime.py` —— `ExternalAgentRuntime`；以 streaming 模式把 `claude` /
  `codex` 作为本地子进程拉起（二进制来自 `COFFER_CHAT_BIN_<TYPE>` 或 PATH），把
  stdout 行映射成事件，在 agent 的 `config_dir` 下运行，并始终回收子进程（结束 /
  出错 / 停止 / 关闭时都不留孤儿）。

## 约束小结

- 全部 HTTP 仅 loopback；内置 runtime 用 daemon token 经 `127.0.0.1` 触及网关。
- LangGraph / LangChain 限制在 `infrastructure/chat/`（importlinter Contract 7）；
  domain + application 只通过 `AgentRuntime` port 触及引擎。
- user 消息文本：1–32768 字符，在 API 边界强制。
- 每个会话一轮进行中的 streaming（单飞，冲突时 409）。
- 确认为内置 runtime 接通；v1 的外部 agent 在它们自己的权限策略下运行（那里的
  `resolve_confirmation` 是 no-op）。
