## Why

A skill a person adds, or an MCP server or custom tool they register, often
carries its credentials in plain text — a token in a script, a password in a
stdio server's `env`, a bearer token in a header. Coffer already keeps
secrets encrypted and resolves them at the moment of use, but nothing helps
move a plaintext value that is already there into the store. The Secrets page
used to scan the skill store and the old `~/.coffer/secrets/` folder; that scan
was removed with the folder's migration, and it never looked at MCP servers or
custom tools.

## What Changes

- `POST /api/v1/secrets/scan` reports plaintext secrets in managed skills'
  files and in registered MCP servers' stdio `env`, HTTP `headers` and HTTP API
  (custom tool) `headers` — by resource, place and what each becomes — never a
  value.
- `POST /api/v1/secrets/import` moves the chosen findings, with a dry run: a
  skill's value becomes a standalone secret cited as `coffer://secret/<name>`
  in its file; a server's value moves into the server's own `secret_refs`
  through the resource service. Each move is audited as `secret_imported`.
- The Secrets page gets **Find plaintext keys**: a dialog listing the findings,
  Review changes (dry run), Apply.

## Impact

- Backend: `infrastructure/secret/plaintext_scan.py`, a new
  `application/secret/plaintext_move.py`, `surfaces/http/secret_boundary_routes.py`
  (or a new route module), `secret_schemas.py`, `domain/audit.py`.
- Frontend: `components/secret/` scan dialog, `pages/SecretsPage.tsx`, i18n, codegen.
- Specs: secret (added requirement), web-ui (Secrets page entry point); `contracts/api.openapi.yaml`.
- Docs: guides/secrets (en + zh).
