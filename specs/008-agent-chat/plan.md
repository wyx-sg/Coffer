# Implementation Plan: 008 — Agent Chat

> 中文版: [plan.zh.md](./plan.zh.md)

**Branch**: `feature/agent-chat`
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Deliver the chat **platform** and one agent on it. The platform is a chat
surface, persisted multi-conversation history, a streamed turn protocol, a
human-approval channel, and user interruption — all expressed against an
**agent-provider registry** so a second agent is a registry entry, not a
re-architecture. The one agent shipped is the built-in "Coffer Assistant": an
in-process LangGraph ReAct loop on a user-configured LLM, using every tool
Coffer's MCP gateway aggregates.

This revision restructures an earlier draft of 008 that hard-wired the built-in
agent into the chat surface. The seam is made real: the orchestrator,
persistence, and wire contract now know only the registry; the built-in agent
is re-expressed as one `AgentProvider` + `AgentAdapter` behind it, with its
external behaviour unchanged.

## Technical Context

| Dimension | Value |
|---|---|
| **Language / Version** | Python 3.12+, TypeScript 5.x |
| **Primary Dependencies** | `langgraph`, `langchain`, `langchain-anthropic`, `langchain-openai`, `langchain-ollama` — confined to `coffer.infrastructure.chat` (importlinter Contract 9). No new dependency added by this revision. |
| **Storage** | SQLite `conversations` / `chat_messages` / `chat_models` (Alembic `0005`). **No migration** — the platform refactor adds no columns. |
| **Testing** | 4-tier model with acceptance markers. The LLM is faked via `FakeChatModel`; the platform seam is exercised with a `FakeAgentAdapter` / `FakeAgentProvider`; the approval channel is proven with a fake provider whose adapter requests approval. |
| **Constraints** | LangGraph/LangChain confined to `infrastructure/chat`. Built-in agent external behaviour unchanged. No credential material in DB or logs. File-size + importlinter contracts hold. |

## Constitution Check

- **Local-first** — conversations, messages, and approval decisions never leave
  the device; LLM providers are inference providers only.
- **Spec-as-Truth** — `spec.md` is revised first; `contracts/api.openapi.yaml`
  is the wire contract gated by `make verify-contract`.
- **Layered architecture** — `domain/chat` stays pure (it gains only the
  `ApprovalRequest` frozen dataclass). `application/chat` defines the platform
  seam (`AgentAdapter`, `AgentProvider`, `ApprovalGate` ports; the registry and
  approval channel concretes). `infrastructure/chat` holds the LangGraph adapter
  and the `BuiltinAgentProvider`. Import direction is unchanged; Contract 9 is
  unchanged.
- **Credentials** — model API keys remain credential refs resolved at runtime.

## The platform seam (frozen contract)

See [data-model.md](./data-model.md) for the verbatim interfaces. In short:

- **`AgentAdapter.run_turn(*, history, approvals)`** — self-contained. The
  adapter carries its own model, tools, and config; the orchestrator injects
  only history and the approval channel.
- **`AgentProvider`** — `agent_key`, `init_conversation`, `build_adapter`,
  `on_conversation_deleted`, `availability`. The unit of extension.
- **`AgentProviderRegistry`** — the only thing the chat surface knows. A second
  agent = one `registry.register(...)` call in the composition root.
- **`ApprovalGate` / `ApprovalDecision` / `ApprovalRequest`** — the
  human-approval channel: a turn emits `ApprovalRequest`, `await`s
  `approvals.wait(request_id)`, and resumes when a decision is posted.

## How the refactor preserves built-in behaviour

| Concern | Before | After |
|---|---|---|
| Model resolution | `TurnOrchestrator.start_turn` | `BuiltinAgentProvider.build_adapter` (raises `NoModelConfigured` there) |
| System prompt + skill catalogue | built in `TurnOrchestrator._run_turn` | built in `BuiltinAgentProvider.build_adapter` |
| History trimming + truncation notice | `TurnOrchestrator._run_turn` | inside `LangGraphBuiltinAgent.run_turn` (a built-in-agent concern) |
| `run_turn` inputs | `history, tool_gateway, model, system_prompt` | `history, approvals` (rest baked into the adapter at build time) |
| Tool loop, recursion cap, event mapping | `LangGraphBuiltinAgent` / `_event_mapping` | unchanged |

The existing 008 acceptance scenarios + e2e are the regression proof that the
built-in agent's observable behaviour did not change.

## Project Structure — backend

```text
backend/coffer/
├── domain/chat/events.py            # MODIFY  + ApprovalRequest, extend AgentEvent
├── domain/errors.py                 # MODIFY  + UnknownAgent, AgentConfigRejected, ApprovalNotFound
├── application/chat/
│   ├── ports.py                     # MODIFY  ApprovalDecision/Gate, AgentProvider, new AgentAdapter
│   ├── approvals.py                 # CREATE  ApprovalChannel (concrete ApprovalGate)
│   ├── registry.py                  # CREATE  AgentProviderRegistry
│   ├── turn_orchestrator.py         # MODIFY  _ActiveTurn, registry-driven, interrupt_turn, submit_approval
│   └── service.py                   # MODIFY  create→init_conversation, delete→on_conversation_deleted
├── infrastructure/chat/
│   ├── builtin_provider.py          # CREATE  BuiltinAgentProvider (the one registered provider)
│   └── langgraph_agent.py           # MODIFY  run_turn(history, approvals); self-contained adapter
└── surfaces/http/
    ├── chat/schemas.py              # MODIFY  ConversationCreate, + AgentOut/AgentListOut/ApprovalSubmit
    ├── chat/conversation_routes.py  # MODIFY  POST body; + GET /chat/agents
    ├── chat/turn_routes.py          # MODIFY  + POST .../approvals, + POST .../interrupt
    ├── dependencies.py              # MODIFY  + set/get_agent_registry
    ├── wiring.py                    # MODIFY  wire_chat builds registry + BuiltinAgentProvider
    └── errors.py                    # MODIFY  map new error codes
```

