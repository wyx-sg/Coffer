# Tasks — 008 Built-in Agent & Chat

Work breakdown for the built-in agent + chat surface. Grouped by phase; `[P]`
marks tasks that can proceed in parallel within their phase. Each acceptance
task references the scenario name it must mark
(`@pytest.mark.acceptance(spec="008-builtin-agent-chat", scenario="…")`).

## Phase 1 — Data model + contracts

- [ ] T101 Author `data-model.md` (+ `.zh.md`): `BuiltinAgentConfig`,
      `Conversation` / `Message` / `ToolCall`, runtime events, the two SQLite
      tables, relationships, audit events.
- [ ] T102 Author `contracts/api.openapi.yaml`: the `/api/v1/conversations`
      endpoints + schemas + error responses.
- [ ] T103 Add Alembic migration `20260601_0006_chat_tables.py` (revision
      `0006`, down_revision `0005`) creating `conversations` + `messages` with
      their indexes and the `messages → conversations` CASCADE FK. Record the
      migration-rebase note (cut from `main@0005`).

## Phase 2 — Domain

- [ ] T201 [P] `domain/builtin_agent/config.py` — `BuiltinAgentConfig`
      (`extra="forbid"`, model not blank, temperature `0..2`, max_tokens `>0`,
      `requires_confirmation` glob helper).
- [ ] T202 [P] `domain/chat/conversation.py` — `Conversation`, `Message`,
      `ToolCall`, and the `ConversationStatus` / `MessageRole` / `MessageStatus`
      enums.
- [ ] T203 [P] `domain/chat/runtime.py` — `TurnMessage`, `ChatTurnRequest`, the
      `RuntimeEvent` union, and `event_payload`.
- [ ] T204 [P] `domain/errors.py` — add `LlmNotConfigured`,
      `ConversationNotFound`, `ConversationBusy`, `MessageRejected`,
      `TargetAgentMissing`, `NotAChatTarget`, `LastBuiltinAgent` with their codes.
- [ ] T205 [P] `domain/audit.py` — add the five `conversation_*` audit event
      types.

## Phase 3 — Application

- [ ] T301 `application/chat/ports.py` — `ConversationRepo`, `MessageRepo`,
      `AgentRuntime`, `RuntimeFactory`, `TitleGenerator` Protocols.
- [ ] T302 `application/chat/service.py` — `ChatService`: lifecycle
      (create/list/get/rename/archive/restore/delete), single-flight active-turn
      map, `send` (validate → build runtime before persist → stream),
      `_run_turn` / `_finalize`, confirmation routing, stop, auto-title.
- [ ] T303 `application/builtin_agent/kind.py` — `make_builtin_agent_kind`,
      `ensure_default_builtin_agent` (seed `coffer` with default model + system
      prompt + confirm policy), `make_refuse_delete_last_hook`.

## Phase 4 — Infrastructure

- [ ] T401 [P] `infrastructure/chat/persistence.py` — SQLAlchemy
      `ConversationRepo` / `MessageRepo` (JSON round-trip for
      `model_snapshot` / `tool_calls` / `error`).
- [ ] T402 `infrastructure/chat/runtime_factory.py` — `CompositeRuntimeFactory`
      (lazy engine import; selects runtime by `target.kind`).
- [ ] T403 `infrastructure/chat/builtin_runtime.py` — `BuiltinRuntime`
      (LangGraph): `init_chat_model` model resolution, keychain/env credential
      resolution with fail-fast `LlmNotConfigured`, gateway tools via
      `langchain-mcp-adapters`, confirm-gated tool wrapper, `create_react_agent`
      loop, `astream_events` → runtime events, stop.
- [ ] T404 [P] `infrastructure/chat/external_runtime.py` — `ExternalAgentRuntime`
      (subprocess): binary resolution (`COFFER_CHAT_BIN_<TYPE>` / PATH),
      per-type command + config-dir env, tolerant stdout line mapper, child
      reaping, stop.
- [ ] T405 importlinter Contract 7 (`langgraph` / `langchain*` forbidden in
      `coffer.domain` + `coffer.application`) + mypy override for
      `builtin_runtime`.

## Phase 5 — Surfaces

- [ ] T501 `surfaces/http/chat/schemas.py` — request/response models + mappers.
- [ ] T502 `surfaces/http/chat/routes.py` — `/api/v1/conversations` router with
      SSE on `POST /{id}/messages` and pre-stream validation.
- [ ] T503 `surfaces/http/errors.py` — map the seven new error codes to status.
- [ ] T504 `surfaces/http/chat_composition.py` + app wiring — register the
      `builtin_agent` kind (with the last-agent guard), seed the default agent at
      startup, build the default runtime factory (gateway endpoint + keyring),
      mount the chat router.
- [ ] T505 `surfaces/cli/chat_cmd.py` — `coffer chat new|list|show|send|confirm|stop|rename|archive|restore|rm`; `--json` on `list` / `show`; streaming `send` printer.

## Phase 6 — Dependencies

- [ ] T601 Add `langgraph`, `langchain`, `langchain-core`,
      `langchain-anthropic`, `langchain-openai`, `langchain-ollama`,
      `langchain-mcp-adapters` to `pyproject.toml`; refresh the lockfile.

## Phase 7 — Tests (acceptance markers in parentheses)

- [ ] T701 [P] Unit: `BuiltinAgentConfig` validation + `requires_confirmation`;
      `event_payload` shapes.
- [ ] T702 Integration with a fake runtime: seed default agent
      (`a built-in agent is seeded on first startup`).
- [ ] T703 Stream a reply (`chat with the built-in agent streams a reply`) and
      gateway tool call (`the built-in agent can call Coffer gateway tools`).
- [ ] T704 Persistence round-trip across simulated restart
      (`conversation and messages persist across daemon restarts`).
- [ ] T705 External runtime via stub binary
      (`chat with an external agent streams its subprocess output`) and missing
      binary (`external agent binary missing is surfaced as a clear error`); no
      orphan child on stop.
- [ ] T706 Conversation lifecycle
      (`create / list / rename / archive / restore / delete a conversation`).
- [ ] T707 Confirmation: pause (`sensitive tool use pauses for confirmation`),
      approve (`approving a confirmation runs the tool and resumes the turn`),
      deny (`denying a confirmation skips the tool and informs the agent`).
- [ ] T708 Auto-title
      (`a new conversation gets an auto-generated title after the first exchange`).
- [ ] T709 Stop (`a streaming turn can be stopped`); no-LLM
      (`send returns 503 when no LLM provider is configured`); concurrent send
      (`concurrent send on a streaming conversation is rejected`).
- [ ] T710 Engine isolation importlinter test
      (`built-in agent runtime is engine-isolated`, SC-006).
- [ ] T711 Contract: OpenAPI snapshot; CLI `--json` stability.

## Phase 8 — Frontend

- [ ] T801 `ChatPage` + components: conversation list, target picker, streaming
      message view with tool-call rows + confirmation cards, input box, Stop.
- [ ] T802 `lib/api/chat.ts` REST client + SSE reader mapping event `type`s.
- [ ] T803 i18n English + Simplified Chinese strings.

## Phase 9 — Verification

- [ ] T901 `make verify` green locally (acceptance audit ties every non-deferred
      scenario to a marker); confirm CI green (SC-008).
