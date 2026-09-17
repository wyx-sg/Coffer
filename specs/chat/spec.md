# Feature Specification: Chat

**Status**: Accepted
**Input**: "A turn has to reach an agent the same way whoever asked for it —
an IM channel, the web page, anything later. One registry, one conversation
store, one queue, one event stream; and a desktop surface onto exactly those
conversations, so the owner can watch and steer from a browser what they
started on a phone."

Chat is the **turn platform**: the agent-provider registry, the agent adapters,
the conversation and message store, the turn lifecycle with its pending queue,
the typed event stream — and the **web Chat page** that drives all of it. The
platform and the page are one spec because the page owns no state of its own:
every row it renders and every control it offers belongs to the platform
underneath it. A channel (spec [channels](../channels/spec.md)) is the
platform's other client, reaching it through the same seams; an agent cannot
tell which window a turn arrived through.

The decision the page rests on is recorded in
[Chat Is a Single-Owner Live Mirror](../../docs/decisions/chat-single-owner-live-mirror.md).
Chat talks to **managed** agents only — the former `builtin` chat persona is
retired, see
[Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md).

## User Scenarios & Testing

### User Story 1 — Run a turn on an agent (Priority: P1)

Something — a page, a channel, a later surface nobody has built yet — hands the
platform a conversation and a message. The platform looks up the agent named on
the conversation, builds its adapter, runs one turn, streams typed events to
whoever is listening, and persists the result as the conversation's own record.
A second message arriving mid-turn waits its place in one queue.

**Why this priority**: Nothing else in this spec exists without it, and it is
what makes a second agent a registry entry rather than a re-architecture.

**Independent Test**: Register a scripted provider, create a conversation on it,
send two messages in quick succession, and observe one turn streaming while the
other waits, then runs.

**Covering scenarios**:

- list available agents
- choose an agent when starting a conversation
- reject an unknown agent or invalid agent configuration
- send a message and receive a streamed reply
- a queued message runs after the current turn
- reply survives a restart

### User Story 2 — Watch and steer the same conversation from the browser (Priority: P2)

The owner is driving a conversation from their phone and sits down at a desk.
The web Chat page lists every conversation in the vault, whatever opened it,
badges the ones a channel is also reachable on, and renders the turn already in
flight from its beginning. From there the owner reads the tool calls as cards,
types the next message into the same pending queue the phone feeds, interrupts
the running turn, renames or archives the conversation, and changes which agent
it runs on, which model, and how hard that model thinks. Nothing about the turn
tells the agent which window it arrived through.

**Why this priority**: This is the one thing no channel can do — a desktop-sized
view onto a conversation the owner started on a phone, and a draft surface wide
enough to pitch the next turn properly.

**Independent Test**: Start a turn from a paired channel, open the page
mid-turn, and observe the in-flight turn replayed from its start and then
followed live; send a second message from the page and observe it queued behind
the running turn on both surfaces; interrupt from the page and observe the
partial reply kept.

**Covering scenarios**:

- observe a turn started from another surface
- second message queues during a streaming turn
- editing a queued message re-queues it at the tail
- interrupting a turn pauses the pending queue
- manage conversations
- archive and restore a conversation
- an archived conversation opens read-only
- a stale conversation link says so

## Requirements

### A. The agent-provider registry

- **FR-001**: A turn MUST reach an agent only through an **agent-provider
  registry**: a turn is run, a conversation is initialised, and a conversation's
  agent state is torn down by asking the registry for the agent named on the
  conversation. Adding another agent MUST be a new registry entry only — no
  change to the conversation/message schema, the turn orchestrator, or any
  client of the platform. No client branches per agent.
- **FR-002**: Each conversation MUST record which agent it belongs to via an
  `agent_key`, plus an opaque, agent-specific configuration that the named agent
  validates and persists. An `agent_key` no agent provides MUST be rejected, and
  an invalid configuration MUST be rejected as a domain error — both before
  anything is written. This is what a channel binding resolves against on the
  peer's first message.
- **FR-003**: The platform MUST expose its registered agents — each with a
  stable key, a display name, and a current availability flag — over the REST
  API, so a caller offers only agents that exist and marks the ones whose CLI is
  absent on this host. It MUST likewise expose, per agent, the models that agent
  can be put on; the route is the platform's, while the catalogue behind it is
  the agent kind's answer (spec [agent-registry](../agent-registry/spec.md)),
  reaching this route through a port rather than an import.
- **FR-004**: An `agent_key` no provider answers for MUST be **404** on a
  subresource path — asking for the models of an agent that does not exist is a
  missing path — and **400** `UNKNOWN_AGENT` when it names the agent a turn was
  to run on, where the path exists and the body is wrong. The two are distinct
  answers to distinct questions and MUST NOT be collapsed into one.

