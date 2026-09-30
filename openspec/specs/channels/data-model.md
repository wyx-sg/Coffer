# Data Model: Channels

## Resource kind: `channel`

A channel is a resource file, `vault/resources/channel/<name>.json`
(spec resource-framework). Its `config` is validated by a discriminated
Pydantic union on `channel_type`. The per-type halves are specified in the children
([`channels/telegram`](telegram/spec.md), [`channels/seatalk`](seatalk/spec.md));
this file is where their storage shape lives, because a child spec carries only
a `spec.md`:

```
ChannelConfig (discriminator: channel_type)
├── common (both types, _CommonChannelFields)
│   ├── default_agent: str | None = None    # uid of the agent resource this channel drives
│   ├── default_agent_config: dict | None
│   ├── require_mention: bool = True        # group gating
│   ├── ignore_other_mentions: bool = False # group gating
│   ├── wait_after_text_seconds: float = 1.5     # burst quiet window after text (0–60)
│   ├── wait_after_forward_seconds: float = 5.0  # …after a forward or bare files (0–60)
│   ├── show_steps: bool = True             # step lines under the live status line
│   ├── notify_after_seconds: float = 90.0  # long-turn ping threshold (0–3600; 0 = off)
│   ├── directories: list[str] = []         # absolute paths `/dir` may switch into (≤32)
│   └── runs_on: str | None = None          # machine_id that runs the adapter
├── TelegramChannelConfig
│   ├── channel_type: "telegram"
│   └── bot_token_ref: str            # secret-store ref, probed at register
└── SeaTalkChannelConfig
    ├── channel_type: "seatalk"
    ├── app_id: str                     # authenticates the websocket register handshake
    └── app_secret_ref: str             # secret-store ref, probed at register
```

Validation rules:

- `*_ref` fields must not look like raw secrets (a Telegram token pattern or
  a long high-entropy string is rejected with a pointer to the secret
  store) — same posture as `mcp_server`'s static-value secret rejection.
- The kind declares `secret_ref_extractor`, so `ResourceService` probes
  every ref before the file is written; a dangling ref aborts registration.
- `default_agent` is the **uid of an agent resource**
  ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
  It is a cross-resource reference, so it holds the one thing about that agent
  the owner cannot change — not its registry name, and not the turn platform's
  agent key. It has **no default value**: a uid is minted per vault, so nothing
  a schema could name would stand for "the usual agent", and `None` means
  exactly what it says — this channel is bound to no agent.
  It is validated against the registered agents at **both** create (`validate_config`)
  and edit (`on_update_config`): a uid naming no registered agent is rejected up
  front rather than failing silently on the first turn. Both hooks are async,
  which `validate_config` did not have to be while this field held an agent key
  an in-memory registry could answer for; a uid is only answerable from the
  resource store. Validation is skipped only when no agent is registered at all,
  so a vault with no agents yet never blocks all channel writes.
  `default_agent_config` is still a pass-through.
