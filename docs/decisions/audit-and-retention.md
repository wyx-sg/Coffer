# Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table

> **Superseded in part (2026-10-04).** The change `move-agent-sessions-to-terminal` removed the web chat and Coffer's copy of conversation text. The conversation retention entries and the `content/chat-media/` sweep are gone; the retention registry, the `local/retention.json` policy file and the `channel-media` attachments sweep stand.

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [Resource Framework Upfront](resource-framework-upfront.md),
[Kind Plugin Contract](kind-plugin-contract.md),
[A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md),
[History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](history-is-one-sqlite-file-written-only-by-the-daemon.md),
[Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md),
[`runs.db` Gives Pruned Space Back With a Threshold `VACUUM`, and Copies Itself With `VACUUM INTO`](runs-db-gives-pruned-space-back.md),
[The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md),
spec resource-framework "Audit every lifecycle change",
spec resource-framework "Prune each registered log table on its own retention period",
spec mcp-gateway "Record invocations with redacted, bounded content",
[Record Tool Call Content, Masked Where the Secrets Are Known and Cut at 16 KB](record-tool-call-content-redacted-and-bounded.md),
spec vault-storage "Store state in five classes by nature",
architecture [observability](../../docs-site/architecture/observability.md),
research note [activity and audit](../research/activity-and-audit.md),
PRs #14, #328, #406

## Context

Coffer changes things the user cares about on their behalf: it writes into
agents' native config files, delivers and reclaims skills, switches model
providers, resolves secrets for a child process, applies changes arriving from
another machine, and runs background workers that rewrite knowledge and memory.
Changes arrive from four surfaces — the web UI, the CLI, raw REST, and the
daemon itself — plus sync and the workers. When something is wrong the user
needs to answer *what changed, when, and who did it*, across every kind, in one
place.

Separately, the MCP gateway forwards every tool call an agent makes. The user
wants to see which tools are used, how long they take and whether they fail.
Those calls carry arguments and results that routinely contain source code,
customer data and tokens echoed back by an upstream.

Both records grow without bound in `runs.db`, the single-user history database
([History Is One SQLite File](history-is-one-sqlite-file-written-only-by-the-daemon.md)),
and so do several other time-ordered tables (sync rounds, chat conversations,
model usage).

## Options Considered

### Option A — a structured audit table with a required actor, a metadata-only invocation log, and a per-table retention registry (chosen)

**Audit log.** One `audit_log` table in `runs.db` (`infrastructure/persistence/models.py`)
written only through `AuditService.record` (`application/audit_service.py`).
Every row has an event type from one shared vocabulary (`AuditEventType` in
`domain/audit.py` — the framework's resource and retention events plus each
kind's own: skill, knowledge, memory, channel, secret, provider, sync,
agent-config events), an actor, a timestamp, and a `details` payload. The
actor is never optional on a mutation path: every mutating `ResourceService`
method takes `actor` as a required keyword; the HTTP surface derives it from
`X-Coffer-Actor` (the UI sends `ui`, the CLI `cli`, a bare REST call gets
`api`; values are bounded to a short lowercase identifier or refused with 400),
and the daemon's own work records `system`, `sync` or a named worker such as
`system:memory-aggregate-worker`. A row stores the resource's
`resource_uid` *and* the kind and name it had at that moment, so one resource's
trail is queried by uid and survives a rename while each row still says what the
resource was called then. A kind's `audit_redactor` strips secret-bearing
config (e.g. `mcp_server` drops `transport.env` and `transport.headers`) before
`details` is stored. `details` says what changed: the old and new title of a
rename, the `from` and `to` of a switch, and for a hand edit of a text file
under `knowledge/` or `skills/` a unified diff cut at 8 KB. Every audited event
is also mirrored as one structured line in the daemon log, carrying the same
redacted `details` cut at 2 KB; the audit row, the invocation rows
and the log lines of one request or turn share a trace id.

**Invocation log.** `mcp_invocations` records, per tool call, resource read or
prompt fetch: timestamp, the server's uid, capability type and key, duration,
session id, the calling agent's uid, the trace id and status (`ok`, `error`, `timeout`, `denied`). What the call
carried — arguments, result or error, a custom tool's request and response — is
stored masked and cut, as decided in
[Record Tool Call Content](record-tool-call-content-redacted-and-bounded.md).
The `error_message` column is Coffer-authored only: a `CofferError`'s message is kept, anything else
is reduced to its class name, and an in-band `isError: true` tool result is
recorded as `error` with a fixed marker rather than its content
(`application/mcp/gateway_handlers.py`). Coffer's own built-in tools are
logged in the same table under the reserved server uid `coffer`, so retention
and the Activity page treat them uniformly; a row keyed on a server that has
since been deleted stays in the log and simply joins to nothing.

