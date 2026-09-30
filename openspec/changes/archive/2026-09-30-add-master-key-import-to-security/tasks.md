## 1. Backend

- [x] 1.1 `key_backup.py`: wrap / peek / unwrap the `.cfk` format (scrypt N=2^17, r=8, p=1; bounded parameters on read; header fingerprint checked against the key); bare Fernet keys still read
- [x] 1.2 Export route: passphrase checked before the grant is redeemed, `.cfk` written `0600` under a numbered name that never overwrites, passphrase in no answer, log or audit row
- [x] 1.3 `POST /sync/key/import/preview`; `POST /sync/key/import` with `passphrase` and `fingerprint` / `replaced` / `readable` / `locked_refs`
- [x] 1.4 The running secret store switches to an imported key (`EncryptedSecretStore.use_key`, wired through `ResolvedMasterKey(on_install=…)`)
- [x] 1.5 Validation failures logged without `input`
- [x] 1.6 `coffer sync key import` prompts for a `.cfk` passphrase without echo
- [x] 1.7 `make contracts`

## 2. Desktop

- [x] 2.1 `export_master_key_backup(passphrase)`: refuses a short one before the presence check, sends it only in the export request

## 3. Frontend

- [x] 3.1 Export dialog (passphrase + repeat, exported state with Show in Finder); browser: disabled "Open in Coffer app to export" with the reason
- [x] 3.2 Import dialog (Choose…, passphrase for a protected file, current vs file fingerprint, Replace key; result with Readable now / Still locked / Open Secrets)
- [x] 3.3 Key fingerprint row, uppercase groups of four
- [x] 3.4 en + zh strings; error strings for the two new codes

## 4. Docs and tests

- [x] 4.1 Backend unit (`key_backup`), integration (export, preview, import, CLI) with acceptance markers
- [x] 4.2 Frontend vitest for the Security tab
- [x] 4.3 docs-site pages that describe the key backup and import
