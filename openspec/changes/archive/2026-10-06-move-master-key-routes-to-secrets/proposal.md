## Why

Settings › Security always shows this machine's master key fingerprint and offers
**Import a master key**, but the routes behind both sat under `/api/v1/sync`,
which the experimental `sync` feature closes while it is off — the default. With
sync off the visible controls were refused with `FEATURE_DISABLED`. The master
key is the secret store's: sync only reads its fingerprint for each machine's
descriptor. The command line copied the same split (`coffer sync key …`), and its
`sync key import` documented a body of only `material` and `passphrase` although
the route requires the desktop app's presence grant, which no command can get.
Separately, `coffer sync file-answer` documented `mine | theirs | merged text`
while the route accepts `mine | theirs | edited`.

## What Changes

- The master key's routes move from `/api/v1/sync/key/*` to
  `/api/v1/secrets/key/*` (`GET fingerprint`, `POST import/preview`,
  `POST import`), outside the `sync` gate. The import stays presence-gated
  exactly as before. The web UI and the desktop app call the new paths.
- The fingerprint, preview and import move from the sync service into a master
  key service of the secret store (`application/secret/master_key_import.py`),
  built over the same resolved key sync's machine descriptor reads, so an import
  is seen by both.
- `coffer sync key fingerprint | import-preview | import` become
  `coffer secret key-fingerprint`, `key-preview` and `key-install`.
  `key-install`'s help says the request needs the presence grant only the app
  signs and that a person imports with `coffer secret import-key`; nothing on the
  command line obtains a grant.
- `coffer sync file-answer`'s help takes its answers from the domain enum:
  `mine | theirs | edited`.
- The requirement "Import a master key after showing whose key it is" moves from
  vault-sync to secret, with two new scenarios; vault-sync and
  experimental-features name the new paths.

## Impact

- Specs: secret (ADDED, MODIFIED), vault-sync (REMOVED, MODIFIED),
  experimental-features (MODIFIED).
- Contracts: the three routes and their five schemas move from the vault-sync
  contract to the secret contract; the frontend's generated clients follow.
- Code: backend HTTP routes, wiring, CLI commands; `frontend/src/lib/api/security.ts`,
  `frontend/src/lib/tauri.ts`; `desktop/src/secrets_import.rs`.
- Docs: the secret-store guide, architecture vault-sync and principles (both
  locales), ADR secrets-cross-machines-only-as-ciphertext.
