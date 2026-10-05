## REMOVED Requirements

### Requirement: Persist conversations and messages in SQLite
**Reason**: Coffer keeps no second copy of a conversation's text. The agent's own session record is the conversation, and `chat_messages` beside it was duplicated state that drifted from it.
**Migration**: None for the person: the text is still in Claude Code or Codex. What stays is the conversation index, specified in "Keep the conversation index without its text", which also carries the title rule this requirement held. Migration `0149` drops `chat_messages`, `chat_reply_files` and `archived_at`; its downgrade recreates them empty.

### Requirement: Bound turn context to the most recent 200 messages
**Reason**: A turn is no longer given Coffer's message history at all, so there is nothing to bound. Every adapter resumes the agent's own session.
**Migration**: See "Let the agent's own session hold the conversation".

### Requirement: Archive and delete idle conversations on a retention schedule
**Reason**: Coffer no longer archives conversations (there is no archived state) and no longer deletes them on a schedule; the conversation text it would have pruned is not stored. Deleting a conversation is the owner's act, made through the agent.
**Migration**: The two retention policy rows are deleted by migration `0149`. A person who wants an old conversation gone uses "Rename and delete a conversation through its agent"; the agent's own clean-up (Claude Code's `cleanupPeriodDays`) removes old sessions by itself.

### Requirement: Register conversation retention in the framework registry
**Reason**: Both conversation retention entries are removed with the schedule they registered.
**Migration**: None. The registry keeps every other entry; see [resource-framework](../resource-framework/spec.md) "Retain attachments on an adjustable policy" for the one other entry this change narrows.

### Requirement: Sweep streaming rows left by a crashed daemon
**Reason**: A turn no longer writes a `streaming` placeholder row, so a crash leaves no row to sweep.
**Migration**: None. A daemon that dies mid-turn leaves the agent's own session as the agent recorded it; the next channel message continues that session.

### Requirement: Put the open conversation in the URL
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). There is no open conversation, so no conversation URL.
**Migration**: `/conversations/:id` and `/conversations/new` are gone; `/conversations` is the list. Open the conversation from its row in the terminal ("Open a conversation in the terminal"); a person who wants a reply in the chat uses the channel.

### Requirement: Create, rename, archive, unarchive and delete conversations
**Reason**: Coffer no longer creates conversations from the web or archives them. Rename and delete move to the agent's own operations.
**Migration**: See "Rename and delete a conversation through its agent". Archive and Unarchive have no replacement.

### Requirement: Open an archived conversation read-only
**Reason**: There are no archived conversations and no conversation view to open read-only.
**Migration**: None.

### Requirement: Send fire-and-return and stream output over one subscription
**Reason**: The web composer that posted `POST .../messages` is removed; channels reach the turn platform in-process, not over HTTP.
**Migration**: `POST /api/v1/chat/conversations/{id}/messages` is removed. The events subscription (`GET .../events`) stays and is specified by "Replay the in-flight turn to late subscribers".

### Requirement: Recover a dropped event stream with bounded retries
**Reason**: This was the page's recovery for its own conversation view, which no longer exists.
**Migration**: None. A client that subscribes to the events route re-subscribes on its own terms; the platform's replay on attach is unchanged.

### Requirement: Show a just-sent prompt immediately
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: None; there is no web composer.

### Requirement: Keep the draft surface open during a turn
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). Queued rows were the composer's view of the pending queue; `PUT .../pending` goes with them.
**Migration**: The queue itself stays ("Queue messages sent during a turn"); it is fed by channels only.

### Requirement: Interrupt the watched turn from the page
**Reason**: The page no longer watches a turn. Stopping a running turn is now the inline Stop on a list row.
**Migration**: See "Show channel conversations on the Conversations page"; `POST .../interrupt` and its semantics ("Pause the pending queue on interrupt") are unchanged.

### Requirement: Render tool calls as cards
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: Open the conversation from its row in the terminal ("Open a conversation in the terminal"); a person who wants a reply in the chat uses the channel.

### Requirement: Summarise the files a reply changed
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: Open the conversation from its row in the terminal ("Open a conversation in the terminal"); a person who wants a reply in the chat uses the channel.

