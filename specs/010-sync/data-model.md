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
| `interval_seconds` | int     | Auto pull/push interval. Default `300`.            |
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

## Filesystem state (the sync workspace)

Default `~/.coffer/sync/` (overridable via `$COFFER_SYNC_ROOT` for tests), a git
working tree whose `origin` is the user's remote.

```
manifest.json
machines/<machine-id>.json      per-machine registry entry (owner-written only)
knowledge/                      mirror of ~/.coffer/knowledge
memory/                         mirror of ~/.coffer/memory
skills/                         mirror of ~/.coffer/skills
resources/<kind>/<name>.yaml    one deterministic file per config resource
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
churn diffs). On import the resource is upserted by `<kind>:<name>`; resources
absent from the workspace but present locally are deleted (full reconcile).

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
