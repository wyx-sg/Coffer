# A Channel Conversation Is Keyed by (Channel, Chat, Thread); a Direct Chat Is One Conversation Until `/thread` Opens Another

**Status**: Accepted
**Date**: 2026-09-28
**Deciders**: Yuxing Wu
**Related**: spec channels ("Key conversation identity by channel, chat and thread", "Open parallel conversations beside a direct chat", "Open a new conversation after an idle period", "Keep DM, group-main and thread turns apart", "Reply in place inside threads");
spec channels/seatalk ("Identify a thread by its root message", "Open a parallel thread under the owner's /thread message");
spec channels/telegram ("Open a parallel thread as a private-chat topic");
[A Channel Turn Folds a Bounded Slice of Its Thread, Read by the Transport](channel-thread-context-is-a-bounded-slice.md), [A Burst of Channel Messages Is One Turn](a-burst-of-channel-messages-is-one-turn.md), [Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Channel Switches](channel-switches-structural-vs-parametric.md), [Channel Owner Gate](channel-owner-gate.md);
research note [IM agent bridges](../research/im-agent-bridges.md) ("Session scope is a configuration axis");
PRs #245, #439

## Context

A conversation is one agent session: one resumed upstream session, one pending
queue, one running turn at a time. Which conversation does a channel message
belong to?

On the platforms Coffer serves, one chat holds several exchanges. A group has
a main timeline and threads, and each thread is its own topic among several
people. A direct chat is one person working with the bot, but SeaTalk lets that
person "reply in thread" on any message, and Telegram lets a bot's private chat
hold forum-style topics. If two exchanges share a conversation, a message in one
waits behind (or is refused by) a turn running in the other, and each reads the
other's context as its own. If an exchange the person thinks of as one is split,
the agent loses the context the person is relying on.

Every bridge surveyed solves this as a choice of key prefix over
(platform, account, chat, thread, user): OpenClaw's `session.dmScope` (`main`
shares one session across DMs), cc-connect's `session_scope`, and a session
per thread or forum topic in ccgram, OpenACP and both Slack integrations
([IM agent bridges](../research/im-agent-bridges.md)).

A conversation also needs a lifetime: a chat left alone for weeks should not
answer its next question inside a stale session.

## Options Considered

### Option A — Key `(channel, chat, thread)`; a group thread is its own conversation, a direct chat is one conversation, and `/thread` opens a parallel one (chosen)

**Identity.** `channel_thread_conversations` holds one row per
`(resource_id, chat_id, thread_id)`: the active conversation and that key's
sticky settings (agent, model, working directory —
[Channel Switches](channel-switches-structural-vs-parametric.md)). A group's
main timeline and a direct chat are `thread_id = ""`. Each group thread is its
own row; on SeaTalk a thread's id is its root message's id, so an @mention in
the group main timeline roots a new thread at itself and the reply goes there.
Owner and pairing identity stay on `channel_peers`, one row per chat.

**A direct chat is one conversation.** A direct-chat thread keys to the
chat's `""` conversation unless it is a conversation of its own. Two ids travel
with every inbound message: `thread_id` is where the reply goes, and
`conversation_thread_id` is which conversation it joins. On SeaTalk
(`direct_threads_are_replies`) a casual reply-in-thread keeps the direct chat's
context and is still answered inside that thread.

**Parallel work is deliberate.** `/thread [title]` in a direct chat opens a
**parallel thread**: a thread with a conversation of its own, recorded as a row
carrying `parallel_ordinal` (`max + 1` over the chat's rows, never reused) and a
title. On SeaTalk the bot replies under the owner's `/thread` message, whose id
becomes the thread's id; on Telegram the bot creates a private-chat topic, which
can only exist because someone created it, so every Telegram private-chat topic
keys as its own conversation. Each parallel thread carries one mark, `🧵#N title`
(title defaulting to `Task`), on its root or topic, as its conversation's title
on the web, and in `/status`. In a group `/thread` is refused: every group thread
is already its own conversation.

**Lifetime.** A message opens a new conversation for its key, exactly as `/new`
does (the sticky settings carry over), when the active one has been idle longer
than the channel's `new_conversation_after_idle_hours` (default 24; 0 never
does) — the chat is told in one line — or when the owner deleted it, which is
announced nowhere because deleting was the owner's own act. The old conversation
stays in the conversation list. The idle clock is per key.

