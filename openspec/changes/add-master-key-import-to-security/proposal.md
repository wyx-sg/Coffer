## Why

Settings › Security is where a person backs up this Mac's master key and brings
another Mac's key in, but it only offered the export, and the export wrote the
raw Fernet key into a plain file: a backup left in Downloads or a synced folder
opened every secret of the vault. Importing lived on the Sync page as a bare
confirm with no way to tell whether the file held this Mac's own key or a
different one, and afterwards said only how many references stayed locked.

Two defects sat underneath. The running credential store kept the key it was
started with after an import, so a secret saved right after importing was
sealed under a key the machine no longer kept, and became unreadable at the
next start. And a request that failed validation logged the submitted body —
for the import route, the key material itself.

## What Changes

- The master key backup is `coffer-master-key.cfk`: the key encrypted under a
  key derived with scrypt from a passphrase of at least eight characters, with
  the key's fingerprint in the clear. The desktop app's Export dialog asks for
  the passphrase twice; it travels page → shell command argument → the
  daemon's export request, and is never stored, logged or recorded. The file
  name never overwrites (`coffer-master-key-2.cfk` beside an existing one).
- `POST /api/v1/sync/key/import/preview` (new) answers whose key a file holds
  beside this Mac's (`fingerprint`, `current_fingerprint`, `same`,
  `protected`) and replaces nothing. `POST /api/v1/sync/key/import` takes an
  optional `passphrase` and answers `fingerprint`, `replaced`, `readable` and
  `locked_refs`. A bare Fernet key (a development build's `master.key`) still
  imports without a passphrase.
- Settings › Security gains "Import a master key" (file, passphrase, current
  key beside the file's key, Replace key, then how many secrets are readable
  and which are still locked, with Open Secrets) and the key fingerprint row,
  shown uppercase in groups of four. In a browser the export is a disabled
  "Open in Coffer app to export" with the reason beside it.
- `coffer sync key import <file>` reads a `.cfk` and asks for its passphrase
  without echoing it.
- An imported key is used by the running credential store at once.
- Validation failures are logged without the submitted values.

## Capabilities

### Modified Capabilities

- `secret`: "Release plaintext only to a present human in the desktop app" —
  the backup is passphrase-protected, the passphrase is checked before the
  grant is spent, and the browser offers no export.
- `vault-sync`: new "Import a master key after showing whose key it is";
  "Cover the same operations over HTTP" lists the preview route.
- `desktop-app`: "Release plaintext and approvals only after a presence check
  in the shell" — the export command takes the passphrase and passes it only
  to the daemon.

## Impact

- Backend: `infrastructure/credentials/key_backup.py` (new),
  `surfaces/http/credential_boundary_routes.py` (export),
  `surfaces/http/sync_routes.py` / `sync_schemas.py` (key section),
  `application/sync/service.py` (key functions), `infrastructure/sync/credentials.py`,
  `infrastructure/credentials/encrypted_store.py` (`use_key`),
  `surfaces/http/sync_wiring.py`, `surfaces/http/errors.py`,
  `surfaces/cli/sync_machine_cmd.py`; two error codes
  `MASTER_KEY_PASSPHRASE_WRONG` and `MASTER_KEY_PASSPHRASE_TOO_SHORT` (422).
- Desktop: `export_master_key_backup(passphrase)`.
- Frontend: Settings › Security export, import and fingerprint rows; the Sync
  page's own export button now reaches a shell that refuses an empty passphrase
  until that page gets the same dialog.
- Wire contract: `secret` (`MasterKeyExportIn.passphrase`) and `vault-sync`
  (`KeyPreviewOut`, `KeyImportIn`, `KeyImportOut`).
