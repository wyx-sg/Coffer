# Data Model — 008 Agent Chat

> 中文版: [data-model.zh.md](./data-model.zh.md)

Entities, ports, the frozen agent-platform contract, SQLite schema, and event
types for the chat platform and the built-in agent. Conversations / messages /
models are **not** Resources.

## Domain entities (`backend/coffer/domain/chat/`)

### `Conversation` (`domain/chat/conversation.py`)

Frozen dataclass — domain stays pure.

| Field                       | Type                 | Notes                                                                                                                                                                                                                                                   |
| --------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                        | `str`                | uuid4 hex                                                                                                                                                                                                                                               |
| `agent_key`                 | `str`                | which agent the thread talks to; default `"builtin"`                                                                                                                                                                                                    |
| `title`                     | `str`                | auto-generated from the first user message; user-editable                                                                                                                                                                                               |
| `model_id`                  | `str \| None`        | **Vestigial legacy column.** Once a `chat_models.id` override into the internal-engine `ModelConfig` registry, which is now **retired** (folded into provider connections, spec 011 / ADR-032). **Not read by the managed-agent turn path** (ADR-024); the internal engine selects its model from the internal-default connection. Out of scope for the chat model picker. |
| `agent_config`              | `str \| None` (JSON) | Provider-owned per-conversation state (Alembic `0018`). Managed agents (Claude Code / Codex) store `{cwd, session_id, model}` here; `model` is the agent's own per-conversation model (free-text, passed through to its CLI), set via the agent-config PATCH route mirroring `/model`. Read/written via `ConversationRepo.get_agent_config` / `set_agent_config`. |
| `archived_at`               | `datetime \| None`   | `None` = active; a timestamp = archived (Alembic `0013`). Drives the active/archived filter and the two-stage retention lifecycle.                                                                                                                      |
| `channel_name`              | `str \| None`        | Optional IM channel binding (ADR-031): the channel this conversation is also driven from. A conversation "has a channel binding" iff this is set (Alembic `0021`).                                                                                       |
| `peer_chat_id`              | `str \| None`        | The IM chat id used as the return address for relaying the agent's output back to the channel. Paired with `channel_name` (Alembic `0021`).                                                                                                             |
| `created_at` / `updated_at` | `datetime`           | UTC; `updated_at` bumped on each new message                                                                                                                                                                                                            |

> **ADR-031** removed the former `origin` (web/channel) and `peer_display_name`
> fields (Alembic `0034`): under the single-owner premise the IM peer is always
> the owner, so there is no separate peer identity to display; "is this a channel
> conversation" is derived from `channel_name` being set.

### `Message` (`domain/chat/message.py`)

Unchanged. Fields: `id`, `conversation_id`, `seq` (0-based), `role`
(`user`|`assistant`), `content` (`list[ContentBlock]`), `status`
(`complete`|`streaming`|`failed`), `model_id`, `prompt_tokens`,
`completion_tokens`, `created_at`. `ContentBlock` = `TextBlock` |
`ToolUseBlock` | `ToolResultBlock`.

### `AgentEvent` (`domain/chat/events.py`)

Union of frozen dataclasses streamed by an `AgentAdapter` during a turn:

- `TurnStarted()`
- `TextDelta(text: str)`
- `ToolCall(tool_use_id, tool_name, tool_input)`
- `ToolResult(tool_use_id, tool_name, output, error)`
- `TurnDone(prompt_tokens, completion_tokens, stop_reason)`
- `TurnError(code, message)`
- `QueueChanged(pending: list[str])` — the ordered pending-queue texts (ADR-031);
  broadcast so every subscriber renders the same pending chips. `type =
  "queue_changed"`.

