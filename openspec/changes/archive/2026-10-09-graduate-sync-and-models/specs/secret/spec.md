## MODIFIED Requirements

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
answer from the secret store, never from sync, because Settings › Security
shows the fingerprint and offers the import whether or not a sync remote is
configured. On
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
