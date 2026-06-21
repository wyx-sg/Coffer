# Feature Specification: Agent Chat

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/agent-chat`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Coffer needs a chat platform. A first-class chat
page where the user holds many conversations, and a stable seam so that more
than one kind of agent can be reached from that page without re-architecture.
Coffer ships one agent on the platform out of the box — a general-purpose
built-in agent that uses every resource in the vault (MCP tools, skills,
memory, knowledge bases) through Coffer's own MCP gateway, on a user-chosen LLM
provider. The platform also carries the controls every conversation needs:
streamed turns, one in-flight turn at a time, and user interruption."

This spec turns Coffer from a vault that _stores_ AI assets into one that
_uses_ them, and it does so as a **platform**, not a single hard-wired feature.
It delivers two things at once:

1. **A chat platform.** A first-class chat surface, persisted multi-conversation
   history, a streamed turn protocol, and user interruption — all expressed
   against an **agent-provider registry**. An agent is reached only through that
   registry, so adding another kind of agent is a new registry entry, not a
   change to the chat page, the persistence layer, or the REST/SSE contract.
2. **Agents on that platform.** Coffer's built-in general-purpose agent,
   "Coffer Assistant" — an in-process agentic loop, driven by the user's own
   MCP servers, skills, memory, and knowledge bases through Coffer's MCP
   gateway, on a user-configured LLM provider — **plus** two CLI-backed agents,
   **Claude Code** and **Codex**, each driven by its installed command-line tool
   in a working directory (the Coffer-managed workspace by default). The CLI agents are
   what keep the seam honest: they are real second and third providers, not a
   promise, and they prove that adding an agent is one registry entry with no
   change to the chat surface, persistence, or the wire contract.

The platform pieces and its agents are co-delivered because a platform with no
agent cannot be exercised, and an agent with no platform cannot be reached. The
agents run with full permissions; owner-pairing is the security gate. The seam
is real on the day it lands rather than a promise.

## Positioning — Vault Console ([ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.md))

After shipping, this surface is repositioned from "a general multi-agent chat
client" to the **Vault Console**: the place to _use and inspect the vault_, not a
daily in-browser coding chat that competes with the agents' own UIs or with IM.
Its two durable jobs are:

1. **Talk to the vault.** Through the built-in agent (an in-process MCP client of
   Coffer's own gateway), the user converses with — and inspects — their memory,
   skills, knowledge, and aggregated MCP tools. Each turn surfaces which vault
   resources it touched, so the console doubles as a way to see what an agent
   would get from the vault.
2. **Observe channel-driven conversations.** Channels (Spec 009) create
   conversations through the **same** `ConversationPort` / `TurnPort` seams this
   surface uses. The console surfaces conversation origin (web draft vs. channel
   peer) so the user can watch turns an IM peer is driving.

The CLI agents (Claude Code, Codex) are **not** repositioned as a daily coding
chat; they remain (a) test-drive targets that keep the provider seam honest and
(b) the conversations an IM peer drives that the user observes here.
**De-scoped:** using Coffer as a primary in-browser coding chat; affordances that
only make sense for that positioning stay out of scope unless a future spec
re-opens it.

## Repositioning — the built-in agent is an internal capability ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md))

[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)
partially supersedes the Vault Console positioning above. The `builtin` "Coffer
Assistant" is **retired as a chat persona**: it is no longer a registered chat
agent and is removed from the agent picker. Chat talks **only** to Coffer-managed
agents (`claude_code`, `codex`, and future managed agents), and the surface
reverts from _Vault Console_ to **Chat**. The "talk to the vault through the
built-in agent" job is dropped; the local model is recast as an **internal-only**
capability reachable solely through `coffer__*` MCP tools — a semantic upgrade to
`coffer__search_tools` and a new `coffer__ask` agentic-RAG tool over
knowledge/memory (see ADR-024). The **observe channel-driven conversations**
job (ADR-021 job 2) stands unchanged, over the same `ConversationPort` /
`TurnPort` seams.

Where the User Stories, Acceptance Scenarios, and Functional Requirements below
still describe the built-in agent as a selectable chat agent (its model picker,
its in-chat vault tool calls, `coffer chat` against it), read them as the
historical shipped behaviour that ADR-024 removes from the chat surface; the
LLM/agentic-loop machinery is kept but repurposed behind `coffer__ask` rather
than presented to the user as a chat persona.

## Repositioning — single-owner live mirror ([ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md))

[ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md) commits
the surface to one irreplaceable job and **narrows** ADR-021 job 2 from _observe_
to _observe + interrupt + inject_. Because Coffer channels are **owner-paired**,
the "IM peer" is the **same owner** on their phone — so Chat is the **desktop
surface of the same conversations the owner also drives from IM**: one owner, one
conversation timeline, two screens, one underlying agent session. From the desktop
the owner can **observe** any conversation live (including a turn kicked off from
the phone, token by token), **interrupt** a running turn, and **inject/continue**
by typing freely — messages **queue**, never block. There is no multi-human model.

Three structural moves follow, refining the requirements below:

1. **A live conversation bus.** Turn events are published to a per-conversation
   broadcaster (with a ring buffer for replay) that any surface subscribes to via
   `GET /conversations/{id}/events`; `POST .../messages` becomes fire-and-return.
   This is the single new capability — observe was the only one of the three
   actually missing (FR-018 → FR-019b).
2. **Send freely; a FIFO pending queue.** The composer never locks; an over-sent
   message queues and is processed in order (amends FR-018).
3. **Collapse origin.** The web/channel dichotomy collapses to one conversation
   model; `channel_name`/`peer_chat_id` survive as an optional `channel_binding`
   (the return address); `origin`/`peer_display_name` are dropped (revises FR-034).

Where User Stories, Acceptance Scenarios, and FRs still describe the composer
locking during a turn or an `origin`/`peer` field, read them as superseded by the
ADR-031 wording here and the revised FRs below.

## Repositioning — a managed agent's per-conversation model is its own model ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) → [ADR-032](../../docs/decisions/ADR-032-provider-switching.md))

[ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)
retired the built-in chat persona, which **re-founds** the per-conversation model
override (FR-025/FR-026, User Story 8). For a managed agent the conversation's
model is **not** the now-retired Coffer model registry (the `Conversation.model_id`
column): it is the agent's **own** model, carried as free-text `agent_config.model`
and passed through to the agent's CLI (Claude Code `--model`, Codex `model`),
exactly as the channel `/model` command already does. Coffer does not validate the
name — a bad model is reported by the agent's CLI on the next turn.

Two layers, one override:

1. **Global default.** Provider Switching ([ADR-032](../../docs/decisions/ADR-032-provider-switching.md), spec 011)
   projects the active provider profile's `model` (and, for Claude, `fast_model`)
   into the agent's native config. This is what a turn runs when the conversation
   does not override the model.
2. **Per-conversation override.** `agent_config.model` is passed as an explicit
   per-turn option that the CLI honours over its config default. An **empty**
   per-conversation model inherits the global default; setting it overrides only
   the subsequent turns of that one conversation and preserves the conversation's
   other agent config (`cwd`, `session_id`).

`Conversation.model_id` (the `Model` registry override of FR-026) is **not read by
the managed-agent turn path** — both managed providers build their adapter from
`agent_config.model`, never from `model_id`. The standalone `ModelConfig`/`chat_models`
registry it referenced is now **retired** (folded into provider connections, spec
011 / ADR-032), so `model_id` is a **vestigial legacy column**: Coffer's internal
engine now selects its model from the internal-default connection, not from this
registry. The column is out of scope for the chat model picker.

The web Chat surface MUST let the owner set `agent_config.model` both when
**starting** a conversation (the draft, beside the agent picker) and
**mid-conversation** (the agent bar), mirroring `/model`. The control is a
free-text combobox with **best-effort** suggestions — the agent's active provider
profile `model`/`fast_model` ([ADR-032](../../docs/decisions/ADR-032-provider-switching.md)),
augmented best-effort by provider model introspection — and an empty value that
inherits the global default.

Where FR-025/FR-026, User Story 8, and the "model selection is recorded" scenario
describe a Coffer-registered `Model` (`model_id`) override for the built-in agent,
read them as repositioned here: for managed agents the per-conversation model is
`agent_config.model`, governed by FR-026a/FR-026b below.

## User Scenarios & Testing

### User Story 1 — Configure a model provider before the first chat (Priority: P1)

The built-in agent has no LLM of its own. On first visit to Chat, the user is
pointed at **Settings → LLM Connections** (spec 011), where they configure at
least one connection: choose a wire (anthropic, openai, or a local ollama
endpoint), supply the credential (cloud wires) or base URL (ollama), and name a
model id. Once one connection exists and is marked the internal default, the
built-in agent can be chosen and chat is unlocked.

**Why this priority**: Without a configured model the built-in agent cannot
answer at all. This is the gate to every other scenario that uses it.

**Independent Test**: With a fresh install, open Settings → LLM Connections, add
an anthropic connection with a credential, mark it the internal default; observe
it listed; the Chat page stops showing the "no model configured" state.

**Covering scenarios** (connection configuration now lives in spec 011 / Settings
→ LLM Connections; this story's chat-side coverage is):

- chat runs on the built-in model when no connection
- list a provider's models
- test a model connection

---

### User Story 2 — Start a conversation by choosing an agent (Priority: P1)

The user starts a new conversation from the Chat page. A **new-conversation
dialog** asks which agent the conversation should talk to: it lists every agent
the platform offers, with each agent marked available or unavailable, and shows
a configuration area whose contents depend on the chosen agent. For the
built-in agent that configuration area is the model selection. The conversation
records which agent it belongs to and is created with that agent's
configuration validated and stored.

**Why this priority**: This is the platform seam made visible. A conversation
that cannot name its agent cannot be routed to one, and a chat page that
hard-codes a single agent is not a platform.

**Independent Test**: Open Chat, click "New conversation"; the dialog lists the
built-in agent; pick it, confirm; a conversation is created whose recorded agent
is the built-in one and which is immediately usable.

**Covering scenarios**:

- the new-conversation dialog lists every registered agent with its availability
- creating a conversation records the chosen agent and validates its config
- an unknown agent or an invalid agent configuration is rejected, nothing persisted
- the agent list is reachable from the REST API

---

### User Story 3 — Chat with an agent and watch it stream (Priority: P1)

The user opens a conversation, types a message, and receives a streamed reply —
text appears token by token, tool calls appear as they happen, and the
conversation stays interactive. Only one turn runs per conversation at a time;
the composer is locked while a turn streams.

**Why this priority**: This is the core deliverable. A chat page that cannot
hold a streamed conversation is not a product.

**Independent Test**: With the built-in agent and one model configured, send
"Explain what Coffer is in two sentences", observe a streamed assistant reply
that completes without error and is still visible after reload.

**Covering scenarios**:

- send a message and receive a streamed assistant reply
- the reply is persisted and survives a page reload and a daemon restart
- the composer stays usable while a turn streams; a message sent during a turn
  queues rather than being rejected ([ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md), supersedes the former composer-lock)
- an LLM/provider error surfaces in the conversation without crashing the page

---

### User Story 4 — The built-in agent works with the vault (Priority: P1)

The user asks the built-in agent something that needs their own data ("what do
my notes say about OAuth?"). The agent calls tools through Coffer's MCP
gateway — upstream MCP server tools, `coffer__recall`, `coffer__search_knowledge`,
`coffer__load_skill` — and each call appears in the message stream as an inline,
expandable card showing the tool name, status, inputs, and result.

**Why this priority**: This is what makes the built-in agent _Coffer's_ agent
rather than a generic chat box — it dogfoods the vault.

**Independent Test**: With a memory store holding a known record, ask the agent a
question answerable only from that record; observe a `coffer__recall`
tool-call card in the stream and an answer grounded in the record.

**Covering scenarios**:

- the agent discovers every tool the gateway aggregates (upstream MCP + built-in)
- a tool call renders as an inline expandable card, collapsed by default
- skills are reachable via `coffer__list_skills` / `coffer__load_skill`
- a failed tool call renders a failed card and the agent continues or reports it
- a turn that reaches the tool-iteration limit ends cleanly, not as an error
- the agent answers normally when the vault has no MCP servers, memory, or KB

---

### User Story 5 — Keep many conversations (Priority: P1)

The user runs more than one thread of work. They create new conversations,
switch between them in the history list, rename them, and delete the ones they
no longer need. Everything persists across daemon restarts.

**Why this priority**: A chat with a single ephemeral thread loses work and does
not match Coffer's local-first, SQLite-as-record posture.

**Independent Test**: Create two conversations, send a message in each, rename
one, restart the daemon, reopen Chat — both conversations and their messages are
still present with the new name; delete one and confirm it is gone.

**Covering scenarios**:

- create, list, switch, rename, and delete conversations
- a new conversation receives an auto-generated title from its first message
- conversations and messages survive a daemon restart
- the conversation history list is collapsible

---

### User Story 7 — Stop a turn that is running (Priority: P2)

A turn is taking too long or going the wrong way. The user clicks **Stop**. The
turn ends immediately; whatever the agent had already produced — partial text,
completed tool calls — is kept as the assistant's message, so the conversation
shows what happened and stays usable. This is distinct from deleting the
conversation, which discards an in-flight turn entirely.

**Why this priority**: Without a stop control a slow or misdirected turn holds
the conversation hostage until it finishes. Not blocking the core loop.

**Independent Test**: Start a turn, click Stop mid-stream; the turn ends, an
assistant message holding the partial output is persisted, and the conversation
accepts the next message.

**Covering scenarios**:

- stopping a running turn ends it and persists the partial assistant message
- a stopped conversation immediately accepts a new turn
- stopping when no turn is running is a harmless no-op
- deleting a conversation with a live turn discards it and leaves no orphan rows

---

### User Story 8 — Switch the model per conversation (Priority: P2)

The user has more than one model configured and picks which one a given
conversation's built-in agent uses, from a model selector in the thread's top
bar.

**Why this priority**: Different work wants different models (a local model for
quick drafts, a frontier model for hard reasoning). Not blocking the core loop.

**Independent Test**: With two models configured, change a conversation's model
in the top-bar selector, send a message, and confirm the turn ran on the chosen
model (recorded on the resulting message).

**Covering scenarios**:

- a conversation uses the default model unless overridden
- changing the model selector affects subsequent turns only
- each assistant message records which model produced it

---

### User Story 10 — See what the agent did and what it cost (Priority: P3)

Every turn records token usage on the resulting message, and every tool the
built-in agent invokes flows through the gateway's existing audit trail.

**Why this priority**: Builds trust and supports debugging and cost awareness.
Not blocking core chat operation.

**Independent Test**: Run a turn that calls at least one tool; confirm the
assistant message shows token usage and the audit log records the completed
turn with actor `agent`.

**Covering scenarios**:

- an assistant message records prompt/completion token usage
- a completed turn is recorded in the audit log with actor `agent`

---

### Edge Cases

- **No model configured**: The Chat page renders an actionable empty state that
  links to Settings → LLM Connections; it does not show a generic error or a dead
  input. Choosing the built-in agent with no internal connection configured fails
  the turn with the no-model state, not a crash.
- **Unknown agent / invalid agent configuration**: Creating a conversation with
  an agent the platform does not offer, or with a configuration that agent
  rejects, fails with a message naming the problem; nothing is persisted.
- **Invalid or revoked credential**: The turn fails with a message naming the
  provider; the conversation stays usable; no partial assistant message is left
  in a "streaming forever" state.
- **Tool call fails** (upstream MCP server down, built-in tool raises): the tool
  card shows a failed state, the failure is returned to the agent as a tool
  result, and the agent may retry, route around it, or report it.
- **Runaway tool loop**: a turn is bounded by a tool-iteration limit; on reaching
  it the turn ends cleanly as a normal turn completion (carrying the stop reason
  `max_iterations`), not as an error.
- **Conversation longer than the model context window**: the built-in agent
  sends the most recent history that fits within a context budget (approximated
  by a character budget, ~4 chars/token); older turns are omitted from the model
  input with a marker, while the full conversation remains stored.
- **Second message sent while a turn is streaming**: accepted and enqueued on the
  pending queue (the composer never locks); it runs as its own turn after the
  current one ends (FR-018/FR-018a). Interrupting instead pauses the queue
  (FR-018b).
- **Streaming client disconnects mid-turn** (page closed, navigated away): the
  turn completes server-side and the assistant message is persisted; the next
  load shows the finished message.
- **Turn interrupted by the user**: the turn stops at once and the partial
  assistant message is persisted (User Story 7).
- **Conversation deleted while its turn is streaming**: the in-flight turn is
  cancelled and discarded; no orphan message rows remain.
- **A skill with malformed frontmatter**: excluded from the skill catalogue
  exposed to the built-in agent; it does not break tool listing or the turn.
- **Daemon restart with an interrupted turn**: no conversation is left with a
  half-written streaming message; an interrupted turn is marked failed.

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is
referenced by at least one test marked
`@pytest.mark.acceptance(spec="008-agent-chat", scenario="…")` (Python) or
`acceptance("008-agent-chat", "…", …)` (TypeScript).

### Scenario: list available agents

- **Given** a running daemon,
- **When** the user asks the platform which agents it offers,
- **Then** the managed agents (`claude_code`, `codex`) are listed, each with a
  display name and an availability flag, the `builtin` agent is **not** among
  them ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)),
  and the list is reachable from the REST API.

### Scenario: choose an agent when starting a conversation

- **Given** a running daemon,
- **When** the user creates a conversation, naming an agent and supplying that
  agent's configuration,
- **Then** the conversation is persisted recording that agent, the agent's
  configuration is validated and stored, and the conversation is ready to use.

### Scenario: reject an unknown agent or invalid agent configuration

- **Given** a running daemon,
- **When** the user creates a conversation naming an agent the platform does not
  offer, or supplying a configuration that agent rejects,
- **Then** the request is rejected with a message naming the problem and no
  conversation is persisted.

### Scenario: send a message and receive a streamed reply

- **Given** a conversation and at least one configured model,
- **When** the user sends a message and subscribes to the conversation's event
  stream,
- **Then** the assistant reply streams incrementally over the subscription,
  completes, and is persisted as a message on that conversation.

### Scenario: observe a turn started from another surface

- **Given** a conversation with a turn already in flight (e.g. started from the
  IM channel),
- **When** a client subscribes to `GET /conversations/{id}/events`,
- **Then** the in-flight turn's events so far are replayed and then streamed live
  to completion, without the client having started the turn.

### Scenario: a queued message runs after the current turn

- **Given** a turn is in flight,
- **When** the user sends a second message,
- **Then** it is accepted (not rejected), held as a pending item, and run as its
  own turn once the in-flight turn ends.

### Scenario: interrupting a turn pauses the pending queue

- **Given** a turn is in flight with one or more pending messages queued,
- **When** the user interrupts the turn,
- **Then** the current turn stops with its partial output kept and the pending
  messages are held (not auto-run) until the owner resumes or drops them.

### Scenario: reply survives a restart

- **Given** a conversation with a completed assistant reply,
- **When** the daemon restarts and the user reopens the conversation,
- **Then** every message is present and unchanged.

### Scenario: skills are reachable as tools

- **Given** at least one valid skill in the vault,
- **When** the agent lists available tools,
- **Then** `coffer__list_skills` and `coffer__load_skill` are present and
  `coffer__load_skill` returns the skill's content.

### Scenario: stop a running turn

- **Given** a turn that is streaming,
- **When** the user stops it,
- **Then** the turn ends at once, an assistant message holding whatever was
  produced so far is persisted, and the conversation immediately accepts a new
  turn.

### Scenario: manage conversations

- **Given** a running daemon,
- **When** the user creates, renames, switches, and deletes conversations,
- **Then** each operation persists and the history list reflects it; a deleted
  conversation and its messages are removed.

### Scenario: archive and restore a conversation

- **Given** a conversation in the active history list,
- **When** the user archives it,
- **Then** it leaves the default (active) list, appears in the archived list,
  and is not destroyed; restoring it returns it to the active list. Archiving a
  conversation that does not exist is rejected.

### Scenario: second message queues during a streaming turn

- **Given** a turn is streaming,
- **When** the user sends another message in the same conversation,
- **Then** the message is accepted and enqueued (the composer does not lock), and
  runs as its own turn after the current one ends.

### Scenario: editing a queued message re-queues it at the tail

- **Given** one or more messages are queued behind a streaming turn, shown one
  per row,
- **When** the user edits a queued message,
- **Then** that message is pulled out of the queue and back into the composer to
  amend, and re-sending it enqueues it at the tail of the pending queue.

### Scenario: model selection is recorded

- **Given** two configured models,
- **When** the user sets a conversation's model and sends a message,
- **Then** the turn runs on the chosen model and the assistant message records
  which model produced it.

### Scenario: set a managed agent's model per conversation

- **Given** a conversation with a managed agent and an active provider profile,
- **When** the owner sets the conversation's agent model to a free-text id (from
  the draft or the agent bar),
- **Then** the value is persisted as `agent_config.model`, the conversation's
  `cwd` and `session_id` are preserved, and subsequent turns pass that model to
  the agent's CLI; clearing it reverts to the provider profile's projected
  default.

### Scenario: chat runs on the built-in model when no connection

- **Given** a running daemon with no LLM connection configured for the agent,
- **When** the user opens the Chat page,
- **Then** the composer is available (no blocking empty state) and a sent turn
  runs on the agent's own built-in model/login — a Coffer LLM connection is an
  optional override, not a prerequisite (ADR-032 amendment D1).

### Scenario: token usage and audit

- **Given** a turn that completes,
- **When** the turn ends,
- **Then** the assistant message records token usage and the audit log contains
  the completed turn with actor `agent`.

### Scenario: list a provider's models

- **Given** the user is adding or editing a model and has entered a provider
  (plus base URL / credential ref where the provider needs them),
- **When** they fetch the provider's models,
- **Then** Coffer returns the model ids the provider exposes for selection, and
  if none can be listed it returns an empty list with a message so the user can
  still type a model id manually.

### Scenario: test a model connection

- **Given** a model's provider, model id, and (where required) credential ref,
- **When** the user tests the connection,
- **Then** Coffer makes a minimal request to the provider and reports success or
  a humanized failure message, without persisting anything.

### Scenario: a channel-driven conversation is observable from the console

- **Given** a conversation that carries a channel binding (the owner is driving it
  from an IM channel),
- **When** the user opens Chat,
- **Then** the conversation appears badged with its channel binding, and its turns
  stream the same turn events over the subscription that a web-started turn would.

## Requirements

### Functional Requirements

**Chat platform & the agent-provider seam**

- **FR-001**: The chat surface MUST reach an agent only through an
  **agent-provider registry**: a turn is run, a conversation is initialised, and
  a conversation's agent state is torn down by asking the registry for the agent
  named on the conversation. The chat page, the persistence layer, and the
  REST/SSE contract MUST NOT depend on any specific agent.
- **FR-002**: Adding another agent to the platform MUST be a new registry entry
  only — it MUST require no change to the chat REST/SSE contract, the
  conversation/message schema, the turn orchestrator, or the chat page.
- **FR-003**: Each conversation MUST record which agent it belongs to via an
  `agent_key`. Creating a conversation MUST accept an `agent_key` (defaulting to
  the built-in agent) and an opaque, agent-specific configuration; the named
  agent MUST validate and persist that configuration, rejecting an invalid one
  as a domain error. An `agent_key` no agent provides MUST be rejected.
- **FR-004**: The platform MUST expose the list of registered agents — each with
  a stable key, a display name, and a current availability flag — through the
  REST API and the GUI's new-conversation dialog.
- **FR-005**: An agent is addressed for a turn through an **agent adapter** that
  is self-contained: given only the conversation history, it yields a stream of
  typed turn events. The adapter carries its own
  model, tools, and configuration; the orchestrator MUST NOT inject them. The
  platform ships three agents behind this seam — the built-in agent plus two
  CLI-backed agents (Claude Code, Codex) — so the seam is validated by real
  additional providers, not a single occupant.
- **FR-005a**: System MUST ship subprocess-backed agent providers for Claude Code and
  Codex. Each runs in a working directory (its `agent_config.cwd`). When a turn
  supplies no cwd, the provider MUST default to the Coffer-managed workspace
  `~/.coffer/workspace` (created on first use) rather than reject the turn — so a
  chat draft (no per-turn directory picker) and a channel without a configured
  workspace both work out of the box. An explicitly-supplied cwd MUST be an
  existing directory or the configuration is rejected. A CLI agent's availability MUST reflect whether its command-line
  binary is resolvable on the daemon's PATH; an unavailable agent is listed but
  not selectable. A CLI turn MUST run the tool in that directory, stream its
  line-delimited JSON output mapped onto the platform's turn events, and persist
  the upstream session id so the next turn continues the same session. Claude
  Code is driven via the Claude Agent SDK and Codex via `codex app-server`
  (JSON-RPC 2.0 over stdio, NDJSON-framed); both run with full permissions
  (owner-pairing is the security gate).

**Built-in agent & agentic loop**

- **FR-006**: System MUST ship a built-in general-purpose agent, "Coffer
  Assistant", defined in code (identity, system prompt, default behaviour).
  Agents are defined in code and registered at startup; there is no creation,
  editing, or deletion of agents through the API.
- **FR-007**: System MUST run the built-in agent as an in-process agentic loop:
  call the selected LLM, execute any requested tools, feed results back, and
  repeat until the model yields a final answer or a bound is hit.
- **FR-008**: System MUST bound each built-in-agent turn by a configurable
  tool-iteration limit and end an over-limit turn cleanly as a normal turn
  completion (stop reason `max_iterations`), not as an error.
- **FR-009**: The built-in agent's system prompt MUST establish its identity as
  Coffer's assistant and include a catalogue (name + description) of the vault's
  skills.
- **FR-010**: The built-in agent MUST resolve the conversation's model when its
  adapter is built for a turn; a turn started for the built-in agent with no
  model configured MUST fail with the "no model configured" condition before
  any message is streamed.

**Vault capability surface (built-in agent)**

- **FR-011**: System MUST give the built-in agent every tool Coffer's MCP gateway
  aggregates — upstream MCP server tools and `coffer__`-prefixed built-in
  tools — by consuming the gateway in-process, without a network or subprocess
  transport.
- **FR-012**: System MUST expose the vault's skills to the agent as gateway
  built-in tools `coffer__list_skills` and `coffer__load_skill`, following the
  existing per-kind `application/<kind>/builtin_tools.py` pattern.
- **FR-013**: When the built-in agent invokes a tool, System MUST route it
  through the gateway so the gateway's existing capability gating and invocation
  log apply.
- **FR-014**: A tool failure MUST be returned to the agent as a tool result
  describing the error; it MUST NOT abort the turn.

**Conversations & persistence**

- **FR-015**: System MUST persist conversations and their messages in SQLite as
  the system of record; they are not modelled as Resources of the kind-agnostic
  Resource framework.
- **FR-016**: Users MUST be able to create, list, open, rename, and delete
  conversations; a new conversation MUST receive an auto-generated title derived
  from its first message; deleting a conversation MUST also tear down its agent's
  per-conversation state through the registry.
- **FR-016a**: Users MUST be able to archive a conversation and restore it. An
  archived conversation is excluded from the default (active) list, retrievable
  through an archived listing, and not destroyed; archiving is reversible and
  distinct from deletion. The conversation history MUST be searchable by title,
  and the active/archived views MUST be switchable from an in-list filter.
- **FR-016b**: Conversations MUST follow a two-stage, retention-managed lifecycle,
  both windows configurable under Settings → Data: (1) the retention worker
  auto-archives conversations with no new message for the auto-archive window
  (default 7 days), and (2) deletes archived conversations (and their messages)
  the configured number of days after they were archived (default 30 days).
  Either window may be set to keep-forever to disable that stage; auto-archiving
  is reversible (the user can restore) and only deletion is destructive.
- **FR-017**: A message MUST store its role and an ordered list of content blocks
  of types `text`, `tool_use`, and `tool_result`; assistant messages MUST also
  store token usage and the model that produced them when the agent reports one.

**Turn lifecycle: streaming, interruption**

- **FR-018**: System MUST process at most one in-flight turn per conversation,
  but MUST NOT reject a message sent while a turn is running (revises the original
  reject-and-lock rule, [ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md)).
  A message sent during a turn is **enqueued** on a per-conversation **pending
  queue**; the composer never locks.
- **FR-018a**: When the in-flight turn ends, System MUST dequeue the head of the
  pending queue, commit it as the conversation's next user message, and run its
  turn — sequential FIFO, one turn per queued message (not coalesced). A pending
  message is **not** committed to the message sequence until its turn starts; it
  is surfaced as a removable pending item the owner may drop before it runs. The
  pending queue is in-memory; it auto-advances after *any* turn on the
  conversation ends (including an IM-driven one), so a desktop message queued
  behind a phone-started turn still runs when that turn completes. (A message
  arriving *from* an IM channel while a turn is in flight is held by the channel's
  own inbound buffering, Spec 009, rather than this queue; v1 does not merge the
  two into one physical FIFO.) A daemon restart drops not-yet-committed pending
  messages.
- **FR-018b**: Interrupting a turn (FR-021) MUST also **pause** the pending queue:
  the current turn stops with its partial output kept, and queued messages are
  held (not auto-run) until the owner resumes or drops them.
- **FR-019**: System MUST express a turn as a sequence of typed events covering,
  at minimum, turn start, text deltas, tool calls, tool results, turn completion,
  turn error, and **pending-queue change** (`queue_changed`, carrying the ordered
  pending items so every subscriber renders the same pending state).
- **FR-019a**: System MUST expose a per-conversation **live event subscription**
  at `GET /conversations/{id}/events` (SSE) that any number of clients may attach
  to. On attach, if a turn is in flight it MUST replay the current turn's events
  (so a late subscriber — e.g. the desktop opened mid-turn, or watching a
  phone-started turn — catches up), then stream live; when no turn is in flight it
  MUST hold the connection open and deliver the next turn's events whenever one
  starts, from any surface.
- **FR-019b**: `POST /conversations/{id}/messages` MUST start (or enqueue) a turn
  and return immediately (fire-and-return); it MUST NOT be the event stream. All
  turn-event consumption flows through the FR-019a subscription (single event
  path), so observing a turn the client started and observing a turn another
  surface started travel the same code.
- **FR-019c**: System MUST expose the pending queue for management at
  `PUT /conversations/{id}/pending`, which replaces the ordered pending texts
  (one primitive covering resume, drop, and reorder): the replacement unpauses
  the queue and starts the next turn when none is in flight, and broadcasts
  `queue_changed` to all subscribers.
- **FR-021**: System MUST let the user interrupt a running turn: the turn stops
  at once and the partial assistant message (whatever text and tool blocks were
  produced) MUST be persisted. Interruption is distinct from conversation
  deletion, which discards the in-flight turn.
- **FR-022**: An interrupted turn (user interrupt, client disconnect, daemon
  restart, conversation deletion) MUST NOT leave a conversation with a
  perpetually "streaming" message; such a turn MUST be finalised or marked
  failed.

**Model providers & credentials**

- **FR-023**: Users MUST be able to register, list, edit, and remove configured
  models; v1 MUST support the provider types `anthropic`, `openai`, and `ollama`,
  and adding another provider type MUST be configuration, not re-architecture.
- **FR-024**: A configured model MUST carry the credential it needs only as a
  credential reference resolved at runtime through the credential module; no
  secret material is stored with the model row or reaches the database in
  plaintext.
- **FR-025**: System MUST mark exactly one configured model as the default and
  use it for any conversation that does not override the model.
- **FR-026**: A conversation MUST be able to override the model; the override
  affects only subsequent turns of that conversation.
- **FR-026a**: For a **managed agent**, the conversation's model override MUST be
  the agent's own model carried as free-text `agent_config.model` and passed
  through to the agent's CLI (not a Coffer-registered `Model`/`model_id`).
  Setting it MUST preserve the conversation's other agent config (`cwd`,
  `session_id`) and affect only subsequent turns; an empty value MUST inherit the
  global default that Provider Switching ([ADR-032](../../docs/decisions/ADR-032-provider-switching.md))
  projects into the agent's native config. The managed-agent turn path MUST NOT
  read `Conversation.model_id`.
- **FR-026b**: The REST API MUST expose reading and setting a conversation's
  `agent_config.model`, and creating a conversation MUST accept an initial
  `agent_config.model`. The GUI MUST surface this both at conversation creation
  (beside the agent picker) and mid-conversation, as a free-text combobox whose
  best-effort suggestions come from the agent's active provider profile
  `model`/`fast_model` augmented by best-effort provider model introspection
  (FR-030 REST parity).

**Surfaces**

- **FR-027**: System MUST provide a Chat page in the desktop app: a collapsible
  conversation-history list, a new-conversation dialog with an agent picker and a
  per-agent configuration area, a message thread with streamed text (driven by the
  FR-019a live subscription, not by polling), inline expandable tool-call cards, a
  model selector, a composer that **auto-grows** with multi-line input (capped,
  then scrolls internally) and **never locks** (a message sent during a turn
  queues and renders one-per-row as a removable and editable pending item;
  editing pulls it back into the composer and re-queues it at the tail,
  FR-018/FR-018a), and a stop control for an in-flight turn.
- **FR-028**: System MUST add a "Chat" entry to the application sidebar as the
  primary (top-most) navigation item; the existing 002-ui-shell IA is otherwise
  unchanged.
- **FR-029**: The dedicated Settings → Models registry page is **retired**: the
  standalone `ModelConfig`/`chat_models` registry it managed is gone (folded into
  provider connections, spec 011 / ADR-032). Coffer's internal-engine connection
  is now configured on the unified **Settings → LLM Connections** page (spec 011),
  and managed agents pick their connection on the agent detail page.
- **FR-030**: Every chat operation available in the GUI MUST be available through
  the REST API; CLI read operations MUST support `--json`. The model-registry
  CRUD REST and the `coffer model` CLI are **retired** with the `ModelConfig`
  registry (spec 011); only the provider **introspection** routes
  (`list-models`, `test-connection`) remain. (The `coffer chat` CLI was removed
  with the retired built-in chat agent, ADR-024.)

**Observability**

- **FR-031**: System MUST record per-message token usage and surface it in the
  GUI and in CLI `--json` output.
- **FR-032**: System MUST record each completed turn in the audit log with actor
  `agent`; tool invocations the built-in agent makes are recorded in the
  gateway's invocation log under the agent's gateway session.

**Chat surface: channel binding ([ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.md) → [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) → [ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md))**

- **FR-033**: The Chat surface (labelled **Chat**, reverted from _Vault Console_
  per [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md))
  MUST talk **only** to Coffer-managed agents and MUST let the owner observe,
  interrupt, and continue any conversation live, including those the owner drives
  from an IM channel ([ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md)).
  The `builtin` agent MUST NOT be offered as a chat agent; its model is an
  internal-only capability reached through `coffer__*` tools (ADR-024), not a chat
  persona. The Chat surface MUST NOT position itself as a primary in-browser coding
  chat.
- **FR-034**: A conversation MAY carry an optional **channel binding**
  (`channel_name` + `peer_chat_id`) — the return address for relaying the agent's
  output back to the IM app. The conversation history MUST surface whether a
  conversation has a channel binding (a conversation "has a binding" iff
  `channel_name` is set) and which channel it is. The former `origin` (web vs.
  channel) and `peer_display_name` fields are removed
  ([ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md)): under
  the single-owner premise the peer is always the owner, so there is no separate
  peer identity to display.

### Key Entities

- **Agent Provider**: The platform's unit of extension. A provider owns one
  agent type: it has a stable `agent_key`, validates and stores a conversation's
  agent-specific configuration when the conversation is created, builds a
  configured agent adapter for each turn, tears down per-conversation state on
  deletion, and reports whether it is currently available. Providers are held in
  the **agent-provider registry**; the chat surface knows only the registry.
- **Agent Adapter**: One agent's handling of one turn. Given the conversation
  history, it yields a stream of agent events. It is self-contained — it carries
  its own model, tools, and configuration, supplied by its provider when the
  adapter is built.
- **Built-in Agent**: Coffer's single, code-defined general-purpose agent
  ("Coffer Assistant"), delivered as one agent provider + adapter. Identity,
  system-prompt template, default model selection, and tool-iteration limit. Not
  user-editable in v1. `agent_key` = `builtin`.
- **Conversation**: A persisted chat thread. Fields: id, `agent_key`, title,
  optional model override, timestamps. Not a Resource.
- **Message**: One entry in a conversation. Fields: id, conversation ref,
  ordering, role (`user` | `assistant`), ordered content blocks, token usage and
  producing model (assistant only), timestamp.
- **Content Block**: A unit of message content — `text`, `tool_use` (tool name +
  input), or `tool_result` (tool name + output or error).
- **Model**: A user-configured LLM the built-in agent can run on. Fields: id,
  display name, provider type (`anthropic` | `openai` | `ollama`), model id,
  credential reference (cloud), base URL (Ollama / custom), default flag.
- **Agent Event**: A typed event on the conversation's live stream — turn start,
  text delta, tool call, tool result, turn done, turn error, or queue changed
  (`queue_changed`, the conversation-level pending-queue snapshot, ADR-031).

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can register a model, start a
  conversation with the built-in agent, and hold a streamed multi-turn
  conversation in a real browser via `make dev`, without reading source code.
- **SC-002**: A question answerable only from the user's memory or knowledge base
  is answered correctly, with the corresponding tool call visible in the thread.
- **SC-003**: Conversations and messages created in either the GUI or the CLI are
  visible and identical in the other surface, and survive a daemon restart.
- **SC-004**: Every Acceptance Scenario in this spec is covered by at least one
  test marked `acceptance(spec="008-agent-chat", scenario="…")`, and
  `make verify-acceptance` reports zero uncovered scenarios.
- **SC-005**: The full `make verify` suite passes locally and in CI;
  `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-006**: No LLM-provider credential is ever written to the database or to
  logs in plaintext; validated by a dedicated security test.
