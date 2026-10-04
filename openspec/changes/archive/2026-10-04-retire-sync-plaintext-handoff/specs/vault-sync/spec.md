## REMOVED Requirements

### Requirement: Refuse to push a plaintext secret
**Reason**: Its scenario "the Sync page names each place and offers the hand-off and push anyway" describes the agent hand-off, which is removed: a secret is never handed to an agent. A MODIFIED block cannot drop a scenario, so the requirement is re-added under the same title with the card's new actions.
**Migration**: `problem.handoff` is `null` for `plaintext_found` and the `sync_plaintext_found` attention item carries no hand-off. Move a value with the card's "Move into secrets…" (the Secrets page's move, scoped to the flagged files) and sync again.
