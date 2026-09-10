# Audit & accountability

::: tip Core anchor
The audit log and invocation log are Coffer's accountability records — they answer "who did what" and "who called what, when, with what outcome." They are distinct from operational observability. Both are stored locally, both are prunable, and neither ever stores secret material or user data.
:::

For operational observability (structured logs, trace correlation, error envelope), see [Observability](/architecture/observability).

## The problem this solves

A developer registers a fleet of MCP servers, imports skills, accumulates knowledge, runs chat conversations, pairs notification channels, and syncs it all across machines — driven from Claude Code, Codex, the UI, and custom scripts, often simultaneously. Without accountability records, answering even basic governance questions becomes opaque: "Who disabled the `filesystem__write_file` tool — me or the UI?" "Which server's tool did Claude Code call at 2pm, and what was the outcome?" "When was this server's config last changed?" "When was a credential last rotated, or the master key relocated?" The audit log and invocation log answer these questions without requiring the user to run a separate monitoring stack.

Coffer's approach is deliberately lean: a pair of local database tables, not a time-series database or a log-management SaaS. All records stay on-device and within the `~/.coffer/` backup footprint.

## Audit log: lifecycle changes

Every change to any resource or capability is written to the `audit_log` table before the response is returned to the caller. The audit entry captures:

| Field           | What it tells you                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `event_type`    | Which lifecycle operation occurred (e.g. `resource_created`, `capability_disabled`, `token_rotated`) |
| `resource_kind` | The kind of the affected resource (e.g. `mcp_server`), or `null` for daemon-level events             |
| `resource_name` | The specific resource name, or `null` for daemon-level events                                        |
| `actor`         | Who triggered the change: `cli`, `api`, `ui`, or `system`                                            |
| `timestamp`     | UTC time of the event                                                                                |
| `details`       | A structured JSON payload describing the change (e.g. the pre-delete snapshot, the new config diff)  |

The actor field deserves particular attention. Every surface sets it explicitly: the Typer CLI passes `X-Coffer-Actor: cli` in its HTTP calls to the daemon; REST API clients can set `X-Coffer-Actor: api` or `X-Coffer-Actor: ui`; if the header is absent, the daemon defaults to `"api"`. The daemon itself emits `system` events for automated operations like retention cleanup. This means the audit log provides an accurate picture of whether a change was initiated interactively, programmatically, or automatically.

