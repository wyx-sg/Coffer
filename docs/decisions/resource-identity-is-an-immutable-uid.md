# Resource Identity Is an Immutable `uid`, Not the Name

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Supersedes**: [Resource Identifier Format](resource-identifier-format.md) — wholly; the `<kind>:<name>` string form is deleted, not demoted
**Related**: spec [resource-framework](../../specs/resource-framework/spec.md), spec [vault-sync](../../specs/vault-sync/spec.md), [Everything Is a Resource Kind](everything-is-a-resource-kind.md), [Per-Agent Resource Scope](per-agent-resource-scope.md)

## Context

The superseded ADR made `<kind>:<name>` the external identifier and rejected a
UUID on two grounds: a UUID is not human-readable, and "Coffer is single-user
local-first — there is no other Coffer to distinguish from".

The second ground stopped being true when spec vault-sync landed. A vault now
converges across the user's machines through a git remote, so there *are* other
Coffers, and the question the identifier has to answer changed with it: not
"what do I call this?" but "is the thing on that machine the same thing as the
thing on this one?". A name cannot answer it, because a name is exactly what the
user is allowed to change.

Four consequences accumulated in the code, each one a patch over the same hole:

1. **A rename crosses the sync remote as a deletion plus a creation.** The
   bundle path is `resources/<kind>/<name>.yaml`, the diff is taken with
   `--no-renames`, and the deletion guard pairs a delete with an add by content
   — which a rename changes, because the document spells its own name. So the
   receiving machine runs the full `ResourceService.delete`: `ON DELETE CASCADE`
   drops the resource's `channel_peers` (paired chats), its
   `mcp_capability_preferences` (which tools the user switched off) and its
   `skill_agent_bindings`, and `release_orphaned_credentials` deletes the API
   key no remaining row cites. Whether the re-creation that follows succeeds
   depends on whether the new name sorts before or after the old one in the
   path-ordered apply loop.
2. **Only one kind of the seven can be renamed at all.** `ResourceService.rename`
   has exactly one caller — `provider` — and it exists because a provider's name
   is written out into another tool's config file and has to be rewritten there.
   The other six kinds offer no rename; the user deletes and re-creates, paying
   the same cascade locally.
3. **The name has to satisfy a URL segment and a filename**, so the label the
   user sees is constrained to `^[a-zA-Z0-9_.-]+$` and 64 characters. A
   knowledge collection cannot be called 账号系统架构 for reasons that have
   nothing to do with knowledge collections.
4. **Cross-resource references hold names, so the same agent needs two of them.**
   `application/channel/agent_vocabulary.py` exists solely to translate between
   an agent's registry name (`claude-code`) and its agent key (`claude_code`)
   because three call sites compared them directly and rejected the only value
   the reach picker could produce.

Meanwhile a stable identity already existed and was already load-bearing
*internally*: `resources.id` is the foreign key of `skill_agent_bindings`,
`mcp_capability_preferences`, `channel_peers` and `channel_thread_conversations`,
and `audit_log.resource_id` is what lets a resource's history survive a rename.
None of it is visible from any surface — no response schema carries it — and it
cannot be promoted as-is, because it is an autoincrement row number: machine A's
row 7 and machine B's row 7 are different resources, which is why
`domain/sync/serialization.py` excludes it from the synced document by name.

## Decision

A resource's external identity is an immutable, business-agnostic **`uid`**.

- **Shape**: a UUID hex string (`uuid4().hex`), the convention already used for
  `machine_id` and for provider credential refs.
- **Spelling**: `uid` everywhere — `resources.uid`, `Resource.uid`,
  `/api/v1/resources/{uid}`, the `uid` key in a synced document. Deliberately
  *not* `id`: five tables already use `resource_id` for the integer row number,
  and giving `id` a second meaning is the "one field answering two questions"
  failure this codebase has paid for before.
- **The integer `id` stays exactly as it is** — internal surrogate primary key,
  unchanged FK target for the four kind-owned tables. Nothing about those tables
  changes.
- **`name` becomes a mutable label.** It stays unique within a kind, because a
  user should not have two skills called the same thing, but uniqueness is a
  constraint, not an identity. Renaming is a field in `PATCH`, at the same level
  as editing a description; `POST /api/v1/resources/provider/{name}/rename` is
  deleted, its reason for existing gone.
