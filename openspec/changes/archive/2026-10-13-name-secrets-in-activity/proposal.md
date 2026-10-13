## Why

Activity showed a secret by its ref, and every secret's ref is a minted 32-hex
id: "Handed secret fe55638667a74ca18a73e78cf67f5fe5 to the sync remote". A
person cannot tell which secret that is.

## What Changes

- **Activity names a secret by its label**, read from the Secrets list now (so a
  rename shows), else from `ref_label` on the row (so a deleted secret still
  reads), else as "an unnamed secret". A ref from before minted ids reads as
  its own name. The id is never shown.
- **Audit rows of secret events carry `ref_label`** when the secret has a label:
  filed centrally by the audit service, and by the two routes whose label is not
  yet (a new secret) or no longer (a delete) in the notes when the row is written.
- The sentences say "secret “X”" or "an unnamed secret" as one phrase.

Resources (providers, channels, tools, servers) already read by their name; the
check found no other event that showed an id.

## Impact

- Capabilities: `secret` (the audit requirement).
- Code: `audit_service.py`, `secret_notes_wiring.py`, `secret_routes.py`, `app.py`;
  frontend `secretSentence.ts`, `auditFacts.ts`, `useActivitySentence.ts`, locales.
