# Data Model — 008 Agent Chat

Entities, ports, the frozen agent-platform contract, SQLite schema, and event
types for the chat platform and the built-in agent. Conversations / messages /
models are **not** Resources.

## Domain entities (`backend/coffer/domain/chat/`)

### `Conversation` (`domain/chat/conversation.py`)

Frozen dataclass — domain stays pure.

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | uuid4 hex |
| `agent_key` | `str` | which agent the thread talks to; default `"builtin"` |
| `title` | `str` | auto-generated from the first user message; user-editable |
| `model_id` | `str \| None` | `chat_models.id` override; `None` → default model. Built-in agent's per-conversation model storage. |
| `agent_config` | `str \| None` (JSON) | Provider-owned per-conversation state (Alembic `0018`). CLI agents store `{cwd, session_id, permission_mode?}` here; the built-in agent stores nothing (it uses `model_id`). Read/written via `ConversationRepo.get_agent_config` / `set_agent_config`. |
| `archived_at` | `datetime \| None` | `None` = active; a timestamp = archived (Alembic `0013`). Drives the active/archived filter and the two-stage retention lifecycle. |
| `created_at` / `updated_at` | `datetime` | UTC; `updated_at` bumped on each new message |

### `Message` (`domain/chat/message.py`)

Unchanged. Fields: `id`, `conversation_id`, `seq` (0-based), `role`
(`user`|`assistant`), `content` (`list[ContentBlock]`), `status`
(`complete`|`streaming`|`failed`), `model_id`, `prompt_tokens`,
`completion_tokens`, `created_at`. `ContentBlock` = `TextBlock` |
`ToolUseBlock` | `ToolResultBlock`.

### `ModelConfig` (`domain/chat/model.py`)

Unchanged. `id`, `display_name` (unique), `provider`
(`anthropic`|`openai`|`ollama`), `model`, `credential_ref` (required for cloud),
`base_url` (required for ollama), `is_default`, timestamps.

### `AgentEvent` (`domain/chat/events.py`)

Union of frozen dataclasses streamed by an `AgentAdapter` during a turn.
**`ApprovalRequest` is added by this revision**; all others are unchanged:

- `TurnStarted()`
- `TextDelta(text: str)`
- `ToolCall(tool_use_id, tool_name, tool_input)`
- `ToolResult(tool_use_id, tool_name, output, error)`
- `ApprovalRequest(request_id, tool_use_id, tool_name, tool_input)` — **new**
- `TurnDone(prompt_tokens, completion_tokens, stop_reason)`
- `TurnError(code, message)`

Each carries a `type` discriminator reused verbatim as the SSE event name;
`ApprovalRequest.type == "approval_request"`.

## Frozen platform contract

The interfaces below are the platform seam. They are **frozen** — a second
agent provider is built against exactly these and nothing else.

