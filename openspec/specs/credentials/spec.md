# Feature Specification: Credentials

**Status**: Accepted
**Scope note**: This spec owns the encrypted credential store — the ciphertext, the master key that opens it, the routes and commands that manage both, and the rule that every other spec carries a reference rather than a secret.
**Input**: Every kind Coffer manages needs a secret eventually: an HTTP MCP server's bearer token, a channel bot's token, a provider's API key. None of them may hold one. This spec is the single place a secret is written, read, and destroyed, so that "Coffer never persists a plaintext secret" is one claim to verify rather than one per kind.

## User Scenarios & Testing

### User Story 1 — Store a secret once, reference it everywhere (Priority: P1)

A developer registers an HTTP MCP server that needs an `Authorization` header, a chat bot that needs a platform token, and a model provider that needs an API key. They want to type each secret once, have it stored encrypted, and have every configuration that needs it hold only a name — so that exporting a config, reading the audit log, or sending a bug report can never leak it.

**Why this priority**: Without it, every kind invents its own secret handling and the promise "no plaintext is persisted" becomes unverifiable.

**Independent Test**: From a terminal, store a secret under a ref, register an HTTP MCP server citing that ref, and confirm the server works while the stored resource config contains only the ref.

**Covering scenarios** (full Given/When/Then under `## Acceptance Scenarios` below):

- store and reference a credential
- credentials never leak to logs or audit
- a surface lifts a pasted secret into the store before registering

---

### User Story 2 — Remove a secret without breaking what uses it (Priority: P1)

The developer rotates or retires a credential. They want deletion to be safe: refused while something still cites the reference, named so they know what to detach, and clean afterwards — no ciphertext left behind and no configuration left pointing at nothing.

**Why this priority**: A delete that silently breaks a channel is worse than no delete at all, and the failure only surfaces the next time that channel is used.

**Independent Test**: Try to delete a credential an MCP server cites; observe the refusal naming that server. Detach the server, delete again, observe success.

**Covering scenarios**:

- delete a credential frees the reference
- a credential in use cannot be deleted
- deleting a resource releases the credentials nothing else cites
- a failed registration leaves no orphaned credential

---

### User Story 3 — Decide where the key lives, and never lose it (Priority: P2)

The developer accepts the default — a `0600` file beside the database — or moves the master key into the OS keychain for machines where `~/.coffer/` might be read by something else. Either way they must never end up with ciphertext they cannot open, and a failed or interrupted move must resolve back to a working state.

**Why this priority**: The key is the only secret material outside the database. Losing it costs every stored credential; silently regenerating it costs them without saying so.

**Independent Test**: Read the key's location from the CLI, move it to the keychain, restart the daemon, confirm stored secrets still decrypt, and move it back.

**Covering scenarios**:

- the master key is never regenerated over existing ciphertext
- relocating the master key verifies the destination before removing the source
- a missing master key is a named, fatal startup failure

---

### User Story 4 — Do all of it from a terminal (Priority: P2)

The developer scripts setup on a new machine: writing secrets from a password manager through a pipe, listing which references the vault expects, checking whether each is present, and deleting one without a prompt in a script.

**Why this priority**: Secrets are the part of setup people most want to automate and least want in shell history.

**Independent Test**: Pipe a secret into `coffer credentials set`, list refs, read one back redacted and then with `--show`, and delete it with `--force`.

**Covering scenarios**:

- the command line stores a secret without it reaching shell history
- the command line redacts a secret unless asked, and an asked-for read is audited

---

### Edge Cases

- **Ciphertext that will not decrypt**: a row whose bytes do not open with the current master key is reported as unreadable, naming the ref. It is never reported as absent, because "absent" invites the user to re-register rather than to restore the right key.
- **A locked OS keychain**: a read that needs the keychain and cannot have it fails with a locked condition rather than a missing one, and the legacy migration skips that reference and retries on the next start.
- **Two writes to the same ref**: the later write wins; the row is re-encrypted in place and keeps its creation time.
- **A ref cited by a resource that no longer exists**: the reference is released when that resource is deleted, and a release that fails never turns the completed deletion into an error — the secret merely lingers.
- **A store call made on the event loop**: forbidden. The store is a blocking SQLite writer, and a busy-wait on the loop deadlocks against the coroutine holding the write lock.

## Acceptance Scenarios

Per `.agents/sdd.md` and `.agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="credentials", scenario="…")` (Python) or `acceptance("credentials", "…", …)` (TypeScript). Coverage is audited by `make verify-acceptance`.

### Scenario: store and reference a credential

- **Given** the user has not yet stored an HTTP credential,
- **When** the user issues `POST /api/v1/credentials` (or the equivalent CLI) with `ref` and the secret `value` in the request body, then registers an HTTP MCP server whose `credential_refs` cites `{ref}`,
- **Then** the credential value is written only as Fernet ciphertext in the `credentials` table (its plaintext never reaches the SQLite DB, any log, or the audit), and the server registration succeeds with the credential resolved (decrypted) at upstream-spawn time.

