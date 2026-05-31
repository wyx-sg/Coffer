# Data Model — 008 Built-in Agent & Chat

Entities, fields, relationships, and SQLite additions for the built-in agent
and the chat surface. Builds on the kind-agnostic Resource framework (spec 001) and unions the external `agent` kind (spec 004) as a chat target. The
`builtin_agent` kind is **additive** — it is its own kind, not a `type` on the
existing `agent` kind, and it reuses the `resources` table (no new table for
the agent itself).

## Domain entities

### `BuiltinAgentConfig` (`domain/builtin_agent/config.py`)

Pydantic v2 `BaseModel` stored on `Resource.config` when `kind == "builtin_agent"`.
Pure value-level validation only — the `model` string is opaque here and is
resolved by the LangGraph runtime in infrastructure (`init_chat_model`), so the
domain carries no engine dependency. `model_config = ConfigDict(extra="forbid")`.

| Field            | Type            | Notes                                                                                                                         |
| ---------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `model`          | `str`           | provider-qualified, `min_length=1`, must not be blank, e.g. `anthropic:claude-sonnet-4-6`, `openai:gpt-4o`, `ollama:llama3`   |
| `system_prompt`  | `str \| None`   | optional steering prompt; `None` = none                                                                                       |
| `temperature`    | `float \| None` | optional sampling temperature; `0.0 ≤ x ≤ 2.0`; `None` = provider default                                                     |
| `max_tokens`     | `int \| None`   | optional output cap; `> 0`; `None` = provider default                                                                         |
| `credential_ref` | `str \| None`   | keychain ref for the provider API key (cloud); `None` for local providers (Ollama) or when the key comes from the environment |
| `use_gateway`    | `bool`          | default `True`; when true the agent is given Coffer's own MCP gateway tools                                                   |
| `confirm_tools`  | `list[str]`     | default `[]`; tool-name glob patterns that require human confirmation before running                                          |

Method `requires_confirmation(tool_name) -> bool` returns true when `tool_name`
matches any `confirm_tools` glob (via `fnmatch`).

The seeded default agent (`coffer`) ships with
`model = "anthropic:claude-sonnet-4-6"`, a concise system prompt, and a
conservative destructive-op confirm policy: `["*delete*", "*clear*", "*remove*", "*write*"]`.

### `Conversation` (`domain/chat/conversation.py`)

Dataclass; in-memory representation of one row from `conversations`.

| Field            | Type                 | Notes                                                        |
| ---------------- | -------------------- | ------------------------------------------------------------ |
| `id`             | `str`                | opaque id (hex uuid by default)                              |
| `target_ref`     | `str`                | `<kind>:<name>` — `builtin_agent:<name>` or `agent:<name>`   |
| `title`          | `str \| None`        | placeholder is `"New chat"` until the auto-title replaces it |
| `status`         | `ConversationStatus` | `active` \| `archived`                                       |
| `model_snapshot` | `dict[str, Any]`     | model/config snapshot recorded at creation (see below)       |
| `created_at`     | `datetime`           | UTC                                                          |
| `updated_at`     | `datetime`           | UTC; touched on each completed turn and on lifecycle changes |

Properties: `target -> ResourceRef` (parses `target_ref`); `is_active -> bool`.

The **model snapshot** is small and target-shaped:

- built-in target: `{"target": "builtin_agent:<name>", "model": "<model string>"}`
- external target: `{"target": "agent:<name>", "agent_type": "<claude_code|codex>"}`

### `Message` (`domain/chat/conversation.py`)

Dataclass; one entry in a conversation.

| Field             | Type                     | Notes                                                       |
| ----------------- | ------------------------ | ----------------------------------------------------------- |
| `id`              | `str`                    | persisted as `messages.mid` (unique); not the row pk        |
| `conversation_id` | `str`                    | FK → `conversations.id`                                     |
| `role`            | `MessageRole`            | `user` \| `assistant` \| `tool`                             |
| `content`         | `str`                    | finalized text (streaming deltas are transient, not stored) |
| `status`          | `MessageStatus`          | `streaming` \| `complete` \| `failed` \| `canceled`         |
| `created_at`      | `datetime`               | UTC                                                         |
| `tool_calls`      | `list[ToolCall]`         | embedded; default `[]`                                      |
| `error`           | `dict[str, Any] \| None` | `{"code", "message"}` for failed turns; else `None`         |

### `ToolCall` (`domain/chat/conversation.py`)

Dataclass embedded in a message. Argument/result are stored as **short
summaries only** — never full payloads — mirroring the gateway invocation-logging
discipline (no secret leakage).

| Field            | Type           | Notes                                                                      |
| ---------------- | -------------- | -------------------------------------------------------------------------- |
| `id`             | `str`          | runtime-assigned id; matches the SSE `tool_call` / `confirmation` event id |
| `tool`           | `str`          | tool name                                                                  |
| `args_summary`   | `str`          | JSON-ish summary, truncated to 200 chars                                   |
| `result_summary` | `str \| None`  | result summary, truncated to 200 chars; `None` until the tool ends         |
| `confirmed`      | `bool \| None` | `None` = confirmation N/A; `True`/`False` = approved/denied                |

