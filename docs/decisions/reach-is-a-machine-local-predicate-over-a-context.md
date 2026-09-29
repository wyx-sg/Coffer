# Reach Is a Machine-Local Predicate Over an Extensible Context

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Resource Reach Is Machine-Local and Never Converges](resource-reach-is-machine-local.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [A Channel Answers Only Its Paired Owner, and Fails Closed in Groups](channel-owner-gate.md), [A Kind Plugs In as One Frozen Record of Optional Hooks: Validators Before the Write, Reactions After](kind-plugin-contract.md), [Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), spec resource-framework "Carry a per-agent reach on every resource", spec vault-sync "Keep reach machine-local", spec vault-sync "Scope names agents only", spec vault-sync "Say where reach is set that it is machine-local", spec channels "Limit the agents a channel may drive to its scope", spec channels "Bind each channel to the one machine that runs it", spec mcp-gateway "Gate server exposure by scope per session", spec mcp-gateway "Take the agent identity from the handshake"

## Context

A resource's **reach** answers "is this live here, and for whom?". It is two
columns of the `resources` row — `enabled` and `scope_json`
(`infrastructure/persistence/models.py:47`, `:53`) — and two ADRs fix its
meaning: it is machine-local and never converges
([Resource Reach Is Machine-Local](resource-reach-is-machine-local.md)), and
its scope is one allow-list of agent uids with one predicate
([Per-Agent Resource Scope](per-agent-resource-scope.md)).

The shape is narrower than the question, and the code shows three seams:

- **Two halves checked separately.** `Scope` holds one field, `agents`
  (`domain/scope.py`), and `is_active(scope, agent_uid)` (`domain/scope.py:75`)
  knows nothing of `enabled`. Every enforcement site combines them by hand:
  the gateway lists `enabled=True` rows and then filters by scope
  (`application/mcp/gateway_scope.py:33-34`); skill delivery writes
  `s.enabled and is_active(s.scope, agent.uid)`
  (then `application/skill/delivery_ops.py:77`, now the skill-link reconcile
  target); skill lifecycle did the same twice
  (then `application/skill/lifecycle_ops.py:183`, `:231`). A new site that forgets
  the first half widens reach.
- **One dimension, and one more on the way.** The agent-facets design
  introduces project-level landing points for delivered assets
  ([Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md)),
  which brings "only in this repository" within reach of the same control.
  The predicate's signature takes one identity, so a second dimension means
  changing all fourteen calls of `is_active` in `application/` — seven of them
  the channel's.
- **Channel scope means something else.** For `channel` the allow-list names
  the agents a channel may **drive** — a route allow-list for inbound turns,
  not a filter on who consumes it. It carries an invariant with a field of the
  channel's *config*: a non-empty allow-list must contain `default_agent`,
  enforced by `validate_scope_for` (`application/resource_scope_ops.py:55`),
  a hook only the channel kind supplies (`application/channel/kind.py:317`).
  At runtime the channel translates the uids into agent keys
  (`_scope_as_keys`, `application/channel/wanted.py:239`) and
  `application/channel/agent_routing.py:29-48` calls `is_active` with an agent
  **key** — the one place the predicate's argument is not a uid. And an empty
  allow-list means the adapter does not start at all.

The v0.4 file migration moves every one of these facts: resource
configuration into `vault/`, reach into `local/`
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)).
The channel invariant would then span a synced file (`default_agent`) and a
machine-local one (the allow-list), which no single write's validation can
see — a round could deliver a `default_agent` the local allow-list excludes.
And whatever shape reach has after that migration is the shape the next
migration starts from; changing it later means moving it twice.

## Options Considered

### Option A — One predicate over a context; reach folds `enabled` in; channel routing leaves reach (chosen)

- **Reach is one record per resource uid, in `local/`.** Its shape is
  `{enabled, agents, projects}`, each dimension `null` (unrestricted) or a
  list; a missing record means the kind's defaults (enabled, and the kind's
  `default_scope` — unrestricted except `provider`, which pre-fills from its
  wire). New dimensions are added as new keys; a record is a local file
  carrying a `format_version` like any other
  ([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md)).
- **One predicate over a context.** `is_active(reach, ctx)` takes a
  `ReachContext(agent_uid, project, …)`:
  - `enabled` false → false;
  - each dimension that is `null` → no restriction;
  - each restricted dimension → `ctx`'s value must be in the list;
  - a restricted dimension the context cannot answer (no agent identity, no
    project) → false. This is the existing rule that an unidentified session
    sees strictly less, generalised to every dimension;
  - a dimension the build does not know (a record written by a newer build on
    this machine) → false, and the resource is flagged: a permission read by a
    build that cannot interpret it must narrow, never widen.
- **Callers stop combining halves.** Every enforcement site passes its
  context and gets one answer; `enabled=True` pre-filters are removed so there
  is one place the answer is computed.
- **`projects` is reserved, not enforced.** The field is stored and validated
  now; no surface offers it and no site passes a project until a consumer (a
  project-level landing point) exists. Reserving it costs one key and saves
  the second migration.
