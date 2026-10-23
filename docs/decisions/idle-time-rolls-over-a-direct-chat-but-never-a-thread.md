# Idle Time Rolls Over a Direct Chat's Conversation, but Never a Thread's

**Status**: Accepted
**Date**: 2026-10-23
**Deciders**: Yuxing Wu
**Related**: [A Channel Conversation Is Keyed by (Channel, Chat, Thread)](channel-conversation-identity.md), [A Channel Turn Folds a Bounded Slice of Its Thread](channel-thread-context-is-a-bounded-slice.md);
spec channels ("Open a new conversation after an idle period", "Open parallel conversations beside a direct chat", "Answer the conversation commands from any paired chat");
research note [IM agent bridges](../research/im-agent-bridges.md);
PRs #681

## Context

A channel conversation is one agent session, keyed by `(channel, chat, thread)`
([channel-conversation-identity](channel-conversation-identity.md)). Some of
those keys have a natural end and some do not:

- A **direct chat** (thread `""`, its casual replies-in-thread included) and a
  **group whose main chat is one conversation** (a Telegram group without
  topics) never end. The owner never draws a line between one task and the next
  unless they remember `/new`, so a question asked after a week away lands in a
  session whose context is full of last week's work.
- A **thread** — a SeaTalk group thread, a Telegram forum topic, a parallel
  thread `/thread` opened, a Telegram private-chat topic — is a line the owner
  already drew. On SeaTalk every @mention in a group's main chat roots a fresh
  thread, so a new task is a new thread by default; coming back to an old thread
  and @mentioning the bot there means "carry on with this".

Until now a single rule covered every key: idle longer than
`new_conversation_after_idle_hours` (default 24) and the next message opens a
new conversation. In a group thread that was the wrong answer. The owner came
back to a thread the next day and was told `🆕 Started a new conversation after
24 h idle.`; the agent kept only the 20 most recent thread messages (the bounded
slice a new conversation folds) and lost its own working state — the files it
read, the tool results, how far it had got. Worse, `/resume` works only in a
direct chat, so in a group the old conversation could not be brought back from
the chat at all.

Parallel threads already have their own lifetime since #681: idle for 24 hours
they are closed, silently, and `/resume` inside one reopens it. Rolling them over
on top of that was a second rule for the same case.

How comparable bridges treat a thread
([IM agent bridges](../research/im-agent-bridges.md)):

| Product | Thread ↔ session | Reset by time |
|---|---|---|
| Claude Code in Slack, Codex in Slack | a Slack thread is one task; a later @mention in it continues | no |
| OpenACP, Omnara's Slack integration | a thread or topic per session | no |
| ccgram | a Telegram topic = a terminal window = a session; after a restart it offers Resume / Continue / Fresh | no |
| cc-connect | key may include the thread; the agent's session id is resumed next turn | only `/new` |
| OpenAB | a CLI process per thread, `session_ttl_hours = 24` | reclaims the process, not the conversation |
| OpenClaw | `session.reset` `daily` (04:00) by default, or `idle` | yes, but configurable separately for `direct`, `group` and `thread` (`resetByType`) |

Every product that treats a thread as the unit of conversation leaves the thread
alone; only OpenClaw, which centres on one long-lived main session, resets by
time, and even it gives threads a policy of their own.

## Options Considered

### Option A — Only a key without a thread rolls over (chosen)

Idle rollover applies when the conversation's key has thread `""`: a direct chat
and a group that is one conversation. Every thread-keyed conversation stays until
the owner sends `/new` in it, the conversation is deleted, or (for a parallel
thread) the idle sweep closes it. The setting keeps its name and default; its
description says what it covers.

Pros: matches what the owner means by coming back to a thread, and what every
thread-centred bridge does; fixes the group case where the old conversation
could not be resumed; one rule (`thread == ""`) with no new setting; parallel
threads keep exactly one lifetime rule.

Cons: a thread used for weeks keeps a growing context. The agents compact their
own context, the bounded slice keeps what is folded per turn small, and `/new`
in the thread starts over.

Wins because a thread is a boundary the owner already drew, and idle time is
only needed where there is none.

### Option B — A separate idle setting for threads (OpenClaw's `resetByType`)

Keep the chat-wide setting for direct chats and add a thread setting, default
0 (never).

Pros: an owner who wants threads to expire can have it.

Cons: a second knob almost nobody would change; one owner per channel leaves
little of the variation per-type policies serve in a multi-user gateway — the
same reason [channel-conversation-identity](channel-conversation-identity.md)
declined a session-scope setting. The default behaviour would equal Option A.

Loses because it adds a setting to reach the same default.

### Option C — Keep rolling threads over, and allow `/resume` in group threads

Pros: the smallest change to behaviour; the lost conversation can be brought
back.

Cons: the default is still wrong — every return to a thread after a day starts
cold and needs a manual `/resume`; it widens the group command set the owner
must learn.

Loses because it repairs the symptom and keeps the surprise.

### Option D — One rule for every key (the design this replaced)

Every conversation, thread or not, rolls over after the idle period.

Pros: one rule, no exceptions.

Cons: everything in the Context above: threads lose their working state the
owner came back for, groups cannot `/resume`, and parallel threads carry two
lifetime rules.

Loses because it treats a deliberate boundary like an absent one.

### Option E — Nothing rolls over by idle time

Every conversation lives until `/new`.

Pros: nothing happens the owner did not ask for.

Cons: a direct chat has no boundary at all; the first message after a long break
is answered inside a stale session. An owner who wants this sets the idle period
to 0.

Loses because a direct chat needs a boundary the owner does not have to remember
to draw.

## Decision

A message opens a new conversation for its key when the active one has been idle
longer than `new_conversation_after_idle_hours` (default 24; 0 never) **only when
the key has no thread** — a direct chat, or a group that is one conversation. A
conversation keyed to a thread is never rolled over by idle time; it ends by
`/new`, by being deleted, or, for a parallel thread, by the idle sweep closing
the thread.

Rules a future change must respect:

- The rollover test reads the **conversation** thread id, not the reply thread
  id, so a direct chat's casual reply-in-thread still rolls over with the
  direct chat.
- The turn driver and the thread-context folder decide with the same function
  (`rolls_over_when_idle`), so the folder never prepares context for a
  conversation the driver will not use.

## Consequences

- Returning to a group thread, a forum topic or a parallel thread continues its
  conversation; the `🆕 Started a new conversation after 24 h idle.` line is seen
  only in a direct chat or a thread-less group.
- Long-lived threads rely on the agents' own compaction and on `/new`.
- Enforced by `rolls_over_when_idle` in
  `backend/coffer/application/channel/conversation_ops.py`, used by
  `ensure_conversation` and `predict_conversation`; tested in
  `backend/tests/integration/channel/test_idle_rollover.py`.
