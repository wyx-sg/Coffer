## MODIFIED Requirements

### Requirement: Expose the master key's location on every surface
Users MUST be able to read and change the key's location from the management API
(`GET`/`PUT /api/v1/settings/credentials`), from the CLI as the `credentials.storage` setting
(`coffer config get credentials.storage` and `coffer config set credentials.storage file|keychain`,
see [resource-framework](../resource-framework/spec.md), the requirement that defines
`coffer config`), and from a Settings card that states the consequence and confirms before it
writes. `coffer config set credentials.storage` MUST refuse any value other than `file` or
`keychain` before calling the route, and a change MUST run the verified relocation of "Verify the
destination before relocating the master key".

#### Scenario: read and change the master key location from the API and the command line
- **GIVEN** a running daemon whose master key is in the file beside the database
- **WHEN** the location is read with `GET /api/v1/settings/credentials` and with `coffer config get credentials.storage`, then changed to the keychain with `PUT /api/v1/settings/credentials`
- **THEN** both reads report the file location
- **AND** after the change both surfaces report the keychain, and a previously stored secret still reads back

#### Scenario: move the master key with the config command
- **GIVEN** a running daemon whose master key is in the file beside the database
- **WHEN** the user runs `coffer config set credentials.storage keychain`, and then `coffer config set credentials.storage vault`
- **THEN** the first moves the key to the keychain, audited as `master_key_relocated`, and a previously stored secret still reads back
- **AND** the second exits non-zero naming the accepted values and leaves the key where it is

### Requirement: Confirm a command-line delete unless forced
`coffer credentials rm <ref>` MUST confirm before deleting, unless `--force` is given.

#### Scenario: the command line confirms a delete unless forced
- **GIVEN** a stored credential
- **WHEN** the user runs `coffer credentials rm <ref>` and declines the confirmation, then runs it again with `--force`
- **THEN** the declined run leaves the credential stored
- **AND** the forced run deletes it without asking

### Requirement: Route every credential command through the daemon
Every credential command MUST go through the daemon's API and MUST import no credential or keyring
code of its own. This covers the `coffer credentials` group and the `credentials.storage` setting of
`coffer config`. The daemon is the sole owner of the key, and a CLI that opened the keychain itself
would be a second reader to keep honest.

#### Scenario: credential commands import no credential code
- **GIVEN** the `coffer credentials` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the credentials infrastructure package
- **AND** it reaches the vault only through the daemon client

#### Scenario: the config command reaches the master key only through the daemon
- **GIVEN** the `coffer config` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the credentials infrastructure package
- **AND** it reads and changes `credentials.storage` only through the daemon client
