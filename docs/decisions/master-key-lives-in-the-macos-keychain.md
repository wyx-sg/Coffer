# The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault

**Status**: Proposed
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](credentials-across-machines.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), [Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md), [principles](../../docs-site/architecture/principles.md) (Credentials; "Not a firewall or security boundary"; an amendment to both is proposed separately), research note [credentials and secrets](../research/credentials-secrets.md), spec secret "Keep the master key in exactly one place", spec secret "Resolve the master key file-first and create it only for an empty store", spec secret "Verify the destination before relocating the master key", spec secret "Expose the master key's location on every surface", spec secret "Refuse to start when the master key is missing", PR #51, PR #62

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
a copy of it) can decrypt everything". Readers of that directory are common —
Time Machine and other backups, cloud-drive and dotfile tools, an agent's file
search — and one of them is not accidental: a prompt-injected agent running as
the user.

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
[Credentials Cross Machines Only as Ciphertext](credentials-across-machines.md)).
And platform differences live behind one port, with only macOS shipping
([Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md)).

## Options Considered

### Option A — Keep the file default with a keychain opt-in (today)

- **Pros.** Zero prompts on any build, signed or not; nothing to migrate;
  developer builds from source behave exactly like releases.
- **Cons.** Every copy of `~/.coffer/` is a copy of every secret, and an agent
  that reads one file holds the master key. The hardening exists but almost
  nobody opts in, so the default is the posture. Two storage modes mean a
  relocation feature, a setting on every surface and two resolution paths to
  keep correct.
- **Why it loses.** Its only advantage over the Keychain was the prompt wall,
  which a Developer ID removes.

### Option B — Every secret in the Keychain

Drop the envelope and store each secret as its own Keychain item under the
signed app's access control.

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
  keychain queries. With one key in an access group no other binary can read
  (Option C), a copied `vault/secret/` is already useless.
- **Why it loses.** It gives up vault sync and the portable store for no gain
  against the threat.

### Option C — The master key only, in a data-protection access group limited to Coffer's Team ID, read silently by Coffer's signed binaries (chosen)

- **One item.** A generic-password item in the data-protection keychain,
  service `coffer`, account `master-key`, in the access group
  `<Team ID>.coffer`, with **no** user-presence flag. Coffer's binaries carry
  the `keychain-access-groups` entitlement for that group, signed with the
  Developer ID (and a provisioning profile where the entitlement requires one).
  Any other binary — an agent's own program, `/usr/bin/security`, a script —
  gets no access and no Allow / Always Allow dialog.
- **Silent reads by the signed daemon.** The daemon reads the key at every
  start, including a login-service restart after a crash with nobody at the
  keyboard, and keeps it in memory for its lifetime. There is no prompt and no
  locked state.
- **Presence gates the operations, not the key.** What lets plaintext out —
  revealing, copying or exporting a secret, exporting the master key — and
  what sends a secret to a new destination — signing the approval of a new
  binding — happen only in the desktop app, each behind its own
  LocalAuthentication check (Touch ID or the login password) with a reuse
  window of zero
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).
  The desktop app reads the key from the same access group for those
  operations.
- **The signed CLI shares the group.** The `coffer` CLI is signed into the same
  access group, so it could read the key. That is acceptable because no CLI or
  REST path returns plaintext or the key, and the hardened runtime keeps
  another process from attaching to or injecting code into Coffer's signed
  binaries, so an agent cannot make the CLI do what its code does not.
- **Signing is a precondition.** Every shipped binary is signed with the
  Developer ID under the hardened runtime, without `get-task-allow`, and the
  archive and `.dmg` are notarised, so a same-user debugger cannot attach to a
  process that holds the key. An unsigned build — a developer building from
  source — cannot claim the access group, and runs under an isolated `HOME`
  with a test-only key backend that release builds do not contain.
- **Never a plaintext file, never through the API.** There is no file mode and
  no fallback to one. No route, command or tool returns the key. Ciphertext
  with no readable key stops the start with `MASTER_KEY_MISSING`; a Keychain
  that refuses the read stops it with `CREDENTIAL_LOCKED`. A new key is
  created only for an empty store.
