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

## Filesystem state (the sync workspace)

Default `~/.coffer/sync/` (overridable via `$COFFER_SYNC_ROOT` for tests), a git
working tree whose `origin` is the user's remote.

```
manifest.json
knowledge/                      mirror of ~/.coffer/knowledge
memory/                         mirror of ~/.coffer/memory
resources/<kind>/<name>.yaml    one deterministic file per config resource
credentials/<ref>.enc           Fernet ciphertext, base64 text; never the key
```

### `manifest.json`

| Field             | Type   | Notes                                            |
| ----------------- | ------ | ------------------------------------------------ |
| `schema_version`  | int    | Bumped on incompatible workspace layout changes. |
| `machine_id`      | String | Stable id of the machine that wrote the commit.  |
| `coffer_version`  | String | Producer version, for diagnostics.               |
| `kinds`           | list   | Config kinds included in this workspace.         |

`schema_version` is checked on import; a workspace newer than the running build
fails fast (`SYNC_WORKSPACE_TOO_NEW`), mirroring the DB `DB_SCHEMA_TOO_NEW` rule.

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
line. No master key, no plaintext, no metadata beyond the ref (the filename).

## Local-only, never in the workspace

`~/.coffer/logs/`, `coffer.db`, `daemon.json`, PID/port files, and the master
key file/keychain entry.
