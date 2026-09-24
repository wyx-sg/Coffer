# Resource Identity Is an Immutable `uid`, Not the Name

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [The Resource Framework Is Core Domain](resource-framework-upfront.md), [Kind Plug-in Contract](kind-plugin-contract.md), [Vault Sync](vault-sync.md), [Sync Deletion Breaker](sync-deletion-breaker.md), [Credential References](credential-references.md), [Per-Agent Resource Scope](per-agent-resource-scope.md), spec resource-framework "Address every resource by an immutable uid through one kind-agnostic surface", spec resource-framework "Treat a resource's name as a mutable label", spec vault-sync "Key resource documents by uid", PR #406

## Context

Every resource needs an identifier that the outside world holds: REST paths,
CLI arguments, cross-resource references (a resource's per-agent `scope` lists
agents; a channel's `default_agent` names one), the synced document's path in
the git tree the vault converges through, and the audit trail. Inside the
database there is also `resources.id`, an autoincrement integer that is the
foreign-key target of `skill_agent_bindings`, `mcp_capability_preferences`,
`channel_peers` and `channel_thread_conversations`, and that `audit_log.resource_id`
records.

The identifier has to answer two different questions:

1. *What do I call this?* — a label a person reads and types.
2. *Is the thing on that machine the same thing as the thing on this one?* —
   an identity that survives every edit a user is allowed to make, and that two
   machines holding one vault agree on without talking to each other, since a
   vault converges through a git remote with no online handshake
   ([Vault Sync](vault-sync.md)).

From the first spec until PR #406 the external identifier was the string
`<kind>:<name>` backed by `UNIQUE (kind, name)`. That answered question 1 well
and was chosen when "there is no other Coffer to distinguish from" was true.
Vault sync made question 2 real, and a name cannot answer it, because a name is
exactly what the user is allowed to change. The failures that accumulated are
the evidence the options below are weighed against:

- **A rename crossed the sync remote as a deletion plus a creation.** The
  document lived at `resources/<kind>/<name>.yaml` and spelled its own name, so
  a rename changed both its path and its bytes. The applier takes the diff with
  `--no-renames` and applies one path at a time (`infrastructure/sync/git_mirror.py`),
  so a changed path is always a delete and an add; the receiving machine ran
  the full `ResourceService.delete`: `ON DELETE CASCADE` dropped the resource's
  paired chats, its per-tool switches and its skill bindings, and
  `release_orphaned_credentials` deleted the API key no remaining row cited.
  Whether the re-creation then succeeded depended on whether the new name
  sorted before or after the old one.
- **Rename was one kind's private operation.** Only `provider` had it, through
  its own route, because its name was written into another tool's config file.
  Every other kind offered delete-and-re-create, paying the same cascade
  locally.
- **The label carried the identity's constraints.** A name had to be a URL
  segment and a file name.
- **Cross-resource references needed translating.** "Which agent" was spelled
  three ways — agent resource names in skill and channel scopes, agent types in
  provider scopes, and agent keys (`claude_code`) in a channel's
  `default_agent` — and `application/channel/agent_vocabulary.py` existed only
  to translate between two of them.

## Options Considered

### Option A — An opaque, immutable `uid` minted once as `uuid4().hex`; the name becomes a mutable label (chosen)

`resources.uid` (unique index `uq_resources_uid`) is a 32-character hex UUID4
minted by `ResourceService.register` before anything is written, never
changed, never reused. Everything outside the process addresses a resource by
it: `/api/v1/resources/{uid}`, per-kind route prefixes
(`/api/v1/resources/mcp_server/{uid}/…`), cross-resource references, the sync
path `resources/<kind>/<uid>.yaml` with `uid` inside the document, web UI
detail routes. `name` stays unique within a kind but is a label, renamed
through the ordinary `PATCH`. The integer `id` stays exactly what it was: the
internal, per-machine surrogate key and foreign-key target.

Existing rows needed uids that every machine in a fleet would compute
identically without coordination, so the migration (revision 0095) derives
them once: `uuid5(namespace, f"{kind}:{name}")`. `(kind, name)` was the
identity until that revision, so every machine agrees on it at the moment it
upgrades. After that revision the derivation is never used again; every new
resource gets a random `uuid4`.

- **Pros.** A rename is a modification of one file and one column; nothing
  else holds the name. Every kind gets rename at once. Two machines hold one
  identity per resource. The spelling (`uuid4().hex`) is the one already used
  for provider credential refs, the fallback machine id and the frontend's
  minted credential refs (`lib/credentialRef.ts`).
- **Cons.** A URL is no longer guessable from a name, and every surface
  changed in one release, with no redirect from name-based URLs. The CLI has to
  resolve names to uids (`surfaces/cli/_resolve.py`, one
  `GET /resources?kind=&name=` round trip).
- **Why it wins.** It is the only option that fixes all four failures, and the
  readability it gives up is recovered by keeping `kind` and `name` as fields on
  every response and letting humans keep typing names.

### Option B — Keep `<kind>:<name>` as the identity (the design this replaced)

A `ResourceRef(kind, name)` value object parsed at the domain boundary; routes
`/api/v1/resources/<kind>/<name>`; references and sync paths by name.

- **Pros.** Short and self-describing (`mcp_server:filesystem`), needs no
  lookup to know which kind to ask, maps directly onto URLs and CLI arguments.
- **Cons.** Every failure in the Context. The colon also had to be excluded
  from names and every consumer had to know the convention.
- **Why it loses.** It cannot answer question 2, and question 2 is the one that
  loses data.

### Option C — Keep the name as identity; teach sync to recognise renames

Record a rename event in the bundle (or pair a delete and an add by content
similarity) and apply it as a move.

- **Pros.** No identity change, no surface churn.
- **Cons.** It invents a rename protocol on top of a system whose arbiter is
  git, and similarity pairing is a guess: the deletion breaker does ask git for
  renames (`-M`, PR #409), but only to decide whether a deletion *had a
  destination* — which excuses it from the breaker's count — not to apply a
  move ([Sync Deletion Breaker](sync-deletion-breaker.md)). It leaves the other
  three failures untouched.
- **Why it loses.** It replaces a data-loss bug with a consistency protocol and
  still keeps the label and the identity welded together.

### Option D — Promote the existing integer `id`

- **Pros.** Already exists, already the foreign-key target, already what the
  audit log records.
- **Cons.** It is a per-machine row number: machine A's row 7 and machine B's
  row 7 are different resources. As a sync filename it would three-way-merge
  two unrelated resources, which is why `domain/sync/serialization.py` excludes
  it from the synced document.
- **Why it loses.** It is not an identity across machines.

### Option E — `uuid5` of `(kind, name)` for every resource, not only for the migration

- **Pros.** Deterministic with no coordination, ever: two machines that
  independently create `skill:foo` get the same uid.
- **Cons.** The identity becomes a function of a label at the moment of
  creation. Deleting `foo` and creating a new `foo` would hand the new resource
  the dead one's identity — its audit trail here, and its config on every other
  machine — which is the confusion the change exists to end. Two unrelated
  resources created under one name on two machines would silently become one
  document and fight every round.
- **Why it loses.** Determinism is needed exactly once, for rows that already
  existed, and the migration uses it exactly there.

### Option F — ULID (or another time-ordered id)

- **Pros.** Sortable by creation time, shorter (26 characters), good B-tree
  locality.
- **Cons.** Nothing lists resources by creation order (the repo orders by
  `kind, name`), a few hundred rows gain nothing from index locality, and it is
  a second id spelling beside the `uuid4().hex` already used for credential
  refs and machine ids — either a new dependency or a hand-written encoder.
- **Why it loses.** Its advantages answer questions Coffer does not ask.

### Option G — A URN (`urn:coffer:<kind>:<…>`)

- **Pros.** Globally namespaced, standard (RFC 8141), self-describing.
- **Cons.** Wrapping a name keeps every failure of Option B; wrapping a uid
  adds a prefix that only restates `kind`, which is already a field. The
  machines sharing a vault are one user's, so there is no foreign Coffer to be
  distinguished from.
- **Why it loses.** Ceremony around whichever identity it wraps.

### Option H — Path-style `<kind>/<name>`

- **Pros.** Reads naturally in URLs.
- **Cons.** Same identity-is-the-label problem as Option B, and the slash
  collides with URL and file-path separators wherever the string is embedded.
- **Why it loses.** It is Option B with a worse separator.

### Option I — Composite key `(kind, name)`, never serialised as one string

- **Pros.** No string format to define or parse.
- **Cons.** Still name-as-identity; and every cross-resource reference (a
  scope's agent list, a channel's `default_agent`) needs an object instead of a
  field.
- **Why it loses.** It keeps the defect and adds weight to every reference.

## Decision

A resource's identity is `uid`: an opaque `uuid4().hex`, minted once by
`ResourceService.register`, immutable, never reused, the same on every machine
that holds the resource. It is spelled `uid` everywhere — never `id`, which
keeps its meaning of the internal integer surrogate key (the kind-owned tables
and the audit log already hold that integer in `resource_id` columns, and one
field answering two questions is a failure this codebase has paid for). The only caller that supplies a uid instead of
minting one is the sync applier, creating a resource another machine already
identified.

`name` is a mutable label: unique within its kind, renamed by a field on
`PATCH /api/v1/resources/{uid}` for every kind, audited as `from`/`to`. The
`<kind>:<name>` string and the `ResourceRef` type are gone; responses carry
`uid`, `kind` and `name` as three plain fields. Cross-resource references hold
uids. The sync document for a resource is `resources/<kind>/<uid>.yaml`.

The label keeps one rule, in `domain/resource.py`: `^[a-zA-Z0-9_.-]+$`, at most
64 characters, applied by every path that sets a name. It is no longer an
identity constraint; it stays because `skill`, `knowledge` and `memory` turn the
name into a directory. A kind may narrow it further (`validate_name`:
`mcp_server` reserves the `__` namespace separator; `skill` applies its
frontmatter name rule).

## Consequences

- A rename is a column write plus, for the kinds that key something else by
  name, their `on_rename` hook ([Kind Plug-in Contract](kind-plugin-contract.md)).
  Four kinds supply one: `skill`, `knowledge` and `memory` move their directory,
  and `mcp_server` evicts every session supervisor's live connection under the
  old name so a renamed server does not leave an unreachable subprocess behind.
  A hook failure aborts the rename with nothing changed. `agent`, `provider` and
  `channel` rename by writing one column.
- The CLI keeps taking names and resolves them to uids itself; nobody types a
  uid. The web UI addresses detail pages by uid, and the old name-based routes
  were deleted with no redirect, so a bookmarked name URL breaks once.
- The one-time data migrations that moved every stored name-reference to a uid
  are part of this decision:
  - 0095 adds `resources.uid`, backfilled by the `uuid5` derivation above.
  - 0096 rewrites cross-references: `scope_json` entries, a channel's
    `default_agent`, and `conversations.channel_name` (renamed to
    `channel_uid`). It never widens reach: an unresolvable entry is dropped, an
    allow-list whose every entry is unresolvable becomes `[]` (no agent), never
    `NULL` (every agent), and an unresolvable `default_agent` is left as it is
    so it fails visibly.
  - 0097 re-keys `mcp_server_health` and `mcp_invocations` from the server's
    name to its uid. Health rows for servers that no longer exist are dropped;
    invocation rows are history and are kept under `deleted:<name>`; rows under
    Coffer's own built-in sentinel `coffer` are left alone.
  - 0098 removes `skill_md_name`, a second stored copy of a skill's name that a
    rename would otherwise have had to update.
  - 0099 stops `channel` and `mcp_server` credential refs being built from the
    resource's name: a name-derived ref is rewritten to
    `<kind>/<uuid5(old ref)>/<key>` (derived, so two machines compute the same
    new ref for the same ciphertext file), and new refs are random
    ([Credential References](credential-references.md)).
  - 0100 removes the `workflow:` ref spelling from `workflow_runs.template_ref`.
- The sync bundle's layout schema version was bumped, so a machine on an older
  build refuses the new layout (`domain/sync/manifest.refuse_if_too_new`) and
  asks the user to upgrade instead of misreading it.
- `application/channel/agent_vocabulary.py` is deleted: there is one spelling
  of "which agent".
- History survives renames: `audit_log.resource_id` points at the row, and each
  entry keeps the name the resource had when the event happened.
