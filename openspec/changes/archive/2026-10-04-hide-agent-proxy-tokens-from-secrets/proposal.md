## Why

The Secrets page listed each managed agent's model-proxy token by its ref's last
segment — a 32-character agent uid such as `9a006a32d0bf5787955c43d54e4b44e9` —
used by nothing. Coffer mints these tokens and the agents fetch them on their
own, so a person has nothing to enter, replace, reveal or cite there; the rows
only read as unknown secrets that are safe to delete.

## What Changes

- `GET /api/v1/secrets` and `coffer secret list` leave out `proxy-token/<agent_uid>`.
- A secret row's ⋯ menu loses **View in Activity**.
- The Used by popover names the secret by the name the list shows, keeps its
  title on one line, and wraps a long reference instead of overflowing.

## Impact

- Backend: `surfaces/http/secret_routes.py`.
- Frontend: `components/secret/SecretRowMenu.tsx`, `SecretUsedBy.tsx`, i18n.
- Specs: secret.
- Docs: guides/secrets (en + zh).
