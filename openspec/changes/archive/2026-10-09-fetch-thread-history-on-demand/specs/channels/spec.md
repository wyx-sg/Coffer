## ADDED Requirements

### Requirement: Ground a thread turn in a bounded slice of the thread
A thread turn MUST fold a bounded slice of its thread, never the whole thread,
and never what the conversation it runs in already saw. On a transport that can
read thread history, a message that lands in a thread folds in:

- on the **first turn of a conversation in that thread** — a new conversation
  (the thread's first, after `/new`, after an idle rollover or a deleted
  conversation), or a conversation `/resume` switched to that has had no turn
  there — the thread's **20 most recent messages** other than the triggering
  message, the bot's earlier replies included, under `[Thread messages]`;
- on **every later turn of that conversation in that thread**, only the messages
  posted **since that conversation's previous turn there**, leaving out the bot's
  own replies and the triggering message, under
  `[New thread messages since your last turn in this thread]` — at most the 20
  most recent of them — and **nothing at all** when there are none.

Where the conversation is in each thread is a per-conversation cursor (the
message that triggered its latest turn there) kept in `runs.db`, so it survives a
daemon restart. A message that roots a fresh thread at itself reads nothing but
still sets the cursor; a read that fails folds nothing and leaves the cursor
where it was. A quoted message is folded as before ("Ground a turn in the message
it quotes"). See the [chat architecture](../../../docs-site/architecture/chat.md)
page for where the cursor is taken and claimed.

#### Scenario: a conversation's first turn in a thread folds the thread's latest messages
- **GIVEN** a paired group on a transport that can read threads, and a thread of
  25 earlier messages
- **WHEN** the owner @mentions the bot in that thread for the first time
- **THEN** the turn opens with `[Thread messages]` and the 20 most recent of those
  messages, and the triggering message is not among them

#### Scenario: a later turn folds only what was posted since the previous turn
- **GIVEN** a conversation that already had a turn in a thread, after which the
  bot replied and two other members posted
- **WHEN** the owner @mentions the bot in that thread again
- **THEN** the turn folds only the two members' messages, under
  `[New thread messages since your last turn in this thread]`, without the
  earlier messages, the bot's reply or the triggering message

#### Scenario: a later turn with nothing new folds no thread context
- **GIVEN** a conversation that already had a turn in a thread, after which only
  the bot posted
- **WHEN** the owner @mentions the bot in that thread again
- **THEN** the turn carries no thread block, only the owner's message

#### Scenario: a new conversation in the thread is seeded again
- **GIVEN** a thread whose conversation already had a turn there
- **WHEN** the owner sends `/new` in the thread and then @mentions the bot
- **THEN** the new conversation's first turn folds the thread's latest messages
  again under `[Thread messages]`

#### Scenario: the thread cursor survives a daemon restart
- **GIVEN** a conversation that had a turn in a thread
- **WHEN** the daemon's cursor store is opened afresh over the same `runs.db`
- **THEN** it still holds that conversation's place in the thread: the message
  that triggered its turn

### Requirement: Read a thread's earlier messages on demand
Coffer MUST give an agent in a channel turn the built-in tool
`coffer__channel_read_thread`, which reads a thread's messages page by page,
newest page first. It takes the `channel` (name or uid), `chat_id`, `chat_kind`
and `thread_id` the turn's origin block names, an optional `before` (a message
id: return messages older than it) and a `limit` (1–100, default 20). It returns
the page oldest first — each message's id, sender, time, text, whether the bot
sent it, and the local paths of the images and files it carries, downloaded with
the bot's credentials — plus whether older messages remain, the `before` value
that reads them, and the platform's note on what it cannot return. It reads only
through a channel running on this machine, only a thread of a chat that channel
has paired (the owner's direct chat, or a group the owner has addressed the bot
in), and never a chat's main history. On a platform with no history API it
fails saying so. It is turn-scoped like `coffer__ask`: listed to and served for
only an MCP session inside a turn Coffer runs.

#### Scenario: an agent pages back through a thread with the tool
- **GIVEN** a paired group thread of eight messages on a transport that can read
  threads, one of which carries an image
- **WHEN** the agent calls the tool with a limit of 3, then again with the
  returned `before`, then once more
- **THEN** the pages hold the three newest, the three before them (the image as a
  local file path), and the remaining two with no more to read

#### Scenario: the tool reads only threads of paired chats
- **GIVEN** a running channel
- **WHEN** the agent calls the tool for a chat the channel has not paired, without
  a thread id, or for a channel that is not running
- **THEN** each call fails with a message saying why and nothing is read

#### Scenario: the tool says a platform without a history API cannot be read
- **GIVEN** a Telegram channel
- **WHEN** the agent calls the tool for one of its threads
- **THEN** the call fails saying the platform has no history API

#### Scenario: the tool is offered only inside a Coffer turn
- **GIVEN** the daemon is running
- **WHEN** one MCP session inside a live Coffer turn and one outside any turn list
  tools and call `coffer__channel_read_thread`
