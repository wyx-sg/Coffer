## Why

Two things measured on a real install (backlog items O-4 and O-5):

- **`runs.db` only grows.** Retention deletes rows, but SQLite keeps the freed
  pages inside the file. One install's `runs.db` was 150 MB, of which 145 MB
  was free pages (4.6 MB of real history). Every schema upgrade then copied
  the whole file, free pages and all, as `runs.db.pre-<revision>`, so two
  copies added another 300 MB.
- **A half-typed channel setting took effect.** A channel's typed settings
  saved 600 ms after typing stopped. Changing the wait after a text message
  from 3 to 32 paused on "3" long enough to save it, then saved "32"; each
  save was live config the channel used at once, and a vault commit. One
  edit session left eleven commits.

## What Changes

- **The pre-migration copy is written with `VACUUM INTO`.** It is one
  self-contained file with a consistent snapshot of the live data (whatever the
  WAL still held included) and no free pages, so there are no `-wal`/`-shm`
  companions to copy, and it is as small as the history it holds.
- **The retention worker gives free pages back.** After each pass it rebuilds
  `runs.db` with `VACUUM` once free pages are at least half of the file and at
  least 8 MB, then truncates the WAL. A file that is mostly data is left alone.
- **A typed channel setting commits when the field is finished**: on blur or
  Enter, only when it parses, and only when it differs from what was last
  saved. Switches and lists still save as they change. Nothing about the vault
  writer changes: every save is still one commit (the person chose to keep
  that invariant; see the ADR).

## Capabilities

### Modified Capabilities

- `daemon`: the pre-migration backup is a compact `VACUUM INTO` copy without companions.
- `resource-framework`: retention gives the space pruning frees back to the disk.
- `channels`: a typed setting is committed when its field is finished.

## Impact

- `backend/coffer/infrastructure/persistence/migrations_runner.py`, new
  `infrastructure/persistence/space.py`, `application/retention_worker.py`,
  the background-worker wiring.
- `frontend/src/components/channel/useSettingDraft.ts` and its two callers.
- ADRs `audit-and-retention` and `every-vault-write-is-a-validated-commit-naming-its-writer`;
  `docs-site/architecture/persistence.md` and `docs-site/guides/channels.md` (en and zh).
