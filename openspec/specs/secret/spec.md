# Secrets

## Purpose
Secrets is the encrypted secret store: the ciphertext, the master key that opens it, the
routes that manage both, and the rule that every other capability carries a reference
rather than a secret. Every kind Coffer manages eventually needs a secret — an HTTP MCP server's
bearer token, a channel bot's token, a provider's API key — and none of them may hold one. This is
the single place a secret is written, read and destroyed, so that "Coffer never persists a plaintext
secret" is one claim to verify rather than one per kind. A developer types each secret once, has it
stored encrypted, and every configuration that needs it holds only a name — so exporting a config,
reading the audit log or sending a bug report can never leak it. The whole lifecycle — store, cite
from a resource of any kind that declares secrets, rotate, delete, move the master key — works
through the Secrets page, Settings and the REST routes with no daemon restart, and `coffer secret set`
stores a value from a terminal, which is what lets setup on a new machine be scripted from a
password manager.

It is also the **secret boundary** against the agents Coffer serves
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)):
no route or command returns a value; a value reaches only a present human in the desktop app, and
a secret goes to a destination it did not go to before only after that human approves it there.

The capability ships no web page of its own and still satisfies the End-to-End Deliverable Rule: it
delivers a complete route family (`/api/v1/secrets/*` plus `/api/v1/settings/secrets` and
`/api/v1/settings/secret-boundary`) over its own files under `local/secret-boundary/`, and the
commands that need a terminal (see [resource-framework](../resource-framework/spec.md), "Keep the
command line to what needs it"): `coffer secret list` and `coffer secret set`, which a hand-off
prompt tells an agent to run because a person types the value, and `coffer run`, which resolves
standalone secrets into one child. Approving, revealing and writing a key backup have no command on
purpose: each needs the desktop app's presence check. Its visual surfaces are the Secrets page,
which lists every stored and cited secret with what uses it, and Settings → Security, the master
key's card; the secret fields themselves live in other capabilities' dialogs, because a secret is
entered where the thing that needs it is
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

### Requirement: Read and change the master key's location through the API and Settings
Users MUST be able to read and change the key's location from the management API
(`GET`/`PUT /api/v1/settings/secrets`) and from a Settings card that states the consequence and
confirms before it writes. `secrets.storage` is not one of the keys read before the daemon binds,
so `coffer config` does not carry it (see [resource-framework](../resource-framework/spec.md),
"Keep the command line to what needs it"). `PUT /api/v1/settings/secrets` MUST refuse any value
other than `file` or `keychain` as a validation error, and a change MUST run the verified relocation
of "Verify the destination before relocating the master key".

#### Scenario: read and change the master key location from the API and the Settings card
- **GIVEN** a running daemon whose master key is in the file `~/.coffer/master.key`
- **WHEN** the location is read with `GET /api/v1/settings/secrets` and on the Settings card, then changed to the keychain with `PUT /api/v1/settings/secrets`
- **THEN** both reads report the file location
- **AND** after the change both surfaces report the keychain, and a previously stored secret still reads back

#### Scenario: move the master key from the Settings card and refuse an unknown location
- **GIVEN** a running daemon whose master key is in the file `~/.coffer/master.key`
- **WHEN** the user picks the keychain on the Settings card and confirms, and then `PUT /api/v1/settings/secrets` is sent the value `vault`
- **THEN** the first moves the key to the keychain, audited as `master_key_relocated`, and a previously stored secret still reads back
- **AND** the second is refused as a validation error naming the accepted values and leaves the key where it is

### Requirement: Store a secret through the API
`POST /api/v1/secrets` MUST store `{ref, value}` for a ref that exists, answer `204`, and record a
`secret_set` audit entry carrying the ref only, plus whether it replaced a value. A new secret is
stored without a `ref` (see "Mint every secret's id; a person names it"). A new secret and a replacement
are both stored at once, with no approval, because a caller that supplies a value already has it;
where a value may go is decided at each destination (see "Hold a secret for a new destination
until a person approves it"). A replacement MUST reach whatever holds the old value, such as the
model proxy, which is refreshed with the new one; the consumers that read a secret when they use
it, an MCP server's next spawn or a channel adapter's next start, get the new value then.

#### Scenario: storing a secret answers 204 and audits the ref only
- **GIVEN** a running daemon
- **WHEN** the user posts `{ref, value}` for an existing ref to `/api/v1/secrets`
- **THEN** the response is `204` and the ref reads back present
- **AND** a `secret_set` audit entry names the ref and does not contain the value

#### Scenario: replacing a value in use stores it at once
- **GIVEN** a secret an approved MCP server receives
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `204`, the store holds the new value, and no approval waits
- **AND** the `secret_set` audit entry names the ref and says it replaced a value, without either value

#### Scenario: adding a standalone secret stores it at once
- **GIVEN** the protection is on
- **WHEN** a value is posted with a label and no ref
- **THEN** the answer is `201` with the minted ref, the value reads back from the store, and no approval waits

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
- **WHEN** the user issues `DELETE /api/v1/secrets/{ref}` (the Secrets page's Delete button),
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
`coffer secret set --name "<label>"` (a new secret) and `coffer secret set <ref>` (an existing one) MUST take the secret from standard input, or from a hidden prompt on
a terminal, MUST reject an empty value with a non-zero exit, and MUST document `--value` as unsafe
because it lands in shell history.

#### Scenario: the command line stores a secret without it reaching shell history
- **GIVEN** a terminal,
- **WHEN** the user pipes a secret into `coffer secret set --name "<label>"`, or is prompted for it with the input hidden,
- **THEN** the secret is stored, an empty value is rejected with a non-zero exit, and passing `--value` instead prints an explicit warning that the value lands in shell history.

### Requirement: Route every secret command through the daemon
Every secret command MUST go through the daemon's API and MUST import no secret or keyring
code of its own. This covers the `coffer secret` group and `coffer config`, which carries no secrets
setting. The daemon is the sole owner of the key, and a CLI that opened the keychain itself
would be a second reader to keep honest.

#### Scenario: secret commands import no secret code
- **GIVEN** the `coffer secret` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the secrets infrastructure package
- **AND** it reaches the vault only through the daemon client

#### Scenario: the config command carries no master key setting
- **GIVEN** the `coffer config` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the secrets infrastructure package
- **AND** it has no `secrets.storage` key, so the master key's location is changed only through the daemon's settings route

### Requirement: Carry references, never secrets, in resource configuration
A resource's configuration MUST carry secret references and never secret values. Each kind
declares how its refs are extracted from its own config shape; a kind that declares no extractor
cites no secrets and is never probed. A reference is resolved only at the moment of use.

#### Scenario: store and reference a secret
- **GIVEN** the user has not yet stored an HTTP secret,
- **WHEN** the user issues `POST /api/v1/secrets` (the Secrets page's Add button, or `coffer secret set`) with a `label` and the secret `value` in the request body, then registers an HTTP MCP server whose `secret_refs` cites the minted `ref` it answers,
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
A resource that newly cites a `dialog` secret nothing else cites becomes its `created_for`.
Deleting a resource MUST release a secret only when it was minted for that resource
(`created_for` in the secret's notes) and nothing else cites it: no other resource and no
skill file holding its `coffer://secret/<id>`. Every other secret the resource cited is kept and
shows as not used. The first citation of a secret a resource was given (`dialog`, unclaimed or
claimed by it) needs no approval; a `page` secret needs a person the first time any resource cites it. Each release is recorded. A failed release MUST NOT turn the
already-completed deletion into an error — the secret lingers, which is the status quo, rather
than the deletion appearing to have failed.

#### Scenario: deleting a resource releases the secrets nothing else cites
- **GIVEN** a registered resource citing three secrets: two minted for it, one of which a second resource also cites, and one a person added on the page
- **WHEN** the first resource is deleted
- **THEN** the minted secret nothing else cites is removed from the store and audited, the shared one and the page-added one are kept, and a failure to release either does not fail the deletion

#### Scenario: a dialog's secret is the server's and a page's is not
- **GIVEN** a secret stored under a minted ref and labelled before any resource cites it, and another added on the page
- **WHEN** a new MCP server cites the first, and another new server cites the second
- **THEN** the first needs no approval and is released when its server is deleted, while the second waits for a person and is kept

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
The events `secret_set`, `secret_revealed`, `secret_deleted`, `secret_notes_updated`, `secret_migrated`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported` and the
`secret_approval_*` events MUST carry the ref, the name, the destination or the changed field names only. An audit payload
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
There is no `GET /api/v1/secrets/{ref}` and no `POST /api/v1/sync/key/export`, and no
`coffer` command prints a stored value.
Writing a secret stays open to every surface: a caller that supplies a value
already has it. An audit row is not a refusal — a path that returns a value is
a defect however it is audited
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

#### Scenario: no route or command hands out a stored value
- **GIVEN** a running daemon holding a secret under a ref
- **WHEN** a caller with the daemon's token asks `GET /api/v1/secrets/{ref}` and `POST /api/v1/sync/key/export`, and a person runs `coffer secret list`
- **THEN** each route is refused as one that does not exist, and the list names the ref without its value
- **AND** no response or output carries the value or the master key

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
stays refused for that target until the destination changes). Citing an existing
secret from a destination that did not cite it, and changing the target of one
that did, each record a pending approval, once per target; a later target
supersedes the approval for the earlier one. A binding already approved for
its target MUST keep working. A binding is approved without a person only when
its value was supplied for it — the destination was just registered or changed,
and the ref was never bound anywhere, is not a standalone `secret/` name and
was written on this machine within the last five minutes (see "Approve a secret's binding when its
destination is registered") — or while the protection is switched off.
Approving MUST
take a presence grant (`POST /api/v1/secrets/approvals/{id}/approve`, or several at once
under "Approve several bindings in one confirmation");
refusing (`POST .../reject`) MUST NOT, and records its audit event. `GET /api/v1/secrets/approvals`
lists approvals, having first evaluated every current destination, and marks
superseded those nothing asks for any more.

#### Scenario: citing an existing secret from a new MCP server waits for approval
- **GIVEN** a secret an MCP server is already approved to receive
- **WHEN** a second MCP server citing the same ref is registered, and a session reaches its tools
- **THEN** the second server is not spawned with the secret, the attempt answers `SECRET_BINDING_PENDING`, and one pending approval names the ref, the new server and its command line
- **AND** the first server keeps receiving the secret

#### Scenario: a refused binding stays refused until its target changes
- **GIVEN** a pending approval for a server's secret that a person rejects
- **WHEN** the server is next started or listed, and then its target changes
- **THEN** the first answers `SECRET_BINDING_REJECTED` (409, a refusal, not a wait) and the web UI says it was refused instead of showing a pending approval
- **AND** until then checking again raises no fresh approval for the same target; the changed target drops the old refusal and a fresh pending approval for it waits for a person

#### Scenario: changing where a secret goes asks again
- **GIVEN** an MCP server whose secret is approved for its command line
- **WHEN** its command is changed to another program
- **THEN** the secret is withheld and a pending approval names the new command line
- **AND** after the approval is applied with a presence grant the server receives the secret again

#### Scenario: moving a provider connection's base URL asks again
- **GIVEN** a provider connection whose key the model proxy already receives
- **WHEN** its base URL is changed, and separately its key is replaced
- **THEN** the replaced key is stored at once, but it is not handed to the proxy or the engine for the new URL until the approval naming that URL is applied
- **AND** once that approval is applied the proxy is refreshed with the key

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

### Requirement: Report a pending approval on the command line by exiting
A command whose change leaves a secret waiting for a person MUST say so on standard error and exit
`9`, which an agent reads as "tell the developer, do not retry": a registration that cites a
secret from a new destination answers `SECRET_BINDING_PENDING`. Storing a value with `coffer
secret set` waits for nobody, so it has no `--wait` and never exits `9`. The command line neither
lists nor answers approvals: they are listed on the Secrets page and `GET /api/v1/secrets/approvals`,
refused with the Reject button or `POST .../reject`, and approved only in the desktop app, so no
command approves.

#### Scenario: a command whose change leaves a binding waiting exits 9
- **GIVEN** a secret already sent to one MCP server
- **WHEN** a command registers a second server citing it and the daemon answers `SECRET_BINDING_PENDING`
- **THEN** the command prints the daemon's message and exits `9`

#### Scenario: storing a replacement value with the command line waits for nobody
- **GIVEN** a secret sent to an MCP server, and a provider connection's key stored under a ref
- **WHEN** the user stores a new value for each ref with `coffer secret set`
- **THEN** each command prints `stored: <ref>` and exits `0`, the store holds the new value, and no approval waits

### Requirement: Send a secret only to the origin it was approved for
A secret is approved for a target, so a request that carries one MUST NOT
deliver it to any other origin (scheme, host and port) by following a redirect.
Every outbound path that injects a stored secret — an HTTP custom tool's request,
an HTTP MCP upstream's headers, the engine's and the probe's provider calls,
the model proxy's relay, a channel adapter's platform calls and the sync
remote's git credential — MUST follow one rule: it does not follow a redirect
to another origin. An HTTP client that injects a secret MUST NOT follow
redirects at all, so the 3xx is the answer (a custom tool reports it as "Location:
… (not followed)"), except the SeaTalk media download, which carries only a
short-lived `Authorization` bearer that the client drops on a cross-origin hop; the MCP transport follows only within the endpoint's own
origin, which keeps its headers on the origin they were configured for; and
git's credential helper MUST answer only for the origin of the remote the call
is about, so the redirect target a remote names is never offered the token.
The rule covers every header Coffer injects, not only `Authorization`, and a
secret placed in a query.

#### Scenario: a redirect to another origin is never sent the secret
- **GIVEN** an origin that redirects every request to a second origin on another port, and a secret injected into a request to the first as `X-API-Key`, as `x-api-key`, as a bearer token or as git's Basic credential
- **WHEN** a custom tool, an HTTP MCP upstream, the engine's model client, the provider probe or a sync remote call is made against the first origin
- **THEN** the first origin receives the secret as approved and the second origin receives no request carrying it (for a custom tool, an engine client and the probe, no request at all)
- **AND** a sync remote that needs the credential at its own origin still receives it there

### Requirement: Fix a secret's placement by its destination's definition
Where a secret is placed in a request is part of what a person approved, and
only a destination's own definition decides it. A secret's binding is keyed by
its ref, its destination and its **slot** — the header name of an HTTP MCP
server or custom-tool group, the environment variable of a stdio server — and
pinned to its target; moving an approved ref to another slot of the same
destination, or into another destination, MUST record a pending approval like a
target change and inject nothing in the new place until it is approved. A
provider connection's target MUST include the protocol that decides which header
carries its key (`model api <base URL> as <protocol>`), so changing the protocol
asks again. The only fields that receive a stored secret are the headers a
destination's definition names: an argument hole in a custom tool's path, query,
headers or body is filled only from the calling agent's own arguments and MUST
NEVER be filled from a stored secret, a tool header spelled like a secret header
MUST NOT replace the injected value, and the secret is never placed in a URL, a
query or a body.

#### Scenario: a secret moved to another placement of its destination waits
- **GIVEN** a secret approved for an HTTP MCP server's `X-API-Key` header, a custom-tool group's header, a stdio server's environment variable, and a provider connection's key presented as `openai`
- **WHEN** each is changed so the same ref rides in another header or variable, or the provider's protocol becomes `anthropic`, at an unchanged URL
- **THEN** each answers `SECRET_BINDING_PENDING` for the new placement while the approved one keeps working

#### Scenario: a template cannot pull in a stored secret
- **GIVEN** a custom-tool group with a secret header and a tool whose path, query, headers and body templates name arguments after that header and after "secret"
- **WHEN** the request is built
- **THEN** the stored value appears only in the group's own header, and in no URL, query, body or other header

### Requirement: Default the approval protection by the build
`secrets.require_approval` MUST default by how the build was made, with the
same fact that chooses where the master key lives ("Keep the master key behind a
storage port chosen by the build"): a signed release, whose master key only its
signed binaries can read, defaults it **on**; a development build, whose master
key is a file any process of the same user can read and whose approvals
therefore protect nothing against a same-user agent, defaults it **off**. Only
the default depends on the build: a setting stored by a person MUST win in both,
turning it on MUST still need nobody, and turning it off once on MUST still wait
for the desktop app. `GET /api/v1/settings/secret-boundary` MUST report
`default_on` (whether the build defaults it on) beside `require_approval`, and
Settings and the Secrets page MUST say, in one line with the detail behind a
help tip, that in this build approvals are off by default because an unsigned
build cannot protect the master key. The Overview's `secret_approval_off` item
MUST be listed only when the build defaults it on and it is off, which is a
person's choice; an unsigned build's default off MUST NOT raise it.

#### Scenario: a signed build starts with the protection on
- **GIVEN** a signed build and no stored setting
- **WHEN** the setting is read and the attention list is read
- **THEN** `require_approval` is true with `default_on` true, a destination citing a secret that went elsewhere waits, and no `secret_approval_off` item is listed

#### Scenario: an unsigned build starts with the protection off and says nothing
- **GIVEN** a development build and no stored setting
- **WHEN** the setting is read, a second destination cites a secret already sent elsewhere, and the attention list is read
- **THEN** `require_approval` is false with `default_on` false, the second destination is approved without asking, and no `secret_approval_off` item is listed

#### Scenario: a stored setting wins over the build's default
- **GIVEN** a development build where a person turned the protection on
- **WHEN** a second destination cites a secret already sent elsewhere, and the protection is then turned off
- **THEN** the destination waits for approval, and turning it off answers a pending `disable_protection` approval

### Requirement: Turn the protection off only through the desktop app
`secrets.require_approval` (`GET|PUT /api/v1/settings/secret-boundary`) MUST
switch on at once and MUST switch off only through a pending
`disable_protection` approval applied with a presence grant; no environment
variable, config file or CLI flag switches it off. (Where it is off because the
build defaults it off, "Default the approval protection by the build", there is
nothing to switch off.)

#### Scenario: switching the protection off waits for the desktop app
- **GIVEN** the protection is on
- **WHEN** `PUT /api/v1/settings/secret-boundary` is sent turning it off
- **THEN** it answers a pending `disable_protection` approval and the protection stays on
- **AND** once the approval is applied with a presence grant a new destination is approved without asking

### Requirement: Resolve standalone secrets into one child with coffer run
A standalone secret MUST live in the store under `secret/<id>`, where `<id>` is the
minted 32 hex characters (older names are moved to one at start), and MUST be
cited from files as `coffer://secret/<id>`
([Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)).
`coffer run [--secret NAME|ENV=NAME|ENV=coffer://secret/<id>]… [--env-file FILE] [--no-masking] -- cmd
args…` MUST accept a secret as its name or as its `coffer://secret/<id>` URI
(a bare URI sets the variable the name would; skills cite a secret in the URI
form, which the citation index sees, so the secret lists the skill under Used
by), and MUST resolve every named secret, every `coffer://secret/` value in the
env file and every such value in its own environment through
`POST /api/v1/secrets/resolve`, which MUST answer standalone names
only and MUST record one `secret_resolved` entry per name carrying the ref, the name,
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
(`last_used_at`, stamped at most once a minute and not by a reveal), the resources that cite it with the slot each cites it under, its label, description and
`created_for`, its `coffer://secret/<id>` and the skills whose files cite that URI, whether
nothing references it (`unreferenced`), the destinations it is approved for or
waits on, and whether another process of this user can read the value where
Coffer puts it (a standalone secret, or a stdio MCP server's environment). The
listing reads what cites each secret from the citation index (see "Keep an index of what cites each secret"), decrypts nothing and records no audit entry; who used a secret is audited, not listed here (see "Audit every use of a secret by who used it"). It MUST leave out an
agent's model-proxy token (`proxy-token/<agent name>`): Coffer mints it and the
agent fetches it itself, so no person enters, replaces or cites it. A delete MUST also be
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

#### Scenario: an agent's model-proxy token is not listed
- **GIVEN** a stored agent model-proxy token and a stored standalone secret
- **WHEN** the secrets are listed
- **THEN** only the standalone secret is listed

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
in place of its last use, and a banner counting them and naming the first of
them ("N secrets have no value on this Mac · linear, SeaTalk and sentry can’t
start until they have a value") whose **Add values** opens one dialog with a
field per missing secret, where a field left empty stays missing and **Save N
values** stores the rest. The banner offers no master-key import: importing a
key replaces this Mac's own, so it lives in the sync join flow and in Settings ›
Security. Adding a value MUST be an ordinary write of the ref, stored at once like any other write, and reveal MUST be unavailable for such a
row. The same set is listed on Overview (see "List secrets with no value here
and waiting approvals on Overview"), and the banner's × ignores it exactly as
Ignore does there.

#### Scenario: a ciphertext from another Mac's key is listed as locked
- **GIVEN** a stored standalone secret encrypted with another Mac's master key, and one stored on this Mac
- **WHEN** the secrets are listed
- **THEN** the first is present and `locked`, the second is not `locked`
- **AND** no value is decrypted and no audit entry is written

#### Scenario: a value added for a locked secret replaces it at once
- **GIVEN** a locked standalone secret
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `204`, the row is no longer `locked` and the store reads back the new value

#### Scenario: a secret this Mac cannot open is missing on this Mac
- **GIVEN** a locked secret and a cited secret the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both rows read "Missing on this Mac" with Add value, and a banner says 2 secrets have no value on this Mac and offers Add values, with no link to import a master key
- **AND** Reveal is unavailable for the locked row, and Add value posts the new value for its ref

### Requirement: Show each change waiting for approval as the question it asks
The web UI MUST show every pending approval as the question it asks — a new
use, or turning the protection off — naming the
secret, who asked and when, and what uses the secret. The Secrets page MUST carry
a banner "N changes waiting for approval" with **Review**, and mark a row
whose new use waits as "Waiting for approval". In the desktop app
**Approve…** MUST run the shell's presence check (Touch ID or the login
password); in a browser Approve MUST be disabled, naming the desktop app, while
**Reject** stays available.

#### Scenario: a browser can reject a change but not approve it
- **GIVEN** a pending new use of a secret, opened in a browser
- **WHEN** the approvals window shows it
- **THEN** Approve is disabled and says to approve in the Coffer desktop app
- **AND** Reject is enabled and refuses the approval over REST

### Requirement: Approve several bindings in one confirmation
A person MUST be able to approve several pending approvals under one presence
check, for the case that a change leaves a handful of destinations waiting at
once. `POST /api/v1/secrets/approvals/approve` takes a list of `{id,
fingerprint}` — each approval's id and the target fingerprint it was shown
with — and ONE presence grant for the operation `approve_batch`, whose target is
`batch:` followed by the SHA-256 of the sorted `id:fingerprint` lines of exactly
that list. The daemon MUST recompute the target from the list it receives, so
the set approved is the set the person was shown: a grant signed for another
list, for a single approval, or by anyone but the desktop app is refused with
`PRESENCE_GRANT_INVALID` and approves nothing, and a batch grant authorises no
single approval. The daemon MUST then apply each item only if it is still
pending, is not the switch that turns the protection off, and is still pinned to
the fingerprint listed; every other item is skipped, left as it is, and
reported with its reason (`changed`, `not_pending`, `not_found`,
`not_batchable`, `failed`). Nothing outside the list is touched, and nothing is
approved by any other path — no selection, default or "approve all" runs without
the grant. Turning the protection off MUST still be approved on its own.
`POST /api/v1/secrets/approvals/reject` refuses several at once and, like
refusing one, takes no presence. The command line has no approvals command:
approving is the desktop app's.

In the desktop app the shell, not the page, decides what is covered: it reads
each selected approval from the daemon, keeps those still waiting, names the
first few in its own operating-system prompt and counts the rest, and signs over
that list. The web UI MUST show the pending approvals as one table in a dialog: a row per
change with its kind, the secret, where it goes (what uses it, or the target
that receives it), who asked and when. Once two or more wait, a header checkbox
selects rows, nothing is selected to begin with, and the buttons read **Reject
all** and **Approve all N…** until rows are selected, then **Reject N** and
**Approve N…** beside "N of M selected". **Approve…** runs the shell's presence
check directly, over exactly the rows it covers; there is no second review step,
because the table already is the review. Afterwards the same rows say, per
change, approved or skipped and why. Rejecting shows a toast and keeps no list
of refused changes. In a browser Approve MUST be disabled, naming the desktop
app, while Reject stays available.

#### Scenario: one confirmation approves every binding shown
- **GIVEN** three pending approvals for three destinations that cite one secret
- **WHEN** one `approve_batch` grant signed over exactly those three is sent with the three `{id, fingerprint}` pairs
- **THEN** all three are approved, each destination receives the secret, and each approval is audited as approved

#### Scenario: a batch grant covers exactly the bindings shown
- **GIVEN** three pending approvals and a batch grant signed over two of them
- **WHEN** it is sent with all three, or a single-approval grant or a swapped fingerprint is sent instead, or the batch grant is used to approve one approval alone
- **THEN** each attempt is refused with `PRESENCE_GRANT_INVALID` and all three still wait

#### Scenario: a binding whose target changed is skipped
- **GIVEN** three pending approvals shown to a person, and one server whose command is changed before the confirmation
- **WHEN** the batch grant over the three is sent
- **THEN** the changed server's old approval is skipped as no longer pending and its new approval for the new command still waits, while the other two are approved

#### Scenario: a fingerprint that is not the one shown is skipped
- **GIVEN** a batch whose list names an approval with a fingerprint other than the one it is pinned to
- **WHEN** the grant over that list is sent
- **THEN** that item is skipped as `changed` and stays pending, and the others are approved

#### Scenario: nothing in a batch is approved without a present human
- **GIVEN** three pending approvals
- **WHEN** the batch is sent with no grant, with a forged signature, or with a grant already used
- **THEN** it is refused (`422` or `PRESENCE_GRANT_INVALID`) and nothing is approved

#### Scenario: approving several waits for a review of every change
- **GIVEN** three changes waiting, in the desktop app
- **WHEN** the person opens the approvals dialog
- **THEN** the table lists all three with their destinations and targets and none is ticked to begin with, and nothing is approved until **Approve…** runs the presence check over the rows it covers

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
approvals asked and answered), `settings.json` (the
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

### Requirement: List secrets with no value here and waiting approvals on Overview
The secret kind MUST contribute to the attention list ([resource-framework](../resource-framework/spec.md)
"Report what needs a person across every kind") one item for the **set** of
secrets that have no value on this Mac — cited by a resource but not stored
here, or stored under another Mac's master key and so unopenable (see "Show a
secret this Mac cannot open as missing on this Mac") — and one for the **set**
of approvals still pending. The first MUST read `secret_missing_here`, severity
`error`, with the reason "N secrets have no value on this Mac." ("1 secret has no
value on this Mac.") and the action `open` as a `GET` of `/api/v1/secrets`; the
second MUST read `secret_approvals_pending`, severity `warning`, with the reason
"N changes waiting for approval." and the action `review` as a `GET` of
`/api/v1/secrets/approvals?status=pending`. A `GET` action is a navigation: the
page it opens is the client's to choose. Each item's `uid` MUST be a short,
order-independent fingerprint of the set's members (the refs, the approval ids),
so its attention key identifies exactly that set: ignoring the item ignores that
set, and a secret going missing, a value being added, or an approval arriving or
being decided changes the key and brings the item back. Both count toward the
per-kind counts the menu bar reads, and neither is listed
when its set is empty.

#### Scenario: secrets with no value on this Mac are listed on Overview
- **GIVEN** one secret cited by a resource but not stored here, and one stored under another Mac's key
- **WHEN** the attention list is read
- **THEN** it carries one `secret_missing_here` item, severity `error`, with the reason "2 secrets have no value on this Mac." and the action `open`, and the per-kind count for `secret` includes it
- **AND** with a pending approval it also carries one `secret_approvals_pending` item, severity `warning`, whose action is `review`

#### Scenario: an ignored secret item returns when the situation changes
- **GIVEN** the `secret_missing_here` item ignored by its key
- **WHEN** another secret goes missing
- **THEN** the item is listed again under a new key, and the earlier key still lists nothing

### Requirement: Move plaintext secrets in managed resources into the store
`POST /api/v1/secrets/scan` MUST report every plaintext secret in what Coffer
manages, and MUST NOT return a value:

- **skills** — every text file of a skill in the master store (Coffer's own
  bundled skills excepted): an assignment whose name says password, secret,
  token or key, or a well-known token shape;
- **MCP servers** — a registered server's stdio `env` value, HTTP `headers`
  value, or HTTP API (custom tool) `headers` value whose name says password,
  secret, token, key or authorization, or whose value is a well-known token
  shape or a `Bearer`/`Token` credential.

A value that is already a reference (`coffer://secret/…`), an interpolation
(`$VAR`, `${VAR}`, `{{…}}`), a placeholder (`<…>`, `xxx`, `your-…`,
`changeme`, `example…`) or code is not a finding. Each finding carries a stable
id, its source (`skill` or `mcp_server`), the resource's name, where it is
(a skill's file and line; a server's `env` or `header` and its key), and what
it would become: the label a skill's secret will get, the server's own
`secret_refs` slot for a server. The scan also reports how many files and
servers it read (`files_checked`, `servers_checked`).

`POST /api/v1/secrets/import` (the chosen finding ids, and an optional dry run
that writes nothing) MUST move each chosen value:

- a skill's value is stored at a minted `secret/<uuid4 hex>` labelled with the
  proposed name and, once the store reads the same value back, replaced in its
  file by `coffer://secret/<id>`, atomically and keeping the file's mode; a file that cannot be rewritten
  leaves its findings skipped as `stored`, naming the secret, and importing the
  same findings again retries the file;
- a server's value is stored under a new ref of the server's own
  (`secret/<uuid4 hex>`, minted for that server), and the server's config is changed through the
  resource service to drop the plaintext entry and cite the ref in
  `secret_refs` under the same key — so the change is validated, audited and
  reconciled like any edit, and, its value supplied for it moments ago, needs
  no approval (see "Hold a secret for a new destination until a person approves it").
  A server whose config cannot be changed leaves its findings skipped with the
  reason and nothing stored.

Each value stored MUST be audited as `secret_imported`, naming the secret or
ref and where it came from, never the value.

The Find plaintext keys dialog lists the findings grouped by source, each by
resource, place and what it becomes, all ticked; Review changes runs the dry
run and lists the secrets it would add and the files and servers it would
change; Apply moves them and reports what moved and what was skipped and why. A
scan that finds nothing says how many files and servers it read.

#### Scenario: a scan names plaintext secrets in skills and MCP servers without their values
- **GIVEN** a skill whose script assigns a token, a stdio MCP server whose `env` holds a password, and an HTTP API server whose `Authorization` header holds a bearer token
- **WHEN** the scan runs
- **THEN** all three are reported with their resource, place and what each becomes, and the response contains none of the values

#### Scenario: references, interpolations and placeholders are not findings
- **GIVEN** a server whose `env` holds `${API_TOKEN}`, `<your-token>` and a non-secret `LOG_LEVEL=debug`, and a skill citing `coffer://secret/github`
- **WHEN** the scan runs
- **THEN** none of them is reported

#### Scenario: importing a skill's value leaves a reference in its file
- **GIVEN** a skill finding
- **WHEN** it is imported, first as a dry run
- **THEN** the dry run changed nothing, and the import stores the value under a minted id, which reads back the same
- **AND** the file cites `coffer://secret/<id>` in place of the value with its mode unchanged, and one `secret_imported` entry names the secret without the value

#### Scenario: importing a server's value moves it into the server's secret refs
- **GIVEN** a stdio MCP server finding and an HTTP header finding
- **WHEN** they are imported
- **THEN** each server's config no longer holds the value, cites a new ref of its own in `secret_refs` under the same key, and that ref holds the value
- **AND** the server resolves the secret with no approval waiting, and a later scan reports neither

#### Scenario: a file that cannot be rewritten keeps its key and says so
- **GIVEN** a skill finding in a file Coffer cannot write
- **WHEN** it is imported
- **THEN** nothing is reported moved, the finding is skipped as `stored` naming its secret, the file is unchanged and the store holds the value
- **AND** importing the same finding again once the file is writable moves it and rewrites the file

#### Scenario: a scan that finds nothing says how much it read
- **GIVEN** a skill and a server holding no plaintext secret
- **WHEN** the scan runs
- **THEN** it reports no findings, at least one file read and one server read

### Requirement: Label and describe a secret without changing its reference
A secret's ref MUST stay its identity for life: no label or description change
moves the value or changes anything that cites it. `PUT /api/v1/secrets/notes`
(`{ref, label, description}`) MUST store, for a stored or cited ref (else 404),
a label of up to 64 characters and a description of up to 200 (longer is 422);
a field left out is unchanged and an empty value removes it. Labels and
descriptions MUST live in one versioned vault state document keyed by ref —
never beside a ciphertext — so they travel with sync. The same document records where a secret came from (`origin`: `page` for one a
person added on the Secrets page or with `coffer secret set --name`, `dialog` for one
written under a minted id by a resource dialog, an import or a service for the resource about
to cite it) and, for a dialog's, the resource that cites it (`created_for`); editing a label or
description never changes either.
`GET /api/v1/secrets` and `coffer secret list --json` MUST carry each ref's
`label`, `description` and `created_for`. Deleting a secret, and the release of
a ref when the resource citing it is deleted, MUST drop its notes. A change MUST
be audited as `secret_notes_updated` naming the ref and which fields changed,
never their text.

#### Scenario: a label and description change nothing that cites the secret
- **GIVEN** a ref an MCP server cites
- **WHEN** it is labelled "Jira PAT" and described "release bot's token"
- **THEN** the list carries the label and description, the server's config still cites the same ref, the server resolves it with no approval waiting, and the store holds the same single file

#### Scenario: notes go with the secret
- **GIVEN** a labelled, described standalone secret
- **WHEN** it is deleted
- **THEN** the notes document holds no entry for its ref

### Requirement: Mint every secret's id; a person names it
Every new secret's id MUST be minted by Coffer as `secret/<uuid4 hex>` (32
lowercase hex characters), whoever the secret is for: a standalone secret, an
MCP server's header, a channel's token, a provider's key. A resource's config
cites `secret/<hex>` in its secret slot and a file cites
`coffer://secret/<hex>`; it is the same id. A person gives a secret only a
label. `POST /api/v1/secrets` MUST accept `{label?, created_for?, value}`
without a `ref`, mint the id, store the value, keep the label and `created_for`
(the uid of the resource it is minted for) as the secret's notes, and answer
`201` with `{ref, uri}`. The Secrets page's Add secret and `coffer secret set
--name <label>` do this and show or print `coffer://secret/<id>`. A secret written under a new `secret/<hex>` ref, without the page, is a dialog's. A request
that names a `ref` MUST replace the value of a secret that exists, as before,
and MUST be refused (422) when the ref does not exist and is not itself
`secret/<32 hex>`; `proxy-token/…` refs are Coffer's own and never go through
this route. `coffer secret set <ref>` replaces an existing secret's value only.

#### Scenario: a secret added on the page gets a minted id and its label
- **GIVEN** the Secrets page
- **WHEN** a secret is added with the label "GitHub token" and a value
- **THEN** it is stored at `secret/<32 hex characters>`, the list shows it as "GitHub token", and the dialog offers `coffer://secret/<that id>` to copy

#### Scenario: a person cannot choose an id
- **GIVEN** a running daemon
- **WHEN** a client stores a value under the new ref `secret/orders-db`, and `coffer secret set --name "Orders DB"` is run
- **THEN** the first is refused with 422 and nothing is stored, and the second stores the value at `secret/<32 hex>` labelled "Orders DB" and prints its URI

### Requirement: Move every secret to a fixed id once
At daemon start every stored or cited ref that is not `secret/<32 hex>` MUST be
moved to one, except a proxy token: a standalone `secret/<name>` keeps its old
name as its label; any other ref a resource cites becomes `secret/<uuid4 hex>`
with origin `dialog` and `created_for` set to its citer's uid when exactly one resource
cites it (a standalone secret gets origin `page`). A stored ref nothing cites
is moved too, labelled with its old ref, with origin `page`.
A move writes the value at the new ref and reads it back, carries this
machine's binding, creation time, last-used stamp and the notes, repoints every
citing resource config through the resource service and the sync remote's push
token, rewrites `coffer://secret/<old>` in the skill master store's files,
deletes the old ref, and is audited as `secret_migrated` naming both refs. A
failure before any citer changed removes the new ref; one part-way leaves the
old ref in place. A second start moves nothing.

#### Scenario: start-up moves old names to fixed ids and keeps them readable
- **GIVEN** a standalone `secret/github` cited by a skill's script, a ref `postman.AUTHORIZATION` an MCP server cites, a ref `team.TOKEN` two servers cite, and a ref `mcp_server/<32 hex>/JIRA_TOKEN` a server cites
- **WHEN** the daemon starts
- **THEN** `secret/github` is now `secret/<32 hex>` labelled "github" and the script cites its new URI, each server's `postman.AUTHORIZATION` and `JIRA_TOKEN` now cites a `secret/<32 hex>`, both servers sharing `team.TOKEN` cite one new ref, each with its old value and no approval waiting
- **AND** a second start moves nothing

### Requirement: Audit every use of a secret by who used it
Every decrypt-for-use MUST be audited as `secret_resolved`: a resource's
destination (an MCP server's spawn or header, a channel adapter's start, a
provider's key, the sync push) with `{ref, destination_kind, destination_uid,
destination_name, slot}`, and a `coffer run` resolve with `{ref, name, argv0,
cwd}`; never a value or the rest of a command line. A (ref, destination, slot)
MUST be audited at most once a minute. The rows are read in Activity; no secrets
route lists them.

#### Scenario: a server start and a coffer run each show as a use
- **GIVEN** a standalone secret and a stored secret an MCP server resolves
- **WHEN** the server's secret is resolved for its destination and `coffer run` resolves the standalone secret
- **THEN** one `secret_resolved` entry per ref names the destination (the server and its slot, or the program and folder of the `coffer run`), and no entry contains a value

### Requirement: Keep an index of what cites each secret
What cites each secret MUST be kept in an index under `derived/`
(`secret-citations.json`) — a rebuildable cache, never synced — rather than
rescanned on each read. The configs and skill files stay the source of truth.
The index MUST be rebuilt in full at daemon start and whenever the file is
missing, unreadable or of another format, and updated on every resource
register, update, rename and delete and on a skill's file changes. Listing
secrets, refusing the delete of a secret in use, releasing a secret when a
resource is deleted and the move to fixed ids MUST read the index and not
rescan the resources or the skill files.

#### Scenario: a new citation shows without a rescan
- **GIVEN** a stored secret
- **WHEN** an MCP server citing it is registered, then a skill file cites its URI, then the index file is deleted and the daemon restarted
- **THEN** after each step the list shows that citer, and after the restart it gives the same answer
