## Context

A channel turn has two things to show: that the agent is working (and, where
possible, what it is doing), and then the answer. Until now Coffer used one
mechanism for both on SeaTalk: a stream (`init_stream` / `update_stream`)
opened at turn start that showed a status block and step lines and then grew
into the reply. Three problems followed from that one choice:

- SeaTalk's client has no append. Every update replaces the whole message, and
  any change to text already on screen — a step line shifting up, the clock —
  re-types the bubble. A 2 s redraw bound slowed the flicker but could not
  remove it.
- A message created when the turn began notifies nobody when it is finished,
  so a long turn needed a separate "✅ Done · …" ping (and a "❓ Needs you" ping
  for a question).
- The reply was `ReplyText.full()`: every text segment the agent wrote between
  tool calls, joined. The answer arrived under its own narration.

The details card was a second, independent workaround: SeaTalk cannot collapse
a `## Details` section, so the details moved behind a summary card whose tap
left it reading "Details posted in the thread.".

## Research

OpenClaw, Hermes and Devin's chat integrations (and the bridges in
`docs/research/im-agent-bridges.md`) all separate the two: a running turn is
shown through typing, a reaction or a status surface built for previews
(Telegram's `sendMessageDraft`), and the final message holds only the answer,
sent as a new message so it notifies. None of them grows the answer out of a
progress message.

## Goals / Non-Goals

**Goals:** no flicker on SeaTalk; a reply that is the answer alone on every
transport; no extra completion message; no card standing in for text.

**Non-Goals:** changing Telegram's live surface (its draft and edited status
message stay); changing group replies on SeaTalk (still withdrawable cards);
showing step-level progress on SeaTalk by some other means.

## Decisions

### SeaTalk has no live surface

`SEATALK_CAPABILITIES.supports_live_text` becomes false and `open_live_text`
returns `None`. The existing typing heartbeat (every 3 s, DM and group thread)
is the whole of the progress signal; the reply goes through the ordinary send
path, which already cuts at paragraphs and numbers parts `(2/3)`. The stream
code (`seatalk_live.py`, `seatalk_stream_text.py`, the escape-and-clip helpers in
`render.py` used only for interim snapshots, `COFFER_SEATALK_STREAM_INTERVAL`)
is deleted.

*Alternative:* keep the stream but write only append-only snapshots (status in
a separate typing call, answer streamed under nothing). Rejected: the message is
still created at turn start, so it still does not notify, and the ping would
have to stay.

### Every live surface is scaffolding

With SeaTalk's stream gone, no transport's surface becomes the reply. The
`live_text_persists` capability (and the turn-start acknowledgement it drove)
and `streams_in_groups` (only SeaTalk set it) have no reader left and are
removed, as are the mention-on-every-snapshot path and `TurnSurface.persisted`.

### The ping goes with it

The ping fired only when the answer finished a surface that persisted from the
turn's start. No transport has one, so the ping is dead code: removed end to end
— `notify_after_seconds` in the config model, the binding and the renderer; the
question ping; the REST contract (`make contracts`); the Channels settings field
and its strings. A stored config may still carry the key, and the config model
refuses unknown keys, so the model drops it on read (the same
`_drop_retired_*` pattern the agent and provider configs use) rather than
failing a channel's start.

### The reply is the last segment

`ReplyText.full()` becomes `ReplyText.answer()`: the text after the last tool
call, or — when the turn wrote nothing after its last tool call — the last
segment that has text. That holds on every transport; narration still shows on
a live surface as the `💬` line. The agent note now tells the agent that only
the text after its last tool call is sent, so it writes the whole answer there.

### No details card

The summary card, its `details:` / `detailsfile:` callback routes and the
temp-file store are deleted. A transport that cannot collapse `## Details`
sends it as ordinary text. The agent note asks for a `## Details` section only
when the transport declares `collapses_details` (Telegram), carried to the
prompt composer on `ChannelNote.collapses_details`.

### SeaTalk direct-chat text is not put on the withdraw record

A SeaTalk direct reply used to be the stream (never recorded). It is now plain
text, which SeaTalk can neither delete nor rewrite. `ReplyTracker.send` records
a message only when it went out with buttons (a card) or the transport removes
messages, so `/del` in a SeaTalk direct chat still says there is nothing to
withdraw instead of failing on a text message.

### The step-lines setting is offered only where it shows

`show_steps` shapes only a live surface's status block, which SeaTalk no longer
has. The Channels page shows the switch only for Telegram channels (the same
per-type gate `require_mention` uses); the config field itself stays.

## Risks / Trade-offs

- A long SeaTalk turn now says *that* it is working (typing), not *what* it is
  doing. Accepted: the owner asked for this trade; the typing indicator is
  continuous.
- An agent that writes its whole answer before a final bookkeeping tool call
  still gets it delivered (the fallback to the last segment), but one that
  spreads the answer across segments loses the earlier parts. The agent note
  now says so.
