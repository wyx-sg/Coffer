# Kinds Are Wired Explicitly by One Composition Root, With No Global Registry

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: [The Resource Framework Is Core Domain](resource-framework-upfront.md), [Code Layout — Layer-First](code-layout-layer-first.md), [Kind Plug-in Contract](kind-plugin-contract.md), [Layering & boundaries](../../docs-site/architecture/layering.md), PR #386

## Context

The import-linter contracts forbid any kind from importing another and forbid
the kind-agnostic core from importing any kind
([Code Layout — Layer-First](code-layout-layer-first.md)). Yet the running
daemon is thick with cross-kind dependencies: deleting an agent has to clean up
skill bindings; the provider kind projects into each agent's native config;
the MCP gateway advertises built-in tools the skill, knowledge and memory kinds
register; channels drive turns through the chat platform and save through the
knowledge kind; sync needs every area's state providers, import gates and
post-import hooks. Something has to see all of them at once, construct them in
an order that satisfies those dependencies, and hand FastAPI routes the
services they need.

The 2026-09-14 architecture review found how the first answer to that had
decayed:

- Wiring steps talked to each other through `app.state`. A step set an
  attribute (`sync_state_providers`, `sync_post_import_hooks`,
  `memory_organise_runner`, `sync_service`, …) and a later step read it, so the
  dependency order was invisible and a step could run before what it needed
  existed. It also failed silently: an area that registered its sync state
  provider in the wrong place simply did not converge, which is how channel
  pairings went a whole release without syncing.
- `surfaces/http/dependencies.py` was one 368-line hub of FastAPI providers for
  every kind, typed `Any` (43 occurrences), because a typed provider would have
  made the kind-agnostic hub import every kind.
- A `KindModule` carrier (routers, CLI groups, `on_delete`, all `Any`-typed)
  was meant to let kinds register their own surfaces; nothing used it.

PR #386 replaced all three. This ADR records the shape it settled on.

## Options Considered

### Option A — One explicit composition root: typed results passed as parameters (chosen)

`surfaces/http/app.py`'s lifespan is the composition root, split into per-area
modules for the 400-line cap (`kind_wiring.py`, `*_wiring.py`,
`*_composition.py`). Every step is a plain function that takes what it needs as
parameters and **returns what it built** as a small frozen dataclass
(`AgentSkillWiring`, `ProviderWiring`, `KnowledgeWiring`, `MemoryWiring`,
`McpWiring`, `ChatWiring`, …). `wire_resource_kinds` calls the kind steps in
dependency order — agent and skill, then provider (it projects into agents),
then knowledge, then memory (so the gateway advertises `coffer__recall`), then
MCP last of the kinds (so it picks up every built-in tool), then Coffer's own
guide skill — and returns them bundled in `KindWirings`. Chat, curation and
channels are wired after that from those results. Sync contributions travel
the same way: one mutable `SyncContributions` collector is created by the
lifespan, passed to each step that has something to contribute, and handed to
`start_sync` at the end.

FastAPI providers follow the same split. `surfaces/http/dependencies.py` holds
only the kind-agnostic core (actor, resource, audit, retention, internal-engine
config). Each kind publishes its own concretely-typed `set_*`/`get_*` pairs
from its own module (`surfaces/http/mcp/dependencies.py`,
`skill_dependencies.py`, `provider_dependencies.py`, …); the lifespan calls
each setter once, routes name the getter in `Depends()`, and a getter called
before its setter raises instead of handing a route `None`.

- **Pros.** The order the lifespan reads in *is* the dependency order, and the
  argument list is the dependency: a step cannot be called before its inputs
  exist, and a type checker sees every edge. Forgetting to pass a contribution
  is a missing argument, not a silent no-op. No `Any` is needed anywhere,
  because each provider module is allowed to import its own kind. Tests build
  exactly the pieces they need by calling the same functions.
- **Cons.** Adding a kind means editing the composition root by hand: a wiring
  step, a line in `kind_wiring.py`, router inclusion in `routing.py`, a Typer
  group in `surfaces/cli/main.py`. The root is long and has to be kept readable
  on purpose. The CLI's group list is static.
- **Why it wins.** Everything the review found was a consequence of implicit
  ordering or untyped sharing; explicit parameters remove both, and the cost —
  a few lines per kind in one place — is paid rarely.

### Option B — Global registry populated by import side effects

Each kind module registers itself on import (`@register_kind`, a module-level
`REGISTRY[...] = ...`), and the app iterates the registry.

- **Pros.** Adding a kind touches only the kind's own package; the root never
  changes.