- **Export and import only in the desktop app.** Exporting the key as a
  backup — the one way it reaches a file — is a desktop-app action behind a
  presence check, to a path the user picks, mode `0600`, audited as
  `master_key_exported`. `coffer sync key export` is removed. Import, also in
  the desktop app, writes the key into the Keychain item and refuses a key that
  does not open the store's existing ciphertext. Losing the Keychain — a reset
  login keychain, a new Mac without migration — loses the secrets unless such a
  backup or another machine exists, so the product offers the export once after
  migration and on the Security page.
- **Secrets are unchanged.** Every secret stays Fernet ciphertext in the
  store — as files in `vault/secret/` once the storage migration lands —
  so sync of ciphertext, the fresher-encryption rule and the reference model
  are untouched.
- **Behind the platform port.** The key's store is a port operation, not a
  macOS call spread through the code. Another OS uses its own credential store;
  a port with no store that limits reads to Coffer's own signed code is not a
  supported target until its own decision says what it does.
- **Migration on upgrade.** At the first start of a signed build, a
  `master.key` file, or a key in the old file-based keychain item, is moved
  into the new item: write the item, read it back, check that it opens an
  existing ciphertext and that its fingerprint matches the source's, then
  delete the source. An interruption leaves the source, which the next start
  migrates again. A new item and a source that disagree stop the start and
  name both fingerprints rather than choosing. The move is audited as
  `master_key_relocated`.

- **Pros.** A copy of `~/.coffer/` or of the vault decrypts nothing; no binary
  outside Coffer's signed family reads the key, and there is no dialog a
  reflexive click could turn into access; the daemon starts and restarts
  unattended; one mode, one resolution path, no relocation feature; one thing
  to back up; vault sync and the store's portability are kept.
- **Cons.** A paid Developer Program, the entitlement (and a provisioning
  profile where needed), and a signing and notarisation step in every release.
  Developer builds from source need the test-only backend. The Keychain
  becomes a single point of loss that only an explicit export or a second
  machine covers. The key's protection rests on the integrity of Coffer's
  signed binaries: a defect that made one of them print the key would expose
  it, which is why "no path returns the key" is a rule, not a convention.
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
  run from the CLI archive as it does today.
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
  Option C removes; and a key in two places is what the credentials spec's
  "exactly one place" rule exists to prevent, because a second key shadows
  the first.
- **Why it loses.** A silent downgrade is the file default by another path.

### Option G — Derive the key from a passphrase

- **Pros.** Nothing on the machine decrypts the store.
- **Cons.** A typed passphrase at every daemon start, including unattended
  restarts, and a forgotten passphrase loses everything.
- **Why it loses.** It is Option D's locked daemon with a worse answer to the
  prompt.

## Decision

The master key lives only in the macOS data-protection Keychain, in one item
in an access group limited to Coffer's Team ID, with no user-presence flag.
Coffer's Developer-ID-signed binaries carry that group's entitlement; the
daemon reads the key silently at every start, attended or not, and no other
binary can read it or be offered a dialog to allow it. Human presence — a
LocalAuthentication check in the desktop app, with no reuse window — gates the
operations that let plaintext out or bind a secret to a new destination, not
the key. The key is never a plaintext file, never returned by any route, and
reaches a file only when the user exports a backup in the desktop app. Every
secret stays Fernet ciphertext in the vault's credential store, opened by that
key. An existing `~/.coffer/master.key` or old keychain item is moved into the
new item, verified, and deleted at the first start of a signed build. On other
operating systems the platform port supplies a credential store limited to
Coffer's signed code in the Keychain's place.

Rules a future change must respect:

- No code path writes the master key to disk except the desktop app's explicit,
  presence-gated, audited export, and no route or command returns it.
- There is no fallback to a file.
- Only binaries signed with Coffer's Developer ID carry the access-group
  entitlement; shipped binaries are signed under the hardened runtime without
  `get-task-allow` and notarised, and an unsigned release is a release defect.
- The key item carries no presence flag; presence is checked on the operations
  that let plaintext out or bind a secret to a new destination.

## Consequences

