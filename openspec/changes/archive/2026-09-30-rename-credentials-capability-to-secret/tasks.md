## 1. Capability

- [x] 1.1 Move `openspec/specs/credentials/` to `openspec/specs/secret/` and retitle the spec "Secrets"
- [x] 1.2 Assign the `/api/v1/credentials` and `/api/v1/settings` routes to `secret` in `scripts/gen_contracts.py` and regenerate the contract
- [x] 1.3 Rewrite every citation, spec link and acceptance marker that names `credentials` as a capability

## 2. Command line

- [x] 2.1 Replace the `coffer credentials` group with `coffer secret` (same subcommands, no alias)
- [x] 2.2 Say "secret" in the group's help, output and error text
- [x] 2.3 Add `coffer credentials` to `scripts/check_removed_commands.py` with `coffer secret` as the replacement
- [x] 2.4 Update CLI tests

## 3. Words users read

- [x] 3.1 Web UI strings (en, zh): "secret" wherever a user reads "credential"
- [x] 3.2 docs-site, README, `.agents/`, the coffer-guide skill; regenerate the CLI reference (`make docs-reference`)
- [x] 3.3 e2e specs that run or quote the command

## 4. Internal names

- [x] 4.1 `git mv` the Python packages and modules named credential* (`application/secret/`, `infrastructure/secret/`, `infrastructure/sync/secret.py`, `application/secret_migration.py`, `domain/secret_errors.py`, `surfaces/http/secret_*.py`) and their tests; rename classes, functions and variables; update the import-linter contracts, `scripts/stamp_build_identity.py` and every doc that names a module path
- [x] 4.2 Frontend: `components/secret/`, `lib/api/secret.ts`, `lib/secretRef.ts`, `useSecretSettings`, `SecretRowEditor`; merge the `credentials.*` i18n namespace into `secrets.*`
- [x] 4.3 REST: `/api/v1/credentials…` → `/api/v1/secrets…`, `/api/v1/settings/credentials` → `/api/v1/settings/secrets`; the desktop shell, CLI, web UI and e2e callers follow; `make contracts` and `make docs-reference`
- [x] 4.4 Error codes `CREDENTIAL_*` → `SECRET_*` (with the i18n `errors.*` keys, the backend-keys fixture and the error-codes reference) and the CLI exit code `SECRET_ISSUE`
- [x] 4.5 Audit event types `credential_*` → `secret_*`, with their Activity labels
- [x] 4.6 Migration 0135 renames the table, the sync remote's columns, the stored audit event types and the config keys (`transport.secret_refs`, a provider's `secret_ref`), with a downgrade and a migration test
- [x] 4.7 Requirement titles, scenario names and their citations and markers say *secret* where they meant a stored secret
