# Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](history-is-one-sqlite-file-written-only-by-the-daemon.md), [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), spec vault-storage "Carry a format version on every vault document", spec vault-storage "Keep every vault document a JSON object that preserves what it does not know", spec vault-storage "Move an existing home into the vault layout once, on request, reversibly", spec vault-sync "Refuse a remote at another layout", spec daemon "Deploy frozen sibling binaries and back up the history database before migrating", spec vault-sync "Run an unattended rewriter on one owner machine", spec vault-sync "Hold a round that would lose too much", PR #452

## Context

The vault is files that several machines on several builds read and write, and
a version mechanism has to survive that. Three things are true at once: a
person edits the files, so a document can be at any version a build ever wrote;
two machines on two builds share one tree for as long as the user takes to
upgrade both; and a migration that runs once at startup, as the history
database's does, has no single owner here, because every machine would rewrite
the same synced files.

The history database already has the answer for its own shape: one Alembic
revision, run forward at startup, a revision it does not know refused, a copy
made first
([History Is One SQLite File](history-is-one-sqlite-file-written-only-by-the-daemon.md)).
That works because one machine owns one database and upgrades it in one step
before any row is read. It cannot govern files that travel.

The design this replaced had two other mechanisms. The sync tree carried one
bundle-wide `schema_version` in `manifest.json`, and a build that met a higher
number refused the **whole remote**, so a single machine upgraded ahead of the
others stopped every older machine's convergence until each was upgraded. And
documents parsed strictly: a document with a field the reader did not know was
refused, and the kind configs forbid extra keys, on the stated grounds that "a
typo'd key is a document that would import as something other than what it
says". The cost landed with `title` (PR #452, 2026-09-28): the resource
document gained a key, and a machine on any build before it refused every
titled document as `unexpected field(s): title`.
[Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md) said
"a sync peer on an older build ignores the key"; the parser those builds ran
did not.

The one-time move of a home out of the single database (`coffer.db`) into
files is also a one-way move of every user's data, and the rule is that every
data migration can be rolled back, with the old data kept untouched.

## Options Considered

### Option A — A version per file, unknown fields preserved, older files read-only, one owner machine commits the upgrade (chosen)

- **Per-file `format_version`.** Every vault document Coffer parses (resource
  files, state files, machine descriptors) carries an integer `format_version`
  for its own kind (a document without one is version 1). Each kind declares its
  current version and a chain of pure upgrade steps, `vN → vN+1`
  (`FormatSpec` and `UpgradeStep` in `domain/vault/formats.py`), each marked
  **additive** (only new optional fields: an older reader can still read the
  file) or **breaking**. A file carries `format_compat`, the oldest version
  that can still read it; a file that never names one is breaking by default,
  because a build must not guess that a future change was additive.
- **Unknown fields are preserved, at the document level.** A reader validates
  the fields it knows and keeps every other top-level field verbatim, and every
  write puts them back where they were. An unknown top-level key is reported on
  the resource as a warning ("field `enabeld` is not known to this build"),
  never refused: to an older build a newer build's field and a typo look the
  same, and refusing the first to catch the second is the `title` failure
  above. A resource's `config` is the kind's own, and every kind's config model
  refuses a key it does not declare (`extra="forbid"`); the vault's resource
  rule refuses such a file with a finding that names the key, whether a person
  wrote it or a sync merge brought it. The rule for unknown keys is therefore
  for documents, not configs: a new config field is a format step that older
  builds cannot read, and it is what the version and `format_compat` exist to
  carry.
- **An older file is read, not rewritten.** A build reads a file below its
  current version through the upgrade chain, in memory. It never writes that
  file back at a new version on an ordinary write, and an edit to such a file
  is refused with a finding, so a build cannot publish a version the rest of the
  fleet may not read.
- **A newer file is read-only.** A build that meets a `format_version` above
  its own reads a file whose `format_compat` it satisfies (keeping unknown
  fields) and shows it, but never writes, deletes or reconciles it; a file
  whose `format_compat` is above the build keeps the build's last valid version
  of that resource and is flagged "written by a newer Coffer". Convergence
  continues for every other file — no whole-remote refusal for a per-file
  version.
