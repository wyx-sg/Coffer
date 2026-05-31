# Implementation Plan: 008 — Built-in Agent & Chat

**Branch**: `feature/008-builtin-agent-chat` (builds on spec 001 Resource
framework + spec 004 agent registry)
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Give Coffer its own agent and a chat surface. Add an **additive**
`builtin_agent` Resource kind — a real LLM loop implemented with LangGraph so
any mainstream provider works — wired to Coffer's own MCP gateway so it can use
every MCP server / skill / knowledge base / memory the vault manages. Add a
chat surface where a conversation targets either the built-in agent or a
Coffer-managed external agent (`claude_code` / `codex`) driven as a local
headless subprocess. Conversations and messages persist locally; streaming is
live over SSE; sensitive tool use can pause for human-in-the-loop confirmation;
conversations get an auto-generated title. Ships with REST routes, CLI
subcommands, and a desktop Chat page. Channels (spec 009) bridge external
messaging into this chat later.

## Technical Context

| Dimension                    | Value                                                                                                                                                                        |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**       | Python 3.12+, TypeScript 5.x                                                                                                                                                 |
| **New runtime dependencies** | `langgraph`, `langchain`, `langchain-core`, `langchain-anthropic`, `langchain-openai`, `langchain-ollama`, `langchain-mcp-adapters` — all confined to `infrastructure/chat/` |
| **Storage**                  | SQLite (`conversations`, `messages`); built-in agent config reuses `resources`.                                                                                              |
| **Testing**                  | 4-tier; acceptance markers tie to scenarios. The LangGraph adapter's live-model paths are deferred to the e2e tier; the port contract is validated with a fake runtime.      |
| **Target Platforms**         | macOS arm64+x64, Windows x64, Linux x64+arm64                                                                                                                                |
| **Performance Goals**        | First streamed reply within 10 s of opening Chat (SC-001). Stop halts output within 1 s (SC-004).                                                                            |
| **Constraints**              | Local-first (user data stays local; calling cloud LLM providers is allowed); engine isolation enforced by importlinter; loopback-only API; layered architecture preserved.   |
| **Scale**                    | Single user; one active streaming turn per conversation.                                                                                                                     |

## Constitution Check

| Clause                     | Compliance | Notes                                                                                                                            |
| -------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------- |
| I. Local-First             | ✅         | Conversations + messages stored locally in SQLite. Talking to cloud LLM providers is explicitly allowed (user data stays local). |
| II. Spec-as-Truth          | ✅         | Spec committed before code; companion docs match the implemented contract.                                                       |
| III. Open-Source-Readiness | ✅         | LangGraph / LangChain are OSS (MIT).                                                                                             |
| Languages                  | ✅         | Python + TypeScript.                                                                                                             |
| Architecture: layered      | ✅         | Engine behind the `AgentRuntime` port; LangChain/LangGraph confined to `infrastructure/chat/` (importlinter Contract 7).         |
| Persistence                | ✅         | Control plane in SQLite; no bulk content tables.                                                                                 |
| Credentials                | ✅         | Provider keys resolved through the keychain via `credential_ref`; never stored in config or DB.                                  |
| Network defaults           | ✅         | Loopback-only HTTP API; the built-in runtime reaches the gateway over `127.0.0.1` with the daemon token.                         |

## Project Structure

### Documentation

```
specs/008-builtin-agent-chat/
  spec.md
  plan.md              (this file)
  data-model.md
  research.md
  contracts/api.openapi.yaml
  quickstart.md
  tasks.md
```

### Backend modules

```
backend/coffer/domain/builtin_agent/
  __init__.py
  config.py            # BuiltinAgentConfig (Pydantic; pure, no engine import)

backend/coffer/domain/chat/
  __init__.py
  conversation.py      # Conversation / Message / ToolCall + status enums
  runtime.py           # RuntimeEvent union + ChatTurnRequest + event_payload

backend/coffer/application/builtin_agent/
  __init__.py
  kind.py              # make_builtin_agent_kind + ensure_default_builtin_agent + last-agent guard

backend/coffer/application/chat/
  __init__.py
  ports.py             # ConversationRepo / MessageRepo / AgentRuntime / RuntimeFactory / TitleGenerator (Protocols)
  service.py           # ChatService — lifecycle + streaming turn orchestration

backend/coffer/infrastructure/chat/
  __init__.py
  persistence.py       # SQLAlchemy ConversationRepo / MessageRepo
  runtime_factory.py   # CompositeRuntimeFactory (lazy engine import)
  builtin_runtime.py   # BuiltinRuntime (LangGraph) — the ONLY LangChain importer
  external_runtime.py  # ExternalAgentRuntime (subprocess: claude / codex)

backend/coffer/infrastructure/persistence/migrations/versions/
  20260601_0006_chat_tables.py   # conversations + messages (revision 0006, down 0005)

backend/coffer/surfaces/http/chat/
  __init__.py
  routes.py            # /api/v1/conversations/* (SSE on send)
  schemas.py           # request/response Pydantic models + mappers
backend/coffer/surfaces/http/chat_composition.py   # default runtime factory (gateway endpoint + keyring)
backend/coffer/surfaces/cli/chat_cmd.py            # coffer chat ...
```

