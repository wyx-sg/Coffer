## Why

A value a person says is not a secret keeps coming back. On the Secrets page,
unticking a finding lasts one scan. In vault sync, **Push anyway** allows the
exact file versions it found, so any later edit to the same file — even to
another line — makes a new version, the whole file is read again, and the same
value stops the next push. With gitleaks' `generic-api-key` now flagging
high-entropy values under key-named fields, that happens in notes people edit
every day.

## What Changes

- Coffer remembers, on this machine, values a person says are not secrets — by
  an HMAC fingerprint under a key derived from the master key, never the value
  or a plain hash — and stops reporting them in Find plaintext keys and in the
  push check, wherever they sit and whatever else in their file changes. A
  changed value is reported again.
- **Find plaintext keys**: each finding gets **Not a secret**; remembered
  findings come back marked `ignored`, hidden behind **Show ignored (N)** with
  **Report again**. New routes `POST /api/v1/secrets/scan/ignore` and
  `/unignore`, CLI `coffer secret ignore` / `unignore`, audit events
  `secret_plaintext_ignored` / `secret_plaintext_unignored`.
- **Push anyway** also remembers each value the round found, so an edit
  elsewhere in the file no longer stops the next push; its confirmation says so.

## Capabilities

### New Capabilities

### Modified Capabilities

- `secret`: adds "Remember a value a person says is not a secret".
- `vault-sync`: modifies "Refuse to push a plaintext secret" — remembered values
  do not stop a round, and Push anyway remembers what it found.

## Impact

- Backend: a fingerprint key context in `domain/secrets.py`; a machine-local
  store `local/secret/plaintext-ignored.json`; the secret scan service and
  routes; the push check and Push anyway; audit event types; CLI commands.
- Contracts: `ignored` on scan findings; two routes.
- Frontend: Find plaintext keys dialog, Sync page's Push anyway confirmation;
  en/zh copy.
- Docs: secrets and vault-sync guides (en + zh), generated CLI/REST reference.
