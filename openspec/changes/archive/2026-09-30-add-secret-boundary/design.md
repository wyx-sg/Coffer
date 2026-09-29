# Design: the secret boundary

The decision and its alternatives are in the ADRs
[only-a-present-human-sees-a-secret-or-sends-it-somewhere-new](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md),
[master-key-lives-in-the-macos-keychain](../../../docs/decisions/master-key-lives-in-the-macos-keychain.md) and
[standalone-secrets-are-named-references-injected-into-one-child](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md).
This file records how the implementation meets them, and the choices the ADRs
leave open.

## D1. The presence grant

The daemon holds the master key; the desktop shell is the only one of Coffer's
binaries whose code runs a presence check. The grant joins the two.

- **Key.** `grant_key = HMAC-SHA256(key = master_key_bytes, msg =
  "coffer-presence-grant-key/v1")`, where `master_key_bytes` is the Fernet key's
  base64 text with surrounding whitespace stripped. The grant key is derived on
  demand, never stored, never the master key itself.
- **Challenge.** `POST /api/v1/credentials/presence/challenge {op, target}` →
  `{nonce, op, target, expires_in_seconds}`. `op` is one of `reveal`,
  `approve`, `export_master_key`; `target` is the ref, the approval id, or the
  directory. A nonce lives 120 s, at most 64 are outstanding, and it is
  consumed by the first redeem **whether or not the signature verifies**.
- **Signature.** `hex(HMAC-SHA256(grant_key, "coffer-presence-grant/v1\n" + op
  + "\n" + target + "\n" + nonce))`, lower-case, 64 hex digits, sent as
  `{nonce, signature}` beside the operation's own fields.
- **Order in the shell.** Presence check first (a fresh `LAContext` per
  operation, policy `deviceOwnerAuthentication`, the localized reason naming
  the operation and its target so the *operating system* shows what is being
  approved), then challenge, sign, and the operation's request. A cancelled or
  failed check sends nothing.
- **Test vector** (shared by the Python and Rust tests): master key
  `ZmFrZS1tYXN0ZXIta2V5LWZvci10ZXN0cy0wMDAwMDA=` →
  grant key `84cccae592fbe9961c40a663f512eaa2045d99f3ccd974e92fddbf8ea4492347`;
  `(reveal, gh/token, nonce-123)` →
  `8654e8c12fcba0b8617f06e3c84c9636ab6d5a0a3b5221d531d1dc08c7a6cd50`;
  `(approve, 0123456789abcdef, nonce-456)` →
  `13c3e5b98ae8c394f98b1f1631ac06e4d886b604876383fc29aee12b6118892c`;
  `(export_master_key, /Users/me/Backups, nonce-789)` →
  `2382008c76facbd67f01aacbf1da779c690ae654af87f9a8bf5ade889cfba3bd`.

**Production path.** The master key sits in the data-protection Keychain, access
group `<TEAMID>.coffer`, readable only by binaries signed with that Team ID and
carrying the `keychain-access-groups` entitlement. The shell reads it from the
same item (`kSecUseDataProtectionKeychain`, service `coffer`, account
`master-key`) to derive the grant key. A process an agent controls cannot read
the item, so it cannot sign a grant; the signed CLI could read it, but no CLI
code path signs one, and the hardened runtime keeps other processes from
attaching to or injecting into the signed binaries.

**Development fallback — clearly marked.** A build without the stamped access
group (every build from source, and every build until the Developer ID exists)
keeps the key in `~/.coffer/master.key` (or the legacy login-keychain item),
and the shell derives the grant key from that file. Any same-user process can
read that file, so **in a development build a grant can be forged and the
boundary does not hold**. `GET /api/v1/credentials/presence/status` answers
`development: true`, the shell titles every presence prompt "Development
build", and the docs say so. The shell still requires an interactive
confirmation in the app window before signing: LocalAuthentication when the
Mac has it, otherwise (dev builds only) a modal alert in the app window.

## D2. Destinations, targets and bindings

A binding is `(ref, destination_kind, destination_uid, slot)` approved for one
**target fingerprint** (`sha256(target)[:32]`). The target is what receives the
value, written so a person can read it in the approval:

| Destination | Slot | Target |
| --- | --- | --- |
| stdio MCP server | env var | `stdio <command args…> [in <cwd>] [with K=V …]` — the non-secret env is part of it, since `NODE_OPTIONS=--require …` changes what the process does |
| HTTP MCP server | header | `http <url>` |
| Telegram channel | `token` | `telegram bot` |
| SeaTalk channel | `secret` | `seatalk app <app_id>` |
| Sync remote | `token` | `git <url>` |
| Provider connection | `key` | `model api <base url>` — the proxy state and the engine ask before they get the key |
| Custom tool (later) | its auth slot | its base URL — same call |

`CredentialResolver.materialize(refs, destination)` asks
`SecretBoundary.require(destination, refs)` before it reads a value; a guarded
resolver (every one the composition root builds) refuses a call without a
destination. `require` returns when every slot is approved, and otherwise
records a pending approval per slot and raises `SECRET_BINDING_PENDING` (409)
naming the approval ids. Nothing is injected. A new target supersedes the
pending approval for the old one.

**When a binding is approved without a person:**

