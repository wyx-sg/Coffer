# The Master Key Lives in the macOS Keychain, Readable Only by the Signed Coffer App; Secrets Stay Envelope-Encrypted in the Vault

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](credentials-across-machines.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), [Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md), [principles](../../docs-site/architecture/principles.md) (Credentials; "Not a firewall or security boundary"), research note [credentials and secrets](../research/credentials-secrets.md), spec credentials "Keep the master key in exactly one place", spec credentials "Resolve the master key file-first and create it only for an empty store", spec credentials "Verify the destination before relocating the master key", spec credentials "Expose the master key's location on every surface", spec credentials "Refuse to start when the master key is missing", PR #51, PR #62

## Context

Every Coffer secret is Fernet ciphertext opened by one master key
([Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md)).
By default that key is `~/.coffer/master.key`, a `0600` file beside the data;
the OS keychain is an opt-in. The default was chosen for one reason: Coffer's
binaries were unsigned, and macOS re-prompted for keychain access on every
rebuild.

That reason was measured, not assumed. Two spikes on 2026-06-05 established
that silent keychain access needs both the item's trusted-application list and
its **partition list** to pass. For code without an Apple Team ID — ad-hoc or
self-signed alike — the partition list pins the creating binary's **cdhash**,
so every update re-prompts; creating the item with `/usr/bin/security -T`
instead sets the partition to `apple`, which excludes Coffer's code
altogether. With a Developer ID the partition is `teamid:<Team ID>`, which
every build signed by that team satisfies. The creator reading its own item
within one build is silent either way (PR #51 made the daemon the only
keychain owner for that reason; PR #62 then moved the secrets out of the
keychain into the store).

The 1.0 plan buys the Apple Developer Program, so Coffer's binaries will carry
a Developer ID signature and be notarised. The prompt problem is then gone,
and what is left of the file default is its cost, which the envelope ADR
states itself: "the key sits beside the data, so a reader of `~/.coffer/` (or
a copy of it) can decrypt everything". Readers of that directory are common
and mostly accidental — Time Machine and other backups, cloud-drive and
dotfile tools, an agent's file search. The security page's threat table
already says the offline copy of `~/.coffer/` is protected "only in keychain
mode".

Two things constrain where the key and the secrets go. The vault converges
through a user-owned git remote and carries ciphertext as files under
`vault/credentials/` when the user opts in
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md),
[Credentials Cross Machines Only as Ciphertext](credentials-across-machines.md)).
And platform differences live behind one port, with only macOS shipping
([Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md)).

## Options Considered

### Option A — Keep the file default with a keychain opt-in (today)

- **Pros.** Zero prompts on any build, signed or not; nothing to migrate;
  developer builds from source behave exactly like releases.
- **Cons.** Every copy of `~/.coffer/` is a copy of every secret. The
  hardening exists but almost nobody opts in, so the default is the posture.
  Two storage modes mean a relocation feature, a setting on every surface and
  two resolution paths to keep correct.
- **Why it loses.** Its only advantage over the Keychain was the prompt wall,
  which a Developer ID removes.

### Option B — Every secret in the Keychain

Drop the envelope and store each secret as its own Keychain item under the
signed app's ACL.

- **Pros.** OS-grade protection per secret; no key in any file; each item's
  access is visible in Keychain Access.
- **Cons.** Ciphertext stops being something Coffer holds: the vault could no
  longer carry secrets to the user's other machines as files, and the only
  Keychain-level sync is iCloud Keychain, a vendor cloud as system of record,
  which Local-First forbids. The platform port would need a per-secret store
  on every OS, each with its own limits (Windows Credential Manager caps a
  blob at 2,560 bytes; Linux Secret Service may be absent on a headless
  machine). A backup becomes one entry per secret instead of one key, and the
  store's enumeration, audit and reference counting would be rebuilt on
  keychain queries. Against the threat Coffer defends — secrets leaking by
  accident into copies, transcripts and git — it adds nothing: with the key
  in the Keychain, a copied `vault/credentials/` is already useless.
- **Why it loses.** It gives up vault sync and the portable store for no
  gain against Coffer's threat model.

### Option C — The master key only, in the Keychain, readable only by the signed app (chosen)

- **One item.** A generic-password item in the login keychain, service
  `coffer`, account `master-key`, created by the daemon itself so its
  trusted application is the daemon's own designated requirement (its
  identifier anchored to Coffer's Team ID) and its partition list is
  `teamid:<Team ID>`. Every signed release reads it silently; nothing else
  does without the user's approval in a system prompt. The daemon remains
  the only reader; the CLI, shim, desktop shell and proxy never touch it.
- **Signing is a precondition.** Every shipped binary is signed with the
  Developer ID under the hardened runtime and the archive and `.dmg` are
  notarised. An unsigned build — a developer building from source — can still
  use the item and pays the per-rebuild prompt, or runs under an isolated
  `HOME` with a test-only key backend that release builds do not contain.
- **Never a plaintext file.** There is no file mode and no fallback to one.
  A Keychain that cannot be read at start stops the daemon with
  `CREDENTIAL_LOCKED`, as the keychain mode does today; ciphertext with no
  key stops it with `MASTER_KEY_MISSING`. A new key is created only for an
  empty store.
