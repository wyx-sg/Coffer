# Secrets

## Purpose
Secrets is the encrypted secret store: the ciphertext, the master key that opens it, the
routes and commands that manage both, and the rule that every other capability carries a reference
rather than a secret. Every kind Coffer manages eventually needs a secret — an HTTP MCP server's
bearer token, a channel bot's token, a provider's API key — and none of them may hold one. This is
the single place a secret is written, read and destroyed, so that "Coffer never persists a plaintext
secret" is one claim to verify rather than one per kind. A developer types each secret once, has it
stored encrypted, and every configuration that needs it holds only a name — so exporting a config,
reading the audit log or sending a bug report can never leak it. The whole lifecycle — store, cite
from a resource of any kind that declares secrets, rotate, delete, move the master key — works
from the terminal with no daemon restart, which is what lets setup on a new machine be scripted from
a password manager.

It is also the **secret boundary** against the agents Coffer serves
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)):
no route or command returns a value; a value reaches only a present human in the desktop app, and
a secret goes to a destination it did not go to before only after that human approves it there.

The capability ships no web page of its own and still satisfies the End-to-End Deliverable Rule: it
delivers a complete CLI (`coffer secret set|get|list|rm|approvals|reject|scan|import`,
`coffer run`, plus the `secrets.storage` and `secrets.require_approval` keys of `coffer config`)
and a complete route family (`/api/v1/secrets/*` plus `/api/v1/settings/secrets` and
`/api/v1/settings/secret-boundary`) over its own files under `local/secret-boundary/`. Approving, revealing and writing a key
backup have no CLI counterpart on purpose: each needs the desktop app's presence check, and the
CLI names the app instead. Its visual
surfaces are the Secrets page, which lists every stored and cited secret with what uses it, and
Settings → Security, the master key's card; the secret fields themselves live in
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

### Requirement: Address a secret by an opaque reference
A secret MUST be addressed by an opaque reference — a slash-separated string of `[A-Za-z0-9_.-]`
segments, none of them made only of dots (`.` and `..` name no file) — which carries no meaning to the store. A write to an existing ref MUST re-encrypt in
place rather than create a second file, so rotating a secret needs no change anywhere that cites it.
When two writes reach the same ref, the later write wins, and the ref keeps its creation time.

#### Scenario: writing an existing ref re-encrypts it in place
- **GIVEN** a secret stored under a ref
- **WHEN** a second value is written under the same ref
- **THEN** the store still holds exactly one file for that ref, which now decrypts to the second value
- **AND** the ref keeps its original creation time

#### Scenario: a dot-only segment is refused rather than answered with a server error
- **GIVEN** a running daemon
- **WHEN** a secret is stored under the ref `..` or `a/../b`, or presence is probed or a delete is asked for such a ref
- **THEN** each is refused as a validation error (`422`) and nothing is written

### Requirement: Report undecryptable ciphertext as unreadable
A stored ciphertext that will not decrypt with the current master key MUST raise
`SECRET_UNREADABLE` naming the ref, never a not-found — "absent" would invite the user to
re-register rather than to restore the right key. The presence probe MUST answer from the row's
existence alone, so a corrupt entry still reports present and cannot be mistaken for one that was
never stored.

#### Scenario: an unreadable ciphertext names its ref
- **GIVEN** a stored secret whose ciphertext cannot be decrypted with the current master key,
- **WHEN** something reads that ref,
- **THEN** the failure is `SECRET_UNREADABLE` naming the ref rather than a not-found,
- **AND** the presence probe still reports the ref as present, because it never decrypts.

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

#### Scenario: an imported master key replaces the key where it is kept
- **GIVEN** a development build whose master key is in the OS keychain
- **WHEN** a different master key is imported
- **THEN** the keychain holds the imported key and no key file appears, and the old key is backed up to a `master.key.bak-*` file instead of staying behind in the keychain

