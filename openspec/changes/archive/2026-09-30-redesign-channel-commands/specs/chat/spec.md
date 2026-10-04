## ADDED Requirements

### Requirement: Mirror a web reply into the channel it came from
A message the owner sends from the Chat page into a conversation an IM channel
opened MUST also reach that channel, so the phone sees the whole conversation
and not only its own half. The message goes to the chat and thread the
conversation belongs to — never anywhere else, and never a group's main chat —
marked as coming from Coffer (`(from Coffer) <text>`), and the agent's answer to
it is delivered to the channel exactly as the answer to a message typed there
would be. Only the send route mirrors; a Retry resends on the web alone.

Where the conversation lives decides whether it can be mirrored at all: a direct
chat (and any of its threads) and a group thread can; a group's main chat
cannot, and a reply there stays in Coffer. When the channel cannot send right
now — it is not running on this machine, or the platform refused — the reply is
kept, the conversation lists it as not delivered to that channel, the agent's
answer is collected behind it, and both are delivered, oldest first, once the
channel is running again. A reply is never dropped because a send failed. The
send is answered with what happened to the mirror: `sent`, `pending` (kept for
later) or `kept` (stays in Coffer); `null` for a conversation no channel opened.

This is the chat half of the channel's own return address (see
[Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md)):
chat declares the port, the channel kind implements it, and chat never imports
the channel kind.

#### Scenario: a web reply reaches the channel chat marked as from Coffer
- **GIVEN** a conversation a paired channel opened in a direct chat
- **WHEN** the owner sends a message to it from the Chat page
- **THEN** the channel chat receives the message prefixed `(from Coffer) `, and
  the send answers `sent`

#### Scenario: the agent's answer to a web reply is delivered to the channel
- **GIVEN** a conversation a paired channel opened
- **WHEN** the owner sends a message to it from the Chat page and the agent answers
- **THEN** the answer is delivered into the same channel chat and thread

#### Scenario: a web reply to a group main-chat conversation stays in Coffer
- **GIVEN** a conversation bound to a group's main chat
- **WHEN** the owner sends a message to it from the Chat page
- **THEN** nothing is sent to the group, the send answers `kept`, and the turn
  still runs on the web

#### Scenario: a reply the channel cannot send is kept and retried
- **GIVEN** a conversation a channel opened, while that channel is not running
- **WHEN** the owner sends a message to it from the Chat page, the agent answers,
  and the channel starts again
- **THEN** the send answers `pending`, the conversation lists the reply as not
  delivered, and once the channel runs the reply and then the answer are
  delivered and no longer listed

#### Scenario: the conversation says where a reply will also go
- **GIVEN** a conversation a channel opened in a direct chat's parallel thread
- **WHEN** a client reads the conversation
- **THEN** its channel binding says a reply is deliverable and names the target,
  the platform and the thread's mark

### Requirement: Show where a reply will also be sent
The Chat page MUST tell the owner, before they send, where a reply to a channel's
conversation will also go — "Also sends to SeaTalk · 🧵#1 deploy check" — or that
it will stay in Coffer, and MUST mark each reply the channel has not received yet
as not delivered to that channel until it is.

#### Scenario: the Chat page shows where a reply also goes
- **GIVEN** an open conversation a channel opened, with one reply not yet delivered
- **WHEN** the page renders its composer
- **THEN** the composer says where the reply will also be sent, and the
  undelivered reply is marked as not delivered to that channel