- **SC-007**: Adding a second agent provider requires no change to the chat
  REST/SSE contract, the conversation/message schema, the turn orchestrator, or
  the chat page — verified by review against the agent-provider registry, the
  `AgentProvider` / `AgentAdapter` interfaces, and the `agent_key` field, and
  demonstrated by a second provider used only in tests.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or
  remote-access requirement. Remote channels (Telegram and similar) are not in
  scope.
- The kind-agnostic Resource framework, audit log, credential module, and the
  MCP gateway with its `BuiltinToolRegistry` and `coffer__` built-in tools —
  from specs 001–006 — are in place on this branch's base.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing,
  design system, and the Settings layout — is in place; the Chat page and the
  Settings → LLM Connections page (spec 011) render within that shell.
- Memory and knowledge-base tools (`coffer__recall`, `coffer__search_knowledge`,
  and siblings) already exist as gateway built-in tools from specs 005–006; this
  spec consumes them and does not redefine them.
- The built-in agent's agentic loop is implemented with the LangGraph framework
  and LLM clients reached through LangChain's provider abstraction; these are
  open-source dependencies and the layered-architecture rule is respected —
  those SDKs stay confined to `infrastructure/chat/`, the turn orchestration and
  the agent-provider registry are `application/`, and `domain/chat/` imports
  neither.
