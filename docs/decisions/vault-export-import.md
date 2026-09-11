# Vault Export and Import

> 中文版: [vault-export-import.zh.md](./vault-export-import.zh.md)

- **Status:** Accepted
- **Spec:** [vault-export-import](../../specs/vault-export-import/spec.md)
- **Constitution:** Principle I (0.4.0 — export is ordinary local file output, no exception required; 0.5.0 — pushing exports to a user-owned backup remote is a bounded exception)

## Context

Coffer is local-first: each machine owns its vault and no vendor cloud is a
system of record. A user who moves to a new machine, or who works on two,
needs to carry the vault across — knowledge, memory, registered resources, and
credentials.

This ADR originally answered that with continuous sync over a user-owned git
repository. Keeping two live vaults convergent turned out to be a much harder
problem than moving one: it required machine identity, tombstones with a TTL so
a deletion could not be resurrected, timestamp arbitration for competing edits,
quarantine-and-retry for resources that fail to import, a separate git working
tree, and a background worker. That machinery was the majority of the sync
slice, and none of it is needed to answer the question users actually asked.

## Decision

Coffer **exports** the vault to a directory the user chooses and **imports**
one back. There is no transport medium, no remote, and no background
replication — moving the directory between machines is the user's business
(`scp`, a USB drive, their own git repo if they want one).

Because an export is ordinary local file output under the user's control, it
needs no exception to Principle I: it creates no second system of record, and
nothing reaches a vendor-controlled service.

### Export and import are a cross-cutting service, not a resource kind

They operate over the *whole* vault; they are not user-managed entities like
`mcp_server` or `channel`. So they follow the retention/credentials
cross-cutting pattern — `application/sync/` + `infrastructure/sync/` + CLI and
HTTP surfaces — rather than the `Kind` framework, which keeps the cross-kind
import contracts free of a non-kind.

### The export is a directory of text

- **Knowledge / memory** are mirrored as files (they are already the on-disk
  truth); the SQLite index is rebuilt on import by the existing
  reconcile-by-content-hash path.
- **Config resources** are serialized **deterministically** (sorted keys,
  normalized timestamps, local-only fields stripped) to one YAML file per
  resource, and reconciled back into SQLite via the kind-agnostic
  `ResourceService`.
- **Credentials** travel as Fernet ciphertext blobs, and only when the user
  asks for them explicitly.

SQLite stays the local system of record; the export is inspectable text, so a
user can read exactly what they are carrying before they carry it.

### Paths are normalized on the way out and expanded on the way in

An export written on one machine has to be importable on another whose home
directory differs. Absolute paths under `$HOME` are stored relative to a `~`
sentinel and expanded against the importing machine's home. This is the one
piece of portability machinery that survives from continuous sync, because it
addresses a real difference between machines rather than a race between them.

### The master key never enters the export

An export only ever holds ciphertext. The Fernet master key is bootstrapped
onto the other machine out-of-band (`coffer sync key export/import`). A machine
that has ciphertext but not the key reports `credentials_locked` and refuses to
spawn the affected resources — it never silently fails decryption.

Credentials are omitted from an export by default and included only with an
explicit flag, because an export directory is easy to leave somewhere careless.

### A backup remote is a destination for exports, not a second vault

Export and import move a vault between machines the user still has. They do
nothing for the two failures that actually destroy data: the disk dies, or
something is deleted and noticed a week later. Both need a copy beyond the
machine's own blast radius, and the second needs history.

So Coffer can hold **one backup remote**: a git repository the user owns.
A worker exports on a timer into a git working tree, commits when the export
differs from the last one, and pushes. Restore is an explicit command that
fetches, optionally checks out an earlier point in history, and runs the
ordinary import.

Three properties keep this from becoming the sync engine that was withdrawn:

- **One-way.** Coffer pushes; it never pulls to merge. Nothing arbitrates
  between two machines, because nothing is trying to converge them.
- **The remote is not a system of record.** The local vault is authoritative;
  the remote is a copy that is read only when a human asks for it.
- **The bundle format is unchanged.** A backup is an ordinary export that
  happens to live in a git tree, so the serializer, the path portability rules
  and the credential handling are the ones already specified here.

Commit happens before push and is not rolled back when the push fails: the
local git history is itself the first layer of recovery, and a failed push
retries on the next tick with nothing lost. A push that cannot authenticate or
reach the network is recorded and surfaced, never fatal to the worker.

Because an automatic backup mirrors deletions as faithfully as additions, the
copy at `HEAD` cannot answer "restore what I deleted last week" — only the
history can. That is why restore takes a revision or a date, and why the
timer-driven commit is what makes the feature work at all.

### Import is last-writer-wins, and never deletes

The importing vault takes the export's version of everything the export
contains, and keeps everything it holds that the export does not. There is no
arbitration, because there is no concurrent writer to arbitrate against — the
user chose which direction to move the data when they ran the command.

A resource absent from the export is never deleted: an export is a snapshot of
one machine, not an assertion about what should exist everywhere.

## Alternatives considered

- **Continuous sync over a user-owned git repository** — what this ADR
  previously decided. It delivered convergence, but its cost was tombstones,
  machine identity, conflict arbitration, quarantine-and-retry, a git workspace
  and a worker — a large, high-churn surface for a workflow that in practice
  runs a handful of times. Withdrawn.
- **Hosted Coffer sync service** — best UX, but a vendor-controlled system of
  record; rejected (would need a much broader constitutional amendment).
- **Peer-to-peer (Syncthing-style)** — most local-first, but requires device
  discovery and online overlap; rejected.
- **Copy `~/.coffer/` wholesale** — simplest, but carries machine-local state
  (daemon discovery file, absolute paths, per-machine logs) and a binary SQLite
  file that cannot be inspected or partially applied; rejected. Hence the
  deterministic text export.

## Consequences

- A `sync/` slice remains across the layers, holding serialization, path
  portability, the file-tree mirror, credential ciphertext handling, the two
  operations, and — for the backup remote — one `sync_remotes` config row, a
  `GitMirror` port with a single subprocess adapter behind it, and a timer
  worker shaped like `RetentionWorker`. Still no `sync_state`/tombstone/machine
  tables and no file watcher: those belonged to convergence, which is still
  not built.
- Export and import touch the local filesystem only. The backup worker is the
  one path that reaches the network, and only to a remote the user configured.
- Determinism of the resource serializer stays load-bearing — an export is
  meant to be diffable by the user — and stays unit-tested.
- Carrying credentials is a deliberate two-step act: the ciphertext flag on the
  export, plus the out-of-band key bootstrap.
- Two machines can drift apart, and Coffer will not notice or reconcile that.
  Keeping them aligned is a manual re-export, which is the trade this ADR
  accepts. A backup remote does not change this: two machines backing up to
  one repository overwrite each other's snapshots, and the older one is
  recoverable only from history.
- The backup remote needs a push credential, which becomes one more secret in
  the credential store — resolved at push time, never written into
  `.git/config` and never passed on a command line.