### Frontend modules

```
frontend/src/pages/ChatPage.tsx
frontend/src/components/chat/         # conversation list, message stream, tool-call rows, confirmation cards, target picker, Stop
frontend/src/lib/api/chat.ts          # REST client + SSE reader
frontend/src/i18n/locales/{en,zh}.json  # chat strings appended
```

## Architecture

### Layers

- **Domain** (`domain/builtin_agent`, `domain/chat`): pure value objects —
  `BuiltinAgentConfig`, `Conversation` / `Message` / `ToolCall`, the
  `RuntimeEvent` union, and `ChatTurnRequest`. No engine, no I/O.
- **Application** (`application/builtin_agent`, `application/chat`): the
  `builtin_agent` Kind + seeding + last-agent guard, and `ChatService` plus the
  ports it depends on. Depends only on Protocols it defines.
- **Infrastructure** (`infrastructure/chat`): the persistence repos and the two
  runtimes. The LangGraph engine lives here and nowhere else.
- **Surfaces** (`surfaces/http/chat`, `surfaces/cli/chat_cmd.py`): REST (SSE on
  send) and CLI. Composition wires the default runtime factory.

### `AgentRuntime` port + two runtimes

`ChatService` talks to agents only through the `AgentRuntime` port (`stream`,
`resolve_confirmation`, `stop`), so its turn orchestration is identical for both
runtimes. `RuntimeFactory.build(target, config)` picks the implementation by
`target.kind`:

- `builtin_agent` → `BuiltinRuntime` (LangGraph). Resolves the model with
  `init_chat_model` (provider-agnostic), loads gateway tools via
  `langchain-mcp-adapters` from Coffer's own `/mcp` endpoint when `use_gateway`,
  wraps confirm-gated tools to pause for a human decision, runs a
  `create_react_agent` loop, and maps `astream_events` to runtime events.
- `agent` → `ExternalAgentRuntime` (subprocess). Spawns `claude` / `codex` in
  headless streaming mode under the agent's `config_dir`, maps stdout to events,
  and always reaps the child.

### Engine isolation

LangChain/LangGraph are confined to `infrastructure/chat/builtin_runtime.py` —
even the imports there are lazy (inside `stream`) so wiring the factory at
startup never requires the engine to be installed. importlinter **Contract 7**
(`forbidden`, source `coffer.domain` + `coffer.application`, forbidden the
`langgraph` / `langchain*` packages) enforces this and backs SC-006.

### Streaming + turn control

`send` validates the text and target, builds the runtime **before** persisting
anything (so a missing provider key raises `LlmNotConfigured` → 503 with nothing
half-written), persists the user message and a streaming-assistant message, then
returns the turn stream. The HTTP surface emits each event as
`data: {json}\n\n` over `text/event-stream`; pre-stream validation
(404/409/422/503) is awaited before the streaming body is committed so it maps
to the normal error envelope. Single-flight is enforced by an in-memory
active-turn map (409 on conflict). Stop sets a flag and asks the runtime to
stop; the assistant message is finalized as `canceled` with partial content.

### Confirmation

For the built-in runtime Coffer controls tool execution: a tool whose name
matches `confirm_tools` is wrapped so it emits a `ConfirmationRequest`, awaits a
decision future, and either runs (and returns its result) or returns a "declined"
string to the agent. `ChatService.resolve_confirmation` routes the decision to
the active runtime. External agents in v1 run under their own permission policy
(`resolve_confirmation` is a no-op there; `confirm_tools` is empty for them).

### Error codes → HTTP status