- **THEN** only the session inside the turn sees and runs it; outside it is an
  unknown tool

## MODIFIED Requirements

### Requirement: Reply in place inside threads
Threads MUST be read and replied-to in place, and a group reply always lands in
a thread — never the group main chat. A DM or group message sent in a thread
also replies into that thread, and so does the reply to a slash command sent
there. A thread is read through every page the platform returns, and a turn
folds a bounded slice of it (see "Ground a thread turn in a bounded slice of the
thread"); the rest is read on demand ("Read a thread's earlier messages on
demand"). Reading *recent group-main* history is intentionally NOT done: the
addressed message is self-contained, and the permission to read a group's
back-chatter is not something this product asks for. How a thread is
identified, and whether its history can be fetched at all, is a platform fact
each child spec states. A quoted/replied message contributes a `> sender: …`
context prefix (see "Ground a turn in the message it quotes").

#### Scenario: the owner @mentions the bot inside a thread
- **GIVEN** a paired channel and a group chat with a thread, on a transport
  that can fetch thread history
- **WHEN** the owner @mentions the bot inside that thread
- **THEN** the thread's own messages are read and folded into the turn, and
  the reply is routed back into the same thread

#### Scenario: a group slash-command reply routes to the group/thread
- **GIVEN** a paired channel and a group chat/thread the owner has messaged in
- **WHEN** the owner sends a slash command (e.g. `/status`) inside that
  group/thread
- **THEN** the command's reply is routed with the same `chat_kind`/`thread_id`
  as the triggering message, not the DM defaults

### Requirement: Download the media a thread's messages carry
Thread-history media MUST be downloaded, not flattened to a dead link. When a
turn folds thread messages on a transport that can fetch thread history, the
media those **folded** messages carry is downloaded and attached to the turn,
alongside the flattened text, rather than surfacing only as an auth-gated
`[image] <url>` the agent could not open. Messages the fold leaves out are not
downloaded; a page the read tool returns has its own messages' media downloaded.

#### Scenario: thread-history images reach a vision agent
- **GIVEN** a paired channel and a group thread whose own messages include an
  image (a directly-sent one and one nested in a forwarded record)
- **WHEN** the owner @mentions the bot inside that thread
- **THEN** the thread's images are downloaded and attached to the turn — reaching
  the vision agent as real bytes, not a dead auth-gated file link

#### Scenario: only the folded messages' media is downloaded
- **GIVEN** a thread of more than 20 earlier messages, the oldest and one of the
  newest carrying an image
- **WHEN** the owner @mentions the bot in that thread for the first time
- **THEN** only the newer message's image is downloaded

### Requirement: Ground a DM thread's turn in the thread
A thread MUST ground its turn in a DM too, not only in a group. Direct chats with
a bot thread as well, and a transport that can fetch a DM thread does so — the
same bounded fold ("Ground a thread turn in a bounded slice of the thread"), the
same media download, the same degrade-to-nothing on any failure. The asymmetry
this removes was real and invisible: a DM thread was already replied to in place
(see "Reply in place inside threads") yet the turn driving that reply could not
see anything else in the thread. Group-*main* chatter is still never fetched.

#### Scenario: a DM thread grounds its turn in the thread's own messages
- **GIVEN** a paired direct chat on an adapter that supports history fetch, and a
  message arriving inside an existing thread
- **WHEN** the turn is built
- **THEN** the thread's own messages are fetched through the direct-chat thread
  endpoint and folded into the turn, exactly as a group thread's are

### Requirement: Say what a thread read cannot show
A thread's folded context MUST say what it does not show. SeaTalk's thread
endpoints return only replies sent in the last 7 days, and never whisper or
deleted messages; a root message is exempt from the window. A thread whose root
predates the window therefore reads as its root plus recent replies, however long
it looks in the app. A conversation's first fold in such a thread ends with a
note saying so, so the agent reports what it could not see instead of answering
as if the fragment were the whole thread. And whenever the fold leaves older
messages out, it ends with one line saying how many and how to read them: a
`coffer__channel_read_thread` call with the channel, chat id, chat kind, thread
id and `before` set to the oldest message shown.

#### Scenario: a thread older than the platform's 7-day reach says what it cannot show
- **GIVEN** a thread whose root was sent more than 7 days ago
- **WHEN** its context is fetched for a turn
- **THEN** the returned messages are followed by a note that SeaTalk returns only
  the last 7 days of replies and that older messages are not shown

#### Scenario: a fold that leaves out older messages says how to read them
- **GIVEN** a thread of 25 earlier messages
- **WHEN** a conversation's first turn there folds the latest 20
- **THEN** the block ends with a note that 5 earlier messages are not shown,
  naming `coffer__channel_read_thread` with the channel, the thread id and
  `before` set to the oldest message shown

### Requirement: Open every turn with its message origin
Every turn MUST carry its own origin. The turn text opens with a
`[Message origin]` block naming the platform, the channel (its current name,
which `coffer__channel_read_thread` takes), the chat (kind, the chat title where
the platform supplies one, and always the chat id), the thread, and the sender
(display name **and** the stable platform id, which a platform tool call takes
and which, in a group, appears nowhere else because `chat_id` is the group's) —
so an agent asked "which group is this?" answers from the turn it was given
instead of listing the bot's groups and inferring, and a platform tool call has a
chat id to aim at. The block is folded in after command detection (a prefixed
`/help` would stop being a command) and after the empty-envelope check, and is
folded into the turn's text exactly like thread context, so it stays one string
and the agent's own session records it. It rides on **every** turn, not just a
conversation's first: `/new <agent>` can swap the agent between conversations of
one thread (see "Drive every managed agent from one bot") and a resumed session
would otherwise lose it. Title and sender name are chat-member-settable, so both
are collapsed to one clipped line before they reach the prompt — a rename cannot
forge extra origin lines. Where a platform hands the chat title over for free it
is included; where it does not the chat is named by id alone, which an agent can
resolve to a name through the platform's own tools.

#### Scenario: a group turn names the group it came from
- **GIVEN** a paired channel whose owner @mentions the bot in a group thread
- **WHEN** the turn is driven
- **THEN** the turn text opens with a `[Message origin]` block naming the platform,
  the channel, the chat kind and title, the chat id, the thread id, and the sender

#### Scenario: a DM turn names its own chat
- **GIVEN** a paired channel and a DM from its owner
- **WHEN** the turn is driven
- **THEN** the origin block names the platform, the channel and the direct chat by
  id, omitting the thread line a DM has no value for

#### Scenario: every turn carries its origin
- **GIVEN** a paired channel that has already run one turn
- **WHEN** the owner sends a second message
- **THEN** that turn's text opens with its own origin block too — the provenance is
  not a first-turn-only header

#### Scenario: a slash command keeps its leading slash
- **GIVEN** a paired channel
- **WHEN** the owner sends `/help`
- **THEN** it is handled as a command (no origin block is prefixed, no conversation
  is created)

### Requirement: Tell a channel-driven agent it is on a chat channel
A channel-originated turn MUST tell the agent it is bridged to a chat channel,
not a terminal. The agent receives a short system-prompt note naming **where**
it is — the platform, the chat kind (direct chat, group chat, group thread) and
the channel by its current label — and **what renders there**, in the sentence
or two the running transport declares as its `render_notes` (SeaTalk: bold,
italic, inline code, code fences and lists, but no headings, links or tables;
Telegram: its rich Markdown, tables included). It then asks for a reply shaped
for a phone: do not narrate steps (Coffer already shows the working state); the
first line is the outcome in one sentence, because it becomes the notification;
at most about 15 lines, anything longer under a `## Details` heading; code blocks
under 30 lines, longer logs attached as files; diagrams and charts as PNG files,
never as source; and, when the agent needs a yes or a choice before it goes on,
to call `coffer__ask` (see "Ask the owner in the chat and take the chat's answer back to the agent").
Concise never drops evidence — an investigation's key log lines, error messages
and IDs are quoted verbatim — and the agent is told it cannot click permission
or confirmation dialogs on the user's computer. Where the running transport can
read threads, the note also names `coffer__channel_read_thread` for a thread's
earlier messages, with its arguments taken from the origin block. Web-UI turns
are unaffected — the note rides only on a conversation whose `channel_uid` is
set. A channel that has been deleted, or is not running, still gets the note,
saying less.

#### Scenario: the channel-driven agent is told it is on a chat channel
- **GIVEN** a channel-originated conversation
- **WHEN** a turn is driven from the channel
- **THEN** the agent receives a system-prompt note naming the platform, the chat
  kind and the channel, telling it not to narrate its steps, to quote an
  investigation's key evidence verbatim, and that it cannot click the user's OS
  dialogs, while a web-UI conversation gets no such note

#### Scenario: the note lists what renders on the platform the turn is on
- **GIVEN** a SeaTalk group-thread conversation on a running channel
- **WHEN** its turn's note is composed
- **THEN** it says the turn is in a SeaTalk group thread and that headings, links
  and tables do not render there (write one bullet per row)

#### Scenario: the note asks for the answer's shape
- **WHEN** a channel turn's note is composed
- **THEN** it asks for the outcome in one first sentence, long content under
  `## Details`, diagrams as PNG files, and a `coffer__ask` call when the agent
  needs the owner's answer

#### Scenario: the note names the thread-reading tool where threads can be read
- **GIVEN** a conversation on a running channel whose transport can read threads
- **WHEN** its turn's note is composed
- **THEN** it names `coffer__channel_read_thread` and the origin block its
  arguments come from, while a note for a transport that cannot read threads
  does not
