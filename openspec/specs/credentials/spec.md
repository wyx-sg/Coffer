# Credentials

## Purpose
Credentials is the encrypted credential store: the ciphertext, the master key that opens it, the
routes and commands that manage both, and the rule that every other capability carries a reference
rather than a secret. Every kind Coffer manages eventually needs a secret — an HTTP MCP server's
bearer token, a channel bot's token, a provider's API key — and none of them may hold one. This is
the single place a secret is written, read and destroyed, so that "Coffer never persists a plaintext
secret" is one claim to verify rather than one per kind. A developer types each secret once, has it
stored encrypted, and every configuration that needs it holds only a name — so exporting a config,
reading the audit log or sending a bug report can never leak it. The whole lifecycle — store, cite
from a resource of any kind that declares credentials, rotate, delete, move the master key — works
from the terminal with no daemon restart, which is what lets setup on a new machine be scripted from
a password manager.

It is also the **secret boundary** against the agents Coffer serves
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)):
no route or command returns a value; a value reaches only a present human in the desktop app, and
a secret goes to a destination it did not go to before only after that human approves it there.

The capability ships no web page of its own and still satisfies the End-to-End Deliverable Rule: it
delivers a complete CLI (`coffer credentials set|get|list|rm|approvals|reject|scan|import`,
`coffer run`, plus the `credentials.storage` and `secrets.require_approval` keys of `coffer config`)
and a complete route family (`/api/v1/credentials/*` plus `/api/v1/settings/credentials` and
`/api/v1/settings/secret-boundary`) over its own tables. Approving, revealing and writing a key
backup have no CLI counterpart on purpose: each needs the desktop app's presence check, and the
CLI names the app instead. Its only
visual surface is Settings → Security, the master key's card; the secret fields themselves live in
other capabilities' dialogs, because a secret is entered where the thing that needs it is
configured. Token authentication and loopback-only binding on these routes are the daemon's rule,
not this capability's. Carrying ciphertext and the master key to another machine is vault-sync's:
this capability owns where the key lives on this machine, not how a user carries it to the next.
The product-wide invariants (ciphertext-only storage, the sole key manager, where the key lives,
`keyring` confinement, references everywhere else) are also stated in `docs-site/architecture/principles.md`;
this is where they become operable behaviour with routes, commands and tests.

The store is not a password manager: it has no sharing model, no expiry, no per-agent scope and no
notion of a secret for something Coffer does not manage. The master key can be moved but not
rotated; re-encrypting every row under a new key is not offered, and a user who needs a new key
re-enters their secrets.

## Requirements

### Requirement: Store secrets only as ciphertext
The system MUST persist every secret only as Fernet ciphertext in the `credentials` table
([Envelope-Encrypted Credential Store](../../../docs/decisions/envelope-encrypted-credential-store.md)).
Secret plaintext MUST NOT be written to the database, any log file, any audit entry, or any
structured event. A stored credential records its ref, its ciphertext and its creation and update
timestamps, and nothing else, because anything else would be a place for the secret to leak.

#### Scenario: a stored secret is only ciphertext in the credentials table
- **GIVEN** an empty credential store
- **WHEN** a secret is stored under a ref
- **THEN** the `credentials` row for that ref holds bytes that do not contain the secret's plaintext
- **AND** those bytes decrypt with the master key back to the secret

### Requirement: Address a secret by an opaque reference
A secret MUST be addressed by an opaque reference — a slash-separated string of `[A-Za-z0-9_.-]`
segments — which carries no meaning to the store. A write to an existing ref MUST re-encrypt in
place rather than create a second row, so rotating a secret needs no change anywhere that cites it.
When two writes reach the same ref, the later write wins, and the row keeps its creation time.

#### Scenario: writing an existing ref re-encrypts it in place
- **GIVEN** a credential stored under a ref
- **WHEN** a second value is written under the same ref
- **THEN** the store still holds exactly one row for that ref, which now decrypts to the second value
- **AND** the row keeps its original creation time

### Requirement: Report undecryptable ciphertext as unreadable
A stored ciphertext that will not decrypt with the current master key MUST raise
`CREDENTIAL_UNREADABLE` naming the ref, never a not-found — "absent" would invite the user to
re-register rather than to restore the right key. The presence probe MUST answer from the row's
existence alone, so a corrupt entry still reports present and cannot be mistaken for one that was
never stored.

#### Scenario: an unreadable ciphertext names its ref
- **GIVEN** a stored credential whose ciphertext cannot be decrypted with the current master key,
- **WHEN** something reads that ref,
- **THEN** the failure is `CREDENTIAL_UNREADABLE` naming the ref rather than a not-found,
- **AND** the presence probe still reports the ref as present, because it never decrypts.

