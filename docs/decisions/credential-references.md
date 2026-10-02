# Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Kind Plugin Contract](kind-plugin-contract.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [principles](../../docs-site/architecture/principles.md) (Secrets), spec secret, spec vault-sync, research note [credentials and secrets](../research/credentials-secrets.md), PRs #293, #406

## Context

Nearly every kind needs a secret: an HTTP MCP server's bearer token or a stdio
server's API key in its environment, a channel bot's token, a model provider's
API key, the sync remote's push token. A resource's configuration, meanwhile,
goes everywhere: it is a file in the vault repository that sync publishes
([Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md)), returned
by the API to the web UI, shown in dialogs, written into audit details and
diagnostics bundles, and projected into agents' native config files. A secret
anywhere in a config would leak through every one of those paths, and "Coffer
never persists a plaintext secret" would have to be re-verified per kind and
per surface.

Two further forces:

- **Rename.** Since [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md)
  (PR #406) a resource can be renamed on every kind except the two whose name
  agents see ([MCP servers and skills](names-visible-to-agents-are-fixed.md)),
  so anything keyed on a resource's name breaks on rename.
- **Sync has no handshake.** Ciphertext travels as `secret/<ref>.enc` in the
  vault, so a ref is also a file path two machines must agree on without talking
  ([Secrets Cross Machines Only as Ciphertext](secrets-cross-machines-only-as-ciphertext.md));
  and deleting a resource while its secret lingered is what let the 2026-07-10
  incident re-seed a months-old blob (PR #293).

## Options Considered

### Option A — An opaque reference in the config, resolved from the encrypted store at use (chosen)

A secret is addressed by an opaque **ref**: slash-separated segments of
`[A-Za-z0-9_.-]` that mean nothing to the store
(spec secret "Address a secret by an opaque reference"). A config carries
refs, never values — for `mcp_server` a `secret_refs` map of env var or header
name to ref; each kind declares where its refs live through
`Kind.secret_ref_extractor` (`mcp_server`, `channel` and `provider` do)
(spec secret "Carry references, never secrets, in resource configuration").
The `mcp_server` config model additionally refuses a static env or header
value that looks like a secret — `Bearer …`, `ghp_`, `github_pat_`, `sk-`,
`xoxb-` and its siblings, a JWT prefix — and tells the user to move it into
`secret_refs` (`domain/mcp/server_config.py`).

Resolution happens only at the moment of use: `SecretResolver.materialize`
(`application/secret/resolver.py`) turns `{key: ref}` into
`{key: secret}` for an upstream spawn, header injection or adapter start, and
the plaintext lives only in that process environment or request
(spec secret "Hold plaintext only in memory at the moment of use"). A ref
the store does not hold raises `SecretMissing` rather than starting a
half-configured resource. The resolver also asks the secret boundary whether the
destination's target may receive the value, and injects nothing until a person
has approved a binding that is new
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

The lifecycle is kept whole around the ref:

- **Write first.** A surface that accepts a pasted secret stores it and
  persists only the ref, and removes the secret again if the registration
  that follows fails (spec secret "Store a pasted secret before persisting its reference").
- **No dangling citations.** Deleting a secret is refused with
  `409 SECRET_IN_USE` while any resource cites it, naming each citer by
  kind and current name. No foreign key can express this — the ref lives
  inside another kind's config — so `ResourceService.find_secret_citations`
  walks every registered config through its kind's extractor
  (spec secret "Refuse to delete a secret still in use").
- **No orphans.** Deleting a resource releases the refs nothing else cites,
  on this machine and, through a converged deletion, on every other
  (spec secret "Release unshared references when a resource is deleted").
  The standalone `secret/` namespace is exempt, because its citers are mostly
  files Coffer does not parse.
- **A value is never read back by a route.** No route, command or tool returns
  a secret's value; it is seen only in the desktop app behind a presence check
  (`secret_revealed`), the presence probe decrypts nothing and audits nothing,
  and citing a ref from a new destination waits for an approval
  ([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

Refs are **minted opaque**: `provider/<uuid4 hex>/key` in the backend
(`application/provider/service.py`), `<kind>/<uuid4 hex>/<logical key>` for
`channel` and `mcp_server` in the frontend (`lib/secretRef.ts`), one per
secret. A rotation re-encrypts under the same ref, so nothing that cites it
changes. A ref is a file name in the vault (`secret/<ref>.enc`, or
`local/secret/<ref>.enc` for a ref true of one machine), which is why it must
be stable and free of the resource's name.

Pros: the config is safe to show, export, diff and sync; one store and one
resolver for every kind; rotation touches only the store; rename touches no
secret.

Cons: two things to keep consistent (the citation and the row), which is why
delete is guarded from both sides; a ref is not self-describing beyond its
trailing logical key; a resource can be registered citing a ref the store does
not yet hold, which `coffer secret list` reports as missing.

It wins because it makes "no plaintext outside the store" one claim about one
module instead of a claim about every config shape and every surface.

### Option B — Encrypted values inline in the config

Store each secret as Fernet ciphertext directly inside the resource's config.

Pros: no second store, no citation to keep consistent; a config is
self-contained.

Cons: every config reader now handles ciphertext — the UI, the audit
redactors, the sync exporter, the native-config projection — and each must know
which fields to leave alone. Two resources sharing one token hold two copies
that rotate separately. Deleting a secret without its resource, or listing
which secrets exist, means scanning every kind's config shape.

Lost: it spreads secret handling across every consumer of config, which is
what the store exists to prevent.

### Option C — Environment variable names

Let a config name an environment variable (`$GITHUB_TOKEN`) that the daemon
reads from its own environment.

Pros: familiar; nothing stored by Coffer.

Cons: the daemon is started by launchd, the desktop shell or a CLI spawn, each
with a different environment, so the value depends on how the daemon happened
to start. Secrets end up in shell profiles in plaintext. Nothing can travel to
another machine, and nothing can be audited.

Lost: it moves the plaintext somewhere worse and makes resolution
non-deterministic.

### Option D — External secret manager URIs (`op://`, `vault://`)

Let a ref point at 1Password, HashiCorp Vault or the OS keychain, resolved
through that tool's CLI at use.

Pros: secrets stay in a manager the user already trusts; rotation happens
there.

Cons: a hard runtime dependency on a third-party CLI and its session state at
every MCP spawn; unlocked-session prompts from a background daemon; nothing to
carry across machines except the assumption that the other machine has the
same manager configured. Supporting several managers multiplies all of it.

Not built: nothing in Option A forecloses it — a ref is opaque, so a future
resolver could route a scheme prefix to an external manager without changing
any config shape.

### Option E — A secret table per kind

Give each kind its own secret store keyed by resource.

Pros: ownership is structural; deleting the resource cascades.

Cons: the same secret shared by two resources of different kinds is
duplicated; every kind reimplements encryption, audit and CLI; one store's
invariants become N stores' invariants, and the sync layer would need a
per-kind hook to carry each.

Lost: one store is one thing to verify.

### Option F — Refs derived from the resource's name (the earlier convention)

Mint `channel/<name>/<secret>` or `<name>.<ENV>` so a ref is readable at a
glance.

Pros: human-readable; no minting step.

Cons: the name becomes a key. Renaming must move the secret in the store in an
order that never lets a live agent see it missing; a user-typed ref like
`smart.TOKEN` is indistinguishable from a minted one, so cleanup could delete a
secret the user shared deliberately; and on sync a move is a delete plus an
unrelated add over files neither side can read to compare.

Lost once rename became universal: refs that earlier builds derived from a
name were rewritten to `<kind>/<uuid5(old ref)>/<logical key>`, derived rather
than random so two machines migrating independently computed the same new ref
and the move crossed the remote as one change on each side.

## Decision

Resource configuration carries opaque secret references and never secret
values; each kind declares where its refs live; the encrypted store is the only
holder of a secret; resolution happens only at spawn, header injection or
adapter start, and only into a destination a person has approved. Refs are
minted opaque, per secret, and never derived from a mutable name. A secret
cannot be deleted while cited, and a deleted resource releases what nothing
else cites.

## Consequences

- Any new kind that needs a secret declares a `secret_ref_extractor`;
  without one, its refs are invisible to citation checks and to
  `coffer secret list`.
- Exporting, syncing or displaying a config never needs redaction for secrets.
- The sync layer carries refs in resource documents and ciphertext only on a
  remote configured for it; a machine without the ciphertext holds a resource
  whose ref is reported missing or locked rather than a broken secret.
- A secret a person or a skill owns, rather than a resource, takes a named
  `secret/<name>` ref instead of a minted one
  ([Standalone Secrets Are Named `coffer://secret/` References](standalone-secrets-are-named-references-injected-into-one-child.md)).
