# Resource Framework

The Resource framework is Coffer's core abstraction. Understanding it is the key to understanding how the system scales gracefully as new managed entity types are added.

## Everything is a resource kind

Every user-managed entity in Coffer is a **Resource**, identified by a stable string of the form `<kind>:<name>`. Six kinds are registered today:

| Kind             | Spec                                                   | Description                                                                                                       |
| ---------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [001-mcp-gateway](/reference/specs/001-mcp-gateway/spec)         | A registered upstream MCP server: transport config, credential references, and the per-server gateway policies.  |
| `agent`          | [004-agent-registry](/reference/specs/004-agent-registry/spec)   | A registered local AI coding agent (e.g. Claude Code): its config directory, Coffer-MCP install state, and derived workspace facets. |
| `skill`          | [005-skill-manager](/reference/specs/005-skill-manager/spec)     | A master skill bundle Coffer delivers into one or more agents' skill directories.                                |
| `knowledge_base` | [006-knowledge-base](/reference/specs/006-knowledge-base/spec)   | KB face of the shared knowledge substrate: any-format upload → markdown truth + grep / FTS5 / vector retrieval.  |
| `memory`         | [007-memory](/reference/specs/007-memory/spec)                   | memory face of the same substrate: per-fact markdown + regenerated `MEMORY.md`, shared across agents.            |
| `channel`        | [009-channels](/reference/specs/009-channels/spec)               | A messaging-channel binding (Telegram, SeaTalk): transport config, credential refs, and a default agent.         |

`knowledge_base` and `memory` are two faces of **one knowledge substrate** — markdown files on disk are the source of truth and SQLite is a rebuildable index ([ADR-012](/reference/adr/ADR-012-files-as-truth-sqlite-retrieval)). New kinds plug into the same framework without modifying it. The encrypted credential store and multi-machine sync are deliberately **cross-cutting concerns, not kinds**: they serve every kind rather than being managed entities in their own right.

The framework provides four things, and only four things:

| Concern               | What the framework does                                                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Identity**          | Assigns each resource a `kind`, a `name`, and the composite stable reference `<kind>:<name>`.                                     |
| **Lifecycle**         | Defines and enforces the states a resource can be in: registered, enabled, disabled, deleted.                                     |
| **Audit**             | Records every lifecycle change with a timestamp and an actor (`cli`, `api`, `ui`, `system`).                                      |
| **Schema validation** | Dispatches per-kind Pydantic schema validation at the application boundary, while the dispatch mechanism itself is kind-agnostic. |

::: warning What the framework does NOT do
The Resource framework does not unify invocation semantics. Each kind defines how its capabilities are used. There is no god `invoke()` method, no shared call path, no cross-kind behavior. The framework describes how a resource is registered, described, and curated — not what happens when you use it.
:::

## Why kind-agnostic upfront (ADR-001)

The constitution normally defers cross-cutting abstractions until a second feature needs them ("extract on second feature"). The Resource framework is an explicit exception, and the reason is cost asymmetry.

The framework spans every layer: domain entities, database schema, audit table, retention framework, surface routing (REST API sub-routers, CLI subcommand groups). If this abstraction had been designed as an `mcp_server`-specific implementation in the first spec and then extracted when a second kind arrived, the refactoring cost would not be a modest extraction — it would require re-modeling the audit table, the surface routing, and the retention framework simultaneously. The "second feature" refactor would be a substantial, risky migration, not a clean module move.

The alternative of building per-kind silos with no shared abstraction was also rejected: with multiple kinds planned with high confidence (six are registered today), building identity + lifecycle + audit + surface CRUD separately for each would produce more code and more drift than one framework.

The consequence is that the first spec (`001-mcp-gateway`) carries the framework's abstraction overhead with only one concrete kind to justify it. This is accepted as a known cost, explicitly balanced against the avoided refactor.

## Identifier format: `<kind>:<name>` (ADR-003)

Resources are referenced externally by the string `<kind>:<name>`:

- CLI: `coffer resource show mcp_server:filesystem`
- REST API URL: `/api/v1/resources/mcp_server/filesystem`
- Config references: an agent's `tools` field listing `mcp_server:filesystem`