1. **Adoption.** At the first start on revision 0112 every binding in use is
   approved once, through the same enumeration that computes targets at use, and
   a marker row stops it running again. Upgrading breaks nothing that worked.
2. **A value supplied for it.** The ADR's "a binding whose secret value was
   supplied in the same call" is implemented as: the ref has never been bound
   anywhere, is not a standalone `secret/` name, and was stored within the last
   five minutes. Every surface that registers a resource with a pasted secret
   stores it first and cites it next, seconds apart; a secret stored long ago,
   or already sent anywhere, or kept for `coffer run`, is not fresh.
3. **Protection switched off** (`secrets.require_approval = off`), which itself
   waits for an approval.

Bindings are evaluated at the moment of use (spawn, adapter start, push), so a
change made behind Coffer's back — a vault file edited, a sync that brought a
new server — is caught where it matters. `GET /credentials/approvals` refreshes
first, so a change saved a moment ago is listed at once, and approvals whose
destination was deleted or moved on are marked `superseded`.

## D3. Replacing a value in use, and switching protection off

`POST /credentials` on a ref that has an approved binding, or on a standalone
secret, answers **202** with a pending `replace_value` approval; the new value
waits Fernet-encrypted in `secret_approvals.pending_ciphertext` and is written
on approval (the column is cleared on any decision). A new ref, or one nothing
receives, is written at once (204). Replacing a channel's token with an
attacker's bot would redirect the user's conversations, which is why a value in
use is a widening like any new destination.

`PUT /settings/secret-boundary {require_approval: false}` answers 202 with a
`disable_protection` approval; `true` applies at once. Rejecting any approval
needs no presence — refusing only narrows — and is open to every surface.

## D4. `coffer run`

The CLI collects `--secret NAME` (variable `NAME` upper-cased, `-`/`.` → `_`),
`--secret ENV=NAME`, `coffer://secret/<name>` values in `--env-file` and in its
own environment, and asks `POST /credentials/secrets/resolve {names, argv0,
cwd}`. That route answers **standalone `secret/<name>` values only** — a
resource's secret is never answerable there — and records one `secret_resolved`
row per name with the program and working directory, never the rest of argv.
The child gets the values in its environment; its stdout and stderr are piped
through `StreamMasker`, which replaces exact values of eight characters or more
with `***` and holds back a tail the length of the longest value so a match
split across reads is still caught. `--no-masking` passes stdio straight
through (interactive tools keep their terminal). Signals are forwarded and the
exit status passes through (`128 + signal` for a signalled child). A pty is not
used; a tool that needs a real terminal is run with `--no-masking`.

This route returns plaintext to a same-user caller. That is the ADR's accepted
residual risk for `coffer run` — the agent is the child's parent — and it is
confined to the namespace the user created for exactly that use.

## D5. The Secrets page backend

`GET /credentials` lists the union of stored refs (the store's new
`list_refs`) and cited refs, each with `cited_by`, `uri` and
`mentioned_by_skills` for a standalone secret (a literal search of the skill
master store for `coffer://secret/<name>`), `unreferenced`, `bindings`
(approved and pending) and `readable_by_local_processes` (a standalone secret,
or a ref a stdio server's environment carries). A delete is refused with
`CREDENTIAL_IN_USE` while a resource cites the ref or a skill cites the URI; a
real removal also forgets the ref's bindings, so a new value under that ref is
a new secret. Reveal and replace go through the desktop app (D1, D3).

The plaintext scan reads `~/.coffer/secrets/*.env` and `*.json` and every text
file of the skill master store (assignments whose name says secret, and
well-known token shapes), and reports `{id, path, source, key, line,
proposed_name}` — never the value — plus mentions of `~/.coffer/secrets/` in
skills. The move stores each value as `secret/<proposed_name>`, reads it back
and compares, refuses a name that already holds another value, and only then
rewrites the file (atomic replace, mode kept) with the reference. No plaintext
backup is kept. It was implemented and tested on a throwaway `HOME` only.

## D6. Master key storage

`MasterKeyManager` gains an optional `vault` — the `KeychainAccessGroupBackend`
of `infrastructure/credentials/master_key_backends.py` — chosen by
`build_identity.keychain_access_group()`, a constant the release pipeline
stamps into a frozen, signed build (it is `None` in source). With a vault the
key lives there only: a file or legacy-keychain key is written into it, read
back and compared, then deleted (audited `master_key_relocated`); two
disagreeing keys stop the start naming both fingerprints; `relocate` is
refused; an import keeps a different existing key as a second Keychain item
(`master-key.bak-<stamp>`), never as a file. The item carries no
`kSecAttrAccessControl` (no presence flag) and is
`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`. Without a vault the
development arrangement is unchanged (the `0600` file, the legacy keychain
opt-in and its relocation).

**Not verified here** (recorded in the master-key ADR's open questions): that a
Developer-ID-signed **bare** `coffer-daemon` outside an app bundle can use the
access-group entitlement (it may need a provisioning profile, which only a
bundle carries). The backend's SecItem calls are exercised only through an
injected fake; the real calls return `errSecMissingEntitlement` on an unsigned
build and were not run against the user's Keychain.

## D7. Migration 0112

Three tables: `secret_bindings`, `secret_approvals` (index on `status`),
`secret_boundary_settings`. Nothing is back-filled in SQL; the adoption in D2
runs at the first start through the same code that checks targets later.
