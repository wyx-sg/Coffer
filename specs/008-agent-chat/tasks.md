# Tasks — 008 Agent Chat

Execution order. Each numbered group is one commit (Conventional Commits, TDD:
failing test → implementation → green). `make verify` is green before the work
is reported. Detail lives in `plan.md`, `data-model.md`, `research.md`, and
`contracts/api.openapi.yaml`.

## C1 — Spec docs

- [x] T-001 Revise `spec.md` to the agent-agnostic chat platform
- [x] T-002 Revise `plan.md`, `research.md`, `data-model.md`, `tasks.md`
- [x] T-003 Revise `contracts/api.openapi.yaml` (GET /agents, POST /approvals, POST /interrupt, ConversationCreate)
- [x] T-004 Commit `docs(agent-chat): revise spec 008 to an agent-agnostic chat platform`

## C2 — Domain

- [x] T-010 `domain/chat/events.py` — add `ApprovalRequest`, extend the `AgentEvent` union
- [x] T-011 `domain/errors.py` — add `UnknownAgent`, `AgentConfigRejected`, `ApprovalNotFound`
- [x] T-012 Commit `feat(agent-chat): add approval event + platform domain errors`

## C3 — Application platform seam

- [x] T-020 `application/chat/ports.py` — `ApprovalDecision`, `ApprovalGate`, `AgentProvider`; new `AgentAdapter.run_turn(*, history, approvals)`
- [x] T-021 `application/chat/approvals.py` — `ApprovalChannel` + unit test
- [x] T-022 `application/chat/registry.py` — `AgentProviderRegistry` + unit test
- [x] T-023 `application/chat/service.py` — `create_conversation(agent_key, agent_config)` → `init_conversation`; `delete_conversation` → `on_conversation_deleted`
- [x] T-024 `application/chat/turn_orchestrator.py` — `_ActiveTurn`, registry-driven `start_turn`, `interrupt_turn`, `submit_approval`, approval-event relay
- [x] T-025 Update `tests/unit/chat/conftest.py` fakes + `test_turn_orchestrator_with_fake_adapter.py`, `test_chat_service_with_fakes.py`
- [x] T-026 Commit `feat(agent-chat): agent-provider registry, approval channel, interrupt`

## C4 — Built-in agent as a provider

- [x] T-030 `infrastructure/chat/langgraph_agent.py` — `run_turn(*, history, approvals)`; self-contained adapter
- [x] T-031 `infrastructure/chat/builtin_provider.py` — `BuiltinAgentProvider`
- [x] T-032 Update `test_langgraph_agent_real.py` + add `test_builtin_provider.py`
- [x] T-033 Commit `feat(agent-chat): re-express the built-in agent as an agent provider`

## C5 — HTTP surface

- [x] T-040 `surfaces/http/chat/schemas.py` — `ConversationCreate` (agent_key/agent_config), `ChatAgentOut`/`ChatAgentListOut`, `ApprovalSubmit`
- [x] T-041 `surfaces/http/chat/conversation_routes.py` — POST body; `GET /chat/agents`
- [x] T-042 `surfaces/http/chat/turn_routes.py` — `POST .../approvals`, `POST .../interrupt`
- [x] T-043 `surfaces/http/{dependencies,wiring,errors}.py` — registry wiring + new error-code mapping
- [x] T-044 Update `tests/integration/chat/*` + `tests/contract/test_chat_openapi.py`. Approval + interrupt are proven by orchestrator-level acceptance tests with a fake approval-requesting adapter (the spec's "fake test adapter"); the HTTP routes get 404/409/204 route-guard tests
- [x] T-045 Commit `feat(agent-chat): chat platform REST surface — agents, approvals, interrupt`

## C6 — Frontend

- [x] T-050 `lib/api/chat.ts`, `lib/chat/streamClient.ts` — agent list, approvals, interrupt, `approval_request` event
- [x] T-051 `lib/hooks/{useChatAgents,useConversations,useChatTurn}.ts`
- [x] T-052 `components/chat/{NewConversationDialog,ApprovalCard}.tsx`; `Composer`, `MessageThread`, `ChatPage` updates
- [x] T-053 i18n keys (`en.json`, `zh.json`); `ApprovalCard` + `NewConversationDialog` component tests
- [x] T-054 Commit `feat(agent-chat): chat platform UI — agent picker, approval card, stop`

## C7 — End-to-end + verification

- [x] T-060 Update `e2e/web/specs/chat.spec.ts` (new-conversation dialog, agent picker)
- [x] T-061 `make verify` green; `make verify-acceptance` zero uncovered; `make verify-e2e` green (25 tests)
- [x] T-062 Commit `test(agent-chat): e2e for the agent picker and new-conversation dialog`

## C8 — STOP

- [ ] T-070 Report. PR **not** opened; await explicit user merge instruction.
