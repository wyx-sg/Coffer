## Why

The deletion breaker held a sync round that would lose many files and waited for the person to confirm. In two months of use it fired only on Coffer's own work (the memory sync, a Tidy the person started), and the answer was always "delete". It grew three exception rules (uid, content-id and rename pairing; deletions Coffer can explain; an answer remembered by file) to stay quiet. Every round already snapshots the vault before it checks anything out, can be rolled back, and the vault's history keeps every deleted file. The owner asked for the logic to be removed. The Overview's sync health tile also read "N rounds held" while it counted every sync attention item, which looked like several held batches.

## What Changes

- A deletion of any size syncs like any other change, in either direction. Nothing holds a round.
- **BREAKING** Removed: the breaker and its pairing rules, the `hold` stop kind, `GET /api/v1/sync/hold/diff`, `POST /api/v1/sync/hold/confirm`, `POST /api/v1/sync/hold/restore`, `coffer sync hold-diff`, `hold-confirm`, `hold-restore`, the **Review deletions** page (`/sync/deletions`), the `sync_deletions_held` attention item, the held banner and pill, and the desktop alert's `awaiting_confirmation` status. `held` fields are gone from the round, status and file-diff shapes.
- Round history rows an earlier build recorded as `held` still read; a hold an earlier build left in `local/sync/round.json` is dropped when it is read.
- The Overview sync item's button reads **Review sync**, and the sync health tile counts items that need attention.
- The main spec `openspec/specs/vault-sync/spec.md` and `data-model.md` were edited directly (requirements and scenarios renamed and removed), so this change carries no delta.

## Capabilities

### Modified Capabilities

- `vault-sync`: a mass deletion syncs like any other change; no hold.
- `web-ui`: the Overview sync button reads Review sync.

## Impact

Backend sync domain, application, HTTP routes and CLI; frontend Sync and Overview; desktop sync alert; contracts; docs-site (en and zh); ADR `docs/decisions/sync-applies-mass-deletions-like-any-change.md` (rewrites the breaker's ADR).
