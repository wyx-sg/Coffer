## Why

The Sync page's plaintext card and the `sync_plaintext_found` attention item
handed the places to an agent with a prompt to move each value into a Coffer
secret. Following it, an agent opens the file that holds the secret, and a
secret is never handed to an agent.

## What Changes

- Removes vault-sync "Refuse to push a plaintext secret" as it stands. An
  OpenSpec MODIFIED block cannot drop a scenario, and its scenario "the Sync
  page names each place and offers the hand-off and push anyway" names the
  hand-off. The change `move-sync-plaintext-into-secrets`, archived right
  after this one in the same PR, adds the requirement back under the same
  title with the card's new actions.

## Impact

- Spec: vault-sync, together with `move-sync-plaintext-into-secrets`.
