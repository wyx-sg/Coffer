## Why

`hand-files-to-external-tools` replaced the History tabs of knowledge documents
and skills with a **History…** dialog that names the vault path, copies a
`git log` command and hands a restore to the person's agent. The dialog shows no
history at all: to see who changed a document and what they changed, a person
had to leave Coffer for a terminal or ask an agent. Every write to the vault is
already a commit naming its writer, so the history is Coffer's own record and
reading it is not a second editor or a second agent. The owner's decision
(2026-10-05): bring back a read-only history inside Coffer for knowledge
documents and skills, and let Coffer itself restore a version.

## What Changes

- **Vault history routes, read-only plus one restore**:
  `GET /api/v1/vault/history` (a file's or folder's versions, newest first,
  each with its writer from the commit's `Coffer-Writer` trailer, time and the
  files it touched with line counts), `GET /api/v1/vault/diff` (one version's
  diff file by file, `against=previous` for what the version changed or
  `against=current` for how the path differs now) and
  `POST /api/v1/vault/restore` (write a version back as a NEW commit naming the
  writer and `Coffer-Restored-From`, refused `VAULT_FILE_STALE` when the path
  changed since its history was read, audited as `vault_file_restored`). A
  read first commits an edit found on disk under the path, so the newest
  version is the file as it is. `secret/` and paths outside the vault are
  refused; an unknown version is `404 VAULT_VERSION_NOT_FOUND`.
- **A knowledge document gets a History tab** beside Document
  (`/knowledge/<uid>/history?file=<path>`), and **a skill gets a History tab**
  after Requires (`/skills/<name>/history`): the version list beside the chosen
  version's diff, **Changes in this version** / **Compare with current**, and
  **Restore this version…**, which asks first. Coffer's own skill is not in the
  vault and says it has no history.
- **The History… dialog and its hand-off go**: `POST /api/v1/vault/history/handoff`,
  its prompt (`domain/vault/handoffs.py`) and `VaultHistoryDialog`; the History…
  items leave the knowledge document's and the skill's ⋯ menus.
- Knowledge's delete **Undo** and its routes are unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `vault-storage`: the restore hand-off is replaced by reading and restoring
  versions of a vault file or folder.
- `knowledge`: a document's pane carries Document and History tabs; the
  history is read and restored through the vault's routes.
- `skill-manager`: a skill has a History tab; the ⋯ menu loses History….
- `web-ui`: the History… dialog is replaced by a History tab shared by
  documents and skills; the Skills page draws four tabs.
- `vault-sync`: a restore to a revision is made from a History tab (or with
  git), as a new commit.

## Impact

- Backend: `application/vault/history_service.py` (new, adapted from the one
  removed in #534), `application/vault/ports.py` (`VaultHistoryPort`),
  `infrastructure/vault/repository.py` (`diff`), `surfaces/http/vault_routes.py`,
  `vault_schemas.py`, `error_status_vault.py`; `domain/vault/handoffs.py` deleted.
- Frontend: `components/history/` (`VersionHistorySplit` restored,
  `VaultHistoryView`, `VaultVersionPanel`, `VaultRestoreDialog`),
  `components/skills/SkillHistoryTab`, knowledge pane tabs, `lib/api/vault.ts`,
  `lib/hooks/useVaultHistory.ts`, `lib/vault/versionLabels.ts`,
  `lib/diff/unifiedDiff.ts`, i18n (en + zh); `components/vault/VaultHistoryDialog`
  deleted.
- Contract: `vault-storage` regenerated.
- Docs: guides and architecture pages for knowledge, skills, vault files,
  persistence and observability (en + zh), the error-code reference, the
  data models, the vault-write ADR's note.
- Canvas (not editable from this session): Context (knowledge document
  History tab) and Capabilities (skill History tab), and the removal of the
  History… dialog.
