# Chat

## Purpose
A turn has to reach an agent the same way whoever asked for it — an IM channel,
the web page, anything later. Chat is the **turn platform**: the agent-provider
registry, the agent adapters, the conversation and message store, the turn
lifecycle with its pending queue, the typed event stream — and the **web Chat
page** that drives all of it, so the owner can watch and steer from a browser
what they started on a phone. The platform and the page are one capability
because the page owns no state of its own: every row it renders and every
control it offers belongs to the platform underneath it. A channel
([channels](../channels/spec.md)) is the platform's other client, reaching it
through the same seams; an agent cannot tell which window a turn arrived
through. The decision the page rests on is recorded in
[Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md).
Chat talks to **managed** agents only — the former `builtin` chat persona is
retired, see
[Built-in Agent Is Internal](../../../docs/decisions/builtin-agent-is-internal-capability.md).

What the platform promises as outcomes: adding a third agent takes one registry
entry and one adapter and touches no conversation schema, orchestrator code or
client; a turn started from any surface is observable, interruptible and
continuable from every other surface with no per-surface branch on the turn
path; no turn ever ends silently, and a daemon killed mid-turn leaves no
conversation showing a reply that will never arrive; and from a fresh install
with one managed agent present, a user can open the Chat page, send a first
message and receive a streamed reply without configuring a Coffer LLM
connection first.

Known boundaries. **The platform ships no CLI, and that is a known gap**: no
`chat` command group is registered, so conversations, the pending queue and the
agent-provider registry are reachable over REST and from the web page only,
against the REST/CLI parity rule in [`.agents/openspec.md`](../../../.agents/openspec.md).
Two route prefixes serve this one capability: `/api/v1/chat` carries everything
about a conversation, and `/api/v1/agent-providers` carries the registry itself,
because its subject is the adapters that can drive a turn and not the `agent`
resource rows `/api/v1/agents` serves. The model catalogue is the agent kind's
answer ([agent-registry](../agent-registry/spec.md)), published into chat's
dependencies at the composition root as a port, because the import-linter fence
forbids chat from importing the agent kind. Chat state is single-daemon and
does not converge across machines. A channel keeps its own table mapping a chat
thread to a conversation id; that pointer is soft, may dangle, and chat neither
maintains nor validates it. Attachment bytes are not chat's storage: the media
directory and its prune belong to whoever downloaded the file
([channels](../channels/spec.md)); chat persists only the reference and reads
the bytes at turn time.

## Requirements

### Requirement: Route every turn through the agent-provider registry
A turn MUST reach an agent only through an **agent-provider registry**: a turn
is run, a conversation is initialised, and a conversation's agent state is torn
down by asking the registry for the agent named on the conversation. Adding
another agent MUST be a new registry entry only — no change to the
conversation/message schema, the turn orchestrator, or any client of the
platform. No client branches per agent.

#### Scenario: a turn reaches the agent the conversation names
- **GIVEN** a registry holding two agents, each with its own adapter
- **WHEN** a conversation is created on the second agent and a turn is started on it
- **THEN** the second agent's provider builds the adapter that runs the turn
- **AND** the first agent's provider is never asked for an adapter

### Requirement: Record the agent on each conversation
Each conversation MUST record which agent it belongs to via an `agent_key`,
plus an opaque, agent-specific configuration that the named agent validates and
persists. An `agent_key` no agent provides MUST be rejected, and an invalid
configuration MUST be rejected as a domain error — both before anything is
written. This is what a channel binding resolves against on the peer's first
message.

#### Scenario: choose an agent when starting a conversation
- **GIVEN** a running daemon,
- **WHEN** a conversation is created for a named managed agent with a working
  directory,
- **THEN** the conversation records that agent and its configuration.

#### Scenario: reject an unknown agent or invalid agent configuration
- **GIVEN** a running daemon,
- **WHEN** a conversation is created for an `agent_key` no agent provides, or
  with a working directory that is not an existing directory,
- **THEN** each is rejected as a domain error and nothing is persisted. An
  *absent* working directory is not invalid — it defaults to the Coffer-managed
  workspace.

### Requirement: Expose the registered agents and their models
The platform MUST expose its registered agents — each with a stable key, a
display name, and a current availability flag — over the REST API, so a caller
offers only agents that exist and marks the ones whose CLI is absent on this
host. It MUST likewise expose, per agent, the models that agent can be put on;
the route is the platform's, while the catalogue behind it is the agent kind's
answer ([agent-registry](../agent-registry/spec.md)), reaching this route
through a port rather than an import.

#### Scenario: list available agents
- **GIVEN** a running daemon,
- **WHEN** the platform is asked which agents it offers,
- **THEN** the managed agents (`claude_code`, `codex`) are listed, each with a
  display name and an availability flag, the `builtin` agent is **not** among
  them ([Built-in Agent Is Internal](../../../docs/decisions/builtin-agent-is-internal-capability.md)),
  and the list is reachable from the REST API.

### Requirement: Distinguish a missing agent path from a bad turn body
An `agent_key` no provider answers for MUST be **404** on a subresource path —
asking for the models of an agent that does not exist is a missing path — and
**400** `UNKNOWN_AGENT` when it names the agent a turn was to run on, where the
path exists and the body is wrong. The two are distinct answers to distinct
questions and MUST NOT be collapsed into one.