### Requirement: Render assistant text as GitHub-flavoured markdown
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: Open the conversation from its row in the terminal ("Open a conversation in the terminal"); a person who wants a reply in the chat uses the channel.

### Requirement: Show a failed turn as one inline banner with Retry
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). Coffer also no longer holds the failed message to resend, so `POST .../messages/{id}/resend` and `ATTACHMENT_EXPIRED` go.
**Migration**: A channel turn that fails still tells the chat through the channel's renderer; the owner sends the message again from the chat.

### Requirement: Create the conversation on the first send
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). Conversations are created by a channel's first message.
**Migration**: None. "Offer and run only managed agents" keeps the rule that a turn for an unmanaged agent is refused.

### Requirement: Offer models from a fixed dropdown that keeps the current value
**Reason**: The Conversations page has no model control. The owner sets a conversation's model with `/model` in the channel ([channels](../channels/spec.md) "Switch the model from chat"), and the agent's catalogue is still served by `GET /api/v1/agent-providers/{agent_key}/models`.
**Migration**: Use `/model` in the chat. [provider-switching](../provider-switching/spec.md) "Choose a model from a fixed list" is updated to match.

### Requirement: Re-materialise attachments from persisted history
**Reason**: A message is no longer persisted, so there is no history to read the attachment back from. The attachment travels with the turn that carries it.
**Migration**: See "Let the agent's own session hold the conversation"; the adapters still materialise an attachment in their own native shape.

### Requirement: Search the conversation list by title and message text
**Reason**: Message text is not stored, so it cannot be searched. Search over the list now matches title and working directory.
**Migration**: See "List conversations by latest activity" (`q`) and "Show channel conversations on the Conversations page".

### Requirement: Upload a file for a web message
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). `POST /api/v1/chat/attachments` and `~/.coffer/content/chat-media` are removed.
**Migration**: A file reaches an agent through a channel, which downloads it to the channel media directory.

### Requirement: Send uploaded files with a web message
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). `attachment_ids` goes with the send route.
**Migration**: As above.

### Requirement: Prune uploaded chat media on the retention cadence
**Reason**: There are no web uploads and no `chat-media` directory to prune. The channel media directory stays under the `attachments` policy.
**Migration**: See [resource-framework](../resource-framework/spec.md) "Retain attachments on an adjustable policy", which names the channel directory only.

### Requirement: Attach files from the Conversations page composer
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: As above.

### Requirement: Show a message's attachments in the thread
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal"). `GET .../attachments/{attachment_id}` is removed.
**Migration**: None.

### Requirement: Mirror a web reply into the channel it came from
**Reason**: A reply is no longer typed on the web, so nothing is mirrored into a channel, and the not-delivered state for such replies goes with it.
**Migration**: Reply in the chat itself, or open the session in the terminal.

### Requirement: Show where a reply will also be sent
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: None.

### Requirement: Answer a question in the conversation
**Reason**: The question cards on the web page are removed. A question is answered in the channel only.
**Migration**: Answer in the chat: [channels](../channels/spec.md) "Ask the owner in the chat and take the chat's answer back to the agent". The question's lifecycle is "Pause a turn on a question for the owner".

### Requirement: Record what each reply changed in each file
**Reason**: Per-reply diffs were stored beside the reply text in `chat_reply_files`; both are removed. The agent's own session and the working tree record what changed.
**Migration**: Use `git diff` or the agent's own interface.

### Requirement: Open a changed file's diff in a drawer
**Reason**: The Conversations page no longer shows or drives a conversation. Coffer is not a second agent (principles, IV. AI-Native): the Claude desktop app and Codex already are the chat client, and the page saw almost no use. The page is now a list that hands a row to the agent's own interface ([chat](../chat/spec.md) "Open a conversation in the terminal").
**Migration**: As above.

### Requirement: Let the owner set agent and model
**Reason**: Both controls were the page's. The agent is fixed per conversation when a channel opens it and the model is set with `/model` in the chat. The rule that a missing Coffer LLM connection blocks nothing is unchanged and stays with [provider-switching](../provider-switching/spec.md): the turn runs on the agent's own login.
**Migration**: `GET|PATCH /api/v1/chat/conversations/{id}/agent-config` is removed. Use `/model` and `/dir` in the chat.

