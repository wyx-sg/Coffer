## MODIFIED Requirements

### Requirement: Keep the master key in exactly one place
In a development build the Fernet master key MUST live in exactly one of two places: a `0600`
file, `~/.coffer/master.key` (the default), or the OS keychain (opt-in); a signed release keeps it in
its Keychain access group instead (see "Keep the master key behind a storage port chosen by the
build"). It MUST NOT exist in two places as a system of record. The master key is the single
piece of secret material outside the vault and is never copied into the vault or into anything
it publishes. A read that needs the keychain and cannot have it MUST fail with a locked condition
rather than a missing one.

#### Scenario: the master key lives in the file or the keychain, never both
- **GIVEN** a master key stored in the `0600` file `~/.coffer/master.key`
- **WHEN** the key is relocated to the OS keychain and then back to the file
- **THEN** after the first move the keychain holds the key and the file no longer exists
- **AND** after the second move the file holds the same key with mode `0600` and the keychain entry is gone

### Requirement: Verify the destination before relocating the master key
Relocating the key MUST write and verify the destination copy before removing the source, so an
interruption resolves back to the source location with a harmless duplicate rather than to no key
at all. Moving the key between the file and the OS keychain MUST leave every stored secret
readable, in both directions, across a daemon restart.

#### Scenario: relocating the master key verifies the destination before removing the source
- **GIVEN** the master key is stored in the `0600` file `~/.coffer/master.key`,
- **WHEN** the user moves it to the OS keychain,
- **THEN** the keychain copy is written and read back before the file is removed, the move is audited as `master_key_relocated`, and an interruption anywhere in between leaves the key resolvable from the file.

### Requirement: Expose the master key's location on every surface
Users MUST be able to read and change the key's location from the management API
(`GET`/`PUT /api/v1/settings/secrets`), from the CLI as the `secrets.storage` setting
(`coffer config get secrets.storage` and `coffer config set secrets.storage file|keychain`,
see [resource-framework](../resource-framework/spec.md), the requirement that defines
`coffer config`), and from a Settings card that states the consequence and confirms before it
writes. `coffer config set secrets.storage` MUST refuse any value other than `file` or
`keychain` before calling the route, and a change MUST run the verified relocation of "Verify the
destination before relocating the master key".

#### Scenario: read and change the master key location from the API and the command line
- **GIVEN** a running daemon whose master key is in the file `~/.coffer/master.key`
- **WHEN** the location is read with `GET /api/v1/settings/secrets` and with `coffer config get secrets.storage`, then changed to the keychain with `PUT /api/v1/settings/secrets`
- **THEN** both reads report the file location
- **AND** after the change both surfaces report the keychain, and a previously stored secret still reads back

#### Scenario: move the master key with the config command
- **GIVEN** a running daemon whose master key is in the file `~/.coffer/master.key`
- **WHEN** the user runs `coffer config set secrets.storage keychain`, and then `coffer config set secrets.storage vault`
- **THEN** the first moves the key to the keychain, audited as `master_key_relocated`, and a previously stored secret still reads back
- **AND** the second exits non-zero naming the accepted values and leaves the key where it is
