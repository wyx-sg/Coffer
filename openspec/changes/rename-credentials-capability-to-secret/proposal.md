## Why

Coffer's user-facing word for an API key or token it stores is **secret**: the page is Secrets, the dialogs say
"Add secret", and a reference is written `secret:<name>`. The command line and the capability still said
*credentials*, so a reader met two words for one thing, and `coffer credentials` was the only plural group in a
CLI whose other groups are singular (`coffer mcp`, `coffer skill`, `coffer provider`).

## What Changes

- The OpenSpec capability `credentials` becomes `secret`: `openspec/specs/credentials/` moves to
  `openspec/specs/secret/` (spec, data model and generated contract), its title becomes "Secrets", and
  `scripts/gen_contracts.py` assigns the `/api/v1/credentials` and `/api/v1/settings` routes to `secret`.
  The id is singular because the capability id is a path, and a checked-in permission rule denies agents any path
  containing `secrets/`.
- Every citation (`spec credentials "..."`, links to `openspec/specs/credentials/spec.md`) and every acceptance
  marker (`spec="credentials"`) follows the new id. Requirement titles are unchanged.
- The CLI group `coffer credentials` is replaced by `coffer secret`, with the same subcommands. The old group is
  removed with no alias; `scripts/check_removed_commands.py` fails any doc, spec, skill, web UI or e2e file that
  still quotes it.
- The flags and the setting that said *credential* follow, also with no alias: `coffer mcp add|edit --credential`
  becomes `--secret` and `--clear-credentials` becomes `--clear-secrets`; `coffer provider add --credential-ref` and
  `coffer sync remote set --credential-ref` become `--secret-ref`; `--with-credentials|--without-credentials`
  becomes `--with-secrets|--without-secrets`; the `coffer config` key `credentials.storage` becomes
  `secrets.storage`, beside `secrets.require_approval` (the key is only a name for `PUT /api/v1/settings/credentials`;
  nothing stores it).
- The docs-site page `guides/credentials` becomes `guides/secret-store` ("Secret store").
- User-facing text says "secret": CLI help and output, error messages, the web UI's strings, docs-site, README and
  the coffer-guide skill. The generated CLI reference is regenerated.
- Internal names stay: the Python packages `application/credentials/` and `infrastructure/credentials/`, the
  database tables, the REST path `/api/v1/credentials`, error codes (`CREDENTIAL_*`) and audit event types.

## Capabilities

### New Capabilities

### Modified Capabilities

None: the capability is renamed, its requirements are not. The spec text changes only where it names the command.

## Impact

- `openspec/specs/secret/`, `scripts/gen_contracts.py`, `scripts/check_removed_commands.py`.
- `backend/coffer/surfaces/cli/` (the group and its help), tests that invoke it or carry acceptance markers.
- `docs-site/`, `README.md`, `.agents/`, the coffer-guide skill, `frontend/src/i18n/locales/`, e2e specs.
