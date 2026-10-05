# Chat

## Purpose
A turn has to reach an agent the same way whoever asked for it — an IM channel,
the web page, anything later. Chat is the **turn platform**: the agent-provider
registry, the agent adapters, the conversation and message store, the turn
lifecycle with its pending queue, the typed event stream — and the web UI's
**Conversations page** that drives all of it, so the owner can watch and steer from a browser
what they started on a phone. The platform and the page are one capability
because the page owns no state of its own: every row it renders and every
control it offers belongs to the platform underneath it. A channel
([channels](../channels/spec.md)) is the platform's other client, reaching it
through the same seams; an agent cannot tell which window a turn arrived
through. The decision the page rests on is recorded in
[Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md).
Chat talks to **managed** agents only — the former `builtin` chat persona is
retired, see
[Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md).

What the platform promises as outcomes: adding a third agent takes one registry
entry and one adapter and touches no conversation schema, orchestrator code or
client; a turn started from any surface is observable, interruptible and
continuable from every other surface with no per-surface branch on the turn
path; no turn ever ends silently, and a daemon killed mid-turn leaves no
conversation showing a reply that will never arrive; and from a fresh install
with one managed agent present, a user can open the Conversations page, send a first
message and receive a streamed reply without configuring a Coffer LLM
connection first.

Known boundaries. **The platform ships no CLI, by design**: no `chat` command
group is registered, so conversations, the pending queue and the agent-provider
registry are reachable over REST and from the web page only, as the minimal-CLI
rule in [`.agents/openspec.md`](../../../.agents/openspec.md) asks of anything
that is neither a program's entry point, an offline operation nor a hand-off.
Two route prefixes serve this one capability: `/api/v1/chat` carries everything
about a conversation, and `/api/v1/agent-providers` carries the registry itself,
because its subject is the adapters that can drive a turn and not the `agent`
resource rows `/api/v1/agents` serves. The model catalogue is the agent kind's
answer ([agent-registry](../agent-registry/spec.md)), published into chat's
dependencies at the composition root as a port, because the import-linter fence
forbids chat from importing the agent kind. Chat state is single-daemon and
does not converge across machines. A channel keeps its own table mapping a chat
thread to a conversation id; that pointer is soft, may dangle, and chat neither
maintains nor validates it. Attachment bytes never enter chat's database. A
file a channel downloaded lives in that channel's media directory, whose prune
belongs to [channels](../channels/spec.md); a file attached on the Conversations page is
chat's own, uploaded to `~/.coffer/content/chat-media` and pruned by the same attachments retention policy.
Either way a conversation persists only the reference and reads the bytes at
turn time.

Conversations are always on: no experimental feature gates them. The knowledge and memory features only change what a conversation's turns carry (spec [experimental-features](../experimental-features/spec.md) "Close the memory feature's surfaces").

## Requirements

### Requirement: Route every turn through the agent-provider registry
A turn MUST reach an agent only through an **agent-provider registry**: a turn
is run, a conversation is initialised, and a conversation's agent state is torn
down by asking the registry for the agent named on the conversation. Adding
another agent MUST be a new registry entry only — no change to the
conversation schema, the turn orchestrator, or any client of the
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
offers only agents that exist; whether one is offered is decided by "Offer and run
only managed agents". It MUST likewise expose, per agent, the models that agent can be put on;
the route is the platform's, while the catalogue behind it is the agent kind's
answer ([agent-registry](../agent-registry/spec.md)), reaching this route
through a port rather than an import.

#### Scenario: list available agents
- **GIVEN** a running daemon,
- **WHEN** the platform is asked which agents it offers,
- **THEN** the managed agents (`claude_code`, `codex`) are listed, each with a
  display name and an availability flag, the `builtin` agent is **not** among
  them ([Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md)),
  and the list is reachable from the REST API.

### Requirement: Offer and run only managed agents
Chat MUST offer an agent only when its CLI is installed on this host and an
agent of its type is registered with Coffer (added on the Agents page);
an agent that is not installed, or installed but not added, MUST NOT
be offered for selection. A turn for a type with no registered agent MUST be
refused with an `agent_not_managed` rejection rather than run against the CLI's
own default config directory, which Coffer was told to leave alone.

#### Scenario: an unmanaged agent type is not offered and runs no turn
- **GIVEN** the `claude_code` CLI is installed but no `claude_code` agent is registered
- **WHEN** the provider is asked whether it is available and a turn is started on it
- **THEN** it is not available and the turn is refused as `agent_not_managed`
- **AND** once an agent of that type is registered, the provider is available and the turn runs

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

### Requirement: End every adapter stream with a terminal event
The adapter seam is a contract in both directions. An adapter MUST yield a
terminal turn-done or turn-error event before its iterator ends, and on
cancellation MUST clean up and re-raise rather than swallow it — the platform's
interrupt, delete and idle-watchdog paths all arrive that way. An iterator that
simply stops is not a completed turn (see "Deliver partial output as events when a turn is interrupted or fails").

