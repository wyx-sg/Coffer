## Why

The finished Sync design changes four behaviours the backend has to carry.
Retiring a machine and stopping sync no longer ask first; each is undone from
the toast instead, so each has to be restorable. The merge an agent writes is
shown for the person to check rather than recorded blind with "I merged it".
The files a first join finds different are the same question as a stopped
round's conflicts and open in the same Resolve view. And the problems the Sync
page shows can be ignored from the page or from the Overview with one key, so
every one needs an attention item named by its situation.

## What Changes

- vault-sync: new requirement "Undo a retired machine".
  `POST /api/v1/sync/machines/{id}/restore` registers the machine again with
  the descriptor it had before it was retired, read from the vault's history.
- vault-sync: new requirement "Undo stop syncing". `DELETE /api/v1/sync/remote`
  keeps what it forgot (the remote's settings, joined, a waiting round, a join's
  differing files) on this machine and answers `restorable`;
  `POST /api/v1/sync/remote/restore` puts it back.
- vault-sync: "Hand a conflict's merge to an agent" is replaced by "Hand
  conflicting files to an agent". The hand-off is recorded by
  `POST /api/v1/sync/stop/handoff` (one file, or every file an agent may merge)
  and covers a join's differing files through
  `POST /api/v1/sync/join-choices/handoff`; the prompt states the goal and the
  constraints with no shell command. A file reads `handed_off`, then
  `merged_by_agent` once the agent has written its merge into the copy, with the
  merge and its diff from this machine's version; it stays unresolved until it
  is marked resolved (the `edited` answer). `.../files/discard` and
  `.../join-choices/discard` go back to two choices. `POST /stop/merged` and
  `coffer sync resolve --merged` are removed.
- vault-sync: a join's differing files are served in the stopped round's file
  shape and can be answered `edited`, which commits the merge as this machine's
  version.
- vault-sync: the attention list's sync items are named by their situation
  (commits and files in conflict, a hold's files, a join's files, the plaintext
  found, the failing remote) so ignoring one hides that situation only, and
  `git` missing and an unreachable remote get items of their own.
- vault-sync: new requirement "Move the vault out of a synchronised folder".
  `POST /api/v1/sync/vault/move` moves the vault out of a synchronised folder
  and leaves `~/.coffer/vault` leading to it; the status carries
  `vault_real_path` and `default_vault_path`.
- vault-sync: the Sync page's requirement drops the "?" and the confirmations
  of Stop syncing and Retire.

## Impact

- Backend: `application/sync` (round_answers, round_merge, service_merge,
  service_remote, service_machines, attention), `domain/sync` (stops, handoffs,
  errors), `infrastructure/sync/local_state`, the sync HTTP routes and schemas,
  `coffer sync conflicts|resolve|edit|choose`.
- Contract: `openspec/specs/vault-sync/contracts/api.openapi.yaml` and the
  frontend's generated types.
- Frontend: the API client `lib/api/sync.ts`; the Sync pages follow in their own
  change.
