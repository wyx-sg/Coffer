## ADDED Requirements

### Requirement: Show a secret this Mac cannot open as missing on this Mac
`GET /api/v1/credentials` MUST mark a stored ref whose ciphertext this Mac's
master key cannot open as `locked`, found by checking each token's signature
against the key without decrypting any value and without an audit entry. The
Secrets page MUST show every row this Mac has no value for — cited but not
stored, or `locked` — as **Missing on this Mac**, with an **Add value** action
in place of its last use, and a banner counting them ("N secrets have no value
on this Mac") whose **Import master key…** opens Settings › Security. Adding the
value MUST be an ordinary write of the ref, subject to the same approvals as any
other write, and reveal MUST be unavailable for such a row.

#### Scenario: a ciphertext from another Mac's key is listed as locked
- **GIVEN** a stored standalone secret encrypted with another Mac's master key, and one stored on this Mac
- **WHEN** the secrets are listed
- **THEN** the first is present and `locked`, the second is not `locked`
- **AND** no value is decrypted and no audit entry is written

#### Scenario: a value added for a locked secret replaces it once approved
- **GIVEN** a locked standalone secret
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `202` naming a pending `replace_value` approval and the row stays `locked`
- **AND** once the approval is applied with a presence grant the row is no longer `locked` and the store reads back the new value

#### Scenario: a secret this Mac cannot open is missing on this Mac
- **GIVEN** a locked secret and a cited secret the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both rows read "Missing on this Mac" with Add value, and a banner says 2 secrets have no value on this Mac and links Import master key… to `/settings/security`
- **AND** Reveal is unavailable for the locked row, and Add value posts the new value for its ref

### Requirement: Hold a new standalone secret until a person approves it
`POST /api/v1/credentials` on a standalone `secret/<name>` that has no value on
this Mac MUST NOT store it while the protection is on: it MUST answer `202` with
a pending `add_secret` approval ("New secret") holding the value only as
ciphertext; applying the approval with a presence grant stores the value, and
rejecting it drops the ciphertext and stores nothing. A newer value for the same
name MUST supersede the approval still waiting. With the protection off the
secret MUST be stored at once. `coffer secret set` MUST report the wait as it
reports any other pending approval.

#### Scenario: adding a standalone secret waits for approval
- **GIVEN** the protection is on and no secret named `npm-publish-token`
- **WHEN** a value is posted for `secret/npm-publish-token`
- **THEN** the answer is `202` naming a pending `add_secret` approval, the store holds nothing under the name, and nothing holds the value in plaintext
- **AND** the approval reads "Approve the new secret npm-publish-token?" labelled New secret and used by nothing yet, and applying it with a presence grant stores the value

### Requirement: Show each change waiting for approval as the question it asks
The web UI MUST show every pending approval as the question it asks — a new
value, a new secret, a new use, or turning the protection off — naming the
secret, who asked and when, and what uses the secret. The Secrets page MUST carry
a banner "N changes waiting for approval" with **Review**, and mark a row whose
new value, or whose adding, waits as "Waiting for approval". In the desktop app
**Approve…** MUST run the shell's presence check (Touch ID or the login
password); in a browser Approve MUST be disabled, naming the desktop app, while
**Reject** stays available.

#### Scenario: a browser can reject a change but not approve it
- **GIVEN** a pending new value for a secret, opened in a browser
- **WHEN** the approvals window shows it
- **THEN** Approve is disabled and says to approve in the Coffer desktop app
- **AND** Reject is enabled and refuses the approval over REST

## MODIFIED Requirements

### Requirement: Hold a replaced value in use until a person approves it
`POST /api/v1/credentials` on a ref an approved destination receives, or on a
standalone `secret/` name that already has a value, MUST NOT replace the value:
it MUST answer `202` with a pending `replace_value` approval and keep the new
value only as ciphertext until the approval is applied, and drop it when the
approval is decided either way. Writing a new ref that is not a standalone
secret, or one nothing receives, MUST store it at once (`204`); a new standalone
secret waits as "Hold a new standalone secret until a person approves it" says.

