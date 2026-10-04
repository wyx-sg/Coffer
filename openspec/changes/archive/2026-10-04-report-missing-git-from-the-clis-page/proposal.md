## Why

A missing `git` was reported on Overview only by sync, and only while the sync
feature is on and a remote is configured. Coffer needs `git` for the vault's
history all the time, so without sync nobody reported it.

## What Changes

- The CLIs attention source raises an item for a command Coffer itself runs
  (`git`) as it does for a command a skill requires. Its reason says what Coffer
  cannot do without it, and a missing one is an error.
- Sync raises no `sync_git_missing` item. The last round's problem is still held
  back while `git` is missing, and the Sync page keeps its own `git_missing`
  card (without an Ignore, since the Overview item lives under the CLIs page).
- Specs `skill-manager` ("List the commands Coffer itself runs") and
  `vault-sync` (the attention requirement) are edited in place, so
  `skip_specs` is set.

## Impact

- Backend: `application/skill/cli_attention.py`, `cli_handoff.py`,
  `application/sync/attention.py`.
- Frontend: `pages/sync/useSyncIgnore.ts`.
- Docs: guides/clis, guides/vault-sync (en + zh).
