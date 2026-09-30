## MODIFIED Requirements

### Requirement: Release plaintext only to a present human in the desktop app
Revealing or copying a secret, and writing a backup of the master key, MUST
happen only through the desktop app, each behind its own LocalAuthentication
check (Touch ID or the login password, `deviceOwnerAuthentication`) with no
reuse window. The daemon MUST release a value (`POST
/api/v1/secrets/presence/reveal`), write a key backup
(`POST /api/v1/secrets/presence/master-key-export`) or apply an approval
only against a **presence grant**: a one-time challenge
(`POST /api/v1/secrets/presence/challenge`) bound to one operation and one
target, signed with a key derived from the master key. A challenge MUST expire
within two minutes, MUST be consumed by its first use whether or not the
signature verifies, and MUST NOT authorise any other operation or target.

The key backup MUST be protected by a passphrase of at least eight characters
that the person types in the desktop app: the file (`coffer-master-key.cfk`)
holds the master key encrypted under a key derived from that passphrase with
scrypt, beside the key's fingerprint, and never the key in the clear. A
shorter passphrase MUST be refused with `MASTER_KEY_PASSPHRASE_TOO_SHORT`
before the grant is redeemed. The backup MUST be written into the directory
the person picked, under a name of Coffer's choosing, with mode `0600`, never
over an existing file (a number is added to the name instead), audited as
`master_key_exported` with its path and fingerprint; neither the key nor the
passphrase MAY cross the API in an answer, reach the log or an audit row, or
be stored. A reveal MUST be audited as `secret_revealed` with the ref only.
`GET /api/v1/secrets/presence/status` MUST say whether the daemon runs a
development build, in which the master key is a file any same-user process can
read and a grant can therefore be forged; the desktop app MUST say so on every
presence prompt. The browser UI MUST offer none of these actions and MUST name
the desktop app instead: Settings › Security shows the export as a disabled
"Open in Coffer app to export" with the reason beside it. How the grant is
formed is in the change's design.

#### Scenario: a reveal with a valid grant returns the value once
- **GIVEN** a stored secret and a challenge issued for revealing exactly that ref
- **WHEN** the reveal is sent with the challenge signed by the grant key
- **THEN** the value is returned and a `secret_revealed` entry names the ref and not the value
- **AND** sending the same grant again is refused with `PRESENCE_GRANT_INVALID`

#### Scenario: a grant for one operation authorises nothing else
- **GIVEN** a challenge issued to reveal one ref
- **WHEN** it is signed with the wrong key, used for another ref, or used to approve an approval
- **THEN** each attempt is refused with `PRESENCE_GRANT_INVALID` and nothing is revealed or applied

#### Scenario: the master key backup is written only against a grant
- **GIVEN** a directory the person picked and a passphrase
- **WHEN** the key backup is requested with a valid grant for that directory, and again without one
- **THEN** the first writes a `0600` `coffer-master-key.cfk` into that directory that opens with the passphrase and does not hold the key in the clear, answers only its path and fingerprint, and records `master_key_exported` without the passphrase
- **AND** the second is refused and writes nothing
- **AND** a later backup into the same directory is written beside the first under a numbered name

#### Scenario: a short backup passphrase is refused first
- **GIVEN** a valid grant to write a key backup into a directory
- **WHEN** the backup is requested with a passphrase under eight characters
- **THEN** it is refused with `MASTER_KEY_PASSPHRASE_TOO_SHORT` and nothing is written
- **AND** the same grant still writes the backup with a long enough passphrase

#### Scenario: the browser offers no master key export
- **GIVEN** Settings › Security open in a browser rather than the desktop app
- **WHEN** the Encryption section renders
- **THEN** the backup row shows a disabled "Open in Coffer app to export" and says exporting is only available in the desktop app
- **AND** no control starts an export