### Scenario: delete a credential frees the reference

- **Given** a credential `{ref}` exists and is cited by zero MCP servers,
- **When** the user issues `DELETE /api/v1/credentials/{ref}` (or the equivalent CLI),
- **Then** the ciphertext row is removed, the deletion is audited, and a later registration may reuse `{ref}` without conflict.

### Scenario: credentials never leak to logs or audit

- **Given** an MCP server registered with a credential reference,
- **When** the server is spawned, exercised, and torn down through one representative session,
- **Then** an automated scan of every database row, audit entry, invocation record, and log file under `~/.coffer/logs/` reveals zero occurrences of the credential's literal value.

### Scenario: a credential in use cannot be deleted

- **Given** a stored credential whose ref is cited by at least one registered resource,
- **When** the user deletes it,
- **Then** the request is refused with `409 CREDENTIAL_IN_USE`, the message names every citing resource as its kind plus its current name (`channel 'my-bot'`, `mcp_server 'github'`) rather than as a uid — the user has to go and find the thing, and an opaque identity is not what the page they go to shows them, and the ciphertext row is still present afterwards.

### Scenario: an unreadable ciphertext names its ref

- **Given** a stored credential whose ciphertext cannot be decrypted with the current master key,
- **When** something reads that ref,
- **Then** the failure is `CREDENTIAL_UNREADABLE` naming the ref rather than a not-found,
- **And** the presence probe still reports the ref as present, because it never decrypts.

### Scenario: the master key is never regenerated over existing ciphertext

- **Given** a vault whose `credentials` table holds at least one row and whose master key is absent from both the file location and the keychain,
- **When** the daemon starts,
- **Then** it refuses to start with `MASTER_KEY_MISSING` naming the expected key path,
- **And** no new key is written, so restoring the original key restores access.

### Scenario: relocating the master key verifies the destination before removing the source

- **Given** the master key is stored in the `0600` file beside the database,
- **When** the user moves it to the OS keychain,
- **Then** the keychain copy is written and read back before the file is removed, the move is audited as `master_key_relocated`, and an interruption anywhere in between leaves the key resolvable from the file.

### Scenario: a missing master key is a named, fatal startup failure

- **Given** a key file that exists but is truncated or corrupt, beside ciphertext,
- **When** the daemon starts,
- **Then** it fails with `MASTER_KEY_MISSING` naming the path rather than starting with a key that opens nothing.

### Scenario: the command line stores a secret without it reaching shell history

- **Given** a terminal,
- **When** the user pipes a secret into `coffer credentials set <ref>`, or is prompted for it with the input hidden,
- **Then** the secret is stored, an empty value is rejected with a non-zero exit, and passing `--value` instead prints an explicit warning that the value lands in shell history.

### Scenario: the command line redacts a secret unless asked, and an asked-for read is audited

- **Given** a stored credential,
- **When** the user runs `coffer credentials get <ref>`, and then the same command with `--show`,
- **Then** the first prints `[redacted]` and records no audit entry, while the second prints the value and records a `credential_read` entry carrying the ref only.

### Scenario: a failed registration leaves no orphaned credential

- **Given** a registration dialog into which the user pasted a secret,
- **When** the secret is written to the store and the registration that follows it fails,
- **Then** the just-written credential is deleted again, so the store holds no entry that nothing cites.

### Scenario: a surface lifts a pasted secret into the store before registering

- **Given** a user pastes an MCP server definition, or fills a channel's token field, in the web UI,
- **When** the resource is registered,
- **Then** the secret was written to the credential store first and the persisted resource config carries only the ref.

### Scenario: deleting a resource releases the credentials nothing else cites

- **Given** a registered resource citing two credential refs, one of which a second resource also cites,
- **When** the first resource is deleted,
- **Then** the ref nothing else cites is removed from the store and audited, the shared ref is kept, and a failure to release either one does not fail the deletion.

### Scenario: a legacy keychain secret migrates once and then does nothing

- **Given** a pre-0.2 vault whose OS keychain still holds a secret for a ref a registered resource cites, and whose store does not,
- **When** the daemon starts,
- **Then** the secret is moved into the encrypted store and audited as `credential_migrated`,
- **And** a second start moves nothing, reads no keychain entry for any already-stored ref, and a locked keychain leaves startup unaffected.

## Requirements

### Functional Requirements

**The encrypted store ([Envelope-Encrypted Credential Store](../../../docs/decisions/envelope-encrypted-credential-store.md))**

