# ADR-043 — Sync v2: Machine Identity and Near-Real-Time Convergence

> 中文版: [ADR-043-sync-machine-identity-near-real-time.zh.md](./ADR-043-sync-machine-identity-near-real-time.zh.md)

- **Status:** Accepted
- **Spec:** [010-sync](../../specs/010-sync/spec.md) (amended; slices also amend
  [007-memory](../../specs/007-memory/spec.md) and [009-channels](../../specs/009-channels/spec.md))
- **Amends:** [ADR-016](./ADR-016-multi-machine-sync.md) (keeps the git medium
  and the export→merge→import engine; replaces the interval-only auto-sync and
  the delete-by-absence import rule)

## Context

ADR-016 shipped whole-vault sync over a user-owned git repo, aimed at machines
that take turns. The actual usage is **two machines in parallel**, with
**different usernames / directory layouts**, wanting convergence in tens of
seconds. Auditing the shipped engine against that revealed:

1. Auto-sync is interval-only (default 300 s); the "debounced push-on-change"
   ADR-016 promised was never built.
2. Channel resources sync with `enabled: true` and the runtime starts every
   enabled channel — two machines fight over one Telegram bot, and pairing
   state (`channel_peers`) stays behind.
3. Import deletes by absence, so a resource that *fails* to import on one
   machine (e.g. a machine-local path) is later *deleted* everywhere.
4. Absolute paths in configs — and memory's project IDs, which are hashes of
   the absolute git-root path — break across machines with different homes.
5. Shared intent (MCP tool preferences, engine configs, skill-delivery intent,
   channel pairing) never syncs.
6. There is no model concept of "a machine" to hang any of this on
   (`machine_id` was just `platform.node()` in commit messages).

## Decision

Keep the git transport and engine skeleton; add a **thin machine-identity
layer** and fix the findings. The pieces (delivered as independent slices):

- **Machine identity.** A stable per-installation ULID + editable display
  name (DB singleton, never synced as data). The workspace gains a
  `machines/<id>.json` registry area where each machine writes only its own
  entry — visibility without conflicts.
- **Runtime affinity.** Channel configs carry `runs_on: <machine_id>`; only
  the bound machine starts the adapter; pairing identity syncs so rebinding
  needs no re-pairing. `null` (post-upgrade default) runs nowhere until the
  user picks a machine.
- **Path portability.** `${HOME}` normalization on export/import for config
  string values, plus per-machine JSON-Merge-Patch overrides under
  `machines/<id>/overrides/` for genuinely divergent values. Memory project
  IDs derive from the normalized `origin` remote URL (path-hash fallback +
  one-time alias migration), so the same repo maps to the same memory store on
  every machine.
- **Tombstoned deletion.** Deletes travel as explicit
  `tombstones/resources/<kind>/<name>.json` files; absence alone never
  deletes. Failed imports are quarantined and preserved, not dropped.
- **Near-real-time engine.** In-daemon change notifications + a `watchfiles`
  watcher over the three file trees (agents can write memory through symlinks,
  bypassing the daemon) feed a debounced push; a lightweight
  `git ls-remote` head probe (default every 15 s) triggers pulls. The interval
  sweep remains as a fallback. Expected convergence ≈ 15–30 s.

Machine identity carries exactly three responsibilities — affinity, overrides,
visibility — plus provenance labels on tombstones. It is **not** a per-record
versioning scheme.

## Alternatives considered

- **Per-record version vectors / operation log** — the textbook fix for
  finding 3; rejected as a distributed-systems tax on a single-user tool. Git
  3-way merge over per-ULID files already handles the file-tree domains well.
- **Hub / leader machine** — one always-on machine runs everything and relays
  state; rejected: breaks symmetry (laptop closes → channels die) and doesn't
  address paths.
- **Migration-only (backup/restore)** — considered when re-scoping; rejected
  because the machines are used in parallel, and overwrite semantics would
  discard the other machine's changes.
- **Real push transport (relay / P2P)** — sub-second convergence but re-opens
  ADR-016's medium decision; tens-of-seconds is achievable inside the existing
  constitutional posture, so not now.

## Consequences

- Sync workspace layout grows `machines/`, `tombstones/`, `state/` areas; the
  manifest schema version bumps (to 2) with the tombstone slice, so all
  machines must upgrade Coffer before the first v2 sync.
- New backend dependency `watchfiles`; `git ls-remote` polling becomes a
  steady, small network egress while auto-sync is on.
- The channel runtime consults machine identity — the first kind-level
  behavior keyed to a machine.
- A rebind can briefly double-run a channel during propagation; accepted for a
  single-user tool.
- Chat history, audit logs, and runtime state remain machine-local by design.
