# Spec 010 — Data Model

> 中文版: [data-model.zh.md](./data-model.zh.md)

## Persistent state

### `sync_config` (single row)

Mirrors the `embedding_config` singleton pattern (one row, fixed id).

| Field              | Type    | Notes                                              |
| ------------------ | ------- | -------------------------------------------------- |
| `id`               | String  | `SINGLETON` constant primary key.                  |
| `remote`           | String? | Git remote URL; null until configured.             |
| `enabled`          | bool    | Master on/off for sync. Default `false`.           |
| `auto`             | bool    | Whether the daemon auto-sync worker runs. Default `false`. |
| `interval_seconds` | int     | Auto-sync fallback sweep interval. Default `300`.  |
| `poll_remote_seconds` | int  | Auto-sync remote-head probe cadence. Default `15`, min `5`. |
| `branch`           | String  | Git branch to sync on. Default `main`.             |
| `updated_at`       | String  | ISO-8601.                                          |

No secrets are stored here. Git remote auth is the user's ambient git
credential configuration.

### `sync_state` (single row)

Last-run status, also a singleton row.

| Field             | Type    | Notes                                                          |
| ----------------- | ------- | -------------------------------------------------------------- |
| `id`              | String  | `SINGLETON`.                                                   |
| `status`          | String  | `clean` / `syncing` / `conflicted` / `error` / `credentials_locked` / `unconfigured`. |
| `last_sync_at`    | String? | ISO-8601 of the last successful run.                           |
| `last_error`      | String? | Last error message (redacted, no secrets).                     |
| `conflict_paths`  | JSON    | List of workspace-relative paths currently in conflict.        |
| `locked_refs`     | JSON    | Credential refs present as ciphertext but undecryptable here.  |
| `quarantined_refs`| JSON    | `<kind>:<name>` refs whose import failed here; retried each run. |
| `updated_at`      | String  | ISO-8601.                                                      |

Both tables live in `infrastructure/sync/persistence.py`; migration `0017`.

### `machine_identity` (single row)

This machine's stable identity (ADR-043). Machine-local state *about* the
machine — never exported as vault data (the workspace `machines/` entry is
derived from it at export time).

| Field          | Type   | Notes                                             |
| -------------- | ------ | ------------------------------------------------- |
| `id`           | int    | `1` (CHECK-constrained singleton).                |
| `machine_id`   | String | ULID minted on first daemon start; never changes. |
| `display_name` | String | Defaults to the hostname; user-editable.          |
| `created_at`   | String | ISO-8601.                                         |
| `updated_at`   | String | ISO-8601.                                         |

Lives in `infrastructure/sync/persistence.py`; migration `0042`.

### `sync_tombstones` (ledger)

Local record of this machine's config-resource deletions, pending export as
workspace tombstone files. A row is dropped when the resource is re-registered
locally or after the 90-day TTL.

| Field        | Type   | Notes                                  |
| ------------ | ------ | -------------------------------------- |
| `id`         | int    | Autoincrement PK.                      |
| `kind`       | String | Resource kind. Unique with `name`.     |
| `name`       | String | Resource name.                         |
| `deleted_at` | String | ISO-8601 of the local deletion.        |

Lives in `infrastructure/sync/persistence.py`; migration `0043`.

## Filesystem state (the sync workspace)

Default `~/.coffer/sync/` (overridable via `$COFFER_SYNC_ROOT` for tests), a git
working tree whose `origin` is the user's remote.

```
manifest.json
machines/<machine-id>.json      per-machine registry entry (owner-written only)
machines/<machine-id>/overrides/<kind>/<name>.yaml   per-machine merge patch
knowledge/                      mirror of ~/.coffer/knowledge
memory/                         mirror of ~/.coffer/memory
skills/                         mirror of ~/.coffer/skills
resources/<kind>/<name>.yaml    one deterministic file per config resource
tombstones/resources/<kind>/<name>.json   explicit deletion record
state/<area>/...yaml            module-owned shared state docs
credentials/<ref>.enc           Fernet ciphertext, base64 text; never the key
```

### `manifest.json`

| Field             | Type   | Notes                                            |
| ----------------- | ------ | ------------------------------------------------ |
| `schema_version`  | int    | Bumped on incompatible workspace layout changes. |

Only the schema version — the manifest is byte-identical on every machine so it
can never merge-conflict. Per-machine facts live in `machines/` instead.
`schema_version` is checked on import; a workspace newer than the running build
fails fast (`SYNC_WORKSPACE_TOO_NEW`), mirroring the DB `DB_SCHEMA_TOO_NEW` rule.
Current version: **3** (2 = tombstone-driven deletion; 3 = `${HOME}`-normalized
paths — an older importer would install the literal token into configs). All
machines upgrade before the first sync at a new version.

