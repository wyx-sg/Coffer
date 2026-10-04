## 1. Backend

- [x] 1.1 Remove `plaintext_handoff` and stop attaching it to the status problem and the attention item
- [x] 1.2 Integration test: no surface carries a hand-off for `plaintext_found`

## 2. Frontend

- [x] 2.1 `ScanSecretsDialog` takes `only` (vault-relative paths) and says when none of them can be moved from
- [x] 2.2 The plaintext card offers Move into secrets… and Push anyway…, no hand-off
- [x] 2.3 en and zh copy; component tests

## 3. Specs and docs

- [x] 3.1 vault-sync delta
- [x] 3.2 Vault-sync guide (en and zh)

## 4. Verify

- [x] 4.1 `npx openspec validate --all --strict`, targeted tests and the lint gates
- [x] 4.2 Archive the change