### Requirement: Confine key management to the secret package
Only this capability's `infrastructure/secret/` package MAY manage the master key, and only its
keyring adapter MAY import `keyring`. Any other module — a surface, another kind, or a CLI
command — MUST NOT reach the keychain.

#### Scenario: only the keyring adapter imports keyring
- **GIVEN** the backend source tree
- **WHEN** every module is scanned for imports of `keyring`
- **THEN** the only module that imports it is the keyring adapter in `infrastructure/secret/`

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

### Requirement: Store a secret through the API
`POST /api/v1/secrets` MUST store `{ref, value}`, answer `204`, and record a `secret_set`
audit entry carrying the ref only — except when the ref's value is in use, when it MUST answer
`202` with a pending approval instead (see "Hold a replaced value in use until a person approves
it").

#### Scenario: storing a secret answers 204 and audits the ref only
- **GIVEN** a running daemon
- **WHEN** the user posts `{ref, value}` to `/api/v1/secrets`
- **THEN** the response is `204` and the ref reads back present
- **AND** a `secret_set` audit entry names the ref and does not contain the value

### Requirement: Probe presence without decrypting or auditing
`GET /api/v1/secrets/{ref}/exists` MUST report presence without decrypting, and MUST NOT audit.
It is the probe a surface uses when it needs to know whether to ask the user for a value, which is
not an access to the secret.

#### Scenario: the presence probe records no audit entry
- **GIVEN** a stored secret and a ref that was never stored
- **WHEN** both are probed with `GET /api/v1/secrets/{ref}/exists`
- **THEN** the first reports present and the second reports absent
- **AND** neither probe adds an entry to the audit log

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
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)).
A Coffer-initiated delete MUST NOT leave any resource citing a reference the store does not hold.

#### Scenario: a secret in use cannot be deleted
- **GIVEN** a stored secret whose ref is cited by at least one registered resource,
- **WHEN** the user deletes it,
- **THEN** the request is refused with `409 SECRET_IN_USE`, the message names every citing resource as its kind plus its current name (`channel 'my-bot'`, `mcp_server 'github'`) rather than as a uid — the user has to go and find the thing, and an opaque identity is not what the page they go to shows them, and the ciphertext file is still present afterwards.

### Requirement: Read a secret on the command line without shell history
`coffer secret set <ref>` MUST take the secret from standard input, or from a hidden prompt on
a terminal, MUST reject an empty value with a non-zero exit, and MUST document `--value` as unsafe
because it lands in shell history.

#### Scenario: the command line stores a secret without it reaching shell history
- **GIVEN** a terminal,
- **WHEN** the user pipes a secret into `coffer secret set <ref>`, or is prompted for it with the input hidden,
- **THEN** the secret is stored, an empty value is rejected with a non-zero exit, and passing `--value` instead prints an explicit warning that the value lands in shell history.

### Requirement: Confirm a command-line delete unless forced
`coffer secret rm <ref>` MUST confirm before deleting, unless `--force` is given.

#### Scenario: the command line confirms a delete unless forced
- **GIVEN** a stored secret
- **WHEN** the user runs `coffer secret rm <ref>` and declines the confirmation, then runs it again with `--force`
- **THEN** the declined run leaves the secret stored
- **AND** the forced run deletes it without asking

### Requirement: Route every secret command through the daemon
Every secret command MUST go through the daemon's API and MUST import no secret or keyring
code of its own. This covers the `coffer secret` group and the `secrets.storage` setting of
`coffer config`. The daemon is the sole owner of the key, and a CLI that opened the keychain itself
would be a second reader to keep honest.

#### Scenario: secret commands import no secret code
- **GIVEN** the `coffer secret` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the secrets infrastructure package
- **AND** it reaches the vault only through the daemon client

#### Scenario: the config command reaches the master key only through the daemon
- **GIVEN** the `coffer config` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the secrets infrastructure package
- **AND** it reads and changes `secrets.storage` only through the daemon client