The full set of audited event types (defined as `AuditEventType` in `domain/audit.py`), grouped by domain. There are 39, and the list is deliberately short — see [What is worth auditing](#what-is-worth-auditing) below.

**Resource & capability:**

| Event                                        | Trigger                                                            |
| -------------------------------------------- | ------------------------------------------------------------------ |
| `resource_created`                           | After `ResourceService.register`                                   |
| `resource_updated`                           | After config or description change                                 |
| `resource_enabled` / `resource_disabled`     | After `set_enabled` when state actually flipped                    |
| `resource_deleted`                           | After `delete`; includes a pre-delete config snapshot in `details` |
| `resource_scope_updated`                     | When a resource's per-agent activation scope changes               |
| `capability_enabled` / `capability_disabled` | When a user toggles a capability                                   |

**Daemon & settings:**

| Event                         | Trigger                                       |
| ----------------------------- | --------------------------------------------- |
| `token_rotated`               | After `POST /api/v1/daemon/rotate-token`      |
| `retention_updated`           | When a retention policy is changed            |
| `embedding_config_updated`    | When the embedding provider/model is changed  |
| `internal_engine_model_set`   | When the internal engine's model is chosen    |

**Credentials & master key:**

| Event                                                       | Trigger                                                           |
| ----------------------------------------------------------- | ---------------------------------------------------------------- |
| `credential_set` / `credential_read` / `credential_deleted` | After a write / read / delete in the encrypted credential store   |
| `credential_migrated`                                       | Per ref, when a legacy keychain secret is migrated into the store |
| `master_key_relocated`                                      | After the master key moves between file and keychain storage      |
| `master_key_exported` / `master_key_imported`               | Out-of-band master-key transfer to / from another machine         |

**Agent workspace** — every one of these writes a file Coffer does not own:

| Event                                                     | Trigger                                                                 |
| --------------------------------------------------------- | ----------------------------------------------------------------------- |
| `agent_config_file_written` / `agent_config_file_deleted`  | When an agent config file is written / deleted                          |
| `agent_mcp_installed` / `agent_mcp_uninstalled`            | When Coffer's MCP entry is installed into / removed from an agent       |
| `agent_mcp_entry_adopted`                                  | When an MCP entry found in an agent's own config is adopted into Coffer  |

**Skill:**

| Event                                       | Trigger                                                 |
| ------------------------------------------- | ------------------------------------------------------- |
| `skill_imported` / `skill_updated`          | When a skill is imported / updated in the master store   |
| `skill_bound` / `skill_unbound`             | When a skill is delivered to / withdrawn from an agent   |
| `skill_relinked`                            | When a skill link is repaired                            |
| `skill_drift_remediated`                    | When on-disk drift from the managed skill is repaired    |
| `skill_adopted` / `skill_unmanaged_deleted` | When an unmanaged skill is adopted / a stray is deleted  |

**Knowledge** — only the destructive pair:

| Event                 | Trigger                                      |
| --------------------- | -------------------------------------------- |
| `kb_document_deleted` | When an ingested document is deleted          |
| `memory_deleted`      | When an entry is deleted                      |
| `memory_cleared`      | When a knowledge scope's entries are cleared   |

The `kb_*` and `memory_*` prefixes are historical: they were the wire values before the two kinds merged into `knowledge`, and they are kept verbatim so existing audit rows and queries stay valid.

**Channel:**

| Event                                       | Trigger                                              |
| ------------------------------------------- | ---------------------------------------------------- |
| `channel_pairing_issued` / `channel_paired` | When a pairing code is issued / a peer claims it     |

**Provider:**

| Event                           | Trigger                                                     |
| ------------------------------- | ----------------------------------------------------------- |
| `provider_switched`             | When a connection is projected into an agent's native config |
| `provider_internal_default_set` | When a connection becomes Coffer's internal engine           |

**Export / import:** the resource writes an import performs are recorded as ordinary resource lifecycle events, so an imported change is as traceable as one made by hand. There are no configuration or conflict events, because there is no sync configuration and no conflict state ([ADR-016](/reference/adr/ADR-016-vault-export-import)).

## What is worth auditing

An event earns a row only if it meets at least one of three tests:

- **It lands outside Coffer.** An agent's config file, a symlink into someone's `~/.claude/`, a key projected into `~/.codex/config.toml`. Coffer reached into territory it does not own, and the log is the only place that fact is written down.
- **It is irreversible or security-sensitive.** A delete, a credential read, a master-key export, a token rotation. There is no state to inspect afterwards, or the reading itself is the thing worth knowing.
- **It is a low-frequency configuration change that current state cannot reveal.** A retention window changed; a capability was turned off. The current value is visible, but *that someone changed it* is not.

Twenty-seven event types were retired in 2026-09 for meeting none of these. The reasons are worth stating, because they are the same reasons that should stop the list growing back:

- **Runtime telemetry** (`daemon_started`, `chat_turn_completed`, `channel_turn_started`, `sync_completed`, …) — that the daemon ran or a turn completed belongs in a log line, not in a durable record of changes.
- **Facts a table already holds** (`capability_first_seen`) — `mcp_capability_preferences.first_seen_at` *is* that event, stored where it can be queried.
- **Idempotent recomputation** (`kb_reindexed`, `memory_organized`, `memory_reorganized`, `kb_document_ingested`, `memory_added`, …) — running them again changes nothing, and the result is on disk. The file is the record.
- **Detection that changed nothing** (`skill_drift_detected`, `skill_autobind_skipped`) — noticing is not doing. The *remediation* is audited; the noticing is not.
- **Low-value session state** (`conversation_created`, `conversation_archived`, `handoff_set`) — recoverable, visible in the thing itself, and high-volume.

The largest single win was removing `journal_append`, which had accounted for **98.5%** of all audit rows (4,318 of 4,384) while recording only a character count — the content it described was already sitting in a Markdown file.

Note that `credential_set` and `credential_deleted` are audited — the _fact_ that a secret was stored or removed is recorded. The secret value itself is never in the `details` payload.

## Invocation log: what went through the gateway

Every tool call, resource read, and prompt fetch that the daemon routes through the gateway produces one row in `mcp_invocations`. The row captures:

| Field             | What it tells you                                      |
| ----------------- | ------------------------------------------------------ |
| `timestamp`       | When the call started                                  |
| `resource_name`   | Which registered MCP server handled the call           |
| `capability_type` | `tool`, `resource`, or `prompt`                        |
| `capability_key`  | The original (unprefixed) capability name              |
| `duration_ms`     | Wall-clock milliseconds from receipt to upstream reply |
| `status`          | `ok`, `error`, `timeout`, or `denied`                  |
| `error_message`   | Populated when `status != "ok"`                        |
| `session_id`      | Per-MCP-client session correlation ID                  |

::: tip Invariant: arguments and results are never persisted
The `mcp_invocations` schema has no column for call arguments or return contents. This is a deliberate, permanent design decision — not an omission to fill later. Arguments and results may contain sensitive information (file contents, API responses, user data). Storing them would make the invocation log a potential data exfiltration channel, would inflate storage significantly, and would create a retention problem with no clear solution. The invocation log answers "who called what, when, and with what outcome" — nothing more.
:::

The `status` field distinguishes four outcomes that matter for accountability:

- **`ok`** — the upstream replied successfully within the timeout.
- **`error`** — the upstream replied with a JSON-RPC error (the error message is stored without the full response payload).
- **`timeout`** — the upstream did not reply within `request_timeout_seconds`. The upstream subprocess or HTTP connection is torn down.
- **`denied`** — the call was rejected by Coffer before reaching the upstream, because the capability is disabled or the resource is in a non-ready state. This lets the user distinguish "the upstream failed" from "I disabled this tool yesterday".

The `session_id` field correlates all invocations from a single MCP client session. A user who asks "why did Claude Code's tool call fail" can filter `mcp_invocations` by session ID to see the full sequence of calls that session made — without needing to look at Claude Code's own logs.

## Retention: bounded log growth

Log-style tables grow without bound unless pruned. The `retention_policies` table and the `RetentionService` background worker together keep growth under control.

### How a table opts in

Any table that should be prunable implements the `PrunableTable` protocol and is registered at the composition root:

```python
PrunableTable(
    name="mcp_invocations",
    timestamp_column="timestamp",
    default_retention_days=30,
    display_name="Tool invocations",
    description="Records of every capability call through the gateway",
)
```

`name` must appear in the SQL allowlist set. `timestamp_column` must appear in the column allowlist. These allowlists are hardcoded in `infrastructure/persistence/retention.py` and cannot be extended at runtime. This means the prune worker can only delete from tables the developer explicitly whitelisted — arbitrary SQL execution is not possible.

### The retention_policies table

One row per registered prunable policy. Default values seeded at first daemon startup:

| Policy                  | Action                                     | Default  |
| ----------------------- | ------------------------------------------ | -------- |
| `audit_log`             | Delete rows older than the window          | 365 days |
| `mcp_invocations`       | Delete rows older than the window          | 30 days  |
| `conversations_archive` | Auto-archive chats idle for this many days | 7 days   |
| `conversations`         | Delete archived chats this many days after archival | 30 days |

The user can change any via `PATCH /api/v1/retention/{table_name}`. Setting `retention_days` to `null` means "keep forever". Zero is forbidden. The change is audited as `retention_updated`.

### The background worker

An asyncio task running inside the daemon polls the `retention_policies` table on a configurable interval and issues `DELETE FROM <table> WHERE <timestamp_column> < ?` for each table whose `retention_days` is not null. The worker:

- Runs the delete inside a transaction so partial deletes cannot produce a half-pruned table.
- Updates `last_pruned_at` and `last_pruned_rows` in `retention_policies` after each successful prune.
- Does not block the event loop between tables — it yields between each table's delete.
- Does not cascade-delete across tables: audit entries for a deleted server are retained (the retention policy is per-table, not per-resource).

## See also

- [Architecture reference](/reference/project/architecture) — Audit, Retention, and cross-cutting concerns table
- [Spec 001 reference](/reference/specs/001-mcp-gateway/spec) — Invocation log invariant, token authentication, and `X-Coffer-Actor` header semantics
