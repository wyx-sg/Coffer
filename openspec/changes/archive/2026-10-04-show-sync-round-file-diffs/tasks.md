## 1. Backend

- [x] 1.1 `round_diff.file_diff` over the round's recorded commits; secret, binary and size handling
- [x] 1.2 `GET /api/v1/sync/runs/{id}/diff`, `RoundFileDiffOut`, error codes and statuses
- [x] 1.3 Integration tests on the two-machine harness

## 2. Frontend

- [x] 2.1 Expandable file rows in the round drawer with a lazily fetched diff and `+N −M` counts
- [x] 2.2 en and zh copy for secret, binary, too large and unavailable; component test

## 3. Specs and docs

- [x] 3.1 vault-sync delta
- [x] 3.2 Vault-sync guide (en and zh) and the regenerated contracts and error-code reference

## 4. Verify

- [x] 4.1 `npx openspec validate --all --strict`, targeted tests and the lint gates
- [x] 4.2 Archive the change