### Requirement: Carry references, never secrets, in resource configuration
A resource's configuration MUST carry secret references and never secret values. Each kind
declares how its refs are extracted from its own config shape; a kind that declares no extractor
cites no secrets and is never probed. A reference is resolved only at the moment of use.

#### Scenario: store and reference a secret
- **GIVEN** the user has not yet stored an HTTP secret,
- **WHEN** the user issues `POST /api/v1/secrets` (or the equivalent CLI) with `ref` and the secret `value` in the request body, then registers an HTTP MCP server whose `secret_refs` cites `{ref}`,
- **THEN** the secret value is written only as Fernet ciphertext in its file under `vault/secret/` (its plaintext never reaches any file, the history database, any log, or the audit), and the server registration succeeds with the secret resolved (decrypted) at upstream-spawn time.

### Requirement: Store a pasted secret before persisting its reference
Any surface that accepts a pasted or typed secret MUST write it into the store first and persist
only the resulting ref, so the secret never reaches a resource config even transiently.

#### Scenario: a surface lifts a pasted secret into the store before registering
- **GIVEN** a user pastes an MCP server definition, or fills a channel's token field, in the web UI,
- **WHEN** the resource is registered,
- **THEN** the secret was written to the secret store first and the persisted resource config carries only the ref.

### Requirement: Remove a secret written for a failed registration
A secret written for a registration that then fails MUST be removed again, so a failed attempt
leaves no entry nothing cites.

#### Scenario: a failed registration leaves no orphaned secret
- **GIVEN** a registration dialog into which the user pasted a secret,
- **WHEN** the secret is written to the store and the registration that follows it fails,
- **THEN** the just-written secret is deleted again, so the store holds no entry that nothing cites.

### Requirement: Release unshared references when a resource is deleted
Deleting a resource MUST release the secret refs that nothing else cites, recording each
release. A failed release MUST NOT turn the already-completed deletion into an error — the
secret lingers, which is the status quo, rather than the deletion appearing to have failed.

#### Scenario: deleting a resource releases the secrets nothing else cites
- **GIVEN** a registered resource citing two secret refs, one of which a second resource also cites,
- **WHEN** the first resource is deleted,
- **THEN** the ref nothing else cites is removed from the store and audited, the shared ref is kept, and a failure to release either one does not fail the deletion.

### Requirement: Hold plaintext only in memory at the moment of use
Plaintext MUST exist only in memory, between the decrypt that produces it and the process spawn or
header injection that consumes it. It MUST NOT be held longer, and it MUST NOT be written anywhere:
no secret value may appear in any file under `~/.coffer`, database table, log file, audit entry
or invocation record.

#### Scenario: secrets never leak to logs or audit
- **GIVEN** an MCP server registered with a secret reference,
- **WHEN** the server is spawned, exercised, and torn down through one representative session,
- **THEN** an automated scan of every file under `~/.coffer` — the vault, `local/`, the history database, and every log file under `~/.coffer/logs/` — and of every database row, audit entry and invocation record reveals zero occurrences of the secret's literal value.

