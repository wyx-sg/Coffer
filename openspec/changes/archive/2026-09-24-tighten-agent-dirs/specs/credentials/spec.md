## MODIFIED Requirements

### Requirement: Resolve the master key file-first and create it only for an empty store
Key resolution MUST read the file first and the keychain second, and MUST create a new key only
while the `credentials` table is empty. It MUST also never create a key while the keychain cannot be read —
locked, or its unlock prompt dismissed: the key may be there (it is opted into with a relocation),
and a new file key would shadow it on every later start because the file is read first. The
daemon then refuses to start with `CREDENTIAL_LOCKED`, naming the key file it looked for and
saying to unlock the keychain, and writes nothing. A host with no keychain backend at all holds
nothing there, so it is treated as an empty keychain. Resolution order is what makes an interrupted relocation
recoverable; the creation rule is what stops a fresh key silently orphaning existing ciphertext.

#### Scenario: the master key is never regenerated over existing ciphertext
- **GIVEN** a vault whose `credentials` table holds at least one row and whose master key is absent from both the file location and the keychain,
- **WHEN** the daemon starts,
- **THEN** it refuses to start with `MASTER_KEY_MISSING` naming the expected key path,
- **AND** no new key is written, so restoring the original key restores access.

#### Scenario: a locked keychain at start creates no key
- **GIVEN** a vault whose `credentials` table is empty, no key file, and an OS keychain that raises "locked" on every read
- **WHEN** the daemon starts
- **THEN** it refuses to start with `CREDENTIAL_LOCKED`, naming the expected key path and saying to unlock the keychain
- **AND** no key file is written, so the keychain's key is the one read once it is unlocked

### Requirement: Refuse to start when the master key is missing
A key that is absent or unusable while ciphertext exists MUST be a fatal `MASTER_KEY_MISSING` naming
the expected path, and the daemon MUST NOT start. It MUST NOT write a replacement key over live
ciphertext under any condition. Restoring the original key MUST restore access to every previously
stored secret. Because an empty store gets a key at its first start and a store with
ciphertext does not start without one, a running daemon always holds a master key; a machine can
be without one only when the key disappears while the daemon runs, which is the case
[vault-sync](../vault-sync/spec.md) "Report refs without a key as locked" covers.

#### Scenario: a missing master key is a named, fatal startup failure
- **GIVEN** a key file that exists but is truncated or corrupt, beside ciphertext,
- **WHEN** the daemon starts,
- **THEN** it fails with `MASTER_KEY_MISSING` naming the path rather than starting with a key that opens nothing.