#### Scenario: an agent stream that ends without a terminal is a turn error
- **GIVEN** an agent whose event stream ends without a completion event,
- **WHEN** the turn is driven,
- **THEN** exactly one terminal event follows, a `stream_ended` turn error, with
  the text streamed before the cut delivered ahead of it

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

### Requirement: Queue messages sent during a turn
System MUST process at most one in-flight turn per conversation without
rejecting a message sent while a turn is running: such a message is enqueued on
a per-conversation **pending queue**. When the in-flight turn ends, System MUST
dequeue the head and run its turn — sequential FIFO, one turn per queued
message, never coalesced by the queue. The queue is in-memory, so a daemon
restart drops what has not yet started. Every message comes from a channel, and
the channel's own status command counts what waits; no client keeps a buffer of
its own.

#### Scenario: second message queues during a streaming turn
- **GIVEN** a turn is streaming,
- **WHEN** another message is sent on the same conversation,
- **THEN** it is accepted and enqueued rather than rejected, and runs as its own
  turn after the current one ends.

#### Scenario: a queued message runs after the current turn
- **GIVEN** a message queued behind a running turn
- **WHEN** that turn completes
- **THEN** the queued message's turn runs, one turn per queued message

#### Scenario: a channel message waits in the conversation's own queue
- **GIVEN** a turn running on a paired channel's conversation
- **WHEN** the peer sends more messages
- **THEN** they wait on the one pending queue in arrival order and run as consecutive turns

### Requirement: Pause the pending queue on interrupt
Interrupting a turn MUST also **pause** the pending queue: the current turn
stops with its partial output delivered to the chat, and queued messages are held rather than
auto-run until the owner resumes them. The next message from the channel resumes the held queue.

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

### Requirement: Replay the in-flight turn to late subscribers
System MUST publish those events on a per-conversation in-process bus that any
number of subscribers may attach to. On attach, if a turn is in flight the bus
MUST replay the current turn's events so a late subscriber catches up, then
stream live. A turn runs as a detached task, so it survives the subscriber that
started it going away — which is why a reply completes even
when a client's connection drops mid-turn.

#### Scenario: observe a turn started from another surface
- **GIVEN** a turn already running on a conversation,
- **WHEN** a second subscriber attaches to that conversation's event bus,
- **THEN** it receives the current turn's events from the beginning and then
  follows live, so a subscriber that arrives mid-turn misses nothing.

