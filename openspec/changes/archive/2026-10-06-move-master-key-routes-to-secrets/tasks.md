## 1. Backend

- [x] 1.1 Move the key half of the sync service into `application/secret/master_key_import.py` (`MasterKeyService`), published by the sync wiring over the same resolved key
- [x] 1.2 Serve `/api/v1/secrets/key/{fingerprint,import/preview,import}` from `surfaces/http/secret_key_routes.py`, inside the secrets router; remove them from `sync_routes`
- [x] 1.3 Move the five key schemas to `secret_key_schemas.py`; `make contracts`

## 2. Command line

- [x] 2.1 Replace `sync key fingerprint | import-preview | import` with `secret key-fingerprint | key-preview | key-install`; `key-install`'s help names the grant and `coffer secret import-key`
- [x] 2.2 `sync file-answer`'s help lists the answers from `Answer`

## 3. Web UI and desktop app

- [x] 3.1 `securityApi` and the shell's import call the new paths; types come from the secret contract

## 4. Tests

- [x] 4.1 Fingerprint and preview answer with sync on and off; the old sync paths are gone
- [x] 4.2 `coffer secret key-install` without a grant and with a forged one is refused (exit 6, exit 11) and the key is unchanged
- [x] 4.3 `sync file-answer`'s documented answers are exactly the accepted ones

## 5. Docs

- [x] 5.1 Secret-store guide, architecture vault-sync and principles (en + zh), ADR secrets-cross-machines-only-as-ciphertext