### Requirement: Reconcile a replaced queue against existing entries
**Reason**: Only the Conversations page replaced the queue (`PUT .../pending`, reorder and drop). Channels only append to the queue and `/stop` pauses it, so nothing reconciles a replacement.
**Migration**: `PUT /api/v1/chat/conversations/{id}/pending` is removed. A person who wants to drop queued messages sends `/new` or `/stop` in the chat.

### Requirement: Keep each agent adapter self-contained
**Reason**: The adapter is no longer handed the conversation history, which this requirement named as its input; the rule that an adapter is self-contained and the orchestrator injects nothing moves, unchanged, into the requirement that says what a turn is given.
**Migration**: See "Let the agent's own session hold the conversation" (scenario "the orchestrator hands an adapter only the turn" replaces "the orchestrator hands an adapter only the history").

### Requirement: Record the model an adapter reports
**Reason**: Its scenario recorded the model on the assistant message, which Coffer no longer stores; the retitled requirement keeps the optional read.
**Migration**: See "Read the model an adapter reports without requiring it" ("a reported model reaches the turn's log line" replaces "model selection is recorded").

### Requirement: Hold a queued turn that fails to start
**Reason**: One of its scenarios, and its closing sentence, described the Conversations page resuming a held queue, which no longer exists; the retitled requirement resumes it from the chat.
**Migration**: See "Hold a queued turn that fails to start until the chat writes again"; the scenario "a held queue is resumed from the page, not retried" is dropped.

### Requirement: Replay without double-rendering
**Reason**: Its scenario rested on a turn's content being persisted and loaded from history, which is no longer so.
**Migration**: See "Drop a finished turn's replay buffer" ("a completed turn is not replayed" replaces "a completed turn is not replayed on top of its persisted rows").

### Requirement: Keep a turn's record in its conversation, not the audit log
**Reason**: A turn's record is no longer a stored conversation but the agent's own session; the audit-log rule is unchanged.
**Migration**: See "Leave a turn's record to the agent's own session, not the audit log" ("a turn leaves no audit row and no stored text" replaces "a turn is recorded in its conversation and not in the audit log").

### Requirement: Keep partial output when a turn is interrupted or fails
**Reason**: Partial output is no longer persisted on a message row, so the persistence, the once-a-second save and the crash recovery go; delivering the partial text and a single terminal event stays.
**Migration**: See "Deliver partial output as events when a turn is interrupted or fails"; the scenario "a daemon that dies mid-turn keeps what was streamed" is dropped and "a shutdown keeps the partial reply" becomes "a shutdown stops running turns first".

### Requirement: Show every conversation on the Conversations page
**Reason**: The page now lists channel conversations only and opens rows in a terminal; it no longer shows the Coffer-opened conversations, message previews, bulk selection or the archived view.
**Migration**: See "Show channel conversations on the Conversations page" (scenarios "a channel's conversation is listed beside the web's with a badge", "ticking rows replaces the filter row with a selection bar", "Select all ticks every conversation the view holds" and "a channel's conversation is continued from the page" are dropped; "the Source pill filters by several sources" becomes "the Channel pill filters by several channels").

### Requirement: Express a turn as typed events
**Reason**: Its scenarios described the web page's event stream (`GET /api/v1/chat/conversations/{id}/events`) and its generated wire models; the route had no consumer once the page went and is removed. The in-memory event vocabulary the channels render stays, in "Express a turn as typed events in memory".
**Migration**: None for the person. A client of the removed SSE route follows the turn through the channel it came from.

### Requirement: Use the wire event name as the type discriminator
**Reason**: There is no event wire any more: the SSE route and its contract models are removed with the page.
**Migration**: None.

## MODIFIED Requirements

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

### Requirement: List conversations by latest activity
Conversations MUST list newest-activity first, and a conversation's activity
timestamp MUST be bumped both when a turn **starts** and when it **finalises**
— a long turn moves its conversation to the top of the list when it begins, and
is still ordered correctly when it ends. The listing holds the conversations a
channel opened and nothing else — there is no archived listing and no conversation
without a channel. It MUST page by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor")
with the conversation id as the tie-break, so a conversation whose activity is
bumped while a reader pages moves to the head rather than appearing twice.
It MUST narrow, in the server — the page and its `total` both — by channel
(`source`: a comma-separated set of channel uids), by agent (`agent`: a
comma-separated set of agent keys) and by a search (`q`): a case-insensitive
substring of the conversation's title or working directory, compared with the
query trimmed, a blank query listing every conversation. A cursor MUST be bound
to the `q`, source and agent filters it was issued for.