### Requirement: Keep secret values out of secret audit events
The events `secret_set`, `secret_revealed`, `secret_deleted`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported` and the
`secret_approval_*` events MUST carry the ref, the name or the destination only. An audit payload
MUST NOT carry a secret value, and a new secret event that does MUST NOT be added.

#### Scenario: secret audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a secret is stored and deleted through the API
- **THEN** the `secret_set` and `secret_deleted` entries each carry the ref
- **AND** none of those entries contains the secret value anywhere in its payload

### Requirement: Return no plaintext on any route, command or tool
No management route, `coffer` command or MCP tool MUST return a secret's
plaintext or the master key, with two exceptions this spec names: the desktop
app's presence-gated reveal and key backup (see "Release plaintext only to a
present human in the desktop app"), and `coffer run`'s resolve of standalone
secrets (see "Resolve standalone secrets into one child with coffer run").
There is no `GET /api/v1/secrets/{ref}`, no `coffer secret get
--show`, no `POST /api/v1/sync/key/export` and no `coffer sync key export`.
Writing a secret stays open to every surface: a caller that supplies a value
already has it. An audit row is not a refusal — a path that returns a value is
a defect however it is audited
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

#### Scenario: no route or command hands out a stored value
- **GIVEN** a running daemon holding a secret under a ref
- **WHEN** a caller with the daemon's token asks `GET /api/v1/secrets/{ref}`, `POST /api/v1/sync/key/export`, `coffer secret get <ref> --show` and `coffer sync key export <file>`
- **THEN** each is refused as a route or command that does not exist
- **AND** no response or output carries the value or the master key

### Requirement: Check a secret's presence on the command line
`coffer secret get <ref>` MUST print `[redacted]` when the store holds the
ref and exit `4` when it does not, by way of the presence probe, which decrypts
nothing and audits nothing. It MUST offer no option that prints the value; its
help MUST name the desktop app as the place to see one.

#### Scenario: the command line confirms presence and has no way to print a value
- **GIVEN** a stored secret
- **WHEN** the user runs `coffer secret get <ref>`, and then the same command with `--show`
- **THEN** the first prints `[redacted]` and records no audit entry
- **AND** the second is refused as an unknown option and prints nothing of the value

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

### Requirement: Hold a secret for a new destination until a person approves it
A destination is a place Coffer sends a secret's plaintext: an MCP server's
environment variable or HTTP header, a channel adapter's secret, the sync
remote's push token, and — through the same service call — a provider
connection's key and a custom tool's authentication. Every consumer MUST name
the destination and the **target** that receives the value (a stdio server's
whole command line with its working directory and non-secret environment, an
HTTP URL, a git URL, a channel's platform and app) before it resolves a secret,
and MUST inject nothing into a target no person approved: the attempt answers
`SECRET_BINDING_PENDING` (409) naming the pending approvals, or
`SECRET_BINDING_REJECTED` (409) naming a refused one (nothing waits, and it
stays refused for that target until the destination changes or
`POST /api/v1/secrets/approvals/{id}/ask-again` supersedes the refusal). Citing an existing
secret from a destination that did not cite it, and changing the target of one
that did, each record a pending approval, once per target; a later target
supersedes the approval for the earlier one. A binding already approved for
its target MUST keep working. A binding is approved without a person only when
its value was supplied for it — the destination was just registered or changed,
and the ref was never bound anywhere, is not a standalone `secret/` name and
was written on this machine within the last five minutes (see "Approve a secret's binding when its
destination is registered") — or while the protection is switched off.
Approving MUST
take a presence grant (`POST /api/v1/secrets/approvals/{id}/approve`);
refusing (`POST .../reject`) MUST NOT. `GET /api/v1/secrets/approvals`
lists approvals, having first evaluated every current destination, and marks
superseded those nothing asks for any more.

#### Scenario: citing an existing secret from a new MCP server waits for approval
- **GIVEN** a secret an MCP server is already approved to receive
- **WHEN** a second MCP server citing the same ref is registered, and a session reaches its tools
- **THEN** the second server is not spawned with the secret, the attempt answers `SECRET_BINDING_PENDING`, and one pending approval names the ref, the new server and its command line
- **AND** the first server keeps receiving the secret

#### Scenario: a refused binding says it was refused and can be asked about again
- **GIVEN** a pending approval for a server's secret that a person rejects
- **WHEN** the server is next started or listed, and then the refusal is asked about again with `POST /api/v1/secrets/approvals/{id}/ask-again`
- **THEN** the first answers `SECRET_BINDING_REJECTED` (409, a refusal, not a wait) and a command that saved the server prints that it was refused and exits with the conflict code instead of `9`
- **AND** asking again supersedes the refusal, and a fresh pending approval for the same target waits for a person; a target that has changed since drops the old refusal without being asked

#### Scenario: an approval that cannot be applied stays pending
- **GIVEN** a pending replacement whose sealed value the current master key cannot open
- **WHEN** it is approved with a presence grant
- **THEN** the approval is not recorded as approved, it stays pending with its sealed value, and the old value is unchanged

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

#### Scenario: adopting an MCP entry never replaces or deletes a secret it did not create
- **GIVEN** a registered server citing a secret ref, and an agent's config entry whose adoption maps a secret key to that same ref
- **WHEN** the entry is adopted, and again under a name that is already taken
- **THEN** the first is refused with `ADOPT_SECRET_REF_EXISTS` (409), the second with the name-conflict error before any value is written, and the existing secret still holds its value and is still approved for the server citing it
- **AND** a ref that is a standalone `secret/<name>` is refused the same way

#### Scenario: a stored key goes only to the endpoint of the connection that holds it
- **GIVEN** an MCP server's token stored under a ref, and a saved provider connection whose key is another ref
- **WHEN** `POST /api/v1/models/list-models` or `/test-connection` is sent that ref with a base URL no saved connection holds it for, or a ref no connection holds
- **THEN** each is refused as a validation error before anything is decrypted or sent, whatever protocol the request names, while an inline typed key and a saved connection's own ref and base URL work as before

#### Scenario: a value supplied for its destination needs no approval
- **GIVEN** a secret stored under a ref nothing has ever received
- **WHEN** a destination citing that ref is registered
- **THEN** the binding is recorded as approved with the registration, and the secret is injected when the destination first uses it

### Requirement: Approve a secret's binding when its destination is registered
The secret boundary MUST be applied when a destination is **registered or changed**, not only at its first use. Every resource kind that sends a secret somewhere — an MCP server, a channel, a provider connection — MUST go through one post-register seam that the resource service runs after every create and every configuration change, whichever surface made it; the sync remote, which is not a resource, MUST run the same evaluation when its remote is set or checked. The seam MUST evaluate the destination the kind declares against the boundary at that moment: a value **supplied for the destination** — a ref never bound anywhere, not a standalone `secret/` name, and written on this machine within the last five minutes — MUST be approved and its binding recorded within the registration, so a later destination citing the same ref is a second destination and waits, however soon it comes; a ref already in use elsewhere, or a target that moved, MUST record its pending approval within the same call, so the approval is on the list and shown where the resource was saved rather than at the first spawn. A binding met only at the moment of use — a spawn, an adapter start, a push, a listing — MUST never count as supplied. A failure of the seam MUST NOT undo the registration, and the binding is evaluated again at every use.

#### Scenario: a destination registered with a stored secret is settled at once
- **GIVEN** a secret stored under a ref nothing has ever received
- **WHEN** an MCP server citing it is registered, and then a second server citing the same ref is registered
- **THEN** the first server's binding is approved by its registration, with no approval to answer
- **AND** the second server's registration records one pending approval naming the ref and its command line, so a second destination cannot borrow a value supplied for the first

#### Scenario: a target change waits where it is saved
- **GIVEN** an MCP server whose secret is approved for its command line
- **WHEN** its command is changed and saved
- **THEN** the pending approval naming the new command line exists as soon as the save answers, before any spawn or listing

### Requirement: Answer a pending approval on the command line by waiting or exiting
A command that saves a change which then waits for approval — `coffer mcp add`,
every `coffer <kind> edit` (including `coffer provider edit` with `--secret` or
`--base-url`), `coffer channel add`, `coffer provider add`, `coffer sync remote
set`, `coffer secret set` and `coffer config set secrets.require_approval
off` — MUST print `waiting for approval in the Coffer app` with what waits and
its approval id, and exit `9`; with `--wait` it MUST poll until the person
answers, exiting `0` once approved and non-zero once rejected. What a change to
a destination waits on includes a pending replacement of the value of a secret
that destination cites, not only a pending binding to it. `coffer secret
approvals` MUST list what waits (`--all` includes decided ones, `--json` for
scripts) and `coffer secret reject <id>` MUST refuse one; no command
approves.

#### Scenario: the command line reports a pending approval and exits 9
- **GIVEN** a secret already sent to one MCP server
- **WHEN** the user registers another server citing it with `coffer mcp add`
- **THEN** the server is registered, the command prints "waiting for approval in the Coffer app" naming the approval, and exits `9`
- **AND** `coffer secret approvals` lists that approval

#### Scenario: the command line waits for the approval with --wait
- **GIVEN** a command run with `--wait` whose change waits for approval
- **WHEN** the approval is applied in the desktop app
- **THEN** the command reports it approved and exits `0`

#### Scenario: the command line reports a pending provider key and exits 9
- **GIVEN** a provider connection whose key is in use
- **WHEN** the user runs `coffer provider edit` with a new `--secret`, then with a new `--base-url`, and then `coffer provider add` for a second connection citing the same key with `--secret-ref`
- **THEN** each change is saved, and each command prints "waiting for approval in the Coffer app" naming its approval and exits `9`, while the stored key keeps its old value
- **AND** a `coffer provider edit` that changes only the description exits `0`

### Requirement: Hold a replaced value in use until a person approves it
`POST /api/v1/secrets` on a ref an approved destination receives, or on a
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
`POST /api/v1/secrets/resolve`, which MUST answer standalone names
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
`coffer secret list` and `GET /api/v1/secrets` MUST list every ref the
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
refused with `SECRET_IN_USE` while a skill in the master store cites a
standalone secret's URI, naming that skill, and a delete that removes a ref
MUST forget its approved destinations.

#### Scenario: the command line lists every cited ref with its presence
- **GIVEN** a registered MCP server citing a stored ref and a registered model provider citing a ref the store does not hold
- **WHEN** the user runs `coffer secret list`
- **THEN** both refs are listed
- **AND** the MCP server's ref is shown as present and the provider's ref as missing

#### Scenario: a secret nothing references is listed as unreferenced
- **GIVEN** a standalone secret no resource and no skill cites, and another that a skill cites by URI
- **WHEN** the secrets are listed
- **THEN** the first is marked unreferenced and readable by local processes
- **AND** the second names the skill, and deleting it is refused naming that skill

#### Scenario: the list says when each secret was created and last used
- **GIVEN** a standalone secret stored and never used
- **WHEN** the secrets are listed, then `coffer run` resolves it, then they are listed again
- **THEN** the first listing carries its `created_at` and no `last_used_at`
- **AND** the second carries a `last_used_at` no later than now

### Requirement: Move plaintext secret files into the store
`POST /api/v1/secrets/scan` (`coffer secret scan`) MUST report every
plaintext secret in `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json`
(a flat map of strings) and in the skill master store (assignments whose name
says password, secret, token or key, and well-known token shapes) by file,
line, key and proposed name, every skill that still mentions
`~/.coffer/secrets/`, and how many files it read (`files_checked`); it MUST NOT
return a value. When a skill still mentions `~/.coffer/secrets/`, the scan MUST
also carry `handoff`, a prompt (Principle IV, AI-Native) that asks the person's
agent to rewrite each such command to get its value through
`coffer run --secret ENV=NAME -- …` or `coffer run --env-file` with
`coffer://secret/<name>` references, to show the person the diff, and never to
print, copy or read a value; the prompt names only each mention's skill, file,
line and the path it reads, and the secret name each key of a secrets file
becomes — never a value and never a file's contents. With no mention the scan
carries a `null` `handoff`. The Find plaintext keys dialog keeps listing the
mentions for the person to update by hand and offers Copy prompt and, where a
managed agent is available, Ask an agent beside them;
`coffer secret scan --prompt` prints the same prompt.
`POST /api/v1/secrets/import` (`coffer secret import
[--id]… [--dry-run]`) MUST store each chosen value as `secret/<proposed name>`,
confirm the store reads back the same value, and only then replace the value in
its file with the reference, atomically and keeping the file's mode; a name that
is new waits for approval like any new standalone secret (the finding is skipped
as waiting, the value is not stored and its file is untouched, and importing
again once the approval is applied moves it); a name already holding a different
value MUST be skipped with its file untouched; a
file that cannot be rewritten MUST leave its findings skipped as `stored` —
naming the secret the value is now stored as, the file still holding it — while
the other files are rewritten, and importing the same findings again MUST retry
the file; `--dry-run` writes nothing. Each value stored MUST be audited as
`secret_imported` without the value.