- **The `<kind>:<name>` string form goes away entirely.** `ResourceRef` stops
  being an identity type and the `ref` field is removed from every response;
  what remains is three plain fields — `uid`, `kind`, `name`. Keeping the old
  string around as "the label" would leave two spellings of identity in the
  codebase and an obvious place for the next reader to reach for the wrong one.
- **Cross-resource references hold `uid`s** — a resource `scope`'s agent list, a
  channel's `default_agent`.
- **The sync bundle is laid out by `uid`**: `resources/<kind>/<uid>.yaml`, with
  `uid` inside the document. A rename is then a modification of one file, which
  is what it always was.

### How two machines agree on a uid without talking

The migration cannot mint a random uid per machine: two machines would each
invent their own for the same resource and the next round would see two
unrelated documents. Nor can they negotiate — a vault converges through a git
remote with no online handshake.

So uid generation is split:

| Case | uid |
| --- | --- |
| Rows existing at migration time | `uuid5(COFFER_RESOURCE_NAMESPACE, f"{kind}:{name}")` |
| Every resource created afterwards | `uuid4().hex` |

`(kind, name)` is the one thing every machine in a fleet provably agrees on at
the moment it upgrades — it was the identity until then — so deriving from it
makes every machine compute the same uid independently, with no protocol. After
that the identity is the uid and the derivation is never used again, which is
what keeps "delete `foo`, create a new `foo`" from resurrecting the old
resource's identity.

A mixed fleet is handled by the mechanism that already exists: the bundle's
layout schema version is bumped, and a machine on an older build refuses a
too-new layout through `domain/sync/manifest.refuse_if_too_new` and tells the
user to upgrade.

### What stays readable

`kind` remains a field on every response and a namespace in the per-kind route
prefixes (`/api/v1/resources/mcp_server/{uid}/capabilities`), so the
self-description the superseded ADR valued is not lost — only the part of it
that was pretending to be an identity. The CLI keeps taking names and resolves
them to uids itself; nobody is asked to type a UUID. The web UI addresses detail
pages by uid, with **no** redirect from the old name-based paths: this change
ships no compatibility shim, and the name-addressed legacy routes that already
existed (`/mcp-servers/mcp_server/:name`, `/knowledge-bases/:name`) are deleted
with it. A vault is one user's, upgraded in one step; a shim here would only be
a second way to address a resource, kept alive forever to serve a bookmark.

## Consequences

**Positive**

- A rename converges as a rename. The cascade, the credential release and the
  sort-order dependence in §Context 1 all stop being reachable.
- Rename becomes available to all kinds for free, because it is no longer an
  operation — it is a field.
- The name is released from the URL and filename character set, so labels can be
  whatever the user wants to read.
- `agent_vocabulary.py` is deleted: with uids on both sides there is one
  vocabulary.
- The audit log's `resource_id` stops being the only place that knew the truth
  and becomes consistent with every other surface.

**Negative**

- A URL is no longer guessable from a name, and an existing bookmark breaks —
  no redirect is kept. The CLI still takes names, so the cost lands on saved web
  URLs only, and it is paid once.
- Every surface changes at once: about sixty routes, thirteen OpenAPI contracts,
  every detail page. There is no incremental version of this that leaves the
  system consistent, which is why it ships as one change.
- A one-time migration rewrites cross-references. Rows whose reference cannot be
  resolved are handled explicitly rather than cleared — see the migration's own
  note — because clearing an agent allow-list silently widens it from "these
  agents" to "every agent".

## Alternatives Considered

**Promote the existing integer `id`.** Rejected: it is a per-machine row number.
Using it as the bundle filename would three-way-merge two unrelated resources
whenever two machines happened to allocate the same row.

**Keep the name as identity; teach sync to recognise renames.** Rejected. It
requires inventing a rename event in the bundle and a protocol for applying it,
which replaces a data-loss bug with a consistency protocol — and leaves
problems 2, 3 and 4 untouched.

**Change only the cross-references and the sync layout, leave the routes on
names.** Rejected as a half-measure: it fixes the data loss but keeps rename as
a per-kind special operation, keeps the character-set tax on labels, and leaves
two identity systems with a boundary nobody can see.
