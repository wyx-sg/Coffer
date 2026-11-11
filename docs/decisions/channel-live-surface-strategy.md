# A Channel Turn Posts Nothing Until It Is Done, and the Reply Is the Answer Alone

**Status**: Accepted (revised 2026-11-06: the Telegram preview surface was removed)
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: spec channels ("Send only the answer, once the turn is done", "Acknowledge receipt and completion by capability", "Summarise a turn that did not end normally");
spec channels/seatalk ("Show only typing while a turn runs", "Keep a typing heartbeat alive in DMs and group threads");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md);
PRs #354, #356, #357, #719

## Context

A managed-agent turn can run for minutes — tool calls, file edits, then the
answer. On a phone, the time between sending a message and seeing anything is
the whole experience: a long silence reads as a bot that missed the message.
The agents stream their reply as text increments, so there is something that
*could* be shown as it is written.

The platforms offer very different ways to show a turn while it runs:

- **Telegram** can edit a delivered message (`editMessageText`), but edits
  run into flood limits of roughly one per second. Since Bot API 10.1 it also
  has `sendMessageDraft`: a temporary, never-persisted preview built for
  streaming, with a platform-drawn stop control — but only in private chats.
  Telegram has reactions and a typing action.
- **SeaTalk** cannot edit a text message at all, but can **stream** one:
  `init_stream` opens a message and each `update_stream` replaces its content
  with a full snapshot. The client re-types the whole message whenever a
  snapshot changes anything already shown, so a message carrying progress
  flickers on every step. SeaTalk has a typing cue (about 4 s long, in direct
  chats and group threads) and no reactions.

The other IM-agent products (OpenClaw, Hermes, Devin's chat integrations; see
[the IM bridges survey](../research/im-agent-bridges.md)) show a running turn
through typing or a status surface rather than through the answer message
itself, and their final message holds only the answer: the narration an agent
writes between tool calls ("let me check the logs…") is progress, not reply.

From 2026-10-09 to 2026-11-06 Coffer ran Option B below: Telegram showed a
status header and the growing answer on a draft (direct chats) or a deleted
status message (groups). Reviewing it under the principle that Coffer does only
what the agent cannot, the owner asked for the bot to behave like a person
does: say nothing until it is done, then send one message.

## Options Considered

### Option A — Receipt and typing only; the reply is one new message holding only the answer (chosen)

Nothing is posted, edited or deleted while a turn runs, on any transport. The
chat shows receipt: a reaction on the owner's message where the transport has
reactions (👀 received, then working, then done / failed / stopped), and the
typing indicator, re-sent every 3 s by a heartbeat
(`application/channel/turn_surface.py`), wherever the transport can type. When
the turn ends, the reply goes out as one new message — cut at paragraphs when
long, always plain text with no button (see [A Channel Reply Is Plain
Text](a-channel-reply-is-plain-text.md)) — and that message is what notifies.

- **The reply is the answer alone:** the text written after the last tool call
  (or, when nothing followed it, the last text written); messages the agent
  marked as commentary never reach it.
- **Completion:** a clean success sends nothing extra. Only a failed,
  interrupted or tool-limited turn gets a one-line summary.
- **Stopping:** `/stop`, the same on every platform.
- `/status` says whether a turn is running.

Pros: the chat holds only answers, exactly like talking to a person; one code
path for every platform, with no preview mechanism, pacing, latching or
scaffolding to maintain (the draft, the status message, the stop-button route
and the thinking-block rendering were all deleted); nothing in the chat ever
flickers, is edited or disappears; every reply notifies because it is new.

Cons: a long turn says *that* it is working but not *what* it is doing; the
owner who wants to watch opens the conversation in Coffer's web UI, where the
full stream is shown.

Wins on the lean principle: the progress view was Coffer work the owner did
not want, and the web UI already shows a turn in full.

### Option B — A preview surface where the platform has one, typing elsewhere (the design this replaced)

How it works: the core asked `supports_live_text` and drove a `LiveText` handle
with full snapshots. Telegram used a message draft in direct chats (updated
every 0.2 s, carrying the platform's stop button routed to the interrupt path,
the status header in a rich draft's thinking block) and, in groups, a silent
status message opened after 1.5 s, edited at most every 1.5 s, and deleted
before the reply. SeaTalk had no live surface and showed typing.

Pros: on Telegram the owner could watch the step count, the clock, the agent's
narration and the answer appear; the platform's stop button worked.

Cons: three Telegram mechanisms (draft, rich draft, edited status message) plus
probes and latches, all to show something that is replaced a moment later;
the group's status message still had to be deleted; and the two platforms
behaved differently for no reason the owner valued.

Loses on how much Coffer did for how little the owner wanted it.

### Option C — Stream the SeaTalk reply in place

How it works: a SeaTalk stream opened at turn start showing the status block,
finishing as the reply, with a "✅ Done" ping because finishing an old message
notifies nobody.

Cons: the client re-types the whole message whenever the status changes, so it
flickered however the writes were paced; the reply carried the narration; a
long turn needed a second message anyway.

Loses on how the chat reads.

### Option D — Acknowledge with a message, then send the final reply

How it works: a quick "working on it" message, the whole reply at the end, plus
a completion summary.

Cons: the ack and the summary are extra messages. A reaction and typing say the
same with no message at all.

Loses on noise.

### Option E — A new message per chunk or per sentence

Cons: floods the chat and the notification tray, hits send rate limits, and
scatters the reply over dozens of messages.

Loses on noise.

## Decision

No transport shows a turn's progress. While a turn runs the chat shows only a
reaction (where the platform has reactions) and typing (where it has typing,
kept up by a heartbeat). The finished reply is always one new message holding
only the answer. Only an abnormal ending adds a summary line.

Rules a future change must respect:

- Nothing is sent, edited or deleted in the chat between receipt and the reply.
- The reply carries only the text after the last tool call, never narration or
  commentary.
- Reintroducing a progress view is a new decision that revisits this ADR, not
  an adapter detail.

## Consequences

- A new platform declares whether it can react and type; there is no preview
  capability to implement.
- No reply is created before the turn ends, so a reply always notifies and no
  long-turn ping is needed.
- Enforced by: `ChannelCapabilities` in `domain/channel/envelopes.py` (no
  progress field); `application/channel/turn_render.py` (deltas only build the
  answer); `turn_surface.py` (the typing heartbeat); the acceptance test for
  "a turn posts nothing until its reply".