### Runtime value objects (`domain/chat/runtime.py`)

Pure, engine-agnostic units. The `AgentRuntime` **port** is a Protocol in the
application layer (`application/chat/ports.py`); these value objects live in the
domain so every layer can name them.

- `TurnMessage(role, content)` — one prior message handed to a runtime as history.
- `ChatTurnRequest(history, user_message, confirm_tools)` — everything a runtime needs to work one turn.
- **Runtime events** (`RuntimeEvent` union), each with a `KIND` class var that doubles as the SSE `type`:

| Event                 | `KIND` / SSE `type` | Payload fields                |
| --------------------- | ------------------- | ----------------------------- |
| `TextDelta`           | `text_delta`        | `text`                        |
| `ToolCallStarted`     | `tool_call`         | `id`, `tool`, `args`          |
| `ToolResultEvent`     | `tool_result`       | `id`, `tool`, `ok`, `summary` |
| `ConfirmationRequest` | `confirmation`      | `id`, `tool`, `args`          |
| `ErrorEvent`          | `error`             | `code`, `message`             |
| `DoneEvent`           | `done`              | (none)                        |

`event_payload(ev)` maps an event to the JSON dict streamed over SSE; the wire
shape is defined once, next to the events.

## SQLite schema additions

Migration `20260601_0006_chat_tables.py` (revision `0006`, down_revision `0005`)
adds two tables. The `builtin_agent` kind reuses the existing `resources` table,
so no table is added for the agent config itself.

> **Migration-rebase note**: this branch was cut from `main@0005`, before specs
> 006/007 (which also branch near there). When 008 is rebased onto a main that
> already carries their migrations, renumber this revision + down_revision to
> chain after the then-head — a routine multi-feature Alembic reconciliation, no
> schema change.

### `conversations`

| Column                | Type             | Constraints                                         |
| --------------------- | ---------------- | --------------------------------------------------- |
| `id`                  | `TEXT`           | primary key (`pk_conversations`)                    |
| `target_ref`          | `TEXT`           | not null; `<kind>:<name>`                           |
| `title`               | `TEXT`           | nullable                                            |
| `status`              | `TEXT`           | not null, default `active` (`active` \| `archived`) |
| `model_snapshot_json` | `TEXT`           | not null, default `{}`; JSON                        |
| `created_at`          | `TIMESTAMP` (tz) | not null                                            |
| `updated_at`          | `TIMESTAMP` (tz) | not null                                            |

Index: `idx_conversations_status_updated` on `(status, updated_at)` — supports
the list-by-status, recency-ordered query.

### `messages`

| Column            | Type             | Constraints                                                                        |
| ----------------- | ---------------- | ---------------------------------------------------------------------------------- |
| `seq`             | `INTEGER`        | primary key (`pk_messages`), autoincrement — orders messages within a conversation |
| `mid`             | `TEXT`           | unique (`uq_messages_mid`); the domain `Message.id`                                |
| `conversation_id` | `TEXT`           | FK → `conversations.id` **ON DELETE CASCADE**                                      |
| `role`            | `TEXT`           | not null (`user` \| `assistant` \| `tool`)                                         |
| `content`         | `TEXT`           | not null, default `""`                                                             |
| `tool_calls_json` | `TEXT`           | not null, default `[]`; JSON array of tool-call dicts                              |
| `status`          | `TEXT`           | not null (`streaming` \| `complete` \| `failed` \| `canceled`)                     |
| `error_json`      | `TEXT`           | nullable; JSON `{"code", "message"}`                                               |
| `created_at`      | `TIMESTAMP` (tz) | not null                                                                           |

Index: `idx_messages_conversation_seq` on `(conversation_id, seq)` — supports
the per-conversation ordered history fetch.

### Reuse of existing tables

- `resources`: new rows with `kind='builtin_agent'`. No schema change.
- `audit_log`: new event types written (see below).

## Audit event types added

Add to `AuditEventType` (`domain/audit.py`):

| Value                   | When emitted                                              |
| ----------------------- | --------------------------------------------------------- |
| `conversation_created`  | A conversation is created (details record the target ref) |
| `conversation_renamed`  | A conversation is renamed (manually or by auto-title)     |
| `conversation_archived` | A conversation is archived                                |
| `conversation_restored` | An archived conversation is restored to active            |
| `conversation_deleted`  | A conversation (and its cascaded messages) is deleted     |

Built-in-agent lifecycle (create / update / enable / disable / delete /
re-seed) reuses the existing kind-agnostic Resource audit events
(`resource_created`, …); the seeding helper records a `resource_created` for
the default agent. Gateway tool calls made by the built-in runtime share the
existing gateway invocation-logging surface (tool name only).

## Relationships

