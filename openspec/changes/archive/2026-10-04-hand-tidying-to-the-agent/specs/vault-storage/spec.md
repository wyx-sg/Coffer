## MODIFIED Requirements

### Requirement: Admit every vault write through one compare-and-swap path
Every write to the vault — by the daemon for any surface, by sync, by the knowledge sweep —
SHALL go through one write path that, under the vault's single write lock,
re-reads each file and compares it with what the writer expects (the
fingerprint of the bytes it read, "absent", or "whatever `HEAD` holds"),
writes a sibling temporary file and renames it into place, validates every
touched path, and commits the operation as **one** commit whose author and
`Coffer-Writer`, `Coffer-Operation`, `Coffer-Actor` and `Coffer-Machine`
trailers name the writer. A mismatch MUST refuse the write with
`VAULT_FILE_STALE` (409) and change nothing; there is no unconditional mode,
and a file's modification time MUST NOT decide anything. The reasoning is
[Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md).

#### Scenario: a write is one commit naming its writer and machine
- **GIVEN** a vault on a machine with an id
- **WHEN** a person saves a file through Coffer
- **THEN** `HEAD` is one new commit touching exactly that file, whose trailers name the writer `user` and the machine

#### Scenario: a concurrent hand edit is refused rather than lost
- **GIVEN** a person has edited a vault file on disk and the edit is not settled yet
- **WHEN** the daemon writes the same file expecting what `HEAD` holds
- **THEN** the write is refused as stale and the person's bytes are still on disk

#### Scenario: an operation over many files is one commit
- **GIVEN** an operation that writes two files of one skill
- **WHEN** it completes
- **THEN** one commit holds both files
