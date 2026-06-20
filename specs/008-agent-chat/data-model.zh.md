# 数据模型 — 008 Agent Chat

> English: [data-model.md](./data-model.md)

聊天平台与内置 agent 的实体、端口、冻结的 agent 平台契约、SQLite schema 与事件
类型。对话 / 消息 / 模型**不是** Resource。

## 领域实体（`backend/coffer/domain/chat/`）

### `Conversation`（`domain/chat/conversation.py`）

Frozen dataclass —— domain 保持纯净。

| 字段                        | 类型                 | 说明                                                                                                                                                                                                                         |
| --------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                        | `str`                | uuid4 hex                                                                                                                                                                                                                    |
| `agent_key`                 | `str`                | 该线程对话所用的 agent；默认 `"builtin"`                                                                                                                                                                                     |
| `title`                     | `str`                | 从首条用户消息自动生成；用户可编辑                                                                                                                                                                                           |
| `model_id`                  | `str \| None`        | `chat_models.id` 覆盖项；`None` → 默认模型。内置 agent 的每对话模型存储。                                                                                                                                                    |
| `agent_config`              | `str \| None` (JSON) | provider 自有的每对话状态（Alembic `0018`）。CLI agent 在此存储 `{cwd, session_id, permission_mode?}`；内置 agent 不存储任何东西（它使用 `model_id`）。通过 `ConversationRepo.get_agent_config` / `set_agent_config` 读/写。 |
| `archived_at`               | `datetime \| None`   | `None` = 活跃；时间戳 = 已归档（Alembic `0013`）。驱动活跃/已归档过滤器与两阶段保留生命周期。                                                                                                                                |
| `channel_name`              | `str \| None`        | 可选的 IM channel binding（ADR-031）：本对话同样从其被驱动的 channel。一个对话"有一个 channel binding"当且仅当本字段被设置（Alembic `0021`）。                                                                                |
| `peer_chat_id`              | `str \| None`        | 用作回邮地址、把 agent 输出转发回 channel 的 IM chat id。与 `channel_name` 配对（Alembic `0021`）。                                                                                                                          |
| `created_at` / `updated_at` | `datetime`           | UTC；每条新消息都会 bump `updated_at`                                                                                                                                                                                        |

> **ADR-031** 移除了原先的 `origin`（web/channel）与 `peer_display_name`
> 字段（Alembic `0034`）：在单属主前提下 IM peer 永远是属主，所以没有单独的 peer
> 身份要显示；"这是不是一个 channel 对话"由 `channel_name` 是否被设置导出。

### `Message`（`domain/chat/message.py`）

未变。字段：`id`、`conversation_id`、`seq`（从 0 开始）、`role`
（`user`|`assistant`）、`content`（`list[ContentBlock]`）、`status`
（`complete`|`streaming`|`failed`）、`model_id`、`prompt_tokens`、
`completion_tokens`、`created_at`。`ContentBlock` = `TextBlock` |
`ToolUseBlock` | `ToolResultBlock`。

### `ModelConfig`（`domain/chat/model.py`）

未变。`id`、`display_name`（唯一）、`provider`
（`anthropic`|`openai`|`ollama`）、`model`、`credential_ref`（云端必填）、
`base_url`（ollama 必填）、`is_default`、时间戳。

### `AgentEvent`（`domain/chat/events.py`）

由一个 `AgentAdapter` 在一个回合期间流出的 frozen dataclass 的 union：

- `TurnStarted()`
- `TextDelta(text: str)`
- `ToolCall(tool_use_id, tool_name, tool_input)`
- `ToolResult(tool_use_id, tool_name, output, error)`
- `TurnDone(prompt_tokens, completion_tokens, stop_reason)`
- `TurnError(code, message)`
- `QueueChanged(pending: list[str])` —— 有序的待处理队列文本（ADR-031）；广播以让每个
  订阅者渲染相同的 pending chips。`type = "queue_changed"`。

每个都携带一个 `type` 判别符，原样复用为 SSE 事件名。回合事件被发布到一个**每对话的
broadcaster**（带一个当前回合事件的环形缓冲区，供迟到订阅者回放），任意数量的客户端
通过 `GET /conversations/{id}/events` 挂接它（ADR-031）；orchestrator 不再把一个单一的
消费者队列交给 POST 请求。

## 冻结的平台契约

下方的接口就是平台接缝。它们是**冻结的** —— 第二个 agent provider 恰好针对
这些、且仅针对这些来构建。

```python
# application/chat/ports.py
class AgentAdapter(Protocol):
    """One agent's handling of one turn. The adapter is self-contained — it
    carries its own model, tools, and configuration (injected by its provider
    at build time). It MUST yield a terminal TurnDone or TurnError before the
    iterator ends (unless cancelled), and on asyncio.CancelledError it MUST
    clean up and re-raise.

    An adapter MAY also expose an optional ``model_id: str`` attribute naming
    the model the turn ran on; the orchestrator records it on the assistant
    message when present. It is optional (adapters with no Coffer-registered
    model omit it) and therefore not part of this frozen Protocol."""
    async def run_turn(
        self, *, history: Sequence[Message],
    ) -> AsyncIterator[AgentEvent]: ...

class AgentProvider(Protocol):
    agent_key: str
    async def init_conversation(
        self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        """Validate + persist agent-specific config at conversation creation;
        an invalid config raises a domain error (mapped to 400)."""
    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        """Build a configured adapter per turn. The built-in provider resolves
        the model here and raises NoModelConfigured when none exists."""
    async def on_conversation_deleted(self, conversation_id: str) -> None:
        """Tear down agent-specific state; idempotent."""
    async def availability(self) -> bool:
        """Whether this agent can currently be picked."""
```

