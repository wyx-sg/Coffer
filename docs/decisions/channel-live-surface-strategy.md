# A Channel Turn Shows Progress on a Preview Surface Where One Exists, and the Reply Is the Answer Alone

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: spec channels ("Show a turn's progress on one live surface", "Show a turn's working state as one status line", "Stream through the platform's own surface where the chat has one", "Acknowledge receipt and completion by capability", "Summarise a turn that did not end normally", "Stop the turn from the platform's own stop control");
spec channels/telegram ("Stream through a message draft in direct chats only", "Use a deleted status message as the live scaffolding");
spec channels/seatalk ("Show only typing while a turn runs", "Keep a typing heartbeat alive in DMs and group threads");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md);
PRs #354, #356, #357

## Context

A managed-agent turn can run for minutes — tool calls, file edits, then the
answer. On a phone, the time between sending a message and seeing anything is
the whole experience: a long silence reads as a bot that missed the message.
The agents stream their reply as text increments (Claude Code only when asked,
via `include_partial_messages`), so there is something to show as it is
written.

The platforms offer very different ways to show a turn while it runs:

- **Telegram** can edit a delivered message (`editMessageText`), but edits
  run into flood limits of roughly one per second. Since Bot API 10.1 it also
  has `sendMessageDraft`: a temporary, never-persisted preview built for
  streaming, with a platform-drawn stop control — but only in private chats.
  Telegram has reactions.
- **SeaTalk** cannot edit a text message at all, but can **stream** one:
  `init_stream` opens a message and each `update_stream` replaces its content
  with a full snapshot. The client re-types the whole message whenever a
  snapshot changes anything already shown — a step line shifting, the clock —
  so a message carrying a status block flickers on every step. Updates more
  than 30 s apart terminate the stream. SeaTalk has a typing cue (about 4 s
  long, in direct chats and group threads) and no reactions.
- Both have per-message length caps (4096).

The other IM-agent products (OpenClaw, Hermes, Devin's chat integrations; see
[the IM bridges survey](../research/im-agent-bridges.md)) show a running turn
through typing or a status surface rather than through the answer message
itself, and their final message holds only the answer: the narration an agent
writes between tool calls ("let me check the logs…") is progress, not reply.

Measured against the real SDK, text deltas arrive about every 25 ms carrying
~4 characters each, so the update interval alone decides whether a reply reads
as typing or arrives a sentence at a time.

## Options Considered

### Option A — A preview surface where the platform has one, typing elsewhere; the reply is a new message holding only the answer (chosen)

The core asks one question, `supports_live_text` — *is there a surface I can
keep updating while the turn runs?* — and gets a `LiveText` handle whose
`update(text)` always takes the full accumulated snapshot and whose
`close(text)` returns whatever still has to be sent the ordinary way
(`application/channel/ports.py`). The surface shows the status block — the
narration, the step lines ("⏳ Bash · list the desktop") — with the answer
growing under it, and is always **scaffolding**: the finished reply goes out as
a new message, which is also what notifies. The renderer
(`application/channel/turn_render.py`) never knows which mechanism is
underneath, and adds **no throttle of its own**: the surface's transport owns
the rate.

- **Telegram, direct chat:** a message draft, updated every 0.2 s
  (`infrastructure/channel/telegram_draft.py`), carrying the stop control
  routed to the interrupt path; the finished reply is sent as a real message.
- **Telegram, group** (or a Bot API without drafts): a status message opened
  once the turn has run 1.5 s, edited at most every 1.5 s, and deleted when the
  real reply is sent — scaffolding, not the answer
  (`TelegramLiveText` in `infrastructure/channel/live_text.py`).
- **SeaTalk:** no live surface (`supports_live_text` false). The typing
  indicator, re-sent every 3 s, is the progress; the finished reply is one new
  message (cut at paragraphs when long) in a direct chat, withdrawable cards in
  a group.
- **The reply is the answer alone:** the text written after the last tool call
  (or, when nothing followed it, the last text written). Narration can show on
  a preview surface but never reaches the final message.
- **Receipt:** a transport with reactions marks the owner's message 👀 on
  receipt and ✅ on a clean finish; one without keeps a typing heartbeat alive
  for the turn, in DMs and group threads.
- **Completion:** a clean success sends nothing extra — the reply is the
  signal. Only a failed, interrupted or tool-limited turn gets a one-line
  summary.
