# A Channel Reply Grows on One Live Surface, Paced by the Transport

**Status**: Accepted
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Related**: spec channels ("Grow a reply in place on one live surface", "Stream through the platform's own surface where the chat has one", "Acknowledge receipt and completion by capability", "Summarise only a turn that did not end normally", "Stop the turn from the platform's own stop control");
spec channels/telegram ("Stream through a message draft in direct chats only", "Use a deleted status message as the live scaffolding");
spec channels/seatalk ("Stream the reply under SeaTalk's streaming contract", "Keep a typing heartbeat alive in DMs and group threads");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md);
PRs #354, #356, #357

## Context

A managed-agent turn can run for minutes — tool calls, file edits, then the
answer. On a phone, the time between sending a message and seeing anything is
the whole experience: a long silence reads as a bot that missed the message.
The agents stream their reply as text increments (Claude Code only when asked,
via `include_partial_messages`), so there is something to show as it is
written.

The platforms offer very different ways to show a growing reply:

- **Telegram** can edit a delivered message (`editMessageText`), but edits
  run into flood limits of roughly one per second. Since Bot API 10.1 it also
  has `sendMessageDraft`: a temporary, never-persisted preview built for
  streaming, with a platform-drawn stop control — but only in private chats.
  Telegram has reactions.
- **SeaTalk** cannot edit a text message at all, but can **stream** one:
  `init_stream` opens a message and each `update_stream` replaces its content
  with a full snapshot (the client shows the latest snapshot; it does not
  animate). Updates more than 30 s apart terminate the stream, and a
  terminated stream id is rejected forever. SeaTalk has a typing cue (about 4 s
  long) and no reactions. Its docs suggest buffering to about one update per
  200 ms and publish no rate limit.
- Both have per-message length caps (4096).

Measured against the real SDK, text deltas arrive about every 25 ms carrying
~4 characters each, so the update interval alone decides whether a reply reads
as typing or arrives a sentence at a time.

## Options Considered

### Option A — One live surface per turn, requested by capability; each transport paces its own updates (chosen)

The core asks one question, `supports_live_text` — *is there a surface I can
keep updating while the turn runs?* — and gets a `LiveText` handle whose
`update(text)` always takes the full accumulated snapshot and whose
`close(text)` returns whatever still has to be sent the ordinary way
(`application/channel/ports.py`). Tool activity lines show first ("⏳ Bash ·
list the desktop"), then the reply text takes the same surface over. The
renderer (`application/channel/turn_render.py`) never knows which mechanism is
underneath, and adds **no throttle of its own**: the surface's transport owns
the rate.

- **Telegram, direct chat:** a message draft, updated every 0.2 s
  (`infrastructure/channel/telegram_draft.py`), carrying the stop control
  routed to the interrupt path; the finished reply is sent as a real message.
- **Telegram, group** (or a Bot API without drafts): a status message opened
  once the turn has run 1.5 s, edited at most every 1.5 s, and deleted when the
  real reply is sent — scaffolding, not the answer
  (`TelegramLiveText` in `infrastructure/channel/live_text.py`).
- **SeaTalk:** a stream opened the moment the turn starts with a "working on
  this" line, updated every 100 ms (`COFFER_SEATALK_STREAM_INTERVAL`), and
  re-sent every 10 s so a long tool run stays inside the 30 s window
  (`LIVE_KEEPALIVE_SECONDS`). The streamed message *is* the reply
  (`live_text_persists=True`), so opening it early costs nothing.
- **Receipt:** a transport with reactions marks the owner's message 👀 on
  receipt and ✅ on a clean finish; one without keeps a typing heartbeat alive
  for the turn, in DMs and group threads.
- **Completion:** a clean success sends nothing extra — the reply is the
  signal. Only a failed, interrupted or tool-limited turn gets a one-line
  summary.
- A surface that fails latches dead and the reply falls back to ordinary
  chunked messages, so a progress problem never loses the answer.

Pros: one renderer for every platform; each platform uses the best surface it
has, at the fastest rate it tolerates; the owner sees acknowledgement within a
second and text as it is written.

Cons: three pacing constants to maintain, each tuned against a platform's
undocumented tolerance (100 ms on SeaTalk trades an unpublished allowance for
readability; a push-back is answered by back-off and logged). A Telegram group
still shows edit-rate progress, not typing-rate.

Wins because it keeps the core platform-free while letting each platform show
its best, and because moving the throttle into the transport is what made
streaming read as streaming.

### Option B — Acknowledge, then send the final reply

How it works — what SeaTalk did before its streaming API was adopted: a quick
"working on it", nothing during the turn, the whole reply at the end, plus a
completion summary so the owner knew the turn had ended.

Pros: simplest; no rate limits to respect; works on any platform.

Cons: a multi-minute silence between ack and answer; on a platform that
cannot edit, the ack and the summary are extra messages cluttering the chat,
and on a long turn the silence reads as the bot having missed the message.

Loses because both platforms now offer a growing surface, and not using it
leaves the longest wait blank.

### Option C — Edit one message everywhere

How it works: every platform sends a status message and rewrites it.

Pros: one mechanism.

Cons: SeaTalk cannot edit a text message, so it is not available there at
all. On Telegram, edits hit flood limits at about one per second and leave a
message to delete; the draft endpoint exists precisely to avoid both.

Loses because the platform that most needs a live surface has no edit.

### Option D — A new message per chunk or per sentence

How it works: send each increment as its own message.

Pros: no edit or stream API needed; every platform can do it.

Cons: floods the chat and the notification tray, hits send rate limits fast,
and leaves the reply scattered over dozens of messages.

Loses on noise.

### Option E — A core-level throttle shared by every transport

How it works — the design this replaced: the renderer throttled every snapshot
to 1.5 s before handing it to the transport, which also buffered.

Pros: one knob.

Cons: the slower throttle hid the faster one entirely, so SeaTalk's stream
jumped a paragraph at a time; and the right rate is a fact about each
platform's endpoint, which the core does not know.

Loses because rate limiting belongs to the component that knows the limit
(PR #357).

## Decision

Every turn renders onto at most one live surface, requested through
`supports_live_text` and driven through the `LiveText` handle with full
snapshots. Telegram uses a message draft in direct chats and a deleted status
message in groups; SeaTalk uses a persisted stream opened at turn start with a
10 s keep-alive. Each transport paces its own updates (0.2 s draft, 1.5 s
edit, 100 ms SeaTalk stream); the core adds no throttle. Receipt is a reaction
where the platform has one and a typing heartbeat where it does not. Only an
abnormal ending sends a summary.

Rules a future change must respect:

- The core never branches on which live mechanism a transport uses.
- A snapshot is always the full text, never a delta.
- A dead surface is never reused; the ordinary send path always delivers the
  reply.

## Consequences

- A new platform chooses its surface and pace inside its adapter and declares
  `supports_live_text` / `live_text_persists`; the renderer needs no change.
- `supports_edit` and `supports_live_text` are separate capabilities and must
  stay separate: SeaTalk streams but cannot edit.
- Clients too old for a platform's streaming (SeaTalk before 3.67) see only
  the final message, which is the same reply.
- Enforced by: `ChannelCapabilities` in `domain/channel/envelopes.py`;
  `LiveText` in `application/channel/ports.py`; `turn_render.py`;
  `infrastructure/channel/live_text.py` and `telegram_draft.py`.
