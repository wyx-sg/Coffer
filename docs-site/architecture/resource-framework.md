# Resource Framework

The Resource framework is Coffer's core abstraction. Understanding it is the key to understanding how the system scales gracefully as new managed entity types are added.

## Everything is a resource kind

Every user-managed entity in Coffer is a **Resource**, identified by an immutable `uid`. **Seven** kinds are registered today — one `make_<kind>_kind()` factory each, under `application/<kind>/kind.py`:

| Kind             | Spec                                                   | Description                                                                                                       |
| ---------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | `mcp-gateway`         | A registered upstream MCP server: transport config, credential references, and the per-server gateway policies.  |
| `agent`          | `agent-registry`   | A registered local AI coding agent (e.g. Claude Code): its config directory, Coffer-MCP install state, and derived workspace facets. |
| `skill`          | `skill-manager`     | A master skill bundle Coffer delivers into one or more agents' skill directories.                                |
| `knowledge`      | `knowledge`             | One collection of what agents know: one tree of Markdown documents that people and Coffer's curation pass write together; agents read it with their own `Read`/`Grep`. |
| `memory`         | `memory`                   | One partition of the facts Coffer aggregated out of the agents' *own* native memory — `global` plus one per project — as files under `~/.coffer/memory/`. |
| `provider`       | `provider-switching` | A vendor endpoint and its key: `{protocol, base_url, credential_ref}`. One may be the internal default Coffer's own passes run on. |
| `channel`        | `channels`               | A messaging-channel binding (Telegram, SeaTalk): transport config, credential refs, and a default agent.         |

`knowledge` was once two kinds — a `knowledge_base` you could only read and a `memory` only agents wrote to — but they shared their storage from the start, so the split bought nothing and forced every caller to classify its own data before it could pick a tool. They are now one kind over one storage root: a knowledge resource **is** the directory `~/.coffer/knowledge/<name>/`, and the markdown files in it are the whole of its content. The kind adds no table of its own — the `resources` row carries the collection's identity and description, the files carry everything else. A knowledge resource is **co-managed**: both you and your agents write into it.

Today's `memory` kind is a different thing from that retired one, and the distinction is load-bearing: it is **derived, not co-managed**. Coffer reads each agent's native memory and normalises it into facts; it never writes back.

New kinds plug into the same framework without modifying it. The encrypted credential store and vault sync are deliberately **cross-cutting concerns, not kinds**: they serve every kind rather than being managed entities in their own right.

The framework provides four things, and only four things:

| Concern               | What the framework does                                                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Identity**          | Mints each resource an immutable `uid` and records its `kind` beside a mutable `name` label.                                      |
| **Lifecycle**         | Defines and enforces the states a resource can be in: registered, enabled, disabled, deleted — and renaming, which is a field on `PATCH /api/v1/resources/{uid}` rather than a state change. |
| **Audit**             | Records every lifecycle change with a timestamp and an actor (`cli`, `api`, `ui`, `system`).                                      |
| **Schema validation** | Dispatches per-kind Pydantic schema validation at the application boundary, while the dispatch mechanism itself is kind-agnostic. |

::: warning What the framework does NOT do
The Resource framework does not unify invocation semantics. Each kind defines how its capabilities are used. There is no god `invoke()` method, no shared call path, no cross-kind behavior. The framework describes how a resource is registered, described, and curated — not what happens when you use it.
:::

## Why kind-agnostic upfront (ADR resource-framework-upfront)

Coffer's principles normally defer cross-cutting abstractions until a second feature needs them ("extract on second feature"). The Resource framework is an explicit exception, and the reason is cost asymmetry.

The framework spans every layer: domain entities, database schema, audit table, retention framework, surface routing (REST API sub-routers, CLI subcommand groups). If this abstraction had been designed as an `mcp_server`-specific implementation in the first spec and then extracted when a second kind arrived, the refactoring cost would not be a modest extraction — it would require re-modeling the audit table, the surface routing, and the retention framework simultaneously. The "second feature" refactor would be a substantial, risky migration, not a clean module move.

The alternative of building per-kind silos with no shared abstraction was also rejected: with multiple kinds planned with high confidence (seven are registered today), building identity + lifecycle + audit + surface CRUD separately for each would produce more code and more drift than one framework.

The consequence is that the first spec (`mcp-gateway`) carries the framework's abstraction overhead with only one concrete kind to justify it. This is accepted as a known cost, explicitly balanced against the avoided refactor.

## Identity: an immutable `uid` (ADR resource-identity-is-an-immutable-uid)

A resource's external identity is its **`uid`** — an opaque `uuid4().hex`, minted once when the resource is created, never reused, and the **same value on every machine that holds that resource**:

- REST API URL: `/api/v1/resources/{uid}`, and the per-kind routes under it (`/api/v1/resources/mcp_server/{uid}/capabilities`)
- Sync bundle: one document per resource at `resources/<kind>/<uid>.yaml`, carrying its `uid` inside
- Cross-resource references: a resource `scope`'s agent list, a channel's `default_agent`

