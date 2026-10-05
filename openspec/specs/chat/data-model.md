# Data Model: Chat

One table, one JSON column, one event union. The table is an index of
conversations in `~/.coffer/runs.db` (machine-local, never synced); it holds no
conversation text (see "Keep the conversation index without its text"). The
event union is what a running turn streams: a wire contract, not storage.
Nothing a turn produces is stored; the agent's own session is the record (see
"Let the agent's own session hold the conversation").

## `conversations`

One row per channel thread. Not a Resource of the kind-agnostic Resource
framework (see "Keep the conversation index without its text") — conversations
have no scope, no reach, and no secret, and they are created by a channel's
message rather than by registration, never by the web. Every row has a channel;
the migration that removed the web chat deleted the rows that had none.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT, PK | Opaque id. |
| `agent_key` | TEXT, NOT NULL | Which registered agent runs this thread's turns. **No column default** ("Require every writer to name the agent"): it used to default to `builtin`, an agent since withdrawn, so the default could only mint an unroutable row. |
| `title` | TEXT, NOT NULL | Opens as a placeholder; replaced by the first user message's own words, unless the owner renamed it first. The owner's rename also renames the agent's native session (see "Rename and delete a conversation through its agent"). |
| `agent_config` | TEXT, NULL | JSON of the provider-owned `AgentConfig`. NULL = none stored yet. |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | Bumped at turn **start** and again at turn **finalise**, so a channel conversation sorts by its latest activity in the Conversations list (agent-registry "List every agent's sessions in one list"). |
| `channel_uid` | TEXT | The **uid** of the channel that owns this thread. A uid and not a name, because a binding has to keep naming the same channel after the user renames it (ADR resource-identity-is-an-immutable-uid); the label a person or an agent reads is resolved from it at read time. Nothing delivers a reply to it from the web any more. |
| `peer_chat_id` | TEXT | The chat id inside that channel. |

Index: `idx_conversations_updated (updated_at)` — the recency ordering of a
channel's conversations when the Conversations list is narrowed to channels
(agent-registry "List every agent's sessions in one list"); otherwise the list
is each agent's own session listing, merged.

### What a conversation carries beyond its row

`ConversationOut` (the chat contract, the single-conversation read) and a
channel-narrowed row of the session listing add fields read at request time, never
stored on the row. Each is read once for a whole page — the agents' names, the
channels and the places of the channel-bound conversations are one query each —
so a longer page costs no more queries.

| Field | Meaning |
| --- | --- |
| `running` | A turn is in flight right now — the orchestrator's in-process state. |
| `needs_you` | A question waits on the owner (see "Show which conversations wait on you"). In-memory turn state, never stored. |
| `cwd` | The directory the conversation runs in, read from `agent_config`. |
| `has_session` | A native session id is stored. The id itself is not on the wire; the daemon uses it to build the resume command (see "Open a conversation in the terminal"). |
| `channel_binding.platform` | The channel's type key (`seatalk` / `telegram`); null once the channel is deleted. |
| `channel_binding.place` | Where in the channel the conversation lives, from `channel_thread_history` and its thread row: `chat_kind` (`direct` / `group`, null when never learnt), `thread` (a thread or topic, not the chat's main timeline), `parallel_mark` (the `🧵#N title` of a `/thread` parallel conversation) and `chat_name` (a group's name when Coffer knows one; Coffer stores no group titles today, so it is null). Null when no chat is known for the conversation. |

The row also reads the agent's display name; nothing else.

### `agent_config` — the JSON column's shape

A frozen value object, not a free dict; the providers validate raw input into
it and unset fields are omitted from the stored JSON rather than written null.

| Field | Meaning |
| --- | --- |
| `cwd` | The directory a turn runs in. Optional here: a conversation whose provider has not stored one yet is represented faithfully, and it is building the adapter that requires one. |
| `session_id` | The agent's own upstream session, so the next turn resumes rather than restarts. The only link to the agent's own record of the conversation (see "Let the agent's own session hold the conversation"). A stale one costs one retry, not the conversation (see "Retry a forgotten resume id once as a fresh session"); a conversation whose session the agent has cleaned up resumes as a fresh session. |
| `model` | The agent's own model id, passed through to its CLI. Empty clears the override. |

The HTTP `agent_config` request field stays an opaque object: the typed shape is
internal, so tightening it is not a wire change.

## The event union — a wire contract, not a table

`turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`,
`turn_error`, `queue_changed`. Each member's `type` discriminator **is** the SSE
event name, so the union is the contract the channel renderer and any events
subscriber dispatch on (see "Express a turn as typed events in memory").
`queue_changed` is conversation-level rather than turn-level: broadcast by the
orchestrator, never emitted by an adapter, and replayed latest-only (see "Drop
a finished turn's replay buffer").

A `turn_error` carries a short machine `code` and a message. Three codes are the
platform's own rather than an agent's (see "Deliver partial output as events when a turn is
interrupted or fails"): `stream_ended` — the agent's stream ended without a
terminal event; `turn_timeout` — the idle watchdog cancelled a silent turn; and
`daemon_stopped` — the daemon cancelled a running turn on its way down. Every
other code is the agent adapter's.

## Non-persistent state

Held per conversation in one process-global dict, never in the database (see
"Release turn state nobody needs"): the event bus with its replay buffer, the
in-flight turn, the pending message queue, the queue's pause flag and the
pending question (its context, the questions and their state; see "Pause a turn
on a question for the owner"). A daemon restart therefore drops uncommitted
queued messages and open questions; a shutdown stops in-flight turns itself
before the database closes, and a daemon that dies outright leaves nothing
behind: the next channel message resumes the agent's session. A conversation's
state exists only while a turn, a queued message or a subscriber needs it.

An `Attachment` (`path`, `mime`, `filename`) is a turn-time value object, not a
stored one: the channel's media directory (`~/.coffer/content/channel-media`)
holds the bytes, and the reference travels to the adapter with the turn rather
than being re-derived from history. `path` is never emitted to the wire.

## Domain errors

| Code | Raised when |
| --- | --- |
| `CONVERSATION_NOT_FOUND` | Any operation naming a conversation that does not exist. |
| `UNKNOWN_AGENT` | A turn names an `agent_key` no provider answers for (see "Distinguish a missing agent path from a bad turn body"). A *subresource path* for the same key is 404 instead. |
| `AGENT_CONFIG_REJECTED` | The named agent refuses the configuration — e.g. a `cwd` that is not an existing directory — or no enabled managed agent of the type exists (`reason` `agent_not_managed`). |
| `QUESTION_CLOSED` | A question is answered after it was answered, cancelled or lost with a restart. |

## What points at a conversation from outside

The channel kind keeps its own table mapping `(channel, chat_id, thread_id)` to
a conversation id. That pointer is **soft**: there is no foreign key, chat does
not maintain it, and it may dangle after a conversation is deleted. Deleting a
conversation — or its native session from Agent › Sessions — removes the index
row, and the channel's next message opens a fresh conversation. The table is
channels' (spec [channels](../channels/spec.md)); this note records only that
chat does not treat an inbound pointer as a reason to keep a row alive.

## Migration `0149`

Drops `chat_reply_files`, `chat_messages` and `chat_conversations.archived_at`;
deletes the conversation rows no channel owns; deletes the stored retention
policy rows of `conversations_archive` and `conversations`. The downgrade
recreates the empty tables and the column and restores no data. See "Keep the
conversation index without its text", scenario "the upgrade drops the text and
keeps channel conversations". Leftover `~/.coffer/content/chat-media` files can
be deleted by hand.