### Requirement: Keep blocking store calls off the event loop
The store's blocking methods MUST NOT be called on the event loop; every async caller MUST go
through the store's own `a*` facade or an explicit worker thread. The store is a blocking SQLite
writer: a store write busy-waits on SQLite's lock, and on the loop that wait blocks the coroutine
holding the lock, so the wait can only ever time out.

#### Scenario: an async caller reaches the store through its async facade
- **GIVEN** a credential store used from a coroutine running on the event loop
- **WHEN** the coroutine stores, reads, probes and deletes a credential through the store's `a*` methods
- **THEN** each blocking store call runs on a worker thread rather than on the event loop's thread
- **AND** each operation completes with the same result the blocking method gives

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

### Requirement: Confine key management to the credentials package
Only this capability's `infrastructure/credentials/` package MAY manage the master key, and only its
keyring adapter MAY import `keyring`. Any other module — a surface, another kind, or a CLI
command — MUST NOT reach the keychain.

#### Scenario: only the keyring adapter imports keyring
- **GIVEN** the backend source tree
- **WHEN** every module is scanned for imports of `keyring`
- **THEN** the only module that imports it is the keyring adapter in `infrastructure/credentials/`

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

### Requirement: Verify the destination before relocating the master key
Relocating the key MUST write and verify the destination copy before removing the source, so an
interruption resolves back to the source location with a harmless duplicate rather than to no key
at all. Moving the key between the file and the OS keychain MUST leave every stored secret
readable, in both directions, across a daemon restart.

#### Scenario: relocating the master key verifies the destination before removing the source
- **GIVEN** the master key is stored in the `0600` file beside the database,
- **WHEN** the user moves it to the OS keychain,
- **THEN** the keychain copy is written and read back before the file is removed, the move is audited as `master_key_relocated`, and an interruption anywhere in between leaves the key resolvable from the file.

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

### Requirement: Probe presence without decrypting or auditing
`GET /api/v1/credentials/{ref}/exists` MUST report presence without decrypting, and MUST NOT audit.
It is the probe a surface uses when it needs to know whether to ask the user for a value, which is
not an access to the secret.

#### Scenario: the presence probe records no audit entry
- **GIVEN** a stored credential and a ref that was never stored
- **WHEN** both are probed with `GET /api/v1/credentials/{ref}/exists`
- **THEN** the first reports present and the second reports absent
- **AND** neither probe adds an entry to the audit log

### Requirement: Delete a credential idempotently
`DELETE /api/v1/credentials/{ref}` MUST be idempotent, answer `204` whether or not the ref was
present, and record a `credential_deleted` audit entry when it removed something.

#### Scenario: delete a credential frees the reference
- **GIVEN** a credential `{ref}` exists and is cited by zero MCP servers,
- **WHEN** the user issues `DELETE /api/v1/credentials/{ref}` (or the equivalent CLI),
- **THEN** the ciphertext row is removed, the deletion is audited, and a later registration may reuse `{ref}` without conflict.

### Requirement: Refuse to delete a credential still in use
The delete MUST be refused with `409 CREDENTIAL_IN_USE` while any registered resource's
configuration still cites the ref, and the error MUST name every citing resource by kind and current
name, so the user knows exactly what to detach first; it MUST NOT identify them by uid, which is the
identity the system keeps across a rename and not something the user can recognise on a page
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
A Coffer-initiated delete MUST NOT leave any resource citing a reference the store does not hold.

#### Scenario: a credential in use cannot be deleted
- **GIVEN** a stored credential whose ref is cited by at least one registered resource,
- **WHEN** the user deletes it,
- **THEN** the request is refused with `409 CREDENTIAL_IN_USE`, the message names every citing resource as its kind plus its current name (`channel 'my-bot'`, `mcp_server 'github'`) rather than as a uid — the user has to go and find the thing, and an opaque identity is not what the page they go to shows them, and the ciphertext row is still present afterwards.

### Requirement: Read a secret on the command line without shell history
`coffer credentials set <ref>` MUST take the secret from standard input, or from a hidden prompt on
a terminal, MUST reject an empty value with a non-zero exit, and MUST document `--value` as unsafe
because it lands in shell history.

#### Scenario: the command line stores a secret without it reaching shell history
- **GIVEN** a terminal,
- **WHEN** the user pipes a secret into `coffer credentials set <ref>`, or is prompted for it with the input hidden,
- **THEN** the secret is stored, an empty value is rejected with a non-zero exit, and passing `--value` instead prints an explicit warning that the value lands in shell history.

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

### Requirement: Carry references, never secrets, in resource configuration
A resource's configuration MUST carry credential references and never secret values. Each kind
declares how its refs are extracted from its own config shape; a kind that declares no extractor
cites no credentials and is never probed. A reference is resolved only at the moment of use.