- **A channel with no resolvable `default_agent` is deliberately dark.** The
  runtime gate (`application/channel/wanted.py`) declines to start its adapter
  and logs `channel.not_started` with the reason, in three cases: the channel
  names no agent at all, its own scope excludes the agent it names, or the uid
  names no agent registered here (the ordinary state of a channel that arrived
  from another machine before that machine's agents did). This replaced a
  schema default of `"claude_code"`, which was a fiction — there was never an
  agent behind it, only a key that happened to match one on most machines. The
  failure is loud and early rather than per-turn: the management surface reports
  the channel as not running, and no message is ever accepted only to be refused.
- The **agent key** the turn platform routes on survives in exactly one place:
  the live `ChannelBinding`, onto which the runtime gate projects
  `default_agent` (uid → agent resource → `config["type"]`) and the channel's scope.
  That projection is the single crossing between the two vocabularies. It
  replaced `application/channel/agent_vocabulary.py`, which existed only because
  a scope named agent RESOURCES while `default_agent` named an agent KEY and
  three call sites compared the two directly — reading every correctly-narrowed
  scope as excluding the channel's own agent.
- A channel carries NO model curation. It briefly had its own `default_model`
  and `models` allowed range; both are gone, because a channel binds an agent
  and nothing more: a new conversation runs on the bound agent's own CLI
  default, and the `/model` card offers that agent's whole catalogue and refuses
  no id. Migration `20260912_0068_drop_channel_model_curation.py` takes both keys
  off every stored channel config in one direction only, with no load-time shim
  (house rule). `_CommonChannelFields` IGNORES unknown keys, so nothing
  rejects a file still carrying them — the migration is what removes them.
- `runs_on` is the `machine_id` of the one machine whose daemon starts this
  channel's adapter (see "Bind each channel to the one machine that runs it"). It lives in `config` because it must TRAVEL:
  config is what the resource file carries between machines, while the
  channel's `enabled` / scope are reach, in `local/reach.json`, which
  deliberately stays home. `None` is unbound and runs nowhere — never "runs
  here", which a document naming nobody would mean on every machine at once.
  Migration `20260914_0079_bind_channels_to_this_machine.py` writes this
  machine's cached id into every pre-existing channel config, so a channel that
  was running before the field existed keeps running after it: until that
  revision a channel never left the machine it was registered on, so "this
  machine" is the true answer rather than a safe guess. Data-only and one
  direction, with no load-time shim (house rule); a vault whose machine id
  cannot be read is left unbound, which the surfaces show plainly rather than
  papering over with an invented id.
- A channel bound to a machine OTHER than this one is exempt from the
  `default_agent` registry check on both write paths. That check asks whether
  the channel will be able to drive anything when it starts, and a channel this
  machine never starts has no answer to give; without the exemption a channel
  synced from an owner machine that has an agent this one lacks would be
  refused at the registry door.
- A SeaTalk channel has **one inbound transport**, the outbound websocket
  connection (spec channels/seatalk "Receive every event over one outbound
  websocket connection"), so its configuration carries no transport field and no
  ingress field. The webhook-era keys — `delivery`, `signing_secret_ref`,
  `public_base_url`, `tunnel_token_ref` — were removed from every stored config by
  migration `0103` (below), in one direction for the data and with no load-time
  shim (house rule). The secret values the two removed refs cited are left
  in the secret store: a migration that deletes secrets could not be undone
  by its downgrade, and `coffer secret rm <ref>` removes them on
  purpose. A channel config refuses every key no channel type declares, so a
  file still carrying one is refused by the vault (spec vault-storage "Keep
  every vault document a JSON object that preserves what it does not know").
- Channel turns run in the Coffer-managed default workspace
  `~/.coffer/content/workspace` (created on first use).

## Pairings — `vault/state/channel-peers/<channel name>.json`

**The pairings, and nothing else.** One entry per `(channel, chat)`: the paired
owner's DM, plus one per group or thread the owner has addressed the bot in. It
answers "may this sender drive turns here". Which chats on a platform belong to
the channel's owner is the person's, and travels, so it is a vault state
document (spec vault-storage), one per channel with at least one pairing
(`ChannelPeerRepo`, `infrastructure/channel/persistence.py`):

```json
{
  "channel_uid": "3f2a9c0e8b1d4c6a9e7f0b2d4c6a8e0f",
  "format_version": 1,
  "peers": [
    {
      "chat_id": "e12345",
      "sender_id": "e12345",
      "display_name": "Ada",
      "paired_at": "2026-09-30T08:00:00+00:00"
    }
  ]
}
```

| key | notes |
| --- | ----- |
| `channel_uid` | the channel's uid — what the document is found by; the file name only follows the channel's name |
| `format_version` | the state document's format (1) |
| `peers[].chat_id` | Telegram chat id / SeaTalk employee_code or group id; unique within the document |
| `peers[].sender_id` | the paired sender's stable id (Telegram from.id, SeaTalk employee_code); the owner gate checks it when present. `null` → the chat-id-only gate |
| `peers[].display_name` | the sender's name at pairing time, for UI/status |
| `peers[].paired_at` | ISO time (UTC) |

`peers` keeps pairing order, and the owner peer is the earliest-paired entry
(`chat_id` breaks a tie), so every machine holding the document gives the same
answer. Re-pairing one chat replaces its entry without touching any other;
un-pairing the last chat removes the file. The document moves when the channel
is renamed and is deleted with it, in the channel's own commit.

Everything in it is a fact about the platform, which is why it travels: a
channel that moved to another machine without its pairings would make the
owner re-pair from their phone. What a chat's live conversation is — and the
agent a thread has stuck to — is not in it: those are `runs.db`'s thread tables
below, because conversations are machine-local. In the one-time upgrade to the
vault layout each channel's `channel_peers` rows became its document and
revision 0136 dropped the table.

## `runs.db` — the thread tables

The three tables below are history and machine-local: they name
conversations, and conversations do not travel. Each names its channel by
`resource_uid` (revision 0136 re-keyed them from the integer channel id). No
foreign key points at the channel — it is a file — so the channel's `on_delete`
deletes its thread, history and outbox rows (`delete_for_channel`).

### `channel_thread_conversations`

**Where a chat's live conversation actually is.** "Key conversation identity
by channel, chat and thread" keeps conversation identity off the pairing and
on the `(channel, chat, thread)` triple, because a peer is one owner while a
group is many threads: keyed by the peer alone, two threads of one group
collided on one conversation and the second turn was refused with "a turn is
already running".

| column                   | type                                         | notes                                                                                                        |
| ------------------------ | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `id`                     | INTEGER PK                                   |                                                                                                              |
| `resource_uid`           | VARCHAR NOT NULL                             | the channel's uid                                                                                            |
| `chat_id`                | TEXT                                         | the DM, or the group                                                                                         |
| `thread_id`              | TEXT                                         | `""` is the DM or a group's main chat; each group thread and each parallel thread is its own row             |
| `active_conversation_id` | TEXT NULL                                    | this thread's current conversation; cleared when the conversation disappears                                  |
| `preferred_agent`        | TEXT NULL                                    | this thread's sticky agent (`/new <agent>`); NULL → the channel's `default_agent`                                    |
| `updated_at`             | DATETIME (UTC)                               |                                                                                                              |
| `parallel_ordinal`       | INTEGER NULL                                 | set on a parallel thread `/thread` opened: its number within the chat; NULL on every other row                |
| `parallel_title`         | TEXT NULL                                    | that thread's title; its mark `🧵#N title` is built from the two                                              |
| `chat_kind`              | TEXT NULL                                    | `direct` / `group` — which send path reaches the thread; NULL until a message there records it                |
| `preferred_model`        | TEXT NULL                                    | the thread's sticky model (`/model`); rides only while the sticky agent is the one in effect                  |
| `preferred_effort`       | TEXT NULL                                    | the thread's sticky reasoning effort                                                                         |
| `preferred_cwd`          | TEXT NULL                                    | the thread's sticky working directory (`/dir`), one of the channel's `directories` or beneath one             |

Constraints: `UNIQUE (resource_uid, chat_id, thread_id)`; index on `resource_uid`.

`active_conversation_id` is a soft reference into the turn platform's
`conversations` table (no FK across the seam): if the conversation was deleted,
the next inbound message detects the dangling id and opens a fresh one, built
from this row's sticky agent plus the channel's defaults. The sticky agent is
dropped in favour of the channel default once the channel's scope no longer
admits it ("Limit the agents a channel may drive to its scope"), so narrowing a scope takes effect on the next conversation.

A row is only keyed by a direct-chat thread when that thread is a conversation
of its own ("Key conversation identity by channel, chat and thread"): a
parallel thread (a row with a `parallel_ordinal`), or any private-chat topic on
a transport whose direct-chat threads are deliberate (Telegram). A casual
reply-in-thread in a SeaTalk direct chat keys to the chat's `""` row. The
ordinal is `max + 1` over the chat's rows, so a number is never reused after
its conversation is replaced ("Open parallel conversations beside a direct chat").

Migrations: `20260708_0041_channel_thread_conversations.py` creates it;
`20260928_0104_channel_parallel_threads.py` adds `parallel_ordinal` and
`parallel_title`, nullable, with no backfill: the direct-chat thread rows that
exist were casual replies, and leaving them without an ordinal is what folds
them into the direct chat's conversation. Reversible by dropping both columns.
`20260930_0108_channel_sticky_settings_history_outbox.py` adds `chat_kind` and
the three `preferred_*` settings, nullable, no backfill; 0136 re-keys it to
`resource_uid`.

A group's `thread_id=""` row doubles as the **group's defaults** ("Set a
group's defaults from its main chat"): a group thread with no setting of its own
opens with the group row's, except that a model and effort chosen for another
agent are not inherited.

### `channel_thread_history`

Every conversation a chat thread opened — what `/resume` lists ("Resume an
earlier conversation from chat") and what a reply typed on the web is mirrored
back through (spec chat "Mirror a web reply into the channel it came from").

| column            | type                                         | notes                                     |
| ----------------- | -------------------------------------------- | ----------------------------------------- |
| `id`              | INTEGER PK                                   | order of opening                          |
| `resource_uid`    | VARCHAR NOT NULL                             | the channel's uid                         |
| `chat_id`         | TEXT                                         | the chat                                  |
| `thread_id`       | TEXT                                         | the conversation thread (`""` for a DM)   |
| `conversation_id` | TEXT, UNIQUE                                 | soft reference into `conversations`       |
| `chat_kind`       | TEXT NULL                                    | `direct` / `group`, when known            |
| `opened_at`       | DATETIME (UTC)                               |                                           |

Index on `(resource_uid, chat_id, thread_id)`. Migration 0108 creates it; 0136
re-keys it to `resource_uid`.

### `channel_outbox`

Messages Coffer owes a chat and has not delivered: a web reply (`kind=reply`,
stored with its `(from Coffer) ` prefix) and the agent's answer collected behind
it (`kind=answer`). A row is marked delivered, never deleted by a failed send.

| column            | type                                         | notes                                   |
| ----------------- | -------------------------------------------- | --------------------------------------- |
| `id`              | INTEGER PK                                   | delivery order                          |
| `resource_uid`    | VARCHAR NOT NULL                             | the channel's uid                       |
| `chat_id`         | TEXT                                         |                                         |
| `thread_id`       | TEXT                                         |                                         |
| `chat_kind`       | TEXT                                         | `direct` / `group`                      |
| `conversation_id` | TEXT                                         | the conversation the message belongs to |
| `kind`            | TEXT                                         | `reply` / `answer`                      |
| `text`            | TEXT                                         | what is sent                            |
| `created_at`      | DATETIME (UTC)                               |                                         |
| `delivered_at`    | DATETIME NULL                                | NULL while pending                      |

Indexes on `(resource_uid, delivered_at)` and `conversation_id`. Migration 0108
creates it; 0136 re-keys it to `resource_uid`.

## Migrations that touch a channel's config

These Alembic data migrations ran against channel configs while resources were
rows of the pre-vault database; they are its history, and the one-time upgrade
carried their result into the resource files.

| revision | what it does |
| --- | --- |
| `20260710_0047_channel_runs_on_to_scope.py` | backfills `scope_json` from the then-current `config_json.runs_on`, for the machine axis on reach that has since been withdrawn |
| `20260912_0068_drop_channel_model_curation.py` | strips `default_model` and `models` off every stored channel config |
| `20260914_0079_bind_channels_to_this_machine.py` | writes this machine's id into every channel that carries no `runs_on` |
| `20260915_0080_repair_stale_channel_bindings.py` | replaces a `runs_on` that **cannot** be a machine id — the withdrawn axis wrote ULIDs under this very key — with this machine, the answer an absent key would have given |
| `20260915_0081_channel_scope_names_agent_resources.py` | rewrites each channel's stored scope from agent **keys** into agent **resource names** — an intermediate step, superseded by 0096 |
| `20260918_0096_cross_references_point_at_uids.py` | rewrites each channel's stored scope from agent resource names into agent **uids**, and its `default_agent` from an agent key into an agent uid (it also renames `conversations.channel_name` to `channel_uid`) |
| `20260918_0099_credential_refs_stop_naming_their_resource.py` | rewrites every `*_ref` field of a channel config (`bot_token_ref`, `app_secret_ref`, `signing_secret_ref`, `tunnel_token_ref`) from `channel/<name>/<secret>` to an address that does not spell the channel's name, moving the secret row with it |
| `20260924_0103_seatalk_channels_drop_webhook_fields.py` | removes `delivery`, `signing_secret_ref`, `public_base_url` and `tunnel_token_ref` from every SeaTalk channel config, leaving the secret values the refs cited in the store; the downgrade writes `delivery: "websocket"` back, the value every rewritten channel now behaves as and the only one the older model accepts without a signing secret |

All eight rewrite channel config data with no load-time shim (house rule), and
all but 0103 in one direction only; 0096 also renames a `conversations` column,
and that schema half reverses on downgrade while the data half does not. 0103's
downgrade does not restore the removed keys either — it writes only the
`delivery` value an older build needs to accept the row.

## In-memory state (never persisted)

| object              | scope            | content                                                                                      |
| ------------------- | ---------------- | -------------------------------------------------------------------------------------------- |
| `PairingCode`       | per channel      | code, expiry, remaining attempts; replaced on re-issue, dropped on success/expiry/exhaustion |
| live-surface state  | per running turn | the handle of the one surface the turn is growing, and the transport's own update buffer     |
| seatalk token cache | per channel      | app access token + expiry                                                                    |
| seen-event ids      | per channel      | for de-duplicating a redelivered platform event                                              |

**The channel keeps no message queue of its own.** A message arriving mid-turn
goes to the orchestrator's `enqueue_message` exactly as a web message does, so
both surfaces drain one FIFO per conversation and a turn finishing on either
advances it (spec chat). What the channel owns is a *refusal threshold*:
`QUEUE_MAX = 10` is compared against that conversation's own pending queue, and
past it the chat is told the bot is busy rather than the message being buffered
here. The web composer is not bounded.

Crash behavior: all of it evaporates with the daemon; turns are swept failed
by the turn platform's startup sweep, codes are re-issued, queues are empty.
Nothing the user relies on lives only in memory.

## Normalized envelopes (domain value objects)

```
InboundAttachment:  on-disk path, mime, filename — the bytes are already
                    downloaded and never enter the chat DB
InboundMessage:     channel name, chat_id, text, platform message id, timestamp;
                    the sender as three values — sender_id (the owner gate),
                    sender_mention_id and sender_mention_email (the @mention of
                    the asker) — plus sender_display; chat_kind, chat_title,
                    thread_id, quoted_message_id; addressed and mentions_others
                    (group gating); attachments; ephemeral_id
InboundCallback:    a selection-card tap: the opaque `data` value, callback_id,
                    platform message id, and the same chat/thread/sender
                    identity a message carries, so a tap is
                    owner-gated and answered in its own group/thread
InboundLifecycle:   the bot's own standing in a chat changed — removed, or the
                    group turned external
InboundStop:        the platform's own stop control was pressed
ChoiceButton:       label + opaque value; a list of them renders as a card
EphemeralTarget:    who a privately-delivered reply is addressed to
SentMessage:        what a send returned, so a later rewrite can address it
ChannelCapabilities: supports_live_text, live_text_persists, supports_edit,
                    supports_card_update, supports_buttons, supports_typing,
                    supports_reactions, supports_media, supports_groups,
                    supports_history_fetch, max_message_chars,
                    mention_template, mention_email_template — how the
                    transport spells an @mention of an id (or of an email
                    address); an empty template means it cannot mention
```

Adapters translate platform payloads to/from these; the application core
never sees a Telegram update or SeaTalk event shape. `supports_live_text` and
`supports_edit` are independent on purpose — SeaTalk answers yes to the first
and no to the second (see "Grow a reply in place on one live surface").

## Audit events (spec channels)

| event                    | when                                                                  |
| ------------------------ | --------------------------------------------------------------------- |
| `channel_pairing_issued` | a pairing code is generated                                           |
| `channel_paired`         | a sender claims the code and becomes the peer                         |

Resource lifecycle events (`resource_created` … `resource_deleted`) come from
the framework automatically. Turn activity is **not** audited: a turn happening
is neither irreversible, security-sensitive, nor invisible afterwards — the
conversation and its messages are the record. Pairing is audited because it
grants a sender the right to drive turns, which is exactly the kind of change
the log exists for.
