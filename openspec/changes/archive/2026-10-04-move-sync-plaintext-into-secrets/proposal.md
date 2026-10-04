## Why

When a round refuses to push because a file holds a plaintext secret, the Sync
page's card and the attention item offered an agent hand-off: a prompt asking
an agent to move each value into a Coffer secret. Following that prompt means
an agent opens the file that holds the secret. A secret must never be handed
to an agent. Coffer already has a move that needs no agent — the Secrets
page's "Find plaintext keys" — and the design for the card (board 6.4.32) shows
"Move into secrets…" and "Push anyway…".

## What Changes

- The plaintext card's actions are "Move into secrets…" and "Push anyway…".
  The agent hand-off is gone from the card.
- "Move into secrets…" opens the Secrets page's move dialog in place, listing
  only the findings in the flagged files. It moves values out of skill files
  through the same reviewed dry run and import; for flagged files it cannot
  move from (anything but a skill's file) the dialog says so and the person
  edits them. After the move the person syncs again.
- The backend drops the plaintext hand-off prompt: `problem.handoff` is `null`
  for `plaintext_found`, and the `sync_plaintext_found` attention item carries
  no hand-off; its text now reads "Move it into secrets, or push anyway."

## Impact

- Spec: vault-sync "Refuse to push a plaintext secret" (the card's actions,
  no hand-off; a scenario renamed for the new actions).
- Backend: `domain/sync/handoffs.py` loses `plaintext_handoff`; the sync status
  and attention source stop attaching it.
- Frontend: `SyncPlaintextCard`, `ScanSecretsDialog` gains `only`; en and zh
  copy.
- Docs: the vault-sync guide (en and zh).
