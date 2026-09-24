# The Resource Framework Is Core Domain, Designed Before the Second Kind

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [principles](../../docs-site/architecture/principles.md) (Technology & architectural constraints — the extraction rule and its one exception), [Code Layout — Layer-First](code-layout-layer-first.md), [Kind Plug-in Contract](kind-plugin-contract.md), [Composition Root With Explicit Wiring](composition-root-explicit-wiring.md), [Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md), [Per-Agent Resource Scope](per-agent-resource-scope.md), [SQLite and One Alembic Lineage](sqlite-alembic-persistence.md), spec resource-framework, spec mcp-gateway, [Resource framework](../../docs-site/architecture/resource-framework.md)

## Context

Coffer manages several kinds of user-owned things: MCP servers, coding agents,
skills, knowledge collections, memory partitions, model providers and messaging
channels. When the first spec (mcp-gateway) was written, only `mcp_server` was
concrete, but the next kinds were already named with confidence by the owner.

The principles bias hard towards late abstraction:

> Cross-cutting modules are extracted only after the second feature needs them.

So the question was whether the thing every kind would share — identity,
lifecycle (register / update / enable / disable / delete), audit, config
validation, and later reach and sync — is a "cross-cutting module" subject to
that rule, or part of the core domain model that the first kind should already
be built on.

What made it more than a style question is where the shared part lives. It is
not a helper library; it is the `resources` table every other table points at,
the audit log's `resource_id`, the REST routes under `/api/v1/resources`, the
CLI `resource` group and the sync document format. Every one of those is
either user data or an external contract, so building it MCP-shaped first and
generalising it later means migrating a live database and breaking a public
API, not moving code between files.

## Options Considered

### Option A — Kind-agnostic Resource framework as core domain, from the first kind (chosen)

