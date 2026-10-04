## 1. Backend

- [x] 1.1 `shape_of` / `mask` for a value, and `mask_line` beside the plaintext scan
- [x] 1.2 `round_plaintext_context.context`: masked lines around the place, added/modified, on-remote, masked diff
- [x] 1.3 `GET /api/v1/sync/plaintext/context`, `PlaintextContextOut`, `SYNC_PLAINTEXT_NOT_LISTED`
- [x] 1.4 Unit tests for the shape and the masking; integration tests on the two-machine harness

## 2. Frontend

- [x] 2.1 Expandable places in the plaintext card with lazily fetched masked lines, shape and diff
- [x] 2.2 en and zh copy; component test

## 3. Specs and docs

- [x] 3.1 vault-sync delta
- [x] 3.2 Vault-sync guide (en and zh), regenerated contracts and the error-code reference

## 4. Verify

- [x] 4.1 `npx openspec validate --all --strict`, targeted tests and the lint gates
- [x] 4.2 Archive the change