- **Revises** [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md)
  where it places the key: its Option A (file default, keychain opt-in)
  becomes an argued option, its rejected Option C (keychain default) is
  adopted without the opt-out, and the relocation feature
  (`credentials.storage`, `PUT /api/v1/settings/credentials`, the Security
  card's toggle) is removed. The envelope, the store and the audit events
  stand.
- **Revises** [Distribution — Three PyInstaller Binaries](distribution-pyinstaller.md):
  binaries are signed under the hardened runtime with the access-group
  entitlement and notarised; the release workflow holds the Developer ID
  certificate (and the provisioning profile, if needed) in CI secrets.
- **To prove before acceptance.** A spike on a Developer-ID build must show
  that the access-group entitlement works for the daemon as the bare frozen
  binary the CLI archive ships, outside an app bundle. If it does not, the
  daemon runs from inside the signed app bundle, and a CLI-only install
  without the app can use Coffer but holds no secrets; this ADR and the
  distribution ADR are revised to say which.
- **Specs.** The credentials requirements "Keep the master key in exactly one
  place", "Resolve the master key file-first and create it only for an empty
  store", "Verify the destination before relocating the master key" and
  "Expose the master key's location on every surface" are rewritten for one
  location and the upgrade migration; vault-sync's `key export` and `key
  import` move to the desktop app.
- **Principles** (an amendment proposed in its own change). The Credentials clause's "a `0600` file beside the DB by
  default, the OS keychain via `keyring` when opted in" becomes "the OS
  credential store (the macOS Keychain), readable only by Coffer's signed
  binaries".
- **Threat model.** The security page's "offline copy of `~/.coffer/`" row
  becomes protected by default, and a same-user process no longer reaches the
  key through a file, a route or an "Always Allow". What a same-user agent can
  still reach is listed in
  [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md).
- **Docs.** Install, FAQ, daemon guide, troubleshooting (keychain prompts),
  security and distribution pages drop `master.key` as a file and explain the
  export backup.

## Open questions

Recorded 2026-09-30, when the storage port and the access-group backend were
built (OpenSpec change `add-secret-boundary`, design D6):

- **The access-group spike is still owed.** Nobody has yet shown that a
  Developer-ID-signed **bare** `coffer-daemon` — the frozen binary the CLI
  archive ships, outside an app bundle — can use the `keychain-access-groups`
  entitlement. It may need a provisioning profile, which only an app bundle
  carries. "To prove before acceptance" above stands; if the spike fails, the
  daemon runs from inside the signed app bundle and this ADR and the
  distribution ADR are revised to say so.
- **The backend is tested only with an injected fake.** The data-protection
  Keychain backend (service `coffer`, account `master-key`, the stamped access
  group, `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, no access-control
  flag) sits behind the master-key storage port, selected by an access group
  the release pipeline stamps into a frozen, signed build. Its Keychain calls
  are exercised only through a fake; on an unsigned build the real calls fail
  with a missing-entitlement error, and they have not been run against a real
  Keychain.
- **Until the signed build exists, the development fallback is what runs.** A
  build without the stamp keeps the key in the `0600` file (or the legacy
  login-keychain item, opt-in), exactly as before, and reports itself as a
  development build. "There is no fallback to a file" and "never a plaintext
  file" therefore hold for **signed releases only**; in a development build any
  same-user process can read the key, and the presence grant of
  [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
  can be forged. The "test-only key backend that release builds do not contain"
  is, as built, that development arrangement rather than a separate backend.
- **As built, the backup is written by the daemon, not the app.** The desktop
  app runs the presence check and signs a grant; the daemon writes the backup
  into the folder the person picked (`coffer-master-key.cfk`, mode `0600`,
  never over an existing file) and returns only the path and the fingerprint.
  Since 2026-09-30 the file holds the key encrypted under a key scrypt derives
  from a passphrase the person types in the app, so a stray copy opens nothing
  on its own (OpenSpec change `add-master-key-import-to-security`). Import is
  `coffer sync key import` and Settings › Security's **Import a master key**,
  open to every surface, since whoever holds the file and its passphrase holds
  the key; it shows the file's key fingerprint beside this machine's before
  replacing anything.
