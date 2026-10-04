# Data Model: Chat

Three tables, one JSON column, one block union, one event union. Everything a
turn produces lands in the tables, which are history in `~/.coffer/runs.db`
(machine-local, never synced); everything a turn streams is the event
union, which is a wire contract and not storage.

## `conversations`

One row per thread, whatever opened it. Not a Resource of the kind-agnostic
Resource framework (see "Persist conversations and messages in SQLite") —
conversations have no scope, no reach, and no secret, and they are created
by a message rather than by registration.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT, PK | Opaque id. |
| `agent_key` | TEXT, NOT NULL | Which registered agent runs this thread's turns. **No column default** ("Require every writer to name the agent"): it used to default to `builtin`, an agent since withdrawn, so the default could only mint an unroutable row. |
| `title` | TEXT, NOT NULL | Opens as a placeholder; replaced by the first user message's own words, unless the owner renamed it first. |
| `agent_config` | TEXT, NULL | JSON of the provider-owned `AgentConfig`. NULL = none stored yet. |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | Bumped at turn **start** and again at turn **finalise** (see "List conversations by latest activity"). |
| `archived_at` | TIMESTAMP, NULL | NULL = active. Set by the owner or by the auto-archive stage. |
| `channel_uid` | TEXT, NULL | Return address: the **uid** of the channel this thread is also reachable on. "Has a binding" iff set. A uid and not a name, because a binding has to keep naming the same channel after the user renames it (ADR resource-identity-is-an-immutable-uid); the label a person or an agent reads is resolved from it at read time. |
| `peer_chat_id` | TEXT, NULL | The chat id that return address aims at. |

Indexes: `idx_conversations_updated (updated_at)` — the recency ordering of
"List conversations by latest activity" — and `idx_conversations_archived
(archived_at)` — the active/archived split, which is two listings rather than
one filtered list.

### What a listed conversation carries beyond its row

`ConversationOut` (the chat contract) adds three things read at request time,
never stored on the row. Each is read once for a whole page — the channels, the
places of the channel-bound conversations and the previews are one query each —
so a longer page costs no more queries.

| Field | Meaning |
| --- | --- |
| `preview` | The newest message's text blocks on one line (whitespace collapsed, clipped to 160 characters with an ellipsis). A channel turn's leading context blocks (`[Message origin]` and the like) are left out. A message with no words (tool-only) is skipped for the newest one that has some; null when none does. |
| `running` | A turn is in flight right now — the orchestrator's in-process state, which a `streaming` message row only mirrors. |
| `channel_binding.platform` | The channel's type key (`seatalk` / `telegram`); null once the channel is deleted. |
| `channel_binding.place` | Where in the channel the conversation lives, from `channel_thread_history` and its thread row: `chat_kind` (`direct` / `group`, null when never learnt), `thread` (a thread or topic, not the chat's main timeline), `parallel_mark` (the `🧵#N title` of a `/thread` parallel conversation) and `chat_name` (a group's name when Coffer knows one; Coffer stores no group titles today, so it is null). Null when no chat is known for the conversation. |

### `agent_config` — the JSON column's shape

A frozen value object, not a free dict; the providers validate raw input into
it and unset fields are omitted from the stored JSON rather than written null.

| Field | Meaning |
| --- | --- |
| `cwd` | The directory a turn runs in. Optional here: a conversation whose provider has not stored one yet is represented faithfully, and it is building the adapter that requires one. |
| `session_id` | The agent's own upstream session, so the next turn resumes rather than restarts. A stale one costs one retry, not the conversation (see "Retry a forgotten resume id once as a fresh session"). |
| `model` | The agent's own model id, passed through to its CLI. Empty clears the override. |
| `effort` | How hard that model thinks. A **separate field**, not part of the model name, because that is how the agents take it. |

The HTTP `agent_config` request field stays an opaque object: the typed shape is
internal, so tightening it is not a wire change.

## `chat_messages`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT, PK | |
| `conversation_id` | TEXT, NOT NULL | Soft parent — deletion is done by the service, which removes the messages with the conversation. |
| `seq` | INTEGER, NOT NULL | Position in the thread, from 0. |
| `role` | TEXT | `user` \| `assistant`. |
| `content` | TEXT | JSON list of content blocks (below). |
| `status` | TEXT | `complete` \| `streaming` \| `stopped` \| `failed`. `stopped` is a reply the user interrupted (partial output kept); `failed` an errored or swept turn. A row is written `streaming` before the turn's first event and finalised in place (see "Sweep streaming rows left by a crashed daemon"). |
| `model_id` | TEXT, NULL | The model the turn ran on, when the adapter named one. Never read back as configuration. |
| `prompt_tokens` | INTEGER, NULL | |
| `completion_tokens` | INTEGER, NULL | |
| `created_at` | TIMESTAMP | |
| `finished_at` | TIMESTAMP, NULL | When an assistant reply ended (complete, stopped or failed). Null while it streams, on user messages, on rows from before the column existed, and on rows the startup sweep failed. |

Constraints: `uq_chat_messages_conv_seq (conversation_id, seq)` — one message
per position, which is what makes the sequence a sequence — and
`idx_chat_messages_conv (conversation_id, seq)`, the history read of "Bound turn
context to the most recent 200 messages".

## `chat_reply_files`