- A surface that fails latches dead and the reply falls back to ordinary
  chunked messages, so a progress problem never loses the answer.

Pros: one renderer for every platform; a platform with a real preview surface
shows progress at the fastest rate it tolerates; the answer always arrives as a
new message, so it notifies and needs no separate "done" ping; the reply reads
as an answer, not a log of the turn.

Cons: a SeaTalk turn shows nothing but typing until the answer lands, so a long
turn there says *that* it is working but not *what* it is doing. A Telegram
group still shows edit-rate progress, not typing-rate.

Wins because it keeps the core platform-free, shows progress only where the
platform has a surface built for it, and keeps the chat holding answers.

### Option B — Stream the SeaTalk reply in place (the design this replaced)

How it works: a SeaTalk stream opened at turn start showing the status block,
re-sent on a keep-alive, finishing as the reply; every narration segment joined
into it; a long turn followed by a "✅ Done · …" ping because finishing a
message created minutes earlier notifies nobody; and, since SeaTalk cannot
collapse a details section, the details moved behind a summary card with
**Details** / **As file** buttons.

Pros: the owner sees what the agent is doing on SeaTalk, not just that it is.

Cons: the client re-types the whole message whenever the status block changes,
so it flickered however the writes were paced (a 2 s redraw bound only slowed
the flicker); the reply carried the agent's step-by-step narration; a long turn
needed a second message to notify anyway; and the details card's "Details
posted in the thread." left a stray card behind.

Loses on how the chat reads: the live view cost more than it showed.

### Option C — Acknowledge with a message, then send the final reply

How it works: a quick "working on it" message, nothing during the turn, the
whole reply at the end, plus a completion summary.

Pros: simplest; works on any platform.

Cons: the ack and the summary are extra messages cluttering the chat. Typing
says the same thing with no message at all.

Loses on noise.

### Option D — Edit one message everywhere

How it works: every platform sends a status message and rewrites it.

Pros: one mechanism.

Cons: SeaTalk cannot edit a text message, so it is not available there at
all. On Telegram, edits hit flood limits at about one per second and leave a
message to delete; the draft endpoint exists precisely to avoid both.

Loses because the platform that most needs a live surface has no edit.

### Option E — A new message per chunk or per sentence

How it works: send each increment as its own message.

Pros: no edit or stream API needed; every platform can do it.

Cons: floods the chat and the notification tray, hits send rate limits fast,
and leaves the reply scattered over dozens of messages.

Loses on noise.

### Option F — A core-level throttle shared by every transport

How it works — the design this replaced: the renderer throttled every snapshot
to 1.5 s before handing it to the transport, which also buffered.

Pros: one knob.

Cons: the slower throttle hid the faster one entirely, so a stream jumped a
paragraph at a time; and the right rate is a fact about each platform's
endpoint, which the core does not know.

Loses because rate limiting belongs to the component that knows the limit
(PR #357).

## Decision

Every turn renders onto at most one live surface, requested through
`supports_live_text` and driven through the `LiveText` handle with full
snapshots. Telegram uses a message draft in direct chats and a deleted status
message in groups; SeaTalk has none and shows typing. Each transport paces its
own updates (0.2 s draft, 1.5 s edit); the core adds no throttle. Receipt is a
reaction where the platform has one and a typing heartbeat where it does not.
The finished reply is always a new message holding only the answer. Only an
abnormal ending sends a summary.

Rules a future change must respect:

- The core never branches on which live mechanism a transport uses.
- A snapshot is always the full text, never a delta.
- A live surface is scaffolding: it never becomes the reply.
- The reply carries only the text after the last tool call.
- A dead surface is never reused; the ordinary send path always delivers the
  reply.

## Consequences

- A new platform chooses its surface and pace inside its adapter and declares
  `supports_live_text`; the renderer needs no change.
- The core asks for a live surface (`supports_live_text`), never for "can a
  delivered text message be rewritten".
- No transport's reply is created before the turn ends, so a reply always
  notifies and no long-turn ping is needed.
- Enforced by: `ChannelCapabilities` in `domain/channel/envelopes.py`;
  `LiveText` in `application/channel/ports.py`; `turn_render.py`;
  `infrastructure/channel/live_text.py` and `telegram_draft.py`.