Each carries a `type` discriminator reused verbatim as the SSE event name. Turn
events are published to a **per-conversation broadcaster** (with a ring buffer of
the current turn's events for late-subscriber replay) that any number of clients
attach to via `GET /conversations/{id}/events` (ADR-031); the orchestrator no
longer hands a single consumer queue to the POST request.

## Frozen platform contract

The interfaces below are the platform seam. They are **frozen** — a second
agent provider is built against exactly these and nothing else.

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

`ToolGateway` / `ToolSpec` (unchanged) remain the built-in agent's view of the
aggregated tool surface; they are an infrastructure-side concern of the
built-in agent, not part of the frozen seam.

## Platform components

- **`AgentProviderRegistry`** (`application/chat/registry.py`) — maps
  `agent_key` → provider + display name. `register(provider, display_name)`,
  `get(agent_key)` (raises `UnknownAgent`), `entries()` (for `GET /agents`).
- **`BuiltinAgentProvider`** (`infrastructure/chat/builtin_provider.py`) —
  the one registered provider. `init_conversation` validates `agent_config`'s
  optional `model_id` and stores it on `conversations.model_id`. `build_adapter`
  resolves the model (→ `NoModelConfigured` if none), builds the LangChain
  model, fetches the skill catalogue, builds the system prompt, and returns a
  per-turn `LangGraphBuiltinAgent`. `availability()` → `True`.
- **`LangGraphBuiltinAgent`** (`infrastructure/chat/langgraph_agent.py`) — the
  `AgentAdapter` for the built-in agent. Built per turn with its model, tool
  gateway, system prompt, and resolved `model_id`. `run_turn(history)`
  trims history to the context budget and drives the LangGraph ReAct loop.

## Domain errors (`domain/errors.py`)

Existing: `ConversationNotFound` (404), `TurnInProgress` (409). (The chat
model-registry errors `ModelNotFound` / `ModelRejected` / `NoModelConfigured`
were removed with the retired `ModelConfig` registry, spec 011 / ADR-032;
transcript distillation keeps its own `NoModelConfiguredError` → wire
`NO_MODEL_CONFIGURED` (409) when no internal connection is set.)

**Added by this revision:**

- `UnknownAgent` — code `"UNKNOWN_AGENT"` → 400; `agent_key` has no provider.
- `AgentConfigRejected` — code `"AGENT_CONFIG_REJECTED"` → 400; a provider
  rejects its `agent_config` (carries a `reason`).

## SQLite schema

The platform refactor itself added no columns — the built-in agent's only
per-conversation config is the existing `model_id` column. The CLI agents,
needing per-conversation working directory + session state, added the generic
`conversations.agent_config` JSON column (Alembic `0018`) through the same
`init_conversation` seam, exactly the "a future provider brings its own
persistent config" extension point the platform anticipated — no change to the
chat surface or the wire contract.

Tables: `conversations` (Alembic `0005`; `archived_at` `0013`; `agent_config`
`0018`), `chat_messages`. The former `chat_models` table is retired with the
`ModelConfig` registry (spec 011 / ADR-032).

## Cascade & integrity rules

| Action                | Effect                                                                                                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Create a conversation | Persist the row, then `provider.init_conversation`. If the provider rejects the config, the conversation row is rolled back (deleted) and the error surfaces.                               |
| Send while a turn runs | Enqueue on the in-memory pending queue (ADR-031); broadcast `QueueChanged`. When the in-flight turn ends, dequeue the head, commit it as the next user message, and run its turn (sequential FIFO). Not rejected. |
| Interrupt a turn      | Cancel the turn task; the task's handler persists the **partial** assistant message (`status='complete'`, `stop_reason='interrupted'`) and emits a terminal `TurnDone`. Also **pauses** the pending queue — queued messages are held, not auto-run (ADR-031).                     |
| Delete a conversation | Cancel any live turn (discard — no partial persisted); `provider.on_conversation_deleted`; `MessageRepo.delete_by_conversation`; delete the conversation row; audit `conversation_deleted`. The pending queue is dropped.                       |
| Delete a model in use | Allowed; conversations referencing it resolve the default at turn time.                                                                                                                     |
| Daemon startup        | Sweep: any `chat_messages.status='streaming'` → `failed`.                                                                                                                                   |

## Audit events (`domain/audit.py`)

Unchanged: `conversation_created`, `conversation_deleted`,
`chat_turn_completed` (actor `agent`), `model_created` / `model_updated` /
`model_deleted`.

## Wire contract (REST + SSE)

Lives in `contracts/api.openapi.yaml`. Routes added/changed by **ADR-031**:

- `GET /api/v1/chat/conversations/{id}/events` — SSE subscribe to the
  conversation's live turn events (replay-then-live) — **new**
- `POST /api/v1/chat/conversations/{id}/messages` — now **fire-and-return**: starts
  or enqueues a turn and returns `202 {queued: bool}`; it is no longer the event
  stream — **changed**
- `ConversationOut` drops `origin`/`peer`; gains optional `channel_binding`
  (`{channel, chat_id}`) — **changed**

Routes added by the per-conversation-model repositioning ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) → [ADR-032](../../docs/decisions/ADR-032-provider-switching.md)):

- `GET /api/v1/chat/conversations/{id}/agent-config` — read `{cwd, model}` — **new**
- `PATCH /api/v1/chat/conversations/{id}/agent-config` — set `agent_config.model` (managed agents), preserving `cwd`/`session_id`; empty clears the override — **new**

Unchanged routes: `GET /chat/agents`, conversation list/get/patch/delete/archive/
unarchive, message history, `POST .../interrupt` → 204, and the `/api/v1/models`
CRUD.

SSE event names on the subscribe stream: `turn_start`, `text_delta`, `tool_call`,
`tool_result`, `turn_done`, `turn_error`, `queue_changed`.
