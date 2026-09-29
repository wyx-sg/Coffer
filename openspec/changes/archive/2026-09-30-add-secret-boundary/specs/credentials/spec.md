## ADDED Requirements

### Requirement: Return no plaintext on any route, command or tool
No management route, `coffer` command or MCP tool MUST return a secret's
plaintext or the master key, with two exceptions this spec names: the desktop
app's presence-gated reveal and key backup (see "Release plaintext only to a
present human in the desktop app"), and `coffer run`'s resolve of standalone
secrets (see "Resolve standalone secrets into one child with coffer run").
There is no `GET /api/v1/credentials/{ref}`, no `coffer credentials get
--show`, no `POST /api/v1/sync/key/export` and no `coffer sync key export`.
Writing a secret stays open to every surface: a caller that supplies a value
already has it. An audit row is not a refusal — a path that returns a value is
a defect however it is audited
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

#### Scenario: no route or command hands out a stored value
- **GIVEN** a running daemon holding a secret under a ref
- **WHEN** a caller with the daemon's token asks `GET /api/v1/credentials/{ref}`, `POST /api/v1/sync/key/export`, `coffer credentials get <ref> --show` and `coffer sync key export <file>`
- **THEN** each is refused as a route or command that does not exist
- **AND** no response or output carries the value or the master key

### Requirement: Check a secret's presence on the command line
`coffer credentials get <ref>` MUST print `[redacted]` when the store holds the
ref and exit `4` when it does not, by way of the presence probe, which decrypts
nothing and audits nothing. It MUST offer no option that prints the value; its
help MUST name the desktop app as the place to see one.

#### Scenario: the command line confirms presence and has no way to print a value
- **GIVEN** a stored credential
- **WHEN** the user runs `coffer credentials get <ref>`, and then the same command with `--show`
- **THEN** the first prints `[redacted]` and records no audit entry
- **AND** the second is refused as an unknown option and prints nothing of the value

### Requirement: Release plaintext only to a present human in the desktop app
Revealing or copying a secret, and writing a backup of the master key, MUST
happen only through the desktop app, each behind its own LocalAuthentication
check (Touch ID or the login password, `deviceOwnerAuthentication`) with no
reuse window. The daemon MUST release a value (`POST
/api/v1/credentials/presence/reveal`), write a key backup
(`POST /api/v1/credentials/presence/master-key-export`) or apply an approval
only against a **presence grant**: a one-time challenge
(`POST /api/v1/credentials/presence/challenge`) bound to one operation and one
target, signed with a key derived from the master key. A challenge MUST expire
within two minutes, MUST be consumed by its first use whether or not the
signature verifies, and MUST NOT authorise any other operation or target. The
key backup MUST be written into the directory the person picked, under a name
of Coffer's choosing, with mode `0600`, never over an existing file, audited as
`master_key_exported`; the key itself MUST NOT cross the API. A reveal MUST be
audited as `credential_revealed` with the ref only.
`GET /api/v1/credentials/presence/status` MUST say whether the daemon runs a
development build, in which the master key is a file any same-user process can
read and a grant can therefore be forged; the desktop app MUST say so on every
presence prompt. The browser UI MUST offer none of these actions and MUST name
the desktop app instead. How the grant is formed is in the change's design.

#### Scenario: a reveal with a valid grant returns the value once
- **GIVEN** a stored secret and a challenge issued for revealing exactly that ref
- **WHEN** the reveal is sent with the challenge signed by the grant key
- **THEN** the value is returned and a `credential_revealed` entry names the ref and not the value
- **AND** sending the same grant again is refused with `PRESENCE_GRANT_INVALID`

#### Scenario: a grant for one operation authorises nothing else
- **GIVEN** a challenge issued to reveal one ref
- **WHEN** it is signed with the wrong key, used for another ref, or used to approve an approval
- **THEN** each attempt is refused with `PRESENCE_GRANT_INVALID` and nothing is revealed or applied

#### Scenario: the master key backup is written only against a grant
- **GIVEN** a directory the person picked
- **WHEN** the key backup is requested with a valid grant for that directory, and again without one
- **THEN** the first writes a `0600` file holding the key into that directory, answers only its path and fingerprint, and records `master_key_exported`
- **AND** the second is refused and writes nothing

