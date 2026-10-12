# A Burst of Channel Messages Is One Turn, Released After a Per-Channel Quiet Window

**Status**: Accepted
**Date**: 2026-09-28
**Deciders**: Yuxing Wu
**Related**: spec channels ("Take a burst of messages as one turn"); spec channels/seatalk ("Hand a chat's events to the channel in arrival order"); spec channels/telegram ("Debounce an album into one turn"); [A Channel Conversation Is Keyed by (Channel, Chat, Thread)](channel-conversation-identity.md), [Channels Are Thin Transport Adapters](channel-adapter-framework.md), [SeaTalk Inbound Is One Outbound WebSocket](seatalk-websocket-inbound.md); research note [IM agent bridges](../research/im-agent-bridges.md) ("Bursts are batched by a quiet window"); PR #439

## Context

A person on a phone rarely says everything in one message. They forward a chat
record and then type "look into this", or send a question and a correction
right behind it. A channel that turns every inbound message into its own turn
makes the agent answer the forwarded record on its own, then answer "look into
this" in a second turn — two answers to one question, the first of them a guess.
Messages sent while a turn runs had the same problem: two corrections typed
during a long turn became two queued turns.

Order matters as much as grouping. SeaTalk's websocket ingested each event in
its own task, and ingesting is not uniform: a forwarded record downloads its
files, a quote is resolved over HTTP. So a record sent first could reach its
conversation after the text sent behind it, and the agent answered "look into
this" without the record.

The person must still see at once that each message was heard, and a command
such as `/stop` must act now, not after a delay.

## Options Considered

### Option A — Hold each message for a quiet window that restarts on every new message, then release the burst as one turn (chosen)

`InboundBurst` (`application/channel/inbound_burst.py`) holds messages per
`(channel, chat, thread)`. Each message re-arms a timer; when the chat has been
quiet for the window, the held messages become one turn: every message's text in
arrival order, every attachment, and one origin block taken from the last
message (the reply attaches to and mentions whoever spoke last). The window
depends on what arrived last: `wait_after_text_seconds` (default 1.5 s) after
text, `wait_after_forward_seconds` (default 5 s) after a message that is rarely
the whole ask — a forwarded record, or files without text. Both are the
channel's own settings, 0–60 s; 0 makes every such message its own turn.

Around it:

- **Acknowledge on arrival.** The receipt mark (a reaction, or typing) is sent
  when a message is held, not when the window closes, and every message of the
  burst carries the turn's later marks.
- **Commands are never held.** A command first releases what its chat and
  thread hold, so the turn it follows runs first; `/stop` instead drops the
  held messages, which had not started.
- **Messages during a running turn** are coalesced the same way before they
  join the conversation's pending queue.
- **Order is fixed at the transport.** Arrival order is known only where the
  frame is read, so SeaTalk chains each chat's ingest behind the previous one
  for that chat (`group_id` or DM `employee_code`); different chats still run
  concurrently. Telegram's poller already hands updates over one at a time.

Pros: one question gets one answer, including the forward-then-ask pattern;
the window costs at most its length once per burst; nothing about it is
platform-specific except ordering, which only the transport can do.

Cons: every plain message waits the text window before its turn starts; a
person who pauses longer than the window still splits a thought; the right
window is personal, which is why it is a setting.

Wins because the latency is small and bounded, and it fixes the common case
the per-message design got wrong.

### Option B — One turn per message, queued in order (the design #439 replaced)

Each inbound message is its own turn; messages during a running turn queue as
separate turns.

Pros: no added latency; nothing to configure.

Cons: the agent answers half a question, then the other half; a correction
typed during a long turn becomes a turn of its own after the turn it
corrects; on SeaTalk, without ordering, the halves could even run in the wrong
order.

Loses on the forward-then-ask pattern, which is how people hand an agent a
problem from another chat.

### Option C — Steer new messages into the running turn

Inject a message that arrives while a turn runs into that turn, as OpenClaw's
default `steer` queue mode does.

Pros: a correction reaches the agent while it still matters.

Cons: it changes a turn already under way rather than the next one, so a turn
that has acted on the old instruction cannot take it back, and it bypasses the
turn platform's one-turn-at-a-time pending queue (spec chat) that the web page
and every channel share. It also does nothing for a burst that arrives before
any turn starts.

Loses because it solves a different problem (interrupting work) and still
leaves the idle-chat burst unsolved.

### Option D — Fixed constants instead of per-channel settings

The same two windows, hard-coded.

Pros: one less setting to document; nobody has to tune it.

Cons: how long a pause means "I'm done" is personal — someone who types
corrections in three quick lines wants longer, someone who sends one message at
a time wants none.

Loses on that: the first implementation used constants and they were made
settings within the same release.

### Option E — Batch only by content (a forward always waits for a follow-up, text never waits)

Hold only messages that are rarely complete on their own.

Pros: no delay on ordinary text.

Cons: a question followed by a correction is two turns again; the rule needs
the content of every possible message type to be classified.

Loses because the text window's cost (1.5 s) is small next to the cost of a
split answer, and a person who wants no delay sets it to 0.

## Decision

A channel holds each inbound message per `(channel, chat, thread)` for a quiet
window that restarts on every new message and releases the burst as one turn.
The window is the channel's `wait_after_text_seconds` after text and
`wait_after_forward_seconds` after a forward or bare files, each 0–60 s.
Messages are acknowledged on arrival, commands release (or, for `/stop`, drop)
what is held, and messages during a running turn are coalesced the same way. A
transport hands one chat's events to the channel in arrival order.

Rules a future change must respect:

- Coalescing lives in the application layer and stays platform-independent;
  only ordering belongs to the transport.
- A receipt mark is never delayed by the window.
- A command is never held behind a window.

## Consequences

- A new transport must deliver one chat's events in order (serially per chat,
  concurrently across chats) and needs nothing else to get coalescing.
- Every plain message's turn starts at least the text window after it arrives.
- Enforced by: `application/channel/inbound_burst.py` (`window_for`,
  `merge_parts`), the per-chat ingest chain in
  `infrastructure/channel/seatalk_ws.py`, and the channel config fields in
  `domain/channel/config.py`.
