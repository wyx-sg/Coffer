# The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault

**Status**: Accepted
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [principles](../../docs-site/architecture/principles.md) (Secrets), research note [credentials and secrets](../research/credentials-secrets.md), spec secret "Keep the master key in exactly one place", spec secret "Keep the master key behind a storage port chosen by the build", spec secret "Resolve the master key file-first and create it only for an empty store", spec secret "Verify the destination before relocating the master key", spec secret "Read and change the master key's location through the API and Settings", spec secret "Refuse to start when the master key is missing", PR #51, PR #62

## Context

Every Coffer secret is Fernet ciphertext, one file per secret under
`vault/secret/` (or `local/secret/` for a ref that is true of this machine
only), opened by one master key. The ciphertext is the envelope; the question
this ADR answers is where the one key lives, and what a reader of
`~/.coffer/` or a copy of it can do with it.

The historical default was a `0600` file, `~/.coffer/master.key`, beside the
data, with the OS keychain as an opt-in. It was chosen for one reason: Coffer's
binaries were unsigned, and macOS re-prompted for keychain access on every
rebuild. That reason was measured, not assumed. Two spikes on 2026-06-05
established that silent keychain access needs both the item's
trusted-application list and its **partition list** to pass. For code without
an Apple Team ID — ad-hoc or self-signed alike — the partition list pins the
creating binary's **cdhash**, so every update re-prompts; creating the item
with `/usr/bin/security -T` instead sets the partition to `apple`, which
excludes Coffer's code altogether. With a Developer ID the partition is
`teamid:<Team ID>`, which every build signed by that team satisfies. The
creator reading its own item within one build is silent either way (PR #51
made the daemon the only keychain owner for that reason; PR #62 then moved the
secrets out of the keychain into the store).

The 1.0 release carries a Developer ID signature and is notarised. The prompt
problem is then gone for releases, and what is left of the file default is its
cost: the key sits beside the data, so a reader of `~/.coffer/` (or a copy of
it) can decrypt everything. Readers of that directory are common — Time Machine
and other backups, cloud-drive and dotfile tools, an agent's file search — and
one of them is not accidental: a prompt-injected agent running as the user.

That agent is the threat [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
decides against, and it asks more of the key's home than "not a file".
Measured on 2026-09-30 (macOS 15.7.7):

- A **file-based keychain item** trusts applications by code-signing identity.
  Any other same-user process that asks for it — `security
  find-generic-password -w` is enough — gets the system's Allow / Always Allow /
  Deny dialog. **One "Always Allow" adds that binary to the item's list for
  good**, and `/usr/bin/security` on that list opens the item to every script.
  Items written by `/usr/bin/security` itself (as `gh`'s token is, through
  go-keyring) are readable by any same-user process with no prompt at all, from
  inside Claude Code's sandbox too.
- The **data-protection keychain** keys access on an access group, claimed
  through the `keychain-access-groups` entitlement, which only code signed with
  the owning Team ID (with a provisioning profile where the entitlement needs
  one) can carry. A binary outside the group gets no access and **no dialog**:
  there is nothing for a tired human to click. An item may also carry
  `SecAccessControl` flags; `.userPresence` puts Touch ID or the login password
  in front of every read, which is argued below and not adopted.
- Coffer's daemon is a resident login service that a login service restarts
  after a crash with nobody at the keyboard
  ([The Daemon Is Resident](daemon-is-a-resident-login-service.md)). Whatever
  guards the key must not need a person at those moments.
- An ad-hoc daemon without the hardened runtime lets a same-user debugger
  attach and read decrypted secrets from its memory; with the hardened runtime
  and no `get-task-allow`, the attach is refused.

Two things constrain where the key and the secrets go. The vault converges
through a user-owned git remote and carries ciphertext as files under
`vault/secret/` when the user opts in
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md),
[Secrets Cross Machines Only as Ciphertext](secrets-cross-machines-only-as-ciphertext.md)).
And platform differences live behind one port, with only macOS shipping
([Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md)).

## Options Considered

### Option A — A `0600` file beside the data, with the OS keychain as an opt-in

One Fernet key in `~/.coffer/master.key`, or, when the user opts in, in the
login keychain through `keyring` (service `coffer`). The key is read file
first, created only for an empty store, and relocated (written and verified at
the destination, the source removed last), never re-encrypted.