What one assistant reply changed in each file it wrote (see "Record what each
reply changed in each file"). One row per file per reply; none for a reply that
changed nothing and for replies from before the table existed.

| Column | Type | Notes |
| --- | --- | --- |
| `message_id` | TEXT, PK part, FK → `chat_messages.id` `ON DELETE CASCADE` | The reply. The cascade is what deletes the rows with the reply, with its conversation and with retention's prune. |
| `path` | TEXT, PK part | The file's absolute path as the agent wrote it. |
| `seq` | INTEGER, NOT NULL | Position in the reply's list, first-touched first. |
| `added` | INTEGER, NOT NULL | Lines added, counted from the diff. |
| `removed` | INTEGER, NOT NULL | Lines removed, counted from the diff. |
| `diff` | TEXT, NULL | The unified diff (3 lines of context, `--- a/<path>` / `+++ b/<path>`). NULL when `diff_omitted` is set, or for an empty file that was created. |
| `diff_omitted` | TEXT, NULL | `binary` (not UTF-8 text) or `too_large` (over 1 MB); the counts are then line totals either side. |

Index: `idx_chat_reply_files_message (message_id, seq)`. At most 200 files are kept per reply.

### Content blocks

A message's `content` is an ordered list of a four-member union, stored as JSON
and discriminated by `type`:

| `type` | Fields | Notes |
| --- | --- | --- |
| `text` | `text` | |
| `tool_use` | `tool_use_id`, `tool_name`, `tool_input` | Rendered as its own card. |
| `tool_result` | `tool_use_id`, `tool_name`, `output`, `error`, `duration_ms` | Pairs with its `tool_use` by id. `duration_ms` is how long the tool ran, stamped by the turn runner between the call and its result; absent when unknown. |
| `attachment` | `path`, `mime`, `filename` | A **reference**: bytes stay on disk — under `~/.coffer/content/channel-media` for a channel's download, `~/.coffer/content/chat-media` for a Conversations page upload. `path` is never emitted to the wire — the API exposes `filename` and `mime` only. |

### The attachment value object

What an adapter is handed for a turn is not the block but an `Attachment`
(`path`, `mime`, `filename`), re-derived from the last user message in history
at turn time (see "Re-materialise attachments from persisted history"). Audio is
transcribed and documents are extracted before the adapter sees them; images and
anything else survive as attachments for the adapter to materialise natively.

### Conversations page uploads — files, not a table

A file attached on the Conversations page is stored before its message is sent, as two
flat files under `~/.coffer/content/chat-media` (see "Upload a file for a web message"), in the
`content/` class: the user's only copy, not synced:

| File | Content |
| --- | --- |
| `<id><ext>` | The bytes. `<ext>` is the uploaded name's extension when it is short and plain, so a path-native agent still sees it. |
| `<id>.json` | `filename` (display name), `mime`, `size`, `stored` (the bytes' file name). Written after the bytes. |

`id` is 32 lowercase hex characters, opaque to the client, and the only thing a
send names (`attachment_ids`). There is no table and no link from an upload to
a conversation: a send turns each id into an `attachment` block, and the
attachments retention sweep (30 days unless the user changed it) removes both files whether or not they were sent.

## The event union — a wire contract, not a table

`turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`,
`turn_error`, `queue_changed`. Each member's `type` discriminator **is** the SSE
event name (see "Use the wire event name as the type discriminator"), so the
union is the contract the page's reducer dispatches on. `queue_changed` is
conversation-level rather than turn-level: broadcast by the orchestrator, never
emitted by an adapter, and never accumulated into the assistant message — which
is why the bus replays only its latest value (see "Replay without
double-rendering").

A `turn_error` carries a short machine `code` and a message. Three codes are the
platform's own rather than an agent's (see "Keep partial output when a turn is
interrupted or fails"): `stream_ended` — the agent's stream ended without a
terminal event; `turn_timeout` — the idle watchdog cancelled a silent turn; and
`daemon_stopped` — the daemon cancelled a running turn on its way down. Every
other code is the agent adapter's.

## Non-persistent state

Held per conversation in one process-global dict, never in the database (see
"Release turn state nobody needs"): the event bus with its replay buffer, the
in-flight turn, the pending message queue, and the queue's pause flag. A daemon
restart therefore drops uncommitted queued messages; a shutdown stops in-flight
turns itself before the database closes, and a daemon that dies outright leaves
them to the startup sweep (see "Sweep streaming rows left by a crashed daemon"). A
conversation's state exists only while a turn, a queued message or a subscriber
needs it.

## Retention entries

Two entries in the framework's own retention registry (see "Register
conversation retention in the framework registry"), tuned on the same surface as
every other retained table:

| Entry | Timestamp column | Default | Action |
| --- | --- | --- | --- |
| `conversations_archive` | `updated_at` | 7 days | Sets `archived_at` on `conversations` — reversible. |
| `conversations` | `archived_at` | 30 days | Deletes the row, and its messages with it. |

## Domain errors

| Code | Raised when |
| --- | --- |
| `CONVERSATION_NOT_FOUND` | Any operation naming a conversation that does not exist. |
| `UNKNOWN_AGENT` | A turn names an `agent_key` no provider answers for (see "Distinguish a missing agent path from a bad turn body"). A *subresource path* for the same key is 404 instead. |
| `AGENT_CONFIG_REJECTED` | The named agent refuses the configuration — e.g. a `cwd` that is not an existing directory — or no enabled managed agent of the type exists (`reason` `agent_not_managed`). |

## What points at a conversation from outside

The channel kind keeps its own table mapping `(channel, chat_id, thread_id)` to
a conversation id. That pointer is **soft**: there is no foreign key, chat does
not maintain it, and it may dangle after a conversation is deleted. The table is
channels' (spec [channels](../channels/spec.md)); this note records only that
chat does not treat an inbound pointer as a reason to keep a row alive.