#### Scenario: store and reference a credential
- **GIVEN** the user has not yet stored an HTTP credential,
- **WHEN** the user issues `POST /api/v1/credentials` (or the equivalent CLI) with `ref` and the secret `value` in the request body, then registers an HTTP MCP server whose `credential_refs` cites `{ref}`,
- **THEN** the credential value is written only as Fernet ciphertext in the `credentials` table (its plaintext never reaches the SQLite DB, any log, or the audit), and the server registration succeeds with the credential resolved (decrypted) at upstream-spawn time.

### Requirement: Store a pasted secret before persisting its reference
Any surface that accepts a pasted or typed secret MUST write it into the store first and persist
only the resulting ref, so the secret never reaches a resource config even transiently.

#### Scenario: a surface lifts a pasted secret into the store before registering
- **GIVEN** a user pastes an MCP server definition, or fills a channel's token field, in the web UI,
- **WHEN** the resource is registered,
- **THEN** the secret was written to the credential store first and the persisted resource config carries only the ref.

### Requirement: Remove a credential written for a failed registration
A credential written for a registration that then fails MUST be removed again, so a failed attempt
leaves no entry nothing cites.

#### Scenario: a failed registration leaves no orphaned credential
- **GIVEN** a registration dialog into which the user pasted a secret,
- **WHEN** the secret is written to the store and the registration that follows it fails,
- **THEN** the just-written credential is deleted again, so the store holds no entry that nothing cites.

### Requirement: Release unshared references when a resource is deleted
Deleting a resource MUST release the credential refs that nothing else cites, recording each
release. A failed release MUST NOT turn the already-completed deletion into an error — the
credential lingers, which is the status quo, rather than the deletion appearing to have failed.

#### Scenario: deleting a resource releases the credentials nothing else cites
- **GIVEN** a registered resource citing two credential refs, one of which a second resource also cites,
- **WHEN** the first resource is deleted,
- **THEN** the ref nothing else cites is removed from the store and audited, the shared ref is kept, and a failure to release either one does not fail the deletion.

### Requirement: Hold plaintext only in memory at the moment of use
Plaintext MUST exist only in memory, between the decrypt that produces it and the process spawn or
header injection that consumes it. It MUST NOT be held longer, and it MUST NOT be written anywhere:
no secret value may appear in any database table, log file, audit entry or invocation record.

#### Scenario: credentials never leak to logs or audit
- **GIVEN** an MCP server registered with a credential reference,
- **WHEN** the server is spawned, exercised, and torn down through one representative session,
- **THEN** an automated scan of every database row, audit entry, invocation record, and log file under `~/.coffer/logs/` reveals zero occurrences of the credential's literal value.

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

### Requirement: Migrate legacy keychain secrets once at startup
At startup the daemon MUST move any pre-0.2 OS-keychain secret into the encrypted store, for cited
refs only, auditing each move as `credential_migrated`. It MUST NOT enumerate the keychain, MUST be a
no-op once every cited ref is in the store, and MUST NOT block startup on failure — a locked keychain
skips that ref and is retried on the next start. This load-time shim is kept deliberately, against
the rule that a migration leaves no shim behind: its source is the user's OS keychain rather than a
column, so no data migration can replace it, and it cannot be proven finished on an install nobody
has started yet. It is retired when the pre-0.2 install base is.

#### Scenario: a legacy keychain secret migrates once and then does nothing
- **GIVEN** a pre-0.2 vault whose OS keychain still holds a secret for a ref a registered resource cites, and whose store does not,
- **WHEN** the daemon starts,
- **THEN** the secret is moved into the encrypted store and audited as `credential_migrated`,
- **AND** a second start moves nothing, reads no keychain entry for any already-stored ref, and a locked keychain leaves startup unaffected.

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
every `coffer <kind> edit` (including `coffer provider edit` with `--secret` or
`--base-url`), `coffer channel add`, `coffer provider add`, `coffer sync remote
set`, `coffer credentials set` and `coffer config set secrets.require_approval
off` — MUST print `waiting for approval in the Coffer app` with what waits and
its approval id, and exit `9`; with `--wait` it MUST poll until the person
answers, exiting `0` once approved and non-zero once rejected. What a change to
a destination waits on includes a pending replacement of the value of a secret
that destination cites, not only a pending binding to it. `coffer credentials
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

#### Scenario: the command line reports a pending provider key and exits 9
- **GIVEN** a provider connection whose key is in use
- **WHEN** the user runs `coffer provider edit` with a new `--secret`, then with a new `--base-url`, and then `coffer provider add` for a second connection citing the same key with `--credential-ref`
- **THEN** each change is saved, and each command prints "waiting for approval in the Coffer app" naming its approval and exits `9`, while the stored key keeps its old value
- **AND** a `coffer provider edit` that changes only the description exits `0`

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
