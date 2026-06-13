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
provider. The platform also carries the capabilities an agent needs that the
built-in agent's own gating makes optional — a human-approval channel for tool
calls — and the controls every conversation needs: streamed turns, one
in-flight turn at a time, and user interruption."

This spec turns Coffer from a vault that *stores* AI assets into one that
*uses* them, and it does so as a **platform**, not a single hard-wired feature.
It delivers two things at once:

1. **A chat platform.** A first-class chat surface, persisted multi-conversation
   history, a streamed turn protocol, human-in-the-loop tool approval, and user
   interruption — all expressed against an **agent-provider registry**. An agent
   is reached only through that registry, so adding another kind of agent is a
   new registry entry, not a change to the chat page, the persistence layer, or
   the REST/SSE contract.
2. **Agents on that platform.** Coffer's built-in general-purpose agent,
   "Coffer Assistant" — an in-process agentic loop, driven by the user's own
   MCP servers, skills, memory, and knowledge bases through Coffer's MCP
   gateway, on a user-configured LLM provider — **plus** two CLI-backed agents,
   **Claude Code** and **Codex**, each driven by its installed command-line tool
   in a working directory the user picks per conversation. The CLI agents are
   what keep the seam honest: they are real second and third providers, not a
   promise, and they prove that adding an agent is one registry entry with no
   change to the chat surface, persistence, or the wire contract.

The platform pieces and its agents are co-delivered because a platform with no
agent cannot be exercised, and an agent with no platform cannot be reached.
Every platform capability that the built-in agent does not itself need — the
approval channel above all — still ships complete and is proven end-to-end, so
the seam is real on the day it lands rather than a promise.

## User Scenarios & Testing

### User Story 1 — Configure a model provider before the first chat (Priority: P1)

The built-in agent has no LLM of its own. On first visit to Chat, the user is
pointed at **Settings → Models**, where they register at least one model: choose
a provider (Anthropic, OpenAI, or a local Ollama endpoint), supply the
credential (cloud providers) or base URL (Ollama), and name a model id. Once one
model exists, the built-in agent can be chosen and chat is unlocked.

**Why this priority**: Without a configured model the built-in agent cannot
answer at all. This is the gate to every other scenario that uses it.

**Independent Test**: With a fresh install, open Settings → Models, add an
Anthropic model with a credential, save; observe it listed and marked as the
default; the Chat page stops showing the "no model configured" state.

**Covering scenarios**:
- register a cloud model with a credential
- register a local Ollama model with a base URL and no credential
- reject a model whose required credential or base URL is missing
- the first registered model becomes the default
- register and list models from the command line

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
- the composer is disabled while a turn is streaming and re-enabled when it ends
- an LLM/provider error surfaces in the conversation without crashing the page

---

### User Story 4 — The built-in agent works with the vault (Priority: P1)

