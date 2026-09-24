# A Channel Conversation Is Keyed by (Channel, Chat, Thread) and Grounded in Its Thread and Quote

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu
**Related**: spec channels ("Key conversation identity by channel, chat and thread", "Keep DM, group-main and thread turns apart", "Reply in place inside threads", "Ground a turn in the message it quotes", "Ground a DM thread's turn in the thread", "Download the media a thread's messages carry", "Open every turn with its message origin");
spec channels/seatalk ("Identify a thread by its root message", "Resolve a quoted message with the bot's own token", "Read every page of a thread", "Fetch a DM thread from its own endpoint");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Channel Switches](channel-switches-structural-vs-parametric.md), [Channel Owner Gate](channel-owner-gate.md);
PRs #245, #353, #428

## Context

Two questions decide what an agent knows when a channel message reaches it.

**Which conversation does a message belong to?** A conversation is one agent
session: one resumed upstream session, one pending queue, one running turn at a
time. On the platforms Coffer serves, one chat holds several independent
exchanges — a group's main timeline and each of its threads, and on SeaTalk a
DM's threads too. If two threads share a conversation, a message in one waits
behind (or is refused by) a turn running in the other, and each thread's agent
reads the other's context as its own.

**What surrounding text does the agent need?** In a thread, "repeat this" or
"as above" points at earlier messages in the thread, which the bot never
received: SeaTalk delivers a group message to a bot only when it @mentions the
bot. A reply that quotes an earlier message carries only the quoted message's
id. And on SeaTalk message ids are **per app**: the same message has a
different id for every bot, so only the bot that received the event can
resolve it — an agent holding its own SeaTalk tools could not look the quote
up. Telegram, by contrast, includes the replied-to message inline in the
update, and its Bot API offers bots no history read at all.

## Options Considered

### Option A — Identity `(channel, chat, thread)`; the transport reads the thread and the quote with the bot's own token and folds them into the turn text (chosen)

**Identity.** `channel_thread_conversations` (migration `0041`) holds one row
per `(resource_id, chat_id, thread_id)`: the active conversation and the
thread's sticky agent. A DM or group main timeline is `thread_id = ""`; each
thread is its own row. On SeaTalk a thread's id is its root message's id, so an
@mention in the group main timeline roots a new thread at itself and the reply
goes there. Owner and pairing identity stay on `channel_peers`, one row per
chat. Replies return to the same chat and thread they came from.

**Context.** On a transport declaring `supports_history_fetch` (SeaTalk), the
core's `fold_turn_context` (`application/channel/turn_context.py`) asks the
adapter for:

- the **quoted message**, resolved with the bot's own token through
  `get_message_by_message_id`, placed right above the message as
  `> sender: …` lines;
- the **thread's own messages**, read oldest-first from the group or DM thread
  endpoint, following `next_cursor` at 100 messages per page (the endpoint's
  maximum) up to 20 pages (`infrastructure/channel/seatalk_history.py`), placed
  above that under a "Thread messages" heading;
- the images and files those messages carry, downloaded with the app token
  and attached to the turn.

A message that roots a new thread fetches nothing; a slash command never
fetches context; any failed read leaves the turn as it was. Every turn also
opens with an origin block naming the chat and sender. The folded text is the
turn's user message, so the context the agent saw is recorded in the
conversation.

Pros: concurrent threads never collide on one turn lock, and one bot can run
different agents in different threads. The agent sees what the owner was
looking at when they wrote "as above", including pictures. The quote
resolution works only because the transport, not the agent, performs it.

Cons: a long thread is re-read and re-sent on every turn in it, costing tokens
and a few API calls each time; the same earlier messages appear in the history
once per turn. A thread past 20 pages loses its newest messages (the cap
exists only so a runaway cursor cannot stall a turn). Group-main history is
never read: the platform does not deliver non-@ messages and the endpoint's
permission is not granted to a self-built app.

Wins because it is the only arrangement in which the thread's context is both
reachable (per-app ids) and scoped to the right conversation.

### Option B — Identity per chat (the peer)

How it works — the design first shipped: one active conversation per
`(channel, chat)`, stored on the peer row.

Pros: simplest mapping; one row per chat.

Cons: in a group with threads, two threads shared one conversation and one
turn lock, so concurrent @mentions collided ("a turn is already running") and
each thread's history leaked into the other. Replaced by per-thread identity
in PR #245; migration `0084` later dropped the peer's leftover columns.

Loses because the platforms' own unit of conversation is the thread.

### Option C — A fresh conversation per message

How it works: every inbound message starts its own conversation.

Pros: no identity mapping at all; no collisions.

Cons: the agent forgets everything between messages, which defeats driving a
coding agent over several steps from a phone.

Loses on continuity.

### Option D — Let the agent fetch its own context

How it works: send only the message and its ids; the agent calls a SeaTalk
MCP tool to read the thread or the quote if it wants.

Pros: no tokens spent on context the agent does not need; the core stays
smaller.

Cons: SeaTalk ids are per app, so the agent's own tools cannot resolve the
bot's quote or thread ids; the agent would need the bot's credentials, which
Coffer does not hand to a full-permission agent; and an agent does not know to
fetch context it cannot see referenced.

Loses because the ids are only meaningful to the bot.

### Option E — Mirror the platform history into Coffer and send only the delta

How it works: keep every thread message Coffer has seen and send the agent
only what is new since its last turn.

Pros: no repeated context; cheaper turns.

Cons: the bot does not receive most thread messages (only @mentions), so the
mirror would itself be built from fetches; edits and deletions on the platform
would diverge from the copy; and a new store of other people's messages is a
retention and privacy surface of its own.

Loses because the fetch is needed anyway and the copy adds a store without
removing it.

## Decision

A channel conversation is identified by `(channel, chat, thread)`, stored in
`channel_thread_conversations` with that thread's sticky agent; a DM or group
main timeline is the empty thread. On a transport that can read history, each
non-command turn is grounded by the transport fetching the thread's own
messages (every page, oldest first, bounded) and the quoted message with the
bot's own token, downloading their media, and folding them into the turn's text
above the message itself. Group-main history is never read.

Rules a future change must respect:

- Anything that selects a conversation or a sticky choice keys on all three
  parts.
- Context reads happen in the transport with the bot's credentials, gated on
  `supports_history_fetch`, and degrade to nothing on failure.

## Consequences

- Concurrent turns in different threads of one group run independently.
- A new transport that can read history implements the adapter's
  context-fetch port and declares the capability; one that inlines quotes on
  the update (Telegram) needs neither.
- Token cost grows with thread length per turn; the page cap is the only
  bound.
- Enforced by: migration `0041`'s table and
  `application/channel/conversation_ops.py`;
  `application/channel/turn_context.py`;
  `infrastructure/channel/seatalk_history.py`.
