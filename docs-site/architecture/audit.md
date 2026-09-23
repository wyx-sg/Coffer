# Audit & accountability

::: tip Core anchor
The audit log and invocation log are Coffer's accountability records — they answer "who did what" and "who called what, when, with what outcome." They are distinct from operational observability. Both are stored locally, both are prunable, and neither ever stores secret material or user data.
:::

For operational observability (structured logs, trace correlation, error envelope), see [Observability](/architecture/observability).

## The problem this solves

A developer registers a fleet of MCP servers, imports skills, accumulates knowledge, runs chat conversations, pairs notification channels, and syncs it all across machines — driven from Claude Code, Codex, the UI, and custom scripts, often simultaneously. Without accountability records, answering even basic governance questions becomes opaque: "Who disabled the `filesystem__write_file` tool — me or the UI?" "Which server's tool did Claude Code call at 2pm, and what was the outcome?" "When was this server's config last changed?" "When was a credential last rotated, or the master key relocated?" The audit log and invocation log answer these questions without requiring the user to run a separate monitoring stack.

Coffer's approach is deliberately lean: a pair of local database tables, not a time-series database or a log-management SaaS. All records stay on-device and within the `~/.coffer/` backup footprint.

## Who reads this

**An agent and a person, asking the same question.** These records once had
three readers and three shapes: an audit-log page nobody opened, an invocation
tab whose every row belonged to an agent, and a daemon log that had to be found
on disk and grepped. The pages went. What came back is the need underneath
them: when something is misbehaving, nobody asks "what changed" or "what was
called" or "what errored" — they ask *what happened*.

So the records are shaped for that one question, and reached two ways:

- **`coffer__diagnose`** is the agent's way in. One call returns the audit log
  (what changed, and who) and the daemon log (what happened, including
  failures) on a single newest-first timeline, because an agent hitting a
  failure does not know which of the two it needs.
- **`/activity`** is the person's — one page, one tab and one table per record,
  each with the columns that record actually has and rows that expand to their
  raw form. Reading across the three is the tool's job, not the page's: one
  table could only have shown what all three have in common.
- **Event types carry both shapes.** The page renders them as plain-language
  activity lines ("Enabled demo-fs"), translated in both locales and guarded
  by the same CI check that guards error codes; the tool returns the wire value
  (`resource_enabled`), which is what an agent wants.
- **Every audited event is also a log line**, so the two records share
  vocabulary and an agent grepping one finds the other.

`GET /api/v1/audit` and `coffer audit` are unchanged for scripting. The page's
other two lanes read `GET /api/v1/mcp/invocations` (cross-server) and
`GET /api/v1/daemon/logs`.

## Audit log: lifecycle changes

Every change to any resource or capability is written to the `audit_log` table before the response is returned to the caller. The audit entry captures:

| Field           | What it tells you                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `event_type`    | Which lifecycle operation occurred (e.g. `resource_created`, `capability_disabled`, `token_rotated`) |
| `resource_id`   | The affected resource's stable id, which a rename does not change — so a trail stays one trail across `resource_renamed` |
| `resource_kind` | The kind of the affected resource (e.g. `mcp_server`), or `null` for daemon-level events             |
| `resource_name` | The specific resource name, or `null` for daemon-level events                                        |
| `actor`         | Who triggered the change: `cli`, `api`, `ui`, `system`, `user`, `agent`, or `channel`                |
| `timestamp`     | UTC time of the event                                                                                |
| `details`       | A structured JSON payload describing the change (e.g. the pre-delete snapshot, the new config diff)  |

The actor field deserves particular attention. Every surface sets it explicitly: the Typer CLI passes `X-Coffer-Actor: cli` in its HTTP calls to the daemon; REST API clients can set `X-Coffer-Actor: api` or `X-Coffer-Actor: ui`; if the header is absent, the daemon defaults to `"api"`. The daemon itself emits `system` events for automated operations like retention cleanup. This means the audit log provides an accurate picture of whether a change was initiated interactively, programmatically, or automatically.

