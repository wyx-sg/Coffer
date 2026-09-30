## 1. Store and list

- [x] 1.1 Migration 0135: nullable `secrets.last_used_at`.
- [x] 1.2 `EncryptedSecretStore`: stamp use in `get` (at most once a minute), `peek` for reads that are not uses (reveal, import read-back), `last_used`, `unreadable_refs` by token signature.
- [x] 1.3 `GET /api/v1/secrets`: `locked`, `created_at`, `last_used_at`.

## 2. Approvals

- [x] 2.1 `add_secret` op: a new standalone secret waits sealed; approve stores, reject drops; a newer value supersedes.
- [x] 2.2 `ApprovalOut.op` and the domain vocabulary carry `add_secret`; its description names the secret.

## 3. Plaintext scan

- [x] 3.1 `files_checked` on the scan.
- [x] 3.2 A file that cannot be rewritten skips its findings as `stored`; the rest are rewritten; stored values are audited; a second import retries.

## 4. Secrets page

- [x] 4.1 Last used and Created columns; Missing on this Mac with Add value; missing banner with Import master key….
- [x] 4.2 Approvals banner with what approving takes here; Waiting for approval on a row whose new value or adding waits.
- [x] 4.3 Approvals window: one question per change with Change, Secret, Requested by, Used by; Approve… in the app, disabled in a browser; toasts on approve and reject.
- [x] 4.4 Saved-and-waiting as a toast; ⋯ menu copy; `coffer run --secret` help; delete body and Last used; reveal Secret and Created.
- [x] 4.5 Scan: nothing found with the files read; "Moved N of M keys" with Try again.

## 5. Contract, docs, tests

- [x] 5.1 `make contracts`.
- [x] 5.2 docs-site Secrets guide.
- [x] 5.3 Backend unit and integration tests; frontend vitest; e2e `shell_secrets.spec.ts` follows the new add flow.