The user asks the built-in agent something that needs their own data ("what do
my notes say about OAuth?"). The agent calls tools through Coffer's MCP
gateway — upstream MCP server tools, `coffer__recall`, `coffer__search_knowledge`,
`coffer__load_skill` — and each call appears in the message stream as an inline,
expandable card showing the tool name, status, inputs, and result.

**Why this priority**: This is what makes the built-in agent *Coffer's* agent
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

### User Story 6 — Approve or deny an agent's tool call (Priority: P2)

Some agents must not run a tool until the user says so. When an agent reaches a
tool call that needs permission, the turn pauses and the chat surface shows an
**approval card** naming the tool and its inputs. The user clicks **Allow** or
**Deny**; the agent receives the decision and continues — running the tool on
allow, or treating the denial as the tool's result on deny. Coffer's built-in
agent relies on the gateway's own capability gating and does not pause for
per-call approval; the approval channel is a platform capability that ships
complete for any agent that does.

**Why this priority**: An agent that can act on the user's machine is only safe
if the user can interpose. Building the channel into the platform — rather than
into one agent — is what keeps the seam honest. Not blocking the core loop.

**Independent Test**: Drive a turn with an agent that requests approval for a
tool call; observe the approval card; click Allow; observe the tool run and the
turn finish. Repeat with Deny; observe the agent receive the denial.

**Covering scenarios**:
- an agent turn pauses and emits an approval request the surface renders
- allowing a request lets the agent run the tool and finish the turn
- denying a request returns the denial to the agent as the tool result
- an approval decision for an unknown or already-decided request is rejected
- per-tool approval relay works for SDK-backed Claude Code

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

### User Story 9 — Chat from the command line (Priority: P2)

The user, a developer, talks to the built-in agent without the GUI:
`coffer chat` opens an interactive streaming session; `coffer chat -m "…"` runs
one turn and prints the reply.

**Why this priority**: CLI parity is a standing Coffer convention for developer
surfaces. Not blocking the GUI deliverable.

**Independent Test**: Run `coffer chat -m "say hello"` and observe a streamed
reply on stdout; run `coffer chat`, hold a two-turn conversation, exit, and
confirm the conversation appears in the GUI history list.

**Covering scenarios**:
- `coffer chat -m` runs a single turn and prints the reply
- `coffer chat` holds an interactive multi-turn session
- CLI conversations are the same entities the GUI lists

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
  links to Settings → Models; it does not show a generic error or a dead input.
  Choosing the built-in agent with no model configured fails the turn with the
  no-model state, not a crash.
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
- **Approval decision with no matching request**: a decision posted for a
  request id that does not exist, or one already decided, is rejected; the turn
  is unaffected.
- **A turn is interrupted while waiting for approval**: the pending approval
  wait is cancelled along with the turn; whatever the agent produced before the
  pause is preserved per the interruption rule below.
- **Conversation longer than the model context window**: the built-in agent
  sends the most recent history that fits within a context budget (approximated
  by a character budget, ~4 chars/token); older turns are omitted from the model
  input with a marker, while the full conversation remains stored.
- **Second message sent while a turn is streaming**: rejected; the composer is
  disabled for the duration of the in-flight turn.
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

### Scenario: register a model provider

- **Given** a running daemon with no model configured,
- **When** the user registers a model with a provider, model id, and the
  credential or base URL its provider requires,
- **Then** the model is persisted, the first such model is marked default, and
  the Chat page no longer reports "no model configured".

### Scenario: reject an incomplete model

- **Given** a running daemon,
- **When** the user registers a cloud model without a credential, or an Ollama
  model without a base URL,
- **Then** registration is rejected with a message naming the missing field and
  nothing is persisted.

### Scenario: list available agents

- **Given** a running daemon,
- **When** the user asks the platform which agents it offers,
- **Then** the built-in agent is listed with a display name and an availability
  flag, and the list is reachable from the REST API.

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
- **When** the user sends a message,
- **Then** the assistant reply streams incrementally, completes, and is persisted
  as a message on that conversation.

### Scenario: reply survives a restart

- **Given** a conversation with a completed assistant reply,
- **When** the daemon restarts and the user reopens the conversation,
- **Then** every message is present and unchanged.

### Scenario: the agent calls a vault tool

- **Given** a memory store containing a record that answers a question,
- **When** the user asks that question,
- **Then** the turn includes a `coffer__recall` tool call rendered as an
  inline expandable card, and the answer is grounded in the record.

### Scenario: skills are reachable as tools

- **Given** at least one valid skill in the vault,
- **When** the agent lists available tools,
- **Then** `coffer__list_skills` and `coffer__load_skill` are present and
  `coffer__load_skill` returns the skill's content.

### Scenario: a failed tool call does not break the turn

- **Given** a tool that returns an error when invoked,
- **When** the agent calls it during a turn,
- **Then** the tool card shows a failed state, the error is returned to the agent
  as a tool result, and the turn still completes with an assistant message.

### Scenario: tool-iteration limit ends the turn cleanly

- **Given** a turn that would call tools indefinitely,
- **When** the iteration limit is reached,
- **Then** the turn ends cleanly — a normal turn completion (`turn_done`, not
  `turn_error`), carrying the stop reason `max_iterations` — and the
  conversation stays usable.

### Scenario: an agent turn pauses for human approval

- **Given** an agent whose turn requests approval before running a tool,
- **When** the turn reaches that tool call,
- **Then** the stream carries an approval request the chat surface renders as a
  card, the turn waits, and on the user allowing it the agent runs the tool and
  the turn completes.

### Scenario: a denied tool call is reported to the agent

- **Given** an agent turn paused on an approval request,
- **When** the user denies it,
- **Then** the denial is delivered to the agent as the tool's result and the
  turn completes without running the tool.

### Scenario: per-tool approval relay works for SDK-backed Claude Code

- **Given** a turn driven by the SDK-backed Claude Code provider that requests a
  tool call requiring approval,
- **When** the `can_use_tool` callback fires and the user submits an allow or
  deny decision through the platform's approval channel,
- **Then** on allow the SDK callback resolves to `PermissionResultAllow` and the
  turn completes with `TurnDone`; on deny the callback resolves to
  `PermissionResultDeny` (carrying the denial message) and the turn also
  completes cleanly with `TurnDone`.

### Scenario: per-tool approval relay works for app-server-backed Codex

- **Given** a turn driven by the app-server-backed Codex provider, where Codex
  sends an `item/commandExecution/requestApproval` or
  `item/fileChange/requestApproval` request mid-turn,
- **When** the platform emits an `ApprovalRequest` event and the user submits an
  allow or deny decision through the platform's approval channel,
- **Then** on allow the adapter writes `{decision: "accept"}` back to Codex and
  the turn proceeds and completes with `TurnDone`; on deny the adapter writes
  `{decision: "decline"}` back to Codex and the turn also completes cleanly
  with `TurnDone`.

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

### Scenario: composer locked during a streaming turn

- **Given** a turn is streaming,
- **When** the user attempts to send another message in the same conversation,
- **Then** the send is rejected until the turn ends.

### Scenario: model selection is recorded

- **Given** two configured models,
- **When** the user sets a conversation's model and sends a message,
- **Then** the turn runs on the chosen model and the assistant message records
  which model produced it.

### Scenario: command-line parity for chat and models

- **Given** a running daemon,
- **When** the user runs `coffer model add` and `coffer model list --json`, then
  `coffer chat -m "…"` and an interactive `coffer chat` session,
- **Then** the model registers and lists, a streamed reply is produced, and CLI
  conversations appear in the same history list the GUI shows.

### Scenario: no-model empty state

- **Given** a running daemon with no model configured,
- **When** the user opens the Chat page,
- **Then** an actionable empty state linking to Settings → Models is shown and no
  message can be sent.

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
  is self-contained: given only the conversation history and an approval
  channel, it yields a stream of typed turn events. The adapter carries its own
  model, tools, and configuration; the orchestrator MUST NOT inject them. The
  platform ships three agents behind this seam — the built-in agent plus two
  CLI-backed agents (Claude Code, Codex) — so the seam is validated by real
  additional providers, not a single occupant.
- **FR-005a**: System MUST ship CLI-backed agent providers for Claude Code and
  Codex. Each is configured per conversation by a working directory (its
  `agent_config.cwd`), which MUST be an existing directory or the configuration
  is rejected. A CLI agent's availability MUST reflect whether its command-line
  binary is resolvable on the daemon's PATH; an unavailable agent is listed but
  not selectable. A CLI turn MUST run the tool in that directory, stream its
  line-delimited JSON output mapped onto the platform's turn events, and persist
  the upstream session id so the next turn continues the same session. Claude
  Code is driven via the Claude Agent SDK: each `can_use_tool` permission
  callback is bridged through the platform's human-approval channel
  (`can_use_tool` → `ApprovalRequest` event → allow/deny decision → SDK result),
  so per-call tool approval works end-to-end for SDK-backed Claude Code. Codex
  is driven via `codex app-server` (JSON-RPC 2.0 over stdio, NDJSON-framed):
  server→client approval requests (`item/commandExecution/requestApproval` and
  `item/fileChange/requestApproval`) are bridged through the same
  human-approval channel (allow → `"accept"` decision, deny → `"decline"`
  decision), so per-tool approval works end-to-end for app-server-backed Codex
  through the same platform channel Claude Code uses.

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

**Turn lifecycle: streaming, approval, interruption**

- **FR-018**: System MUST allow only one in-flight turn per conversation and
  reject a second message until the current turn ends.
- **FR-019**: System MUST stream a turn to the client as a sequence of typed
  events covering, at minimum, text deltas, tool calls, tool results, approval
  requests, turn completion, and turn error.
- **FR-020**: The platform MUST provide a **human-approval channel**: an agent
  turn can emit an approval request that pauses the turn; the user submits an
  allow/deny decision through a dedicated endpoint; the decision is delivered to
  the waiting turn. A decision for an unknown or already-decided request MUST be
  rejected. This channel MUST ship and be verified end-to-end even though the
  built-in agent does not use it.
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

**Surfaces**

- **FR-027**: System MUST provide a Chat page in the desktop app: a collapsible
  conversation-history list, a new-conversation dialog with an agent picker and a
  per-agent configuration area, a message thread with streamed text, inline
  expandable tool-call cards, and approval cards, a model selector, a composer,
  and a stop control for an in-flight turn.
- **FR-028**: System MUST add a "Chat" entry to the application sidebar as the
  primary (top-most) navigation item; the existing 002-ui-shell IA is otherwise
  unchanged.
- **FR-029**: System MUST provide a Settings → Models page covering every model
  registration operation.
- **FR-030**: Every chat and model operation available in the GUI MUST be
  available through the REST API, and the model operations plus `coffer chat`
  MUST be available as CLI commands; CLI read operations MUST support `--json`.

**Observability**

- **FR-031**: System MUST record per-message token usage and surface it in the
  GUI and in CLI `--json` output.
- **FR-032**: System MUST record each completed turn in the audit log with actor
  `agent`; tool invocations the built-in agent makes are recorded in the
  gateway's invocation log under the agent's gateway session.

### Key Entities

- **Agent Provider**: The platform's unit of extension. A provider owns one
  agent type: it has a stable `agent_key`, validates and stores a conversation's
  agent-specific configuration when the conversation is created, builds a
  configured agent adapter for each turn, tears down per-conversation state on
  deletion, and reports whether it is currently available. Providers are held in
  the **agent-provider registry**; the chat surface knows only the registry.
- **Agent Adapter**: One agent's handling of one turn. Given the conversation
  history and an approval channel, it yields a stream of agent events. It is
  self-contained — it carries its own model, tools, and configuration, supplied
  by its provider when the adapter is built.
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
- **Agent Event**: A typed event in a streamed turn — text delta, tool call,
  tool result, approval request, turn done, or turn error.
- **Approval Request / Approval Decision**: The two halves of the human-approval
  channel. A request names a tool call awaiting permission; a decision is the
  user's allow/deny answer carried back to the waiting turn.

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
- **SC-008**: The human-approval channel works end-to-end — an agent turn that
  emits an approval request pauses, the decision endpoint delivers the user's
  answer, and the turn continues — and a running turn can be stopped with its
  partial output preserved; both are proven by acceptance tests. The approval
  channel is additionally exercised by a real provider (SDK-backed Claude Code),
  not only a scripted fake, confirming that per-call tool approval works
  end-to-end for production agent adapters.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or
  remote-access requirement. Remote channels (Telegram and similar) are not in
  scope.
- The kind-agnostic Resource framework, audit log, credential module, and the
  MCP gateway with its `BuiltinToolRegistry` and `coffer__` built-in tools —
  from specs 001–006 — are in place on this branch's base.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing,
  design system, and the Settings layout — is in place; the Chat page and the
  Settings → Models page render within that shell.
- Memory and knowledge-base tools (`coffer__recall`, `coffer__search_knowledge`,
  and siblings) already exist as gateway built-in tools from specs 005–006; this
  spec consumes them and does not redefine them.
- The built-in agent's agentic loop is implemented with the LangGraph framework
  and LLM clients reached through LangChain's provider abstraction; these are
  open-source dependencies and the layered-architecture rule is respected —
  those SDKs stay confined to `infrastructure/chat/`, the turn orchestration and
  the agent-provider registry are `application/`, and `domain/chat/` imports
  neither.
- The interaction model is sequential: one turn per conversation at a time, the
  composer locked while a turn runs. Concurrent turns within one conversation
  are out of scope.
- The agent-provider registry is populated in code at startup; v1 registers one
  provider (the built-in agent). The registry is the seam — populating it from
  user-managed configuration is not in this spec.
- The following are explicitly **out of scope**: user-created or user-edited
  agents; a GUI for managing the agent registry; remote channels; per-agent
  capability scoping beyond the gateway's existing gating and the approval
  channel; conversation summarisation, search, and export.
