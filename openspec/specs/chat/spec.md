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

#### Scenario: a held queue is resumed from the page, not retried
- **GIVEN** a turn error that arrives on the event stream while no turn is
  running and messages are waiting in the pending queue
- **WHEN** the page shows that error
- **THEN** it is presented as a held queue with a Resume action that replaces the
  pending queue with itself (`PUT .../pending`), and offers no Retry that would
  send the last user message again

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

### Requirement: Show every conversation on the Conversations page
The web UI MUST carry a **Conversations** page (`/conversations`): the conversation list on the left and the selected conversation on the right. The list MUST show every
conversation Coffer runs, whatever opened it — a conversation an IM channel (SeaTalk, Telegram)
opened, and one opened from Coffer's own UI, which is modelled as a built-in source named
**Coffer** — shown as a list with no header row, grouped by day (**Today**, **Yesterday**, **Earlier**; the
group titles carry no counts) and newest activity first. A row MUST show the title, a status word
(**Running** with a success-coloured dot while a turn runs; **Needs you** with a warning dot while the
agent waits for an answer, when the conversation says so), the latest message's words on one muted
line, its **source** (the platform's logo and name with where in the chat it lives — `SeaTalk · DM`, a
group by its name when Coffer knows it, a thread or topic rather than the chat's main timeline, a
parallel thread as `DM · Thread 2` — or the Coffer mark and **Coffer**), the agent's badge and name, and
its last activity (the clock time for today and yesterday, a date such as `Sep 22` for earlier). Hovering
a row shows a leading checkbox and a trailing **⋯** menu (Rename, Archive, Delete…; an archived
conversation's menu is Unarchive, Delete…). Rename opens the conversation with its title already being
edited; Archive and Unarchive act at once and answer with a toast that has Undo; Delete… asks first,
naming the conversation, and says its messages are removed from Coffer while the files the agent changed
stay. The filter row reads, in order, an **Active / Archived** switch, a search box over titles and
message text (`/` focuses it), a **Source** pill (Coffer and each channel, several at once, each
channel shown as its platform's logo and `SeaTalk · Team bot`), an **Agent** pill, and **Clear filters**
once anything narrows the list; it shows no result count. The source and agent filters are applied by the server, so a filtered list pages through matches only. All of it is in the URL — `?q=`,
`?source=coffer,<channel uid>`, `?agent=`, `?archived=1` — so a filtered list is a link, and a channel's
**Conversations from this channel** link opens `?source=<uid>`; a link carrying the earlier
`?channel=<uid>` is read once as that source and the address rewritten. The first day group carries a
**Select all** checkbox in the rows' checkbox column — shown on hover, always while anything is ticked,
half-ticked while only some are — that ticks every conversation the view holds, reading the pages not
loaded yet first, and clears them when ticked again. Ticking a row (a shift-click
ticks the range) replaces the filter row with a selection bar — "3 of 8 selected", **Archive**
(**Unarchive** in the archived view), **Delete…** and **Clear** — and a bulk delete asks first, listing
the titles (five, then **Show all**). The list reads 30 conversations and then 50 more as it is
scrolled. With no conversation at all the page is its header and one message; with filters that match
nothing it says so and offers **Clear filters**; a list that fails to load shows the error in its own
area with **Retry**. A conversation's page MUST show the full exchange and a reply box
that continues it, whichever source opened it; **New conversation** is the header's primary action, and the
page opens on the list rather than on a welcome or suggestions page, which it does not have. The
composer carries no voice input: a voice message reaches an agent only through a channel, which
transcribes it (see "Transcribe audio attachments when transcription is configured"). There is no
web-only conversation kind: the page and the channel are two windows onto one timeline, driven by
one owner, and an agent cannot tell which window a turn arrived through.

#### Scenario: a channel's conversation is listed beside the web's with a badge
- **GIVEN** one conversation started from Coffer's own UI and one opened by an IM channel
- **WHEN** the Conversations page's list renders
- **THEN** both conversations are listed, the first with a Coffer badge and the second with a badge naming its channel
- **AND** filtering by that channel lists only the second

#### Scenario: a row names the chat and thread it came from
- **GIVEN** a conversation a SeaTalk direct chat opened, one a group thread opened, and one a `/thread` parallel conversation opened, whose turn is running
- **WHEN** the Conversations page's list renders
- **THEN** the first row's badge names SeaTalk and the direct chat, the second the group and its thread, and the third its `Thread N` mark
- **AND** each row shows its latest message's line, and the third is marked running

#### Scenario: rows are grouped by day without counts
- **GIVEN** conversations last active today, yesterday and weeks ago
- **WHEN** the Conversations page's list renders
- **THEN** the list has no header row and shows the groups Today, Yesterday and Earlier, none of them with a count
- **AND** a row from today shows its clock time and an earlier row its date

#### Scenario: the Source pill filters by several sources
- **GIVEN** conversations from Coffer and from two channels
- **WHEN** the user ticks Coffer and one channel in the Source pill
- **THEN** only those sources' conversations are listed, `?source=` names both, and Clear filters is offered
- **AND** a link carrying the earlier `?channel=<uid>` is read once as that source and its address rewritten to `?source=<uid>`

#### Scenario: a row's menu acts on one conversation
- **GIVEN** a conversation in the list
- **WHEN** the user opens its ⋯ menu
- **THEN** it offers Rename, Archive and Delete…, and Rename opens the conversation with its title being edited
- **AND** Archive acts at once with a toast that has Undo, and Delete… asks first, naming the conversation

#### Scenario: ticking rows replaces the filter row with a selection bar
- **GIVEN** a list of conversations
- **WHEN** the user ticks two rows
- **THEN** the filter row is replaced by "2 of N selected" with Archive, Delete… and Clear
- **AND** Delete… lists the two titles in its confirmation, and a list of more than five shows five and Show all

#### Scenario: Select all ticks every conversation the view holds
- **GIVEN** a view of 35 conversations of which the first 30 are loaded
- **WHEN** the user ticks Select all in the first day group
- **THEN** the remaining page is read and the bar reads "35 of 35 selected"
- **AND** with only some rows ticked Select all is half-ticked, and ticking it when all are ticked clears the selection

#### Scenario: a list that fails to load says so
- **GIVEN** the conversation list request fails
- **WHEN** the page renders
- **THEN** the list area shows an error with Retry, and Retry reads the list again

#### Scenario: a channel's conversation is continued from the page
- **GIVEN** a conversation a SeaTalk channel opened
- **WHEN** the user opens it on the Conversations page and sends a reply
- **THEN** the page shows the full exchange and the reply starts a turn in that same conversation

#### Scenario: the page opens on the list with no welcome page
- **GIVEN** conversations from two sources
- **WHEN** the user opens `/conversations`
- **THEN** it opens the Conversations list with New conversation as the header's primary action, with no welcome or suggestions page and no voice-input control in the composer

### Requirement: Put the open conversation in the URL
The open conversation MUST be part of the URL (`/conversations/:id`), so a refresh, a
deep link and a second tab all reopen the same thread. A link to a conversation
that no longer exists MUST say so explicitly, with a way back to a new draft —
never drop silently into the draft surface as though the link had been to
nothing.

#### Scenario: a stale conversation link says so
- **GIVEN** a link to a conversation that has been deleted,
- **WHEN** it is opened,
- **THEN** the page says the conversation is gone and offers a way to start a
  new one, rather than silently showing the draft surface.

### Requirement: Open an archived conversation read-only
An archived conversation MUST open **read-only**: its history reads normally,
the composer and the model control is disabled, and a restore
control is offered in their place. Archived is a state the owner leaves
deliberately, not a thread that silently accepts a turn and unarchives itself.

#### Scenario: an archived conversation opens read-only
- **GIVEN** an archived conversation,
- **WHEN** it is opened on the Conversations page,
- **THEN** its history reads normally, the composer and the model
  control is disabled, and a restore control is offered.

### Requirement: Recover a dropped event stream with bounded retries
A dropped event stream MUST be recovered by re-subscribing — the replay of
"Replay the in-flight turn to late subscribers" is what makes that safe — with
a backoff and a bounded number of attempts, so a hard failure surfaces as an
error the owner can act on rather than as a client hammering the endpoint.
When every attempt has failed, the reply that lost its stream MUST carry a
warning banner inside it, left-aligned with its text — "Lost the live stream
from the daemon", that the turn may still be running and that reloading shows
what it has written so far, and a Reload conversation action — and MUST stop
showing a typing cursor or "Thinking…"; a tool call with no result then reads
"Unknown" rather than Running.

#### Scenario: a dropped event stream reconnects and is bounded
- **GIVEN** an open conversation whose event subscription drops mid-turn,
- **WHEN** the client recovers,
- **THEN** it re-subscribes with a backoff and replays the in-flight turn; after
  a bounded number of failed attempts it stops and reports the error
  as a warning banner inside the reply, with Reload conversation and no typing
  cursor.

#### Scenario: an idle event stream is re-subscribed
- **GIVEN** an open conversation whose event subscription is closed while no turn
  is running, or whose connection fails
- **WHEN** the client recovers
- **THEN** it re-subscribes with a backoff, so a turn started later from any
  surface still streams; an HTTP error response such as 404 is reported and not
  retried

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
ride the event stream (see "Express a turn as typed events in memory") so a second tab,
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
that was just stopped. The stopped reply MUST say so at its end in a muted line,
"Stopped by you.", and its header reads "Stopped after 12s"; when a tool call
was still running at the stop, the line adds that the edit (for a file-writing
tool) or the command (for a shell tool) was not finished and that sending a
message continues — another tool adds nothing — and that call reads "Stopped"
rather than Running. The persisted reply carries the status `stopped`, so a
reload shows the same.

#### Scenario: the page stops a turn another surface started
- **GIVEN** a turn started by another surface, with a message queued behind it,
- **WHEN** the page calls `POST .../interrupt` for that conversation,
- **THEN** the turn stops with its partial output persisted,
- **AND** the queued message is held rather than auto-run.

#### Scenario: a stopped reply says it was stopped
- **GIVEN** a reply the user stopped while an edit tool call was still running
- **WHEN** the thread renders it, live or after a reload
- **THEN** its header reads "Stopped after" its length and its last line reads
  "Stopped by you. The edit was not finished; send a message to continue."

### Requirement: Render tool calls as cards
The message thread MUST render a turn's tool calls as their own cards rather
than as prose: each card names the tool, shows what it was called with, and
shows the result once one arrives, so a reader can see what the agent *did* and
not only what it said. Text and tool-call blocks appear in the order the turn
emitted them. A card whose result has not arrived yet reads as still running
(muted text with a spinner, no warning colour); a finished card reads
"Done · 0.3s" with the tool's duration when the daemon recorded one, and plain
"Done" when it did not; a failed card reads "Error"; and a card with no result
in a reply that was stopped or whose stream was lost reads "Stopped" or
"Unknown" instead.

#### Scenario: a tool call renders as a card between the text around it
- **GIVEN** an assistant message whose blocks are text, a tool call with its result, then more text, and a second tool call with no result yet
- **WHEN** the thread renders it
- **THEN** each tool call is a card naming its tool, placed between the text blocks in the order the turn emitted them
- **AND** opening the finished card shows what the tool was called with and its result
- **AND** the card with no result reads as still running

### Requirement: Summarise the files a reply changed
Under an assistant reply that is no longer streaming, the thread MUST show a
"Files changed" card listing each file the reply changed, with the lines added and
removed, read from the reply's recorded files (see "Keep the conversation index without its text"); a reply recorded before files were recorded falls back to the
files its tool calls wrote, with repeated edits to one file summed into one row. A
reply that changed no file shows no card. The card sits inside the reply, after
its text and before Copy reply, and its title carries no count.

#### Scenario: a reply's file edits are summed into one row per file
- **GIVEN** an assistant reply whose tool calls edit one file twice, write a second file, and read a third
- **WHEN** the thread renders it
- **THEN** the Files changed card lists the two written files only, one row each, with their added and removed line counts
- **AND** a reply with no file-writing tool call shows no card

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

### Requirement: Create the conversation on the first send
The draft is not a conversation row. **New conversation** opens a blank draft surface,
and the **first send** is what creates the conversation — so a user who opens
the page and changes their mind leaves nothing behind. Where no managed agent
is available at all, the draft MUST be replaced by a state saying how to get
one rather than by a composer that can only fail. That state says "No agent
connected", names Claude Code and Codex, and offers one **Open Agents** link to the
Agents page, where connecting an agent is Coffer's own action; it carries no install
prompt and no install command (handing an install to an assistant belongs to the
Agents page). The draft's title bar says "New conversation", and with an agent its
centre says which agent will run in which folder; the folder picker, agent and model
sit in the reply box's toolbar, and a draft opened from Ask an agent
says under the box that nothing is sent until Send. The folder picker lists Coffer's
workspace and the folders recent conversations started in, then one row for any
other folder: a field to type or paste a path whose one button reads **Choose…**
(the host's folder dialog) while the field is empty and **Use** once it holds a path.

When the conversation is created but the daemon refuses its first message (for
example `ATTACHMENT_NOT_FOUND`), the message MUST NOT be lost: its text and
attachment chips are put back into the new conversation's composer and the
refusal is shown in the thread's banner, without a Retry.

#### Scenario: the draft creates the conversation on first send
- **GIVEN** the Conversations page's New conversation draft,
- **WHEN** the first message is sent from the draft surface,
- **THEN** the conversation is created by that send and the turn runs in it;
  opening the draft and leaving creates nothing. With no managed agent
  available, the draft is replaced by a state saying how to get one.

#### Scenario: with no managed agent the draft links to the Agents page
- **GIVEN** no managed agent is available
- **WHEN** the user opens the New conversation draft
- **THEN** it says no agent is connected and offers Open Agents, which links to the Agents page, with no composer, no Copy prompt and no install command

#### Scenario: a draft's first message refused after its conversation is created keeps its text and files
- **GIVEN** the draft surface with typed text and an attached file
- **WHEN** the conversation is created and its first message is refused
- **THEN** the refusal is shown in the new conversation's thread with no Retry
- **AND** that conversation's composer holds the text and the file's chip, and sending from it carries the same file

### Requirement: Offer models from a fixed dropdown that keeps the current value
The model picker MUST be a fixed dropdown, never free text. It MUST always lead
with a **Default** option, which clears the conversation's model so the agent
runs its projected default and is what the picker shows while no model is set.
After it come the models the platform offers for the agent
([provider-switching](../provider-switching/spec.md) "Serve one model list to
every surface": the agent's own catalogue, or the curated
`text` ids of the connection the agent runs on, when it runs on one — a
connection that curates models, none of them `text`, offers none) and the **current value** — which MUST stay
selectable whatever that list contains, so a conversation never shows a picker
that cannot represent the model it is actually on. Those are the only options:
the page does not introspect a connection's endpoint itself.

#### Scenario: the model picker always offers the current value
- **GIVEN** a conversation set to a model the agent's catalogue does not list,
- **WHEN** the model picker is opened,
- **THEN** the current value is among the options and is selected, and the
  picker accepts no free text
- **AND** the Default option is offered first, alongside the catalogue's models.

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

### Requirement: Attach files from the Conversations page composer
The Conversations page's composer MUST let the owner attach files three ways: an attach
button that opens the file picker, dropping files onto the composer, and
pasting an image. While files are dragged over it, only the reply box changes
— an accent border and the placeholder "Drop to attach" — with no overlay over
the page. Each attached file MUST show as a chip with its name, its size and a
control that removes it, and it MUST be uploaded at once, the chip saying so
while it uploads. A file over 20 MB, or one past the tenth, MUST NOT be
attached or uploaded: it is dropped, and one line under the reply box says
"<file> was not attached: <reason>. Up to 10 files, 20 MB each." — the limits
appear nowhere else. A file the daemon refuses on upload (an unsupported type)
MUST stay on its chip with the reason and is never sent. Send MUST be disabled
while any upload is in flight or failed, so a message never leaves without a
file its owner attached; a message with only attachments may be sent. Sending
clears the chips, and the files travel with the message by the ids their
uploads returned.

#### Scenario: attaching a file shows a chip and sends it with the message
- **GIVEN** an open conversation on the Conversations page
- **WHEN** the owner attaches a file with the attach button and sends a message
- **THEN** a chip with the file's name and size appears, and the message is sent with that file's upload id
- **AND** the chips are cleared after the send

#### Scenario: send waits for uploads in flight
- **GIVEN** a file whose upload has not finished
- **WHEN** the owner looks at the composer
- **THEN** its chip says it is uploading and Send is disabled until the upload finishes

#### Scenario: a failed upload says why and is not sent
- **GIVEN** a file the daemon refuses
- **WHEN** its upload fails
- **THEN** its chip shows the reason and Send is disabled
- **AND** removing the chip enables Send again

#### Scenario: a file past the limits is not attached and the reply box says why
- **GIVEN** the composer of an open conversation
- **WHEN** the owner picks a file over 20 MB
- **THEN** nothing is uploaded and no chip appears
- **AND** one line under the reply box names the file, the reason and the limits

#### Scenario: a pasted image is attached
- **GIVEN** the composer has focus
- **WHEN** the owner pastes an image
- **THEN** it is attached and uploaded like a picked file

### Requirement: Show where a reply will also be sent
The Conversations page MUST tell the owner, before they send, where a reply to a channel's
conversation will also go — the source in the title bar beside the conversation's title
("SeaTalk · coffer-dev › thread"), which means replies typed here also go there — or that
it will stay in Coffer ("Replies stay in Coffer", with the reason one tap away), and MUST
mark each reply the channel has not received yet as not delivered to that channel until it
is, in a quiet warning line under the message: "Not delivered to SeaTalk yet · will retry".
The reply box carries no line of its own about this.

#### Scenario: the Conversations page shows where a reply also goes
- **GIVEN** an open conversation a channel opened, with one reply not yet delivered
- **WHEN** the page renders its composer
- **THEN** the title bar names the source the reply will also be sent to, and the
  undelivered reply is marked as not delivered to that channel

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

### Requirement: Answer a question in the conversation
While a reply waits on a question, its header MUST read "Waiting for you" and a
question card MUST sit at the end of the reply, above the reply box: the context
(markdown, a diff as a code block), each question with its options as equal
buttons — a single-choice tap answers, a multi-select question toggles its
options and sends them with Submit — with each option's description under its
label, and the line "<agent> is waiting for your answer.". Text sent from the reply box
while a question is pending MUST answer the first unanswered question instead of
queueing a message; the box's placeholder says so ("Reply, or answer with the
buttons above"). In a channel conversation the card notes it was also asked in
that chat. An answered question MUST collapse to one line, "✓ <question> ·
Answered: <answer> · HH:MM", adding "in <platform>" when it was answered in the
chat, and a cancelled one to "Not answered".

#### Scenario: a multi-select question is answered with Submit
- **GIVEN** a pending question with three options and multi-select on
- **WHEN** the owner toggles two options and presses Submit
- **THEN** the agent receives both labels, and the card collapses to one line naming them

#### Scenario: text typed while a question waits is the answer
- **GIVEN** a pending question
- **WHEN** the owner types "only on staging" and sends it
- **THEN** the question is answered with that text and no message is queued

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

### Requirement: Open a changed file's diff in a drawer
A row of "Files changed" whose reply has a recorded diff MUST open a drawer on the
right, 640 wide and starting under the title bar, holding that file's diff for
that reply: the path with its added and removed counts, "<n> of <N>" with previous
and next file and a close control (Esc closes too), and the diff with old and new
line numbers, hunk headers and added and removed lines marked. The open file's row
MUST be highlighted in the card. A reply recorded before this existed keeps its
estimated rows, which open nothing.

#### Scenario: the drawer walks the reply's files
- **GIVEN** a reply with two changed files, both with diffs
- **WHEN** the owner clicks the first row and then next file
- **THEN** the drawer shows "1 of 2" with the first file's diff, then "2 of 2" with the second's, and the second row is highlighted
- **AND** Esc closes the drawer

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

### Requirement: Let the owner set agent and model
The page MUST let the owner choose the agent a conversation runs on, on the
draft surface — once the conversation exists its agent is fixed and shown as a
label, because its upstream session and working directory belong to that one
agent (see "Record the agent on each conversation"). The page MUST let the owner
read and set the conversation's model over
`GET|PATCH .../agent-config`, persisting it while
preserving the conversation's working directory and upstream session id, and
reverting to the agent's own default when it is cleared. The model picker MUST
be offered on the **draft** surface as well as in an open
conversation, because the first turn is the one a user most wants to pitch, and
by the time the conversation exists that turn is already running. The page
offers no reasoning-effort control: the agent runs at the effort its own
configuration names.

A missing Coffer LLM connection MUST NOT block the page: with none configured
the draft surface still accepts a message and the turn runs on the agent's own
built-in model and login, because a Coffer connection is an optional override,
not a prerequisite ([provider-switching](../provider-switching/spec.md), and
[Provider Connections Projected Into Agent Config](../../../docs/decisions/provider-connections-projected-into-agent-config.md)).

#### Scenario: chat runs on the built-in model when no connection
- **GIVEN** a running daemon with no Coffer LLM connection configured for the
  agent,
- **WHEN** the Conversations page is opened,
- **THEN** the draft surface is available with no blocking empty state, and a
  sent turn runs on the agent's own built-in model and login — a Coffer
  connection is an optional override, not a prerequisite.