### B. Agent adapters

- **FR-005**: An agent is addressed for a turn through an **agent adapter** that
  is self-contained: given only the conversation history, it yields a stream of
  typed turn events. The adapter carries its own model, tools, and
  configuration; the orchestrator MUST NOT inject them.
- **FR-006**: System MUST ship subprocess-backed agent providers for Claude Code
  and Codex. Each runs in a working directory (its `agent_config.cwd`); when a
  turn supplies none, the provider MUST default to the Coffer-managed workspace
  `~/.coffer/workspace` (created on first use) rather than reject the turn — so
  a client with no configured workspace works out of the box. An
  explicitly-supplied cwd MUST be an existing directory or the configuration is
  rejected. Availability MUST reflect whether the agent's binary is resolvable
  on the daemon's PATH; an unavailable agent is listed but not selectable. A
  turn MUST stream the tool's line-delimited JSON output mapped onto the
  platform's turn events, and persist the upstream session id so the next turn
  continues the same session. Claude Code is driven through the Claude Agent SDK
  and Codex through `codex app-server` (JSON-RPC 2.0 over stdio, NDJSON-framed);
  both run with full permissions — owner pairing (spec
  [channels](../channels/spec.md)) is the security gate. Both MUST emit the
  reply as text increments *as it is written*, not as one block at the end of
  the turn, otherwise a live surface has nothing to grow and a reply lands all
  at once after a long silence. The Claude Agent SDK does this only when asked
  (`include_partial_messages`), and it then delivers BOTH the increments and the
  finished assistant message, so the adapter MUST subtract what it already
  emitted and send the reply exactly once.
- **FR-007**: The adapter seam is a contract in both directions. An adapter MUST
  yield a terminal turn-done or turn-error event before its iterator ends, and
  on cancellation MUST clean up and re-raise rather than swallow it — the
  platform's interrupt, delete and idle-watchdog paths all arrive that way. An
  iterator that simply stops is not a completed turn (FR-020).
- **FR-008**: An adapter MAY name the model the turn actually ran on; where it
  does, the platform MUST record that model on the assistant message. It is
  optional, so an adapter bringing no Coffer-registered model is still a valid
  adapter — the platform reads it best-effort and never requires it of the seam.
- **FR-009**: A resume id the agent no longer recognises MUST NOT fail the turn.
  Where connecting with a stored upstream session id fails and a session id was
  in play, the platform MUST retry the turn **once** as a fresh session; only a
  second failure becomes a turn error. A prior turn can leave an id the agent's
  own CLI later refuses, and without this the conversation would be permanently
  unusable rather than merely discontinuous.
- **FR-010**: Every turn MUST carry an authoritative note telling the agent which
  model Coffer put it on and what else it could be switched to. The agent cannot
  see Coffer's choice and, asked, invents one; the note therefore says it
  outranks the agent's own guess, names the leading few ids and points at the
  picker for the rest rather than spending prompt on the whole catalogue. Where
  Coffer set no override, the note MUST say the agent's own default is in use
  rather than name a model.

### C. The conversation and message store

- **FR-011**: System MUST persist conversations and their messages in SQLite as
  the system of record; they are not Resources of the kind-agnostic Resource
  framework. A message MUST store its role and an ordered list of content blocks
  of types `text`, `tool_use`, `tool_result`, and `attachment` (FR-044);
  assistant messages MUST also store token usage and the model that produced
  them when the agent reports one. A conversation opens under a placeholder
  title, which System MUST replace with the text of its first user message
  (truncated); once the owner has named a conversation themselves, System MUST
  NOT overwrite that name — an explicit rename outranks the generated one. The
  name MUST come from the part of that message the person actually wrote, which
  a client that folds context blocks into its turns passes down explicitly; the
  platform MUST NOT recognise any client's block format itself. Where the person
  wrote nothing at all (a photo or a file on its own), the attachment filenames
  name the conversation; where there is nothing nameable at all, the
  conversation keeps its placeholder title rather than being named after
  boilerplate.
- **FR-012**: A turn's own record is the conversation it ran in. The user
  message, the assistant message, its tool-call and tool-result blocks, its
  model and its token usage are all persisted (FR-011) and readable from the
  REST API and the Chat page, so "which agent did what" is answerable after the
  fact from the timeline rather than from a second ledger. Turn activity MUST
  therefore NOT be written to the audit log: a turn is neither irreversible nor
  security-sensitive nor invisible afterwards, and an audit row per turn would
  duplicate the timeline while diluting a log whose value is that everything in
  it changed who may do what.
