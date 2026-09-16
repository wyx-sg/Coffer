# Implementation Plan: Chat

## Summary

One platform, two clients. The registry, the adapters, the conversation store,
the turn lifecycle and the event bus are the platform; the web Chat page and the
channel kind are what drive it. The page is planned here rather than in its own
spec because it owns no state — every row it renders and every control it offers
is one of the tables or seams below.

The seam that makes a second agent cheap is `AgentProvider` / `AgentAdapter`
(FR-001, FR-005): the surfaces know the registry, never a provider. The seam
that makes a second *client* cheap is the event bus (FR-026): a turn is a
detached task publishing to subscribers, so "the turn I started" and "the turn
my phone started" are the same code path.

## Technical Context

- **Language/stack**: Python 3.12, FastAPI, SQLAlchemy 2 async + Alembic, SSE
  via `sse-starlette`; React 19 + TypeScript + TanStack Query on the page.
- **Storage**: SQLite, the only data-access path (`infrastructure/persistence/`).
- **Concurrency**: one asyncio daemon. Turn state is process-global (FR-024);
  there is no cross-process coordination and none is planned.
- **External processes**: the Claude Agent SDK and `codex app-server`, each
  spawned per turn by its provider and cancelled through the adapter's own path.

## Constitution Check

- **Local-first**: everything above runs on the user's machine. The one
  exception is FR-045's transcription, which is off unless the user designates
  an internal engine — stated as an exception in the spec rather than hidden.
- **One data-access path**: all reads and writes go through
  `infrastructure/chat/persistence.py`; no route touches a session.
- **Kind isolation**: enforced, not asserted — see Importlinter below.
- **End-to-end deliverable**: the REST half is complete; the CLI half is
  **absent** and recorded as a divergence in the spec's `## Assumptions` rather
  than papered over.

## Module layout — backend

| Module | Holds |
| --- | --- |
| `domain/chat/conversation.py` | The `Conversation` value object. |
| `domain/chat/message.py` | `Message`, `Role`, and the four-member content-block union with its JSON codec. |
| `domain/chat/attachment.py` | The `Attachment` value object an adapter materialises (FR-044). |
| `domain/chat/agent_config.py` | The typed per-conversation provider config (cwd, session id, model, effort). |
| `domain/chat/events.py` | The `AgentEvent` union — and the `type` discriminators that are the wire's event names (FR-027). |
| `domain/chat/errors.py` | `CONVERSATION_NOT_FOUND`, `UNKNOWN_AGENT`, `AGENT_CONFIG_REJECTED`, `TURN_IN_PROGRESS`. |
| `application/chat/ports.py` | The platform seam: `AgentAdapter`, `AgentProvider`, `ModelCatalogPort` (FR-005, FR-007, FR-008). |
| `application/chat/registry.py` | `AgentProviderRegistry` — the one place a turn resolves an agent (FR-001). |
| `application/chat/service.py` | `ChatService`: conversations, messages, titling, the activity bump at start and finalise (FR-014). |
| `application/chat/turn_orchestrator.py` | One turn per conversation, the pending queue, pause/resume, queue reconciliation (FR-018, FR-019, FR-022, FR-023). |
| `application/chat/turn_runner.py` | The detached turn task: history window, placeholder row, idle watchdog, terminal-event handling (FR-013, FR-020, FR-021). |
| `application/chat/turn_state.py` | The process-global per-conversation state and its eviction (FR-024). |
| `application/chat/bus.py` | Fan-out, turn replay, the single latest queue snapshot (FR-026, FR-028). |
| `application/chat/turn_persistence.py` | Assembling a finished turn's blocks into the assistant message. |
| `infrastructure/chat/persistence.py` | The two ORM tables and their repos. |
| `infrastructure/chat/claude_sdk_*.py` | The Claude Code provider, adapter, and event mapping — including the one-shot fresh-session retry (FR-009). |
| `infrastructure/chat/codex_*.py` | The Codex provider, its JSON-RPC/NDJSON app-server client, and event mapping. |
| `infrastructure/chat/adapter_support.py` | What both providers owe their agent: the channel note, the memory injection point, the per-turn model note (FR-010, FR-047). |
| `infrastructure/chat/default_workspace.py` | `~/.coffer/workspace`, created on first use (FR-006). |
| `infrastructure/chat/transcribe.py` | The speech-to-text seam (FR-045). |
| `infrastructure/chat/document_extract.py` | The document-extraction seam (FR-046). |
| `surfaces/http/chat/agent_provider_routes.py` | `/api/v1/agent-providers` — the registry's own two reads (FR-003, FR-004). |
| `surfaces/http/chat/conversation_routes.py` | `/api/v1/chat/conversations` CRUD, archive/unarchive, agent-config, messages. |
| `surfaces/http/chat/turn_routes.py` | The SSE stream, the pending queue, interrupt. |
| `surfaces/http/chat/dependencies.py` | Per-kind dependency providers, including the catalogue port. |
| `surfaces/http/chat_wiring.py` | Composition root for the kind: repos, registry, services, the startup sweep, the catalogue published as a port. |
| `surfaces/http/chat_provider_wiring.py` | Where the providers are registered — adding an agent is one more `register()` here. |

