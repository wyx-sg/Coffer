## 1. Backend

- [x] 1.1 Delete `RefMigrator` and its wiring; delete `rewrite_secret_uris`, `SecretBoundary.rebind` and `EncryptedSecretStore.carry_records`
- [x] 1.2 Remove the `secret_migrated` audit event; migration 0150 deletes its rows
- [x] 1.3 Delete the migration's integration test

## 2. Frontend

- [x] 2.1 Drop the display fallbacks for old ref shapes; remove the `secret_migrated` strings

## 3. Specs and docs

- [x] 3.1 Remove the requirement "Move every secret to a fixed id once"; update the data model
- [x] 3.2 Remove the migration paragraphs from the secrets guides (en and zh)
