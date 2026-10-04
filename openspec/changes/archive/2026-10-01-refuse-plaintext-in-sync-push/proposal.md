## Why

Vault sync pushes the vault to a git remote the person owns. The only
plaintext-secret scan today is gitleaks in Coffer's own CI, which never sees a
user's vault. A key pasted into a knowledge document, a resource file or a
skill script is therefore pushed on the next round, and once it is on the
remote it is in the remote's history, in every clone and in every backup of
either, out of Coffer's reach for good.

## What Changes

- vault-sync: before a round pushes, it reads every file version the push
  would publish (each blob the remote does not hold yet, from every commit
  since the remote's head) with the detection `coffer secret scan` already
  uses. An encrypted `secret/<ref>.enc` file is ciphertext and is not read.
- vault-sync: a file that still holds a value stops the round with the new
  status `plaintext_found` before anything is pushed. The round record, the
  status's `problem` and the attention item `sync_plaintext_found` name each
  file, line and key, never the value.
- vault-sync: a value that is only in an earlier, unpushed commit (the file was
  fixed since) is not published: the round folds the unpushed commits into one
  commit on the remote's head, with the same files, and pushes that.
- vault-sync: the problem carries an agent hand-off that moves each value into
  a Coffer secret and points the file at it, without printing the value.
- vault-sync: "Push anyway" (`POST /api/v1/sync/plaintext/push-anyway`,
  `coffer sync push-anyway`) allows exactly the file versions the last round
  found, records the event `sync_plaintext_pushed` in the audit log, and runs a
  round. With nothing found it is refused with `SYNC_NO_PLAINTEXT_FOUND` (409).
- web-ui (Sync page): a `plaintext_found` card lists the places and offers
  Retry, the hand-off, and Push anyway behind a confirmation.
- Docs: the vault-sync guide, the error-code reference, and the architecture
  page's status table.
