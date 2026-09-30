## Why

Coffer's configuration lives in one SQLite file beside its history, so every
fact that should travel between machines is translated into a file and back by
the sync round, and every rule about what must not travel (reach, derived
output, machine-local tables) lives inside that translation. Configuration
cannot be read or edited as a file, a person's edit has no history, and a
single-machine user has no way back to last week's version of a skill. The
ADRs storage-is-five-classes-by-nature, identity-is-the-uid-inside-the-file,
every-vault-file-carries-its-format-version,
every-vault-write-is-a-validated-commit-naming-its-writer and
sync-applies-clean-merges-and-stops-on-any-conflict decide the replacement.

## What Changes

- **Five storage classes.** `~/.coffer/` is split by what state *is*: `vault/`
  (the user's configuration and content, always a git repository), `local/`
  (machine-local: reach, agents, the sync remote, retention, the secret
  boundary's approvals), `content/` (media, the chat workspace), `runs.db`
  (history) and `derived/` (rebuildable: the memory tree, health, delivery
  bindings, caches). Only `vault/` is ever committed or pushed.
- **Resources are files.** Each resource is `vault/resources/<kind>/<name>.json`
  carrying its `uid` and `format_version`; agents are machine-local
  (`local/resources/agent/`), memory partitions and Coffer's own guide skill are
  derived. Identity is the uid inside the file; a duplicate uid is refused, a
  missing one is minted. MCP capability switches, channel pairings and engine
  settings are vault state documents. Credential ciphertext is
  `vault/credentials/<ref>.enc`. The integer resource id is gone; every history
  table references the uid.
- **Every write is a validated commit naming its writer.** One write path
  compares the expected content, writes atomically, validates, and commits one
  commit per operation with `Coffer-Writer` / `Coffer-Actor` / `Coffer-Machine`
  trailers. Hand edits are found by a debounced watcher and content scans; an
  invalid edit stays uncommitted and flagged while the last valid version stays
  in effect. Content APIs require an expected fingerprint. History, diff and
  restore work for any vault file on REST and the CLI; the Skills page gains a
  History tab and knowledge history reads the vault repository (its old
  repository is folded in).
- **Thin sync.** A round only fetches, merges with `git merge-tree` outside the
  working tree, and pushes. A clean merge is validated, guarded by the deletion
  breaker, snapshotted and checked out; any conflict stops the round and the
  person answers each file (keep this machine's, take the other's, or edit).
  A same-name resource with a different uid is a conflict. Joining previews what
  happens first. Rollback restores a pre-apply snapshot as a new commit. The
  translation layer, the automatic conflict arbiter and the agent resolver are
  removed.
- **One-time migration, rehearsable and reversible.** The first start of this
  build backs `coffer.db` up as `coffer.db.pre-vault`, writes the vault, moves
  the trees, folds the knowledge history in and renames the database to
  `runs.db`. `coffer migrate --rollback` restores the previous layout;
  `coffer migrate --rehearse` runs the migration on a copy.

## Capabilities

### New Capabilities
- `vault-storage`: the five classes, the vault repository, the file formats,
  identity by uid, per-file format versions, the one write path, hand edits,
  history/diff/restore, and the migration with its rollback and rehearsal.

### Modified Capabilities
- `vault-sync`: the round is pull, merge outside the tree, guard, check out,
  push; conflicts stop the round and are answered per file; joining is
  previewed; the translation, pointer and resolver requirements are removed.
- `resource-framework`: resources are files with their uid inside; reach is a
  machine-local record; the revision counter follows the file.
- `credentials`: ciphertext is stored as files in the vault; the boundary's
  bindings and approvals are machine-local files.
- `knowledge`: history is the vault repository; curation finds a person's
  edits from commits, not modification times; saves require an expected
  fingerprint.
- `skill-manager`: master folders are in the vault; a skill has a history with
  diff and restore; file saves require an expected fingerprint.
- `memory`: the memory tree is under `derived/`.
- `daemon`: the migration runs before any service starts and backs up first.

## Impact

- Backend: new `domain/vault/`, `application/vault/`, `infrastructure/vault/`
  (+ `migration/`); the resource, credential, boundary, preference, pairing,
  engine, retention and skill-source stores move onto files; `runs.db`
  Alembic revision 0136; `application/sync/`, `domain/sync/` and
  `infrastructure/sync/` rewritten around the vault repository; per-kind sync
  adapters deleted.
- Frontend: Sync page moved onto the new API; Skills History tab.
- Principles: the Persistence clause, the Credentials clause and the "Single
  SQLite writer" guarantee are amended to name `runs.db` and the vault files.
- Docs: `data-model.md` files describe files; docs-site persistence,
  vault-sync and filesystem reference rewritten; ADRs amended where this change
  chose differently (JSON documents, the revision counter).
