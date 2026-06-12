# ADR-016 — Multi-Machine Sync over a User-Owned Git Repository

> 中文版: [ADR-016-multi-machine-sync.zh.md](./ADR-016-multi-machine-sync.zh.md)

- **Status:** Accepted
- **Spec:** [010-sync](../../specs/010-sync/spec.md)
- **Amends:** Constitution Principle I (0.3.0 — user-controlled sync medium exception)

## Context

Coffer is local-first: each machine owns its vault and no vendor cloud is a
system of record. Users who run Coffer on more than one machine had no way to
keep those vaults consistent — knowledge, memory, registered resources, and
credentials diverged. Multi-machine sync was an explicit non-goal precisely
because the obvious solution (a hosted sync service) would violate Principle I.

We want sync **without** giving up local-first guarantees.

## Decision

Sync vault state through **a git repository the user owns** (private GitHub repo,
self-hosted git, etc.). Git is the transport and the history/merge engine; every
machine keeps a full vault. This is authorised by the bounded Principle I
exception (0.3.0): no new system of record, ciphertext-only secrets, user opt-in
and ownership.

### Sync is a cross-cutting service, not a resource kind

Sync operates over the *whole* vault; it is not a user-managed entity like
`mcp_server` or `channel`. So it follows the retention/credentials cross-cutting
pattern — `application/sync/` + `infrastructure/sync/` + dedicated CLI/HTTP
surfaces + a daemon worker + a single-row `sync_config` table — rather than the
`Kind` framework. This avoids polluting the cross-kind import contracts with a
non-kind.

### Separate sync workspace + export/import

A dedicated git working tree (`~/.coffer/sync/`) is kept apart from the live
`~/.coffer/` runtime directory. A sync run **exports** local state into the
workspace, runs git, then **imports** the merged result back:

- **Knowledge / memory** are mirrored as files (they are already the on-disk
  truth) and the SQLite index is rebuilt by the existing reconcile-by-content-
  hash path.
- **Config resources** are serialized **deterministically** (sorted keys,
  normalized timestamps, local-only fields stripped) to one YAML file per
  resource, so git diffs and merges are meaningful, and reconciled back into
  SQLite via the kind-agnostic `ResourceService`.
- **Credentials** are exported as Fernet ciphertext blobs and imported into the
  `credentials` table.

SQLite stays the local system of record; the workspace is diffable text.

### Master key never enters the medium

The git repo only ever holds ciphertext. The Fernet master key is bootstrapped
onto each machine out-of-band (`coffer sync key export/import`). A machine that
has ciphertext but not the key reports `credentials_locked` and refuses to spawn
the affected resources — it never silently fails decryption.

This is also what makes the constitutional argument clean: even if the remote is
GitHub, the vendor only ever holds undecryptable ciphertext.

### Manual + opt-in auto

`coffer sync` is the explicit, predictable default. An opt-in daemon worker
(modeled on the retention worker) adds debounced push-on-change + interval pull
for users who want hands-off convergence. Off by default.

### Conflicts stop the run

One file per resource keeps conflicts small. On any `git merge` conflict the run
enters a `conflicted` state and imports nothing; the user resolves via
`coffer sync resolve` (ours/theirs/path). Neither side is ever silently
discarded; auto-sync pauses pushing while conflicted.

## Alternatives considered

- **Hosted Coffer sync service** — best UX, but a vendor-controlled system of
  record; rejected (would need a much broader amendment).
- **Peer-to-peer (Syncthing-style)** — most local-first, but requires device
  discovery/online overlap and gives no history/merge for free; rejected as the
  first cut.
- **User-owned object storage (S3/Dropbox)** — simple, but weak conflict
  handling and unfriendly to the per-resource diff/merge model; rejected.
- **Commit `coffer.db` directly** — SQLite is binary and unmergeable; rejected.
  Hence the text export/import layer.

## Consequences

- New `sync/` slice across all four layers, a `sync_config` table + migration,
  CLI/HTTP surfaces, a desktop panel, and a daemon worker.
- Outbound git is a network egress; it respects the loopback-only posture (git
  runs as a subprocess using the user's ambient git credentials, not Coffer's
  HTTP client).
- Determinism of the resource serializer is load-bearing for clean merges and is
  unit-tested.
- The credential bootstrap is a one-time manual step per machine — an accepted
  cost of never putting the key in the medium.