- **FR-001**: System MUST persist every secret only as Fernet ciphertext in the `credentials` table. Secret plaintext MUST NOT be written to the database, any log file, any audit entry, or any structured event.
- **FR-002**: A secret MUST be addressed by an opaque reference — a slash-separated string of `[A-Za-z0-9_.-]` segments — which carries no meaning to the store. A write to an existing ref MUST re-encrypt in place rather than create a second row, so rotating a secret needs no change anywhere that cites it.
- **FR-003**: A stored ciphertext that will not decrypt with the current master key MUST raise `CREDENTIAL_UNREADABLE` naming the ref, never a not-found. The presence probe MUST answer from the row's existence alone, so a corrupt entry still reports present and cannot be mistaken for one that was never stored.
- **FR-004**: The store's blocking methods MUST NOT be called on the event loop; every async caller MUST go through the store's own `a*` facade or an explicit worker thread. A store write busy-waits on SQLite's lock, and on the loop that wait blocks the coroutine holding the lock, so the wait can only ever time out.

**The master key**

- **FR-005**: The Fernet master key MUST live in exactly one of two places: a `0600` file beside the database (the default) or the OS keychain (opt-in). It MUST NOT exist in both as a system of record.
- **FR-006**: Only this spec's `infrastructure/credentials/` package may manage the key, and only its keyring adapter may import `keyring`. No other module — no surface, no other kind, and no CLI command — reaches the keychain.
- **FR-007**: Key resolution MUST read the file first and the keychain second, and MUST create a new key only while the `credentials` table is empty. Resolution order is what makes an interrupted relocation recoverable; the creation rule is what stops a fresh key silently orphaning existing ciphertext.
- **FR-008**: A key that is absent or unusable while ciphertext exists MUST be a fatal `MASTER_KEY_MISSING` naming the expected path, and the daemon MUST NOT start. It MUST NOT write a replacement key over live ciphertext under any condition.
- **FR-009**: Relocating the key MUST write and verify the destination copy before removing the source, so an interruption resolves back to the source location with a harmless duplicate rather than to no key at all.
- **FR-010**: Users MUST be able to read and change the key's location from the management API (`GET`/`PUT /api/v1/settings/credentials`), from the CLI (`coffer credentials storage [--set file|keychain]`), and from a Settings card that states the consequence and confirms before it writes.

**Management API**

- **FR-011**: `POST /api/v1/credentials` MUST store `{ref, value}`, answer `204`, and record a `credential_set` audit entry carrying the ref only.
- **FR-012**: `GET /api/v1/credentials/{ref}` MUST return the decrypted value, record a `credential_read` audit entry carrying the ref only, and answer `404` when the ref is absent — so every deliberate read of a secret leaves a trail.
- **FR-013**: `GET /api/v1/credentials/{ref}/exists` MUST report presence without decrypting, and MUST NOT audit. It is the probe a surface uses when it needs to know whether to ask the user for a value, which is not an access to the secret.
- **FR-014**: `DELETE /api/v1/credentials/{ref}` MUST be idempotent, answer `204` whether or not the ref was present, and record a `credential_deleted` audit entry when it removed something.
- **FR-015**: The delete MUST be refused with `409 CREDENTIAL_IN_USE` while any registered resource's configuration still cites the ref, and the error MUST name every citing resource by kind and current name, so the user knows exactly what to detach first; it MUST NOT identify them by uid, which is the identity the system keeps across a rename and not something the user can recognise on a page ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).

**The command line**

- **FR-016**: `coffer credentials set <ref>` MUST take the secret from standard input, or from a hidden prompt on a terminal, MUST reject an empty value with a non-zero exit, and MUST document `--value` as unsafe because it lands in shell history.
- **FR-017**: `coffer credentials get <ref>` MUST print `[redacted]` by way of the unaudited presence probe, and MUST fetch the real value through the audited read only when `--show` is given.
- **FR-018**: `coffer credentials list` MUST show every credential ref cited by a registered resource together with whether the store currently holds it, so a vault restored without its secrets says which ones are missing.
- **FR-019**: `coffer credentials delete <ref>` MUST confirm before deleting, unless `--force` is given.
- **FR-020**: Every credential command MUST go through the daemon's API and MUST import no credential or keyring code of its own. The daemon is the sole owner of the key, and a CLI that opened the keychain itself would be a second reader to keep honest.

**Credential references**

- **FR-021**: A resource's configuration MUST carry credential references and never secret values. Each kind declares how its refs are extracted from its own config shape; a kind that declares no extractor cites no credentials and is never probed.
- **FR-022**: Any surface that accepts a pasted or typed secret MUST write it into the store first and persist only the resulting ref, so the secret never reaches a resource config even transiently.
- **FR-023**: A credential written for a registration that then fails MUST be removed again, so a failed attempt leaves no entry nothing cites.
- **FR-024**: Deleting a resource MUST release the credential refs that nothing else cites, recording each release. A failed release MUST NOT turn the already-completed deletion into an error — the credential lingers, which is the status quo, rather than the deletion appearing to have failed.
- **FR-025**: Plaintext MUST exist only in memory, between the decrypt that produces it and the process spawn or header injection that consumes it. Nothing may hold it longer, and nothing may write it anywhere.