`Resource` is a domain entity with a kind-agnostic shape (`domain/resource.py`):
identity, `kind`, `name`, `config` (validated by the kind's Pydantic schema),
`enabled`, `scope`, timestamps. One kind-agnostic `ResourceService`
(`application/resource_service.py`) owns the lifecycle and writes the audit
trail; one `resources` table stores every kind's rows with the kind-specific
part in `config_json`. A kind is a frozen `Kind` descriptor the service looks
up by name (see [Kind Plug-in Contract](kind-plugin-contract.md)). The
framework unifies **identity, lifecycle, audit, metadata and reach**. It does
**not** unify behaviour: there is no `invoke()` shared across kinds, because
calling a tool, delivering a skill and driving an agent turn have nothing in
common beyond the row they start from.

- **Pros.** The shared surfaces (table, audit, routes, CLI, sync format) are
  correct from day one and never need a data migration to generalise. The
  boundary between framework and kind is explicit before any kind-specific
  assumption can leak into it. Every later kind costs only its own code.
- **Cons.** The first spec carried the abstraction with one kind to justify it.
  The boundary has to be defended: the temptation to unify behaviour (a "god
  `invoke()`") is a standing risk.
- **Why it wins.** Seven kinds now run on it. Two of them (`knowledge`, `memory`)
  own no table at all — a row in `resources` plus files on disk — and the
  knowledge layer was rebuilt from an indexed store into plain files (PR #368)
  without touching the framework. The identity change from name to `uid`
  (PR #406) was made once, in the framework, and every kind gained rename in
  the same change. None of that is cheap in the options below.

### Option B — Extract on the second kind (the principles' default)

Build `mcp_server` as a self-contained feature with its own table, its own
audit rows and its own routes; when the second kind arrives, extract what the
two share.

- **Pros.** No speculative abstraction; the extraction is shaped by two real
  kinds instead of one plus a forecast. It is what the principles ask for
  everywhere else.
- **Cons.** By the time the second kind arrives, the MCP-shaped parts are user
  data and public contract: an `mcp_servers` table with its own foreign keys
  (capability preferences, invocations, health), audit rows keyed to it, and
  routes and CLI commands clients already call. Extracting means a data
  migration of every existing install, a second route family kept alive or
  broken, and an audit history split across two shapes.
- **Why it loses.** The rule exists to avoid paying for abstractions that turn
  out to be wrong; here the cost of *not* abstracting was known in advance and
  larger than the risk of abstracting wrongly, because the named kinds all
  demonstrably shared identity, lifecycle, audit and CRUD. The principles record
  this as the rule's one exception.

### Option C — Full plugin architecture (third-party loadable kinds)

Kinds as installable packages discovered at runtime (entry points or a plugin
directory), with a versioned plugin API, isolation and a manifest.

- **Pros.** Anyone could add a kind without a Coffer release; the framework
  boundary would be enforced by process or package boundaries rather than by
  import-linter.
- **Cons.** A usable plugin contract can only be designed against several
  concrete implementations; designed against MCP alone it would either over-fit
  MCP or be too generic to enforce anything. It would also freeze the kind
  contract as a public API, when that contract has changed shape several times
  since (pre-write validators split from post-write reactions, rename added,
  per-row sync withholding added). Loading third-party code into the daemon
  that holds the credential store is a security surface of its own.
- **Why it loses.** Coffer is a single-user local-first tool with no plugin
  ecosystem to serve. Kinds are added by changing Coffer, and the in-tree
  contract (Option A) gets the same "a kind plugs in without editing the core"
  property without publishing it. How a kind is wired in is its own decision:
  [Composition Root With Explicit Wiring](composition-root-explicit-wiring.md).

### Option D — Per-kind silos: each kind its own tables, routes and audit, no shared abstraction

Every kind is a vertical feature with its own entity table (`mcp_servers`,
`skills`, `agents`, …), its own CRUD routes and its own audit.

- **Pros.** Each kind's table can use real columns instead of a JSON config
  blob, so the database enforces more of each kind's shape. No framework to
  learn.
- **Cons.** Identity, lifecycle, audit, enable/disable, reach, rename, sync
  serialisation and the resource-list UI are rebuilt once per kind, and they
  drift: the name rule, the audit shape and the delete semantics end up
  subtly different in seven places. Anything that needs "every resource" —
  the audit log, `coffer__diagnose`'s history filter, the sync bundle, the
  per-agent reach picker — has to union seven tables.
- **Why it loses.** Four or more kinds sharing the same lifecycle make the
  duplication certain, and the cross-kind readers make it expensive. The real
  benefit — typed columns — is kept where it matters by letting a kind own
  *additional* tables for its operational data (see Consequences), while its
  definition stays one validated row in `resources`.

## Decision

The Resource framework is core domain, not a cross-cutting module, and it was
built with the first kind. Every user-managed thing is a `Resource` row in one
`resources` table, created, changed, enabled, scoped, renamed and deleted
through one `ResourceService`, audited in one `audit_log`, and served through
one kind-agnostic REST surface (`/api/v1/resources`) and CLI group. A kind
contributes a config schema and optional hooks; it does not re-implement any
of the lifecycle. The framework never unifies invocation — each kind decides
what "using" a resource means.

Rules a future change must respect:

- The core never imports a kind. `resource_service`, `audit_service`,
  `retention_service`, `domain/resource.py`, `domain/scope.py` and the other
  modules listed in the import-linter contract "Kind-agnostic core does not
  import kind-specific code" (`backend/pyproject.toml`) are tested against a
  `fake_kind` that exists only in tests.
- A cross-kind concern that is *not* resource lifecycle (subprocess supervision,
  delivery into agent directories, …) still follows the principles'
  extract-on-second-feature rule. This decision is not a licence to
  pre-abstract everything.

## Consequences

- A new kind lands as code only: a `make_<kind>_kind()` factory, its services,
  and a wiring step in the composition root. The `resources` table, the audit
  pipeline, the retention framework and the kind-agnostic routes do not change.
  A kind that has operational data of its own still brings its own tables and
  its own Alembic revision — `mcp_server` owns `mcp_capability_preferences`,
  `mcp_invocations` and `mcp_server_health`; `skill` owns
  `skill_agent_bindings`; `channel` owns `channel_peers` and
  `channel_thread_conversations` — while `agent`, `provider`, `knowledge` and
  `memory` need none.
- Cross-kind readers get one source: the audit log, the sync bundle
  (`resources/<kind>/<uid>.yaml`), the reach picker and the diagnostics tool
  all read `resources` without knowing which kinds exist.
- `config_json` is a TEXT column validated by the kind's Pydantic schema on the
  way in and out, not by the database; see
  [SQLite and One Alembic Lineage](sqlite-alembic-persistence.md).
- Creation is the one lifecycle step a kind may keep for itself, when it has an
  invariant beyond config validation (a skill's master folder, an agent's
  on-disk detection); everything after creation is generic. The mechanics of
  that and every other hook are in [Kind Plug-in Contract](kind-plugin-contract.md).
- Where reach is enforced — at each kind's own choke point, not in the core —
  is decided in [Per-Agent Resource Scope](per-agent-resource-scope.md).
- Because the framework spans every layer, the code layout had to be decided in
  the same spec: [Code Layout — Layer-First](code-layout-layer-first.md).
- REST and CLI answer through the same services, which is what lets spec
  resource-framework "Reach every management operation from both REST and the
  CLI" hold for every kind at once.
