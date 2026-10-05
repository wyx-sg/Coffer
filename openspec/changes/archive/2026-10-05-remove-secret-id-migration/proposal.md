## Why

The one-time start-up move of every secret to a minted `secret/<uuid4 hex>` id
has run on every machine that held older refs. Its code, its audit event and the
display fallbacks for the old ref shapes are now dead weight. Migrations leave
no shims.

## What Changes

- **BREAKING** Remove the start-up move (`RefMigrator`), its `secret_migrated`
  audit event and the requirement that describes it. A ref that is not
  `secret/<32 hex>` is no longer moved, and the Secrets page no longer shows an
  old ref shape by a derived name.
- An alembic data migration deletes `audit_log` rows of the removed
  `secret_migrated` type.
- Remove the helpers written only for the move: rewriting `coffer://secret/<old>`
  in skill files, carrying a ref's binding and time records, and the Secrets
  page's names for `name.KEY`, `<kind>/<hex>/<slot>` and non-hex standalone
  refs.

## Impact

- Backend: `application/secret/ref_migration.py`, `SecretBoundary.rebind`,
  `EncryptedSecretStore.carry_records`, `rewrite_secret_uris`, the wiring in
  `secret_index_wiring.py`; migration 0150.
- Frontend: `secretRows.ts` display names; two i18n strings.
- Specs: `secret`; docs-site secrets guides (en and zh).