- **FR-013**: A turn MUST be given only the most recent 200 messages as context.
  The adapters resume the agent's own session, which already holds the
  conversation; the history the platform passes is what a fresh session or a
  path-native agent gets, and the recent rows are the ones that matter for it. A
  conversation of thousands of messages MUST NOT be loaded whole on every turn.
- **FR-014**: Conversations MUST list newest-activity first, and a conversation's
  activity timestamp MUST be bumped both when a turn **starts** and when it
  **finalises** — a long turn moves its conversation to the top of the list when
  it begins, and is still ordered correctly when it ends. Active and archived
  are two listings, never one list with a flag every caller must remember.
- **FR-015**: `agent_key` MUST have no storage-level default. Every writer names
  the agent explicitly; an absent one is a programming error rather than a
  fallback, because a default could only ever mint a conversation routed to an
  agent that has since been withdrawn — a row no turn can run.

### D. Conversation retention

- **FR-016**: Conversations MUST follow a two-stage, retention-managed
  lifecycle, both windows configurable by the owner: the retention worker
  auto-archives a conversation with no new message for the auto-archive window
  (default 7 days), then deletes archived conversations and their messages the
  configured number of days after archiving (default 30 days). Either window may
  be set to keep-forever to disable that stage. Auto-archiving is reversible;
  only deletion is destructive.
- **FR-017**: Both windows MUST be registered as ordinary entries of the
  framework's own retention registry rather than as a worker private to chat —
  the first sets a column on the conversation, the second deletes the row — so
  they are tuned on the same surface as every other retained table. Deleting a
  conversation MUST take its messages with it, whether the deletion came from
  retention or from the owner.

### E. Turn lifecycle, queueing and interruption

- **FR-018**: System MUST process at most one in-flight turn per conversation
  without rejecting a message sent while a turn is running: such a message is
  enqueued on a per-conversation **pending queue**. When the in-flight turn
  ends, System MUST dequeue the head, commit it as the next user message, and
  run its turn — sequential FIFO, one turn per queued message, never coalesced.
  A pending message is not committed to the message sequence until its turn
  starts. The queue is in-memory, so a daemon restart drops what has not yet
  been committed. Every client feeds this one queue: a message arriving from a
  channel while a turn is in flight is shown in the page's pending rows and
  counted by the channel's own status command, and the two surfaces drain one
  FIFO per conversation — no client keeps a buffer of its own.
- **FR-019**: Interrupting a turn MUST also **pause** the pending queue: the
  current turn stops with its partial output kept, and queued messages are held
  rather than auto-run until the owner resumes them. The next message from any
  surface resumes the held queue.