`name` is a **mutable label**. It stays unique within its kind — you should not have two skills called the same thing — but uniqueness is a constraint, not an identity. Renaming is a field on `PATCH /api/v1/resources/{uid}`, available to every kind; the three file-backed kinds (`skill`, `knowledge`, `memory`) move their directory through an `on_rename` hook, which is the whole of what rename costs.

Nobody is asked to type a UUID. The CLI still takes names and resolves them to a `uid` once, at the surface (`surfaces/cli/_resolve.py`, the single place a label becomes an identity): `coffer resource show mcp_server filesystem`, `coffer resource rename mcp_server filesystem files`. `kind` remains a field on every response and a namespace in the route prefixes, so the self-description the old scheme valued survives — only the part of it that was pretending to be an identity is gone.

Internally, the database keeps its surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT` for joins and foreign keys, unchanged: it is the FK the four kind-owned tables hold, it is per-machine, and it is never an external identity. `UNIQUE (kind, name)` still enforces the label's uniqueness, and `uid` carries its own unique index.

**Why it changed.** The identifier used to be the string `<kind>:<name>`, on the reasoning that Coffer is single-user local-first with no other installation to distinguish from. Vault sync ended that: a vault now converges across the user's machines through a git remote, so the question the identifier has to answer is "is the thing on that machine the same thing as the thing on this one?" — which a name cannot answer, because a name is exactly what the user is allowed to change. A rename crossed the remote as a deletion plus a creation, cascading away the renamed resource's paired chats, capability preferences and skill bindings. The `<kind>:<name>` string form and the `ResourceRef` value object are **deleted**, not kept as a label, so there is only one spelling of identity in the codebase; `ref` is gone from every response, leaving three plain fields — `uid`, `kind`, `name`.

**How two machines agree on a `uid` without talking.** They cannot negotiate — a vault converges through a git remote with no online handshake — so the migration that introduced `uid` backfilled existing rows deterministically, as `uuid5(COFFER_RESOURCE_NAMESPACE, "<kind>:<name>")`. `(kind, name)` is the one thing every machine in a fleet provably agreed on at the moment it upgraded, because it *was* the identity until then, so every machine computes the same value independently with no protocol. Afterwards the derivation is never used again and new resources get a random `uuid4().hex`, which is what keeps "delete `foo`, create a new `foo`" from resurrecting the old resource's identity. A machine on an older build is handled by the bundle's layout `schema_version`, which went 1 → 2: it refuses a too-new tree and tells the user to upgrade.

## Capability state model (ADR capability-state-model)

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

**deleted** — the resource is removed. This is a terminal state. Re-adding a server with the same name is a new registration, with a new `uid`: the name is free to be reused, the identity never is.

Every state transition is recorded in the audit log with an actor. The audit log cannot be modified or deleted through the normal API — it is append-only.

For `mcp_server` specifically, there is a parallel capability-level state: each individual tool, resource, or prompt exposed by an upstream server can be individually enabled or disabled. The database stores only user preference flags for these capabilities — it does not cache capability schemas or descriptions. Those are fetched live from the upstream on each request and held in a per-session in-memory cache with a 60-second TTL.

## Kind registration at the composition root

The framework uses no global registry and no import side effects. Each kind exposes a factory — `make_<kind>_kind()` in `application/<kind>/kind.py` — that returns a frozen `Kind`, and the composition root wires the kind in explicitly: one `*_wiring.py` module per kind builds its services, registers its routers and returns a typed dataclass the root passes forward. The composition roots are `surfaces/http/app.py` (FastAPI wiring) and `surfaces/cli/main.py` (Typer wiring).

A `Kind` carries the small set of answers the framework needs and the kind alone can give: whether the generic `POST /api/v1/resources` may create one (`generic_create_allowed`), whether it has a per-agent activation scope (`supports_scope`), and whether its rows converge with the sync remote (`converges`). The last of those exists so the sync layer has one rule rather than a list of exceptions — `memory` is the only kind that answers no, because a partition row is derived from the agents installed on one machine. A kind nobody has declared anything about converges, so the flag can only ever withhold.

Adding a new kind is mechanical: create the kind's subdirectories in each layer (`domain/<kind>/`, `application/<kind>/`, `infrastructure/<kind>/`), its routes (a `surfaces/http/<kind>/` package or a `<kind>_routes.py` module) and a `surfaces/cli/<kind>_cmd.py` Typer group, implement the kind-specific logic, write its `make_<kind>_kind()` factory, and add one wiring module the composition root calls. The audit, retention, and resource-list surfaces are inherited automatically.

## Why "everything is a resource kind" (ADR everything-is-a-resource-kind)

The information architecture follows the same principle as the domain model: there is a single-axis navigation model where every user-facing managed entity is a resource kind, surfaced through the same sidebar group. There is no separate "surface" concept sitting beside the resource concept.

This eliminates the question "is this new thing a kind or a surface?" for every future spec. Operational tooling — Activity, Sync, Settings — appears in a separate System group; everything the user manages appears in the Resources group, one entry per kind with a list UI.

A deliberate policy follows: **no "coming soon" placeholders**. A kind is not shown in the UI or sidebar until it actually works. The UI always reads as "here is what Coffer does", not "here is what Coffer plans to do."
