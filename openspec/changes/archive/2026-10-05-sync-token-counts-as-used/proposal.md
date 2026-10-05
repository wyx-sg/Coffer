## Why

The vault sync remote's push token is cited by this machine's sync settings,
not by a resource or a skill. The Secrets page therefore listed it as Not used
with nothing under Used by, and offered to delete it, which would break sync.

## What Changes

- The secrets listing names the sync remote as a user of its push token
  (kind `sync_remote`, name "Vault sync", slot `token`), so the secret is not
  `unreferenced`.
- Deleting a secret the sync remote cites is refused with `SECRET_IN_USE`,
  naming the sync remote.

## Impact

- Backend: secret routes. Frontend: Used by shows the sync remote and opens the Sync page.
- Specs: secret.
