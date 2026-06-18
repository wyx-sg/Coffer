# Data Model: 009 — Channels

> 中文版: [data-model.zh.md](./data-model.zh.md)

## Resource: `channel:<name>`

Channels are rows in the existing `resources` table (kind = `channel`).
`config_json` is validated by a discriminated Pydantic union on
`channel_type`:

```
ChannelConfig (discriminator: channel_type)
├── common (both types, _CommonChannelFields)
│   ├── default_agent: str = "claude_code"  # chat provider key; must name a registered agent
│   ├── default_agent_config: dict | None
│   ├── workspaces: list[Workspace] = []   # named cwd allowlist
│   └── default_workspace: str | None      # one of workspaces[].name
├── TelegramChannelConfig
│   ├── channel_type: "telegram"
│   └── bot_token_ref: str            # credential-store ref, probed at register
└── SeaTalkChannelConfig
    ├── channel_type: "seatalk"
    ├── app_id: str
    ├── app_secret_ref: str            # credential-store ref
    └── signing_secret_ref: str        # credential-store ref

Workspace: { name: str, path: str (absolute) }
```

Validation rules:

- `*_ref` fields must not look like raw secrets (a Telegram token pattern or
  a long high-entropy string is rejected with a pointer to the credential
  store) — same posture as `mcp_server`'s static-value secret rejection.
- The kind declares `credential_ref_extractor`, so `ResourceService` probes
  every ref before the row is written; a dangling ref aborts registration.
- `default_agent` is a chat **provider key** (e.g. `claude_code`, underscore) —
  the key the turn orchestrator resolves an agent by — not the `claude-code`
  resource name; a hyphenated value passes registration but fails at turn time
  with `UNKNOWN_AGENT`, leaving the bot silently dead. It is validated against
  the live agent registry (ADR-024 retired the old `builtin` pseudo-agent) at
  **both** create (`validate_config`) and edit (`on_update_config`): an unknown
  agent is rejected up front rather than failing silently on the first turn.
  Validation is skipped only when the registry is empty, so a misconfigured
  registry never blocks all channel writes. `default_agent_config` is still a
  pass-through.
- `workspaces` are the cwd allowlist for agents chosen from this channel.
  Shape (unique names, absolute paths, `default_workspace ∈ names`) is checked
  by the Pydantic model; the kind's `validate_config` hook additionally
  requires each `path` to be an existing directory at registration, so a bad
  workspace aborts registration with nothing persisted. A chat message never
  supplies a bare path — only a workspace name. When a channel declares no
  workspace (and the peer picks none), a turn falls back to the Coffer-managed
  workspace `~/.coffer/workspace` (created on first use) rather than failing —
  so a channel works out of the box without configuring a workspace.

## Table: `channel_peers`

The paired owner and the conversation pointer. One row per channel today;
keyed by chat id so future group support is a new row, not a migration.

| column                   | type                                         | notes                                                                                                                                               |
| ------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                     | INTEGER PK                                   |                                                                                                                                                     |
| `resource_id`            | INTEGER, FK `resources.id` ON DELETE CASCADE | the channel                                                                                                                                         |
| `chat_id`                | TEXT                                         | Telegram chat id / SeaTalk employee_code                                                                                                            |
| `display_name`           | TEXT                                         | sender's name at pairing time, for UI/status                                                                                                        |
| `paired_at`              | DATETIME (UTC)                               |                                                                                                                                                     |
| `active_conversation_id` | TEXT NULL                                    | current conversation; cleared when the conversation disappears                                                                                      |
| `sender_id`              | TEXT NULL                                    | paired sender's stable id (Telegram from.id, SeaTalk employee_code); the owner gate checks it when present. NULL → chat-id-only gate (legacy peers) |
| `preferred_agent`        | TEXT NULL                                    | sticky agent choice (`/agent`); NULL → channel `default_agent`                                                                                      |
| `preferred_workspace`    | TEXT NULL                                    | sticky workspace choice (`/cwd`); NULL → channel `default_workspace`                                                                                |

Constraints: `UNIQUE (resource_id, chat_id)`; index on `resource_id`.

`active_conversation_id` is a soft reference into the chat platform's
`conversations` table (no FK across the seam): if the conversation was
deleted from the Chat page, the next inbound message detects the dangling id
and creates a fresh conversation.

`sender_id` / `preferred_agent` / `preferred_workspace` are all nullable so a
peer paired before this revision degrades gracefully: a null sender id means
the chat-id-only gate, null preferences mean the channel defaults.

Migrations: `20260612_0015_channel_tables.py` (create + symmetric downgrade);
`20260614_0022_channel_peer_differentiation.py` adds the three nullable
columns above. The model module is imported by `migrations/env.py` so Alembic
sees the metadata.

## In-memory state (never persisted)

| object              | scope            | content                                                                                      |
| ------------------- | ---------------- | -------------------------------------------------------------------------------------------- |
| `PairingCode`       | per channel      | code, expiry, remaining attempts; replaced on re-issue, dropped on success/expiry/exhaustion |
| message queue       | per peer         | bounded FIFO (10) of inbound texts awaiting their turn                                       |
| progress state      | per running turn | IM message id of the editable status message, last-edit timestamp                            |
| seatalk token cache | per channel      | app access token + expiry                                                                    |

Crash behavior: all of it evaporates with the daemon; turns are swept failed
by the chat platform's startup sweep, codes are re-issued, queues are empty.
Nothing the user relies on lives only in memory.

## Normalized envelopes (domain value objects)

```
InboundMessage:  channel name, chat_id, sender display name, sender_id, text,
                 platform message id, timestamp
OutboundText:    markdown text (rendered per adapter capability)
ChannelCapabilities: supports_edit, supports_buttons, supports_typing,
                 max_message_chars
```

Adapters translate platform payloads to/from these; the application core
never sees a Telegram update or SeaTalk event shape.

## Audit events (spec 009)

| event                    | when                                                                  |
| ------------------------ | --------------------------------------------------------------------- |
| `channel_pairing_issued` | a pairing code is generated                                           |
| `channel_paired`         | a sender claims the code and becomes the peer                         |
| `channel_notify_sent`    | notify delivers text to the peer                                      |
| `channel_turn_started`   | an inbound message drives a turn (channel, peer, agent, conversation) |

Resource lifecycle events (`resource_created` … `resource_deleted`) come from
the framework automatically. The generic per-turn `chat_turn_completed` audit
is channel-agnostic; `channel_turn_started`
adds the channel/peer/agent context that makes channel-driven work queryable.