#### Scenario: a scan names plaintext secrets without their values
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script assigns a token
- **WHEN** the scan runs
- **THEN** both are reported with their file, key and proposed name, and the response contains neither value

#### Scenario: a skill still reading a secrets file is handed to an agent
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script sources that file
- **WHEN** the scan runs
- **THEN** its hand-off names the skill, the script's path and line and the file it reads, the secret names the file's keys become and how `coffer run` hands a secret to one command, and asks for the diff
- **AND** the prompt contains no value from either file, `coffer secret scan --prompt` prints the same text, and nothing on disk has changed

#### Scenario: importing moves a value and leaves a reference
- **GIVEN** those findings
- **WHEN** they are imported
- **THEN** a dry run changed nothing, and the first import stores nothing and leaves every file as it was, with one pending `add_secret` approval per name
- **AND** once those approvals are applied with a presence grant, importing again makes each value read back from the store under its standalone name and each file cite `coffer://secret/<name>` in place of the value with its mode unchanged

#### Scenario: a file that cannot be rewritten keeps its key and says so
- **GIVEN** a plaintext secrets file in a folder Coffer cannot write
- **WHEN** its finding is imported, after the approval that new secret waits for was applied
- **THEN** nothing is reported moved, the finding is skipped as `stored` naming its secret and why, the file is unchanged, the store holds the value and one `secret_imported` entry names it
- **AND** importing the same finding again once the folder is writable moves it and rewrites the file