### Requirement: Hold a secret for a new destination until a person approves it
A destination is a place Coffer sends a secret's plaintext: an MCP server's
environment variable or HTTP header, a channel adapter's credential, the sync
remote's push token, and — through the same service call — a provider
connection's key and a custom tool's authentication. Every consumer MUST name
the destination and the **target** that receives the value (a stdio server's
whole command line with its working directory and non-secret environment, an
HTTP URL, a git URL, a channel's platform and app) before it resolves a secret,
and MUST inject nothing into a target no person approved: the attempt answers
`SECRET_BINDING_PENDING` (409) naming the pending approvals. Citing an existing
secret from a destination that did not cite it, and changing the target of one
that did, each record a pending approval, once per target; a later target
supersedes the approval for the earlier one. A binding already approved for
its target MUST keep working. A binding is approved without a person only when
it was in use before this requirement existed (adopted once, at the first start
of the daemon that has it), when its value was supplied for it — the ref was
never bound anywhere, is not a standalone `secret/` name, and was stored within
the last five minutes — or while the protection is switched off. Approving MUST
take a presence grant (`POST /api/v1/credentials/approvals/{id}/approve`);
refusing (`POST .../reject`) MUST NOT. `GET /api/v1/credentials/approvals`
lists approvals, having first evaluated every current destination, and marks
superseded those nothing asks for any more.

#### Scenario: citing an existing secret from a new MCP server waits for approval
- **GIVEN** a secret an MCP server has used since before the boundary existed
- **WHEN** a second MCP server citing the same ref is registered, and a session reaches its tools
- **THEN** the second server is not spawned with the secret, the attempt answers `SECRET_BINDING_PENDING`, and one pending approval names the ref, the new server and its command line
- **AND** the first server keeps receiving the secret

#### Scenario: changing where a secret goes asks again
- **GIVEN** an MCP server whose secret is approved for its command line
- **WHEN** its command is changed to another program
- **THEN** the secret is withheld and a pending approval names the new command line
- **AND** after the approval is applied with a presence grant the server receives the secret again

#### Scenario: moving a provider connection's base URL asks again
- **GIVEN** a provider connection whose key the model proxy already receives
- **WHEN** its base URL is changed, and separately its key is replaced
- **THEN** the key is not handed to the proxy or the engine for the new URL until the approval naming that URL is applied, and the replaced key waits sealed until its own approval is applied
- **AND** once each is approved the proxy is refreshed with the key

#### Scenario: a value supplied for its destination needs no approval
- **GIVEN** a secret stored a moment ago under a ref nothing has ever received
- **WHEN** a destination citing that ref first uses it
- **THEN** the secret is injected and the binding is recorded as approved

#### Scenario: bindings in use at upgrade keep working
- **GIVEN** a vault whose resources and sync remote cite secrets before the boundary existed
- **WHEN** the daemon that has the boundary starts for the first time
- **THEN** every binding in use is approved for its current target, and starting again adopts nothing further

### Requirement: Answer a pending approval on the command line by waiting or exiting
A command that saves a change which then waits for approval — `coffer mcp add`,
every `coffer <kind> edit`, `coffer channel add`, `coffer sync remote set`,
`coffer credentials set` and `coffer config set secrets.require_approval off` —
MUST print `waiting for approval in the Coffer app` with what waits and its
approval id, and exit `9`; with `--wait` it MUST poll until the person answers,
exiting `0` once approved and non-zero once rejected. `coffer credentials
approvals` MUST list what waits (`--all` includes decided ones, `--json` for
scripts) and `coffer credentials reject <id>` MUST refuse one; no command
approves.

#### Scenario: the command line reports a pending approval and exits 9
- **GIVEN** a secret already sent to one MCP server
- **WHEN** the user registers another server citing it with `coffer mcp add`
- **THEN** the server is registered, the command prints "waiting for approval in the Coffer app" naming the approval, and exits `9`
- **AND** `coffer credentials approvals` lists that approval

#### Scenario: the command line waits for the approval with --wait
- **GIVEN** a command run with `--wait` whose change waits for approval
- **WHEN** the approval is applied in the desktop app
- **THEN** the command reports it approved and exits `0`

### Requirement: Hold a replaced value in use until a person approves it
`POST /api/v1/credentials` on a ref an approved destination receives, or on a
standalone `secret/` name, MUST NOT replace the value: it MUST answer `202` with
a pending `replace_value` approval and keep the new value only as ciphertext
until the approval is applied, and drop it when the approval is decided either
way. Writing a new ref, or one nothing receives, MUST store it at once (`204`).

#### Scenario: replacing a value in use waits for approval
- **GIVEN** a secret an approved MCP server receives
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `202` naming a pending approval, the store still holds the old value, and nothing in the database holds the new value in plaintext
- **AND** applying the approval with a presence grant replaces the value

### Requirement: Turn the protection off only through the desktop app
`secrets.require_approval` (`GET|PUT /api/v1/settings/secret-boundary`) MUST
switch on at once and MUST switch off only through a pending
`disable_protection` approval applied with a presence grant; no environment
variable, config file or CLI flag switches it off.

#### Scenario: switching the protection off waits for the desktop app
- **GIVEN** the protection is on
- **WHEN** `coffer config set secrets.require_approval off` runs
- **THEN** it exits `9` waiting for approval and the protection stays on
- **AND** once the approval is applied with a presence grant a new destination is approved without asking

### Requirement: Resolve standalone secrets into one child with coffer run
A standalone secret MUST live in the store under `secret/<name>`, where `<name>`
is one segment of `[A-Za-z0-9_.-]` of at most 64 characters, and MUST be cited
from files as `coffer://secret/<name>`
([Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)).
`coffer run [--secret NAME|ENV=NAME]… [--env-file FILE] [--no-masking] -- cmd
args…` MUST resolve every named secret, every `coffer://secret/` value in the
env file and every such value in its own environment through
`POST /api/v1/credentials/secrets/resolve`, which MUST answer standalone names
only and MUST record one `secret_resolved` entry per name carrying the name,
the program and the working directory and never the value or the rest of the
arguments. The values MUST be set only in the child's environment; the child's
standard output and error MUST have every exact value of eight characters or
more replaced by `***`, including a value split across two reads, unless
`--no-masking` is given; the child's exit status MUST pass through. The docs
MUST say that this guards against accidents and does not hide a secret from an
agent that runs the command.

#### Scenario: coffer run sets a secret only in the child
- **GIVEN** a standalone secret `db-password`
- **WHEN** `coffer run --secret db-password -- <cmd>` runs a command that reports whether `DB_PASSWORD` is set
- **THEN** the child sees the value in `DB_PASSWORD` while the calling process's environment does not change
- **AND** one `secret_resolved` entry names `db-password` and the program and does not contain the value

#### Scenario: coffer run masks the value in the child's output
- **GIVEN** a standalone secret whose value the child prints, split across two writes
- **WHEN** it runs under `coffer run`
- **THEN** the output shows `***` where the value was and never the value

#### Scenario: a resource's secret cannot be resolved by coffer run
- **GIVEN** an MCP server's token stored under its minted ref
- **WHEN** a resolve names that ref or any name that is not a stored standalone secret
- **THEN** it is refused and no value is returned

### Requirement: List every stored and cited secret with what uses it
`coffer credentials list` and `GET /api/v1/credentials` MUST list every ref the
store holds and every ref a registered resource cites, each with whether the
store holds it, the resources that cite it, for a standalone secret its
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
- **WHEN** the user runs `coffer credentials list`
- **THEN** both refs are listed
- **AND** the MCP server's ref is shown as present and the provider's ref as missing

#### Scenario: a secret nothing references is listed as unreferenced
- **GIVEN** a standalone secret no resource and no skill cites, and another that a skill cites by URI
- **WHEN** the credentials are listed
- **THEN** the first is marked unreferenced and readable by local processes
- **AND** the second names the skill, and deleting it is refused naming that skill

### Requirement: Move plaintext secret files into the store
`POST /api/v1/credentials/scan` (`coffer credentials scan`) MUST report every
plaintext secret in `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json`
(a flat map of strings) and in the skill master store (assignments whose name
says password, secret, token or key, and well-known token shapes) by file,
line, key and proposed name, and every skill that still mentions
`~/.coffer/secrets/`; it MUST NOT return a value. `POST
/api/v1/credentials/import` (`coffer credentials import [--id]… [--dry-run]`)
MUST store each chosen value as `secret/<proposed name>`, confirm the store
reads back the same value, and only then replace the value in its file with the
reference, atomically and keeping the file's mode; a name already holding a
different value MUST be skipped with its file untouched; `--dry-run` writes
nothing. Each move MUST be audited as `secret_imported` without the value.

#### Scenario: a scan names plaintext secrets without their values
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script assigns a token
- **WHEN** the scan runs
- **THEN** both are reported with their file, key and proposed name, and the response contains neither value

#### Scenario: importing moves a value and leaves a reference
- **GIVEN** those findings
- **WHEN** they are imported
- **THEN** each value reads back from the store under its standalone name, each file now cites `coffer://secret/<name>` in place of the value with its mode unchanged, and a dry run beforehand changed nothing

### Requirement: Keep the master key behind a storage port chosen by the build
Where the master key lives MUST be decided by how the build was made, never by
a setting or an environment variable. A signed release stamped with Coffer's
Keychain access group MUST keep the key only in one data-protection Keychain
item in that group (service `coffer`, account `master-key`) with no
user-presence flag, so the daemon reads it unattended; at its first start it
MUST move a key found in the key file or the legacy keychain item into that
item — writing it, reading it back and comparing before deleting the source —
audited as `master_key_relocated`, MUST stop the start naming both fingerprints
when the two disagree, and MUST refuse to relocate the key back to a file. A
build without the stamp is a development build: it keeps the arrangement of
"Keep the master key in exactly one place", and reports itself as development
(see "Release plaintext only to a present human in the desktop app").

#### Scenario: a signed build moves a file key into its access group
- **GIVEN** a signed build's Keychain item that is empty and a master key in the key file
- **WHEN** the key is resolved
- **THEN** the item holds the key, the file is gone, and the manager reports the access group as the key's location
- **AND** a later request to relocate the key to the file is refused

#### Scenario: the access-group item carries no presence flag
- **GIVEN** the access-group backend
- **WHEN** it writes and reads the master key
- **THEN** every query names the data-protection keychain and Coffer's access group, and none carries an access-control (presence) flag

## MODIFIED Requirements

### Requirement: Store a credential through the API
`POST /api/v1/credentials` MUST store `{ref, value}`, answer `204`, and record a `credential_set`
audit entry carrying the ref only — except when the ref's value is in use, when it MUST answer
`202` with a pending approval instead (see "Hold a replaced value in use until a person approves
it").

#### Scenario: storing a credential answers 204 and audits the ref only
- **GIVEN** a running daemon
- **WHEN** the user posts `{ref, value}` to `/api/v1/credentials`
- **THEN** the response is `204` and the ref reads back present
- **AND** a `credential_set` audit entry names the ref and does not contain the value

### Requirement: Keep the master key in exactly one place
In a development build the Fernet master key MUST live in exactly one of two places: a `0600`
file beside the database (the default) or the OS keychain (opt-in); a signed release keeps it in
its Keychain access group instead (see "Keep the master key behind a storage port chosen by the
build"). It MUST NOT exist in two places as a system of record. The master key is the single
piece of secret material outside the database and is never copied into anything the vault
publishes. A read that needs the keychain and cannot have it MUST fail with a locked condition
rather than a missing one.

#### Scenario: the master key lives in the file or the keychain, never both
- **GIVEN** a master key stored in the `0600` file beside the database
- **WHEN** the key is relocated to the OS keychain and then back to the file
- **THEN** after the first move the keychain holds the key and the file no longer exists
- **AND** after the second move the file holds the same key with mode `0600` and the keychain entry is gone

### Requirement: Keep secret values out of credential audit events
The events `credential_set`, `credential_revealed`, `credential_deleted`, `credential_migrated`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported` and the
`secret_approval_*` events MUST carry the ref, the name or the destination only. An audit payload
MUST NOT carry a secret value, and a new credential event that does MUST NOT be added.

#### Scenario: credential audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a credential is stored and deleted through the API
- **THEN** the `credential_set` and `credential_deleted` entries each carry the ref
- **AND** none of those entries contains the secret value anywhere in its payload

## REMOVED Requirements

### Requirement: Audit every read of a secret value
**Reason**: An audit is not a refusal: an agent holding the daemon's token read any secret through this route and the log recorded the theft afterwards.
**Migration**: No route returns a value ("Return no plaintext on any route, command or tool"). A person sees a value in the desktop app ("Release plaintext only to a present human in the desktop app"), audited as `credential_revealed`.

### Requirement: Redact a secret on the command line unless asked
**Reason**: `--show` printed the value to whoever ran the command, agents included.
**Migration**: `coffer credentials get <ref>` checks presence only ("Check a secret's presence on the command line"); reveal the value in the desktop app.

### Requirement: List every cited reference with its presence
**Reason**: It listed only refs a resource cites, so a stored secret nothing cited was invisible and could not be cleaned up.
**Migration**: Replaced by "List every stored and cited secret with what uses it", which keeps this listing and adds stored refs, skill references, unreferenced and destinations.
