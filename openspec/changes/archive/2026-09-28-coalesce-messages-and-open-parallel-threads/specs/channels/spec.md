## ADDED Requirements

### Requirement: Take a burst of messages as one turn
Messages that arrive in quick succession in one chat and thread MUST become one
turn, not one turn each. A person who forwards a chat record and then types
"look into this" asked one question. The channel waits for a short quiet
window after each message before it starts the turn, and a message arriving
inside the window restarts it. The window is 1.5 seconds after a text message.
It is 5 seconds after a message that is rarely the whole ask: a forwarded chat
record, or files with no text.

The coalesced turn carries:
- every message's text, in arrival order;
- every attachment;
- one origin block, taken from the last message, which is also what the reply
  attaches to and mentions.

Every message is still acknowledged when it arrives (see "Acknowledge receipt
and completion by capability"), never only when the window closes. Messages
sent while a turn is running are coalesced the same way before they join the
conversation's pending queue.

A slash command is never held. It first releases what its chat and thread are
holding, so the turn it follows still runs first. `/stop` is the exception:
it drops the held messages instead, since they had not started.

#### Scenario: a forwarded record and its follow-up become one turn
- **GIVEN** a paired direct chat
- **WHEN** the owner forwards a chat record and, two seconds later, sends "look into this"
- **THEN** one turn runs, and its text holds the forwarded record followed by "look into this"
- **AND** both messages were acknowledged when they arrived

#### Scenario: messages further apart than the window are separate turns
- **GIVEN** a paired direct chat
- **WHEN** the owner sends a text message and sends another one after the window has closed
- **THEN** each message drives its own turn, in arrival order

#### Scenario: /stop drops messages still being held
- **GIVEN** a message waiting in its quiet window
- **WHEN** the owner sends `/stop` before the window closes
- **THEN** the waiting message never becomes a turn

### Requirement: Open parallel conversations in a direct chat
A direct chat MUST be one conversation, and the owner MUST be able to open
further conversations beside it deliberately:
- `/thread [title]` opens a **parallel thread**. It is a thread in the direct
  chat with a conversation of its own, and the owner talks to it by replying
  inside that thread. How the thread is created is a platform fact each child
  spec states.
- Each parallel thread is numbered per chat, and it MUST carry the mark
  `🧵#N title` (title defaulting to `Task`) wherever it is shown: the thread's
  root message or topic name, the conversation's title on the web, `/status`
  inside it, and `/threads`.
- `/threads` answers how many parallel threads the chat has, and lists each
  one's mark, agent, and whether a turn is running, waiting, or idle, newest
  first.
- `/thread` in a group answers that every group thread is already its own
  conversation, and opens nothing.

A thread in a direct chat that `/thread` did not open is, on a platform where
such threads are casual replies, part of the direct chat's conversation. It is
still answered inside that thread.

#### Scenario: /thread opens a marked parallel conversation
- **GIVEN** a paired direct chat whose conversation is mid-task
- **WHEN** the owner sends `/thread deploy check`
- **THEN** a thread marked `🧵#1 deploy check` appears in the chat
- **AND** a message in that thread runs in a new conversation titled `🧵#1 deploy check`, while the direct chat's own conversation is untouched

#### Scenario: /threads counts and lists the parallel threads
- **GIVEN** a direct chat with two parallel threads, one of them running a turn
- **WHEN** the owner sends `/threads`
- **THEN** the answer says there are two parallel threads and lists both marks, each with its agent and its state

## MODIFIED Requirements

### Requirement: Answer the conversation commands from any paired chat
Commands `/new`, `/stop`, `/status`, `/help` MUST work from any paired chat.
`/new` starts a fresh conversation with the thread's current agent (its sticky
`/agent` choice while that agent is still inside the channel's scope, else the
channel's default agent), `/stop`
interrupts the running turn, `/status` reports the active conversation, agent,
and turn state (and the parallel thread's mark inside one), and `/help` lists the commands. `/stop` and `/new` take effect
even while a turn is running; other messages join the conversation's pending
queue (spec `chat` — the one the web shows; the channel refuses past 10 waiting
and tells the peer the channel is busy) and run in order, a burst of them
arriving as one turn (see "Take a burst of messages as one turn"). A message arriving
exactly when the previous turn finishes joins the queue rather than racing it:
turns for one conversation never overlap.

These are the commands that need nothing of the conversation; the ones that
configure the conversation the chat is bound to — `/agent`, `/model`, `/effort`
— are specified in "Switch the conversation's agent from chat" and "Switch the
model and reasoning effort from chat", `/save` in "Save a sent document into
a collection", and `/thread` and `/threads` in "Open parallel conversations in a
direct chat". All of them live on one roster (see "Register the bot's command
menu and profile from one roster"), so none of the lists derived from it can go
stale.

#### Scenario: /new starts a fresh conversation
- **GIVEN** a paired channel with an active conversation
- **WHEN** the peer sends `/new`
- **THEN** a new conversation with the thread's current agent (the default
  agent when none was chosen, or when the chosen one has since left the
  channel's scope) becomes active and the old one remains in history

#### Scenario: /stop interrupts a running turn
- **GIVEN** a turn in progress
- **WHEN** the peer sends `/stop`
- **THEN** the turn ends as interrupted and the chat is responsive again

#### Scenario: messages during a turn are queued in order
- **GIVEN** a turn in progress
- **WHEN** the peer sends two more messages further apart than the quiet window
- **THEN** they run as consecutive turns in arrival order after the first ends

#### Scenario: the queue is bounded and overflow is reported
- **GIVEN** a full message queue
- **WHEN** the peer sends another message
- **THEN** the message is dropped and the peer is told the channel is busy

### Requirement: Key conversation identity by channel, chat and thread
Each group thread MUST be its own conversation. Conversation identity is keyed
by `(channel, chat_id, thread_id)`, not by the peer alone. A DM (`thread_id=""`)
is one conversation; each thread in a group is independent — its own history and
its own turn lock. Concurrent turns in different threads of one group do not
collide on a single conversation. Pairing/owner identity stays on the peer row.

In a direct chat the key's thread is the thread only when that thread is a
conversation of its own: a parallel thread `/thread` opened, or any thread on a
platform where a direct-chat thread only exists because someone created it
(Telegram's private-chat topics). Any other direct-chat thread keys to the DM's
`""` conversation (see "Open parallel conversations in a direct chat"). The key
decides which conversation a message joins; the reply still goes to the thread
the message came from.

#### Scenario: each group thread is an independent conversation
- **GIVEN** a paired channel and a group whose threads share one `chat_id`
- **WHEN** the owner drives a turn in thread A and, before it finishes, a turn
  in thread B
- **THEN** the two threads resolve to two different conversations, both turns
  run concurrently, and neither is refused with "a turn is already running"

#### Scenario: a casual direct-chat reply-in-thread keeps the direct chat's conversation
- **GIVEN** a paired SeaTalk direct chat with an active conversation
- **WHEN** the owner replies inside a thread under one of the bot's answers, a thread `/thread` did not open
- **THEN** the turn runs in the direct chat's conversation, with its context
- **AND** the reply is posted inside that thread