**Retention.** Each log-style table is declared at the composition root as a
`PrunableTable` (name, timestamp column, default days, optional two-stage
archive action) in a `PrunableRegistry` (`application/retention_registry.py`):
`audit_log` 365 days, `mcp_invocations` 30, `sync_runs` 90, idle conversations
archived after 7 and deleted 30 days after archival, and the model usage
history (`usage_requests` following the invocation window, `usage_daily` kept
365 days). The user's setting per table (days, or none for keep forever; zero
and negative are refused) is a machine-local file, `local/retention.json`,
seeded from the registry at startup and never overwritten once the user has
changed it. The SQL repository
(`infrastructure/persistence/retention_repo.py`) is constructed with an
allowlist derived from the same registry and checks table and column against it
before building any statement, so no user-supplied identifier reaches SQL.
`RetentionWorker` prunes on start and every 6 hours, on the same cadence as
the shim and upstream log files and the two attachment media directories
(`content/chat-media/`, `content/channel-media/`, one `attachments` policy, 30 days by default and adjustable); the Data tab and
`POST …/prune` run it on demand; changing a policy is itself audited.

Pros: one queryable answer to "what happened" across every kind; the actor
makes UI, CLI, sync and worker changes distinguishable; the invocation log is
useful for usage and failure analysis; a new log table gets retention by registering, with no
new SQL. Cons: `details` is only as safe as each kind's redactor; the event
vocabulary is one enum every kind edits.

### Option B — log invocation arguments and results unmasked

Pros: full replay and debugging. Cons: every tool call's payload — file
contents, query results, tokens an upstream echoes back in an error — would land
in a plaintext SQLite file that outlives the session, contradicting the rule
that plaintext secrets exist only in memory at the moment of use
([The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md)).
Lost. Payloads are kept only masked and cut, which
[Record Tool Call Content](record-tool-call-content-redacted-and-bounded.md)
argues on its own.

### Option C — export audit and invocation events over OpenTelemetry

Emit spans and events to an OTLP collector and let the user's observability
stack store and query them. Pros: standard tooling, dashboards and alerting;
no retention code in Coffer. Cons: a single-user desktop tool would require the
user to run a collector and a backend before the Activity page could show
anything; the UI would have to query a third-party store; and the audit trail
is product data (it drives per-resource history on detail pages), not telemetry
that may be sampled or dropped. Lost for the built-in record; nothing prevents
adding an exporter later beside it.

### Option D — append-only log files instead of tables

Write audit and invocation events as JSON lines to rotating files. Pros:
tamper-evident append-only semantics; trivial to tail. Cons: per-resource
history, filters by kind, event type and time, and pagination on the Activity
page all become file scans; a rename-surviving join to the resource needs an
index anyway. Lost for the structured records; the daemon log remains a file,
and audited events are mirrored into it for whoever is tailing it.

### Option E — no retention, or one global TTL

Pros: simplest; nothing to configure. Cons: without retention the invocation
log grows by every tool call an agent makes, forever (shim log files, which had
no pruning until PR #328, had reached 2,137 files and 40 MB). One global TTL
cannot express that a year of audit history is cheap and wanted while a month
of invocations is plenty, or that chat conversations need a two-stage
archive-then-delete. Lost: per-table periods, each with its own default.

## Decision

Every lifecycle change to any resource or capability is written to one
`audit_log` with a required actor, one shared event vocabulary, the resource's
local id plus the label it had then, and kind-redacted details. Every MCP call
through the gateway is written to `mcp_invocations`, with a Coffer-authored
error summary and, while recording is on, its masked and cut content. Every log-style
table is pruned on its own retention period from a registry of prunable tables;
only a registered table and column can be pruned, and policy changes are
audited. The audit and invocation logs are machine-local and never sync.

## Consequences

- A new kind contributes its own event types to `AuditEventType` rather than
  growing a private log, and a kind whose config can hold secrets must supply
  an `audit_redactor`.
- A new log table is pruned by adding a `PrunableTable` at the composition
  root; the allowlist follows automatically.
- A policy for a table that stops existing prunes nothing rather than
  erroring, because policies are seeded and never deleted.
- Audit `details` reach `daemon.log`, so a kind's redactor is the one guard for
  both the row and the log line.
- The Activity page reads these two records and the daemon log from their
  owners' routes; each machine's history is its own.