- **Channel routing is configuration, not reach.** Which agents a channel may
  drive becomes a field of the channel's config, `may_drive` (a list of agent
  uids, or `null` for all), validated with `default_agent` by the kind's
  ordinary config validation — one file, one validator, so the invariant can
  no longer be split across two stores. It converges with the channel, exactly
  as `default_agent` and `runs_on` already do: a channel runs on one named
  machine, so a machine-local copy buys nothing. The channel's reach keeps
  only `enabled` (this machine's on/off), and its `supports_scope` is dropped.
  `validate_scope_for`, whose only supplier is the channel kind, is retired
  from the kind contract.
- **Lands with the file migration.** Reach moves from `resources.enabled` and
  `resources.scope_json` into `local/` in the same migration that moves
  configuration into `vault/`, already in this shape; a channel's
  `scope_json` moves into its config as `may_drive` in the same step. It never
  widens: an unresolvable entry is dropped and an allow-list left empty stays
  empty (dormant), as the uid migration did.

Pros: one predicate, one answer per site, no half to forget; a second
dimension is a key, not a signature change; the channel's two fields that must
agree live in one validated file; one migration for reach.

Cons: every call site changes once, now; a dimension the context cannot
supply narrows to nothing, which a future caller that forgets to pass one will
see as a resource that vanished (the safe direction, but a confusing one);
channel routing becomes a synced setting, so narrowing it on one machine
narrows it on the machine that runs the channel.

It wins because it is the last cheap moment to change the shape — the
migration is moving the data anyway — and because it removes the only
cross-store invariant the new storage would otherwise create.

### Option B — Move today's shape unchanged; add dimensions when needed

Migrate `enabled` and `{agents}` into `local/` as they are.

- **Pros.** The smallest migration; nothing speculative.
- **Cons.** The first new dimension migrates reach again and changes every
  call site again; the channel invariant is split across a synced and a local
  file on day one.
- **Why it loses.** It saves a reserved key now and pays a second migration
  and an unvalidatable invariant later.

### Option C — One predicate per dimension

`is_active_for_agent(...)`, `is_active_for_project(...)`, each call site
choosing which to ask.

- **Pros.** Each dimension's rule is simple and separately testable.
- **Cons.** Every site must remember to ask every dimension that applies to
  it, and a site that asks one and forgets another widens reach — the
  `enabled` problem, multiplied by the number of dimensions.
- **Why it loses.** It spreads the combination rule across the call sites,
  which is where it is failing today.

### Option D — A rule language (CEL, JSON-logic) for reach

Store reach as an expression over the context.

- **Pros.** Arbitrary conditions with no schema change.
- **Cons.** The UI's control is a list of checkboxes; an expression is
  something the page has to explain, and a wrong one fails silently. It is the
  templated-reach option [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md)
  rejected (its Option D), on the same verifiability argument.
- **Why it loses.** It buys expressiveness nobody has asked for at the cost of
  a control a person can check at a glance.

### Option E — Keep the channel's allow-list as reach

Leave `may drive` in the scope and keep `validate_scope_for`.

- **Pros.** No change to channel semantics or its UI placement.
- **Cons.** After the migration, `default_agent` is in a synced vault file and
  the allow-list in a local one; the pre-write hook sees only the half being
  written, so a round delivering a new `default_agent` can leave the channel
  excluding its own default — a bot that silently does not start. The
  predicate would also keep being called with agent keys at one site.
- **Why it loses.** It keeps an invariant that the storage split makes
  unenforceable.

### Option F — Reach inside the vault document, with a section per machine

- **Pros.** One file states the whole fleet's reach.
- **Cons.** The machine axis, tried twice and removed (PRs #296, #381, #382),
  for the reasons [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md)
  records: it cannot be verified from where it is set, and it puts a
  permission through a text merge.
- **Why it loses.** Nothing about files changes that argument.

## Decision

Reach is machine-local and stored in `local/`, one record per resource uid:
`enabled` plus an extensible set of dimensions, today `agents` and a reserved
`projects`, each unrestricted when `null`. One predicate,
`is_active(reach, ctx)`, answers every enforcement question from a context of
the asker's identity; a restricted dimension the context cannot answer, or a
dimension the build does not know, answers false. Which agents a channel may
drive is not reach: it is the channel's `may_drive` config field, validated
with `default_agent` and converging with the channel. Reach moves to this shape
in the same migration that moves configuration into the vault.

Rules a future change must respect:

- A new "for whom / where" question is a new reach dimension with a context
  field, never a kind's own field and never a second predicate.
- Missing context and unknown dimensions narrow; nothing widens by default.
- A setting that must agree with a resource's configuration lives in that
  configuration, not in reach.

## Consequences

- **Revises** [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md):
  its decision stands, and is now enforced by where reach is stored
  (`local/`, which no round commits) rather than by the exporter leaving two
  fields out; its note that per-capability toggles and `runs_on` converge is
  joined by the channel's `may_drive`.
- **Revises** [Per-Agent Resource Scope](per-agent-resource-scope.md): the
  allow-list of agent uids becomes the `agents` dimension of reach; the
  predicate gains its context argument; the `channel` row of its enforcement
  table moves out of scope into channel config; `validate_scope_for` leaves
  [the kind contract](kind-plugin-contract.md). The handshake identity and the
  rule that administrative surfaces are not reach-gated are unchanged.
- The channel runtime's translation from uids to agent keys now reads a config
  field; routing by uid end to end is follow-up work in the chat registry.
- **Obligations.** Spec deltas in resource-framework (the reach record and
  predicate), channels (`may_drive`), vault-sync (reach stored locally); a
  property test that no combination of missing context and unknown dimension
  makes `is_active` true where a narrower reach would be false; the migration
  test that a channel's allow-list arrives as `may_drive` unchanged and that no
  row's reach widens.