#### Scenario: an unknown agent is a missing path, not a bad turn
- **GIVEN** a running daemon,
- **WHEN** the models of an `agent_key` no provider answers for are requested,
- **THEN** the answer is 404, while the same key named as a turn's agent is
  rejected as `UNKNOWN_AGENT` with 400.

### Requirement: Keep each agent adapter self-contained
An agent is addressed for a turn through an **agent adapter** that is
self-contained: given only the conversation history, it yields a stream of
typed turn events. The adapter carries its own model, tools, and configuration;
the orchestrator MUST NOT inject them.

#### Scenario: the orchestrator hands an adapter only the history
- **GIVEN** a conversation whose agent's adapter records what it is called with
- **WHEN** a turn runs on that conversation
- **THEN** the adapter receives the conversation history and the turn's attachments
- **AND** it is handed no model, tool list or configuration by the orchestrator

### Requirement: Ship Claude Code and Codex subprocess providers
System MUST ship subprocess-backed agent providers for Claude Code and Codex.
Each runs in a working directory (its `agent_config.cwd`); when a turn supplies
none, the provider MUST default to the Coffer-managed workspace
`~/.coffer/workspace` (created on first use) rather than reject the turn — so a
client with no configured workspace works out of the box. An
explicitly-supplied cwd MUST be an existing directory or the configuration is
rejected. Availability MUST reflect whether the agent's binary is resolvable on
the daemon's PATH; an unavailable agent is listed but not selectable.

A turn MUST stream the tool's line-delimited JSON output mapped onto the
platform's turn events, and persist the upstream session id so the next turn
continues the same session. Claude Code is driven through the Claude Agent SDK
and Codex through `codex app-server` (JSON-RPC 2.0 over stdio, NDJSON-framed);
both run with full permissions — owner pairing
([channels](../channels/spec.md)) is the security gate.

Both MUST emit the reply as text increments *as it is written*, not as one
block at the end of the turn, otherwise a live surface has nothing to grow and
a reply lands all at once after a long silence. The Claude Agent SDK does this
only when asked (`include_partial_messages`), and it then delivers BOTH the
increments and the finished assistant message, so the adapter MUST subtract
what it already emitted and send the reply exactly once.

#### Scenario: a streamed reply reaches the consumer exactly once
- **GIVEN** a Claude Code turn whose SDK delivers the reply as streamed increments and then as the finished assistant message
- **WHEN** the adapter maps the turn onto platform events
- **THEN** the reply arrives as one text delta per increment, in order
- **AND** the joined deltas equal the reply once, not doubled by the finished message
- **AND** the stream ends with a terminal turn-done

