# Feature Specification: Built-in Agent & Chat

**Feature Branch**: `feature/008-builtin-agent-chat`
**Created**: 2026-06-01
**Status**: Draft
**Input**: User description: "Coffer's eighth feature — give Coffer its own built-in agent and a chat surface. Until now Coffer only _managed_ external agents (claude_code / codex) by storing their config; it never ran an LLM itself. This feature adds (a) a built-in agent — a real LLM loop, engine LangGraph so any mainstream model works, wired to Coffer's own MCP gateway so it can use every MCP server / skill / knowledge base / memory the vault manages; and (b) a chat surface where the user can hold a conversation with either the built-in agent OR a Coffer-managed external agent that Coffer drives as a local headless subprocess (claude_code, codex). Conversations and messages persist locally. Streaming is live. Sensitive tool use can pause for human-in-the-loop confirmation, and conversations get an auto-generated title. A separate spec (009) will bridge external messaging channels to this chat. Built on the kind-agnostic Resource framework (001); the built-in agent is its own additive `builtin_agent` resource kind, and chat targets union it with the external `agent` kind (004)."

## User Scenarios & Testing

### User Story 1 — Chat with Coffer's built-in agent (Priority: P1)

The developer opens Coffer's chat surface, starts a new conversation against the built-in agent ("Coffer"), and asks a question that requires the vault — e.g. "search my memory for how I like branches named, then list my registered MCP servers." The built-in agent (a LangGraph loop) reasons, calls Coffer's own gateway tools, and streams its answer back token-by-token. The conversation and every message persist, so reopening it later shows the full history.

**Why this priority**: This is the heart of the spec — Coffer gaining its own agent that dogfoods everything the vault manages. Without it there is nothing to chat with.

**Independent Test**: From a fresh install with an LLM provider key configured, send one message to the seeded built-in agent, observe a streamed assistant reply that invokes at least one `coffer__*` gateway tool, restart the daemon, reopen the conversation, and see the message history intact.

**Covering scenarios**:

- a built-in agent is seeded on first startup
- chat with the built-in agent streams a reply
- the built-in agent can call Coffer gateway tools
- conversation and messages persist across daemon restarts

---

### User Story 2 — Chat with a Coffer-managed external agent (Priority: P1)

The developer has registered `claude_code` (and/or `codex`) as an agent in Coffer. From the chat surface they pick that agent as the conversation target and send a message. Coffer spawns the agent's CLI locally in headless streaming mode, relays the message, and streams the agent's output back into the same chat UI. Because Coffer already installs its MCP gateway into that agent's config, the external agent has the same vault tools available.

**Why this priority**: The user explicitly wants one chat surface for both the built-in agent and the agents Coffer manages. This is what makes Coffer drive — not just store — its agents.

**Independent Test**: Register `claude_code` (binary present on PATH), start a conversation targeting it, send a message, and observe streamed output produced by the spawned `claude` subprocess; stop the daemon and confirm no orphaned child process remains.

**Covering scenarios**:

- chat with an external agent streams its subprocess output
- external agent binary missing is surfaced as a clear error

---

### User Story 3 — Manage conversations (Priority: P1)

The developer keeps several conversations, renames them, archives the stale ones, and deletes the throwaway ones. Each conversation remembers which agent it targets and the model snapshot used.

**Why this priority**: A chat product without conversation management is unusable past the first message.

**Independent Test**: Create three conversations, rename one, archive another, delete the third; list conversations and observe exactly the expected set with correct status.

**Covering scenarios**:

- create / list / rename / archive / restore / delete a conversation
- a conversation records its target agent and model snapshot

---

### User Story 4 — Approve or deny sensitive tool use (Priority: P2)

While an agent (built-in or external) is working, it proposes to run a tool the user has marked as requiring approval (e.g. a write/delete tool). The turn pauses and the chat shows a confirmation card naming the tool and its arguments. The user approves (the tool runs and the turn continues) or denies (the tool does not run and the agent is told it was declined). A pending confirmation that is never answered does not corrupt the conversation.

**Why this priority**: Trust. The built-in agent can reach destructive vault tools; the user must stay in control. (Explicitly added to v1 scope.)