- **Pros.** Zero prompts on any build, signed or not; developer builds from
  source behave like releases; a relocation interrupted anywhere resolves back
  to a working key.
- **Cons.** Every copy of `~/.coffer/` is a copy of every secret, and an agent
  that reads one file holds the master key. The hardening exists but almost
  nobody opts in, so the default is the posture. Two storage modes mean a
  relocation feature, a setting on every surface and two resolution paths to
  keep correct.
- **Why it loses for releases.** Its only advantage over the Keychain was the
  prompt wall, which a Developer ID removes. **It stays the arrangement of a
  development build**, which cannot claim an access group: a build from source
  has no Team ID to sign with, and there the file default and the login-keychain
  opt-in are what run.

### Option B — Every secret in the Keychain

Drop the envelope and store each secret as its own Keychain item under the
signed app's access control. This is also what Coffer first did, with the
daemon as sole keychain owner.

- **Pros.** OS-grade protection per secret; no key in any file; each item's
  access is visible in Keychain Access.
- **Cons.** The prompt wall: an item's access list pins the creating binary,
  so an unsigned daemon re-prompts once per secret on every rebuild, and
  signing only fixes that for releases. Ciphertext stops being something Coffer
  holds: the vault could no longer carry secrets to the user's other machines as
  files, and the only Keychain-level sync is iCloud Keychain, a vendor cloud as
  system of record, which Local-First forbids. The platform port would need a
  per-secret store on every OS, each with its own limits (Windows Credential
  Manager caps a blob at 2,560 bytes; Linux Secret Service may be absent on a
  headless machine). A backup becomes one entry per secret instead of one key,
  and the store's enumeration, audit and reference counting would be rebuilt on
  keychain queries. With one key in an access group no other binary can read
  (Option C), a copied `vault/secret/` is already useless.
- **Why it loses.** It gives up vault sync and the portable store for no gain
  against the threat.

### Option C — The master key only, in a data-protection access group limited to Coffer's Team ID, read silently by Coffer's signed binaries (chosen for signed releases)

- **One item.** A generic-password item in the data-protection keychain,
  service `coffer`, account `master-key`, in the access group `<Team ID>.coffer`
  (stamped into the build by the release pipeline), with **no** user-presence
  flag. Coffer's binaries carry the `keychain-access-groups` entitlement for
  that group (`desktop/entitlements/coffer.entitlements.in`), signed with the
  Developer ID. Any other binary — an agent's own program, `/usr/bin/security`,
  a script — gets no access and no Allow / Always Allow dialog.
- **Silent reads by the signed daemon.** The daemon reads the key at every
  start, including a login-service restart after a crash with nobody at the
  keyboard, and keeps it in memory for its lifetime. There is no prompt and no
  locked state to wait on.
- **Presence gates the operations, not the key.** What lets plaintext out —
  revealing a secret, exporting the master key — and what sends a secret to a
  new destination — approving a new binding — happen only in the desktop app,
  each behind its own LocalAuthentication check (Touch ID or the login
  password) with a reuse window of zero
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).
  The desktop shell reads the key from the same access group (`desktop/src/master_key.rs`)
  to sign each grant, and only reads it.
- **The signed CLI shares the group.** Every signed binary — the app, the
  `coffer` CLI, the daemon and the MCP shim — carries the same entitlement, so
  the CLI could read the key. That is acceptable because no CLI or REST path
  returns plaintext or the key, and the hardened runtime keeps another process
  from attaching to or injecting code into Coffer's signed binaries, so an agent
  cannot make the CLI do what its code does not.
- **Signing is a precondition.** Every shipped binary is signed with the
  Developer ID under the hardened runtime, without `get-task-allow`, and the
  archive and `.dmg` are notarised (`scripts/release_signing.sh` checks each
  binary), so a same-user debugger cannot attach to a process that holds the
  key. The access group is a constant stamped into a frozen build, never a
  setting or an environment variable (`infrastructure/secret/build_identity.py`),
  so nothing an agent can write moves a release's key back into a file.
- **No file mode, no fallback to one, never through the API.** In a signed
  release the key is read from the access-group item only; the key file and the
  login-keychain item are not consulted, and relocating the key to a file is
  refused. No route, command or tool returns the key. Ciphertext with no
  readable key stops the start with `MASTER_KEY_MISSING`; a Keychain that
  refuses the read stops it with `SECRET_LOCKED`. A new key is created only for
  an empty store.
