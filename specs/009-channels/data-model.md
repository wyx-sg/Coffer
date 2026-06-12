# Data Model: 009 — Channels

> 中文版: [data-model.zh.md](./data-model.zh.md)

## Resource: `channel:<name>`

Channels are rows in the existing `resources` table (kind = `channel`).
`config_json` is validated by a discriminated Pydantic union on
`channel_type`:

```
ChannelConfig (discriminator: channel_type)
├── TelegramChannelConfig
│   ├── channel_type: "telegram"
│   ├── bot_token_ref: str            # credential-store ref, probed at register
│   ├── default_agent: str = "builtin"
│   └── default_agent_config: dict | None
└── SeaTalkChannelConfig
    ├── channel_type: "seatalk"
    ├── app_id: str
    ├── app_secret_ref: str            # credential-store ref
    ├── signing_secret_ref: str        # credential-store ref
    ├── default_agent: str = "builtin"
    └── default_agent_config: dict | None
```

Validation rules:

- `*_ref` fields must not look like raw secrets (a Telegram token pattern or
  a long high-entropy string is rejected with a pointer to the credential
  store) — same posture as `mcp_server`'s static-value secret rejection.
- The kind declares `credential_ref_extractor`, so `ResourceService` probes
  every ref before the row is written; a dangling ref aborts registration.
- `default_agent` / `default_agent_config` are not validated at registration
  (the agent registry validates at conversation creation, the platform's
  authoritative gate); an invalid agent surfaces on first contact as a turn
  error.

## Table: `channel_peers`

The paired owner and the conversation pointer. One row per channel today;
keyed by chat id so future group support is a new row, not a migration.

| column | type | notes |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `resource_id` | INTEGER, FK `resources.id` ON DELETE CASCADE | the channel |
| `chat_id` | TEXT | Telegram chat id / SeaTalk employee_code |
| `display_name` | TEXT | sender's name at pairing time, for UI/status |
| `paired_at` | DATETIME (UTC) | |
| `active_conversation_id` | TEXT NULL | current conversation; cleared when the conversation disappears |

Constraints: `UNIQUE (resource_id, chat_id)`; index on `resource_id`.

`active_conversation_id` is a soft reference into the chat platform's
`conversations` table (no FK across the seam): if the conversation was
deleted from the Chat page, the next inbound message detects the dangling id
and creates a fresh conversation.

Migration: `20260612_0015_channel_tables.py` (create + symmetric downgrade);
the model module is imported by `migrations/env.py` so Alembic sees the
metadata.

## In-memory state (never persisted)

| object | scope | content |
| --- | --- | --- |
| `PairingCode` | per channel | code, expiry, remaining attempts; replaced on re-issue, dropped on success/expiry/exhaustion |
| message queue | per peer | bounded FIFO (10) of inbound texts awaiting their turn |
| progress state | per running turn | IM message id of the editable status message, last-edit timestamp |
| approval routing | per pending approval | `request_id ↔ (chat, prompt message id)` so a button tap resolves the right gate and updates the right message |
| seatalk token cache | per channel | app access token + expiry |

Crash behavior: all of it evaporates with the daemon; turns are swept failed
by the chat platform's startup sweep, codes are re-issued, queues are empty.
Nothing the user relies on lives only in memory.

## Normalized envelopes (domain value objects)

```
InboundMessage:  channel name, chat_id, sender display name, text,
                 platform message id, timestamp
ApprovalClick:   channel name, chat_id, value (request id + decision),
                 prompt message id
OutboundText:    markdown text (rendered per adapter capability)
ChannelCapabilities: supports_edit, supports_buttons, supports_typing,
                 max_message_chars
```

Adapters translate platform payloads to/from these; the application core
never sees a Telegram update or SeaTalk event shape.

## Audit events (spec 009)

| event | when |
| --- | --- |
| `channel_pairing_issued` | a pairing code is generated |
| `channel_paired` | a sender claims the code and becomes the peer |
| `channel_notify_sent` | notify delivers text to the peer |

Resource lifecycle events (`resource_created` … `resource_deleted`) come from
the framework automatically. Conversation/turn activity is audited by the
chat platform; the channel layer adds nothing there.