```
Resource (kind=builtin_agent)  ──< targeted by >──  Conversation (target_ref="builtin_agent:<name>")
Resource (kind=agent)          ──< targeted by >──  Conversation (target_ref="agent:<name>")
Conversation 1 ───< has many >─── Message            (ON DELETE CASCADE)
Message      1 ───< embeds   >─── ToolCall           (in tool_calls_json)
```

- A conversation targets exactly one agent resource, chosen at creation.
- The target is not a hard FK (it is a `<kind>:<name>` ref string); a deleted
  target makes the conversation read-only for new turns (`TARGET_AGENT_MISSING`
  on the next `send`) while read paths keep working.

## Application service contract (`application/chat/service.py`)

`ChatService` talks to agents only through the `AgentRuntime` port, so it is
identical for the built-in (LangGraph) and external (subprocess) runtimes. It
holds **one active turn per conversation** in memory to enforce single-flight
(409), route confirmation decisions, and support stop.

| Method                                                   | Purpose                                                                                                                                                                                                                                                              |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `create_conversation(target_ref, actor) -> Conversation` | Parse + validate the target (`NotAChatTarget` if not a chat kind, `ResourceNotFound`→404), record model snapshot, audit.                                                                                                                                             |
| `list_conversations(status, limit, offset) -> list`      | Paginated list, optionally filtered by status.                                                                                                                                                                                                                       |
| `get_conversation(id) -> Conversation`                   | `ConversationNotFound` (404) if absent.                                                                                                                                                                                                                              |
| `get_messages(id) -> list[Message]`                      | Ordered message history.                                                                                                                                                                                                                                             |
| `rename(id, title, actor) -> Conversation`               | Set title; audit `conversation_renamed`.                                                                                                                                                                                                                             |
| `archive / restore(id, actor) -> Conversation`           | Toggle status; audit.                                                                                                                                                                                                                                                |
| `delete(id, actor) -> None`                              | Delete conversation (messages cascade); audit `conversation_deleted`.                                                                                                                                                                                                |
| `send(id, text, actor) -> AsyncIterator[RuntimeEvent]`   | Validate text (`MessageRejected`), reject if busy (`ConversationBusy`→409), build the runtime **before** persisting (so a missing key raises `LlmNotConfigured`→503 with nothing half-written), persist user + streaming-assistant messages, return the turn stream. |
| `resolve_confirmation(id, request_id, approve) -> None`  | Route an approve/deny decision to the active runtime.                                                                                                                                                                                                                |
| `stop(id) -> None`                                       | Mark stopped and ask the runtime to stop; no-op if no active turn.                                                                                                                                                                                                   |

On turn completion `_finalize` persists the finalized assistant content,
tool-call metadata, status (`complete`/`failed`/`canceled`), and any structured
error; then, for the first exchange on a placeholder-titled conversation, applies
the auto-title (generator or truncated-first-message fallback). Persistence
failures during finalize are suppressed so a streaming error never corrupts the
store.

## Ports (`application/chat/ports.py`)

- `ConversationRepo`, `MessageRepo` — persistence (→ `infrastructure/chat/persistence.py`).
- `AgentRuntime` — one turn's execution; `stream`, `resolve_confirmation`, `stop`.
- `RuntimeFactory` — `build(target, config) -> AgentRuntime`; `target.kind`
  selects the implementation (`builtin_agent` → LangGraph; `agent` → subprocess).
- `TitleGenerator` — optional; `generate(user, assistant) -> str | None`.

## Infrastructure adapters (`infrastructure/chat/`)

- `persistence.py` — SQLAlchemy `ConversationRepo` / `MessageRepo`.
- `runtime_factory.py` — `CompositeRuntimeFactory`; lazily imports the heavy
  runtime modules inside `build` so wiring at startup never requires LangChain.
- `builtin_runtime.py` — `BuiltinRuntime`; the **only** module that imports
  LangChain/LangGraph (importlinter Contract 7), and even there the imports are
  lazy (inside `stream`). Resolves the model with `init_chat_model`, loads
  gateway tools via `langchain-mcp-adapters` from Coffer's own `/mcp` endpoint,
  wraps confirm-gated tools to pause for a human decision, runs a
  `create_react_agent` loop, and maps `astream_events` to runtime events.
- `external_runtime.py` — `ExternalAgentRuntime`; spawns `claude` / `codex` as a
  local subprocess in streaming mode (binary from `COFFER_CHAT_BIN_<TYPE>` or
  PATH), maps stdout lines to events, runs under the agent's `config_dir`, and
  always reaps the child (no orphans on end / error / stop / shutdown).

## Constraints summary

- All HTTP loopback-only; the built-in runtime reaches the gateway over
  `127.0.0.1` with the daemon token.
- LangGraph / LangChain confined to `infrastructure/chat/` (importlinter
  Contract 7); domain + application reach the engine only through the
  `AgentRuntime` port.
- User message text: 1–32768 chars, enforced at the API boundary.
- One active streaming turn per conversation (single-flight, 409 on conflict).
- Confirmation is wired for the built-in runtime; external agents in v1 run
  under their own permission policy (`resolve_confirmation` is a no-op there).
