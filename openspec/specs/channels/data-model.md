# Data Model: Channels

## Resource kind: `channel`

Channels are rows in the existing `resources` table (kind = `channel`).
`config_json` is validated by a discriminated Pydantic union on
`channel_type`. The per-type halves are specified in the children
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
│   └── runs_on: str | None = None          # machine_id that runs the adapter
├── TelegramChannelConfig
│   ├── channel_type: "telegram"
│   └── bot_token_ref: str            # credential-store ref, probed at register
└── SeaTalkChannelConfig
    ├── channel_type: "seatalk"
    ├── delivery: "webhook" | "websocket" = "webhook"  # inbound transport (spec channels/seatalk)
    ├── app_id: str                     # required on both
    ├── app_secret_ref: str             # credential-store ref; required on both
    ├── signing_secret_ref: str | None  # webhook: required — websocket: forbidden
    ├── public_base_url: str | None     # webhook only: tunnel public base URL (https://host)
    └── tunnel_token_ref: str | None    # webhook only: cloudflared token ref (managed tunnel)
```

Validation rules:

- `*_ref` fields must not look like raw secrets (a Telegram token pattern or
  a long high-entropy string is rejected with a pointer to the credential
  store) — same posture as `mcp_server`'s static-value secret rejection.
- The kind declares `credential_ref_extractor`, so `ResourceService` probes
  every ref before the row is written; a dangling ref aborts registration.
- `default_agent` is the **uid of an agent resource**
  ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
  It is a cross-resource reference, so it holds the one thing about that agent
  the owner cannot change — not its registry name, and not the turn platform's
  agent key. It has **no default value**: a uid is minted per vault, so nothing
  a schema could name would stand for "the usual agent", and `None` means
  exactly what it says — this channel is bound to no agent.
  It is validated against the agent rows at **both** create (`validate_config`)
  and edit (`on_update_config`): a uid naming no registered agent is rejected up
  front rather than failing silently on the first turn. Both hooks are async,
  which `validate_config` did not have to be while this field held an agent key
  an in-memory registry could answer for; a uid is only answerable from the
  resource table. Validation is skipped only when no agent is registered at all,
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
  `default_agent` (uid → agent row → `config["type"]`) and the channel's scope.
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
  (house rule) — `_CommonChannelFields` forbids extra keys, so a row still
  carrying them would fail to validate on load.
- `runs_on` is the `machine_id` of the one machine whose daemon starts this
  channel's adapter (see "Bind each channel to the one machine that runs it"). It lives in `config_json` and not in a column of
  its own because it must TRAVEL: config is what a resource document carries
  between machines, while the row's `enabled` / `scope_json` carry reach, which
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
  machine never starts has no answer to give; without the exemption a converged
  channel whose owner machine has an agent this one lacks would be refused at
  the registry door every round.
- `delivery` decides which of the SeaTalk fields are legal, and one
  `model_validator(mode="after")` holds the whole rule so the allowed and the
  forbidden combination can never drift apart (spec channels/seatalk, the delivery
  requirements):

  | field                | `delivery: "webhook"`               | `delivery: "websocket"` |
  | -------------------- | ----------------------------------- | ----------------------- |
  | `app_id`             | required                            | required                |
  | `app_secret_ref`     | required                            | required                |
  | `signing_secret_ref` | **required**                        | **forbidden**           |
  | `public_base_url`    | optional                            | **forbidden**           |
  | `tunnel_token_ref`   | optional (managed tunnel when set)  | **forbidden**           |

  The forbidden half is what makes the config readable: a websocket channel has
  no request body to sign, no public URL to describe, and no tunnel to supervise,
  so a stored value for any of the three would claim a runtime arrangement that
  does not exist. Each message names the field and the delivery method it
  conflicts with, in the style of the other cross-field validators, because the
  user reaches this error by switching an existing channel's transport — the one
  moment they are holding both sets of fields at once.
- **No migration accompanies `delivery`.** Every channel stored before the field
  existed is a webhook channel — that was the only transport — and the field's
  default is `webhook`, so an absent value already means exactly what those rows
  already are. Nothing is reinterpreted, no value changes meaning, and there is
  no row whose behaviour depends on being rewritten; a migration here would write
  `webhook` on top of rows that already behave as `webhook`. (Contrast migration
  `0068` above, which had to *remove* keys the model no longer accepts: a new
  field with a default that matches the stored reality is the opposite case.)
  This is also why no load-time shim appears anywhere — there is no old shape to
  translate.
- Channel turns run in the Coffer-managed default workspace `~/.coffer/workspace`
  (created on first use).

## Table: `channel_peers`

**The pairing row, and nothing else.** One row per `(channel, chat)`: the paired
owner's DM, plus one row per group or thread the owner has addressed the bot in.
It answers "may this sender drive turns here", and the `(resource_id, chat_id)`
unique key is what let group support arrive as new rows rather than a migration.

| column                   | type                                         | notes                                                                                                                                               |
| ------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                     | INTEGER PK                                   |                                                                                                                                                     |
| `resource_id`            | INTEGER, FK `resources.id` ON DELETE CASCADE | the channel                                                                                                                                         |
| `chat_id`                | TEXT                                         | Telegram chat id / SeaTalk employee_code or group id                                                                                                |
| `display_name`           | TEXT                                         | sender's name at pairing time, for UI/status                                                                                                        |
| `paired_at`              | DATETIME (UTC)                               |                                                                                                                                                     |
| `sender_id`              | TEXT NULL                                    | paired sender's stable id (Telegram from.id, SeaTalk employee_code); the owner gate checks it when present. NULL → chat-id-only gate (legacy peers) |
| `active_conversation_id` | TEXT NULL                                    | **vestigial.** The live pointer moved to `channel_thread_conversations` with "Key conversation identity by channel, chat and thread"; no live path writes this column any more, so it reads NULL      |
| `preferred_agent`        | TEXT NULL                                    | **vestigial** for the same reason — the sticky agent is per thread now. The synced pairing document still carries the field, so a value can arrive from another machine; nothing reads it back |

Constraints: `UNIQUE (resource_id, chat_id)`; index on `resource_id`.

`sender_id` is nullable so a peer paired before the sender gate existed degrades
gracefully: a null sender id means the chat-id-only gate.

The table is **partly synced**, and the seam runs through the row rather than
around it (spec vault-sync, `state/channel-peers/**`). `chat_id`, `sender_id`
and `display_name` are facts about the platform, so they
travel with the channel — a channel that moved to another machine without them
would make the owner re-pair from their phone every time. The conversation
pointer is a soft reference into THIS machine's conversations, which do not
sync, so an incoming pairing keeps whatever pointer is already here.

Migrations: `20260612_0015_channel_tables.py` (create + symmetric downgrade);
`20260614_0022_channel_peer_differentiation.py` adds `sender_id`,
`preferred_agent` and a `preferred_workspace` that
`20260620_0028_drop_channel_peer_preferred_workspace.py` takes back off when
workspace switching is removed. The model module is imported by
`migrations/env.py` so Alembic sees the metadata.

## Table: `channel_thread_conversations`

**Where a chat's live conversation actually is.** "Key conversation identity
by channel, chat and thread" moved conversation identity off the peer row and
onto the `(channel, chat, thread)` triple, because a peer is one owner while a
group is many threads: keyed by the peer alone, two threads of one group
collided on one conversation and the second turn was refused with "a turn is
already running".

| column                   | type                                         | notes                                                                                                        |
| ------------------------ | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `id`                     | INTEGER PK                                   |                                                                                                              |
| `resource_id`            | INTEGER, FK `resources.id` ON DELETE CASCADE | the channel                                                                                                  |
| `chat_id`                | TEXT                                         | the DM, or the group                                                                                         |
| `thread_id`              | TEXT                                         | `""` is the DM or a group's main chat; each group thread is its own row                                       |
| `active_conversation_id` | TEXT NULL                                    | this thread's current conversation; cleared when the conversation disappears                                  |
| `preferred_agent`        | TEXT NULL                                    | this thread's sticky `/agent` choice; NULL → the channel's `default_agent`                                    |
| `updated_at`             | DATETIME (UTC)                               |                                                                                                              |

Constraints: `UNIQUE (resource_id, chat_id, thread_id)`; index on `resource_id`.

`active_conversation_id` is a soft reference into the turn platform's
`conversations` table (no FK across the seam): if the conversation was deleted,
the next inbound message detects the dangling id and opens a fresh one, built
from this row's sticky agent plus the channel's defaults. The sticky agent is
dropped in favour of the channel default once the channel's scope no longer
admits it ("Limit the agents a channel may drive to its scope"), so narrowing a scope takes effect on the next conversation.
This table is machine-local and does **not** sync — it names conversations, and
conversations do not travel.

Migration: `20260708_0041_channel_thread_conversations.py` creates it and
backfills every existing peer's conversation and sticky agent as that peer's
`thread_id=""` row, so no live DM conversation is lost. Idempotent on a database
that already holds the table; reversible by dropping it.

## Migrations that touch a channel's config

| revision | what it does |
| --- | --- |
| `20260710_0047_channel_runs_on_to_scope.py` | backfills `scope_json` from the then-current `config_json.runs_on`, for the machine axis on reach that has since been withdrawn |
| `20260912_0068_drop_channel_model_curation.py` | strips `default_model` and `models` off every stored channel config |
| `20260914_0079_bind_channels_to_this_machine.py` | writes this machine's id into every channel that carries no `runs_on` |
| `20260915_0080_repair_stale_channel_bindings.py` | replaces a `runs_on` that **cannot** be a machine id — the withdrawn axis wrote ULIDs under this very key — with this machine, the answer an absent key would have given |
| `20260915_0081_channel_scope_names_agent_resources.py` | rewrites each channel's stored scope from agent **keys** into agent **resource names**, at the moment the comparison starts reading them that way |

All five are one-direction and data-only, with no load-time shim (house rule).

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
                    supports_history_fetch, max_message_chars
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
