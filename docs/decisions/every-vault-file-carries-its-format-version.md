# Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Control-Plane State Is One SQLite File, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](sqlite-alembic-persistence.md), [An Unattended Rewriter of Synced Content Runs on One Named Owner Machine](single-owner-machine-for-unattended-rewrites.md), [A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves](sync-deletion-breaker.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), spec daemon "Deploy frozen sibling binaries and back up the history database before migrating", spec vault-sync "Run an unattended rewriter on one owner machine", spec vault-sync "Hold a round that would lose too much", PR #452

## Context

Coffer has two version mechanisms today, and neither survives the vault
becoming files that several machines on several builds read and write.

- **The database** carries one Alembic revision (106 revisions, head `0106`).
  The daemon runs it forward at startup, refuses a revision it does not know
  (`DatabaseSchemaTooNew`), and copies the file aside first as
  `coffer.db.pre-<revision>`, keeping three (`surfaces/http/migrations_runner.py:32`).
  This works because one machine owns one database and upgrades it in one
  step before any row is read.
- **The sync tree** carries one bundle-wide `schema_version` in
  `manifest.json` (`domain/sync/manifest.py:64`, currently `2`). A build that
  meets a higher number refuses the **whole remote**
  (`manifest.py:125`, `SyncBundleTooNew`). So a single machine upgraded
  ahead of the others stops every older machine's convergence until each is
  upgraded — the bump to layout 2 was designed as exactly that stop.

