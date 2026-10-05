## 1. Core
- [x] 1.1 Fingerprint key context, fingerprint function, machine-local ignore store

## 2. Secrets page
- [x] 2.1 Scan marks `ignored`; ignore / unignore service + routes + CLI; audit events; `SECRET_LOCKED` without a master key
- [x] 2.2 Tests incl. `acceptance("secret", "a finding marked not a secret is not reported again")`, `acceptance("secret", "a remembered value can be reported again")`
- [x] 2.3 Dialog: Not a secret, Show ignored (N), Report again; `acceptance("secret", "the dialog hides what is not a secret")`

## 3. Vault sync
- [x] 3.1 `find_plaintext` returns fingerprints; remembered values do not stop a round; `PlaintextFinding.fingerprint` kept in the round record (never on the wire); Push anyway remembers
- [x] 3.2 Tests incl. `acceptance("vault-sync", "a value pushed anyway does not stop a later edit of its file")`; Push anyway confirmation copy

## 4. Finish
- [x] 4.1 Contracts, docs (en + zh), CLI/REST reference
- [x] 4.2 `make -C . verify`, archive