### Requirement: End every adapter stream with a terminal event
The adapter seam is a contract in both directions. An adapter MUST yield a
terminal turn-done or turn-error event before its iterator ends, and on
cancellation MUST clean up and re-raise rather than swallow it — the platform's
interrupt, delete and idle-watchdog paths all arrive that way. An iterator that
simply stops is not a completed turn (see "Keep partial output when a turn is
interrupted or fails").

#### Scenario: an agent stream that ends without a terminal is a turn error
- **GIVEN** an agent whose event stream ends without a completion event,
- **WHEN** the turn is driven,
- **THEN** exactly one terminal event follows, a `stream_ended` turn error, with
  the text streamed before the cut delivered ahead of it

### Requirement: Record the model an adapter reports
An adapter MAY name the model the turn actually ran on; where it does, the
platform MUST record that model on the assistant message. It is optional, so an
adapter bringing no Coffer-registered model is still a valid adapter — the
platform reads it best-effort and never requires it of the seam.

#### Scenario: model selection is recorded
- **GIVEN** a conversation whose model has been set,
- **WHEN** a turn completes,
- **THEN** the assistant message records the model that produced it.

### Requirement: Retry a forgotten resume id once as a fresh session
A resume id the agent no longer recognises MUST NOT fail the turn. Where
connecting with a stored upstream session id fails and a session id was in
play, the platform MUST retry the turn **once** as a fresh session; only a
second failure becomes a turn error. A prior turn can leave an id the agent's
own CLI later refuses, and without this the conversation would be permanently
unusable rather than merely discontinuous.

#### Scenario: a resume id the agent has forgotten retries once as a fresh session
- **GIVEN** a conversation carrying an upstream session id the agent no longer
  recognises,
- **WHEN** a turn is started,
- **THEN** the connect is retried once with no session id and the turn runs; a
  second failure is reported as a turn error rather than retried again.

### Requirement: Tell the agent which model it is on
Every turn MUST carry an authoritative note telling the agent which model
Coffer put it on and what else it could be switched to. The agent cannot see
Coffer's choice and, asked, invents one; the note therefore says it outranks
the agent's own guess, names the leading few ids and points at the picker for
the rest rather than spending prompt on the whole catalogue. Where Coffer set
no override, the note MUST say the agent's own default is in use rather than
name a model.

#### Scenario: every turn tells the agent which model it is on
- **GIVEN** a conversation whose model has been set,
- **WHEN** a turn is started,
- **THEN** the agent's system context carries an authoritative note naming that
  model and listing what else it could be switched to; with no override set the
  note says the agent's own default is in use and names no model.

### Requirement: Persist conversations and messages in SQLite
System MUST persist conversations and their messages in SQLite as the system of
record; they are not Resources of the kind-agnostic Resource framework. A
message MUST store its role and an ordered list of content blocks of types
`text`, `tool_use`, `tool_result`, and `attachment` (see "Re-materialise
attachments from persisted history"); assistant messages MUST also store token
usage and the model that produced them when the agent reports one.

A conversation opens under a placeholder title, which System MUST replace with
the text of its first user message (truncated); once the owner has named a
conversation themselves, System MUST NOT overwrite that name — an explicit
rename outranks the generated one. The name MUST come from the part of that
message the person actually wrote, which a client that folds context blocks
into its turns passes down explicitly; the platform MUST NOT recognise any
client's block format itself. Where the person wrote nothing at all (a photo or
a file on its own), the attachment filenames name the conversation; where there
is nothing nameable at all, the conversation keeps its placeholder title rather
than being named after boilerplate.

#### Scenario: reply survives a restart
- **GIVEN** a completed turn,
- **WHEN** the daemon is restarted and the conversation is read back,
- **THEN** the assistant reply is there — the message store, not the live
  stream, is the system of record.

#### Scenario: a conversation the owner named keeps its name
- **GIVEN** a conversation the owner has renamed,
- **WHEN** its first user message arrives,
- **THEN** the conversation keeps the name the owner gave it, and only a
  conversation still under its placeholder title is named from its first
  message.

#### Scenario: token usage is recorded on the assistant message
- **GIVEN** a turn that completes,
- **WHEN** the turn ends,
- **THEN** the assistant message records the turn's token usage.

### Requirement: Keep a turn's record in its conversation, not the audit log
A turn's own record is the conversation it ran in. The user message, the
assistant message, its tool-call and tool-result blocks, its model and its
token usage are all persisted (see "Persist conversations and messages in
SQLite") and readable from the REST API and the Chat page, so "which agent did
what" is answerable after the fact from the timeline rather than from a second
ledger. Turn activity MUST therefore NOT be written to the audit log: a turn is
neither irreversible nor security-sensitive nor invisible afterwards, and an
audit row per turn would duplicate the timeline while diluting a log whose
value is that everything in it changed who may do what.

#### Scenario: a turn is recorded in its conversation and not in the audit log
- **GIVEN** a conversation stored in a real database and an agent that calls a tool while answering
- **WHEN** a turn runs to completion on it
- **THEN** the conversation holds the user message and an assistant message carrying the tool-call and tool-result blocks, the model and the token usage
- **AND** the audit log holds no row for the turn

### Requirement: Bound turn context to the most recent 200 messages
A turn MUST be given only the most recent 200 messages as context. The adapters
resume the agent's own session, which already holds the conversation; the
history the platform passes is what a fresh session or a path-native agent
gets, and the recent rows are the ones that matter for it. A conversation of
thousands of messages MUST NOT be loaded whole on every turn.

#### Scenario: a long conversation is not loaded whole
- **GIVEN** a conversation holding more than two hundred messages,
- **WHEN** a turn is started,
- **THEN** the adapter is given the most recent two hundred and no more.

### Requirement: List conversations by latest activity
Conversations MUST list newest-activity first, and a conversation's activity
timestamp MUST be bumped both when a turn **starts** and when it **finalises**
— a long turn moves its conversation to the top of the list when it begins, and
is still ordered correctly when it ends. Active and archived are two listings,
never one list with a flag every caller must remember.

#### Scenario: the conversation list is ordered by activity, not by creation
- **GIVEN** two conversations created in order,
- **WHEN** a turn starts on the older one and then completes,
- **THEN** it heads the active listing both while the turn runs and after it
  ends.

### Requirement: Require every writer to name the agent
`agent_key` MUST have no storage-level default. Every writer names the agent
explicitly; an absent one is a programming error rather than a fallback,
because a default could only ever mint a conversation routed to an agent that
has since been withdrawn — a row no turn can run.

#### Scenario: a conversation row with no agent is refused by the store
- **GIVEN** a database migrated to the current schema
- **WHEN** a conversation row is inserted without an `agent_key`
- **THEN** the insert is refused rather than filled with a default agent
- **AND** the `agent_key` column declares no default value

### Requirement: Archive and delete idle conversations on a retention schedule
Conversations MUST follow a two-stage, retention-managed lifecycle, both
windows configurable by the owner: the retention worker auto-archives a
conversation with no new message for the auto-archive window (default 7 days),
then deletes archived conversations and their messages the configured number of
days after archiving (default 30 days). Either window may be set to
keep-forever to disable that stage. Auto-archiving is reversible; only deletion
is destructive.

#### Scenario: an idle conversation is archived, then deleted with its messages
- **GIVEN** the default retention windows, a conversation idle for longer than the auto-archive window, and an archived conversation with messages archived longer ago than the delete window
- **WHEN** the retention worker prunes
- **THEN** the idle conversation is archived but kept
- **AND** the long-archived conversation and its messages are deleted
- **AND** with the auto-archive window set to keep-forever, an idle conversation is left unarchived

### Requirement: Register conversation retention in the framework registry
Both windows MUST be registered as ordinary entries of the framework's own
retention registry rather than as a worker private to chat — the first sets a
column on the conversation, the second deletes the row — so they are tuned on
the same surface as every other retained table. Deleting a conversation MUST
take its messages with it, whether the deletion came from retention or from the
owner.

#### Scenario: chat's retention windows are tuned beside every other table
- **GIVEN** the daemon's composed retention registry
- **WHEN** its retention policies are seeded and listed
- **THEN** the auto-archive window (7 days, archiving by setting a column) and the delete window (30 days) appear as two ordinary entries beside the log tables
- **AND** an owner who deletes a conversation leaves none of its messages behind

### Requirement: Queue messages sent during a turn
System MUST process at most one in-flight turn per conversation without
rejecting a message sent while a turn is running: such a message is enqueued on
a per-conversation **pending queue**. When the in-flight turn ends, System MUST
dequeue the head, commit it as the next user message, and run its turn —
sequential FIFO, one turn per queued message, never coalesced. A pending
message is not committed to the message sequence until its turn starts. The
queue is in-memory, so a daemon restart drops what has not yet been committed.
Every client feeds this one queue: a message arriving from a channel while a
turn is in flight is shown in the page's pending rows and counted by the
channel's own status command, and the two surfaces drain one FIFO per
conversation — no client keeps a buffer of its own.

#### Scenario: second message queues during a streaming turn
- **GIVEN** a turn is streaming,
- **WHEN** another message is sent on the same conversation,
- **THEN** it is accepted and enqueued rather than rejected, and runs as its own
  turn after the current one ends.

#### Scenario: a queued message runs after the current turn
- **GIVEN** a message queued behind a running turn,
- **WHEN** that turn completes,
- **THEN** the queued message is committed as the next user message and its turn
  runs, one turn per queued message.

#### Scenario: a channel message waits in the conversation's own queue
- **GIVEN** a turn running on a paired channel's conversation, with a web tab
  subscribed to it,
- **WHEN** the peer sends more messages and the web sends one too,
- **THEN** they wait on the one pending queue in arrival order — the web's
  pending chips show the channel's messages — and run as consecutive turns

### Requirement: Pause the pending queue on interrupt
Interrupting a turn MUST also **pause** the pending queue: the current turn
stops with its partial output kept, and queued messages are held rather than
auto-run until the owner resumes them. The next message from any surface
resumes the held queue.

#### Scenario: a stop from the chat holds the queued messages
- **GIVEN** a turn running with a channel message queued behind it,
- **WHEN** the peer sends `/stop`,
- **THEN** the turn ends as interrupted and the queued message is held, and the
  peer's next message resumes the queue in order

#### Scenario: interrupting a turn pauses the pending queue
- **GIVEN** a running turn with messages queued behind it,
- **WHEN** the turn is interrupted,
- **THEN** the current turn stops, and the queued messages are held rather than
  auto-run until they are resumed or dropped.

### Requirement: Keep partial output when a turn is interrupted or fails
An interrupted or failed turn — user interrupt, adapter failure, timeout, or
daemon restart — MUST leave its partial assistant message persisted rather than
discarded: marked `complete` when the owner interrupted it, and `failed` when the
adapter failed, the turn timed out, or the daemon restarted under it. Stopping a turn is distinct from discarding the conversation, which
throws the turn away.

Two failures the platform detects itself, agent-agnostically: an agent whose
event stream ends without a terminal event (its process died or lost its
connection mid-turn) MUST be reported as a turn error (`stream_ended`), never
as a completed turn — a tick on a reply cut mid-sentence is a lie; and a turn
that produces no event for the idle window
(`COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300; `0` disables the watchdog)
MUST be cancelled with a `turn_timeout` error, its agent process stopped
through the adapter's own cancellation path. In both cases whatever text
streamed before the failure is kept on the assistant message (marked failed)
and delivered ahead of the notice.

#### Scenario: stop a running turn
- **GIVEN** a turn that has streamed partial text and is still running,
- **WHEN** it is interrupted,
- **THEN** the stream ends with a terminal turn-done carrying stop reason
  `interrupted`, and the partial assistant message is persisted as complete.

#### Scenario: a silent turn is cancelled by the idle watchdog
- **GIVEN** an agent that streams part of a reply and then produces nothing,
- **WHEN** the idle window passes,
- **THEN** the turn ends with a `turn_timeout` error, the agent's cancellation
  path runs, and the partial reply is kept on a message marked failed

#### Scenario: an errored turn still delivers what it streamed
- **GIVEN** a turn that streamed text before failing,
- **WHEN** the channel renders it,
- **THEN** the chat receives the text, then the error notice, then the failed
  summary

### Requirement: Sweep streaming rows left by a crashed daemon
A `streaming` placeholder assistant row MUST be written **before** the first
event of a turn and finalised in place when the turn ends — one row, never a
duplicate. A daemon that dies mid-turn therefore leaves a row saying so, and a
**startup sweep** MUST flip every lingering `streaming` row to `failed` as the
daemon comes up, so no conversation reopens showing a reply that will never
arrive.

#### Scenario: a crashed turn leaves no message stuck streaming
- **GIVEN** an assistant row left in `streaming` by a daemon that died mid-turn,
- **WHEN** the daemon starts again,
- **THEN** the startup sweep flips that row to `failed`, and the conversation
  reopens showing a failed reply rather than one still arriving.

### Requirement: Hold a queued turn that fails to start
A queued turn that fails to **start** MUST NOT vanish and MUST NOT spin. The
platform puts the message back at the **head** of the queue, pauses the queue,
and reports the failure as a turn error on the conversation's event stream —
and, for a client that has no queue rows to look at, hands its renderer a
stream carrying that failure and ending, so the failure is heard rather than
inferred from silence. The owner resumes the queue after fixing the cause.

#### Scenario: a queued turn that fails to start is held, not lost
- **GIVEN** a message at the head of the pending queue whose turn cannot be
  started,
- **WHEN** the platform tries to advance the queue,
- **THEN** the message is put back at the head, the queue is paused, a turn
  error is published, and the message is still there when the owner resumes.

### Requirement: Reconcile a replaced queue against existing entries
Replacing the pending queue MUST reconcile the new ordered texts against the
existing entries, reusing an entry for each text it still contains (first
unused match wins). A queue reordered or partly dropped from the page therefore
keeps each surviving message's attachments and its originating client's
renderer; only a text that was not queued before becomes a new, bare entry.

#### Scenario: a reordered queue keeps each message's attachments
- **GIVEN** a pending queue holding messages that carry attachments,
- **WHEN** the queue is replaced with the same texts in a different order,
- **THEN** each surviving message keeps its attachments and its originating
  client's renderer, and only a text that was not queued before becomes a new
  entry.

### Requirement: Release turn state nobody needs
Per-conversation turn state — the event bus, the in-flight turn, the pending
queue and its pause flag — is **process-global and single-daemon** by design,
one state per conversation. A state MUST exist only while something needs it (a
turn in flight, a message waiting, or a subscriber attached) and MUST be
released otherwise, so a daemon that has served ten thousand conversations does
not carry ten thousand buses.

#### Scenario: turn state is released when nothing needs it
- **GIVEN** a conversation whose turn has ended, with no queued message and no
  subscriber attached,
- **WHEN** the platform settles,
- **THEN** that conversation's turn state is dropped rather than retained for
  the daemon's lifetime.

### Requirement: Express a turn as typed events
System MUST express a turn as a sequence of typed events covering, at minimum,
turn start, text deltas, tool calls, tool results, turn completion, turn error,
and pending-queue change.

#### Scenario: send a message and receive a streamed reply
- **GIVEN** a conversation on a registered agent,
- **WHEN** a turn is started,
- **THEN** the turn's events stream in order — start, text deltas, completion —
  and the assistant reply is persisted.

### Requirement: Replay the in-flight turn to late subscribers
System MUST publish those events on a per-conversation in-process bus that any
number of subscribers may attach to. On attach, if a turn is in flight the bus
MUST replay the current turn's events so a late subscriber catches up, then
stream live. A turn runs as a detached task, so it survives the subscriber that
started it going away — which is why a reply completes and is persisted even
when a client's connection drops mid-turn.

#### Scenario: observe a turn started from another surface
- **GIVEN** a turn already running on a conversation,
- **WHEN** a second subscriber attaches to that conversation's event bus,
- **THEN** it receives the current turn's events from the beginning and then
  follows live, so a subscriber that arrives mid-turn misses nothing.

### Requirement: Use the wire event name as the type discriminator
Each event's `type` discriminator MUST be the event name on the wire, verbatim
— `turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`,
`turn_error`, `queue_changed`. One vocabulary, so a client dispatches on the
event name it receives without a translation table that can drift from the
platform's own names.

#### Scenario: each event is named on the wire by its own type
- **GIVEN** a subscriber attached to a conversation's event stream
- **WHEN** a turn streams its events to it
- **THEN** every server-sent event is named exactly by its payload's `type`
- **AND** the platform's event types are exactly `turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`, `turn_error` and `queue_changed`

### Requirement: Replay without double-rendering
Replay MUST NOT double-render. The queue-changed event is a conversation-level
snapshot, so the bus replays only the **latest** one rather than its history;
and the turn's replay buffer MUST be dropped when the turn ends, because from
that moment the content is persisted and a late subscriber loads it from
history instead.

#### Scenario: a completed turn is not replayed on top of its persisted rows
- **GIVEN** a turn that has completed,
- **WHEN** a subscriber attaches afterwards,
- **THEN** it receives the latest pending-queue snapshot and no turn content,
  because that content is now loaded from history.

### Requirement: Show every conversation on the Chat page
The web UI MUST carry a **Chat page**: two columns, the conversation list on
the left and the selected conversation's message thread with its draft surface
on the right. The list MUST show every conversation in the vault whatever
opened it — a conversation an IM channel created is listed, readable,
watchable, and continuable from the page, and carries a badge naming the
channel it is also reachable on. There is no web-only conversation kind: the
page and the channel are two windows onto one timeline, driven by one owner,
and an agent cannot tell which window a turn arrived through.

#### Scenario: a channel's conversation is listed beside the web's with a badge
- **GIVEN** one conversation started on the web page and one opened by an IM channel
- **WHEN** the Chat page's conversation list renders
- **THEN** both conversations are listed
- **AND** only the channel's conversation carries a badge naming its channel

### Requirement: Put the open conversation in the URL
The open conversation MUST be part of the URL (`/chat/:id`), so a refresh, a
deep link and a second tab all reopen the same thread. A link to a conversation
that no longer exists MUST say so explicitly, with a way back to a new draft —
never drop silently into the draft surface as though the link had been to
nothing.

#### Scenario: a stale conversation link says so
- **GIVEN** a link to a conversation that has been deleted,
- **WHEN** it is opened,
- **THEN** the page says the conversation is gone and offers a way to start a
  new one, rather than silently showing the draft surface.

### Requirement: Create, rename, archive, unarchive and delete conversations
The conversation list MUST support create, rename, archive, unarchive, and
delete. Archiving takes a conversation out of the default (active) listing and
into the archived listing **without destroying it**; unarchiving returns it to
the active listing. Deleting removes the conversation and its messages and
cancels any turn in flight on it — deletion is the destructive one, archiving
is not. An operation naming a conversation that does not exist MUST be
rejected.

#### Scenario: manage conversations
- **GIVEN** a running daemon,
- **WHEN** conversations are created, renamed, and deleted,
- **THEN** each operation persists and the listing reflects it; a deleted
  conversation and its messages are removed.

#### Scenario: archive and restore a conversation
- **GIVEN** a conversation in the active listing,
- **WHEN** it is archived,
- **THEN** it leaves the default (active) listing, appears in the archived
  listing, and is not destroyed; unarchiving returns it to the active listing.
  Archiving a conversation that does not exist is rejected.

### Requirement: Open an archived conversation read-only
An archived conversation MUST open **read-only**: its history reads normally,
the composer and the model/effort controls are disabled, and a restore
control is offered in their place. Archived is a state the owner leaves
deliberately, not a thread that silently accepts a turn and unarchives itself.

#### Scenario: an archived conversation opens read-only
- **GIVEN** an archived conversation,
- **WHEN** it is opened on the Chat page,
- **THEN** its history reads normally, the composer and the model/effort
  controls are disabled, and a restore control is offered.

### Requirement: Send fire-and-return and stream output over one subscription
Sending from the page MUST be **fire-and-return**: `POST .../messages` accepts
the message, starts or enqueues its turn, and returns immediately (202)
carrying none of the turn's output. Turn output is consumed from exactly one
place — `GET .../events`, an SSE subscription — so "the turn I started" and
"the turn my phone started" travel the same code and the sender is never a
special case. On attach the subscription MUST replay the in-flight turn's
events from that turn's beginning and then follow live (see "Replay the
in-flight turn to late subscribers"), so a client that arrives mid-turn misses
nothing; with no turn in flight it MUST hold open and deliver the next turn
whenever it begins, from whichever surface begins it.

#### Scenario: sending a message returns before the turn's output
- **GIVEN** a conversation on a registered agent
- **WHEN** a message is posted to `POST .../messages`
- **THEN** the response is 202 carrying only whether the message was queued
- **AND** none of the turn's output rides on that response

### Requirement: Recover a dropped event stream with bounded retries
A dropped event stream MUST be recovered by re-subscribing — the replay of
"Replay the in-flight turn to late subscribers" is what makes that safe — with
a backoff and a bounded number of attempts, so a hard failure surfaces as an
error the owner can act on rather than as a client hammering the endpoint.

#### Scenario: a dropped event stream reconnects and is bounded
- **GIVEN** an open conversation whose event subscription drops mid-turn,
- **WHEN** the client recovers,
- **THEN** it re-subscribes with a backoff and replays the in-flight turn; after
  a bounded number of failed attempts it stops and reports the error.

### Requirement: Show a just-sent prompt immediately
A just-sent prompt MUST appear in the thread immediately, before its persisted
row has been fetched, and MUST be retired when that row lands or when its turn
settles — whichever comes first. The wire carries no client-generated id, so
the match is by text, time and ordering, and a slow turn start must never leave
a duplicate bubble behind.

#### Scenario: a just-sent prompt is shown before its row lands
- **GIVEN** an open conversation,
- **WHEN** a message is sent,
- **THEN** it appears in the thread immediately and is replaced by its persisted
  row when that arrives — and is dropped when the turn settles even if no row
  ever claims it, so no duplicate bubble is left behind.

### Requirement: Keep the draft surface open during a turn
The draft surface MUST NOT lock while a turn runs. A message sent during a turn
joins the pending queue (see "Queue messages sent during a turn") and is shown
as its own row, one row per queued message, in queue order. A queued row MUST
be removable, and MUST be editable by pulling it back out of the queue into the
draft surface to amend — re-sending it then enqueues it at the **tail**,
because it is a new send and whatever was queued behind it was queued first.
`PUT .../pending` replaces the queue wholesale, and the resulting queue MUST
ride the event stream (see "Express a turn as typed events") so a second tab,
and the phone, render the same rows.

#### Scenario: editing a queued message re-queues it at the tail
- **GIVEN** one or more messages queued behind a streaming turn, shown one per
  row,
- **WHEN** a queued message is edited,
- **THEN** it leaves the queue and returns to the draft surface to be amended,
  and re-sending it enqueues it at the tail of the pending queue.

### Requirement: Interrupt the watched turn from the page
The page MUST be able to interrupt the turn it is watching — whichever surface
started it — via `POST .../interrupt`, with the semantics of "Pause the pending
queue on interrupt": the turn stops with its partial output kept and persisted,
and the pending queue is **paused** rather than auto-advanced into the turn
that was just stopped.

#### Scenario: the page stops a turn another surface started
- **GIVEN** a turn started by another surface, with a message queued behind it,
- **WHEN** the page calls `POST .../interrupt` for that conversation,
- **THEN** the turn stops with its partial output persisted,
- **AND** the queued message is held rather than auto-run.

### Requirement: Render tool calls as cards
The message thread MUST render a turn's tool calls as their own cards rather
than as prose: each card names the tool, shows what it was called with, and
shows the result once one arrives, so a reader can see what the agent *did* and
not only what it said. Text and tool-call blocks appear in the order the turn
emitted them, and a card whose result has not arrived yet reads as still
running.

#### Scenario: a tool call renders as a card between the text around it
- **GIVEN** an assistant message whose blocks are text, a tool call with its result, then more text, and a second tool call with no result yet
- **WHEN** the thread renders it
- **THEN** each tool call is a card naming its tool, placed between the text blocks in the order the turn emitted them
- **AND** opening the finished card shows what the tool was called with and its result
- **AND** the card with no result reads as still running

### Requirement: Render assistant text as GitHub-flavoured markdown
Assistant text MUST render as GitHub-flavoured markdown with single newlines
kept as line breaks — agent output laid out one fact per line must not collapse
into a run-on paragraph — and every fenced code block MUST offer a copy
control, because the code is what a reader most often wants out of a reply.

#### Scenario: assistant text keeps its line breaks and every code block copies
- **GIVEN** an assistant reply holding lines separated by single newlines, a GFM table and two fenced code blocks
- **WHEN** it renders in the thread
- **THEN** each single newline is a line break and the table renders as a table
- **AND** each fenced code block offers its own copy control

### Requirement: Show a failed turn as one inline banner with Retry
A failed turn MUST replace the in-progress bubble with a single inline error
banner in the flow above the composer — never a floating notice and never two
error surfaces at once — carrying a Retry that re-sends the message that failed
and a dismiss that clears it.

#### Scenario: a failed turn offers a retry in the thread
- **GIVEN** a turn that fails,
- **WHEN** the thread renders it,
- **THEN** the in-progress bubble is replaced by one inline banner in the flow,
  carrying a Retry that re-sends the failed message and a dismiss.

### Requirement: Let the owner set agent, model and reasoning level
The page MUST let the owner choose the agent a conversation runs on, on the
draft surface — once the conversation exists its agent is fixed and shown as a
label, because its upstream session and working directory belong to that one
agent (see "Record the agent on each conversation"). The page MUST let the owner
read and set the conversation's model and how hard that model thinks over
`GET|PATCH .../agent-config`, persisting both while
preserving the conversation's working directory and upstream session id, and
reverting to the agent's own default when either is cleared; a body that
mentions one leaves the other where it was.

The reasoning level is a SECOND control beside the model picker, not a variant
of it: the agents take it as their own field rather than as part of the model
name, and it renders only when the chosen model reports levels — nothing to
choose between means no control at all, not a disabled or empty one. Both
controls MUST be offered on the **draft** surface as well as in an open
conversation, because the first turn is the one a user most wants to pitch, and
by the time the conversation exists that turn is already running.

A missing Coffer LLM connection MUST NOT block the page: with none configured
the draft surface still accepts a message and the turn runs on the agent's own
built-in model and login, because a Coffer connection is an optional override,
not a prerequisite ([provider-switching](../provider-switching/spec.md), and the
2026-06-22 amendment of
[Provider Switching](../../../docs/decisions/provider-switching.md)).

#### Scenario: chat runs on the built-in model when no connection
- **GIVEN** a running daemon with no Coffer LLM connection configured for the
  agent,
- **WHEN** the Chat page is opened,
- **THEN** the draft surface is available with no blocking empty state, and a
  sent turn runs on the agent's own built-in model and login — a Coffer
  connection is an optional override, not a prerequisite.

### Requirement: Create the conversation on the first send
The draft is not a conversation row. The page opens on a blank draft surface,
and the **first send** is what creates the conversation — so a user who opens
the page and changes their mind leaves nothing behind. Where no managed agent
is available at all, the draft MUST be replaced by a state saying how to get
one rather than by a composer that can only fail.

#### Scenario: the draft creates the conversation on first send
- **GIVEN** the Chat page with no conversation open,
- **WHEN** the first message is sent from the draft surface,
- **THEN** the conversation is created by that send and the turn runs in it;
  opening the draft and leaving creates nothing. With no managed agent
  available, the draft is replaced by a state saying how to get one.

### Requirement: Offer models from a fixed dropdown that keeps the current value
The model picker MUST be a fixed dropdown, never free text. Its options are the
models the platform offers for the agent
([provider-switching](../provider-switching/spec.md) "Serve one model list to
every surface": the agent's own catalogue, or the active connection's curated
ids when one is active) plus the **current value** — which MUST stay selectable
whatever that list contains, so a conversation never shows a picker that cannot
represent the model it is actually on. Nothing else is offered: the page does
not introspect a connection's endpoint itself.

#### Scenario: the model picker always offers the current value
- **GIVEN** a conversation set to a model the agent's catalogue does not list,
- **WHEN** the model picker is opened,
- **THEN** the current value is among the options and is selected, and the
  picker accepts no free text.

### Requirement: Re-materialise attachments from persisted history
The turn task MUST re-materialise a turn's attachments by reading them back
from the last user message in the persisted history, not from a parameter
threaded down from whoever accepted the message. The persisted reference —
path, mime, filename, with the bytes left on disk — is the single source of
truth, so materialisation survives a daemon restart and stays consistent with
what the page shows. Each adapter then materialises the reference in its own
native shape (a vision agent inlines the content, a path-native agent receives
the path), and the path itself MUST NOT reach the wire: only the adapter, which
has to read the bytes, ever sees it. See
[Persisted Attachment Reference](../../../docs/decisions/persisted-attachment-reference.md)
and [Channel Media](../../../docs/decisions/channel-media.md).

#### Scenario: a later turn re-materialises the attachment from history
- **GIVEN** a user message carrying a persisted attachment reference,
- **WHEN** a later turn runs on that conversation,
- **THEN** the attachment is read back from history and handed to the adapter,
  which materialises it in its own native shape.

### Requirement: Transcribe audio attachments when transcription is configured
An audio attachment MUST be turned into a **transcript** folded into the turn's
prompt before the adapter builds its request, because the shipped agents cannot
hear audio. The transcription engine is injected behind a seam and consumes the
speech-to-text connection and model ([internal-engine](../internal-engine/spec.md) "Transcribe speech on its own connection and model") — its OWN
connection, flagged `transcribe_default`, never the one Coffer's engine runs
on. This is the one place in Coffer where user content may leave the machine,
and it is **off by default**: with no connection marked for transcription, no
model chosen for it, an unsupported protocol, or a credential that will not
resolve, nothing is uploaded and the audio is handed to the agent as an
ordinary file instead. Transcription that yields nothing degrades the same way;
it never wedges or fails the turn.

#### Scenario: an inbound voice message is transcribed for a text-only agent
- **GIVEN** a connection marked for transcription, a speech-to-text model, and
  an audio attachment on a turn,
- **WHEN** the turn is built,
- **THEN** the audio is transcribed and folded into the prompt; with either half
  unset nothing is uploaded and the agent receives the file instead.

### Requirement: Extract document attachments to text
A document attachment (PDF, office formats, epub, rtf) MUST be extracted to
text and folded into the turn's prompt the same way, so a path-native agent
sees its content instead of a note about a binary it cannot parse, and a vision
agent does not waste it as an image. Images stay vision-inlined and audio stays
transcribed; only documents take this path. The extractor is an optional
dependency — absent, or on any extraction failure, the document degrades to
being handed over as a file attachment.

#### Scenario: a PDF reaches a path-native agent as extracted text
- **GIVEN** a document attachment on a turn,
- **WHEN** the turn is built,
- **THEN** its text is extracted and folded into the prompt; with no extractor
  available the document is handed over as a file instead.

### Requirement: Compose the agent's prompt appends in one place
The appends an agent receives on top of its own prompt MUST be composed in
**one** place, shared by every provider, in a fixed order: the note telling a
channel-driven agent it is on a chat channel; then, for a channel-driven turn
only, the memory digest, whose content is memory's own ([memory](../memory/spec.md) "Deliver to channel turns through the system prompt") and
whose injection point is this one; then the model note of "Tell the agent which
model it is on", on every turn. Composing it here is what lets memory reach an
agent with no session-start hook and no install — Coffer owns this turn's
context itself. An agent the developer drives themselves receives memory
through its own hook instead, never both.

#### Scenario: a channel-driven turn carries the memory digest
- **GIVEN** a conversation driven from a channel and a memory digest to deliver,
- **WHEN** the turn's system context is composed,
- **THEN** the channel note, the memory digest and the model note are appended in
  that order; a conversation with no channel receives the model note only.

### Requirement: Search the conversation list by title
The Chat page's conversation list MUST offer a search box that filters the
listed conversations by title as the owner types: a conversation stays listed
when its title contains the query, compared case-insensitively with the query
trimmed, and clearing the query lists every conversation again. The filter runs
over the list already loaded for the current view (active or archived). A query
that matches nothing MUST show a no-match state that is distinct from the
empty-list state, and the search box MUST stay so the query can be changed; a
list with no conversations at all shows its empty state and offers no search.

#### Scenario: search narrows the conversation list by title
- **GIVEN** active conversations titled "Alpha rollout", "beta notes" and "Gamma"
- **WHEN** the owner types " ALP " into the list's search box
- **THEN** only "Alpha rollout" is listed
- **AND** clearing the search lists all three again

#### Scenario: a search that matches nothing is not an empty list
- **GIVEN** a conversation list holding one conversation
- **WHEN** the owner searches for text no title contains
- **THEN** no conversation is listed and the list says nothing matches
- **AND** it does not show the empty-list message, and the search box keeps the query

#### Scenario: an empty conversation list offers no search
- **GIVEN** a view with no conversations
- **WHEN** the conversation list renders
- **THEN** it shows the empty-list message and no search box