**Independent Test**: Configure the built-in agent to require confirmation for a chosen tool, send a message that triggers it, observe the stream pause with a confirmation request, deny it, and observe the tool was not executed and the agent continued gracefully.

**Covering scenarios**:

- sensitive tool use pauses for confirmation
- approving a confirmation runs the tool and resumes the turn
- denying a confirmation skips the tool and informs the agent

---

### User Story 5 — Conversations get a readable title (Priority: P2)

After the first user/assistant exchange, the conversation gets a short, human-readable title generated from its content (instead of "New chat"), so the conversation list is scannable.

**Why this priority**: Scannability of the conversation list. (Explicitly added to v1 scope.)

**Independent Test**: Start a conversation, send one substantive message, and observe the title change from the placeholder to a short generated title derived from the exchange.

**Covering scenarios**:

- a new conversation gets an auto-generated title after the first exchange
- title generation failure falls back to a truncated first message

---

### User Story 6 — Use chat from the desktop app (Priority: P2)

The developer prefers a visual surface: a conversation list, a streaming message view with tool-call rows and confirmation cards, an input box, a target picker, and a Stop button.

**Why this priority**: Required for non-CLI users; chat is inherently more natural in a UI.

**Independent Test**: Launch Coffer, open Chat, pick a target, send a message, watch it stream, stop mid-stream, then rename and delete the conversation — all from the UI.

**Covering scenarios**:

- desktop chat lists conversations and opens one
- desktop chat streams a reply and can stop it
- desktop target picker lists built-in + chat-capable managed agents

---

### User Story 7 — Use chat from the command line (Priority: P2)

The developer scripts or works headless: create a conversation, send a message and watch it stream in the terminal, print history as JSON.

**Why this priority**: CLI parity and scripting / debugging support.

**Independent Test**: From a terminal, `coffer chat new --agent coffer`, `coffer chat send <id> "hello"` and observe streamed output, then `coffer chat history <id> --json`.

**Covering scenarios**:

- CLI create / send (streaming) / history
- CLI JSON output for piping

---

### User Story 8 — Configure the built-in agent (Priority: P3)

The developer changes the built-in agent's model, system prompt, temperature, or whether it may reach the gateway — through the `builtin_agent` resource's normal config edit path.

**Why this priority**: Customization; the seeded defaults work out of the box, so this is not blocking.

**Independent Test**: Edit the seeded built-in agent's model and system prompt, send a message, and observe the new model is used (reflected in the conversation's model snapshot).

**Covering scenarios**:

- edit built-in agent model / system prompt
- the last built-in agent cannot be deleted (re-seeded if absent)

---

### Edge Cases

- **No LLM provider/key configured (built-in agent)**: `send` is rejected with a 503 carrying `LLM_NOT_CONFIGURED` pointing at setup docs. Listing/reading conversations still works.
- **External agent binary missing / not on PATH**: `send` fails fast with a clear error; the message is marked `failed`; no zombie process.
- **Stream stopped by the user**: the in-flight assistant message is marked `canceled`, partial content retained; the subprocess (if any) is terminated.
- **Runtime error mid-stream**: the message is marked `failed` with a structured error; the conversation is not corrupted; a subsequent send works.
- **Confirmation never answered / times out**: the pending tool does not run; the turn ends with the tool declined; the conversation stays usable.
- **Concurrent send on a conversation already streaming**: rejected with 409; the user retries after the active turn finishes.
- **Conversation targets a since-deleted agent**: the conversation becomes read-only for new turns; sending returns a clear error naming the missing agent.
- **Empty / whitespace-only message**: rejected at the API boundary; nothing persisted.
- **Message exceeding the bound**: rejected at the API boundary (`reason = "too_long"`); nothing persisted.

## Acceptance Scenarios

Every scenario maps to at least one test marked `@pytest.mark.acceptance(spec="008-builtin-agent-chat", scenario="…")`.

### Scenario: a built-in agent is seeded on first startup

- **Given** a fresh install with no `builtin_agent` resources,
- **When** the daemon starts,
- **Then** exactly one enabled `builtin_agent` resource exists (a default name such as `coffer`) with a valid default model and system prompt, recorded with an audit entry.