- **Backup is passphrase-protected and presence-gated.** Exporting the key — the
  one way it reaches a file — is a desktop-app action behind a presence check,
  into a folder the person picks. The desktop app signs the grant; the daemon
  writes `coffer-master-key.cfk` (mode `0600`, never over an existing file),
  holding the key encrypted under a key scrypt derives from a passphrase the
  person types, so a stray copy opens nothing on its own, and returns only the
  path and the key's fingerprint. It is audited as `master_key_exported`. Import
  is Settings › Security's **Import a master key**,
  open to every surface, since whoever holds the file and its passphrase holds
  the key; it shows the file's fingerprint beside this machine's before
  replacing anything, and a different key already installed is kept as a second
  Keychain item, never as a file. Losing the Keychain — a reset login keychain,
  a new Mac without migration — loses the secrets unless such a backup or
  another machine exists.
- **Secrets are unchanged.** Every secret stays Fernet ciphertext as a file in
  `vault/secret/`, so sync of ciphertext, the fresher-encryption rule and the
  reference model are untouched.
- **Behind the platform port.** The key's store is a port operation
  (`infrastructure/secret/master_key_backends.py`), not a macOS call spread
  through the code. Another OS would use its own credential store; a port with
  no store that limits reads to Coffer's own signed code is not a supported
  target until its own decision says what it does.

- **Pros.** A copy of `~/.coffer/` or of the vault decrypts nothing; no binary
  outside Coffer's signed family reads the key, and there is no dialog a
  reflexive click could turn into access; the daemon starts and restarts
  unattended; one resolution path in a release; one thing to back up; vault sync
  and the store's portability are kept.
- **Cons.** A paid Developer Program, the entitlement (and a provisioning
  profile where needed), and a signing and notarisation step in every release.
  Developer builds from source cannot use it. The Keychain becomes a single point
  of loss that only an explicit export or a second machine covers. The key's
  protection rests on the integrity of Coffer's signed binaries: a defect that
  made one of them print the key would expose it, which is why "no path returns
  the key" is a rule, not a convention.
- **Why it wins.** It is the only placement in which no same-user binary other
  than Coffer's can read the key or be let in by one click, without making the
  resident daemon wait for a person.

### Option D — Option C plus a presence check on every read of the key

Put `.userPresence` on the item, so every read — the daemon's included —
needs Touch ID or the login password, and the Keychain itself becomes the
presence gate for reveals and approvals.

- **Pros.** One mechanism for both jobs; even Coffer's own binaries cannot
  read the key without a person.
- **Cons.** A prompt at every daemon start — at login, after an upgrade, after
  every crash restart — and a daemon restarted by the login service with
  nobody at the keyboard runs **locked** until someone answers: every MCP
  server, channel and provider that needs a secret stops working unattended,
  which is exactly when a resident daemon exists to keep them running. It
  also needs the daemon to raise a system prompt from a background login
  service. The protection it adds over Option C — against Coffer's own signed
  binaries — is covered by the rule that none of them returns the key.
- **Why it loses.** It trades the resident daemon's unattended operation for
  protection Option C already gets from the access group and the hardened
  runtime. Presence belongs on the operations that let plaintext out, not on
  the key.

### Option E — The master key in a file-based Keychain item trusted to the signed daemon

A login-keychain item created by the daemon, trusted to its designated
requirement, with partition `teamid:<Team ID>`, read without a prompt by every
signed release.

- **Pros.** No prompt; no entitlement or provisioning profile; the daemon can
  run from the CLI archive as a bare binary.
- **Cons.** Any other same-user process that asks gets the Allow / Always
  Allow / Deny dialog, and an agent can ask as often as it likes; one "Always
  Allow" opens the key to that binary for good.
- **Why it loses.** Against a same-user agent its protection is one click deep;
  the data-protection access group shows no dialog at all.

### Option F — Keychain by default with a silent file fallback

Try the Keychain; when it fails, keep the key in a file.

- **Pros.** Never blocks a start.
- **Cons.** The fallback is taken exactly when something is wrong — a locked
  keychain over SSH, an unsigned build — and silently recreates the exposure
  Option C removes; and a key in two places is what the secret spec's "exactly
  one place" rule exists to prevent, because a second key shadows the first.
