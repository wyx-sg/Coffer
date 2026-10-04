## Why

A round's drawer lists the files it applied here and the files it pushed, but
not what changed in them. To learn whether a pulled edit is the one expected, a
person has to leave the page and read the vault's history file by file.

## What Changes

- `GET /api/v1/sync/runs/{id}/diff?path=&side=applied|pushed` returns one file
  of a round as a unified diff, computed on demand from the vault's git history
  between two commits the round already records (nothing new is stored):
  `applied` is `from_commit` to `to_commit`; `pushed` is the remote tip the push
  went on top of (the newest pulled commit, or `from_commit` for a round that
  only pushed) to `to_commit`.
- The path must be one the round lists for that side
  (`SYNC_ROUND_FILE_NOT_LISTED`, 404). A secret returns `kind: "secret"` and no
  content, a binary file `binary`, a large one `too_large`; a round whose commits
  are gone is `SYNC_ROUND_DIFF_UNAVAILABLE` (409).
- The round drawer's Applied and Pushed files expand in place to the diff, with
  a `+N −M` count once loaded. Pulled commits show no diff.

## Impact

- Spec: vault-sync gains "Show what a round changed in each file".
- Backend: `application/sync/round_diff.py`, a route, two error codes, one schema.
- Frontend: the round drawer's change boxes; en and zh copy.
- Docs: the vault-sync guide (en and zh) and the error-code reference.
