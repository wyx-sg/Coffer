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

The capability ships no web page of its own and still satisfies the End-to-End Deliverable Rule: it
delivers a complete CLI (`coffer credentials set|get|list|delete|storage`) and a complete route
family (`/api/v1/credentials/*` plus `/api/v1/settings/credentials`) over its own table. Its only
visual surface is Settings → Security, the master key's card; the secret fields themselves live in
other capabilities' dialogs, because a secret is entered where the thing that needs it is
configured. Token authentication and loopback-only binding on these routes are the daemon's rule,
not this capability's. Carrying ciphertext and the master key to another machine is vault-sync's:
this capability owns where the key lives on this machine, not how a user carries it to the next.
The product-wide invariants (ciphertext-only storage, the sole key manager, the file-or-keychain
pair, `keyring` confinement, references everywhere else) are also stated in `docs-site/architecture/principles.md`;
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
The Fernet master key MUST live in exactly one of two places: a `0600` file beside the database (the
default) or the OS keychain (opt-in). It MUST NOT exist in both as a system of record. The master
key is the single piece of secret material outside the database and is never copied into anything
the vault publishes. A read that needs the keychain and cannot have it MUST fail with a locked
condition rather than a missing one.

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
(`GET`/`PUT /api/v1/settings/credentials`), from the CLI
(`coffer credentials storage [--set file|keychain]`), and from a Settings card that states the
consequence and confirms before it writes.

#### Scenario: read and change the master key location from the API and the command line
- **GIVEN** a running daemon whose master key is in the file beside the database
- **WHEN** the location is read with `GET /api/v1/settings/credentials` and with `coffer credentials storage`, then changed to the keychain with `PUT /api/v1/settings/credentials`
- **THEN** both reads report the file location
- **AND** after the change both surfaces report the keychain, and a previously stored secret still reads back

### Requirement: Store a credential through the API
`POST /api/v1/credentials` MUST store `{ref, value}`, answer `204`, and record a `credential_set`
audit entry carrying the ref only.

#### Scenario: storing a credential answers 204 and audits the ref only
- **GIVEN** a running daemon
- **WHEN** the user posts `{ref, value}` to `/api/v1/credentials`
- **THEN** the response is `204` and the ref reads back present
- **AND** a `credential_set` audit entry names the ref and does not contain the value

### Requirement: Audit every read of a secret value
`GET /api/v1/credentials/{ref}` MUST return the decrypted value, record a `credential_read` audit
entry carrying the ref only, and answer `404` when the ref is absent — so every deliberate read of a
secret leaves a trail.

#### Scenario: reading a credential returns its value and audits the read
- **GIVEN** a stored credential
- **WHEN** the user reads it with `GET /api/v1/credentials/{ref}`, and then reads a ref that was never stored
- **THEN** the first read returns the decrypted value and records a `credential_read` entry naming the ref and not the value
- **AND** the second read answers `404`

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

### Requirement: Redact a secret on the command line unless asked
`coffer credentials get <ref>` MUST print `[redacted]` by way of the unaudited presence probe, and
MUST fetch the real value through the audited read only when `--show` is given.

#### Scenario: the command line redacts a secret unless asked, and an asked-for read is audited
- **GIVEN** a stored credential,
- **WHEN** the user runs `coffer credentials get <ref>`, and then the same command with `--show`,
- **THEN** the first prints `[redacted]` and records no audit entry, while the second prints the value and records a `credential_read` entry carrying the ref only.

### Requirement: List every cited reference with its presence
`coffer credentials list` MUST show every credential ref cited by a registered resource of any kind,
together with whether the store currently holds it and which resources cite it, so a vault restored
without its secrets says which ones are missing; `--json` MUST carry the same presence. It reads
`GET /api/v1/credentials`, which answers `{refs: [{ref, present, cited_by: [{uid, kind, name}]}]}`,
decrypts nothing and records no audit entry.

#### Scenario: the command line lists every cited ref with its presence
- **GIVEN** a registered MCP server citing a stored ref and a registered model provider citing a ref the store does not hold
- **WHEN** the user runs `coffer credentials list`
- **THEN** both refs are listed
- **AND** the MCP server's ref is shown as present and the provider's ref as missing

### Requirement: Confirm a command-line delete unless forced
`coffer credentials delete <ref>` MUST confirm before deleting, unless `--force` is given.

#### Scenario: the command line confirms a delete unless forced
- **GIVEN** a stored credential
- **WHEN** the user runs `coffer credentials delete <ref>` and declines the confirmation, then runs it again with `--force`
- **THEN** the declined run leaves the credential stored
- **AND** the forced run deletes it without asking

### Requirement: Route every credential command through the daemon
Every credential command MUST go through the daemon's API and MUST import no credential or keyring
code of its own. The daemon is the sole owner of the key, and a CLI that opened the keychain itself
would be a second reader to keep honest.

#### Scenario: credential commands import no credential code
- **GIVEN** the `coffer credentials` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the credentials infrastructure package
- **AND** it reaches the vault only through the daemon client

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
The events `credential_set`, `credential_read`, `credential_deleted`, `credential_migrated` and
`master_key_relocated` MUST carry the ref (or the destination location) only. An audit payload MUST NOT
carry a secret value, and a new credential event that does MUST NOT be added.

#### Scenario: credential audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a credential is stored, read with its value, and deleted through the API
- **THEN** the `credential_set`, `credential_read` and `credential_deleted` entries each carry the ref
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
