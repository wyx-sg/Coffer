## ADDED Requirements

### Requirement: Import a master key after showing whose key it is
Importing a master key MUST show, before anything is replaced, whose key the
file holds beside this machine's: `POST /api/v1/secrets/key/import/preview` takes
the file's text and answers the key's fingerprint, this machine's fingerprint
(or none), whether they are the same key, and whether the file is a
passphrase-protected backup, and MUST change nothing. A protected backup's
fingerprint is read from the file without its passphrase and MUST be checked
against the key when the file is opened; a file whose fingerprint is not its
key's MUST be refused with `MASTER_KEY_FILE_INVALID`. `POST
/api/v1/secrets/key/import` takes the file's text and, for a protected backup,
its passphrase; a missing or wrong passphrase MUST be refused with
`MASTER_KEY_PASSPHRASE_WRONG` and replace nothing. A bare Fernet key needs no
passphrase. On success it MUST answer the fingerprint of the key now in use,
whether a different key was replaced (the replaced key is kept as a backup,
never overwritten), how many stored secrets the key decrypts, and the refs it
still cannot decrypt; it is audited as `master_key_imported` with the
fingerprints and never the key or the passphrase. The running daemon MUST use
the imported key from then on, so a secret stored after the import is sealed
under it. Installing a key MUST need a person present: a process that can reach
the API must not be able to swap the master key and then forge presence grants
under the key it chose. `POST /api/v1/secrets/key/import` MUST therefore redeem a
presence grant for the operation `import_master_key` on the fingerprint of the
key in the request, before anything is replaced; a missing grant, or a grant for
another fingerprint, MUST be refused with `PRESENCE_GRANT_INVALID` and change
nothing (see "Release plaintext only to a present human in the desktop app"). The preview needs no grant: it changes nothing and
returns only fingerprints. The audit event records the actor as the desktop app.

The key is the secret store's, not sync's: `GET /api/v1/secrets/key/fingerprint`
(this machine's fingerprint, never the key), the preview and the import MUST
answer the same whether or not the experimental `sync` feature is on, because
Settings › Security shows the fingerprint and offers the import either way. On
the command line, `coffer secret key-fingerprint` and `coffer secret key-preview`
call the first two; `coffer secret key-install` sends the import request and its
help MUST say that the request needs the presence grant only the desktop app
signs and that a person imports with `coffer secret import-key`, which opens the
import in the app. The command line MUST offer no way to obtain a grant, so a
`key-install` without one is refused and changes nothing.

Settings › Security MUST offer the import, in the desktop app only, as one dialog
whose Replace key runs behind the app's Touch ID prompt naming the key's
fingerprint; in a browser the row says to open the Coffer app and offers no
control. The dialog: choose the key file,
see "Current key" beside "Key in the file" marked same or different, type the
passphrase when the file needs one, and confirm with Replace key; afterwards it
says how many secrets are readable now and names those still locked, with a
way to the Secrets page.

#### Scenario: an import shows whose key the file holds before replacing
- **GIVEN** a machine with its own master key, and a passphrase-protected backup of another machine's key
- **WHEN** the backup, and then a copy of this machine's own key, are previewed
- **THEN** the first answers the other key's fingerprint beside this machine's, not the same, and protected
- **AND** the second answers the same key and not protected, and this machine's key is unchanged after both

#### Scenario: a protected key file opens only with its passphrase
- **GIVEN** a passphrase-protected backup of another machine's key
- **WHEN** it is imported with a wrong passphrase, with none, and then with the right one
- **THEN** the first two are refused with `MASTER_KEY_PASSPHRASE_WRONG`, echo no passphrase and leave this machine's key in place
- **AND** the third installs the other key and answers its fingerprint with `replaced` true

#### Scenario: the security tab replaces a key and names what stays locked
- **GIVEN** Settings › Security, and a backup holding a key different from this machine's
- **WHEN** the person chooses the file, types the passphrase and replaces the key
- **THEN** the dialog showed both fingerprints and "different" before anything was sent to import
- **AND** afterwards it names the key now in use, how many secrets are readable, and the names of those still locked, with Open Secrets

#### Scenario: the master key routes answer whether or not sync is on
- **GIVEN** a running daemon with its master key, once with `sync` on and once with it off
- **WHEN** this machine's key fingerprint is read and another key file is previewed
- **THEN** both answer the same way either time: this machine's fingerprint, and the file's key beside it marked not the same
- **AND** no route under `/api/v1/sync` serves the master key any more

#### Scenario: a key install from the command line without a grant changes nothing
- **GIVEN** a running daemon with its master key
- **WHEN** `coffer secret key-install` is run with a key file and no grant, and again with a grant it made up
- **THEN** the first exits with the invalid-input code and the second with the presence-not-confirmed code naming `PRESENCE_GRANT_INVALID`
- **AND** the key and its fingerprint are unchanged, nothing is audited as `master_key_imported`, and `coffer secret key-install --help` names the presence grant and `coffer secret import-key`

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

Installing a master key is a fifth presence-gated operation. `POST /api/v1/secrets/key/import`
MUST redeem a grant for the operation `import_master_key` whose target is the fingerprint of the
key being imported, before anything changes: a process that can only reach the API could
otherwise swap the key and then forge grants with the key it chose. The desktop app asks the
daemon whose key the file holds (`POST /api/v1/secrets/key/import/preview`, read-only), shows that
fingerprint in the operating system's prompt, signs a grant over it and sends the import with
the grant; a grant for another fingerprint, or none, imports nothing. Settings › Security's
import goes through the desktop app's Touch ID; in a plain browser it says to open the Coffer
app and offers no control.

The shell MUST also be sure the daemon is Coffer's before it sends anything. The port and token
in `~/.coffer/daemon.json` can be rewritten by any process of the same user, so a fake daemon
could otherwise be handed the token or collect a grant. `POST /api/v1/secrets/presence/attest`
takes a random `nonce` and answers `HMAC-SHA256(daemon attest key, nonce + "\n" + port)`, the
attest key being derived from the master key (context `coffer-daemon-attest-key/v1`) and the
port being the one the daemon serves, so an answer relayed from the real daemon on another port
is worth nothing. The shell MUST verify the answer with its own derivation before handing the
token to the page (on attach, on a cold start and after a restart) and before every
presence-gated operation (reveal, approve, approve several, key backup, key import); on a
failure it aborts with "This is not Coffer's daemon — nothing was sent" and sends nothing.

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