### Scenario: chat with the built-in agent streams a reply

- **Given** a built-in agent and a configured LLM provider,
- **When** the user creates a conversation targeting it and sends a message,
- **Then** the response streams as incremental events, a user message and an assistant message are persisted, and the assistant message ends in status `complete`.

### Scenario: the built-in agent can call Coffer gateway tools

- **Given** a built-in agent with gateway access enabled and at least one built-in `coffer__*` tool available,
- **When** the user sends a message that requires a vault lookup,
- **Then** the streamed turn includes at least one tool-call event for a `coffer__*` tool and its result is incorporated into the reply.

### Scenario: conversation and messages persist across daemon restarts

- **Given** a conversation with messages,
- **When** the daemon is stopped and restarted,
- **Then** the conversation and its message history are returned unchanged without re-running any turn.

### Scenario: chat with an external agent streams its subprocess output

- **Given** a registered `claude_code` agent whose CLI is available,
- **When** the user creates a conversation targeting it and sends a message,
- **Then** Coffer spawns the agent CLI in headless streaming mode and relays its output as streamed assistant content, persisted like any other turn.

### Scenario: external agent binary missing is surfaced as a clear error

- **Given** a conversation targeting an external agent whose binary is not on PATH,
- **When** the user sends a message,
- **Then** the turn fails with a structured error naming the missing binary, the assistant message is marked `failed`, and no orphan process remains.

### Scenario: create / list / rename / archive / restore / delete a conversation

- **Given** the daemon is running,
- **When** the user creates conversations and then renames, archives, restores, and deletes them,
- **Then** each operation is persisted and reflected in subsequent listings with correct `status`.

### Scenario: sensitive tool use pauses for confirmation

- **Given** an agent turn that proposes a tool marked as requiring confirmation,
- **When** the turn reaches that tool call,
- **Then** the stream emits a `confirmation` event naming the tool and arguments, and the turn is suspended awaiting a decision.

### Scenario: approving a confirmation runs the tool and resumes the turn

- **Given** a suspended turn awaiting confirmation,
- **When** the user approves it,
- **Then** the tool executes, its result is fed back to the agent, and the turn resumes and completes.

### Scenario: denying a confirmation skips the tool and informs the agent

- **Given** a suspended turn awaiting confirmation,
- **When** the user denies it,
- **Then** the tool does not execute, the agent is told the call was declined, and the turn ends without error.

### Scenario: a new conversation gets an auto-generated title after the first exchange

- **Given** a new conversation with the placeholder title,
- **When** the first user/assistant exchange completes,
- **Then** the conversation's title is replaced by a short generated title derived from the exchange.

### Scenario: a streaming turn can be stopped

- **Given** an assistant turn is streaming,
- **When** the user issues stop,
- **Then** streaming halts, the assistant message is marked `canceled` with its partial content retained, and any spawned subprocess is terminated.

### Scenario: send returns 503 when no LLM provider is configured

- **Given** a built-in agent whose resolved provider has no configured key/endpoint,
- **When** the user sends a message,
- **Then** the call is rejected with a 503 carrying `LLM_NOT_CONFIGURED`, and conversation read paths continue to work.

### Scenario: concurrent send on a streaming conversation is rejected

- **Given** a conversation with an active streaming turn,
- **When** a second send is issued for the same conversation,
- **Then** it is rejected with a 409 and the active turn is unaffected.

### Scenario: built-in agent runtime is engine-isolated

- **Given** the codebase,
- **When** imports are analyzed,
- **Then** no module under `coffer.application.*` or `coffer.domain.*` imports `langgraph` / `langchain*`; the engine lives only under `coffer.infrastructure.*`.

> **Deferred to future test work**: these scenarios are part of the contract but their tests land alongside the e2e/UI infrastructure rather than in this PR. `make verify-acceptance` does not gate on them.
>
> - desktop chat lists conversations and opens one
> - desktop chat streams a reply and can stop it
> - desktop target picker lists built-in + chat-capable managed agents
> - CLI create / send (streaming) / history
> - CLI JSON output for piping
> - title generation failure falls back to a truncated first message
> - edit built-in agent model / system prompt
> - the last built-in agent cannot be deleted (re-seeded if absent)