Pros: concurrent group threads never collide on one turn lock, and one bot can
run different agents in different threads; a direct chat keeps the one context
the person is working in, however they reply; running two tasks side by side is
one command and each is visibly numbered.

Cons: in a direct chat, two unrelated questions asked as casual
replies-in-thread share one session; the person has to know `/thread` exists.
A conversation rolled over by idleness starts cold (`/resume` brings the old one
back).

Wins because it follows the platforms' own unit of conversation in groups and
the person's own unit — one working thread — in a direct chat, and makes the
exception explicit.

### Option B — Identity per chat (the peer)

One active conversation per `(channel, chat)`, stored on the peer row.

Pros: simplest mapping; one row per chat.

Cons: in a group with threads, two threads shared one conversation and one turn
lock, so concurrent @mentions collided ("a turn is already running") and each
thread's history leaked into the other.

Loses because a group's unit of conversation is the thread (PR #245 replaced
it).

### Option C — Every thread its own conversation, in direct chats too (the design #439 replaced)

Key every platform thread separately, a direct chat's included.

Pros: one rule for groups and direct chats; parallel work needs no command.

Cons: on SeaTalk "reply in thread" is how people answer a specific earlier
message, not a request for a new task; each such reply opened a brand-new
conversation and dropped the context the person was relying on. And there was
no way to see which parallel conversations a chat had.

Loses because in a direct chat a thread is usually a reply, not a new task.

### Option D — A fresh conversation per message

Every inbound message starts its own conversation.

Pros: no identity mapping; no collisions.

Cons: the agent forgets everything between messages, which defeats driving a
coding agent over several steps from a phone.

Loses on continuity.

### Option E — Session scope as a user setting (OpenClaw's `dmScope`, cc-connect's `session_scope`)

Let the owner choose per channel whether a direct chat, a group or a thread is
one session.

Pros: every arrangement is available; a familiar knob in the bridges surveyed.

Cons: those bridges serve many senders per bot, where the right prefix really
does vary; a Coffer channel answers one paired owner
([Channel Owner Gate](channel-owner-gate.md)), so the variation the setting
exists for is mostly absent, and every turn-locking and sticky-setting path
would have to handle each scope.

Loses because one owner per channel leaves one sensible default, and `/thread`
covers the remaining case per message rather than per channel.

### Option F — One conversation per key that lives until the owner ends it

The key's conversation stays active until `/new`, whatever its age.

Pros: nothing happens the owner did not ask for.

Cons: the first message after a long break is answered inside a stale session
whose context window is full of old work. An owner who wants this has it:
`new_conversation_after_idle_hours = 0`.

Loses because a long-running chat needs a boundary the owner does not have to
remember to draw.

## Decision

A channel conversation is identified by `(channel, chat, thread)` in
`channel_thread_conversations`, with that key's sticky settings; a group main
timeline and a direct chat are the empty thread. Each group thread is its own
conversation. A direct chat is one conversation: its threads join it, except a
parallel thread opened with `/thread` (or, on a transport where a direct-chat
thread only exists when someone creates it, every such thread), which is its own
conversation and carries the mark `🧵#N title`. A message opens a new
conversation for its key when the active one was deleted or has been idle past
`new_conversation_after_idle_hours`.

Rules a future change must respect:

- Anything that selects a conversation, a session or a sticky choice keys on
  `conversation_thread_id`; anything that sends keys on `thread_id`.
- A parallel thread's ordinal is never reused within a chat.
- Idle time is measured per key, so each group or parallel thread rolls over
  on its own.

## Consequences

- Concurrent turns in different group threads, and in a direct chat and its
  parallel threads, run independently.
- A new transport declares whether a direct-chat thread is a reply
  (`direct_threads_are_replies`) and implements `open_thread` for `/thread`.
- A quiet chat does not carry a stale session.
- Enforced by: `channel_thread_conversations` and its `parallel_ordinal` and
  `parallel_title` columns (`infrastructure/channel/thread_persistence.py`),
  `application/channel/conversation_ops.py`,
  `application/channel/parallel_threads.py`.