Each listed conversation carries its title, agent, working directory, activity
time, channel binding (platform and where in the chat it lives), whether it has a
native session yet, and the two in-memory flags `running` (a turn is in flight)
and `needs_you` (a question waits on the owner). It carries no message text.

#### Scenario: the conversation list is ordered by activity, not by creation
- **GIVEN** two conversations created in order
- **WHEN** a turn starts on the older one and then completes
- **THEN** it heads the listing both while the turn runs and after it ends

#### Scenario: the conversation list pages by cursor
- **GIVEN** three channel conversations
- **WHEN** the listing is read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two with the latest activity and the second the third, with a `null` `next_cursor`
- **AND** both pages report a `total` of 3

#### Scenario: the conversation list narrows by source and agent on the server
- **GIVEN** conversations opened by two channels, run by different agents
- **WHEN** the listing is read with `source=<channel uid>` and with `agent=<key>`
- **THEN** the page and `total` hold only the matching conversations, and a cursor issued for one set of filters is `CURSOR_INVALID` for another

#### Scenario: search matches titles and working directories
- **GIVEN** channel conversations titled "Alpha rollout" and "Gamma", the second running in `/work/alpha-api`
- **WHEN** the listing is read with `q` " alpha "
- **THEN** both are listed and `total` is 2
- **AND** a `q` found in neither a title nor a directory lists nothing, because no message text is stored or searched

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

## ADDED Requirements

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

