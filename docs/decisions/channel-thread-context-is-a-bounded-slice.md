# A Channel Turn Folds a Bounded Slice of Its Thread, Read by the Transport

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: spec channels ("Ground a thread turn in a bounded slice of the thread", "Read a thread's earlier messages on demand", "Ground a turn in the message it quotes", "Ground a DM thread's turn in the thread", "Download the media a thread's messages carry", "Open every turn with its message origin");
spec channels/seatalk ("Resolve a quoted message with the bot's own token", "Read every page of a thread", "Fetch a DM thread from its own endpoint");
[A Channel Conversation Is Keyed by (Channel, Chat, Thread)](channel-conversation-identity.md), [Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Channel Attachments](channel-attachments.md);
PRs #353, #428, #630

## Context

In a thread, "repeat this" or "as above" points at earlier messages the bot
never received: SeaTalk delivers a group message to a bot only when it
@mentions the bot. A reply that quotes an earlier message carries only the
quoted message's id, and on SeaTalk message ids are **per app** — the same
message has a different id for every bot — so only the bot that received the
event can resolve it. An agent holding its own SeaTalk tools could not look the
quote up. Telegram includes the replied-to message inline in the update, and its
Bot API offers bots no history read at all.

So the agent needs some of the thread, read by the bot. How much, and when?

The conversation behind a thread ([A Channel Conversation Is Keyed by (Channel,
Chat, Thread)](channel-conversation-identity.md)) keeps its own session, so
whatever an earlier turn was given is already in the agent's context. SeaTalk's
thread endpoints page **oldest-first** at most 100 messages per page, so the
newest messages are reached only by reading every page, and a message's images
and files are a separate download each.

## Options Considered

### Option A — Seed a conversation's first turn with the thread's latest messages, fold only what is new afterwards, and offer a tool for the rest (chosen)

On a transport declaring `supports_history_fetch` (SeaTalk), the core's
`ThreadContextFolder` (`application/channel/turn_context.py`) asks the adapter
for the thread's messages as text (every page, oldest first, bounded at 20
pages; nothing downloaded) and folds a slice above the message:

- on a **conversation's first turn in that thread** — a new conversation, or one
  `/resume` switched to that never had a turn there — the **20 most recent**
  messages other than the triggering one, the bot's replies included, under
  `[Thread messages]`;
- on **every later turn**, only what others posted **since that conversation's
  previous turn there**, leaving out the bot's own messages (the transport's flag
  or the reply ledger), under `[New thread messages since your last turn in this
  thread]`, also at most 20 — and nothing at all when nothing is new.

Where a conversation is in each thread is a cursor in `runs.db`
(`channel_thread_cursors`, keyed by channel, chat, platform thread and
conversation) holding the message that triggered its latest turn there, so it
survives a restart and `/resume` picks up where it left off. A read that fails
folds nothing and leaves the cursor where it was. Only the folded messages'
media is downloaded. When messages were left out, one line names how many and
the exact call to read them with `coffer__channel_read_thread`, a turn-scoped
built-in tool that pages a paired chat's thread newest-first through the bot's
own credentials. The quoted message is resolved with the bot's token and placed
right above the message as `> sender: …` lines. Group-main history is never
read; a slash command never fetches context.

Pros: the agent sees what the person was looking at, pictures included, without
re-reading what its own session already holds; a turn's cost is bounded however
long the thread grows; older messages stay one tool call away, through the only
credentials that can resolve the platform's per-app ids.

Cons: the text of a long thread is still read every turn, because the endpoint
pages from the oldest end; a cursor table and a pending-cursor claim (a
conversation that does not exist yet keys its cursor as pending until the turn
opens it, and a claim not made within 10 minutes expires); a later turn trusts
the session to remember, so a session compacted by the agent may have lost what
the seed gave it.

Wins because it is bounded on both axes — per turn and over a conversation —
while keeping everything reachable.

### Option B — Fold the whole thread into every turn (the design #630 replaced)

Read every page and every message's media on every thread turn and fold all of
it in.

Pros: the agent always has the whole thread in front of it; no cursor.

Cons: from the second turn on almost all of it is a repeat of what the session
already holds, so token cost grows with the thread's length on every turn and
the same messages appear in the history once per turn; every turn downloads
every file again; a thread past 20 pages lost its newest messages, the ones that
matter most.

Loses on cost that grows without bound and context the agent already has.

### Option C — Let the agent fetch its own context

Send only the message and its ids; the agent calls a SeaTalk MCP tool when it
wants the thread or the quote.

Pros: no tokens spent on context the agent does not need.

Cons: SeaTalk ids are per app, so the agent's own tools cannot resolve the
bot's quote or thread ids; it would need the bot's credentials, which Coffer
does not hand to a full-permission agent; and an agent does not know to fetch
context it cannot see referenced.

Loses because the ids are only meaningful to the bot — which is why the
on-demand tool in Option A runs inside Coffer, with the bot's credentials,
rather than as the agent's own.

### Option D — Mirror the platform history into Coffer and send only the delta

Keep every thread message Coffer has seen and send the agent only what is new.

Pros: no repeated reads.

Cons: the bot does not receive most thread messages (only @mentions), so the
mirror would itself be built from fetches; edits and deletions on the platform
would diverge from the copy; a store of other people's messages is a retention
and privacy surface of its own.

Loses because Option A gets the same delta from a cursor of one message id per
conversation, with no copy.

## Decision

On a transport that can read history, the transport reads a thread with the
bot's own credentials, and the core folds a bounded slice into the turn: the 20
latest messages on a conversation's first turn in the thread, only what others
posted since on later turns, tracked by a per-conversation cursor in `runs.db`.
Older messages are named in one line and read on demand with
`coffer__channel_read_thread`. The quoted message is resolved by the transport
and folded right above the message. Group-main history is never read.

Rules a future change must respect:

- Context reads happen in the transport with the bot's credentials, gated on
  `supports_history_fetch`, and degrade to nothing on failure without moving
  the cursor.
- A turn never folds what its own conversation already saw in that thread.
- Media is downloaded only for messages that are folded or returned by the
  tool.

## Consequences

- A turn's context cost is bounded by the slice size, not the thread's length.
- A new transport that can read history implements the adapter's context-fetch
  port and declares the capability; one that inlines quotes on the update
  (Telegram) needs neither, and the tool reports that it has no history API.
- Enforced by: `application/channel/turn_context.py` (`THREAD_FOLD_LIMIT`,
  `PENDING_TTL`), the `channel_thread_cursors` table,
  `infrastructure/channel/seatalk_history.py`, and the channel kind's built-in
  tool `coffer__channel_read_thread`.
