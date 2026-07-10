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
- **Import reconciliation** (amendment 2026-07-10) — reconciling registry ROWS
  is not enough: some resource config drives machine-local side-effects that
  each kind's own service performs on its front door (provider activation
  projects into the agent's native config file; an agent's
  `disable_native_memory` rewrites its settings; `follow_all_skills` drives
  skill delivery). After every import, each kind that declares a
  **post-import reconcile hook** re-applies those side-effects idempotently
  from the now-converged rows, so a change made on machine A takes real
  effect on machine B — the registry and the disk never disagree. Hook
  failures are recorded in the run's errors and retried on every subsequent
  import (the hooks reconcile current state, not deltas). Kinds also MAY
  declare an **import gate**: validation the importing machine runs before
  upserting a doc (an agent whose `config_dir` does not exist/write here —
  the agent is not installed on this machine) — a gate failure quarantines
  the doc exactly like any other import failure, so it retries every run and
  clears by itself once the agent is installed locally. The gate covers
  registrations AND updates: a gate-rejected update quarantines the newer
  doc while the existing local row keeps operating from its last good
  config; hooks skip rows whose machine-local preconditions no longer hold
  (a vanished config dir is reported, never recreated).
- **Sync run** — export → `git pull` (merge) → on clean merge: `git push` +
  import. The whole thing is one `coffer sync` invocation.
- **Conflict** — a `git merge` conflict. The engine resolves it AUTOMATICALLY
  with a deterministic policy (amendment 2026-07-10): per conflicted path,
  the side whose last vault-repo commit touching it is newer wins. Commit
  time is when a change was CAPTURED BY A SYNC RUN, not when the user made
  the edit — so this is precisely "the most recently synced edit wins"; with
  near-real-time auto-sync on every machine the two coincide, but a machine
  syncing after a long offline gap can carry an older edit to victory. The
  policy is machine-independent (every machine picks the same winner); a
  timestamp tie keeps the merging machine's side; `manifest.json` always
  resolves to the local side (it is byte-identical across same-version
  machines, and the schema gate runs before export). Only when the engine
  cannot settle a path does the run park in `conflicted` — the UI then points
  the user at their own repository (e.g. GitHub) instead of offering an
  in-app merge surface; `coffer sync resolve` remains as the CLI escape
  hatch. The losing side's content is never lost — it stays in the vault
  repo's history.
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

**Scope** (Amendment 2026-07-10 — machine × agent scope,
[ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md))
generalizes machine identity into a framework-owned, per-resource activation
matrix: an optional `scope` field lives on every resource (not inside kind
config), keyed by machine ULID (or `"*"` for every machine) with values of
`"*"` (every agent) or a list of agent names.

```
scope == None                                    # active on every machine, for every agent (default)
scope == {}                                      # active nowhere (dormant)
scope == {"<ulid>": ["claude-code"], "*": "*"}   # one machine: Claude Code only; every other machine: every agent
```

| Rule | Behavior |
| --- | --- |
| Entry lookup for machine M | exact-ULID key wins over the `"*"` key; no key present for M → inactive on M |
| `machine_in_scope(scope, m)` | an entry exists for `m` and its value is `"*"` or a non-empty list |
| `agent_in_scope(scope, m, agent)` | the entry's value is `"*"`, or `agent` is in the list; `agent=None` (an unidentified session) matches ONLY `"*"` values |
| `scope == None` | always active — every machine, every agent |
| Unknown machine ULIDs or agent names in an entry | legal, and simply never match (the other machine may not have synced yet; the agent may be registered later) |

Each kind declares which axes its resources use and enforces scope at its OWN
existing choke point — no new central gate:

| Kind | Axes | Enforcement seam |
| --- | --- | --- |
| `mcp_server` | machine × agent | the gateway (spec 001) |
| `skill` | machine × agent | delivery ∩ follow policy (spec 005) |
| `agent` | machine only | projection / reconcile / shim install (spec 004) |
| `channel` | machine only | the channel runtime (spec 009); supersedes `runs_on` |
| `knowledge_base`, `memory` | none | a non-null `scope` is rejected at validation |