#### Scenario: a scan that finds nothing says how many files it read
- **GIVEN** a secrets folder whose only file holds no secret
- **WHEN** the scan runs
- **THEN** it reports no findings and at least one file read

### Requirement: Keep the master key behind a storage port chosen by the build
Where the master key lives MUST be decided by how the build was made, never by
a setting or an environment variable. A signed release stamped with Coffer's
Keychain access group MUST keep the key only in one data-protection Keychain
item in that group (service `coffer`, account `master-key`) with no
user-presence flag, so the daemon reads it unattended; it MUST NOT read a key
from the key file or the login-keychain item, and MUST refuse to relocate the
key to a file. A build without the stamp is a development build: it keeps the
arrangement of "Keep the master key in exactly one place", and reports itself
as development (see "Release plaintext only to a present human in the desktop
app").

#### Scenario: a signed build keeps its key in its access group only
- **GIVEN** a signed build with an empty secret store
- **WHEN** the key is resolved
- **THEN** the key is created in the access-group item, no key file is written, and the manager reports the access group as the key's location
- **AND** a later request to relocate the key to the file is refused

#### Scenario: the access-group item carries no presence flag
- **GIVEN** the access-group backend
- **WHEN** it writes and reads the master key
- **THEN** every query names the data-protection keychain and Coffer's access group, and none carries an access-control (presence) flag

### Requirement: Show a secret this Mac cannot open as missing on this Mac
`GET /api/v1/secrets` MUST mark a stored ref whose ciphertext this Mac's
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
`POST /api/v1/secrets` on a standalone `secret/<name>` that has no value on
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

### Requirement: Store every secret only as a ciphertext file
The system MUST persist every secret only as Fernet ciphertext
([The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](../../../docs/decisions/master-key-lives-in-the-macos-keychain.md)),
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
