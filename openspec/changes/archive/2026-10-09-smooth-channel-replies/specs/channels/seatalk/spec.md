## ADDED Requirements

### Requirement: Show only typing while a turn runs
A SeaTalk turn MUST show its progress through the typing indicator alone (see
"Keep a typing heartbeat alive in DMs and group threads"): the transport
declares no live surface (`supports_live_text` false), so nothing is posted
while the turn runs and no message stream is ever opened. When the turn ends the
reply goes out as new messages — in a direct chat, ordinary text messages
rendered as SeaTalk markdown and cut at paragraph boundaries, every message after
the first opening with its place, `(2/3)`; in a group, withdrawable cards (see
"Send group replies as withdrawable cards").

SeaTalk can stream a message, but its client re-types the whole message whenever
a snapshot changes anything already on screen — a step line shifting, the clock
— so a reply that carries the turn's progress flickers on every step. And a
message created when the turn began notifies nobody when it is finished, so a
long turn needed a second message to say it had ended. Typing says the turn is
alive at no cost, and the answer, sent when it is ready, notifies.

#### Scenario: a seatalk direct turn shows typing and then one new message
- **GIVEN** a SeaTalk direct chat and a turn whose agent narrates, runs a tool and
  then answers
- **WHEN** the turn runs and ends
- **THEN** the typing indicator is sent, no stream request is made, and one text
  message carries the answer alone

#### Scenario: a long seatalk reply goes out as numbered messages
- **GIVEN** a SeaTalk reply longer than one message holds
- **WHEN** it is sent
- **THEN** it is cut at paragraph boundaries into messages headed `(2/3)`, `(3/3)`
  after the first

#### Scenario: a seatalk transport offers no live surface
- **WHEN** the SeaTalk transport's capabilities are read and a live surface is
  asked for, in a direct chat or a group thread
- **THEN** it declares none and opens none, and no stream request reaches the
  platform

## MODIFIED Requirements

### Requirement: Keep a typing heartbeat alive in DMs and group threads
SeaTalk has **no reaction to ack with** and no live surface, so it MUST keep a
periodic **typing heartbeat** alive (an ephemeral action, zero chat clutter) for
the whole turn: it is the only sign of progress until the reply lands. It runs wherever the turn is, DM or
group thread alike: SeaTalk has a thread-scoped group typing endpoint
(`group_chat_typing`) beside the direct-chat one, and the heartbeat was DM-only
purely on the belief that no such endpoint existed. The gate is the receipt
mechanism, not editing. Best-effort — a failed heartbeat never breaks the turn.

#### Scenario: a supports_typing-only DM keeps the typing indicator alive during a long turn
- **GIVEN** a paired channel on an adapter that can show typing but cannot edit,
  in a direct chat
- **WHEN** a long turn runs
- **THEN** the typing indicator is re-sent periodically for the turn's duration
  (an ephemeral action, no chat clutter), and is stopped when the turn ends

#### Scenario: a group turn is acknowledged by typing in the group
- **GIVEN** a paired group on an adapter that can type and has no reactions
- **WHEN** the owner @mentions the bot in a thread of that group
- **THEN** the typing indicator is sent to the group typing endpoint carrying
  that group's id and that thread's id — not to the direct-chat endpoint

### Requirement: Send group replies as withdrawable cards
SeaTalk has no delete API, but a card its bot sent can be rewritten by that bot for 7
days ([channels](../spec.md) "Withdraw a bot reply on the owner's command"). So a
reply in a **group** MUST be sent as interactive cards and never as plain text,
which cannot be rewritten. While the turn runs the group sees only the typing
indication (see "Show only typing while a turn runs"); a direct chat's reply is
ordinary text. The reply is
markdown rendered as SeaTalk's own, in description blocks of at most 1000 characters
(a card holds up to four such blocks here), cut on paragraph and never inside a code
fence; a reply that does not fit one card runs on into further cards, numbered
`(2/3)` after the first, and the 🗑 button rides on the last. Every card id is
reported so the whole reply can be withdrawn.

Withdrawing rewrites each card through Update Message into a neutral "🗑 Withdrawn"
card with no buttons and no title; the adapter declares a window of 7 days and that
withdrawing does not remove the message. Past 7 days the platform refuses and the
core tells the owner privately.

#### Scenario: a group reply is cards with the trash button on the last
- **GIVEN** a SeaTalk group reply longer than one card holds
- **WHEN** it is sent
- **THEN** it goes out as interactive cards, never as text, each card id is reported, and only the last carries the 🗑 button

#### Scenario: a short group reply is one card with markdown rendered
- **GIVEN** a SeaTalk group reply of a few lines with bold text and a code fence
- **WHEN** it is sent
- **THEN** one card carries it rendered as SeaTalk markdown

#### Scenario: withdrawing rewrites each card blank
- **GIVEN** a SeaTalk reply sent as several cards
- **WHEN** it is withdrawn
- **THEN** each card is rewritten through Update Message into a "🗑 Withdrawn" card with no buttons

#### Scenario: a seatalk group turn does not stream
- **GIVEN** a SeaTalk channel and a group turn
- **WHEN** the capabilities are read
- **THEN** no live surface is offered, withdrawing takes up to 168 hours, and withdrawing does not remove the message

## REMOVED Requirements

### Requirement: Stream the reply under SeaTalk's streaming contract
**Reason**: SeaTalk replies are no longer streamed (see "Show only typing while a turn runs"): the client re-types the whole message on every change, so a reply that carried the turn's progress flickered, and a stream created at the turn's start notified nobody when it finished.
**Migration**: None. A direct-chat turn shows typing and then sends its answer as ordinary messages; the `COFFER_SEATALK_STREAM_INTERVAL` setting is gone.

### Requirement: Ping a long turn's end into its thread
**Reason**: The ping made up for an answer that did not notify, because it finished a stream opened when the turn began. The answer is now a new message, which notifies on its own ([channels](../spec.md) removed "Ping the asker when a long turn ends" for the same reason).
**Migration**: None.

### Requirement: Number the messages after the stream
**Reason**: There is no stream to count as part one. A long reply is numbered like any other cut reply (see "Show only typing while a turn runs").
**Migration**: None.

### Requirement: Post a reply's details into the card's thread
**Reason**: The details summary card is gone ([channels](../spec.md) removed "Offer a reply's details behind a summary card"); a reply's `## Details` section goes out as ordinary text.
**Migration**: A Details button on a card sent before the change no longer does anything when tapped.
