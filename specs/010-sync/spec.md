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
  manifest.json              # workspace schema version (byte-identical everywhere)
  machines/<machine-id>.json # per-machine registry entry (each machine writes only its own)
  knowledge/                 # mirror of ~/.coffer/knowledge
  memory/                    # mirror of ~/.coffer/memory
  skills/                    # mirror of ~/.coffer/skills (master skill store)
  resources/<kind>/<name>.yaml   # one deterministic file per config resource
  tombstones/resources/<kind>/<name>.json  # explicit deletion record (90-day TTL)
  state/<area>/...yaml       # module-owned shared state (e.g. channel-peers)
  credentials/<ref>.enc          # Fernet ciphertext blob (never the master key)
  ```

- **Export** — write local vault state into the workspace (files mirrored,
  resources serialized, ciphertext dumped).
- **Import** — apply workspace state back into the local vault (files mirrored
  back + reindex, resources reconciled into SQLite, ciphertext imported).
- **Sync run** — export → `git pull` (merge) → on clean merge: `git push` +
  import. The whole thing is one `coffer sync` invocation.
- **Conflict** — a `git merge` conflict. The engine resolves it AUTOMATICALLY
  with a deterministic newest-wins policy (amendment 2026-07-10): per
  conflicted path, the side whose last commit touching it is newer wins —
  machine-independent, so every machine picks the same winner; a timestamp tie
  keeps the merging machine's side; `manifest.json` always resolves to the
  local side (the schema gate has already run). Only when the engine cannot
  settle a path does the run park in `conflicted` — the UI then points the
  user at their own repository (e.g. GitHub) instead of offering an in-app
  merge surface; `coffer sync resolve` remains as the CLI escape hatch. The
  losing side's content is never lost — it stays in the vault repo's history.
- **Tombstone** — the explicit record of a config-resource deletion
  (`tombstones/resources/<kind>/<name>.json`, carrying when and by which
  machine). Import deletes a local resource **only** when its tombstone is
  present — a resource merely absent from the workspace is never deleted.
  Re-registering a resource clears its tombstone on the machine's next export.
  Tombstones expire after 90 days.
- **Quarantine** — a resource whose import failed on this machine (e.g. a
  machine-local path in its config). Its workspace doc is preserved verbatim —
  never re-exported from the failed local state and never dropped — the import
  retries every run, and the affected refs are reported in sync status. A row
  that cannot be imported on one machine MUST NOT cause its deletion anywhere.
  While quarantined, the remote intent outweighs local state: local edits to
  the same resource are not exported, and a tombstone does not remove the
  preserved doc until the quarantine resolves.
- **Auto-sync** — an opt-in daemon worker giving near-real-time convergence.
  Push side: resource mutations and file-tree changes (a `watchfiles` watcher
  over the knowledge/memory/skills trees — agents can write memory through
  symlinks, bypassing the daemon) trigger a debounced run (quiet period 5 s,
  cap 30 s after the first change). Pull side: a lightweight
  `git ls-remote` head probe every `poll_remote_seconds` triggers a run only
  when the remote actually moved. A fixed-interval sweep remains as the
  fallback (it also catches changes made while a run was in flight — triggers
  are suppressed during a run so the import's own writes cannot re-fire it).
  Off by default. Expected convergence with both machines on: ~15–30 s.

## Machine identity

Each installation mints a stable **machine id** (a ULID) the first time the
daemon starts, persisted machine-locally (a DB singleton — it is state *about*
this machine, never synced as vault data). A human-friendly **display name**
defaults to the hostname and is editable.

The workspace `machines/` area holds one JSON entry per machine: display name,
platform, OS version, Coffer version, and last-sync time. **Each machine writes
only its own entry**, so the area is conflict-free by construction. Entry-churn
control: a machine rewrites its entry only when the run's commit is otherwise
non-empty, or when the entry is older than 24 h (a heartbeat) — an idle machine
MUST NOT generate an endless chain of registry-only commits.

Machine identity exists so the user can see every machine attached to a vault
(this section), and to anchor the follow-up amendments (per-resource runtime
affinity, per-machine config overrides, tombstone provenance — see
[ADR-043](../../docs/decisions/ADR-043-sync-machine-identity-near-real-time.md)).
It is **not** a per-record versioning scheme.

## Path portability

The user's machines have different usernames/home layouts, so absolute paths
inside configs would break when synced verbatim. Two mechanisms, applied in
order at import (shared doc → `${HOME}` expansion → machine override):

- **`${HOME}` normalization** (zero-config): export rewrites every config
  string value under the exporting machine's home to `${HOME}/...`; import
  expands the token to the importing machine's home. The medium never holds a
  literal home path. A value already containing the literal token is exported
  as-is — and, like every token, expands to the local home at import on every
  machine (the token is effectively active everywhere).
- **Per-machine overrides**: an RFC 7386 JSON Merge Patch per resource under
  `machines/<machine-id>/overrides/<kind>/<name>.yaml` (each machine writes
  only its own dir — conflict-free), for values that genuinely differ per
  machine (e.g. an Intel-vs-ARM homebrew path). The patch applies at every
  import and is **stripped at every export** (overridden keys revert to the
  last shared values), so a machine's specialization never leaks into the
  medium; unsetting an override immediately restores the shared values
  locally. Surfaces: `coffer sync override list|set|unset` and
  `/api/v1/sync/overrides`.

## Configuration

A single persisted sync config row:

- `remote` — git remote URL (required to enable).
- `enabled` — master on/off for sync.
- `auto` — whether the daemon auto-sync worker runs.
- `interval_seconds` — fallback sweep interval for auto-sync (default 300).
- `poll_remote_seconds` — how often auto-sync probes the remote head with
  `git ls-remote` (default 15, min 5). One cheap network round trip; a full
  run happens only when the head moved.
- `branch` — git branch to sync on (default `main`). This is an internal ref
  name in Coffer's own sync vault repo, not the user's project branch; both
  machines use the same default, so it is **not exposed in the settings UI**.
  It remains in the config/API and is adjustable via the CLI (`coffer sync
  --branch`) for the rare case of sharing one remote across branches.

Credentials for the git remote (SSH key / token) are the user's own git
configuration; Coffer invokes git and relies on the ambient git credential
setup, exactly as a developer's normal `git push` does. Coffer stores no git
credential and offers no credential-management UI; instead (amendment
2026-07-10): saving a NEW remote (or enabling sync) probes it with one
headless `git ls-remote` and rejects the save with `SYNC_REMOTE_UNREACHABLE`
carrying a hint (`auth` / `not_found` / `network`), and the status endpoint
classifies `last_error` the same way (`error_hint`) so surfaces render
configuration guidance (use an SSH URL / run `gh auth setup-git`) instead of
raw git stderr. The daemon runs headless: an HTTPS remote works only when a
credential helper answers without a terminal.

## Surfaces

- **CLI** — `coffer sync` command group: `init`, `status`, `run` (the default),
  `push`, `pull`, `resolve`, `config`, `machines` (list; `--rename` for this
  machine), `override list|set|unset`, `key export`, `key import`.
- **REST** — `/api/v1/sync/*`: get/put config, get status, trigger a run,
  resolve conflicts, list machines / rename this machine, manage per-machine
  overrides, export/import the master key.
- **Desktop UI** — a Sync settings panel: configure remote (validated on
  save), toggle auto-sync, see status (clean / syncing / conflicted / error,
  last-sync time, actionable error hints), trigger a run, and a machines card
  listing every machine known to the vault (display name, platform, last
  sync, "this machine" badge, rename). There is NO in-app conflict-resolution
  surface (amendment 2026-07-10): conflicts auto-resolve; the rare parked
  conflict directs the user to their own repository. The master-key card
  shows the key's SHA-256 fingerprint (never the key) so the user can confirm
  two machines hold the same key after an export/import.

## Credential bootstrap

The master key never travels in the sync medium. On a new machine the user
brings it over out-of-band exactly once:

- `coffer sync key export <path>` writes the current machine's master key to a
  file the user moves over a channel they trust.
- `coffer sync key import <path>` installs it on the new machine (into the file
  store or keychain per the machine's setting).

In the desktop UI the master-key card MUST let the user pick the file through a
native dialog rather than typing a path — a native save dialog for export and a
native open dialog for import (the OS dialog in the packaged app; on the web via
the daemon picker, spec 004 FR-042 / ADR-036). A typed path field appears only as
a fallback when the host has no native dialog tool.

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

### Scenario: conflicting edits auto-resolve to the newer edit

- **Given** machines A and B both edited the same resource/file since their last
  common sync, and A has already pushed
- **When** machine B runs `coffer sync`
- **Then** the run auto-resolves each conflicted path to the side whose last
  commit is newer (a tie keeps B's side), completes without user action, and
  both machines converge on the same winner on their next runs
- **And** if the engine cannot settle a path, the run parks in `conflicted`
  and the surfaces direct the user to resolve in their own repository
  (`coffer sync resolve` stays available as the CLI escape hatch)

### Scenario: a first sync against a populated remote merges, never deletes

- **Given** a machine whose vault is empty (or partially filled) and a remote
  already carrying another machine's resources, trees, and credentials
- **When** the machine's first sync runs (its export necessarily happens
  before it has ever imported)
- **Then** the export MUST NOT delete anything from the workspace it has not
  ingested: resource docs without a local row are withheld from deletion
  unless tombstoned, and tree/credential deletions do not propagate until a
  run has completed an import on this machine

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

### Scenario: deletions propagate as tombstones

- **Given** machines A and B share a synced `mcp_server` resource
- **When** A deletes the resource and both machines complete a sync round trip
- **Then** the resource is gone on B, and the workspace holds its tombstone
  instead of the resource doc
- **And** if B later re-registers the same resource, it reappears on both
  machines and the tombstone is cleared

### Scenario: a failed import never deletes the resource elsewhere

- **Given** machine A syncs a resource whose config cannot be imported on
  machine B (a machine-local path)
- **When** B runs a sync (the import fails for that resource) and both machines
  complete another round trip
- **Then** the resource still exists on A and in the workspace, B reports the
  ref as quarantined in sync status, and B retries the import on every run

### Scenario: an older build refuses a newer workspace

- **Given** the sync workspace manifest carries a schema version newer than the
  running build supports
- **When** a sync run reaches its import step
- **Then** the run fails with `SYNC_WORKSPACE_TOO_NEW` and imports nothing

### Scenario: channel pairing state syncs with the vault

- **Given** machine A has a channel with a paired owner
- **When** machine B syncs against the same remote
- **Then** B holds the channel AND its pairing identity (chat id, sender id,
  preferred agent) — rebinding the channel to B needs no re-pairing
- **And** each machine's local conversation pointer never travels

### Scenario: config paths follow each machine's home

- **Given** machine A (home `/Users/alice`) syncs a resource whose config
  points inside its home
- **When** machine B (home `/home/bob`) imports it
- **Then** the path lands under B's home, and the sync medium holds
  `${HOME}/...`, never a literal home path

### Scenario: a per-machine override survives sync round trips

- **Given** a synced resource and a per-machine override on machine B
- **When** the machines complete sync round trips, including a shared edit to
  a non-overridden field
- **Then** B keeps its overridden values, A and the medium never see them,
  the shared edit still reaches B
- **And** unsetting the override restores the shared values on B's next run

### Scenario: shared preferences and engine settings sync

- **Given** machine A disabled an MCP tool and picked an internal-engine model
- **When** machine B syncs against the same remote
- **Then** the tool is disabled and the model matches on B — and re-enabling
  the tool on B propagates back to A
- **And** a fresh machine's defaults never overwrite the fleet's settings (it
  publishes a singleton only after persisting it locally)

### Scenario: machines are visible after they sync

- **Given** machines A and B have each completed a sync run against the same
  remote
- **When** the user lists machines on A (settings panel or `coffer sync
  machines`)
- **Then** both machines appear with display name, platform, and last-sync
  time, and A is marked as this machine
- **And** renaming A propagates to B's machine list after the next round trip

## Out of scope references

This spec covers the sync engine and its surfaces. Knowledge/memory file
formats are owned by specs 006/007; the credential store and master key are
owned by spec 006 / the credentials module; the resource model is owned by the
resource framework. This spec reuses them; it does not redefine them.