#### Scenario: replacing a value in use waits for approval
- **GIVEN** a secret an approved MCP server receives
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `202` naming a pending approval, the store still holds the old value, and nothing in the database holds the new value in plaintext
- **AND** applying the approval with a presence grant replaces the value

### Requirement: List every stored and cited secret with what uses it
`coffer secret list` and `GET /api/v1/credentials` MUST list every ref the
store holds and every ref a registered resource cites, each with whether the
store holds it, whether this Mac's key can open it (`locked`), when it was
stored (`created_at`) and when a consumer last had it decrypted on this Mac
(`last_used_at`, stamped at most once a minute and not by a reveal or an
import's read-back), the resources that cite it, for a standalone secret its
`coffer://secret/<name>` and the skills whose files cite that URI, whether
nothing references it (`unreferenced`), the destinations it is approved for or
waits on, and whether another process of this user can read the value where
Coffer puts it (a standalone secret, or a stdio MCP server's environment). The
listing decrypts nothing and records no audit entry. A delete MUST also be
refused with `CREDENTIAL_IN_USE` while a skill in the master store cites a
standalone secret's URI, naming that skill, and a delete that removes a ref
MUST forget its approved destinations.

#### Scenario: the command line lists every cited ref with its presence
- **GIVEN** a registered MCP server citing a stored ref and a registered model provider citing a ref the store does not hold
- **WHEN** the user runs `coffer secret list`
- **THEN** both refs are listed
- **AND** the MCP server's ref is shown as present and the provider's ref as missing

#### Scenario: a secret nothing references is listed as unreferenced
- **GIVEN** a standalone secret no resource and no skill cites, and another that a skill cites by URI
- **WHEN** the credentials are listed
- **THEN** the first is marked unreferenced and readable by local processes
- **AND** the second names the skill, and deleting it is refused naming that skill

#### Scenario: the list says when each secret was created and last used
- **GIVEN** a standalone secret stored and never used
- **WHEN** the secrets are listed, then `coffer run` resolves it, then they are listed again
- **THEN** the first listing carries its `created_at` and no `last_used_at`
- **AND** the second carries a `last_used_at` no later than now

### Requirement: Move plaintext secret files into the store
`POST /api/v1/credentials/scan` (`coffer secret scan`) MUST report every
plaintext secret in `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json`
(a flat map of strings) and in the skill master store (assignments whose name
says password, secret, token or key, and well-known token shapes) by file,
line, key and proposed name, every skill that still mentions
`~/.coffer/secrets/`, and how many files it read (`files_checked`); it MUST NOT
return a value. `POST /api/v1/credentials/import` (`coffer secret import
[--id]… [--dry-run]`) MUST store each chosen value as `secret/<proposed name>`,
confirm the store reads back the same value, and only then replace the value in
its file with the reference, atomically and keeping the file's mode; a name
already holding a different value MUST be skipped with its file untouched; a
file that cannot be rewritten MUST leave its findings skipped as `stored` —
naming the secret the value is now stored as, the file still holding it — while
the other files are rewritten, and importing the same findings again MUST retry
the file; `--dry-run` writes nothing. Each value stored MUST be audited as
`secret_imported` without the value.

#### Scenario: a scan names plaintext secrets without their values
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script assigns a token
- **WHEN** the scan runs
- **THEN** both are reported with their file, key and proposed name, and the response contains neither value

#### Scenario: importing moves a value and leaves a reference
- **GIVEN** those findings
- **WHEN** they are imported
- **THEN** each value reads back from the store under its standalone name, each file now cites `coffer://secret/<name>` in place of the value with its mode unchanged, and a dry run beforehand changed nothing

#### Scenario: a file that cannot be rewritten keeps its key and says so
- **GIVEN** a plaintext secrets file in a folder Coffer cannot write
- **WHEN** its finding is imported
- **THEN** nothing is reported moved, the finding is skipped as `stored` naming its secret and why, the file is unchanged, the store holds the value and one `secret_imported` entry names it
- **AND** importing the same finding again once the folder is writable moves it and rewrites the file

#### Scenario: a scan that finds nothing says how many files it read
- **GIVEN** a secrets folder whose only file holds no secret
- **WHEN** the scan runs
- **THEN** it reports no findings and at least one file read