## Requirements

### Functional Requirements

**Built-in agent (resource)**

- **FR-001**: System MUST support a new resource kind `builtin_agent` whose config is validated against a Pydantic schema with fields: `model` (provider-qualified, e.g. `anthropic:claude-sonnet-4-6`), `system_prompt` (optional), `temperature` (optional), `max_tokens` (optional), `credential_ref` (optional), `use_gateway` (bool, default true), and `confirm_tools` (list of tool-name glob patterns that require human confirmation; the seeded default covers destructive patterns such as `*delete*`, `*clear*`, `*remove*`, `*write*`).
- **FR-002**: On startup the System MUST ensure at least one enabled `builtin_agent` resource exists, seeding a default (name `coffer`) if none is present, and MUST refuse to delete the last remaining `builtin_agent` (re-seeding it on next startup if it is somehow absent). Built-in agents are otherwise managed through the existing kind-agnostic Resource lifecycle (create / update / enable / disable / delete), all audited.
- **FR-003**: A `builtin_agent`'s editable config MUST include `model`, `system_prompt`, `temperature`, `max_tokens`, `credential_ref`, `use_gateway`, and `confirm_tools`.

**Agent runtime abstraction**

- **FR-004**: System MUST define a single `AgentRuntime` port that, given a conversation history and a new user message, yields an ordered async stream of runtime events: text deltas, tool-call start, tool result, confirmation request, error, and done. The chat/conversation layer MUST depend only on this port, never on a concrete runtime.
- **FR-005**: System MUST provide two `AgentRuntime` implementations behind that port — a built-in runtime (internal LLM loop) and an external-agent runtime (subprocess) — selected by the conversation's target agent type.

**Built-in runtime (LangGraph)**

- **FR-006**: The built-in runtime MUST be implemented with LangGraph, resolving the model from the agent's `model` string so any mainstream provider supported by the engine works (Anthropic, OpenAI, local Ollama, …), with credentials resolved through Coffer's keychain.
- **FR-007**: When `use_gateway` is true, the built-in runtime MUST expose Coffer's own MCP gateway tools to the agent by connecting to the local gateway endpoint with the daemon token, so the agent can use every enabled MCP server / skill / knowledge base / memory tool the vault manages.
- **FR-008**: LangGraph / LangChain MUST be confined to `coffer/infrastructure/`. Domain and application layers MUST NOT import them; interaction is via the `AgentRuntime` port (enforced by importlinter).

**External-agent runtime (subprocess)**

- **FR-009**: System MUST support chatting with managed external agents of type `claude_code` and `codex` by spawning their CLI locally in headless streaming mode and mapping their streamed output to `AgentRuntime` events.
- **FR-010**: The external-agent runtime MUST run each agent under that agent resource's existing config (its `config_dir`), MUST stream incremental output, MUST support stopping (terminating the child process), and MUST not leave orphan processes when a turn ends, errors, is stopped, or the daemon shuts down.

**Conversations & messages**

- **FR-011**: System MUST persist conversations (`id`, `target_ref` = `builtin_agent:<name>` or `agent:<name>`, `title`, `status` ∈ {active, archived}, `model_snapshot`, timestamps) and messages (`id`, `conversation_id`, `role` ∈ {user, assistant, tool}, `content`, `tool_calls`, `status` ∈ {streaming, complete, failed, canceled}, `error`, `created_at`) in SQLite. A conversation targets exactly one agent, chosen at creation and recorded with a model snapshot.
- **FR-012**: Users MUST be able to create, list (with pagination), get (with message history), rename, archive, restore, and delete conversations. Deleting a conversation removes its messages.
- **FR-013**: User message text MUST be at least 1 char and at most 32768 chars; empty/whitespace-only and over-length inputs are rejected at the API boundary with nothing persisted.

**Streaming & turn control**

- **FR-014**: Sending a message MUST stream the agent turn to the caller as Server-Sent Events; only the finalized message content and tool-call metadata are persisted (streaming deltas are transient).
- **FR-015**: System MUST reject a second concurrent send for a conversation that already has an active streaming turn with a 409.
- **FR-016**: Users MUST be able to stop an in-flight turn; the assistant message is then marked `canceled` with partial content retained.