And documents parse strictly. `parse_resource_doc` refuses any field it does
not know (`domain/sync/serialization.py:155`) and the kind configs forbid
extra keys (`extra="forbid"` in `domain/skill/config.py`,
`domain/provider/config.py`, `domain/agent/config.py`,
`domain/knowledge/config.py`), on the stated grounds that "a typo'd key is a
document that would import as something other than what it says". The cost
landed with `title` (PR #452, 2026-09-28): the resource document gained a key,
and a machine on any build before it refuses every titled document as
`unexpected field(s): title`. [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)
says "a sync peer on an older build ignores the key"; the parser those builds
run does not.

Once the vault is files, three things change at once: a person edits the
files, so a document can be at any version a build ever wrote; two machines on
two builds share one tree for as long as the user takes to upgrade both; and
the database's "migrate everything once at startup" no longer has one owner,
because every machine would rewrite the same synced files.

The v0.4 migration itself — `coffer.db` into files — is also a one-way move of
every user's data, and the plan's rule is that every data migration can be
rolled back, with the old data kept read-only for one version.

## Options Considered

### Option A — A version per file, unknown fields preserved, older files read-only, one owner machine commits the upgrade (chosen)

- **Per-file `format_version`.** Every vault file that Coffer parses (resource
  files, state files) carries an integer `format_version` for its own kind.
  Each kind declares its current version and a chain of pure upgrade functions
  in `domain/`, `vN → vN+1`, and whether each step is **additive** (only new
  optional fields: an older reader can still read the file) or **breaking**.
- **Unknown fields are preserved.** A reader validates the fields it knows
  strictly and keeps the rest verbatim, and every write puts them back where
  they were. An unknown key is reported on the resource as a warning ("field
  `enabeld` is not known to this build"), never refused: to an older build a
  newer build's field and a typo look the same, and refusing the first to catch
  the second is the `title` failure above. This covers a document's top-level
  fields. A resource's `config` is its kind's own, and every kind's config
  model refuses a key it does not declare; the vault's resource rule refuses
  such a file the same way (amended 2026-09-30, when 1.0 dropped the tolerance
  of retired config keys).
- **An older file is read, not rewritten.** A build reads a file below its
  current version through the upgrade chain, in memory. It never writes that
  file back at a new version on an ordinary write, and an edit to such a file
  is refused with the reason ("this vault is waiting for its layout upgrade on
  `<owner machine>`"), so a build cannot publish a version the rest of the
  fleet may not read.
- **A newer file is read-only.** A build that meets a `format_version` above
  its own reads an additive step's file (keeping unknown fields) and shows it,
  but never writes, deletes or reconciles it; a breaking step's file keeps the
  build's last valid version of that resource and is flagged "written by a
  newer Coffer". Convergence continues for every other file — no whole-remote
  refusal.
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
  [the breaker's ADR](sync-deletion-breaker.md) rejects one (its Option H) —
  but the same guard answered by a proof instead of a threshold.
- **Mixed-version fleets.**

  | Situation | Newer build | Older build |
  | --- | --- | --- |
  | Before the layout commit | reads everything; edits to not-yet-upgraded files refused, with the owner named | unchanged |
  | After an additive layout commit | normal | reads the files, keeps unknown fields, writes nothing it does not understand |
  | After a breaking layout commit | normal | keeps its last valid version of each upgraded resource, flagged; converges everything else |
  | Owner absent or on the older build | waits, and offers "take over upgrades here" (the owner field's existing repair) | — |

- **Rollback of a migration is a restore, never a downgrade.** The one-time
  move from `coffer.db` to files — and any later data migration — follows
  three rules:
  1. **Back up first.** The database is copied as `coffer.db.pre-vault` with
     its `-wal`/`-shm` companions, and the trees it moves are moved, not
     copied, so moving them back is a rename.
  2. **The old data stays read-only for one version.** The migrating build
     never opens `coffer.db.pre-vault` for writing; the next version offers to
     remove it.
  3. **`coffer migrate --rollback` is rehearsable.** It stops the daemon,
     restores `coffer.db.pre-vault` and the trees, and moves `vault/` aside to
     `vault.rolled-back-<timestamp>` rather than deleting it, so changes made
     after the migration survive in that repository's history for a person to
     re-apply. `coffer migrate --rehearse` runs the migration against a copy
     in an isolated `HOME` and reports the difference. A machine that already
     pushed the new layout leaves the remote at it; an older build then refuses
     that remote as today (`SyncBundleTooNew`), which is the safe answer.

Pros: an upgrade on one machine no longer stops convergence on the others; a
field added by one build survives a round trip through another; the rewrite
of synced files happens exactly once, in a commit anyone can inspect; the
breaker never has to be told to look away.

Cons: every kind maintains an upgrade chain and an additive/breaking flag;
until the owner upgrades, the machines already upgraded cannot edit
not-yet-upgraded files; preserving unknown fields means a typo is a warning,
not an error; a YAML round-trip that keeps unknown keys in place needs a
comment- and order-preserving writer.

It wins because it is the only option under which machines on different builds
can share one vault for weeks without either stopping or overwriting what the
other wrote.

### Option B — One vault-wide layout version (today's manifest)

Keep one `schema_version` for the whole tree; a newer number stops older
builds.

- **Pros.** One number to compare; a stop is unambiguous and safe.
- **Cons.** It stops everything for one change: a new optional field on one
  kind halts convergence of every file on every older machine. It says nothing
  about a single file a person edited back to an old shape. And a version bump
  still has to rewrite files somewhere, which it does not specify.
- **Why it loses.** Its granularity is the whole vault; the changes are per
  kind and mostly additive.

### Option C — Strict parsing, no preservation (today's documents)

Refuse unknown fields; a new field means every reader must upgrade first.

- **Pros.** A typo is caught at the door; a document means exactly what the
  reader thinks.
- **Cons.** The `title` refusal: an older build turns every document a newer
  build touched into a failed path. In a vault of files that people edit,
  strictness also refuses a person's harmless extra key forever.
- **Why it loses.** It makes every additive change a fleet-wide flag day.

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
- **Cons.** The history refutes it: 0095–0100 alone moved names to uids,
  rewrote cross-references, re-keyed tables and stripped a duplicate field —
  breaking changes each. A file format that can never shed a mistake carries
  every one forever, which is the load-time-shim problem the migrations rule
  exists to prevent.
- **Why it loses.** It forbids the changes the product has actually needed.

### Option F — Roll back by downgrade migrations

Write `downgrade()` steps and let an older build step the files back.

- **Pros.** Rollback would be the same machinery run backwards.
- **Cons.** [Control-Plane State Is One SQLite File](sqlite-alembic-persistence.md)
  rejected this for the database (its Option G): many data rewrites cannot be
  inverted honestly, and an older build does not ship a newer build's
  downgrade steps.
- **Why it loses.** For the same reasons; a restored copy is the honest
  rollback.

## Decision

Every vault file Coffer parses carries its own `format_version`. A reader
keeps fields it does not know and writes them back; a file older than the
build is read through a pure in-memory upgrade chain and is not rewritten by
an ordinary write; a file newer than the build is read-only there. Upgrading
the vault's files is one **layout commit** made by the owner machine of
unattended rewrites, verified to lose no uid and no tree file, and on that
proof not counted by the deletion breaker. Machines on different builds keep
converging per file. A data migration backs up first, keeps the old data
read-only for one version, and is undone by `coffer migrate --rollback`,
which restores the copy and moves the new vault aside, never a downgrade.

## Consequences

- The bundle-wide `manifest.json` version stops being the gate for builds
  that know per-file versions; a newer file is a per-file read-only state
  instead. The vault still carries one `manifest.json` at `schema_version: 3`,
  for one reason: builds from before this change read only that number, and it
  is what makes them refuse the new layout rather than misread it.
- Kind configs stop using `extra="forbid"` for vault files; they validate
  known fields strictly and carry the rest. The document-level refusal of
  unexpected fields goes with `parse_resource_doc`.
- `runs.db` keeps Alembic and its forward-only rules unchanged; this ADR
  governs vault files only.
- **Obligations.** An upgrade-chain contract per kind with a test that every
  step is deterministic and every additive step leaves an older reader able to
  parse the file; a property test that a layout commit on a random vault
  preserves the uid set; the V4 rehearsal gate — an isolated `HOME`, a copy of a
  real vault, and two machines on different builds upgrading in both orders —
  and a rollback test that restores the pre-migration state byte for byte.

## Implementation notes (2026-09-30)

Where the adopting change departs from the text above, and why:

- **Per-file versions are in place, the layout commit is not yet.** Every
  document carries `format_version` (and may carry `format_compat`), and the
  validator reads each by the rules above: current, older (read, edits
  refused), newer and readable (kept read-only), newer and unreadable (the last
  valid version kept, the file flagged). Every kind is at version 1, so no
  upgrade step exists and no owner machine has anything to commit; the layout
  commit and its no-loss check are built with the first kind that needs a
  second version.
- **The remote's layout must match exactly.** `manifest.json`'s
  `schema_version` (3) is the layout number. A remote at a newer layout is
  refused (`remote too new`); a remote at an older one is refused too
  (`remote too old`) and is rebuilt from a machine that has been upgraded — it
  is not converted in place, because other machines may still be pushing the
  old layout into it, and Coffer keeps no reader for an old layout.
- **The one-time move out of `coffer.db`** is `coffer migrate`, run by the
  person, with `--rehearse` on a copy and `--rollback` byte for byte, rather
  than an Alembic step at daemon start. The history database that remains,
  `runs.db`, still migrates forward through the one Alembic lineage.