A machine-only kind's scope entries accept only `"*"` as their value (an
agent-name list is rejected). A matrix that names an agent is additionally
intersected with that AGENT's own machine axis when computing an activation
slice for the Machines fleet view (below) — the gateway itself trusts the
local shim's self-reported identity and does not re-check the agent's machine
axis, since a local shim can only run where the agent is actually installed.

**Sync-but-inactive.** `scope` rides the resource doc through the existing
export → merge → import pipeline, auto-conflict resolution, tombstones, and
quarantine, completely unmodified: a scoped resource still syncs to and is
visible on every machine; out of scope it is simply not activated (not
spawned, not exposed, not delivered), and the registry stays the single
source of truth — scope is editable from any machine, exactly like editing
any other resource field. Adding `scope` to resource docs bumps the workspace
manifest `SCHEMA_VERSION` from 3 to 4, so a not-yet-upgraded build fails
closed with the existing `SYNC_WORKSPACE_TOO_NEW` gate (see "an older build
refuses a newer workspace" below) instead of silently dropping or misreading
the field.

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
  `push`, `pull`, `resolve`, `config`, `override list|set|unset`, `key export`,
  `key import`. `machines` (list; `--rename` for this machine) is promoted to
  a top-level `coffer machines` command (Amendment 2026-07-10 — machine ×
  agent scope, [ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md));
  `coffer sync machines` remains as a backward-compatible alias. A new
  top-level `coffer scope show|set|clear <kind>:<name>` reads/edits any
  resource's scope (see "Machines fleet view" below).
- **REST** — `/api/v1/sync/*`: get/put config, get status, trigger a run,
  resolve conflicts, list machines / rename this machine, manage per-machine
  overrides, export/import the master key. `scope` is validated per kind
  axes wherever a resource is created or updated (the framework-level
  resource CRUD payload); `GET /api/v1/machines` and
  `GET /api/v1/machines/{id}/slice` (Amendment 2026-07-10 — machine × agent
  scope, ADR-045) serve the fleet list and a machine's activation slice —
  see "Machines fleet view" below.
- **Desktop UI** — a Sync settings panel: configure remote (validated on
  save), toggle auto-sync, see status (clean / syncing / conflicted / error,
  last-sync time, actionable error hints), trigger a run, and a machines card
  listing every machine known to the vault (display name, platform, last
  sync, "this machine" badge, rename). There is NO in-app conflict-resolution
  surface (amendment 2026-07-10): conflicts auto-resolve; the rare parked
  conflict directs the user to their own repository. The master-key card
  shows the key's SHA-256 fingerprint (never the key) so the user can confirm
  two machines hold the same key after an export/import. The full fleet
  view — sync-status strip, one card per machine, and each machine's
  activation slice — moved to a new top-level Machines nav item (Amendment
  2026-07-10 — machine × agent scope, ADR-045); this panel's machines card
  stays as a lighter summary linking there (see "Machines fleet view" below).

## Machines fleet view (Amendment 2026-07-10 — machine × agent scope, [ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md))

A top-level `Machines` nav item (`/machines`) — separate from Settings →
Sync — lists every machine registered in the vault: a sync-status strip
(state, last-sync time, a manual run trigger, and a link back to Settings →
Sync) above one card per machine (display name, platform, last sync, "this
machine" badge). Selecting a machine opens its **activation slice** — agents
present, MCP servers active, skills delivered per agent, channels bound —
computed LOCALLY from the synced registry plus each resource's scope, so any
machine can render any OTHER machine's slice without contacting it. Every
machine's slice is intent only — registry plus scope math, no local
FS/process checks (what its scope says should be active there); a remote
machine's slice additionally carries an intent-only hint. Sync configuration
itself (remote, auto-sync, master key) is NOT part of this view — it stays in
Settings → Sync; this view is about activation, not transport.

- **REST**: `GET /api/v1/machines` (the fleet list) and
  `GET /api/v1/machines/{id}/slice` (that machine's activation slice).
- **CLI**: a top-level `coffer machines` (promoted out of the `coffer sync`
  group; `coffer sync machines` remains as a backward-compatible alias) and
  `coffer scope show|set|clear <kind>:<name>` to read or edit any resource's
  scope.

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

### Scenario: conflicting edits auto-resolve to the most recently synced edit

- **Given** machines A and B both edited the same resource/file since their last
  common sync, and A has already pushed
- **When** machine B runs `coffer sync`
- **Then** the run auto-resolves each conflicted path to the side whose vault
  commit is newer — the most recently synced edit (a tie keeps B's side) —
  completes without user action, and both machines converge on the same
  winner on their next runs
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

### Scenario: imported config re-applies its side-effects on this machine

- **Given** a kind with a post-import reconcile hook (e.g. provider
  activation, an agent's native-memory flag) whose resource changed on
  machine A
- **When** machine B's sync run imports the change
- **Then** B's hook re-applies the machine-local side-effect from the
  converged row (the projection/native-config write happens on B too), and a
  hook failure is reported in the run's errors and retried on the next import

### Scenario: an agent not installed on this machine quarantines at import

- **Given** machine A registers an agent whose `config_dir` does not exist on
  machine B
- **When** B's sync run imports the agent resource
- **Then** the import gate rejects it on B — the doc quarantines (visible in
  sync status), the agent row is NOT created pointing at a dead directory,
  and the import succeeds by itself on a later run once the directory exists

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

### Scenario: stale credential never wins a conflict

- **Given** machines A and B hold different ciphertext for the same credential
  ref, and B's blob embeds an older Fernet encryption time
- **When** B syncs last and the `.enc` path conflicts
- **Then** auto-resolve picks the fresher encryption regardless of which vault
  commit is newer, and every machine converges on it

### Scenario: interrupted run cannot re-export stale ciphertext

- **Given** a machine whose previous run pulled a fresher credential blob but
  crashed before importing it (workspace newer than DB)
- **When** its next run exports
- **Then** the fresher workspace blob is kept, and the run's import adopts it
  into the local vault

### Scenario: stale blob from an unguarded machine is not imported

- **Given** the remote holds an older encryption of a credential this machine
  already stores in a fresher form (e.g. pushed by an older build)
- **When** the machine pulls and imports it cleanly
- **Then** the local credential is kept and the next export heals the vault

### Scenario: deleting a resource releases its credential everywhere

- **Given** a resource whose credential ref no other resource cites
- **When** the resource is deleted on one machine and the deletion syncs
- **Then** the credential row is released on every machine, its blob leaves the
  medium, and a later re-created credential (fresher encryption) supersedes
  the tombstone instead of being deleted

### Scenario: a scoped resource stays dormant outside its scope

- **Given** an `mcp_server` resource whose `scope` names machine A only
  (`{"<A-id>": "*"}`), synced to both machine A and machine B
- **When** machine B reconciles after import
- **Then** the resource's doc is present on B (visible, synced) but B's
  gateway never spawns its upstream and never lists its tools, while machine
  A activates it normally
- **And** the Machines fleet view shows the resource as inactive on B

### Scenario: scope edits propagate like any resource edit

- **Given** a resource currently scoped to machine A only
- **When** the user edits its `scope` on machine A to include machine B, and
  both machines complete a sync round trip
- **Then** B activates the resource on its next reconcile — through the same
  export → merge → import → reconcile-hook pipeline as any other resource
  edit, with no new sync machinery
- **And** a stale build whose manifest schema version predates the `scope`
  field refuses the import with `SYNC_WORKSPACE_TOO_NEW` rather than
  silently dropping the field

### Scenario: the fleet view renders any machine's activation slice

- **Given** machines A and B have each completed a sync run against the same
  remote, and their resources carry a mix of scopes
- **When** the user opens the Machines fleet view on machine A and selects
  machine B's card
- **Then** the detail view renders B's activation slice (agents present, MCP
  servers active, skills delivered per agent, channels bound) computed
  locally from the synced registry plus scope, without machine A contacting B
- **And** because B is remote from A's viewpoint, the rendering carries an
  intent-only hint; viewed on B itself (its own, local slice) the hint does
  not appear

## Out of scope references

This spec covers the sync engine and its surfaces. Knowledge/memory file
formats are owned by specs 006/007; the credential store and master key are
owned by spec 006 / the credentials module; the resource model is owned by the
resource framework. This spec reuses them; it does not redefine them.