The format is self-describing: the prefix tells you which kind to look in, eliminating one lookup in many code paths. It is human-readable and survives debugging without a decoder ring.

Internally, the database uses a surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT` for joins and foreign keys, with a `UNIQUE (kind, name)` constraint enforcing the external identifier's uniqueness. A `ResourceRef(kind: str, name: str)` domain value object handles parsing and serialization at the application boundary — raw strings never enter the domain layer.

**Rejected alternatives:**

- **Full URN** (`urn:coffer:mcp_server:filesystem`): Rejected because Coffer is single-user local-first — there is no other Coffer installation to distinguish from, making the `urn:coffer:` prefix pure ceremony.
- **Pure UUID**: Rejected because opaque, not self-describing, and forces a separate `kind` field on every reference.
- **Path-style** (`mcp_server/filesystem`): Functionally equivalent but rejected because slashes are overloaded in URLs, file paths, and many DSLs; the colon makes the kind-namespace relationship clearer.

## Capability state model (ADR-004)

Each resource moves through a defined lifecycle. The state machine is intentionally simple:

```mermaid
stateDiagram-v2
    [*] --> registered : register

    registered --> enabled : enable
    registered --> disabled : disable
    registered --> deleted : delete

    enabled --> disabled : disable
    enabled --> deleted : delete

    disabled --> enabled : enable
    disabled --> deleted : delete

    deleted --> [*]
```

**registered** — the resource exists in the database with its configuration. It has not yet been explicitly enabled or disabled.

**enabled** — the resource is active. For `mcp_server`, this means the daemon will connect to it and expose its tools to MCP clients.

**disabled** — the resource configuration is retained, but the daemon will not connect to it or expose its tools. Disabling is non-destructive: re-enabling brings it back without re-registration.

**deleted** — the resource is removed. This is a terminal state. Re-adding a server with the same name is a new registration.

Every state transition is recorded in the audit log with an actor. The audit log cannot be modified or deleted through the normal API — it is append-only.

For `mcp_server` specifically, there is a parallel capability-level state: each individual tool, resource, or prompt exposed by an upstream server can be individually enabled or disabled (per ADR-004). The database stores only user preference flags for these capabilities — it does not cache capability schemas or descriptions. Those are fetched live from the upstream on each request and held in a per-session in-memory cache with a 60-second TTL.

## Kind registration at the composition root

The framework uses no global registry and no import side effects. Each kind is wired in explicitly at the composition root via a `KindModule` dataclass. The composition roots are `surfaces/http/app.py` (FastAPI wiring) and `surfaces/cli/main.py` (Typer wiring).

Adding a new kind is mechanical: create the kind's subdirectories in each layer (`domain/<kind>/`, `application/<kind>/`, `infrastructure/<kind>/`, `surfaces/http/<kind>/`, `surfaces/cli/<kind>/`), implement the kind-specific logic, and register a `KindModule` at the composition root. The audit, retention, and resource-list surfaces are inherited automatically.

## Why "everything is a resource kind" (ADR-007)

The information architecture follows the same principle as the domain model: there is a single-axis navigation model where every user-facing managed entity is a resource kind, surfaced through the same sidebar group. There is no separate "surface" concept sitting beside the resource concept.

This eliminates the question "is this new thing a kind or a surface?" for every future spec. Operational tooling — observability, settings — appears in a separate System group; everything the user manages appears in the Resources group.

A deliberate policy follows: **no "coming soon" placeholders**. A kind is not shown in the UI or sidebar until it actually works. The UI always reads as "here is what Coffer does", not "here is what Coffer plans to do."

---

**See also:** [ADR-001: Resource framework upfront](/reference/adr/ADR-001-resource-framework-upfront), [ADR-007: Everything is a resource kind](/reference/adr/ADR-007-everything-is-a-resource-kind), [ADR-003: Resource identifier format](/reference/adr/ADR-003-resource-identifier-format), [ADR-004: Capability state model](/reference/adr/ADR-004-capability-state-model)