Unchanged backend files: `domain/chat/{conversation,message,model}.py`,
`application/chat/{system_prompt,history,model_service}.py`,
`infrastructure/chat/{_event_mapping,langchain_models,gateway_tool_provider,
persistence,model_persistence}.py`, the `0005` migration, `surfaces/cli/*`
(the built-in agent is the CLI default; the CLI ignores unknown SSE events).

## Project Structure — frontend

```text
frontend/src/
├── lib/api/chat.ts                  # MODIFY  ConversationCreate; + AgentInfo, listAgents, submitApproval, interruptTurn
├── lib/chat/streamClient.ts         # MODIFY  + ApprovalRequestEvent in the AgentEvent union
├── lib/hooks/useChatTurn.ts         # MODIFY  handle approval_request; expose interrupt() + pendingApproval
├── lib/hooks/useChatAgents.ts       # CREATE  GET /chat/agents query
├── lib/hooks/useConversations.ts    # MODIFY  create body shape
├── components/chat/ApprovalCard.tsx        # CREATE  generic allow/deny card
├── components/chat/NewConversationDialog.tsx # CREATE  agent picker + per-agent config area
├── components/chat/Composer.tsx     # MODIFY  + Stop button while streaming
├── components/chat/MessageThread.tsx # MODIFY  render ApprovalCard; wire interrupt
├── pages/ChatPage.tsx               # MODIFY  new-conversation dialog; interrupt
└── i18n/locales/{en,zh}.json        # MODIFY  agent picker / approval / interrupt keys
```

The `NewConversationDialog` renders the per-agent configuration area by
`agent_key` (built-in → model select). Its structure — a switch over agent
type — is what lets a future agent's config area drop in without reworking the
dialog.

## Tests

- **Unit** — `test_agent_registry.py`, `test_approval_channel.py` (new);
  `test_turn_orchestrator_with_fake_adapter.py` reworked for the
  registry-driven API, interruption, and the approval relay — driven with a
  fake approval-requesting adapter, which is the spec's "fake test adapter"
  acceptance proof for the approval scenarios; `test_chat_service_with_fakes.py`
  reworked for `agent_key` + `init_conversation`. Shared fakes in `conftest.py`
  gain `FakeAgentProvider` and the `make_chat_services` wiring helper.
- **Integration** — `test_builtin_provider.py` (new — `init_conversation`,
  `build_adapter`, `NoModelConfigured`); `test_langgraph_agent_real`,
  `test_http_routes` (incl. the agents / approvals / interrupt route guards),
  `test_composition_root_chat` (the agent-registry scenarios through real
  wiring), and `test_delete_cancels_turn` reworked for the new signatures.
- **Contract** — `test_chat_openapi.py` extended with the three new endpoints.
- **Frontend** — `ApprovalCard.test.tsx`, `NewConversationDialog.test.tsx`
  (new); the existing chat component/hook tests carried forward.
- **e2e** — `chat.spec.ts` reworked for the new-conversation dialog + agent
  picker.

Every acceptance scenario in `spec.md` carries a covering `acceptance(...)`
marker; `make verify-acceptance` reports zero uncovered scenarios.

## Importlinter contracts

No contract changes. The new `application/chat` modules (`registry`,
`approvals`) and the new `infrastructure/chat/builtin_provider` sit inside
existing source modules; `BuiltinAgentProvider` is the composition-root-built
adapter exactly as `LangGraphBuiltinAgent` already is under Contract 9.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| The refactor silently changes built-in behaviour | The unchanged 008 acceptance scenarios + e2e are the regression gate; `make verify` must stay green. |
| `start_turn` race on the one-in-flight check | `_ActiveTurn` is registered in `_ACTIVE_TURNS` synchronously, immediately after the `TurnInProgress` guard, before any `await`. |
| An interrupted turn double-persists or hangs the SSE | The turn task owns persistence; the `finally` always enqueues the end-of-stream sentinel; interrupt persists exactly once on the `CancelledError` path. |
| `build_adapter` I/O (skill fetch, model build) surfaces late | `build_adapter` runs in `start_turn` before the user message is persisted and before the task spawns, so `NoModelConfigured` and provider errors return as a pre-stream JSON error. |
| Approval wait leaks if the turn ends without a decision | The approval future is bound to the turn task; interrupt/cancel raises `CancelledError` in `wait()`; the channel is discarded with the `_ActiveTurn`. |

## Out of scope (deferred)

User-created or user-edited agents; a GUI for managing the registry; remote
channels; per-agent capability scoping beyond gateway gating + the approval
channel; conversation summarisation, search, export. See `spec.md` Assumptions.
