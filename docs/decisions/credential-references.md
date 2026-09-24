# Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credentials Across Machines](credentials-across-machines.md), [Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md), [Kind Plugin Contract](kind-plugin-contract.md), [Vault Sync](vault-sync.md), [principles](../../docs-site/architecture/principles.md) (Credentials), spec credentials, spec vault-sync, research note [credentials and secrets](../research/credentials-secrets.md), PRs #293, #406

## Context

Nearly every kind needs a secret: an HTTP MCP server's bearer token or a stdio
server's API key in its environment, a channel bot's token, a model provider's
API key, the sync remote's push token. A resource's configuration, meanwhile,
goes everywhere: it is serialized into the [sync tree](vault-sync.md), returned
by the API to the web UI, shown in dialogs, written into audit details and
diagnostics bundles, and projected into agents' native config files. A secret
anywhere in a config would leak through every one of those paths, and "Coffer
never persists a plaintext secret" would have to be re-verified per kind and
per surface.

Two further forces:

- **Rename.** Since [resources got an immutable uid](resource-identity-is-an-immutable-uid.md)
  (PR #406) every kind can be renamed, so anything keyed on a resource's name
  breaks on rename.
- **Sync has no handshake.** Ciphertext travels at `credentials/<ref>.enc`, so
  a ref is also a file path two machines must agree on without talking
  ([Credentials Across Machines](credentials-across-machines.md)); and deleting
  a resource while its credential rows lingered is what let the 2026-07-10
  incident re-seed a months-old blob (PR #293).

## Options Considered

### Option A — An opaque reference in the config, resolved from the encrypted store at use (chosen)

A secret is addressed by an opaque **ref**: slash-separated segments of
`[A-Za-z0-9_.-]` that mean nothing to the store
(spec credentials "Address a secret by an opaque reference"). A config carries
refs, never values — for `mcp_server` a `credential_refs` map of env var or
header name to ref; each kind declares where its refs live through
`Kind.credential_ref_extractor` (`mcp_server`, `channel` and `provider` do)
(spec credentials "Carry references, never secrets, in resource configuration").
The `mcp_server` config model additionally refuses a static env or header
value that looks like a secret — `Bearer …`, `ghp_`, `github_pat_`, `sk-`,
`xoxb-` and its siblings, a JWT prefix — and tells the user to move it into `credential_refs`
(`domain/mcp/server_config.py`).

Resolution happens only at the moment of use: `CredentialResolver.materialize`
(`application/credentials/resolver.py`) turns `{key: ref}` into
`{key: secret}` for an upstream spawn, header injection or adapter start, and
the plaintext lives only in that process environment or request
(spec credentials "Hold plaintext only in memory at the moment of use"). A ref
the store does not hold raises `CredentialMissing` rather than starting a
half-configured resource.

The lifecycle is kept whole around the ref:

- **Write first.** A surface that accepts a pasted secret stores it and
  persists only the ref, and removes the credential again if the registration
  that follows fails (spec credentials "Store a pasted secret before persisting its reference").
- **No dangling citations.** Deleting a credential is refused with
  `409 CREDENTIAL_IN_USE` while any resource cites it, naming each citer by
  kind and current name. No foreign key can express this — the ref lives
  inside another kind's JSON config — so `ResourceService.find_credential_citations`
  walks every registered config through its kind's extractor
  (spec credentials "Refuse to delete a credential still in use").
- **No orphans.** Deleting a resource releases the refs nothing else cites,
  on this machine and, through a converged deletion, on every other
  (spec credentials "Release unshared references when a resource is deleted").
- **Reads leave a trail.** A deliberate read of a value
  (`GET /api/v1/credentials/{ref}`, `coffer credentials get --show`) is audited
  as `credential_read` with the ref only; the presence probe decrypts nothing
  and audits nothing (spec credentials "Audit every read of a secret value").

Refs are **minted opaque**: `provider/<uuid4 hex>/key` in the backend
(`application/provider/service.py`), `<kind>/<uuid4 hex>/<logical key>` for
`channel` and `mcp_server` in the frontend (`lib/credentialRef.ts`), one per
secret. A rotation re-encrypts under the same ref, so nothing that cites it
changes. Refs that earlier builds derived from a resource's name
(`channel/<name>/<secret>`, `<name>.<ENV>`) were rewritten by migration 0099
to `<kind>/<uuid5(old ref)>/<logical key>` — derived rather than random so two
machines migrating independently compute the same new ref and the move
crosses the remote as one change on each side, not a delete beside an
unrelated add.

Pros: the config is safe to show, export, diff and sync; one store and one
resolver for every kind; rotation touches only the store; rename touches no
secret.

Cons: two things to keep consistent (the citation and the row), which is why
delete is guarded from both sides; a ref is not self-describing beyond its
trailing logical key; a resource can be registered citing a ref the store does
not yet hold, which `coffer credentials list` reports as missing.

It wins because it makes "no plaintext outside the store" one claim about one
module instead of a claim about every config shape and every surface.

### Option B — Encrypted values inline in the config

Store each secret as Fernet ciphertext directly inside the resource's config.

Pros: no second table, no citation to keep consistent; a config is
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

Give each kind its own secrets table keyed by resource.

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

Lost once rename became universal; migrated away in 0099.

## Decision

Resource configuration carries opaque credential references and never secret
values; each kind declares where its refs live; the encrypted store is the only
holder of a secret; resolution happens only at spawn, header injection or
adapter start. Refs are minted opaque, per secret, and never derived from a
mutable name. A credential cannot be deleted while cited, and a deleted
resource releases what nothing else cites.

## Consequences

- Any new kind that needs a secret declares a `credential_ref_extractor`;
  without one, its refs are invisible to citation checks and to
  `coffer credentials list`.
- Exporting, syncing or displaying a config never needs redaction for secrets.
- The sync layer carries refs in resource documents and ciphertext only on a
  remote configured for it; a machine without the ciphertext holds a resource
  whose ref is reported missing or locked rather than a broken secret.