- **FR-020**: An interrupted turn — user interrupt, adapter failure, or daemon
  restart — MUST leave the partial assistant message persisted and marked
  complete rather than discarded. Stopping a turn is distinct from discarding
  the conversation, which throws the turn away. Two failures the platform
  detects itself, agent-agnostically: an agent whose event stream ends without a
  terminal event (its process died or lost its connection mid-turn) MUST be
  reported as a turn error (`stream_ended`), never as a completed turn — a tick
  on a reply cut mid-sentence is a lie; and a turn that produces no event for
  the idle window (`COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300; `0` disables
  the watchdog) MUST be cancelled with a `turn_timeout` error, its agent process
  stopped through the adapter's own cancellation path. In both cases whatever
  text streamed before the failure is kept on the assistant message (marked
  failed) and delivered ahead of the notice.
- **FR-021**: A `streaming` placeholder assistant row MUST be written **before**
  the first event of a turn and finalised in place when the turn ends — one row,
  never a duplicate. A daemon that dies mid-turn therefore leaves a row saying
  so, and a **startup sweep** MUST flip every lingering `streaming` row to
  `failed` as the daemon comes up, so no conversation reopens showing a reply
  that will never arrive.
- **FR-022**: A queued turn that fails to **start** MUST NOT vanish and MUST NOT
  spin. The platform puts the message back at the **head** of the queue, pauses
  the queue, and reports the failure as a turn error on the conversation's event
  stream — and, for a client that has no queue rows to look at, hands its
  renderer a stream carrying that failure and ending, so the failure is heard
  rather than inferred from silence. The owner resumes the queue after fixing
  the cause.
- **FR-023**: Replacing the pending queue MUST reconcile the new ordered texts
  against the existing entries, reusing an entry for each text it still contains
  (first unused match wins). A queue reordered or partly dropped from the page
  therefore keeps each surviving message's attachments and its originating
  client's renderer; only a text that was not queued before becomes a new, bare
  entry.
- **FR-024**: Per-conversation turn state — the event bus, the in-flight turn,
  the pending queue and its pause flag — is **process-global and single-daemon**
  by design, one state per conversation. A state MUST exist only while something
  needs it (a turn in flight, a message waiting, or a subscriber attached) and
  MUST be released otherwise, so a daemon that has served ten thousand
  conversations does not carry ten thousand buses.

### F. The typed event stream

- **FR-025**: System MUST express a turn as a sequence of typed events covering,
  at minimum, turn start, text deltas, tool calls, tool results, turn
  completion, turn error, and pending-queue change.
- **FR-026**: System MUST publish those events on a per-conversation in-process
  bus that any number of subscribers may attach to. On attach, if a turn is in
  flight the bus MUST replay the current turn's events so a late subscriber
  catches up, then stream live. A turn runs as a detached task, so it survives
  the subscriber that started it going away — which is why a reply completes and
  is persisted even when a client's connection drops mid-turn.
- **FR-027**: Each event's `type` discriminator MUST be the event name on the
  wire, verbatim — `turn_start`, `text_delta`, `tool_call`, `tool_result`,
  `turn_done`, `turn_error`, `queue_changed`. One vocabulary, so a client
  dispatches on the event name it receives without a translation table that can
  drift from the platform's own names.
- **FR-028**: Replay MUST NOT double-render. The queue-changed event is a
  conversation-level snapshot, so the bus replays only the **latest** one rather
  than its history; and the turn's replay buffer MUST be dropped when the turn
  ends, because from that moment the content is persisted and a late subscriber
  loads it from history instead.

### G. The web Chat page

- **FR-029**: The web UI MUST carry a **Chat page**: two columns, the
  conversation list on the left and the selected conversation's message thread
  with its draft surface on the right. The list MUST show every conversation in
  the vault whatever opened it — a conversation an IM channel created is listed,
  readable, watchable, and continuable from the page, and carries a badge naming
  the channel it is also reachable on. There is no web-only conversation kind:
  the page and the channel are two windows onto one timeline, driven by one
  owner, and an agent cannot tell which window a turn arrived through.
- **FR-030**: The open conversation MUST be part of the URL (`/chat/:id`), so a
  refresh, a deep link and a second tab all reopen the same thread. A link to a
  conversation that no longer exists MUST say so explicitly, with a way back to
  a new draft — never drop silently into the draft surface as though the link
  had been to nothing.
- **FR-031**: The conversation list MUST support create, rename, archive,
  unarchive, and delete. Archiving takes a conversation out of the default
  (active) listing and into the archived listing **without destroying it**;
  unarchiving returns it to the active listing. Deleting removes the
  conversation and its messages and cancels any turn in flight on it — deletion
  is the destructive one, archiving is not. An operation naming a conversation
  that does not exist MUST be rejected.
- **FR-032**: An archived conversation MUST open **read-only**: its history
  reads normally, the composer and the agent/model/effort controls are disabled,
  and a restore control is offered in their place. Archived is a state the owner
  leaves deliberately, not a thread that silently accepts a turn and unarchives
  itself.
- **FR-033**: Sending from the page MUST be **fire-and-return**:
  `POST .../messages` accepts the message, starts or enqueues its turn, and
  returns immediately (202) carrying none of the turn's output. Turn output is
  consumed from exactly one place — `GET .../events`, an SSE subscription — so
  "the turn I started" and "the turn my phone started" travel the same code and
  the sender is never a special case. On attach the subscription MUST replay the
  in-flight turn's events from that turn's beginning and then follow live
  (FR-026), so a client that arrives mid-turn misses nothing; with no turn in
  flight it MUST hold open and deliver the next turn whenever it begins, from
  whichever surface begins it.
- **FR-034**: A dropped event stream MUST be recovered by re-subscribing — the
  replay of FR-026 is what makes that safe — with a backoff and a bounded number
  of attempts, so a hard failure surfaces as an error the owner can act on
  rather than as a client hammering the endpoint.
- **FR-035**: A just-sent prompt MUST appear in the thread immediately, before
  its persisted row has been fetched, and MUST be retired when that row lands or
  when its turn settles — whichever comes first. The wire carries no
  client-generated id, so the match is by text, time and ordering, and a slow
  turn start must never leave a duplicate bubble behind.
- **FR-036**: The draft surface MUST NOT lock while a turn runs. A message sent
  during a turn joins the pending queue (FR-018) and is shown as its own row,
  one row per queued message, in queue order. A queued row MUST be removable,
  and MUST be editable by pulling it back out of the queue into the draft
  surface to amend — re-sending it then enqueues it at the **tail**, because it
  is a new send and whatever was queued behind it was queued first. `PUT
  .../pending` replaces the queue wholesale, and the resulting queue MUST ride
  the event stream (FR-025) so a second tab, and the phone, render the same rows.
- **FR-037**: The page MUST be able to interrupt the turn it is watching —
  whichever surface started it — via `POST .../interrupt`, with the semantics of
  FR-019: the turn stops with its partial output kept and persisted, and the
  pending queue is **paused** rather than auto-advanced into the turn that was
  just stopped.
- **FR-038**: The message thread MUST render a turn's tool calls as their own
  cards rather than as prose: each card names the tool, shows what it was called
  with, and shows the result once one arrives, so a reader can see what the agent
  *did* and not only what it said. Text and tool-call blocks appear in the order
  the turn emitted them, and a card whose result has not arrived yet reads as
  still running.
- **FR-039**: Assistant text MUST render as GitHub-flavoured markdown with
  single newlines kept as line breaks — agent output laid out one fact per line
  must not collapse into a run-on paragraph — and every fenced code block MUST
  offer a copy control, because the code is what a reader most often wants out
  of a reply.
- **FR-040**: A failed turn MUST replace the in-progress bubble with a single
  inline error banner in the flow above the composer — never a floating notice
  and never two error surfaces at once — carrying a Retry that re-sends the
  message that failed and a dismiss that clears it.
- **FR-041**: The page MUST let the owner read and set the conversation's agent
  configuration — which agent it runs on, which model that agent is put on, and
  how hard that model thinks — over `GET|PATCH .../agent-config`, persisting
  both while preserving the conversation's working directory and upstream
  session id, and reverting to the agent's own default when either is cleared; a
  body that mentions one leaves the other where it was. The reasoning level is a
  SECOND control beside the model picker, not a variant of it: the agents take
  it as their own field rather than as part of the model name, and it renders
  only when the chosen model reports levels — nothing to choose between means no
  control at all, not a disabled or empty one. Both controls MUST be offered on
  the **draft** surface as well as in an open conversation, because the first
  turn is the one a user most wants to pitch, and by the time the conversation
  exists that turn is already running. A missing Coffer LLM connection MUST NOT
  block the page: with none configured the draft surface still accepts a message
  and the turn runs on the agent's own built-in model and login, because a
  Coffer connection is an optional override, not a prerequisite (spec
  [provider-switching](../provider-switching/spec.md), and the 2026-06-22
  amendment of [Provider Switching](../../docs/decisions/provider-switching.md)).
- **FR-042**: The draft is not a conversation row. The page opens on a blank
  draft surface, and the **first send** is what creates the conversation — so a
  user who opens the page and changes their mind leaves nothing behind. Where no
  managed agent is available at all, the draft MUST be replaced by a state
  saying how to get one rather than by a composer that can only fail.
- **FR-043**: The model picker MUST be a fixed dropdown, never free text. Its
  options are the union, deduped by id, of the agent's own catalogue, the active
  connection's introspected models, and the **current value** — which MUST stay
  selectable whatever else the union contains, so a conversation never shows a
  picker that cannot represent the model it is actually on.

### H. What a turn carries into the agent

- **FR-044**: The turn task MUST re-materialise a turn's attachments by reading
  them back from the last user message in the persisted history, not from a
  parameter threaded down from whoever accepted the message. The persisted
  reference — path, mime, filename, with the bytes left on disk — is the single
  source of truth, so materialisation survives a daemon restart and stays
  consistent with what the page shows. Each adapter then materialises the
  reference in its own native shape (a vision agent inlines the content, a
  path-native agent receives the path), and the path itself MUST NOT reach the
  wire: only the adapter, which has to read the bytes, ever sees it. See
  [Persisted Attachment Reference](../../docs/decisions/persisted-attachment-reference.md)
  and [Channel Media](../../docs/decisions/channel-media.md).
- **FR-045**: An audio attachment MUST be turned into a **transcript** folded
  into the turn's prompt before the adapter builds its request, because the
  shipped agents cannot hear audio. The transcription engine is injected behind
  a seam and consumes the speech-to-text connection and model (spec
  [internal-engine](../internal-engine/spec.md) FR-025) — its OWN connection,
  flagged `transcribe_default`, never the one Coffer's engine runs on. This is
  the one place in Coffer where user content may leave the machine, and it is
  **off by default**: with no connection marked for transcription, no model
  chosen for it, an unsupported protocol, or a credential that will not resolve,
  nothing is uploaded and the audio is handed to the agent as an ordinary file
  instead. Transcription that yields nothing degrades the same way; it never
  wedges or fails the turn.
- **FR-046**: A document attachment (PDF, office formats, epub, rtf) MUST be
  extracted to text and folded into the turn's prompt the same way, so a
  path-native agent sees its content instead of a note about a binary it cannot
  parse, and a vision agent does not waste it as an image. Images stay
  vision-inlined and audio stays transcribed; only documents take this path. The
  extractor is an optional dependency — absent, or on any extraction failure,
  the document degrades to being handed over as a file attachment.
- **FR-047**: The appends an agent receives on top of its own prompt MUST be
  composed in **one** place, shared by every provider, in a fixed order: the
  note telling a channel-driven agent it is on a chat channel; then, for a
  channel-driven turn only, the memory digest, whose content is memory's own
  (spec [memory](../memory/spec.md) FR-0NN) and whose injection point is this
  one; then the model note of FR-010, on every turn. Composing it here is what
  lets memory reach an agent with no session-start hook and no install — Coffer
  owns this turn's context itself. An agent the developer drives themselves
  receives memory through its own hook instead, never both.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Adding a third agent requires one registry entry and one adapter,
  and touches no conversation schema, no orchestrator code and no client
  (demonstrated by driving the platform against a scripted second provider in
  tests).
- **SC-002**: A turn started from any surface is observable, interruptible and
  continuable from every other surface, with no per-surface branch on the turn
  path.
- **SC-003**: No turn ever ends silently: every turn reaches a terminal event,
  and a daemon killed mid-turn leaves no conversation showing a reply that will
  never arrive.
- **SC-004**: From a fresh install with one managed agent present, a user opens
  the Chat page, sends a first message and receives a streamed reply without
  configuring a Coffer LLM connection first.
- **SC-005**: Every acceptance scenario below is covered by at least one test;
  `make verify` passes.

## Acceptance Scenarios

### Scenario: list available agents

- **Given** a running daemon,
- **When** the platform is asked which agents it offers,
- **Then** the managed agents (`claude_code`, `codex`) are listed, each with a
  display name and an availability flag, the `builtin` agent is **not** among
  them ([Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md)),
  and the list is reachable from the REST API.

### Scenario: choose an agent when starting a conversation

- **Given** a running daemon,
- **When** a conversation is created for a named managed agent with a working
  directory,
- **Then** the conversation records that agent and its configuration.

### Scenario: reject an unknown agent or invalid agent configuration

- **Given** a running daemon,
- **When** a conversation is created for an `agent_key` no agent provides, or
  with a working directory that is not an existing directory,
- **Then** each is rejected as a domain error and nothing is persisted. An
  *absent* working directory is not invalid — it defaults to the Coffer-managed
  workspace.

### Scenario: an unknown agent is a missing path, not a bad turn

- **Given** a running daemon,
- **When** the models of an `agent_key` no provider answers for are requested,
- **Then** the answer is 404, while the same key named as a turn's agent is
  rejected as `UNKNOWN_AGENT` with 400.

### Scenario: a resume id the agent has forgotten retries once as a fresh session

- **Given** a conversation carrying an upstream session id the agent no longer
  recognises,
- **When** a turn is started,
- **Then** the connect is retried once with no session id and the turn runs; a
  second failure is reported as a turn error rather than retried again.

### Scenario: every turn tells the agent which model it is on

- **Given** a conversation whose model has been set,
- **When** a turn is started,
- **Then** the agent's system context carries an authoritative note naming that
  model and listing what else it could be switched to; with no override set the
  note says the agent's own default is in use and names no model.

### Scenario: send a message and receive a streamed reply

- **Given** a conversation on a registered agent,
- **When** a turn is started,
- **Then** the turn's events stream in order — start, text deltas, completion —
  and the assistant reply is persisted.

### Scenario: observe a turn started from another surface

- **Given** a turn already running on a conversation,
- **When** a second subscriber attaches to that conversation's event bus,
- **Then** it receives the current turn's events from the beginning and then
  follows live, so a subscriber that arrives mid-turn misses nothing.

### Scenario: a completed turn is not replayed on top of its persisted rows

- **Given** a turn that has completed,
- **When** a subscriber attaches afterwards,
- **Then** it receives the latest pending-queue snapshot and no turn content,
  because that content is now loaded from history.

### Scenario: second message queues during a streaming turn

- **Given** a turn is streaming,
- **When** another message is sent on the same conversation,
- **Then** it is accepted and enqueued rather than rejected, and runs as its own
  turn after the current one ends.

### Scenario: editing a queued message re-queues it at the tail

- **Given** one or more messages queued behind a streaming turn, shown one per
  row,
- **When** a queued message is edited,
- **Then** it leaves the queue and returns to the draft surface to be amended,
  and re-sending it enqueues it at the tail of the pending queue.

### Scenario: a queued message runs after the current turn

- **Given** a message queued behind a running turn,
- **When** that turn completes,
- **Then** the queued message is committed as the next user message and its turn
  runs, one turn per queued message.

### Scenario: a reordered queue keeps each message's attachments

- **Given** a pending queue holding messages that carry attachments,
- **When** the queue is replaced with the same texts in a different order,
- **Then** each surviving message keeps its attachments and its originating
  client's renderer, and only a text that was not queued before becomes a new
  entry.

### Scenario: a queued turn that fails to start is held, not lost

- **Given** a message at the head of the pending queue whose turn cannot be
  started,
- **When** the platform tries to advance the queue,
- **Then** the message is put back at the head, the queue is paused, a turn
  error is published, and the message is still there when the owner resumes.

### Scenario: interrupting a turn pauses the pending queue

- **Given** a running turn with messages queued behind it,
- **When** the turn is interrupted,
- **Then** the current turn stops, and the queued messages are held rather than
  auto-run until they are resumed or dropped.

### Scenario: stop a running turn

- **Given** a turn that has streamed partial text and is still running,
- **When** it is interrupted,
- **Then** the stream ends with a terminal turn-done carrying stop reason
  `interrupted`, and the partial assistant message is persisted as complete.

### Scenario: a crashed turn leaves no message stuck streaming

- **Given** an assistant row left in `streaming` by a daemon that died mid-turn,
- **When** the daemon starts again,
- **Then** the startup sweep flips that row to `failed`, and the conversation
  reopens showing a failed reply rather than one still arriving.

### Scenario: turn state is released when nothing needs it

- **Given** a conversation whose turn has ended, with no queued message and no
  subscriber attached,
- **When** the platform settles,
- **Then** that conversation's turn state is dropped rather than retained for
  the daemon's lifetime.

### Scenario: reply survives a restart

- **Given** a completed turn,
- **When** the daemon is restarted and the conversation is read back,
- **Then** the assistant reply is there — the message store, not the live
  stream, is the system of record.

### Scenario: a long conversation is not loaded whole

- **Given** a conversation holding more than two hundred messages,
- **When** a turn is started,
- **Then** the adapter is given the most recent two hundred and no more.

### Scenario: a conversation the owner named keeps its name

- **Given** a conversation the owner has renamed,
- **When** its first user message arrives,
- **Then** the conversation keeps the name the owner gave it, and only a
  conversation still under its placeholder title is named from its first
  message.

### Scenario: the conversation list is ordered by activity, not by creation

- **Given** two conversations created in order,
- **When** a turn starts on the older one and then completes,
- **Then** it heads the active listing both while the turn runs and after it
  ends.

### Scenario: manage conversations

- **Given** a running daemon,
- **When** conversations are created, renamed, and deleted,
- **Then** each operation persists and the listing reflects it; a deleted
  conversation and its messages are removed.

### Scenario: archive and restore a conversation

- **Given** a conversation in the active listing,
- **When** it is archived,
- **Then** it leaves the default (active) listing, appears in the archived
  listing, and is not destroyed; unarchiving returns it to the active listing.
  Archiving a conversation that does not exist is rejected.

### Scenario: an archived conversation opens read-only

- **Given** an archived conversation,
- **When** it is opened on the Chat page,
- **Then** its history reads normally, the composer and the agent/model/effort
  controls are disabled, and a restore control is offered.

### Scenario: a stale conversation link says so

- **Given** a link to a conversation that has been deleted,
- **When** it is opened,
- **Then** the page says the conversation is gone and offers a way to start a
  new one, rather than silently showing the draft surface.

### Scenario: a just-sent prompt is shown before its row lands

- **Given** an open conversation,
- **When** a message is sent,
- **Then** it appears in the thread immediately and is replaced by its persisted
  row when that arrives — and is dropped when the turn settles even if no row
  ever claims it, so no duplicate bubble is left behind.

### Scenario: a dropped event stream reconnects and is bounded

- **Given** an open conversation whose event subscription drops mid-turn,
- **When** the client recovers,
- **Then** it re-subscribes with a backoff and replays the in-flight turn; after
  a bounded number of failed attempts it stops and reports the error.

### Scenario: a failed turn offers a retry in the thread

- **Given** a turn that fails,
- **When** the thread renders it,
- **Then** the in-progress bubble is replaced by one inline banner in the flow,
  carrying a Retry that re-sends the failed message and a dismiss.

### Scenario: the draft creates the conversation on first send

- **Given** the Chat page with no conversation open,
- **When** the first message is sent from the draft surface,
- **Then** the conversation is created by that send and the turn runs in it;
  opening the draft and leaving creates nothing. With no managed agent
  available, the draft is replaced by a state saying how to get one.

### Scenario: the model picker always offers the current value

- **Given** a conversation set to a model the agent's catalogue does not list,
- **When** the model picker is opened,
- **Then** the current value is among the options and is selected, and the
  picker accepts no free text.

### Scenario: model selection is recorded

- **Given** a conversation whose model has been set,
- **When** a turn completes,
- **Then** the assistant message records the model that produced it.

### Scenario: chat runs on the built-in model when no connection

- **Given** a running daemon with no Coffer LLM connection configured for the
  agent,
- **When** the Chat page is opened,
- **Then** the draft surface is available with no blocking empty state, and a
  sent turn runs on the agent's own built-in model and login — a Coffer
  connection is an optional override, not a prerequisite.

### Scenario: token usage is recorded on the assistant message

- **Given** a turn that completes,
- **When** the turn ends,
- **Then** the assistant message records the turn's token usage.

### Scenario: a channel message waits in the conversation's own queue

- **Given** a turn running on a paired channel's conversation, with a web tab
  subscribed to it,
- **When** the peer sends more messages and the web sends one too,
- **Then** they wait on the one pending queue in arrival order — the web's
  pending chips show the channel's messages — and run as consecutive turns

### Scenario: a stop from the chat holds the queued messages

- **Given** a turn running with a channel message queued behind it,
- **When** the peer sends `/stop`,
- **Then** the turn ends as interrupted and the queued message is held, and the
  peer's next message resumes the queue in order

### Scenario: an agent stream that ends without a terminal is a turn error

- **Given** an agent whose event stream ends without a completion event,
- **When** the turn is driven,
- **Then** exactly one terminal event follows, a `stream_ended` turn error, with
  the text streamed before the cut delivered ahead of it

### Scenario: a silent turn is cancelled by the idle watchdog

- **Given** an agent that streams part of a reply and then produces nothing,
- **When** the idle window passes,
- **Then** the turn ends with a `turn_timeout` error, the agent's cancellation
  path runs, and the partial reply is kept on a message marked failed

### Scenario: an errored turn still delivers what it streamed

- **Given** a turn that streamed text before failing,
- **When** the channel renders it,
- **Then** the chat receives the text, then the error notice, then the failed
  summary

### Scenario: a later turn re-materialises the attachment from history

- **Given** a user message carrying a persisted attachment reference,
- **When** a later turn runs on that conversation,
- **Then** the attachment is read back from history and handed to the adapter,
  which materialises it in its own native shape.

### Scenario: an inbound voice message is transcribed for a text-only agent

- **Given** a connection marked for transcription, a speech-to-text model, and
  an audio attachment on a turn,
- **When** the turn is built,
- **Then** the audio is transcribed and folded into the prompt; with either half
  unset nothing is uploaded and the agent receives the file instead.

### Scenario: a PDF reaches a path-native agent as extracted text

- **Given** a document attachment on a turn,
- **When** the turn is built,
- **Then** its text is extracted and folded into the prompt; with no extractor
  available the document is handed over as a file instead.

### Scenario: a channel-driven turn carries the memory digest

- **Given** a conversation driven from a channel and a memory digest to deliver,
- **When** the turn's system context is composed,
- **Then** the channel note, the memory digest and the model note are appended in
  that order; a conversation with no channel receives the model note only.

## Assumptions

- **The platform ships no CLI, and that is a known gap.**
  `backend/coffer/surfaces/cli/main.py` registers no `chat` command group, so
  conversations, the pending queue and the agent-provider registry are reachable
  over REST and from the web page only. [`.agents/sdd.md`](../../.agents/sdd.md)
  requires every management operation to be reachable from **both** REST and the
  CLI; this spec does not honour that rule and records the divergence here
  rather than leaving it to be rediscovered. The quickstart is consequently
  browser-driven where every other spec's is `coffer`-driven.
- **Two route prefixes, one spec.** `/api/v1/chat` carries everything about a
  conversation; `/api/v1/agent-providers` carries the registry itself, because
  its subject is the adapters that can drive a turn and not the `agent` resource
  rows `/api/v1/agents` serves. The second prefix is deliberate, not a boundary
  violation.
- **The model catalogue arrives through a port, not an import.** The agent kind
  answers it (spec [agent-registry](../agent-registry/spec.md)); the composition
  root publishes that service into chat's dependencies as a catalogue port,
  because the import-linter fence forbids chat from importing the agent kind.
  The route is chat's, the answer is not.
- **Single-daemon by design.** The event bus and the pending queue are
  in-process; a restart drops queued messages that have not been committed
  (FR-018) and flips in-flight turns to failed (FR-021). Chat state does not
  converge across machines.
- **A conversation may be pointed at from outside with no foreign key.** The
  channel kind keeps its own table mapping a chat thread to a conversation id;
  that pointer is soft and may dangle. Chat neither maintains it nor validates
  it — a conversation is created, listed and deleted on its own terms.
- **Attachment bytes are not chat's storage.** The media directory and its prune
  belong to whoever downloaded the file (spec
  [channels](../channels/spec.md)); chat persists only the reference and reads
  the bytes at turn time (FR-044).
