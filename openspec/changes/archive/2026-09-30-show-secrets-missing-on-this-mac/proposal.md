## Why

The Secrets page is drawn with states the product could not show. A vault that
came from another Mac carries ciphertext this Mac's master key cannot open, or
cites secrets that were never stored here (encrypted secrets don't sync by
default); both looked like ordinary rows until something failed to start. The
list had no "Last used" or "Created", so a stale key could not be told from a
live one. A new standalone secret was written at once, although once stored any
`coffer run` hands it to a child — the user decided adding one is a change a
present person approves, labelled "New secret". And the plaintext-key move
failed as a whole when one file could not be rewritten, after it had already
stored that file's value.

## What Changes

- The secrets list (`GET /api/v1/secrets`, `coffer secret list --json`)
  carries `locked` — stored, but this Mac's key cannot open it, found by each
  token's signature without decrypting anything — plus `created_at` and
  `last_used_at`. The store stamps `last_used_at` when it decrypts a value for a
  consumer (at most once a minute); a reveal or an import's read-back does not
  count. Migration 0135 adds the nullable column.
- The Secrets page shows a row with no value here as **Missing on this Mac**
  with **Add value**, and a banner "N secrets have no value on this Mac" with
  **Import master key…** (Settings › Security). Adding the value is an ordinary
  write: a locked standalone or bound secret waits as `replace_value`.
- Writing a standalone `secret/<name>` that has no value here waits for approval
  as a new op, `add_secret` ("New secret"), holding the value sealed; approving
  stores it, rejecting drops it. With the protection off it is written at once.
- The approvals window asks one question per change ("Approve a new value for
  github-token?", "Approve the new secret npm-publish-token?") with Change,
  Secret, Requested by and Used by; in a browser Approve is disabled, naming the
  desktop app, and only Reject works. The page's banner reads "N changes waiting
  for approval" with what approving takes here, and a row whose new value waits
  reads "Waiting for approval".
- The plaintext scan reports how many files it read (`files_checked`); an import
  whose file cannot be rewritten skips that file's findings as `stored` (the value
  is in the store, the file still holds it), rewrites the rest, audits the stored
  values, and a second import of the same findings retries the file. The page
  says "Moved 2 of 3 keys" and offers Try again.
- Page copy follows the design: Last used and Created columns, "Copy reference
  (…)", the "?" explains `coffer run --secret`, the delete confirmation says the
  value is destroyed on other Macs too when encrypted secrets sync.

## Capabilities

### Modified Capabilities

- `secret`: new requirements "Show a secret this Mac cannot open as missing on
  this Mac", "Hold a new standalone secret until a person approves it" and "Show
  each change waiting for approval as the question it asks"; modified "Hold a
  replaced value in use until a person approves it", "List every stored and
  cited secret with what uses it" and "Move plaintext secret files into the
  store".

## Impact

- Backend: `EncryptedSecretStore` (`peek`, `last_used`, `unreadable_refs`),
  `SecretBoundary.write` / `approve`, the secrets list and scan/import
  routes and schemas, `plaintext_scan.move`; migration 0135.
- Frontend: `components/secret/*`, `pages/SecretsPage.tsx`, en/zh strings.
- Wire: `SecretRefOut`, `ApprovalOut.op`, `SecretScanOut`,
  `SecretImportSkippedOut` (regenerated contract and types).
- The CLI needs no change: `coffer secret set` already reports a 202 as
  waiting for approval and exits `9`, and `coffer secret list --json` passes
  the new fields through.
