## 1. Plan

- [x] 1.1 Proposal, design, spec deltas

## 2. Backend

- [x] 2.1 Restore `VaultHistoryService` (versions, diff against previous / current, restore with `expected_current`), `VaultHistoryPort` and `VaultRepository.diff`
- [x] 2.2 `GET /vault/history`, `GET /vault/diff`, `POST /vault/restore` (audited `vault_file_restored`), `VAULT_VERSION_NOT_FOUND` → 404
- [x] 2.3 Delete `POST /vault/history/handoff`, its schemas and `domain/vault/handoffs.py`
- [x] 2.4 Integration tests with acceptance markers; contracts regenerated

## 3. Frontend

- [x] 3.1 `lib/api/vault.ts`, query keys, `useVaultHistory` / `useVaultDiff` / `useRestoreVaultVersion`, `lib/vault/versionLabels.ts`, `lib/diff/unifiedDiff.ts`
- [x] 3.2 `components/history/`: `VersionHistorySplit` (restored), `VaultHistoryView`, `VaultVersionPanel`, `VaultRestoreDialog`
- [x] 3.3 Knowledge: Document / History tabs in the document's bar, `/knowledge/<uid>/history?file=`; History… leaves the ⋯ menu
- [x] 3.4 Skills: History tab (`/skills/<name>/history`, builtin empty state); History… leaves the ⋯ menu
- [x] 3.5 Delete `VaultHistoryDialog`; i18n en + zh; tests with acceptance markers; e2e knowledge walk

## 4. Docs

- [x] 4.1 docs-site guides and architecture pages (en + zh), error codes, data models, ADR note

## 5. Archive

- [x] 5.1 `npx openspec archive restore-in-app-vault-history --yes`