### Requirement: Show channel conversations on the Conversations page
The web UI MUST carry a **Conversations** page (`/conversations`) that is a list
and nothing else: it has no conversation view, no reply box and no New
conversation action. The list MUST show the conversations IM channels (SeaTalk,
Telegram) opened — what the conversation index holds with a channel — as a
list with no header row, grouped by day (**Today**, **Yesterday**, **Earlier**; the
group titles carry no counts) and newest activity first. A row MUST show the title, a status word
(**Running** with a success-coloured dot while a turn runs; **Needs you** with a warning dot while the
agent waits for an answer, when the conversation says so), its **source** (the platform's logo and name
with where in the chat it lives — `SeaTalk · DM`, a group by its name when Coffer knows it, a thread or
topic rather than the chat's main timeline, a parallel thread as `DM · Thread 2`), the agent's badge and
name, its working directory, and its last activity (the clock time for today and yesterday, a date such
as `Sep 22` for earlier). A running row carries an inline **Stop**, which calls
`POST .../interrupt` for that conversation with the semantics of "Pause the pending queue on
interrupt". Every row carries the split button of "Open a conversation in the terminal", and hovering a
row shows a trailing **⋯** menu (Rename, Delete…). Rename edits the title in place in the row — Enter saves,
Esc cancels — through "Rename and delete a conversation through its agent"; Delete… asks first, as
that requirement says. The row shows no message text, because Coffer stores none.

The filter row reads, in order, a search box over titles and working directories (`/` focuses it), a
**Channel** pill (each channel, several at once, shown as its platform's logo and `SeaTalk · Team bot`),
an **Agent** pill, and **Clear filters** once anything narrows the list; it shows no result count. The
channel and agent filters and the search are applied by the server, so a filtered list pages through
matches only. All of it is in the URL — `?q=`, `?source=<channel uid>[,<channel uid>]`, `?agent=` — so a
filtered list is a link, and a channel's **Conversations from this channel** link opens `?source=<uid>`; a link
carrying the earlier `?channel=<uid>` is read once as that source and the address rewritten. The list
reads 30 conversations and then 50 more as it is scrolled, and refreshes when the window regains focus and
on the change feed's chat events. With no conversation at all the page is its header and one message; with
filters that match nothing it says so and offers **Clear filters**; a list that fails to load shows the
error in its own area with **Retry**. The page opens on the list rather than on a welcome or suggestions
page, which it does not have, and its header has no primary action.

#### Scenario: a channel's conversations are listed with the channel's badge
- **GIVEN** conversations opened by two IM channels
- **WHEN** the Conversations page's list renders
- **THEN** every conversation is listed with a badge naming its channel
- **AND** filtering by one channel lists only that channel's

#### Scenario: a row names the chat and thread it came from
- **GIVEN** a conversation a SeaTalk direct chat opened, one a group thread opened, and one a `/thread` parallel conversation opened, whose turn is running
- **WHEN** the Conversations page's list renders
- **THEN** the first row's badge names SeaTalk and the direct chat, the second the group and its thread, and the third its `Thread N` mark
- **AND** each row shows its agent and working directory, and the third is marked running

#### Scenario: rows are grouped by day without counts
- **GIVEN** conversations last active today, yesterday and weeks ago
- **WHEN** the Conversations page's list renders
- **THEN** the list has no header row and shows the groups Today, Yesterday and Earlier, none of them with a count
- **AND** a row from today shows its clock time and an earlier row its date

#### Scenario: the Channel pill filters by several channels
- **GIVEN** conversations from three channels
- **WHEN** the user ticks two channels in the Channel pill
- **THEN** only those channels' conversations are listed, `?source=` names both, and Clear filters is offered
- **AND** a link carrying the earlier `?channel=<uid>` is read once as that source and its address rewritten to `?source=<uid>`

#### Scenario: a row's menu acts on one conversation
- **GIVEN** a conversation in the list
- **WHEN** the user opens its ⋯ menu
- **THEN** it offers Rename and Delete… and nothing else, and Rename edits the title in place in the row
- **AND** Delete… asks first, naming the conversation

#### Scenario: a list that fails to load says so
- **GIVEN** the conversation list request fails
- **WHEN** the page renders
- **THEN** the list area shows an error with Retry, and Retry reads the list again

#### Scenario: a search that matches nothing is not an empty list
- **GIVEN** a conversation list holding one conversation
- **WHEN** the owner searches for text no title or directory contains
- **THEN** no conversation is listed and the list says nothing matches
- **AND** it does not show the empty-list message, and the search box keeps the query

#### Scenario: an empty conversation list offers no search
- **GIVEN** a list with no conversations
- **WHEN** the conversation list renders
- **THEN** it shows the empty-list message and no search box

#### Scenario: the page opens on the list with no welcome page
- **GIVEN** conversations from two channels
- **WHEN** the user opens `/conversations`
- **THEN** it opens the Conversations list with no welcome or suggestions page, no New conversation action and no reply box

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
A row of the Conversations page MUST hand its conversation to the agent's own
interface: pressing the row, or the main part of its split button **Open in
terminal**, MUST ask the daemon to resume the conversation's native session in the
person's preferred terminal ([web-ui](../web-ui/spec.md) "Let the user choose a
terminal"; [daemon](../daemon/spec.md) "Open an agent session in a terminal") —
`claude --resume <session id>` for Claude Code and `codex resume <session id>` for
Codex, in the session's working directory. The split button's **▾** menu holds
**Copy command**, which copies the same command line for the person to run
anywhere. A conversation that has no native session yet — no turn has run on it —
cannot be opened: its split button is disabled and says why, and it offers no
Copy command. An open the daemon refuses shows its reason in a toast beside Copy
command as the way out. Agent › Sessions rows use the same row and the same
behaviour ([agent-registry](../agent-registry/spec.md) "Open an agent's sessions from its Sessions tab").

#### Scenario: a row opens its session in the preferred terminal
- **GIVEN** a Claude Code conversation with a native session `abc-123` in `/work/api` and a preferred terminal
- **WHEN** the user presses its row
- **THEN** the daemon is asked to open `claude --resume abc-123` in `/work/api` in that terminal, for the conversation's agent
- **AND** a Codex conversation is opened as `codex resume <id>` the same way

#### Scenario: copy command copies the resume command
- **GIVEN** a conversation with a native session
- **WHEN** the user opens the ▾ menu and chooses Copy command
- **THEN** the command line for resuming that session in its directory is copied

#### Scenario: a conversation with no native session cannot be opened
- **GIVEN** a conversation on which no turn has run
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
