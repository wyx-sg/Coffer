## ADDED Requirements

### Requirement: Store every secret only as a ciphertext file
The system MUST persist every secret only as Fernet ciphertext
([Envelope-Encrypted Credential Store](../../../docs/decisions/envelope-encrypted-credential-store.md)),
one file per ref: `~/.coffer/vault/secret/<ref>.enc`, or `~/.coffer/local/secret/<ref>.enc` for a
ref that is true of this machine only, such as a model-proxy token
([vault-storage](../vault-storage/spec.md) "Keep secret ciphertext as one file per reference").
Secret plaintext MUST NOT be written to any file, the history database, any log file, any audit
entry, or any structured event. A file holds the ciphertext and nothing else, because anything
else would be a place for the secret to leak: the ref is its name, its update time is the
token's own encryption time, and when this machine first stored it is a machine-local record
beside the boundary's (see "Keep the boundary's bindings, approvals and switch on this machine").

#### Scenario: a stored secret is only ciphertext in its file
- **GIVEN** an empty secret store
- **WHEN** a secret is stored under a ref
- **THEN** the ref's file under `vault/secret/` holds the Fernet token and a trailing newline, which do not contain the secret's plaintext
- **AND** those bytes decrypt with the master key back to the secret, and no file under `~/.coffer` holds the plaintext

### Requirement: Keep the boundary's bindings, approvals and switch on this machine
The secret boundary's state MUST be files of this machine, under `~/.coffer/local/secret-boundary/`:
`bindings.json` (which destination and target each ref is approved for), `approvals.json` (the
approvals asked and answered, a pending replacement's sealed value with them), `settings.json` (the
`require_approval` switch), `times.json` (when this machine first stored each ref) and
`last-used.json` (when a consumer last had each ref decrypted here). Each MUST be written
atomically with mode `0600`, and none of them MUST ever be written into the vault or travel with
sync: an approval is a person's answer on this machine, given with a presence grant here, and a
second machine decides for itself which targets receive its values. A ref that arrived from
another machine by sync therefore has no creation time here, and MUST NOT be counted as a value a
person here has just supplied (see "Hold a secret for a new destination until a person approves it").

#### Scenario: the boundary's state is machine-local files
- **GIVEN** an empty home
- **WHEN** a binding is approved, an approval is asked and the protection switch is set
- **THEN** `bindings.json`, `approvals.json` and `settings.json` exist under `~/.coffer/local/secret-boundary/`, each with mode `0600`
- **AND** nothing was written into the vault

## MODIFIED Requirements

### Requirement: Address a secret by an opaque reference
A secret MUST be addressed by an opaque reference — a slash-separated string of `[A-Za-z0-9_.-]`
segments — which carries no meaning to the store. A write to an existing ref MUST re-encrypt in
place rather than create a second file, so rotating a secret needs no change anywhere that cites it.
When two writes reach the same ref, the later write wins, and the ref keeps its creation time.

#### Scenario: writing an existing ref re-encrypts it in place
- **GIVEN** a secret stored under a ref
- **WHEN** a second value is written under the same ref
- **THEN** the store still holds exactly one file for that ref, which now decrypts to the second value
- **AND** the ref keeps its original creation time

### Requirement: Keep blocking store calls off the event loop
The store's blocking methods MUST NOT be called on the event loop; every async caller MUST go
through the store's own `a*` facade or an explicit worker thread. The store is a blocking
writer: a store write waits for the vault's one write lock and commits with git, and on the loop
that wait blocks the coroutine holding the lock, so the wait can only ever time out.

#### Scenario: an async caller reaches the store through its async facade
- **GIVEN** a secret store used from a coroutine running on the event loop
- **WHEN** the coroutine stores, reads, probes and deletes a secret through the store's `a*` methods
- **THEN** each blocking store call runs on a worker thread rather than on the event loop's thread
- **AND** each operation completes with the same result the blocking method gives

### Requirement: Resolve the master key file-first and create it only for an empty store
Key resolution MUST read the file first and the keychain second, and MUST create a new key only
while the store holds no ciphertext file. It MUST also never create a key while the keychain cannot be read —
locked, or its unlock prompt dismissed: the key may be there (it is opted into with a relocation),
and a new file key would shadow it on every later start because the file is read first. The
daemon then refuses to start with `SECRET_LOCKED`, naming the key file it looked for and
saying to unlock the keychain, and writes nothing. A host with no keychain backend at all holds
nothing there, so it is treated as an empty keychain. Resolution order is what makes an interrupted relocation
recoverable; the creation rule is what stops a fresh key silently orphaning existing ciphertext.