`ToolGateway` / `ToolSpec`（未变）仍是内置 agent 对聚合后工具表面的视图；它们是
内置 agent 的 infrastructure 侧关注点，不属于冻结的接缝。

## 平台组件

- **`AgentProviderRegistry`**（`application/chat/registry.py`）—— 将
  `agent_key` → provider + display name。`register(provider, display_name)`、
  `get(agent_key)`（抛出 `UnknownAgent`）、`entries()`（供 `GET /agents`）。
- **`BuiltinAgentProvider`**（`infrastructure/chat/builtin_provider.py`）——
  唯一注册的 provider。`init_conversation` 校验 `agent_config` 中可选的
  `model_id` 并把它存到 `conversations.model_id`。`build_adapter` 解析模型
  （无则 → `NoModelConfigured`），构建 LangChain 模型，获取 skill 目录，构建
  system prompt，并返回一个每回合的 `LangGraphBuiltinAgent`。`availability()` →
  `True`。
- **`LangGraphBuiltinAgent`**（`infrastructure/chat/langgraph_agent.py`）——
  内置 agent 的 `AgentAdapter`。每回合连同它的模型、工具 gateway、system prompt
  与已解析的 `model_id` 一并构建。`run_turn(history)` 将历史裁剪到
  上下文预算，并驱动 LangGraph ReAct 循环。

## 领域错误（`domain/errors.py`）

现有：`ConversationNotFound`（404）、`ModelNotFound`（404）、`ModelRejected`
（400）、`NoModelConfigured`（409）、`TurnInProgress`（409）。

**本次修订新增：**

- `UnknownAgent` —— code `"UNKNOWN_AGENT"` → 400；`agent_key` 没有对应 provider。
- `AgentConfigRejected` —— code `"AGENT_CONFIG_REJECTED"` → 400；一个 provider
  拒绝它的 `agent_config`（携带一个 `reason`）。

## SQLite schema

平台重构本身没有新增列 —— 内置 agent 唯一的每对话配置就是已有的 `model_id` 列。
CLI agent 需要每对话的工作目录 + session 状态，通过同一个 `init_conversation`
接缝新增了通用的 `conversations.agent_config` JSON 列（Alembic `0018`），这正是
平台所预期的"一个未来 provider 自带它自己的持久化配置"扩展点 —— 不改动聊天界面
或 wire 契约。

表：`conversations`（Alembic `0005`；`archived_at` `0013`；`agent_config`
`0018`）、`chat_messages`、`chat_models`。

## 级联与完整性规则

| 动作               | 效果                                                                                                                                                              |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 创建一个对话       | 持久化该行，然后 `provider.init_conversation`。若 provider 拒绝该配置，对话行被回滚（删除）且错误浮现。                                                           |
| 在一个回合运行时发送 | 在内存待处理队列上入队（ADR-031）；广播 `QueueChanged`。当进行中回合结束时，把队首出队、把它提交为下一条用户消息，并运行它的回合（顺序 FIFO）。不被拒绝。 |
| 中断一个回合       | 取消该回合任务；任务的 handler 持久化**部分的**助手消息（`status='complete'`、`stop_reason='interrupted'`）并发出一个终结的 `TurnDone`。也**暂停**待处理队列 —— 排队的消息被保留、不自动运行（ADR-031）。 |
| 删除一个对话       | 取消任何活跃回合（丢弃 —— 不持久化部分内容）；`provider.on_conversation_deleted`；`MessageRepo.delete_by_conversation`；删除对话行；审计 `conversation_deleted`。待处理队列被丢弃。 |
| 删除一个在用的模型 | 允许；引用它的对话在回合时解析为默认模型。                                                                                                                        |
| 守护进程启动       | 清扫：任何 `chat_messages.status='streaming'` → `failed`。                                                                                                        |

## 审计事件（`domain/audit.py`）

未变：`conversation_created`、`conversation_deleted`、
`chat_turn_completed`（actor `agent`）、`model_created` / `model_updated` /
`model_deleted`。

## Wire 契约（REST + SSE）

位于 `contracts/api.openapi.yaml`。**ADR-031** 新增/改动的路由：

- `GET /api/v1/chat/conversations/{id}/events` —— SSE 订阅该对话的实时回合事件
  （回放-然后-实时）—— **新增**
- `POST /api/v1/chat/conversations/{id}/messages` —— 现在是 **fire-and-return**：
  发起或入队一个回合并返回 `202 {queued: bool}`；它不再是事件流 —— **改动**
- `ConversationOut` 去掉 `origin`/`peer`；新增可选的 `channel_binding`
  （`{channel, chat_id}`）—— **改动**

未变路由：`GET /chat/agents`、对话 list/get/patch/delete/archive/unarchive、消息
历史、`POST .../interrupt` → 204，以及 `/api/v1/models` CRUD。

订阅流上的 SSE 事件名：`turn_start`、`text_delta`、`tool_call`、`tool_result`、
`turn_done`、`turn_error`、`queue_changed`。