- **Export only as an explicit backup.** `coffer sync key export <file>`
  remains the one way the key reaches a file: on the user's request, to the
  path they name, mode `0600`, audited as `master_key_exported`. Import
  writes the key into the Keychain, never beside the data. Losing the
  Keychain — a reset login keychain, a new Mac without migration — loses the
  secrets unless such a backup or another machine exists, so the product
  offers the export once after migration and on the Security page.
- **Secrets are unchanged.** Every secret stays Fernet ciphertext in the
  store — as files in `vault/credentials/` once the storage migration lands —
  so sync of ciphertext, the fresher-encryption rule and the reference model
  are untouched.
- **Behind the platform port.** The key's store is a port operation, not a
  macOS call spread through the code. Another OS uses its credential store
  (Windows Credential Manager, Linux Secret Service); a port with no usable
  store is not a supported target until its own decision says what it does.
- **Migration on upgrade.** At the first start of a signed build, a
  `master.key` file is moved into the Keychain: write the item, read it back,
  check that it opens an existing ciphertext and that its fingerprint matches
  the file's, then delete the file. An interruption leaves the file, which
  the next start migrates again. A Keychain item and a file that disagree
  stop the start and name both fingerprints rather than choosing. The move is
  audited as `master_key_relocated`.

- **Pros.** A copy of `~/.coffer/` or of the vault no longer decrypts
  anything; there is one mode, one resolution path and no relocation feature;
  one thing to back up; vault sync and the store's portability are kept; the
  prompt wall does not come back, because the partition is the Team ID.
- **Cons.** A paid Developer Program and a signing and notarisation step in
  every release; developer builds from source re-prompt or need the test-only
  backend; the Keychain becomes a single point of loss that only an explicit
  export or a second machine covers; the platform port has to provide a
  credential store on every OS Coffer will ever ship.
- **Why it wins.** It closes the accidental-copy exposure with one Keychain
  item and changes nothing else in the credential design.

### Option D — Keychain by default with a silent file fallback

Try the Keychain; when it fails, keep the key in a file.

- **Pros.** Never blocks a start.
- **Cons.** The fallback is taken exactly when something is wrong — a locked
  keychain over SSH, an unsigned build — and silently recreates the exposure
  Option C removes; and a key in two places is what the credentials spec's
  "exactly one place" rule exists to prevent, because a second key shadows
  the first.
- **Why it loses.** A silent downgrade is the file default by another path.

### Option E — Derive the key from a passphrase

- **Pros.** Nothing on the machine decrypts the store.
- **Cons.** A prompt at every daemon start, including login-service restarts
  with nobody at the keyboard; a forgotten passphrase loses everything.
- **Why it loses.** It brings back a worse prompt wall than the one a
  Developer ID removes.

## Decision

The master key lives only in the macOS Keychain, in one item created by the
signed daemon, whose access is limited to builds signed with Coffer's
Developer ID (trusted application and `teamid:` partition). It is never a
plaintext file; a file exists only when the user explicitly exports a backup.
Every secret stays Fernet ciphertext in the vault's credential store, opened
by that key. An existing `~/.coffer/master.key` is moved into the Keychain,
verified, and deleted at the first start of a signed build. On other operating
systems the platform port supplies the OS credential store in the Keychain's
place.

Rules a future change must respect:

- No code path writes the master key to disk except the explicit, audited
  export.
- There is no fallback to a file; a Keychain that cannot be read stops the
  start.
- Shipped binaries are signed with the Developer ID and notarised; an
  unsigned release is a release defect.
- Only the daemon reads the key.

## Consequences

- **Revises** [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md)
  where it places the key: its Option A (file default, keychain opt-in)
  becomes an argued option, its rejected Option C (keychain default) is
  adopted without the opt-out, and the relocation feature
  (`credentials.storage`, `PUT /api/v1/settings/credentials`, the Security
  card's toggle) is removed. The envelope, the store and the audit events
  stand.
- **Revises** [Distribution — Three PyInstaller Binaries](distribution-pyinstaller.md):
  binaries are signed and notarised; the release workflow holds the
  Developer ID certificate in CI secrets.
- **Specs.** The credentials requirements "Keep the master key in exactly one
  place", "Resolve the master key file-first and create it only for an empty
  store", "Verify the destination before relocating the master key" and
  "Expose the master key's location on every surface" are rewritten for one
  location and the upgrade migration.
- **Principles.** The Credentials clause's "a `0600` file beside the DB by
  default, the OS keychain via `keyring` when opted in" becomes "the OS
  credential store (the macOS Keychain), readable only by the signed app".
- **Threat model.** The security page's "offline copy of `~/.coffer/`" row
  becomes protected by default. A same-user process still reaches secrets
  through the daemon with the per-start token, so this is not a security
  boundary and the docs keep saying so.
- **Docs.** Install, FAQ, daemon guide, troubleshooting (keychain prompts),
  security and distribution pages drop `master.key` as a file and explain the
  export backup.