### Machine entry (`machines/<machine-id>.json`)

| Field            | Type    | Notes                                             |
| ---------------- | ------- | ------------------------------------------------- |
| `machine_id`     | String  | The owning machine's ULID (= the filename).       |
| `display_name`   | String  | Hostname by default; user-editable.               |
| `platform`       | String  | e.g. `darwin` / `linux`.                          |
| `os_version`     | String  | Human-readable OS release.                        |
| `coffer_version` | String  | Producer version, for diagnostics.                |
| `last_sync_at`   | String  | ISO-8601 of the machine's last completed export.  |

Each machine writes **only its own** entry; rewrite happens only when the run's
commit is otherwise non-empty or the entry is >24 h old (heartbeat), so idle
machines don't generate registry-only commit chains.

### Resource serialization (`resources/<kind>/<name>.yaml`)

Deterministic projection of a `Resource`:

```yaml
kind: mcp_server
name: confluence
description: "..."
enabled: true
config: { ... }     # the validated, json-mode config; keys sorted
```

`created_at` / `updated_at` / local `id` are **excluded** (machine-local, would
churn diffs). String values under the exporting machine's home are normalized
to `${HOME}/...` (expanded on import), and keys covered by this machine's
merge patch are stripped back to the last shared values. On import the resource is upserted by `<kind>:<name>`. A local
resource is deleted **only** when its tombstone file is present — absence from
the workspace alone never deletes (a failed import elsewhere must not
masquerade as a deletion). When both a resource doc and a tombstone exist for
the same ref (merge artifact), the resource doc wins.

### Tombstone (`tombstones/resources/<kind>/<name>.json`)

| Field        | Type   | Notes                                            |
| ------------ | ------ | ------------------------------------------------ |
| `deleted_at` | String | ISO-8601 of the deletion.                        |
| `by`         | String | `machine_id` of the deleting machine.            |

Written at export from the `sync_tombstones` ledger; removed at export when the
resource exists live again (re-registration wins); pruned after 90 days.

### State areas (`state/<area>/...yaml`)

Module-owned shared state synced alongside the vault. Each module implements
`SyncedStatePort` (export/import of deterministic YAML docs) and the
composition root registers the providers — sync never imports kind modules.
Current areas:

- `channel-peers/<channel>/<chat>.yaml` — pairing identity (chat_id, sender_id,
  display name, preferred agent, paired_at; the machine-local
  `active_conversation_id` never travels). Import upserts; docs referencing a
  channel not present locally are skipped and retried next run.
- `mcp-preferences/<server>.yaml` — the DISABLED capabilities per server
  (enabled is the default; seen-timestamps stay machine-local). Import
  reconciles servers present locally to match; owned prefixes = local servers.
  Conflict semantics are doc-granular: if both machines disabled different
  capabilities on the same server before their first common sync, the merge
  conflicts and the resolved side wins wholesale — the losing machine's local
  disables are re-enabled by its next import. Embedding may stay degraded on a
  machine until its master key is bootstrapped (locked credential refs import
  fine; vector indexing simply stays inactive).
- `settings/embedding.yaml` + `settings/internal-engine.yaml` — the two
  engine singletons. A machine owns (and publishes) a singleton only once it
  has persisted it locally, so a fresh machine's defaults never same-path
  conflict with the fleet's values on its first merge.

Skill delivery bindings (`skill_agent_bindings`) stay machine-local by
decision: delivery is a side-effectful file operation with no row-level
reconcile loop — syncing the rows would misreport delivery state. Adopt skills
per machine via the existing skill surfaces.

### Credential blob (`credentials/<ref>.enc`)

The Fernet ciphertext for `ref`, base64-encoded as text so git stores a stable
line. No master key, no plaintext, no metadata beyond the ref (the path).

`ref` may be namespaced with slashes (e.g. `channel/seatalk/app-secret`,
`provider/agnes/key`), so the blob lives at the matching nested path
`credentials/channel/seatalk/app-secret.enc`. Export creates the parent dirs;
import walks recursively and rebuilds the full slash ref from the relative path.

## Local-only, never in the workspace

`~/.coffer/logs/`, `coffer.db`, `daemon.json`, PID/port files, and the master
key file/keychain entry.

## Derived indexes (excluded + regenerated)

Files that are *regenerated* from the source-of-truth files are excluded from
the mirror — they differ per machine, so syncing them would cause spurious
same-path conflicts. The memory store's `MEMORY.md` index is the current case:
the per-fact `<slug>.md` files sync, and `MEMORY.md` is rebuilt from the merged
facts on import. The set lives in `infrastructure/sync/workspace.DERIVED_INDEX_NAMES`.
