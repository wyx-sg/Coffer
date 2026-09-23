# Data Model: Chat

Two tables, one JSON column, one block union, one event union. Everything a
turn produces lands in the two tables; everything a turn streams is the event
union, which is a wire contract and not storage.

## `conversations`

One row per thread, whatever opened it. Not a Resource of the kind-agnostic
Resource framework (see "Persist conversations and messages in SQLite") —
conversations have no scope, no reach, and no credential, and they are created
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
| `status` | TEXT | `complete` \| `streaming` \| `failed`. A row is written `streaming` before the turn's first event and finalised in place (see "Sweep streaming rows left by a crashed daemon"). |
| `model_id` | TEXT, NULL | The model the turn ran on, when the adapter named one. Never read back as configuration. |
| `prompt_tokens` | INTEGER, NULL | |
| `completion_tokens` | INTEGER, NULL | |
| `created_at` | TIMESTAMP | |

Constraints: `uq_chat_messages_conv_seq (conversation_id, seq)` — one message
per position, which is what makes the sequence a sequence — and
`idx_chat_messages_conv (conversation_id, seq)`, the history read of "Bound turn
context to the most recent 200 messages".

### Content blocks

A message's `content` is an ordered list of a four-member union, stored as JSON
and discriminated by `type`:

| `type` | Fields | Notes |
| --- | --- | --- |
| `text` | `text` | |
| `tool_use` | `tool_use_id`, `tool_name`, `tool_input` | Rendered as its own card. |
| `tool_result` | `tool_use_id`, `tool_name`, `output`, `error` | Pairs with its `tool_use` by id. |
| `attachment` | `path`, `mime`, `filename` | A **reference**: bytes stay on disk. `path` is never emitted to the wire — the API exposes `filename` and `mime` only. |

### The attachment value object

What an adapter is handed for a turn is not the block but an `Attachment`
(`path`, `mime`, `filename`), re-derived from the last user message in history
at turn time (see "Re-materialise attachments from persisted history"). Audio is
transcribed and documents are extracted before the adapter sees them; images and
anything else survive as attachments for the adapter to materialise natively.

## The event union — a wire contract, not a table

`turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`,
`turn_error`, `queue_changed`. Each member's `type` discriminator **is** the SSE
event name (see "Use the wire event name as the type discriminator"), so the
union is the contract the page's reducer dispatches on. `queue_changed` is
conversation-level rather than turn-level: broadcast by the orchestrator, never
emitted by an adapter, and never accumulated into the assistant message — which
is why the bus replays only its latest value (see "Replay without
double-rendering").

## Non-persistent state

Held per conversation in one process-global dict, never in the database (see
"Release turn state nobody needs"): the event bus with its replay buffer, the
in-flight turn, the pending message queue, and the queue's pause flag. A daemon
restart therefore drops uncommitted queued messages and leaves in-flight turns
to the startup sweep (see "Sweep streaming rows left by a crashed daemon"). A
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
| `AGENT_CONFIG_REJECTED` | The named agent refuses the configuration — e.g. a `cwd` that is not an existing directory. |
| `TURN_IN_PROGRESS` | The immediate-or-refuse entry point was asked to start a turn while one is running. The queueing path ("Queue messages sent during a turn") never raises it. |

## What points at a conversation from outside

The channel kind keeps its own table mapping `(channel, chat_id, thread_id)` to
a conversation id. That pointer is **soft**: there is no foreign key, chat does
not maintain it, and it may dangle after a conversation is deleted. The table is
channels' (spec [channels](../channels/spec.md)); this note records only that
chat does not treat an inbound pointer as a reason to keep a row alive.

## Migration lineage

`20260612_0012_chat_tables` created both tables;
`20260612_0013_conversation_archive` added `archived_at`;
`20260612_0018_conversation_agent_config` added the JSON column;
`20260613_0020_conversation_retention_reset` re-seeded the retention defaults;
`20260614_0021_conversation_origin` added the channel return address, and
`20260621_0034_drop_conversation_origin_peer_display` dropped what it did not
need; `20260621_0036_chat_models_to_provider_resources` moved model state out of
the conversation; `20260916_0083_drop_conversation_model_id` removed the last of
it, leaving the model on the message that ran (`model_id`) and on
`agent_config` as an override — one column answering one question each.
`20260918_0096_cross_references_point_at_uids` renamed `channel_name` to
`channel_uid` and rewrote each stored channel name into that channel's uid;
`20260923_0102_conversation_agent_key_has_no_default` dropped the `builtin`
server default from `agent_key`, rebuilding the table with its rows, `NOT NULL`
and indexes unchanged.