- **Why it loses.** A silent downgrade is the file default by another path.

### Option G — Derive the key from a passphrase

Store no key at all; derive it from a passphrase at each daemon start.

- **Pros.** Nothing on the machine decrypts the store.
- **Cons.** A typed passphrase at every daemon start, including unattended
  restarts, and a forgotten passphrase loses everything.
- **Why it loses.** It is Option D's locked daemon with a worse answer to the
  prompt. The passphrase survives in one place only, protecting the exported
  backup.

### Option H — Re-encrypt every secret when the key moves or changes

Rotate to a new key whenever the key moves between homes, so a moved key is
also a fresh key.

- **Pros.** A moved key is also a fresh key.
- **Cons.** A bulk rewrite of every ciphertext file with a half-migrated
  failure mode and far more code, for no security gain: the data key is the same
  secret wherever it lives.
- **Why it loses.** Relocating only the key is small and crash-safe: the
  destination is written and verified, the source removed last, and an
  interrupted move resolves back to the source. The key can be moved but not
  rotated; a user who needs a new key re-enters their secrets.

## Decision

In a signed release the master key lives only in the macOS data-protection
Keychain, in one item in an access group limited to Coffer's Team ID, with no
user-presence flag. Coffer's Developer-ID-signed binaries carry that group's
entitlement; the daemon reads the key silently at every start, attended or
not, and no other binary can read it or be offered a dialog to allow it. Human
presence — a LocalAuthentication check in the desktop app, with no reuse
window — gates the operations that let plaintext out or bind a secret to a new
destination, not the key. The key is never a plaintext file in a release, never
returned by any route, and reaches a file only when the user exports a
passphrase-protected backup through the desktop app. Every secret stays Fernet
ciphertext in the vault, opened by that key.

A build from source cannot claim the access group. It is a development build
and keeps the earlier arrangement: a `0600` file in `~/.coffer/` by default, or
the login keychain when opted in, with the verified relocation between them.
It reports itself as development, and it does not hold the secret boundary:
any same-user process can read the key. Which arrangement a daemon runs is
decided by how it was built, never by a setting.

Rules a future change must respect:

- No code path writes the master key to disk in a signed release except the
  presence-gated, passphrase-protected, audited backup, and no route or
  command returns it.
- A signed release has no fallback to a file.
- Only binaries signed with Coffer's Developer ID carry the access-group
  entitlement; shipped binaries are signed under the hardened runtime without
  `get-task-allow` and notarised, and an unsigned release is a release defect.
- The key item carries no presence flag; presence is checked on the operations
  that let plaintext out or bind a secret to a new destination.
- The choice between the two arrangements is a build-time constant, never a
  setting or an environment variable.

## Consequences

- The principles' Secrets clause states the placement: the Keychain access
  group in a signed release, the file or login keychain in a development
  build. `keyring` stays imported only by the secret package's keyring adapter.
- Binaries are signed under the hardened runtime with the access-group
  entitlement and notarised; the release workflow holds the Developer ID
  certificate in CI secrets ([Distribution](distribution-pyinstaller.md)).
- The relocation feature survives for development builds only
  (`secrets.storage`, `GET`/`PUT /api/v1/settings/secrets`, the Security card's
  toggle) and is refused by a signed release, so the same three surfaces report
  `keychain_access_group` there.
- The threat model: an offline copy of `~/.coffer/` is protected in a release,
  and a same-user process reaches the key through neither a file, a route nor an
  "Always Allow". What a same-user agent can still reach is listed in
  [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md).
- Not built yet: proof that the access-group entitlement works for the bare
  frozen `coffer-daemon` the CLI archive ships, outside an app bundle (it may
  need a provisioning profile, which only an app bundle carries). If it does
  not, the daemon runs from inside the signed app bundle, a CLI-only install
  without the app can use Coffer but holds no secrets, and the distribution ADR
  is changed to say so.
- Not built yet: the migration of an existing `master.key` file or login-keychain
  item into the access group at a signed build's first start. A signed build
  that finds ciphertext and no item in the group stops with `MASTER_KEY_MISSING`;
  the way in is **Import a master key** of a backup.
- Not built yet: a fake-free test of the access-group backend. Its Keychain
  calls are exercised through an injected fake; on an unsigned build the real
  calls fail with a missing-entitlement error.
- Not decided: which credential store another operating system's port would use.