**Human-in-the-loop confirmation**

- **FR-017**: When a turn proposes a tool whose name matches the target agent's `confirm_tools` policy, the runtime MUST suspend the turn and emit a confirmation request (tool name + arguments); the turn MUST NOT execute that tool until a decision is received. For the built-in runtime this is enforced directly (Coffer controls tool execution); for external-agent runtimes it is enforced where the agent CLI exposes a permission-prompt hook, and otherwise the agent runs under its own configured permission policy (surfaced to the user).
- **FR-018**: Users MUST be able to approve (the tool runs, its result is returned to the agent, the turn resumes) or deny (the tool is skipped, the agent is informed) a pending confirmation. An unanswered confirmation MUST NOT corrupt or block the store; the turn ends with the tool declined.

**Auto-title**

- **FR-019**: After the first user/assistant exchange in a conversation with a placeholder title, the System MUST generate and persist a short title derived from the exchange, falling back to a truncated first user message if generation is unavailable or fails.

**Surfaces**

- **FR-020**: Users MUST be able to perform conversation operations and send/stream/stop messages through (a) a REST API under `/api/v1/conversations/`, (b) `coffer chat …` subcommands, and (c) a desktop chat UI. The target picker MUST list the built-in agent plus all enabled managed agents that support chat (currently `claude_code` and `codex`).
- **FR-021**: Conversation and built-in-agent lifecycle changes MUST be audited; tool invocations made by the built-in runtime through the gateway MUST share the same invocation-logging surface as other gateway tool calls (no argument or return content beyond the tool name).

### Key Entities

- **Built-in Agent** (a resource of kind `builtin_agent`): configuration for Coffer's own LLM agent — model, system prompt, sampling params, credential ref, gateway toggle. At least one always exists.
- **Conversation**: a chat thread targeting exactly one agent. Holds id, target ref, title, status, model snapshot, timestamps.
- **Message**: one entry in a conversation — role, content, tool calls, status, optional error, created_at.
- **Tool Call** (embedded in a message): the tool name, arguments summary, result summary, and whether it required/received confirmation.
- **Confirmation Request** (transient turn state): the pending tool name + arguments awaiting an approve/deny decision.
- **Runtime Event** (transient, not persisted): one streamed unit — text delta, tool-call start, tool result, confirmation request, error, or done.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install with a provider key configured, a user can send their first message to the built-in agent and see a streamed reply within 10 seconds of opening Chat.
- **SC-002**: A built-in-agent turn that needs the vault completes a `coffer__*` tool call and incorporates the result, observable as tool-call events in the stream.
- **SC-003**: A user can chat with a registered `claude_code` (or `codex`) agent and receive streamed output produced by the spawned CLI; stopping the daemon leaves no orphan child process.
- **SC-004**: Stopping a streaming turn halts output within 1 second and preserves the partial assistant message as `canceled`.
- **SC-005**: A confirmation-gated tool never executes without an explicit approval, verified by an acceptance test.
- **SC-006**: Engine isolation is enforced by importlinter: no module under `coffer.application.*` or `coffer.domain.*` imports `langgraph` or `langchain*`.
- **SC-007**: Every Acceptance Scenario is covered by at least one test marked with `acceptance(spec="008-builtin-agent-chat", scenario="…")` (excluding those explicitly deferred above).
- **SC-008**: `make verify` passes locally and in CI.

## Assumptions

- The user runs Coffer on their own machine; talking to cloud LLM providers is allowed (local-first means user _data_ stays local — see `.specify/memory/constitution.md`).
- LangGraph / LangChain remain actively maintained; API churn is absorbed in `infrastructure/` only.
- For external-agent chat, the user has installed the agent's CLI themselves (Coffer does not bundle `claude` or `codex`); Coffer detects presence and reports clearly when absent.
- `cursor` and other registered agent types without a documented headless streaming mode are not chat targets in this spec.
- Channels (bridging external messaging platforms into this chat) are out of scope here and covered by spec 009.
- Single-user concurrency is small; one active streaming turn per conversation is sufficient.