- The interaction model is sequential: one turn per conversation at a time. The
  composer is **not** locked while a turn runs — a message sent during a turn is
  enqueued and runs after it (FR-018, [ADR-031](../../docs/decisions/ADR-031-chat-single-owner-live-mirror.md)).
  Concurrent (overlapping) turns within one conversation are out of scope.
- The agent-provider registry is populated in code at startup; v1 registers one
  provider (the built-in agent). The registry is the seam — populating it from
  user-managed configuration is not in this spec.
- The following are explicitly **out of scope**: user-created or user-edited
  agents; a GUI for managing the agent registry; per-agent capability scoping
  beyond the gateway's existing gating; conversation
  summarisation and export; resuming/continuing a past foreign agent session;
  and any cross-agent raw-transcript browse/search surface (sharing across agents
  is served by distilled memory, [ADR-020](../../docs/decisions/ADR-020-transcript-distillation.md)).
  Remote channels are delivered separately by Spec 009.
- The standalone `ModelConfig`/`chat_models` registry that `Conversation.model_id`
  referenced is **retired** (folded into provider connections, spec 011 /
  ADR-032). `model_id` is now a **vestigial legacy column**, never read by the
  managed-agent turn path: that path uses the agent's own model — the active
  connection's `model` plus the per-conversation `agent_config.model` override
  (PR #170). Coffer's internal engine selects its model from the internal-default
  connection.
