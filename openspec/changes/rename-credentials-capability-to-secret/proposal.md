## Why

Coffer's user-facing word for an API key or token it stores is **secret**: the page is Secrets, the dialogs say
"Add secret", and a reference is written `secret:<name>`. The command line, the capability and the internals still
said *credentials*, so a reader met two words for one thing, and `coffer credentials` was the only plural group in a
CLI whose other groups are singular (`coffer mcp`, `coffer skill`, `coffer provider`).

## What Changes

- The OpenSpec capability `credentials` becomes `secret`: `openspec/specs/credentials/` moves to
  `openspec/specs/secret/` (spec, data model and generated contract), its title becomes "Secrets", and
  `scripts/gen_contracts.py` assigns the secret routes and `/api/v1/settings` to `secret`.
  The id is singular because the capability id is a path, and a checked-in permission rule denies agents any path
  containing `secrets/`.
- Every citation (`spec credentials "..."`, links to `openspec/specs/credentials/spec.md`) and every acceptance
  marker (`spec="credentials"`) follows the new id.
- The CLI group `coffer credentials` is replaced by `coffer secret`, with the same subcommands. The old group is
  removed with no alias; `scripts/check_removed_commands.py` fails any doc, spec, skill, web UI or e2e file that
  still quotes it.
- The flags and the setting that said *credential* follow, also with no alias: `coffer mcp add|edit --credential`
  becomes `--secret` and `--clear-credentials` becomes `--clear-secrets`; `coffer provider add --credential-ref` and
  `coffer sync remote set --credential-ref` become `--secret-ref`; `--with-credentials|--without-credentials`
  becomes `--with-secrets|--without-secrets`; the `coffer config` key `credentials.storage` becomes
  `secrets.storage`, beside `secrets.require_approval` (the key is only a name for `PUT /api/v1/settings/secrets`;
  nothing stores it).
- The docs-site page `guides/credentials` becomes `guides/secret-store` ("Secret store").
- User-facing text says "secret": CLI help and output, error messages, the web UI's strings, docs-site, README and
  the coffer-guide skill. The generated CLI reference is regenerated.
- The internals say "secret" too, with no alias and no reader that accepts the old name:
  - Python: `application/credentials/` → `application/secret/`, `infrastructure/credentials/` →
    `infrastructure/secret/`, `infrastructure/sync/credentials.py` → `infrastructure/sync/secret.py`,
    `application/credential_migration.py` → `application/secret_migration.py`, `domain/credential_errors.py` →
    `domain/secret_errors.py`, `surfaces/http/credential_{routes,boundary_routes,schemas,composition}.py` →
    `secret_*.py`; classes and functions follow (`EncryptedCredentialStore` → `EncryptedSecretStore`,
    `CredentialResolver` → `SecretResolver`, `get_credential_store` → `get_secret_store`, `credential_ref` →
    `secret_ref`, `include_credentials` → `include_secrets`, …). The import-linter contracts, the PyInstaller
    inputs and `scripts/stamp_build_identity.py` follow.
  - Frontend: `components/credentials/` → `components/secret/`, `lib/api/credentials.ts` → `lib/api/secret.ts`,
    `lib/credentialRef.ts` → `lib/secretRef.ts`, `useCredentialSettings` → `useSecretSettings`,
    `CredentialRowEditor` → `SecretRowEditor`; the `credentials.*` i18n namespace merges into `secrets.*`, and keys
    naming a credential say secret.
  - REST: `/api/v1/credentials…` → `/api/v1/secrets…` (`/api/v1/credentials/secrets/resolve` →
    `/api/v1/secrets/resolve`), `/api/v1/settings/credentials` → `/api/v1/settings/secrets`, the router tag
    `credentials` → `secrets`, and the operation ids and schema names follow (`CredentialRefOut` → `SecretRefOut`,
    …). The desktop shell, the CLI, the web UI and the e2e suite call the new paths.
  - Error codes `CREDENTIAL_MISSING|LOCKED|UNREADABLE|IN_USE` → `SECRET_*`, `PROVIDER_CREDENTIAL_SOURCE_INVALID` →
    `PROVIDER_SECRET_SOURCE_INVALID`, and the CLI exit code `CREDENTIAL_ISSUE` → `SECRET_ISSUE` (still 8).
  - Audit event types `credential_set|read|deleted|migrated|revealed` → `secret_*`.
  - Stored data, by migration 0134 (which also adds `last_used_at`): the table `credentials` → `secrets`,
    `sync_remotes.credential_ref|include_credentials` → `secret_ref|include_secrets`, every `audit_log.event_type`
    above, an `mcp_server` config's `transport.credential_refs` → `transport.secret_refs` and a `provider` config's
    `credential_ref` → `secret_ref`. The downgrade reverses each.
  - Requirement titles and scenario names that said *credential* for a stored secret say *secret*; citations and
    acceptance markers follow. Titles where *credential* means something else — the daemon token the desktop app
    hands a page, a release's signing credentials, a chat platform's app credentials, Codex's credential file — are
    unchanged.
- Unchanged on purpose: the vault repository's layout (`credentials/<ref>.enc` and the sync area `credentials`),
  which is being rewritten on its own branch.

## Capabilities

### New Capabilities

### Modified Capabilities

None: the capability is renamed, its behaviour is not. The spec text changes where it names the command, a route, a
stored name or the word itself.

## Impact

- `openspec/specs/secret/` and every spec that cites it, `scripts/gen_contracts.py`, `scripts/check_removed_commands.py`.
- `backend/coffer/` (packages, routes, errors, audit types, migration 0134), `backend/pyproject.toml`, the PyInstaller
  specs' inputs, `scripts/stamp_build_identity.py`, tests.
- `frontend/src/` (components, API layer, hooks, i18n), `desktop/src/`, `e2e/`.
- `docs-site/`, `README.md`, `.agents/`, the coffer-guide skill; the CLI and REST references are regenerated.
