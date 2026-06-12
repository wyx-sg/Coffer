# Spec 010 — Multi-Machine Sync

> 中文版: [spec.zh.md](./spec.zh.md)

Keep one Coffer vault consistent across several of the user's own machines,
using a git repository the user owns as the sync medium. Enabled by the
constitution 0.3.0 amendment to Principle I (user-controlled sync medium
exception). Background and alternatives in
[ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md).

## Why

A developer uses Coffer on more than one computer (laptop, desktop). Today each
machine is an island: knowledge, memory, registered resources, and credentials
diverge. This feature lets the user push local vault state to a git remote they
control and pull it on another machine, so every machine converges on the same
vault — without any vendor-controlled cloud and without the master key ever
leaving a machine.

## What syncs

- **Knowledge base + memory** — the markdown files under `~/.coffer/knowledge/`
  and `~/.coffer/memory/` (files are already the source of truth).
- **Config resources** — `mcp_server`, `agent`, `skill`, `channel` definitions
  (system of record is SQLite; serialized to text for transport).
- **Credentials** — Fernet **ciphertext only**.

## What does not sync (machine-local)

Logs, `coffer.db` (a rebuildable index), `daemon.json`, PID files, port
allocations, and any runtime artifact. The master key is **never** written to
the sync medium.

## Concepts

- **Sync remote** — a git URL the user owns (e.g. a private GitHub repo or a
  self-hosted git server). Coffer ships no hosted endpoint.
- **Sync workspace** — a git working tree Coffer maintains (default
  `~/.coffer/sync/`), kept separate from the live runtime directory. Its layout:

  ```
  manifest.json              # schema version + machine id + last-sync metadata
  knowledge/                 # mirror of ~/.coffer/knowledge
  memory/                    # mirror of ~/.coffer/memory
  resources/<kind>/<name>.yaml   # one deterministic file per config resource
  credentials/<ref>.enc          # Fernet ciphertext blob (never the master key)
  ```

- **Export** — write local vault state into the workspace (files mirrored,
  resources serialized, ciphertext dumped).
- **Import** — apply workspace state back into the local vault (files mirrored
  back + reindex, resources reconciled into SQLite, ciphertext imported).
- **Sync run** — export → `git pull` (merge) → on clean merge: `git push` +
  import. The whole thing is one `coffer sync` invocation.
- **Conflict** — a `git merge` conflict. The run stops in a `conflicted` state;
  nothing is imported until the user resolves it. Neither side is discarded.
- **Auto-sync** — an opt-in daemon worker that runs sync runs on file/resource
  change (debounced) and on a fixed interval. Off by default.

## Configuration

A single persisted sync config row:

- `remote` — git remote URL (required to enable).
- `enabled` — master on/off for sync.
- `auto` — whether the daemon auto-sync worker runs.
- `interval_seconds` — auto pull/push interval (default 300).
- `branch` — git branch to sync on (default `main`).

Credentials for the git remote (SSH key / token) are the user's own git
configuration; Coffer invokes git and relies on the ambient git credential
setup, exactly as a developer's normal `git push` does.

## Surfaces

- **CLI** — `coffer sync` command group: `init`, `status`, `run` (the default),
  `push`, `pull`, `resolve`, `config`, `key export`, `key import`.
- **REST** — `/api/v1/sync/*`: get/put config, get status, trigger a run,
  resolve conflicts, export/import the master key.
- **Desktop UI** — a Sync settings panel: configure remote, toggle auto-sync,
  see status (clean / syncing / conflicted / error, last-sync time), trigger a
  run, and resolve conflicts.

## Credential bootstrap

The master key never travels in the sync medium. On a new machine the user
brings it over out-of-band exactly once:

- `coffer sync key export <path>` writes the current machine's master key to a
  file the user moves over a channel they trust.
- `coffer sync key import <path>` installs it on the new machine (into the file
  store or keychain per the machine's setting).

Until the key is present on a machine, imported ciphertext stays **locked**:
resources that reference it cannot spawn, and status reports
`credentials_locked` with the affected refs.

## Acceptance Scenarios

### Scenario: initialise sync against a user remote

- **Given** a machine with a vault and no sync configured
- **When** the user runs `coffer sync init <git-remote>`
- **Then** Coffer creates the sync workspace, records the remote in sync config,
  performs a first sync run, and reports status `clean`

### Scenario: round-trip vault state to a second machine

- **Given** machine A has synced knowledge, memory, a registered `mcp_server`,
  and a credential
- **When** machine B runs `coffer sync` against the same remote (with the master
  key already bootstrapped)
- **Then** machine B's vault contains the same knowledge/memory files, the same
  `mcp_server` resource, and can decrypt the credential

### Scenario: locked credentials before key bootstrap

- **Given** machine B has pulled ciphertext but has not imported the master key
- **When** machine B runs `coffer sync status`
- **Then** status reports `credentials_locked` listing the affected refs
- **And** after `coffer sync key import <path>` the next status no longer lists
  them

### Scenario: master key never enters the medium

- **Given** any sync run has completed
- **When** the sync workspace contents are inspected
- **Then** no file contains the master key; `credentials/` holds only Fernet
  ciphertext

### Scenario: conflicting edits stop the run for resolution

- **Given** machines A and B both edited the same resource/file since their last
  common sync, and A has already pushed
- **When** machine B runs `coffer sync`
- **Then** the run stops in `conflicted` state, imports nothing, and lists the
  conflicting paths
- **And** `coffer sync resolve` (taking ours/theirs/path) clears the conflict and
  a subsequent run completes

### Scenario: only shared state syncs

- **Given** a vault with logs, `coffer.db`, and `daemon.json`
- **When** a sync run completes
- **Then** the sync workspace contains knowledge, memory, resource, and
  credential files only — no logs, database file, or daemon runtime files

### Scenario: auto-sync converges after a change

- **Given** auto-sync is enabled on machines A and B
- **When** A registers a new resource
- **Then** A pushes the change within the debounce window and B imports it on its
  next interval pull, with no manual command on either machine

## Out of scope references

This spec covers the sync engine and its surfaces. Knowledge/memory file
formats are owned by specs 006/007; the credential store and master key are
owned by spec 006 / the credentials module; the resource model is owned by the
resource framework. This spec reuses them; it does not redefine them.
