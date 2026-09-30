## 1. Hand-offs (backend)

- [x] 1.1 `domain/sync/handoffs.py`: which conflicts an agent may merge (never `secret/*.enc`), the merge prompt, the remote-failure prompts, URL and git-text scrubbing
- [x] 1.2 The stopped round's `handoff`, and each file's `secret` and `agent_merge`. The handed files' marked-up copies are written before the prompt names them. `FileVersionsOut.edited` carries the saved copy
- [x] 1.3 `POST /api/v1/sync/stop/merged` ("I merged it"), refused whole while a marker is left; `SYNC_SECRET_NOT_EDITABLE` for an editor copy or an edited answer on a secret
- [x] 1.4 `problem.handoff` for `push_failed`, `auth_failed` and `unreachable`; the problem `git_missing` with the shared install hand-off; `GIT_MISSING` names no installer and carries `details.handoff`
- [x] 1.5 Attention: `handoff` on `sync_conflicts` and `sync_auth_failed`, and a new `sync_push_failed` item
- [x] 1.6 CLI: `coffer sync status --prompt`, `coffer sync conflicts --prompt`, `coffer sync resolve --merged`, and the hints that name them; `--username` help names GitLab's `oauth2`
- [x] 1.7 Tests: integration (routes, CLI, attention) and unit (scrubbing, what may be handed over)

## 2. Settings › Data › Vault

- [x] 2.1 The Vault block shows size, versions, location and Open folder, as drawn; the storage summary drops `latest_time`, `latest_writer` and `sync_configured`

## 3. The Sync page (canvas 6.5.x)

- [x] 3.1 Header (status, Sync now / Try again, remote URL with copy, "?" on adding a Mac) and the Status / Machines / Remote tabs; set-up and joining in place of the tabs until joined
- [x] 3.2 Status: banner per state, the four area counts, what waits to push, the stopped-round card, the rounds table with the round drawer and rollback, the problem cards with their hand-offs
- [x] 3.3 Resolve conflicts (`/sync/conflicts`): two choices with their diff, Open in editor, Mark resolved, Merge with an agent and I merged it, Continue round; a secret file offers only the two choices
- [x] 3.4 Review held deletions (`/sync/deletions`) with the confirm dialog, and Restore
- [x] 3.5 Machines: This Mac and Runs curation tags, rename this Mac, retire another; the key-mismatch flag
- [x] 3.6 Remote: URL, branch, secret, user name, when rounds run (with Only when I press Sync now), encrypted secrets with a confirm, the vault's folder, Stop syncing
- [x] 3.7 The master key card leaves Sync (Settings › Security has import and export)

## 4. Docs and references

- [x] 4.1 `guides/vault-sync.md` (the page, merging with an agent, the failure hand-offs, a GitLab example with `--username oauth2`), `guides/troubleshooting.md`, `guides/web-ui.md`, `architecture/vault-sync.md`, `architecture/persistence.md`, `reference/error-codes.md`
- [x] 4.2 `guides/memory.md` and `guides/channels.md`: a channel turn's own hook stands aside for session start and each prompt, and triggers still guard it
- [x] 4.3 `make contracts`, `make docs-reference`, en and zh strings