### Requirement: Transcribe audio attachments when transcription is configured
An audio attachment MUST be turned into a **transcript** folded into the turn's
prompt before the adapter builds its request, because the shipped agents cannot
hear audio. The transcription engine is injected behind a seam and consumes the
speech-to-text connection and model ([internal-engine](../internal-engine/spec.md) "Transcribe speech on its own connection and model") — its OWN
connection, flagged `transcribe_default`, never the one Coffer's engine runs
on. This is the one place in Coffer where user content may leave the machine,
and it is **off by default**: with no connection marked for transcription, no
model chosen for it, an unsupported protocol, or a secret that will not
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
channel-driven agent it is on a chat channel — written from facts only the
channel kind holds (the platform, the chat kind, what renders there;
[channels](../channels/spec.md) "Tell a channel-driven agent it is on a chat
channel"), which it hands over as a value chat reads without importing it; then, for a channel-driven turn
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

### Requirement: Pause a turn on a question for the owner
A question an agent raises in a turn — through `coffer__ask`, or through Claude
Code's own `AskUserQuestion`, which the Claude Code adapter MUST intercept before
it runs and turn into the same question — MUST be held in memory as the
conversation's pending question, with its context, its questions and options, and
its state: pending, answered (the answers, which channel they were given in, by
whom and when) or cancelled. The turn MUST stay running while the question is
pending. The first answer MUST win: a later answer to a closed question is
refused with `QUESTION_CLOSED` and changes nothing. Stopping the turn, the turn
ending or the daemon shutting down MUST cancel a pending question, and the agent
is told no answer came. The answers MUST go back to the agent as the tool's
result; nothing is added to the conversation as the owner's message. A question
is stored nowhere: it is asked and answered in the channel ([channels](../channels/spec.md)
"Ask the owner in the chat and take the chat's answer back to the agent") and does not survive a daemon restart.

#### Scenario: AskUserQuestion waits for the owner and gets the answer
- **GIVEN** a Claude Code turn in a channel conversation
- **WHEN** Claude Code calls `AskUserQuestion` with the options "Yes" and "No", and the owner answers "Yes" in the chat
- **THEN** the conversation's question went from pending to answered "Yes" via that channel
- **AND** Claude Code receives "Yes" as its answer and carries on, and no user message was added

#### Scenario: the second answer to one question is refused
- **GIVEN** a question answered "Yes" by tapping its card in SeaTalk
- **WHEN** a later reply "No" is sent for it
- **THEN** the request is refused with `QUESTION_CLOSED` and the answer stays "Yes"

#### Scenario: stopping a turn cancels its question
- **GIVEN** a turn waiting on a pending question
- **WHEN** the owner presses Stop
- **THEN** the question is cancelled and the agent is told the owner stopped the task

### Requirement: Show which conversations wait on you
A conversation with a pending question MUST carry `needs_you` in the list, read from the turn's in-memory state, and its
row MUST show the status "Needs you" (warning colour) where a running one shows
"Running", in its usual place by time — no separate group or filter. The sidebar
MUST NOT carry a count for it.

#### Scenario: a waiting conversation is marked
- **GIVEN** two conversations, one waiting on a question
- **WHEN** the Conversations page renders
- **THEN** that row shows "Needs you" and the other does not
- **AND** once the question is answered the status goes away

### Requirement: Run Claude Code and Codex as subprocess providers on the type's one agent
System MUST ship subprocess-backed agent providers for Claude Code and Codex.
Each runs in a working directory (its `agent_config.cwd`); when a turn supplies
none, the provider MUST default to the Coffer-managed workspace
`~/.coffer/content/workspace` (created on first use) rather than reject the turn — so a
client with no configured workspace works out of the box. An
explicitly-supplied cwd MUST be an existing directory or the configuration is
rejected. Availability MUST reflect two things: whether the agent's binary is
resolvable on the user's PATH (the login shell's PATH merged with the daemon's
inherited one), and whether an **agent of that type is registered** with
Coffer; an agent failing either is unavailable and is not offered (see "Offer
and run only managed agents").

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

A turn MUST run against the config directory of its type's one agent
([agent-registry](../agent-registry/spec.md) "Keep one agent per type, named by
it") — the same one whose models the pickers offer
([agent-registry](../agent-registry/spec.md) "Serve each agent type's model
catalogue from its one agent"); a type with
no registered agent has no turn at all. Coffer delivers skills, installs its
MCP entry and edits config files in that directory, so a turn that read any
other one would not see them. When that agent's `config_dir` is not its type's
standard location, the spawned process's environment MUST carry the variable the
product reads it from — `CLAUDE_CONFIG_DIR=<config_dir>` for Claude Code,
`CODEX_HOME=<config_dir>` for Codex — merged with the daemon's own environment;
for the standard location the environment MUST be left as the daemon's own, so
the process behaves as when the user runs the CLI themselves. No provider key
rides the environment: an API-key connection is reached through Coffer's model
proxy.

#### Scenario: a streamed reply reaches the consumer exactly once
- **GIVEN** a Claude Code turn whose SDK delivers the reply as streamed increments and then as the finished assistant message
- **WHEN** the adapter maps the turn onto platform events
- **THEN** the reply arrives as one text delta per increment, in order
- **AND** the joined deltas equal the reply once, not doubled by the finished message
- **AND** the stream ends with a terminal turn-done

#### Scenario: a turn on an agent with its own config directory runs against that directory
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`, and a `codex` agent registered with a `config_dir` other than `~/.codex`
- **WHEN** a turn runs on each
- **THEN** the Claude Code process is started with `CLAUDE_CONFIG_DIR` set to the agent's `config_dir`, and the Codex app-server with `CODEX_HOME` set to its `config_dir`, the rest of the daemon's environment intact
- **AND** a turn on an agent whose `config_dir` is its type's standard location starts its process with the environment untouched

### Requirement: Express a turn as typed events in memory
System MUST express a turn as a sequence of typed events covering, at minimum,
turn start, text deltas, tool calls, tool results, turn completion and turn
error. The events travel in memory from the adapter to whoever renders the
turn — a channel's live surface — and are never written to a database.

#### Scenario: a turn streams its typed events in order and stores none of them
- **GIVEN** a conversation on a registered agent and a renderer attached to its turn
- **WHEN** a turn runs to completion
- **THEN** the renderer receives the turn's events in order — start, text deltas, completion
- **AND** no row of the turn's text is written anywhere by Coffer

### Requirement: Read the model an adapter reports without requiring it
An adapter MAY name the model the turn actually ran on; where it does, the
platform MUST read it best-effort and write it on the turn's log line, since
Coffer stores no reply to carry it. It is optional, so an adapter bringing no
Coffer-registered model is still a valid adapter — the platform never requires
it of the seam.

#### Scenario: a reported model reaches the turn's log line
- **GIVEN** an adapter that names the model it ran on
- **WHEN** a turn completes
- **THEN** the daemon log line of the turn carries that model
- **AND** an adapter that names none is still accepted and the turn completes

### Requirement: Hold a queued turn that fails to start until the chat writes again
A queued turn that fails to **start** MUST NOT vanish and MUST NOT spin. The
platform puts the message back at the **head** of the queue, pauses the queue,
and reports the failure as a turn error on the conversation's event stream —
and hands the channel's renderer a stream carrying that failure and ending, so
the failure is heard rather than inferred from silence. The next message from
the channel resumes the queue after the cause is fixed.

#### Scenario: a queued turn that fails to start is held, not lost
- **GIVEN** a message at the head of the pending queue whose turn cannot be started
- **WHEN** the platform tries to advance the queue
- **THEN** the message is put back at the head, the queue is paused, a turn error is published, and the message is still there when the queue is resumed

### Requirement: Drop a finished turn's replay buffer
Replay MUST NOT double-render. The queue-changed event is a conversation-level
snapshot, so the bus replays only the **latest** one rather than its history;
and the turn's replay buffer MUST be dropped when the turn ends, because from that moment nothing of the turn is held to replay — the finished reply lives in the agent's own session.

#### Scenario: a completed turn is not replayed
- **GIVEN** a turn that has completed
- **WHEN** a subscriber attaches afterwards
- **THEN** it receives the latest pending-queue snapshot and no turn content

### Requirement: Leave a turn's record to the agent's own session, not the audit log
A turn's own record is the agent's session: the agent keeps the user message,
the reply, its tool calls and results, its model and its usage in the session
the conversation resumes, and Coffer keeps none of them. "Which agent did what"
is answerable after the fact from that session, so turn activity MUST NOT be
written to the audit log: a turn is neither irreversible nor
security-sensitive nor invisible afterwards, and an audit row per turn would
duplicate the session while diluting a log whose value is that everything in it
changed who may do what.

#### Scenario: a turn leaves no audit row and no stored text
- **GIVEN** a conversation index in a real database and an agent that calls a tool while answering
- **WHEN** a turn runs to completion on it
- **THEN** the audit log holds no row for the turn
- **AND** the database holds no message of the turn

### Requirement: Deliver partial output as events when a turn is interrupted or fails
An interrupted or failed turn — user interrupt, adapter failure, a stream that
ends without a terminal event, timeout, daemon shutdown — MUST deliver whatever it
had streamed to its subscribers as events, ahead of exactly one terminal event:
turn-done with stop reason `interrupted` when the owner stopped it, a turn error in
every other case. Coffer keeps no copy of the partial text; it exists on the
event stream, and the agent's own session holds whatever the agent recorded.
Deleting a conversation cancels the turn running on it. Stopping a turn is
distinct from deleting the conversation.

A daemon shutdown MUST stop running turns itself: each is cancelled and emits a
`daemon_stopped` turn error, the shutdown waiting a bounded time for them to
settle.

Three turn errors are the platform's own rather than an agent's —
`stream_ended`, `turn_timeout` and `daemon_stopped`. Two of them it detects
agent-agnostically: an agent whose event stream ends without a terminal event
(its process died or lost its connection mid-turn) MUST be reported as a turn
error (`stream_ended`) by the platform's turn runner whether or not the adapter
reports it, never as a completed turn — a tick on a reply cut mid-sentence is a
lie; and a turn
that produces no event for the idle window
(`COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300; `0` disables the watchdog)
MUST be cancelled with a `turn_timeout` error, its agent process stopped
through the adapter's own cancellation path. In both cases whatever text
streamed before the failure is delivered ahead of the notice.

#### Scenario: stop a running turn
- **GIVEN** a turn that has streamed partial text and is still running
- **WHEN** it is interrupted
- **THEN** the partial text reaches the subscribers and the stream ends with a terminal turn-done carrying stop reason `interrupted`
- **AND** nothing of the reply is stored by Coffer

#### Scenario: a silent turn is cancelled by the idle watchdog
- **GIVEN** an agent that streams part of a reply and then produces nothing
- **WHEN** the idle window passes
- **THEN** the turn ends with a `turn_timeout` error, the agent's cancellation path runs, and the partial text was delivered ahead of the error

#### Scenario: an errored turn still delivers what it streamed
- **GIVEN** a turn that streamed text before failing,
- **WHEN** the channel renders it,
- **THEN** the chat receives the text, then the error notice, then the failed
  summary

#### Scenario: a stream that ends without a terminal is a failure, not a reply
- **GIVEN** an agent that streams part of a reply and then ends its event stream with no terminal event
- **WHEN** the turn is driven
- **THEN** the last event every subscriber receives is a `stream_ended` turn error and no turn-done is emitted
- **AND** the streamed text was delivered ahead of the error

#### Scenario: a shutdown stops running turns first
- **GIVEN** running turns that have streamed partial text
- **WHEN** the daemon shuts down
- **THEN** the turns are stopped before the database is closed, each ending with a `daemon_stopped` turn error
- **AND** each one's streamed text was delivered ahead of it

### Requirement: Show every agent's sessions on the Conversations page
The web UI MUST carry a **Conversations** page (`/conversations`) that lists every session of
every managed agent, wherever it was started — in a terminal, by an IM channel (SeaTalk,
Telegram) or by New conversation — read through [agent-registry](../agent-registry/spec.md)
"List every agent's sessions in one list". It is a list with no conversation view and no reply
box; its header's one primary action is **New conversation** ("Start a new conversation in the
terminal"). The list has a header row naming its columns — **Title**, **Source**, **Agent**,
**Directory**, **Last active** — above rows grouped by day (**Today**, **Yesterday**, **Earlier**;
the group titles carry no counts), newest activity first; a column the list does not show has no
heading. A row MUST show the title, a
status word (**Running** with a success-coloured dot while a turn runs; **Needs you** with a
warning dot while the agent waits for an answer, when the session is a channel conversation's),
its **source** (for a channel conversation the platform's logo and name with where in the chat it
lives — `SeaTalk · DM`, a group by its name when Coffer knows it, a thread or topic rather than the
chat's main timeline, a parallel thread as `DM · Thread 2`; for any other session nothing), the
agent's badge and name, its working directory, and its last activity (the clock time for today and
yesterday, a date such as `Sep 22` for earlier). A running row carries an inline **Stop**, which
calls `POST .../interrupt` for that conversation with the semantics of "Pause the pending queue on
interrupt". Every row carries the split button of "Open a conversation in the terminal" and a
trailing **⋯** menu (Rename, Delete…), both always shown. Rename edits the title in place in the
row — Enter saves, Esc cancels — and Rename and Delete… act through the agent ("Rename and delete a
conversation through its agent"; [agent-registry](../agent-registry/spec.md) "Rename and delete a
native session through the agent"); Delete… asks first. The row shows no message text, because
Coffer stores none.

The filter row reads, in order, a search box over titles and working directories (`/` focuses it), a
**Source** pill (**This Mac**, then each channel shown as its platform's logo and `SeaTalk · Team
bot`, several at once), an **Agent** pill, and **Clear filters** once anything narrows the list; it
shows no result count. The filters and the search are applied by the server, so a filtered list
pages through matches only. All of it is in the URL — `?q=`, `?source=local|<channel uid>[,…]`,
`?agent=` — so a filtered list is a link, and a channel's **Conversations from this channel** link
opens `?source=<uid>`. The list reads 30 sessions and then 50 more as it is scrolled, and refreshes
when the window regains focus and on the change feed's chat events. When an agent's sessions could
not be read, one line above the list names it with **Retry** and the other agents' sessions are
listed. With no session at all the page is its header and one message; with filters that match
nothing it says so and offers **Clear filters**; a list that fails to load for every agent shows the
error in its own area with **Retry**. The page opens on the list rather than on a welcome or
suggestions page, which it does not have.

#### Scenario: a channel's conversations are listed with the channel's badge
- **GIVEN** a session started in a terminal and conversations opened by two IM channels
- **WHEN** the Conversations page's list renders
- **THEN** every one is listed, each channel conversation with a badge naming its channel and the terminal session with none
- **AND** filtering by one channel lists only that channel's

#### Scenario: a row names the chat and thread it came from
- **GIVEN** a conversation a SeaTalk direct chat opened, one a group thread opened, and one a `/thread` parallel conversation opened, whose turn is running
- **WHEN** the Conversations page's list renders
- **THEN** the first row's badge names SeaTalk and the direct chat, the second the group and its thread, and the third its `Thread N` mark
- **AND** each row shows its agent and working directory, and the third is marked running

#### Scenario: rows are grouped by day without counts
- **GIVEN** sessions last active today, yesterday and weeks ago
- **WHEN** the Conversations page's list renders
- **THEN** a header row names the columns Title, Source, Agent, Directory and Last active, and below it the groups Today, Yesterday and Earlier, none of them with a count
- **AND** a row from today shows its clock time and an earlier row its date

#### Scenario: the Channel pill filters by several channels
- **GIVEN** sessions started in a terminal and conversations from three channels
- **WHEN** the user ticks two channels in the Source pill, and then This Mac alone
- **THEN** first only those channels' conversations are listed with `?source=` naming both and Clear filters offered, then only the terminal sessions with `?source=local`

#### Scenario: a row's menu acts on one conversation
- **GIVEN** a session in the list
- **WHEN** the user opens its ⋯ menu
- **THEN** it offers Rename and Delete… and nothing else, and Rename edits the title in place in the row
- **AND** Delete… asks first, naming the session

#### Scenario: a list that fails to load says so
- **GIVEN** the listing fails for every agent
- **WHEN** the page renders
- **THEN** the list area shows an error with Retry, and Retry reads the list again

#### Scenario: one agent's sessions that cannot be read are named above the list
- **GIVEN** Claude Code's sessions listed and Codex named as unavailable
- **WHEN** the page renders
- **THEN** Claude Code's sessions are listed under one line saying Codex's sessions could not be read, with Retry

#### Scenario: a search that matches nothing is not an empty list
- **GIVEN** a list holding one session
- **WHEN** the owner searches for text no title or directory contains
- **THEN** nothing is listed and the list says nothing matches
- **AND** it does not show the empty-list message, and the search box keeps the query

#### Scenario: an empty conversation list offers no search
- **GIVEN** no agent has any session
- **WHEN** the conversation list renders
- **THEN** it shows the empty-list message, New conversation and no search box

#### Scenario: the page opens on the list with no welcome page
- **GIVEN** sessions of two agents
- **WHEN** the user opens `/conversations`
- **THEN** it opens the list with no welcome or suggestions page and no reply box, and New conversation is the header's one primary action

#### Scenario: the page stops a turn another surface started
- **GIVEN** a running turn started from a channel, with a message queued behind it
- **WHEN** the user presses Stop on its row, which calls `POST .../interrupt` for that conversation
- **THEN** the turn stops, its streamed text having reached the chat
- **AND** the queued message is held rather than auto-run

#### Scenario: running and waiting rows are marked from the daemon's turn state
- **GIVEN** a conversation whose turn is in flight and another that waits on a question
- **WHEN** the list renders
- **THEN** the first row reads Running with an inline Stop and the second reads Needs you
- **AND** both flags come from the daemon's in-memory turn state

### Requirement: Open a conversation in the terminal
A row of the Conversations page MUST hand its session to the agent's own
interface: pressing the row, or the main part of its split button **Open in
<terminal>** (named for the preferred terminal, e.g. **Open in iTerm**), MUST ask the
daemon to resume the session in the person's preferred terminal ([web-ui](../web-ui/spec.md)
"Let the user choose a terminal"; [daemon](../daemon/spec.md) "Open an agent session in a
terminal") — `claude --resume <session id>` for Claude Code and `codex resume <session id>` for
Codex, in the session's working directory. The split button's **▾** menu holds
**Open in <terminal>** for every other terminal on this machine — the system
terminal and each detected one — which opens the session there once and leaves the
preference as it is, then **Copy command**, which copies the same command line for
the person to run anywhere: the same shape as the hand-off button. A channel conversation
that has no native session yet — no turn has run on it — cannot be opened: its split button
is disabled and says why, and it offers no Copy command. An open the daemon refuses shows its
reason in a toast beside Copy command as the way out. Agent › Sessions rows use the same row and
the same behaviour ([agent-registry](../agent-registry/spec.md) "Open an agent's sessions from its Sessions tab").

#### Scenario: a row opens its session in the preferred terminal
- **GIVEN** a Claude Code session `abc-123` in `/work/api` and a preferred terminal
- **WHEN** the user presses its row
- **THEN** the daemon is asked to open `claude --resume abc-123` in `/work/api` in that terminal, for the session's agent
- **AND** a Codex session is opened as `codex resume <id>` the same way

#### Scenario: the ▾ menu opens the session in another terminal once
- **GIVEN** a session and iTerm as the preferred terminal
- **WHEN** its row renders and the user opens the ▾ menu and chooses Open in System terminal
- **THEN** the main part reads Open in iTerm, the menu does not repeat iTerm, and the daemon is asked to open the session in the system terminal
- **AND** the preferred terminal is still iTerm

#### Scenario: copy command copies the resume command
- **GIVEN** a session
- **WHEN** the user opens the ▾ menu and chooses Copy command
- **THEN** the command line for resuming that session in its directory is copied

#### Scenario: a conversation with no native session cannot be opened
- **GIVEN** a channel conversation on which no turn has run
- **WHEN** its row renders
- **THEN** the split button is disabled with a tooltip saying there is no session yet, and Copy command is not offered

#### Scenario: a refused open is reported with a way out
- **GIVEN** a daemon that refuses the terminal open
- **WHEN** the user presses a row
- **THEN** a toast shows the reason and offers Copy command

### Requirement: Ask before opening a session that is running
A session whose turn is running, or that is waiting on a question for the owner,
MUST NOT be opened in a terminal without asking. Opening such a row — from the
Conversations page or from Agent › Sessions — MUST first open a dialog that says the
conversation is busy and offers two choices: **Answer in <platform>**, which closes the
dialog and does nothing else, and **Stop the turn and continue in the terminal**,
which interrupts the turn exactly as the row's Stop does (the pending question is
cancelled and the agent is told the owner stopped) and then opens the terminal.
A session that is neither running nor waiting opens at once.

#### Scenario: a running conversation asks before it opens
- **GIVEN** a conversation whose turn is running
- **WHEN** the user presses its row
- **THEN** a dialog offers Answer in the channel's platform and Stop the turn and continue in the terminal, and no terminal has opened

#### Scenario: stopping the turn then opens the terminal
- **GIVEN** the dialog over a conversation waiting on a question
- **WHEN** the user chooses Stop the turn and continue in the terminal
- **THEN** the turn is interrupted, the question is cancelled, and the terminal opens on the session

#### Scenario: answering in the chat leaves the session alone
- **GIVEN** the same dialog
- **WHEN** the user chooses Answer in the chat
- **THEN** the dialog closes, the turn keeps running and no terminal opens

### Requirement: Rename and delete a conversation through its agent
Renaming and deleting a conversation MUST act on the agent's own record of it, then
on Coffer's index row. `PATCH /api/v1/chat/conversations/{id}` (a title) MUST rename
the conversation's native session through the agent
([agent-registry](../agent-registry/spec.md) "Rename and delete a native session through the agent")
and then set the index row's title; a title the owner set outranks the one generated
from the first message. `DELETE /api/v1/chat/conversations/{id}` MUST delete the native
session through the agent, cancel any turn in flight on it, and then delete the index row.
Delete asks first, naming the conversation, and says the conversation is
deleted from the agent as well and cannot be recovered, while the files the agent
changed stay. A conversation that has no native session yet is renamed or deleted
in the index only. When the agent refuses the operation, the error is shown and the
index row is left as it was. An operation naming a conversation that does not
exist MUST be rejected. Chat reaches the agent kind through a port published at the
composition root, because it may not import it.

#### Scenario: rename a conversation in place
- **GIVEN** a conversation with a native session
- **WHEN** the user chooses Rename on its row, types a new title and presses Enter
- **THEN** the native session is renamed through the agent and then the row's title is saved, with no dialog
- **AND** pressing Esc instead keeps the old title

#### Scenario: delete asks first, naming the conversation
- **GIVEN** a conversation titled "Test Conv"
- **WHEN** the user chooses Delete… from its ⋯ menu
- **THEN** a confirmation titled "Delete “Test Conv”?" says it is deleted from the agent too and cannot be recovered, and the files the agent changed stay
- **AND** nothing is deleted until the user confirms

#### Scenario: delete removes the native session and the index row
- **GIVEN** a conversation with a native session and a turn in flight
- **WHEN** the user confirms Delete
- **THEN** the turn is cancelled, the session is deleted through the agent and the index row is gone
- **AND** the channel's next message in that chat opens a fresh conversation

#### Scenario: a conversation with no session is deleted from the index only
- **GIVEN** a conversation on which no turn has run
- **WHEN** it is deleted
- **THEN** only the index row is removed and the agent is not asked

#### Scenario: a refused rename leaves the index alone
- **GIVEN** an agent that refuses to rename the session
- **WHEN** the user renames the conversation
- **THEN** the error is shown and the row keeps its title

#### Scenario: an unknown conversation is rejected
- **GIVEN** no conversation with the given id
- **WHEN** it is renamed or deleted
- **THEN** the operation is rejected as not found

### Requirement: Run a session in one place at a time
A native session MUST be continued in one place at a time. Before a channel turn
resumes a conversation's native session, the turn platform MUST ask whether any
process outside the daemon's own process tree has that session id among its
arguments (a terminal running `claude --resume <id>` or `codex resume <id>`). If one
has, the turn MUST NOT start, and the channel replies "This session is open in a
terminal — continue there, or send /thread to start a new one." Codex's own refusal —
its app-server answering JSON-RPC error `-32600`, "already has an active writer" —
MUST be mapped to the same refusal and the same reply. A process the daemon started
for a turn is part of the daemon's own tree and never counts. The check sees a
session started with its id on the command line; a session opened by picking it
inside the agent's own picker is not seen, and only Codex's writer lock protects it.

#### Scenario: a session open in a terminal refuses the channel turn
- **GIVEN** a conversation whose native session id is in the arguments of a terminal process outside the daemon
- **WHEN** the peer sends a message
- **THEN** the turn does not start and the chat is told "This session is open in a terminal — continue there, or send /thread to start a new one."

#### Scenario: the daemon's own turn does not count
- **GIVEN** a conversation whose session is held by a process the daemon started for a turn
- **WHEN** the next message arrives
- **THEN** it joins the pending queue as usual and no refusal is sent

#### Scenario: a session whose terminal closed runs again
- **GIVEN** the refused conversation after the terminal process has exited
- **WHEN** the peer sends a message
- **THEN** the turn starts

#### Scenario: Codex's active-writer error is the same refusal
- **GIVEN** a Codex session that another process holds, answering `-32600` "already has an active writer"
- **WHEN** a channel turn resumes it
- **THEN** the chat gets the same reply and no turn error is shown

### Requirement: Keep the conversation index without its text
Coffer MUST keep an index of conversations and nothing of what was said in them.
The index is `chat_conversations` in the history database (`~/.coffer/runs.db`):
per conversation its id, agent, title, creation and update times, the channel
and chat it belongs to, and the agent configuration (working directory, the
agent's native session id, model). It holds no message, no reply, no diff and no
attachment; it is history of this machine, never written into the vault, and not a
Resource of the kind-agnostic Resource framework. A conversation is created by a
channel's message and never by the web, so a row always has a channel.

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

On upgrade, the migration MUST drop `chat_messages`, `chat_reply_files` and
`chat_conversations.archived_at`, delete the rows no channel owns (the web's own
conversations — their native sessions remain in the agent and in Agent ›
Sessions), and delete the retention policy rows of the two conversation entries.

#### Scenario: a conversation the owner named keeps its name
- **GIVEN** a conversation the owner has renamed
- **WHEN** its first user message arrives
- **THEN** the conversation keeps the name the owner gave it, and only a conversation still under its placeholder title is named from its first message

#### Scenario: a conversation row holds no message text
- **GIVEN** a channel conversation after several turns
- **WHEN** the history database is read
- **THEN** the index row carries the title, agent, channel, directory and session id, and no table holds the turns' text

#### Scenario: the upgrade drops the text and keeps channel conversations
- **GIVEN** a database holding messages, reply files, an archived conversation, a web-opened conversation and a channel's conversation
- **WHEN** the migration runs
- **THEN** the message and reply-file tables and the archive column are gone, the web-opened conversation's row is gone, and the channel's conversation row is kept
- **AND** the two conversation retention policy rows are gone

### Requirement: Let the agent's own session hold the conversation
A turn MUST be given the person's message — with its attachments and the prompt
appends — and no history. Every adapter resumes the agent's own session, which
holds the conversation, and the native session id kept on the index row is the
only link to it. A fresh session — a conversation's first turn, or the one retry
after a forgotten resume id ("Retry a forgotten resume id once as a fresh session") —
starts without history. An attachment travels with the turn that carries it,
from the channel's media directory to the adapter, and is materialised there in the
adapter's own native shape (a vision agent inlines an image, a path-native agent
receives the path); the path itself MUST NOT reach the wire. Because Coffer keeps
no copy, a conversation whose session the agent has since cleaned up (Claude Code
removes sessions after `cleanupPeriodDays`) resumes as a fresh session.

An agent is addressed for a turn through a self-contained **agent adapter**: given only
the turn, it yields a stream of typed turn events. The adapter carries its own model,
tools and configuration; the orchestrator MUST NOT inject them.

#### Scenario: a turn carries no history
- **GIVEN** a conversation with earlier turns
- **WHEN** a new turn runs
- **THEN** the adapter is given the new message and resumes the stored native session, with no earlier message passed

#### Scenario: a turn's attachment reaches the adapter without a stored message
- **GIVEN** a channel message with an image
- **WHEN** its turn runs
- **THEN** the adapter receives the attachment's path, type and name, and materialises it in its own shape, with no message row involved

#### Scenario: the orchestrator hands an adapter only the turn
- **GIVEN** a conversation whose agent's adapter records what it is called with
- **WHEN** a turn runs on that conversation
- **THEN** the adapter receives the turn's message and attachments and no message history
- **AND** it is handed no model, tool list or configuration by the orchestrator

#### Scenario: a cleaned-up session resumes as a fresh one
- **GIVEN** a conversation whose native session the agent no longer has
- **WHEN** a turn is started
- **THEN** the connect is retried once with no session id, the turn runs without history, and the new session id is stored

### Requirement: Start a new conversation in the terminal
The Conversations page header, and an agent's Sessions tab beside its search box, MUST carry
**New conversation**. It opens a dialog of two fields — **Agent**, the managed agents, preset to
the one chosen last (on a Sessions tab, that tab's agent), and **Working directory**, preset to
Coffer's workspace `~/.coffer/content/workspace` with a folder picker. The dialog's confirm is a
split button named for the preferred terminal, **Open in <terminal>**, whose ▾ offers every
other terminal on this machine for this once. Confirming MUST ask the daemon to start a blank
session of that agent in that directory in that terminal ([daemon](../daemon/spec.md) "Open an
agent session in a terminal") and close the dialog once the daemon has started it; a refusal shows
its reason in the dialog, which stays open. The new session is listed once the agent has recorded
it, on the list's next refresh. With no managed agent the button is disabled and says why.

#### Scenario: New conversation starts the chosen agent in the chosen directory
- **GIVEN** Claude Code and Codex managed, Codex chosen last, and iTerm the preferred terminal
- **WHEN** the user presses New conversation, picks `/work/api` and confirms Open in iTerm
- **THEN** the dialog opened with Codex and the workspace directory, and the daemon is asked to start a blank Codex session in `/work/api` in iTerm
- **AND** the dialog closes

#### Scenario: a refused start keeps the dialog open
- **GIVEN** a daemon that refuses the terminal open
- **WHEN** the user confirms New conversation
- **THEN** the dialog stays open and shows the reason
