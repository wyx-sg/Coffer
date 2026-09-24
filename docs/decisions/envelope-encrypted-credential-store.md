# Envelope-Encrypted Credential Store

**Status**: Accepted
**Date**: 2026-06-12
**Deciders**: Yuxing Wu
**Related**: [principles](../../docs-site/architecture/principles.md) (Credentials), [Credential References](credential-references.md), [Credentials Across Machines](credentials-across-machines.md), [Distribution — PyInstaller](distribution-pyinstaller.md) (unsigned macOS distribution), spec credentials, research note [credentials and secrets](../research/credentials-secrets.md)

## Context

Every secret a resource cites ([Credential References](credential-references.md))
has to be stored somewhere on the machine. Coffer first stored each one
directly in the OS keychain (macOS Keychain, Windows Credential Manager, Linux
Secret Service), with the daemon as the sole keychain owner.

On macOS this broke down in daily use. The keychain pins each item's access
control list to the **cdhash** of the binary that created it, and Coffer's
daemon is distributed **unsigned**
([Distribution — PyInstaller](distribution-pyinstaller.md) defers Apple
notarisation, which needs a paid Apple Developer account). Every rebuild — a
developer iterating, or a user receiving an update — produces a new cdhash,
and macOS re-prompts for keychain access **once per secret, on every
rebuild**. The only real fix for the prompt is a stable signing identity, i.e.
a paid Apple Team ID, which a free, self-distributed tool will not gate its
credential UX on.

The store therefore has to work with zero prompts under an unsigned binary,
never write plaintext anywhere, and still offer keychain-grade hardening to
users who want it.

## Options Considered

### Option A — Fernet ciphertext in SQLite, one master key in a `0600` file by default, keychain opt-in (chosen)

Secrets live only as Fernet ciphertext in a `credentials` table in
`~/.coffer/coffer.db` (ref, ciphertext, created and updated times — nothing
else). One Fernet master key opens them, kept in **exactly one** of two
places: `~/.coffer/master.key` (`0600`, the default, zero prompts) or the OS
keychain (service `coffer`, opt-in) (spec credentials "Keep the master key in exactly one place").

- **File-first resolution; create only for an empty store.** The key file is
  read before the keychain. A new key is generated only while the
  `credentials` table is empty, and never while the keychain cannot be read —
  a fresh file key would shadow a keychain key forever
  (spec credentials "Resolve the master key file-first and create it only for an empty store").
  Ciphertext with no usable key is a fatal `MASTER_KEY_MISSING` naming the
  expected path; a locked keychain at start is `CREDENTIAL_LOCKED`. Coffer
  refuses to start rather than silently lose access.
- **Relocate the key, never re-encrypt the data.** Moving between file and
  keychain writes and verifies the destination, then removes the source last,
  so an interruption resolves back to a working key
  (spec credentials "Verify the destination before relocating the master key").
  The ciphertext column is untouched. Exposed as
  `GET`/`PUT /api/v1/settings/credentials`,
  `coffer credentials storage [--set file|keychain]` and the Settings →
  Security card, audited as `master_key_relocated`.
- **One owner of key material.** `MasterKeyManager`
  (`infrastructure/credentials/master_key.py`) is the only code that reads or
  writes the key, and `keyring_adapter.py` the only module that imports
  `keyring`. The CLI goes through the daemon for everything, so each machine
  has one reader of the key.
- **Blocking store, async facade.** `EncryptedCredentialStore` opens a
  short-lived stdlib `sqlite3` connection per call, because MCP spawn and
  register-time probing are synchronous; loop callers use the `aget`/`aset`/…
  facade under `asyncio.to_thread`, since a synchronous call on the loop would
  deadlock against the aiosqlite connection holding the write lock
  (spec credentials "Keep blocking store calls off the event loop").
- **Audited lifecycle.** `credential_set`, `credential_read`,
  `credential_deleted`, `credential_migrated` and `master_key_relocated`, each
  carrying the ref and never the value.