**Auditing**

- **FR-026**: The events `credential_set`, `credential_read`, `credential_deleted`, `credential_migrated` and `master_key_relocated` MUST carry the ref (or the destination location) only. No audit payload may carry a secret value, and no new credential event may be added that does.

**Legacy keychain migration**

- **FR-027**: At startup the daemon MUST move any pre-0.2 OS-keychain secret into the encrypted store, for cited refs only, auditing each move as `credential_migrated`. It MUST NOT enumerate the keychain, MUST be a no-op once every cited ref is in the store, and MUST NOT block startup on failure — a locked keychain skips that ref and is retried on the next start.

### Key Entities

- **Credential**: One stored secret. Addressed by `ref`; holds Fernet ciphertext plus creation and update timestamps. Nothing else about it is recorded, because anything else would be a place for the secret to leak.
- **Master key**: The single piece of secret material outside the database, in one of two locations. It is never copied into anything the vault publishes.
- **Credential reference**: The string a resource configuration carries in a secret's place. Meaningless to the store, resolved at the moment of use.

## Success Criteria

### Measurable Outcomes

- **SC-001**: No secret value ever appears in any database table, log file, audit entry, or invocation record — verified by an automated scan of those artifacts after a representative session that stores, reads, uses and deletes a credential.
- **SC-002**: A secret can be stored, cited by a resource of any kind that declares credentials, rotated and deleted entirely from the terminal, with no daemon restart at any point.
- **SC-003**: Starting a daemon against ciphertext whose key is absent fails with a message naming the key's expected path, and restoring that key restores access to every previously stored secret.
- **SC-004**: Moving the master key between the file and the OS keychain leaves every stored secret readable, in both directions, across a daemon restart.
- **SC-005**: Deleting a credential that a resource cites is refused with the citing resource named, and no resource is ever left citing a reference the store does not hold as a result of a Coffer-initiated delete.
- **SC-006**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="credentials", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.

## Assumptions

- **This spec ships no web page of its own, and that still satisfies the End-to-End Deliverable Rule.** It delivers a complete CLI (`coffer credentials set|get|list|delete|storage`) and a complete route family (`/api/v1/credentials/*` plus `/api/v1/settings/credentials`) over its own table — persistence plus the surfaces that expose it, wired so a user can really operate the feature. Its only visual surface is Settings → Security, which is the master key's card (FR-010); the secret fields themselves live inside other specs' dialogs, because a secret is entered where the thing that needs it is configured, not on a page of its own. A page listing every stored secret would be a rendering of other specs' configuration, which the spec-division gate rejects.
- **The constitution states the same invariants.** `.specify/memory/constitution.md` asserts ciphertext-only storage, the sole key manager, the file-or-keychain pair, the `keyring` confinement and refs everywhere else as product-wide constraints every kind inherits. This spec is where they become operable behaviour with routes, commands and covering tests; the constitution is where they bind kinds that never read this document.
- **Token auth on this spec's routes is spec daemon's rule.** Every route here requires the daemon's locally minted token and is reachable on loopback only. This spec adds no authentication of its own.
- **Carrying ciphertext to another machine is spec vault-sync's.** Convergence moves `credentials/<ref>.enc` under an explicit opt-in and resolves conflicts freshest-wins, because a Fernet token has no mergeable text. The out-of-band master-key transfer (`/sync/key/export`, `/sync/key/import`) is likewise vault-sync's: this spec owns where the key lives on this machine, not how a user carries it to the next one.
- **The legacy keychain migration is a load-time shim, kept deliberately.** The repo's rule is that a migration leaves no shim behind. FR-027 is the exception on the record: it cannot be replaced by a data migration, because the source is the user's OS keychain rather than a column, and it cannot be proven finished on an install nobody has started yet. It is retired when the pre-0.2 install base is.
- **`coffer credentials list` is narrower today than FR-018 requires.** The command enumerates refs from `mcp_server` resources only, so a channel bot token or a provider API key does not appear even though both kinds declare extractors. FR-018 states the intended behaviour; the narrowing is a known defect to close, not a description of what ships.

## Deliberately out of scope

- **A password manager, or secrets for anything but Coffer's own resources.** The store exists so Coffer's kinds can cite a secret. It has no sharing model, no expiry, no per-agent scope, and no notion of a secret that belongs to something Coffer does not manage.
- **Key rotation.** Re-encrypting every row under a new Fernet key is not offered. The key can be moved, not changed; a user who needs a new key re-enters their secrets, which is a bounded set.