```python
# domain/chat/events.py
@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]
    type: Literal["approval_request"] = "approval_request"

# application/chat/ports.py
@dataclass(frozen=True)
class ApprovalDecision:
    behavior: Literal["allow", "deny"]
    message: str | None = None

class ApprovalGate(Protocol):
    """Inbound channel a running turn waits on for a human approval decision.
    wait() raises CancelledError when the turn is interrupted."""
    async def wait(self, request_id: str) -> ApprovalDecision: ...

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
        self, *, history: Sequence[Message], approvals: ApprovalGate,
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
- **`ApprovalChannel`** (`application/chat/approvals.py`) — concrete
  `ApprovalGate`. Holds `dict[request_id, Future[ApprovalDecision]]`.
  `wait(request_id)` awaits the future; `resolve(request_id, decision)` sets it
  (raises `ApprovalNotFound` when no pending future matches). Pure asyncio.
- **`BuiltinAgentProvider`** (`infrastructure/chat/builtin_provider.py`) —
  the one registered provider. `init_conversation` validates `agent_config`'s
  optional `model_id` and stores it on `conversations.model_id`. `build_adapter`
  resolves the model (→ `NoModelConfigured` if none), builds the LangChain
  model, fetches the skill catalogue, builds the system prompt, and returns a
  per-turn `LangGraphBuiltinAgent`. `availability()` → `True`.
- **`LangGraphBuiltinAgent`** (`infrastructure/chat/langgraph_agent.py`) — the
  `AgentAdapter` for the built-in agent. Built per turn with its model, tool
  gateway, system prompt, and resolved `model_id`. `run_turn(history, approvals)`
  trims history to the context budget, drives the LangGraph ReAct loop, and
  ignores `approvals` (the built-in agent does not use the approval channel).

## Domain errors (`domain/errors.py`)

Existing: `ConversationNotFound` (404), `ModelNotFound` (404), `ModelRejected`
(400), `NoModelConfigured` (409), `TurnInProgress` (409).

**Added by this revision:**

- `UnknownAgent` — code `"UNKNOWN_AGENT"` → 400; `agent_key` has no provider.
- `AgentConfigRejected` — code `"AGENT_CONFIG_REJECTED"` → 400; a provider
  rejects its `agent_config` (carries a `reason`).
- `ApprovalNotFound` — code `"APPROVAL_NOT_FOUND"` → 409; an approval decision
  references an unknown or already-decided `request_id`.

## SQLite schema

The platform refactor itself added no columns — the built-in agent's only
per-conversation config is the existing `model_id` column. The CLI agents,
needing per-conversation working directory + session state, added the generic
`conversations.agent_config` JSON column (Alembic `0018`) through the same
`init_conversation` seam, exactly the "a future provider brings its own
persistent config" extension point the platform anticipated — no change to the
chat surface or the wire contract.

Tables: `conversations` (Alembic `0005`; `archived_at` `0013`; `agent_config`
`0018`), `chat_messages`, `chat_models`.

## Cascade & integrity rules

| Action | Effect |
|---|---|
| Create a conversation | Persist the row, then `provider.init_conversation`. If the provider rejects the config, the conversation row is rolled back (deleted) and the error surfaces. |
| Interrupt a turn | Cancel the turn task; the task's handler persists the **partial** assistant message (`status='complete'`, `stop_reason='interrupted'`) and emits a terminal `TurnDone`. |
| Delete a conversation | Cancel any live turn (discard — no partial persisted); `provider.on_conversation_deleted`; `MessageRepo.delete_by_conversation`; delete the conversation row; audit `conversation_deleted`. |
| Submit an approval | Routed to the conversation's active turn's `ApprovalChannel`; `ApprovalNotFound` (409) when no pending request matches. |
| Delete a model in use | Allowed; conversations referencing it resolve the default at turn time. |
| Daemon startup | Sweep: any `chat_messages.status='streaming'` → `failed`. |

## Audit events (`domain/audit.py`)

Unchanged: `conversation_created`, `conversation_deleted`,
`chat_turn_completed` (actor `agent`), `model_created` / `model_updated` /
`model_deleted`.

## Wire contract (REST + SSE)

Lives in `contracts/api.openapi.yaml`. Routes added/changed by this revision:

- `GET /api/v1/chat/agents` — list registered agents — **new**
- `POST /api/v1/chat/conversations` — body `{agent_key?, agent_config?}` — **changed**
- `POST /api/v1/chat/conversations/{id}/approvals` — `{request_id, behavior, message?}` → 204 / 409 — **new**
- `POST /api/v1/chat/conversations/{id}/interrupt` → 204 — **new**

Unchanged routes: conversation list/get/patch/delete, message history, the
`POST .../messages` SSE turn endpoint (its stream may now also carry
`approval_request` events), and the `/api/v1/models` CRUD.

SSE event names on the message POST: `turn_start`, `text_delta`, `tool_call`,
`tool_result`, `approval_request`, `turn_done`, `turn_error` — one per
`AgentEvent` variant.