| Code                               | Status | Raised when                                           |
| ---------------------------------- | ------ | ----------------------------------------------------- |
| `LLM_NOT_CONFIGURED`               | 503    | built-in target's provider has no usable key/endpoint |
| `CONVERSATION_NOT_FOUND`           | 404    | unknown conversation id                               |
| `CONVERSATION_BUSY`                | 409    | second send while a turn is streaming                 |
| `MESSAGE_REJECTED`                 | 422    | empty / whitespace / over-length message text         |
| `TARGET_AGENT_MISSING`             | 404    | conversation's target agent resource is gone          |
| `NOT_A_CHAT_TARGET`                | 400    | create against a non-chat resource kind               |
| `CANNOT_DELETE_LAST_BUILTIN_AGENT` | 409    | delete the only remaining `builtin_agent`             |

## Phasing

### Phase 0 — Research (see [research.md](./research.md))

- Engine: LangGraph behind a port (ADR-013). Rejected: raw provider SDKs,
  LlamaIndex agents.
- Provider-agnostic model resolution via `init_chat_model` on a
  provider-qualified `model` string.
- External-agent headless invocation per agent type (`claude -p … --output-format stream-json`, `codex exec --json`).
- Confirmation: Coffer-controlled tool gating for the built-in runtime;
  agent-native permission policy for external runtimes.

### Phase 1 — Data model + contracts

- Write data-model.md and contracts/api.openapi.yaml.
- Alembic migration `20260601_0006_chat_tables.py` (revision `0006`,
  down_revision `0005`) creating `conversations` + `messages`.

> **Migration-rebase note**: this branch was cut from `main@0005`, before specs
> 006/007 (which also branch near there). When 008 is rebased onto a main that
> already carries their migrations, renumber this revision + down_revision to
> chain after the then-head. This is a routine multi-feature Alembic
> reconciliation — no schema change, just re-pointing the revision chain.

### Phase 2 — Backend implementation

1. Domain: `BuiltinAgentConfig`, `Conversation`/`Message`/`ToolCall`, the
   `RuntimeEvent` union + `event_payload`.
2. Application: `make_builtin_agent_kind`, `ensure_default_builtin_agent`,
   last-agent delete guard; `ChatService` + ports.
3. Infrastructure: persistence repos; `CompositeRuntimeFactory`;
   `BuiltinRuntime` (LangGraph); `ExternalAgentRuntime` (subprocess).
4. Surfaces: `chat/routes.py` (+ SSE), `chat/schemas.py`, `chat_cmd.py`;
   `chat_composition.py` for the default factory; register the `builtin_agent`
   kind and seed the default agent at startup.
5. importlinter Contract 7; mypy override for the one untyped-engine module.

### Phase 3 — Tests

- Unit: `BuiltinAgentConfig` validation (blank model, temperature/max_tokens
  bounds, `requires_confirmation` globbing); `event_payload` shapes.
- Integration with a **fake runtime** that yields scripted events: stream a
  reply; tool-call → confirmation → approve/deny; stop mid-stream; runtime error
  → message `failed`; concurrent send → 409; missing provider key → 503; auto-title
  on first exchange; persistence round-trip across a simulated restart.
- External runtime: stub binary via `COFFER_CHAT_BIN_<TYPE>`; missing binary →
  structured error; no orphan child on stop.
- Engine isolation: importlinter contract test (SC-006).
- Acceptance markers `@pytest.mark.acceptance(spec="008-builtin-agent-chat", scenario="…")` for each non-deferred scenario.

### Phase 4 — Frontend

- React `ChatPage`: conversation list, target picker (built-in + chat-capable
  managed agents), streaming message view with tool-call rows + confirmation
  cards, input box, Stop button. SSE reader maps event `type`s to UI.
- i18n English + Simplified Chinese.

## Risks / unknowns

- **LangChain/LangGraph API churn** absorbed in `infrastructure/chat/` only; the
  port shields the rest of the codebase.
- **External agent CLI output formats** vary across versions; the line mapper is
  deliberately tolerant (JSON `text` / Claude `stream-json` assistant blocks /
  plain-text fallback). Confirmation hooks for external agents are deferred.
- **Provider credential discovery**: cloud providers need a keychain ref or an
  environment key; the runtime fails fast (503) rather than hanging.

## Open items deferred to future specs

- Channels: bridging external messaging platforms into this chat (spec 009).
- Confirmation enforcement for external-agent runtimes where the CLI exposes a
  permission-prompt hook.
- `cursor` and other agent types without a documented headless streaming mode as
  chat targets.
- Token-level cost / usage accounting per conversation.