- **One-time legacy migration.** At startup, keychain secrets from the earlier
  design that registered resources still cite are encrypted into the store
  (`run_legacy_keychain_migration`); a locked keychain skips and retries on the
  next start (spec credentials "Migrate legacy keychain secrets once at startup").

Pros: zero keychain prompts by default under an unsigned, frequently rebuilt
binary; at most one prompt per daemon start in keychain mode, for the single
master key; switching storage is crash-safe with no bulk-rewrite window.

Cons: in the default mode the key sits beside the data, so a reader of
`~/.coffer/` (or a copy of it) can decrypt everything. Keychain mode is the
defence against offline exfiltration of that directory; this is stated plainly
so nobody over-trusts the default. `coffer.db` is now useless without its key, so a backup must
include both.

It wins because it is the only design that removes the prompts without a
signing dependency while keeping a real hardening path.

### Option B — Stay on per-secret keychain storage and add code signing

Keep one keychain item per secret and sign the daemon so the ACL survives
rebuilds.

Pros: OS-grade protection for every secret; no key file on disk.

Cons: needs a paid Apple Team ID; self-signed identities do not keep the
cdhash-pinned ACL valid.

Lost: the prompt wall is the out-of-box experience until a paid account
exists, and the project will not depend on one.

### Option C — Keychain as default, file as opt-in

Same envelope design with the defaults reversed.

Pros: the stronger mode by default.

Cons: the re-prompt wall stays the first-run experience on the most common
developer platform.

Lost: the mode that works under an unsigned binary must be the default;
hardening is the opt-in.

### Option D — Derive the key from a user passphrase

Store no key at all; derive it from a passphrase at each daemon start.

Pros: nothing on disk decrypts the store.

Cons: a prompt on every daemon start — including launchd restarts with nobody
at the keyboard — and a forgotten passphrase loses every secret.

Lost: it reintroduces the prompt the change exists to remove; the keychain
opt-in already serves users who want the key off disk.

### Option E — Re-encrypt every row when switching storage mode

Rotate to a new key whenever the key moves between file and keychain.

Pros: a moved key is also a fresh key.

Cons: a bulk rewrite with a half-migrated failure mode and far more code, for
no security gain — the data key is the same secret wherever it lives.

Lost: relocating only the key is small and crash-safe.

## Decision

Secrets are stored only as Fernet ciphertext in the `credentials` table; one
master key, file by default and keychain on opt-in, lives in exactly one place
and is managed solely by `coffer.infrastructure.credentials`. The key is
created only for an empty store, never regenerated over existing ciphertext,
and relocated rather than rotated. The daemon is the only process that holds
it.

## Consequences

- The principles' Credentials clause states this as a product invariant:
  ciphertext only, one key manager, file or keychain, `keyring` confined.
- `keyring` confinement is enforced twice: the import-linter contract
  "keyring confined to infrastructure" (`backend/pyproject.toml`) forbids
  `coffer.surfaces` and `coffer.application` from importing it (the domain
  purity contract covers `coffer.domain`), and the acceptance test
  `test_only_the_keyring_adapter_imports_keyring`
  (`tests/unit/infrastructure/credentials/test_key_location_and_boundaries.py`)
  pins `keyring_adapter.py` as the only importer in the whole tree
  (spec credentials "Confine key management to the credentials package"). A
  further contract, "CLI does not access the keychain directly", keeps
  `coffer.surfaces.cli` away from `coffer.infrastructure.credentials`.
- Carrying the key to another machine is a separate, out-of-band act —
  `coffer sync key export|import` — owned by
  [Credentials Across Machines](credentials-across-machines.md); an import
  never overwrites a different key without first keeping a
  `master.key.bak-*` copy.
- The master key can be moved but not rotated; a user who needs a new key
  re-enters their secrets.
- Rollback of a secret written for a failed registration lives at the writing
  surface, which alone knows whether the registration succeeded
  ([Credential References](credential-references.md)).
