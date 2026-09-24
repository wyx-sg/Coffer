# Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository

**Status**: Accepted
**Date**: 2026-09-23
**Deciders**: Yuxing Wu
**Related**: [Vault Sync](vault-sync.md), [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credential References](credential-references.md), [Sync Machine Identity](sync-machine-identity.md), [principles](../../docs-site/architecture/principles.md) (Credentials), spec vault-sync, spec credentials, research note [credentials and secrets](../research/credentials-secrets.md), PRs #293, #381, #415

## Context

Resources that [converge](vault-sync.md) carry
[credential references](credential-references.md), never secrets. A reference
that arrives on a machine without the secret behind it is a broken resource, so
convergence has to answer how secrets themselves reach the other machine — and
it involves two secrets that are not vault content at all:

- **The credential store's secrets.** On each machine they are Fernet
  ciphertext in the `credentials` table, opened by one master key kept in a
  `0600` file or the OS keychain
  ([Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md)).
  The remote is a git repository the user owns, but it may be hosted by a
  forge, shared, or a USB stick that gets lost.
- **The push credential** that lets git authenticate to that remote, itself a
  secret in the store, named on the remote's configuration by reference.

Two incidents bound the design. On 2026-07-10 a machine re-exported a
months-old orphaned credential blob and won the merge simply by syncing last
(PR #293), so "which ciphertext is current" cannot be decided by commit order.
And in 2026-09 sync on macOS failed hourly with `unable to get password from
user`: the push token was handed to git through `GIT_ASKPASS`, which Apple's
git ignores, and the only thing that had ever authenticated was the
`credential.helper = osxkeychain` line in Xcode's system gitconfig — which
Coffer deliberately pins away (PR #415).

## Options Considered

### Option A — Opt-in ciphertext in the repository; the key moved out of band; the push token through a credential helper (chosen)

**Secrets.** When the remote is configured to carry them
(`include_credentials` on the remote, default off, fixed per remote rather than
per round), each ref travels as its raw Fernet ciphertext at
`credentials/<ref>.enc` — read and written without the master key, so neither
direction of a round touches plaintext (`infrastructure/sync/credentials.py`;
spec vault-sync "Carry credentials as ciphertext only"). Two ciphertexts for one
ref never reach a text merge: a Fernet token carries its encryption time in
cleartext, so they are ordered without the key and **the fresher encryption
wins**, whichever commit is newer (`domain/sync/fernet_time.py`;
spec vault-sync "Let the fresher credential ciphertext win"). A header that will
not parse leaves the conflict unsettled rather than guessed.

**The master key.** It is never written into the repository
(spec vault-sync "Never write the master key into the repository"). A user
carries it once per machine, out of band: `coffer sync key export <file>`
writes it to a `0600` file, `coffer sync key import <file>` installs it, and
`coffer sync key fingerprint` prints a 12-character SHA-256 prefix to compare
(`surfaces/cli/sync_machine_cmd.py`; `/api/v1/sync/key/export`, `/import`,
`/fingerprint`). Export and import are audited (`master_key_exported`,
`master_key_imported`). An import that would replace a different key first
copies the old one to a timestamped `master.key.bak-*` sibling, because the
file being replaced may be the only copy that opens existing ciphertext. Each
machine publishes its fingerprint in its descriptor
([Sync Machine Identity](sync-machine-identity.md)), so the machines table says
outright which peers' credentials will not decrypt here. Until the key is
present, arrived refs are reported **locked**; a key that exists but cannot be
read right now reports none locked and logs why, and the key is resolved at
most once per daemon start (spec vault-sync "Report refs without a key as locked").

**The push token.** It is resolved from the store at push time and reaches git
as a **credential helper** passed with `-c` — a shell snippet that answers
`get` from the `COFFER_GIT_TOKEN` environment variable of that one git process
(`infrastructure/sync/git_invoke.py`;
spec vault-sync "Hand the push credential to git as a helper"). Every git
invocation runs with `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` pointed at
`/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, inherited
`GIT_ASKPASS`/`SSH_ASKPASS` removed, and an empty `credential.helper` first so
no helper the user configured can answer ahead of Coffer's or record the
token. The token is never in argv (the helper names the variable, not its
value), never in the remote URL, never in `.git/config`, and every captured
error is redacted before it is raised or recorded.

Pros: a stolen or public remote yields ciphertext only; the ordering rule
needs no key and cannot be won by syncing last; the push works identically on
every platform's git and is independent of whatever the user's own git
configuration happens to hold.

Cons: one manual step per new machine (export, carry, import); a user who never
does it holds locked refs; the master key is one shared secret across the
fleet, so one compromised machine opens every machine's ciphertext.

It wins because it adds no new cryptographic machinery, keeps the repository
harmless on its own, and makes the one manual step visible (locked refs,
fingerprint mismatch) instead of silent.

### Option B — The master key wrapped by a passphrase, stored in the repository

Encrypt the master key with a key derived from a user passphrase and commit
the wrapped key, so a new machine needs only the passphrase.

Pros: no file to carry; the repository is self-contained.

Cons: the repository now holds everything an attacker needs except a
human-chosen passphrase, which an offline attacker can grind at leisure. It
also reintroduces a prompt the credential store was designed to avoid, and a
forgotten passphrase loses every secret.

Lost: it turns "the remote holds nothing usable" into "the remote holds
everything behind a guessable secret".

### Option C — Re-encrypt each secret to every machine's public key (age-style)

Each machine owns a key pair and publishes its public key; secrets are
encrypted once per recipient.

Pros: no shared symmetric key; revoking a machine is possible; a compromised
machine does not open other machines' private keys.

Cons: every write to a secret must re-encrypt it for every known machine, and a
machine that joins later sees nothing until another machine re-encrypts the
whole store for it — a coordination step convergence has no place for. Two
machines re-encrypting concurrently produce ciphertext sets that no rule
orders. It replaces Fernet, the store format, and the conflict rule at once.

Lost: large surface for a threat (one machine of a single user's fleet turning
hostile) the product does not model.

### Option D — Rely on OS keychain sync (iCloud Keychain and similar)

Keep the master key in the OS keychain and let the platform sync it.

Pros: no manual step for users on one platform ecosystem.

Cons: macOS-only in practice, and the credential store's default is the file
precisely because an unsigned binary cannot use the keychain without repeated
prompts ([Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md));
synchronizable items need entitlements an unsigned, self-distributed daemon
does not have. Linux machines would be left out.

Lost: not available to the distribution Coffer ships.

### Option E — Never carry credentials; re-enter secrets on each machine

Sync references only, and let each machine's user type each secret again.

Pros: no secret, however encrypted, ever leaves the machine.

Cons: every arriving resource is broken until someone re-enters its secret, and
rotating a token means repeating it on every machine.

Kept as the **default** (`include_credentials` is off until the user opts in),
lost as the only mode: a user who has chosen a private remote they trust
should not pay that cost.

### Option F — Hand the push token to git through `GIT_ASKPASS`

Set `GIT_ASKPASS` to a helper script that prints the token when git prompts.

Pros: standard for scripted git; the token stays out of argv and config.

Cons: `GIT_ASKPASS` is a prompt path, consulted only when git decides to
prompt, and macOS's own git answers `fatal: unable to get password from user`
without ever running it. It appeared to work only while a system-level
`osxkeychain` helper answered first — the configuration Coffer pins away.

Lost on PR #415, after sync failed on every macOS machine that relied on it.

### Option G — Token in the remote URL, or the user's own git credentials

Embed the token as `https://token@host/...`, or leave authentication to the
user's configured helper or SSH agent.

Pros: zero Coffer code.

Cons: a URL token lands in `.git/config`, in process listings and in every
error git echoes back. Deferring to the user's git configuration means the
daemon's behaviour depends on files Coffer does not control, which is why each
invocation pins them away.

Lost: the first leaks the token; the second makes the round non-reproducible.
An SSH remote still authenticates through the user's SSH agent, which the
pinned git configuration does not affect.

## Decision

Secrets cross machines only as Fernet ciphertext, only on a remote configured
to carry them, and two ciphertexts for one ref are ordered by their cleartext
encryption time. The master key never enters the repository; the user moves it
with `coffer sync key export|import`, compares with `fingerprint`, and an
import never overwrites a different key without keeping a `master.key.bak-*`.
The push token reaches git only through a per-invocation credential helper
reading an environment variable, with the user's global and system git
configuration isolated.

## Consequences

- A remote on its own discloses resource definitions and ciphertext, never a
  usable secret.
- Setting up a second machine is: adopt the remote, import the key. Until the
  second step, the Sync page and `coffer sync` report the locked refs.
- Deleting a resource releases the credentials nothing else cites, on every
  machine, so an orphaned blob cannot be re-seeded by a later export
  ([Credential References](credential-references.md)).
- A new git operation added to the sync adapter inherits the pinned
  configuration and redaction automatically, because both live in the single
  `run_git` entry point rather than per command.
- Rotating the master key is not offered: re-encrypting every row on every
  machine is the coordination Option C was rejected for.