- **Cons.** Registration order is import order, which nobody controls or reads.
  Whether a kind exists depends on whether something happened to import it, so
  a test, the CLI and the daemon can each see a different set. Cross-kind
  dependencies (agent's `on_delete` needs the skill service; MCP needs the
  built-in tools of three kinds) still have to be resolved somewhere, and a
  registry resolves them by lookup at call time — the `app.state` problem again
  under another name. A process-global also leaks between tests.
- **Why it loses.** It hides exactly the ordering this codebase got wrong, and
  it trades a few explicit lines for action at a distance.

### Option C — Entry points / plugin discovery

Kinds declared as `importlib.metadata` entry points (or a plugin directory) and
discovered at startup.

- **Pros.** Kinds could ship outside the repository; the daemon would not need
  a release to gain one.
- **Cons.** All of Option B's ordering and lookup problems, plus a public,
  versioned plugin API and third-party code running in the process that holds
  the credential store. PyInstaller builds need entry-point metadata bundled
  explicitly, a class of "works from source, missing in the frozen app" bug.
- **Why it loses.** There are no out-of-tree kinds to discover; see
  [The Resource Framework Is Core Domain](resource-framework-upfront.md),
  Option C.

### Option D — A dependency-injection container library

Declare providers in a container (`dependency-injector`, `lagom`, …) and let it
resolve the graph.

- **Pros.** The container computes the order and enforces singletons; adding a
  service is a declaration.
- **Cons.** The graph moves from code a reader can follow into container
  configuration; async start-up steps (migrations, boot heals, worker start)
  and teardown do not fit a resolve-on-demand model; FastAPI already has its
  own `Depends()` mechanism, so there would be two DI systems. The cross-kind
  edges would still have to be declared somewhere that imports both kinds.
- **Why it loses.** It adds a framework to solve an ordering problem that a
  straight-line function already solves, and makes the order less visible.

### Option E — Shared mutable `app.state` as the service bus (the design PR #386 replaced)

Each wiring step writes what it built onto `app.state`; later steps and routes
read it from there; one untyped provider hub serves routes.

- **Pros.** No plumbing: any step can reach anything already built.
- **Cons.** The Context above: invisible order, `Any` everywhere, and failures
  that take the form of something silently not happening.
- **Why it loses.** It produced a shipped bug and made the dependency graph
  unreviewable.

## Decision

One composition root, explicit wiring. Every wiring step returns a frozen
record of what it built, and the next step takes it as a parameter; sync
contributions flow through one `SyncContributions` collector passed as a
parameter. FastAPI providers are split into the kind-agnostic hub and one
concretely-typed module per kind. There is no carrier object, no global
registry, no import-time registration, no entry-point discovery and no DI
container.

`app.state` is kept for a short, named list and nothing else:

- `app.state.kinds` — the `dict[str, Kind]` the `ResourceService` looks kinds
  up in. It is created in `create_app`, which registers the `agent` and
  `channel` kinds eagerly (so tests that do not run the lifespan still have
  them); each wiring step then writes its fully-hooked `Kind` into it. The
  service holds the same dict object, so a kind registered by a later step is
  visible to it.
- `app.state.feature_service` — built in `create_app` rather than in the
  lifespan, because `/daemon/status` reports feature switches and must answer
  before the lifespan runs. The lifespan and two wiring steps
  (`channel_wiring.py`, `knowledge_wiring.py`) read it from there; this is the
  one place a wiring step reads `app.state` for an input.
- `app.state.mcp_session_supervisors`, `app.state.background_workers`,
  `app.state.sync_contributions` — published as seams for tests that assert the
  lifespan really registered or started something, never read by production
  code.

The CLI (`surfaces/cli/main.py`) is a daemon client: it mounts each kind's
Typer group statically and holds no `Kind`.

## Consequences

- A new kind is added in the composition root by hand: its `*_wiring.py`
  step (returning a frozen result), its place in `wire_resource_kinds`, its
  routers in `routing.py`, its provider module, its CLI group. The order is
  reviewed where it is written.
- Only the composition root (`surfaces/http/app.py`, `*_wiring.py`,
  `*_composition.py`, `surfaces/cli/main.py`) may import two kinds; the
  cross-kind import-linter contracts name it as the exception, and everything
  else crosses through ports the consuming kind declares.
- An area that needs to take part in sync must accept the `SyncContributions`
  parameter; registering anywhere else does nothing, and the test seam on
  `app.state.sync_contributions` is what catches an area that forgot.
- Adding to the `app.state` list above is a design change and should be
  argued, not a convenience; the `feature_service` read inside two wiring
  steps is the recorded exception, justified by the pre-lifespan status route.
- The `app.py` module docstring still describes `app.state` as carrying only
  `kinds` and `mcp_session_supervisors`; the list above is the accurate one.
