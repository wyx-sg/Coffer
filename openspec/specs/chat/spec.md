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
own default config directory, which Coffer was told to leave alone. With no
managed agent at all, the draft surface is replaced by a state that links to the
Agents page.

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

### Requirement: Keep a turn's record in its conversation, not the audit log
A turn's own record is the conversation it ran in. The user message, the
assistant message, its tool-call and tool-result blocks, its model and its
token usage are all persisted (see "Keep the conversation index without its text") and readable from the REST API and the Conversations page, so "which agent did
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

### Requirement: List conversations by latest activity
Conversations MUST list newest-activity first, and a conversation's activity
timestamp MUST be bumped both when a turn **starts** and when it **finalises**
— a long turn moves its conversation to the top of the list when it begins, and
is still ordered correctly when it ends. Active and archived are two listings,
never one list with a flag every caller must remember. Both listings MUST page
by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor")
with the conversation id as the tie-break, so a conversation whose activity is
bumped while a reader pages moves to the head rather than appearing twice.
Both listings MUST narrow by source (`source`: `coffer` for conversations opened in
Coffer's own UI, any other token a channel uid) and by agent (`agent`: agent keys),
each a comma-separated set, in the server — the page and its `total` both — and a
cursor MUST be bound to the `q`, source and agent filters it was issued for.

#### Scenario: the conversation list is ordered by activity, not by creation
- **GIVEN** two conversations created in order,
- **WHEN** a turn starts on the older one and then completes,
- **THEN** it heads the active listing both while the turn runs and after it
  ends.

#### Scenario: the conversation list pages by cursor
- **GIVEN** three active conversations
- **WHEN** the active listing is read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two with the latest activity and the second the third, with a `null` `next_cursor`
- **AND** both pages report a `total` of 3

#### Scenario: the conversation list narrows by source and agent on the server
- **GIVEN** conversations opened in Coffer and in a channel, run by different agents
- **WHEN** the listing is read with `source=coffer` or `source=<channel uid>`, and with `agent=<key>`
- **THEN** the page and `total` hold only the matching conversations, and a cursor issued for one set of filters is `CURSOR_INVALID` for another

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
started it going away — which is why a reply completes and is persisted even
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
it runs and turn into the same question — MUST be stored as a `question` block of
the reply that asked, with its context, its questions and options, and its state:
pending, answered (the answers, where they were given — the web page or a named
channel —, by whom and when) or cancelled. The turn MUST stay running while the
question is pending. The first answer MUST win: a later answer to a closed
question is refused with `QUESTION_CLOSED` and changes nothing. Stopping the turn,
the turn ending or the daemon shutting down MUST cancel a pending question, and
the agent is told no answer came. The answers MUST go back to the agent as the
tool's result; nothing is added to the conversation as the owner's message.

#### Scenario: AskUserQuestion waits for the owner and gets the answer
- **GIVEN** a Claude Code turn in a Coffer conversation
- **WHEN** Claude Code calls `AskUserQuestion` with the options "Yes" and "No", and the owner answers "Yes" on the Conversations page
- **THEN** the reply holds a question block that went from pending to answered "Yes" via the web page
- **AND** Claude Code receives "Yes" as its answer and carries on, and no user message was added

#### Scenario: the second answer to one question is refused
- **GIVEN** a question answered "Yes" in SeaTalk
- **WHEN** the web page sends the answer "No" for it
- **THEN** the request is refused with `QUESTION_CLOSED` and the answer stays "Yes"

#### Scenario: stopping a turn cancels its question
- **GIVEN** a turn waiting on a pending question
- **WHEN** the owner presses Stop
- **THEN** the question is cancelled and the agent is told the owner stopped the task

### Requirement: Show which conversations wait on you
A conversation with a pending question MUST carry `needs_you` in the list, and its
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

