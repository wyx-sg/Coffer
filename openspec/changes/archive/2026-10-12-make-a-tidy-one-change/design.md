## Context

The decision and its alternatives are argued in ADR
`tidying-knowledge-is-the-agents-job`; this file records only the shape of the
implementation.

## Decisions

**Pause, then settle once.** `VaultWriter.set_paused(provider)` takes a
callable that yields path prefixes; `pending()` and `settle()` skip paths under
them (`pending(include_paused=True)` still sees them, for the idle check).
`KnowledgeHistory.pause_tidies()` installs a provider reading the in-memory
`TIDY_RUNS` registry, so a paused prefix exists exactly while a run is open.
`settle_as(collection, meta)` commits the collection's pending paths with the
tidy's `CommitMeta` after the run is closed, so the ordinary settle path makes
the commit and its compare-and-swap rules apply unchanged.

**Start settles first.** `TidyService.start` runs the ordinary settle before
opening the run, so edits made before the tidy are `disk` commits and the tidy
holds only the agent's work.

**Idle expiry by fingerprint.** Each run keeps the sorted (path, digest) tuple
of the collection's pending paths; the sweep's `expire()` refreshes
`last_activity` whenever it changes and closes a run after `IDLE_S` (30
minutes) without one, with status `expired` and no report. Monotonic time is
used for idleness, wall time only for `started_at` on the wire.

**Memory only.** The registry is bookkeeping about a session in progress, not
knowledge; persisting it would be stored state about the corpus, synced or not.
A restart loses only the grouping: the next settle commits the edits as `disk`.

**Undo compares three versions.** For each file of the change (inbox paths
excluded) the undo reads the bytes at the change, the bytes on disk now and the
bytes at the change's parent. Now ≠ at-change means a later edit, refused with
the list unless `force`. The write is one `recording` transaction by the user,
`OP_RESTORE`, `undoes=<version>`; an absent parent version removes the file.
Undo is generic over any change that touched knowledge files, but the web UI
offers it only on a tidy's entry.

**Contents is a separate route.** The collection read stays cheap (counts and
findings); `GET .../files` reuses `catalogue.walk_files`, which already
returns kind, type and waiting.

**Disk-edit grouping is presentation.** Consecutive `disk` changes within 10
minutes are grouped by the web UI from the feed it already reads; nothing in the
history changes, and no undo is offered for a group.

## Risks / Trade-offs

- An agent that never runs `tidy-start` produces ordinary `disk` commits, as
  before; `tidy-finish` alone still groups whatever is uncommitted at that
  moment.
- A sync round that would touch a paused file waits up to the tidy's end (at
  most 30 idle minutes), as it would for a person's unsaved-to-git edit.
- `force` undo discards later edits; they stay in the history and can be
  restored from a file's History.
