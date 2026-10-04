## 1. Undo

- [x] 1.1 Keep what Stop syncing removes in `local/sync/removed-remote.json` and restore it with `POST /api/v1/sync/remote/restore`
- [x] 1.2 Register a retired machine again from the vault's history with `POST /api/v1/sync/machines/{id}/restore`

## 2. Agent merge

- [x] 2.1 Record a hand-off on the conflicting file (time, agent, conversation) and read `handed_off` / `merged_by_agent` off the marked-up copy
- [x] 2.2 `POST /api/v1/sync/stop/handoff` and the join's twin; goal-and-constraints prompt with no shell command
- [x] 2.3 `.../files/discard` and `.../join-choices/discard` back to two choices; merged text and diff on `files/versions`
- [x] 2.4 Remove `POST /api/v1/sync/stop/merged`, `resolve --merged` and the old prompt's git and CLI commands

## 3. Join files as conflicts

- [x] 3.1 Serve a join's differing files in the stopped round's file shape; editor copy, hand-off and `edited` answer for them

## 4. Attention

- [x] 4.1 Name each sync item by its situation; add `sync_git_missing` and `sync_unreachable`

## 5. Move the vault

- [x] 5.1 `POST /api/v1/sync/vault/move` with the target checks, the lock, the verified move and `SYNC_VAULT_*` errors; `vault_real_path` and `default_vault_path` on the status

## 6. Contract and client

- [x] 6.1 `make contracts`; the sync API client calls the new routes and drops the removed one
- [ ] 6.2 Sync pages and docs-site follow in the frontend change