- **The layout commit.** The upgrade of files happens once, on one machine: the
  owner of unattended rewrites
  ([An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md) —
  the same field, so a fleet has one owner to keep alive, not two). When the
  owner runs a build whose current versions are higher than the vault's, it
  rewrites every lower file through the upgrade chain — and performs any
  directory move the new layout needs — in **one commit** with a
  `Coffer-Layout: <from> -> <to>` trailer. The upgrade functions are pure and
  deterministic, so the commit is reproducible from its parent.
- **The layout commit is exempt from the loss count because it passes a
  stricter check.** The deletion breaker counts losses; a layout commit may
  have none at all. The round verifies it mechanically: the set of resource
  uids per area is identical before and after, and every tree file that
  disappears reappears in the same area with the same blob. A layout commit
  that fails the check is held like any other round. This is not a bypass —
  [the breaker's ADR](sync-deletion-breaker.md) rejects one — but the same
  guard answered by a proof instead of a threshold.
- **Mixed-version fleets.**

  | Situation | Newer build | Older build |
  | --- | --- | --- |
  | Before the layout commit | reads everything; edits to not-yet-upgraded files refused | unchanged |
  | After an additive layout commit | normal | reads the files, keeps unknown fields, writes nothing it does not understand |
  | After a breaking layout commit | normal | keeps its last valid version of each upgraded resource, flagged; converges everything else |
  | Owner absent or on the older build | waits, and offers "take over upgrades here" (the owner field's existing repair) | — |

- **Rollback of a migration is a restore, never a downgrade.** The one-time
  move from `coffer.db` to files follows three rules:
  1. **Back up first.** The database is copied as `coffer.db.pre-vault` with
     its `-wal`/`-shm` companions, and the trees it moves are moved, not
     copied, so moving them back is a rename.
  2. **The old data is never rewritten.** The migrating build leaves
     `coffer.db.pre-vault` and `pre-vault/` as they were, and no code reads the
     old layout except the upgrade and its rollback.
  3. **`coffer migrate --rollback` is rehearsable.** It runs with the daemon stopped,
     restores `coffer.db.pre-vault` and the trees, and moves
     `vault/` and `local/` aside as `vault.rolled-back-<timestamp>` and
     `local.rolled-back-<timestamp>` rather than deleting them, so changes made
     after the migration survive in that repository's history for a person to
     re-apply; it leaves a hold marker that `coffer migrate --resume` lifts.
     `coffer migrate --rehearse` runs the migration against a copy in an
     isolated `HOME` and reports the difference. A remote at the old layout is
     never converted: a build at the new layout replaces it with its own vault
     (a fast-forward push whose parents are this machine's commit and the old
     tip, so the old history stays in git), and a build refuses a remote at a
     newer layout (`remote_too_new`). The upgraded vault is the source of
     truth; converting a remote would invent a second migration path.

Pros: an upgrade on one machine no longer stops convergence on the others; a
field added by one build survives a round trip through another; the rewrite
of synced files happens exactly once, in a commit anyone can inspect; the
breaker never has to be told to look away.

Cons: every kind maintains an upgrade chain and an additive/breaking flag;
until the owner upgrades, the machines already upgraded cannot edit
not-yet-upgraded files; preserving unknown fields means a typo at the top of a
document is a warning, not an error; keeping unknown keys in place needs a writer that preserves key order, which
the vault's JSON encoding does.

It wins because it is the only option under which machines on different builds
can share one vault for weeks without either stopping or overwriting what the
other wrote.

### Option B — One vault-wide layout version (the design this replaced)

Keep one `schema_version` for the whole tree; a newer number stops older
builds.

- **Pros.** One number to compare; a stop is unambiguous and safe.
- **Cons.** It stops everything for one change: a new optional field on one
  kind halts convergence of every file on every older machine. It says nothing
  about a single file a person edited back to an old shape. And a version bump
  still has to rewrite files somewhere, which it does not specify.
- **Why it loses.** Its granularity is the whole vault; the changes are per
  kind and mostly additive. It survives only as the **layout** number in
  `manifest.json` (`schema_version`, now 3), which a remote must match exactly
  and which gates a change of directory structure, not a field.

### Option C — Strict parsing, no preservation (the documents this replaced)

Refuse unknown fields; a new field means every reader must upgrade first.

- **Pros.** A typo is caught at the door; a document means exactly what the
  reader thinks.
- **Cons.** The `title` refusal: an older build turns every document a newer
  build touched into a failed path. In a vault of files that people edit,
  strictness also refuses a person's harmless extra key forever.
- **Why it loses.** It makes every additive change a fleet-wide flag day. It
  remains for a resource's `config`, whose keys are the kind's contract.

### Option D — Upgrade lazily: every build writes the files it touches at its own version

- **Pros.** No layout commit and no owner; files upgrade as they are used.
- **Cons.** The vault stays at mixed versions indefinitely; an older machine
  meets newer files one at a time, each one breaking where it lands; every
  ordinary edit doubles as a format change, so a round's diff mixes content and
  format, and the breaker sees rewrites it cannot tell from edits. Two machines
  on different builds editing one file each rewrite it in their own version.
- **Why it loses.** It spreads the upgrade across every write on every
  machine, which is the opposite of doing it once where it can be checked.

### Option E — Additive changes only, forever

Never rename, restructure or remove a field; only add optional ones.

- **Pros.** No versions, no upgrade chains; every reader tolerates every file.
- **Cons.** The history refutes it: moving names to uids, rewriting
  cross-references, re-keying tables and stripping a duplicate field were
  breaking changes each. A file format that can never shed a mistake carries
  every one forever, which is the load-time-shim problem the migrations rule
  exists to prevent.
- **Why it loses.** It forbids the changes the product has actually needed.

### Option F — Roll back by downgrade migrations

Write `downgrade()` steps and let an older build step the files back.

- **Pros.** Rollback would be the same machinery run backwards.
- **Cons.** [History Is One SQLite File](history-is-one-sqlite-file-written-only-by-the-daemon.md)
  rejected this for the database (its two-way migrations option): many data
  rewrites cannot be inverted honestly, and an older build does not ship a
  newer build's downgrade steps.
- **Why it loses.** For the same reasons; a restored copy is the honest
  rollback.

## Decision

Every vault file Coffer parses carries its own `format_version`. A reader
keeps top-level fields it does not know and writes them back; a file older than
the build is read through a pure in-memory upgrade chain and is not rewritten
by an ordinary write; a file newer than the build is read-only there, or kept at
the last valid version when the build cannot read it. Upgrading the vault's
files is one **layout commit** made by the owner machine of unattended rewrites,
verified to lose no uid and no tree file, and on that proof not counted by the
deletion breaker. Machines on different builds keep converging per file. A data
migration backs up first, leaves the old data untouched, and is undone by
`coffer migrate --rollback`, which restores the copy and moves the new vault
aside, never a downgrade.

## Consequences

- `manifest.json`'s `schema_version` is the vault's **layout** number, not a
  per-file gate. A remote at a newer layout is refused (`remote_too_new`); one at an older
  layout is replaced by this vault; a per-file version never stops a round.
- Kind configs keep `extra="forbid"`. Only a document's top-level fields are
  preserved; a key a kind's config does not declare is refused with a finding,
  and an additive config field is a format step that older builds flag as
  unreadable until they upgrade.
- `runs.db` keeps Alembic and its forward-only rules unchanged; this ADR
  governs vault files only.
- Every kind is at format version 1 today, so no upgrade step exists and no
  owner machine has anything to commit.
- Not built yet: the owner machine's layout commit and its no-loss check
  (`Coffer-Layout: <from> -> <to>` between versions, the uid-set and
  tree-file proof). They are built with the first kind that needs a second
  version. Until then an edit to an older file is refused with a finding that
  does not yet name an owner machine, and "take over upgrades here" does not
  exist.
- Not built yet: the upgrade-chain contract test per kind (every step
  deterministic, every additive step leaving an older reader able to parse the
  file), the property test that a layout commit on a random vault preserves the
  uid set, and the rehearsal gate in which two machines on different builds
  upgrade in both orders.
