## RENAMED Requirements

- FROM: `### Requirement: Name a quoted message without fetching it`
- TO: `### Requirement: Ground a turn in the message it quotes`

## MODIFIED Requirements

### Requirement: Ground a turn in the message it quotes
A quoted message MUST reach the turn as content, not only as a reference. When
the user replies by quoting a message, the quoted message is folded into the
turn as `> sender: …` lines directly above the user's own text, so "repeat this"
or "as I said above" points at something the agent can read. The images and
files the quoted message carries are attached like a thread message's. A
platform that inlines the quote on the update itself has already folded it into
the message text. A platform that delivers only an id has the transport
resolve it with the bot's own credentials: such an id is scoped to the bot that
received it, so no tool the agent holds could resolve it. The origin block (see
"Open every turn with its message origin") still names the quoted message's
id. A lookup that fails leaves the turn as it was, with the id as the only
trace.

#### Scenario: a quoted message is named in the turn's origin
- **GIVEN** a paired channel whose inbound message quotes an earlier message
- **WHEN** the turn is built
- **THEN** the origin block names the quoted message's id

#### Scenario: a quoted message is folded into the turn
- **GIVEN** a paired group on a transport that resolves quotes, and the owner
  quotes an earlier message in the group main chat and @mentions the bot
- **WHEN** the turn is built
- **THEN** the quoted message's sender and text sit as a `> sender: …` line
  directly above the owner's own text
- **AND** no thread history is read, because the @mention roots a fresh thread

### Requirement: Reply in place inside threads
Threads MUST be read and replied-to in place, and a group reply always lands in
a thread — never the group main chat. A DM or group message sent in a thread
also replies into that thread, and so does the reply to a slash command sent
there. A thread is read in full: every message it holds, not a first page.
Reading *recent group-main* history is intentionally NOT done: the
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
