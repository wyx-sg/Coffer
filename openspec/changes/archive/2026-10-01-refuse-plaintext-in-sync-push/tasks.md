## 1. Backend

- [x] 1.1 Expose the skill-file detection as `find_in_text` in the plaintext scanner
- [x] 1.2 List the blobs a push publishes (`new_blobs`) and read them before every push (a round, a fast-forward push, a join)
- [x] 1.3 Stop with `plaintext_found` when a file still holds a value; fold unpushed commits when only history does
- [x] 1.4 Record the findings (`plaintext`) and the fold (`folded`) on the round record
- [x] 1.5 The `plaintext_found` problem with its hand-off, and the `sync_plaintext_found` attention item
- [x] 1.6 "Push anyway": `POST /sync/plaintext/push-anyway`, audited as `sync_plaintext_pushed`, `SYNC_NO_PLAINTEXT_FOUND` when nothing was found
- [x] 1.7 `coffer sync push-anyway`, and `status`/`now` printing each place
- [x] 1.8 Regenerate the vault-sync contract, the frontend types and the i18n fixture

## 2. Web UI

- [x] 2.1 The `plaintext_found` page state, card, round label, toast and attention marker
- [x] 2.2 Push anyway behind a confirmation

## 3. Docs

- [x] 3.1 docs-site vault-sync guide and architecture page (en + zh)
- [x] 3.2 Error-code reference (en + zh) and the audit event list