The full set of audited event types (defined as `AuditEventType` in `domain/audit.py`), grouped by domain. There are **53** at the time of writing, and the list is deliberately short — see [What is worth auditing](#what-is-worth-auditing) below. The enum is the authority; when this page and it disagree, it is this page that is wrong.

**Resource & capability:**

| Event                                        | Trigger                                                            |
| -------------------------------------------- | ------------------------------------------------------------------ |
| `resource_created`                           | After `ResourceService.register`                                   |
| `resource_updated`                           | After config or description change                                 |
| `resource_enabled` / `resource_disabled`     | After `set_enabled` when state actually flipped                    |
| `resource_deleted`                           | After `delete`; includes a pre-delete config snapshot in `details` |
| `resource_renamed`                           | When a resource moves to a new name — its identity, not its config, changed |
| `resource_scope_updated`                     | When a resource's per-agent activation scope changes               |
| `capability_enabled` / `capability_disabled` | When a user toggles a capability                                   |

**Daemon & settings:**

| Event                         | Trigger                                       |
| ----------------------------- | --------------------------------------------- |
| `token_rotated`               | After `POST /api/v1/daemon/rotate-token`      |
| `retention_updated`           | When a retention policy is changed            |
| `internal_engine_model_set`   | When the internal engine's model is chosen    |

The daemon's **port** is a deliberate non-entry here. It is process configuration read before the database opens, and `coffer daemon port` must work with no daemon running — so the audit table is unreachable on exactly the path that matters most. Recording a change only when a daemon happened to be up would be less honest than recording none, so a `daemon_port_set` event existed briefly and was removed with its rows (revision `0069`).

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
| `agent_mcp_entry_removed`                                  | When an MCP entry is deleted from an agent's own config file             |
| `agent_mcp_entry_adopted`                                  | When an MCP entry found in an agent's own config is adopted into Coffer  |
| `agent_plugin_toggled` / `agent_plugin_uninstalled`        | When one of the agent's own plugins is enabled/disabled, or removed      |

**Skill:**

| Event                                       | Trigger                                                 |
| ------------------------------------------- | ------------------------------------------------------- |
| `skill_imported` / `skill_updated`          | When a skill is imported / updated in the master store   |
| `skill_bound` / `skill_unbound`             | When a skill is delivered to / withdrawn from an agent   |
| `skill_relinked`                            | When a skill link is repaired                            |
| `skill_drift_remediated`                    | When on-disk drift from the managed skill is repaired    |
| `skill_adopted` / `skill_unmanaged_deleted` | When an unmanaged skill is adopted / a stray is deleted  |

**Knowledge** — what destroys or rewrites content:

| Event                 | Trigger                                             |
| --------------------- | --------------------------------------------------- |
| `knowledge_written`   | When new material is submitted to a collection — queued in its inbox, or promoted straight to a document when no internal model is configured |
| `knowledge_deleted`   | When a person deletes a document                     |
| `knowledge_curated`   | When a curation pass completed over one pending item |

The `kb_*` prefix that once appeared here is gone entirely, not merely deprecated: those values were the wire form before the `knowledge_base` and `memory` kinds merged into `knowledge`, and revisions `0055` and `0077` purged the rows along with the enum members. An event type nothing can label costs more in `coffer__diagnose` than the record is worth.

`knowledge_curated` is the exception to the rule that recomputation is not audited (below). The curation pass runs unattended, on a timer, and an LLM rewrites documents the user and their agents also edit — that is a change to content, not a recomputation of a derived index, and with no review step the audit log is the only place a person sees it happened. Its `details` carry the item the pass took, the document counts before and after, how many documents were written and retired, and the model that did it. It is recorded for every completed pass, including one that decided to change nothing.

**Memory** — the derived tree, and the hook Coffer installs in someone else's settings file:

| Event                                                     | Trigger                                                                |
| --------------------------------------------------------- | ---------------------------------------------------------------------- |
| `memory_aggregated`                                       | When an aggregation pass re-derived the tree from the agents' own memory |
| `memory_organised`                                        | When an organise pass rewrote a partition                               |
| `memory_delivery_installed` / `memory_delivery_removed`   | When Coffer's session-start hook is written into / removed from an agent's settings |
| `memory_delivery_fired`                                   | When that hook actually ran — which is the only thing that distinguishes an installed hook from no feature at all |

The `memory_*` prefix here belongs to today's `memory` kind. It is **not** the retired `memory_added` / `memory_deleted` / `memory_cleared` family, which described knowledge notes and was purged with the merge. `memory_override_set` and `memory_override_cleared` went the same way in revision `0078`, with the per-fact decisions they recorded.

**Channel:**

| Event                                       | Trigger                                              |
| ------------------------------------------- | ---------------------------------------------------- |
| `channel_pairing_issued` / `channel_paired` | When a pairing code is issued / a peer claims it     |

**Provider:**

| Event                           | Trigger                                                     |
| ------------------------------- | ----------------------------------------------------------- |
| `provider_switched`             | When a connection is projected into an agent's native config |
| `provider_internal_default_set` | When a connection becomes Coffer's internal engine           |
| `provider_transcribe_default_set` | When a connection becomes the one Coffer transcribes speech on |
| `provider_projection_refused`   | When a projection write refused because the agent's native config file changed on disk between Coffer's read and its write (optimistic concurrency) |

**Sync** — the vault converges bidirectionally with a git remote the user owns, so both the rounds and the decisions about them are recorded:

| Event                  | Trigger                                                                       |
| ---------------------- | ----------------------------------------------------------------------------- |
| `sync_run`             | After a converge round, with its outcome                                       |
| `sync_confirmed` / `sync_rejected` | When the user accepts or declines a round that stopped to ask — an oversized deletion, say |
| `sync_rolled_back`     | When a round is undone                                                         |
| `sync_machine_removed` | When a machine is dropped from the set converging on this remote               |

The resource writes a converge round performs are *also* recorded as ordinary resource lifecycle events, so a change that arrived from another machine is as traceable as one made by hand.

## What is worth auditing

An event earns a row only if it meets at least one of three tests:

- **It lands outside Coffer.** An agent's config file, a symlink into someone's `~/.claude/`, a key projected into `~/.codex/config.toml`. Coffer reached into territory it does not own, and the log is the only place that fact is written down.
- **It is irreversible or security-sensitive.** A delete, a credential read, a master-key export, a token rotation. There is no state to inspect afterwards, or the reading itself is the thing worth knowing.
- **It is a low-frequency configuration change that current state cannot reveal.** A retention window changed; a capability was turned off. The current value is visible, but *that someone changed it* is not.

Twenty-seven event types were retired in 2026-09 for meeting none of these. The reasons are worth stating, because they are the same reasons that should stop the list growing back:

- **Runtime telemetry** (`daemon_started`, `chat_turn_completed`, `channel_turn_started`, `sync_completed`, …) — that the daemon ran or a turn completed belongs in a log line, not in a durable record of changes.
- **Facts a table already holds** (`capability_first_seen`) — `mcp_capability_preferences.first_seen_at` *is* that event, stored where it can be queried.
- **Idempotent recomputation** (`kb_reindexed`, `kb_document_ingested`, `memory_added`, …) — running them again changes nothing, and the result is on disk. The file is the record.
- **Detection that changed nothing** (`skill_drift_detected`, `skill_autobind_skipped`) — noticing is not doing. The *remediation* is audited; the noticing is not.
- **Low-value session state** (`conversation_created`, `conversation_archived`, …) — recoverable, visible in the thing itself, and high-volume.

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
| `sync_runs`             | Delete converge-round history older than the window | 90 days |
| `conversations_archive` | Auto-archive chats idle for this many days | 7 days   |
| `conversations`         | Delete archived chats this many days after archival | 30 days |

The user can list them at `GET /api/v1/retention/policies` and change any via `PATCH /api/v1/retention/policies/{table_name}`. Setting `retention_days` to `null` means "keep forever". Zero is forbidden. The change is audited as `retention_updated`.

### The background worker

An asyncio task running inside the daemon polls the `retention_policies` table on a configurable interval and issues `DELETE FROM <table> WHERE <timestamp_column> < ?` for each table whose `retention_days` is not null. The worker:

- Runs the delete inside a transaction so partial deletes cannot produce a half-pruned table.
- Updates `last_pruned_at` and `last_pruned_rows` in `retention_policies` after each successful prune.
- Does not block the event loop between tables — it yields between each table's delete.
- Does not cascade-delete across tables: audit entries for a deleted server are retained (the retention policy is per-table, not per-resource).
