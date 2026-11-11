# A Long Channel Reply Is Rewritten Short by the Agent

**Status**: Accepted
**Date**: 2026-11-10 (first taken 2026-10-20)
**Deciders**: Yuxing Wu
**Related**: [A Channel's System Prompt Is a Fixed Channel Note Plus a Reply Style the Owner Can Rewrite](channel-prompt-fixed-note-and-editable-style.md), [A Channel Turn Posts Nothing Until It Is Done, and the Reply Is the Answer Alone](channel-live-surface-strategy.md), [A Channel Reply Is Plain Text, With No Card or Button](a-channel-reply-is-plain-text.md), spec channels "Ask for the short version of a reply too long for a chat"

## Context

The owner wants a chat with the bot to read like a chat between two people:
results, not thinking; short and clearly structured; and when a detailed report
is needed, the conclusion in the chat and a question whether to send the full
report as a file. The reply style now asks for exactly that (answer first,
about 8 lines, full report only as a file on request). A prompt is a request,
not a guarantee: a SeaTalk reply from Codex on 2026-10-20 ran to several
screens of dense bullets after a style that already said "at most about 15
lines". Something has to happen to a reply that still comes back too long.

Two constraints narrow it. Coffer keeps no reply text
([chat](../../openspec/specs/chat/spec.md) "Keep the conversation index without
its text"), so it cannot hold a long reply and send it later. And whatever
reaches the chat must read as a whole message, not as one cut off.

How comparable products treat a long answer in a chat (from their public docs
as of 2026-10; see also [docs/research](../research/README.md)):

- **Claude in a Projects thread** (the assistant that runs this project): a
  reply over about fifteen lines is delivered as a file or document, with one
  line in the chat pointing at it.
- **Devin in Slack**: posts the result; the detail lives in its worklog, linked.
- **OpenClaw**: an oversized reply falls back to ordinary chunked delivery —
  the whole text arrives in parts.
- **Hermes Agent**, and Coffer itself before this change: cut the reply into
  messages of the platform's size.
- **Claude in Slack**: long work goes to a canvas or file (inferred from the
  product; not found stated in its docs).

None truncates a reply silently; the ones that keep chat readable move the long
part somewhere else and say so. Claude in Slack and Devin keep the long material
behind a link or a page the reader opens on demand.

## Options Considered

### Option A — Ask the agent for the short version, which offers the full one (chosen)

A cleanly finished reply past the bound (20 lines with text or 1,500
characters, not counting `MEDIA:` lines or a collapsed `## Details`) is not
sent. Coffer queues a follow-up turn in the same conversation, opening with
`[Coffer]`: say it again in at most 5 lines, end with one short line offering
the full report as a file, no tools. That reply is plain text like every reply;
the owner who wants the file says so in a message. The follow-up's reply is
never held back again.

- Pros: what reaches the chat is always a whole message written by the agent,
  in its own words and the asker's language. Coffer stores nothing: the agent
  still has the full answer in its session. It follows the owner's exact ask —
  conclusion first, then a question about the file — and asking for the file is
  answering a colleague.
- Cons: one more model call, and the short version arrives seconds to tens of
  seconds later (the typing indicator keeps running). The follow-up is a real
  turn, so the session (and the web view of it) shows Coffer's note. Asking for
  the file costs a further turn.

Wins because it is the only option that never leaves half a message and needs
no reply text kept. With the reply style asking for short replies, it should
fire rarely.

### Option A′ — As A, the offer as a 📄 Full report button (the design until 2026-11-10)

The short version ended on its answer and carried a **📄 Full report** button,
whose tap reached the agent as the owner's message "Send me the full report as
a Markdown file." (Before 2026-10-28 it carried both the button and a closing
question, which said the same thing twice.)

- Pros: one tap to the file; the reply itself ends on its answer.
- Cons: the button made the reply a card on SeaTalk, and the owner asked for
  replies in plain text with no cards (see the plain-text ADR); the tap needed
  its own path into the inbound pipeline.

### Option B — Cut at the first paragraph, mark it, full text behind a button

Send the first paragraph with "the full answer is long — tap for it".

- Pros: no extra model call, no delay.
- Cons: the first paragraph is only a conclusion if the model put one there —
  the replies this is for are the ones that ignored that instruction, so the
  cut often reads as a message stopped mid-thought. The button needs the full
  text kept somewhere, which Coffer does not keep; generating it on tap means a
  turn anyway.

Loses on the very replies it exists for, as the owner pointed out ("this would
send half a message").

### Option C — Send the conclusion and attach the full reply as a file, automatically

- Pros: no extra call; nothing is lost.
- Cons: still needs a conclusion to send, which a long reply may not have; every
  long reply grows an unrequested file, against the owner's "ask first".

### Option D — Prompt only, no fallback

- Pros: nothing to build; no extra calls.
- Cons: a model that ignores the length rule lands the wall of text anyway, as
  the 2026-10-20 reply did.

### Option E — Summarise with a separate, stateless model call

Coffer sends the long reply to a model of its own choosing and asks for a
summary.

- Pros: does not touch the agent's session; can be a cheap model.
- Cons: Coffer has no model call of its own outside an agent turn, so it needs
  a provider, credentials and a model choice just for this; the summariser does
  not know the conversation, so it cannot judge what the asker needs; and the
  full report on tap would still have to come from the agent.

## Decision

A channel reply that finished cleanly and is past the bound is replaced by a
follow-up turn asking the same conversation for the short version
(`application/channel/reply_rewrite.py`, `rewrite_turn.py`), which ends with one
line offering the full report. The reply carries no button.

- The follow-up runs through the conversation's ordinary queue and never names
  the conversation. When a message already waits in that queue, the long reply
  is sent as it is: the waiting message would run first and change what "your
  last reply" means.
- A failed or stopped turn's partial reply is sent as before, with its notice.
- The bound is a constant, not a setting: about two phone screens.
- Coffer's default reply style still says to send a full report only when asked
  and not to end a reply by offering it; the short version is the one exception,
  because there the full answer is the one the reader did not get.

## Consequences

- A long answer costs one extra turn; a full report costs one more.
- The agent's session holds Coffer's `[Coffer]` note between the long answer and
  the short one; the agent is told not to mention it.
- The reply style remains the first line of defence; this only catches what it
  missed.