**No CLI module.** `surfaces/cli/` has no `chat` command group; see the spec's
`## Assumptions`.

## Module layout — frontend

| Module | Holds |
| --- | --- |
| `pages/ChatPage.tsx` | The two-column layout and the URL-is-the-open-conversation rule (FR-029, FR-030). |
| `lib/hooks/useChatController.ts` | Orchestration: which conversation is open, the draft, create-on-first-send (FR-042). |
| `lib/hooks/useChatTurn.ts` | The persistent event subscription, bounded reconnect, send/interrupt/pending (FR-033, FR-034). |
| `lib/hooks/chatTurnEvents.ts` | The event reducer and the optimistic echo's reconciliation (FR-027, FR-035). |
| `lib/hooks/useConversations.ts` | List/create/rename/archive/unarchive/delete and the agent-config reads and writes. |
| `lib/hooks/useAgentProviders.ts`, `useAgentModels.ts` | The registry's two reads. |
| `lib/chat/streamClient.ts` | The SSE client; event names come straight off the wire. |
| `lib/chat/threadView.ts`, `scroll.ts`, `turnErrors.ts` | Which rows render, follow-the-stream scrolling, error wording. |
| `lib/api/chat.ts`, `lib/api/agentProviders.ts`, `lib/api/agentModels.ts` | Typed clients for the contract. |
| `components/chat/` | `ConversationList`, `MessageThread`, `MessageBubble`, `ToolCallCard`, `MarkdownContent`, `Composer`, `PendingQueue`, `DraftThread`, `AgentModelBar`, `ModelPicker`, `EffortPicker`, `ChatErrorBanner`. |
| i18n | The `chat` namespace; no chat string lives outside it. |

## Tests

- **Domain/application**: the orchestrator and runner against scripted
  providers — queueing, pause/resume, head-reinsert on a failed start, the idle
  watchdog, the missing-terminal case, the history window.
- **Infrastructure**: each provider against a fake process, including the
  resume-retry path and the transcription/extraction degradations.
- **HTTP**: the contract's status codes, notably the 404/400 split of FR-004 and
  the 202 of FR-033.
- **Frontend**: the reducer, the echo reconciliation, and each component;
  end-to-end coverage of the page's send → stream → persist loop lives in `e2e/`.
- Every acceptance scenario carries an `acceptance(spec, scenario)` marker with
  `spec="chat"`.

## Importlinter & enforcement

`backend/pyproject.toml` carries a `forbidden` contract, **"Cross-kind imports
forbidden (chat)"**, whose source modules are exactly `coffer.domain.chat`,
`coffer.application.chat`, `coffer.infrastructure.chat` and
`coffer.surfaces.http.chat`, and whose forbidden modules are every other kind's
four layers. It has **zero** `ignore_imports` exceptions — this boundary has
never been waived, and anything chat and another kind both need becomes
kind-agnostic substrate rather than an exception.

Two consequences worth stating, because they look like violations and are not:

- The **model catalogue** is the agent kind's knowledge, so it cannot be
  imported. The composition root publishes the agent service into chat's own
  dependencies as `ModelCatalogPort`, and the route reads only what the port
  promises (FR-003).
- **Adapters never import chat modules** is the same fence seen from the channel
  side; that statement belongs to spec [channels](../channels/spec.md). Chat's
  half is the one above.

Also enforced: all files ≤ 400 lines, every route declares `response_model`,
mypy strict.

## Risks & mitigations

- **Agent CLI drift** — each agent is one provider plus one mapping module, so a
  breaking change upstream breaks one file and is covered by a fake-process
  test.
- **A wedged turn holding a conversation** — the idle watchdog (FR-020) cancels
  through the adapter's own path, and the startup sweep (FR-021) cleans up what
  a crash left.
- **Queue loss on restart** — in-memory by design (FR-018); the mitigation is
  that nothing is *silently* lost, since an uncommitted message was never a row
  and an in-flight turn becomes a visibly failed one.
- **The page is the only human surface** — the missing CLI means a daemon
  without the web UI built has no way to drive a conversation. Recorded in the
  spec's `## Assumptions` as a gap to close, not a design choice.