#### Scenario: the master key is never regenerated over existing ciphertext
- **GIVEN** a vault holding at least one ciphertext file and whose master key is absent from both the file location and the keychain,
- **WHEN** the daemon starts,
- **THEN** it refuses to start with `MASTER_KEY_MISSING` naming the expected key path,
- **AND** no new key is written, so restoring the original key restores access.

#### Scenario: a locked keychain at start creates no key
- **GIVEN** a vault holding no ciphertext file, no key file, and an OS keychain that raises "locked" on every read
- **WHEN** the daemon starts
- **THEN** it refuses to start with `SECRET_LOCKED`, naming the expected key path and saying to unlock the keychain
- **AND** no key file is written, so the keychain's key is the one read once it is unlocked

### Requirement: Refuse to start when the master key is missing
A key that is absent or unusable while ciphertext exists MUST be a fatal `MASTER_KEY_MISSING` naming
the expected path, and the daemon MUST NOT start. It MUST NOT write a replacement key over live
ciphertext under any condition. Restoring the original key MUST restore access to every previously
stored secret. Because an empty store gets a key at its first start and a store with
ciphertext does not start without one, a running daemon always holds a master key; a machine can
be without one only when the key disappears while the daemon runs, which is the case
[vault-sync](../vault-sync/spec.md) "Report the refs a key cannot open as locked" covers.

#### Scenario: a missing master key is a named, fatal startup failure
- **GIVEN** a key file that exists but is truncated or corrupt, beside ciphertext,
- **WHEN** the daemon starts,
- **THEN** it fails with `MASTER_KEY_MISSING` naming the path rather than starting with a key that opens nothing.

### Requirement: Delete a secret idempotently
`DELETE /api/v1/secrets/{ref}` MUST be idempotent, answer `204` whether or not the ref was
present, and record a `secret_deleted` audit entry when it removed something.

#### Scenario: delete a secret frees the reference
- **GIVEN** a secret `{ref}` exists and is cited by zero MCP servers,
- **WHEN** the user issues `DELETE /api/v1/secrets/{ref}` (or the equivalent CLI),
- **THEN** the ciphertext file is removed, the deletion is audited, and a later registration may reuse `{ref}` without conflict.

### Requirement: Refuse to delete a secret still in use
The delete MUST be refused with `409 SECRET_IN_USE` while any registered resource's
configuration still cites the ref, and the error MUST name every citing resource by kind and current
name, so the user knows exactly what to detach first; it MUST NOT identify them by uid, which is the
identity the system keeps across a rename and not something the user can recognise on a page
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
A Coffer-initiated delete MUST NOT leave any resource citing a reference the store does not hold.

#### Scenario: a secret in use cannot be deleted
- **GIVEN** a stored secret whose ref is cited by at least one registered resource,
- **WHEN** the user deletes it,
- **THEN** the request is refused with `409 SECRET_IN_USE`, the message names every citing resource as its kind plus its current name (`channel 'my-bot'`, `mcp_server 'github'`) rather than as a uid — the user has to go and find the thing, and an opaque identity is not what the page they go to shows them, and the ciphertext file is still present afterwards.

### Requirement: Carry references, never secrets, in resource configuration
A resource's configuration MUST carry secret references and never secret values. Each kind
declares how its refs are extracted from its own config shape; a kind that declares no extractor
cites no secrets and is never probed. A reference is resolved only at the moment of use.

#### Scenario: store and reference a secret
- **GIVEN** the user has not yet stored an HTTP secret,
- **WHEN** the user issues `POST /api/v1/secrets` (or the equivalent CLI) with `ref` and the secret `value` in the request body, then registers an HTTP MCP server whose `secret_refs` cites `{ref}`,
- **THEN** the secret value is written only as Fernet ciphertext in its file under `vault/secret/` (its plaintext never reaches any file, the history database, any log, or the audit), and the server registration succeeds with the secret resolved (decrypted) at upstream-spawn time.

### Requirement: Hold plaintext only in memory at the moment of use
Plaintext MUST exist only in memory, between the decrypt that produces it and the process spawn or
header injection that consumes it. It MUST NOT be held longer, and it MUST NOT be written anywhere:
no secret value may appear in any file under `~/.coffer`, database table, log file, audit entry
or invocation record.

#### Scenario: secrets never leak to logs or audit
- **GIVEN** an MCP server registered with a secret reference,
- **WHEN** the server is spawned, exercised, and torn down through one representative session,
- **THEN** an automated scan of every file under `~/.coffer` — the vault, `local/`, the history database, and every log file under `~/.coffer/logs/` — and of every database row, audit entry and invocation record reveals zero occurrences of the secret's literal value.

## REMOVED Requirements

### Requirement: Store secrets only as ciphertext
**Reason**: A secret is no longer a row of a `secrets` table: its ciphertext is a file of its own, and that file is what is stored.
**Migration**: "Store every secret only as a ciphertext file".
