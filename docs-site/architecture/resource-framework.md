# Resource Framework

The Resource framework is Coffer's core abstraction. Understanding it is the key to understanding how the system scales gracefully as new managed entity types are added.

The framework is spec `resource-framework`: the kind registry, the lifecycle surface, per-agent reach, the audit log, per-table retention and the cross-kind read of the passes in flight. What a kind *is* belongs to that kind's own spec.

## Everything is a resource kind

Every user-managed entity in Coffer is a **Resource**, identified by an immutable `uid`. **Seven** kinds are registered today — one `make_<kind>_kind()` factory each, under `application/<kind>/kind.py`:

| Kind         | Spec                 | Description |
| ------------ | -------------------- | ----------- |
| `mcp_server` | `mcp-gateway`        | A registered upstream MCP server. Carries transport configuration, credential references, and the per-server policies the gateway needs. |
| `agent`      | `agent-registry`     | A registered coding agent (Claude Code or Codex), stored as a row of the generic `resources` table. Per-type behaviour is data, not branches: `AGENT_DESCRIPTORS` (`domain/agent/descriptor.py`) holds one record per type, so adding a product means one enum value plus one record. Carries its config directory and the Coffer-MCP install state; the install writes an absolute `coffer-mcp-shim` path (`COFFER_MCP_SHIM_PATH` → `PATH` → the interpreter's scripts dir → the bundled binary), because a GUI- or venv-launched daemon does not inherit the shell `PATH`. The agent's own files are the source of truth and are never copied into SQLite: config files, MCP entries, plugins, native memory and transcripts are all derived at read time. Coffer writes only an agent's documented surfaces, addressed by allowlist key, atomically and with a `.bak` (Codex TOML through `tomlkit`, so comments and ordering survive) — config-file edits, MCP entry remove and adopt, and the plugin enable switch. Internal state (`installed_plugins.json`, `auth.json`, session files) is only read; a write that has to reach it is delegated to the agent's own CLI (`claude plugin uninstall`). |
| `skill`      | `skill-manager`      | A master skill bundle Coffer delivers into one or more agents' skill directories, plus an unmanaged-skill scan that adopts hand-placed skills into the master store. Delivery is decided by the skill's own `enabled` flag intersected with its agent scope and reconciled on every change to either. One skill is Coffer's own: `coffer-guide`, whose `builtin` source means the master folder is rewritten from the running build at every boot and whenever the knowledge catalogue moves, whose deletion is refused (`RESOURCE_PROTECTED`, 409) while `enabled` and scope stay the owner's, and which is otherwise delivered, verified, repaired and audited by exactly the same code as an imported skill (ADR coffer-ships-its-own-skill). |
| `knowledge`  | `knowledge`          | One **collection** — a top-level folder under `~/.coffer/knowledge/` holding one tree of Markdown documents that people and Coffer's curation pass write together, plus a hidden `.inbox/` of new material waiting to be merged. Agents read it with their own `Read`/`Grep`. The collection is the only boundary the system knows; its one switch is `enabled`, which decides whether it is served at all. It carries **no per-agent reach** — every enabled collection is catalogued into every agent's delivered skill (spec knowledge "Gate collections with enabled alone"). Nothing is derived from a cwd and nothing auto-provisions. See [Knowledge lifecycle](/architecture/request-lifecycle#knowledge-lifecycle). |
| `memory`     | `memory`             | One **partition** of aggregated agent memory — `global` plus one per project — as files under `~/.coffer/memory/`. Its facts are read out of the registered agents' own native memories, never written back; everything on disk is derived and rebuildable, with no non-derived state beside it. It carries **no per-agent reach**: an enabled partition is delivered to, and recalled by, every agent (spec memory "Serve every enabled partition to every agent"). Aggregation skips a source file whose content digest matches the last pass (a flat `.source_state.json` under the memory root) only while the raw entries it produced are still on disk, so deleting the tree always rebuilds it. |
| `provider`   | `provider-switching` | One **model-provider profile** — a wire protocol, a base URL and one `credential_ref`. Pure config with no on-disk artifact, so it takes the framework's generic create/update path. Its per-agent scope names the agents it projects into; `application/provider/targets.py` is the enforcement point the switch, the per-agent key lookup, the import reconcile and the boot self-heal all read. A new profile starts scoped to the agents its protocol can actually serve rather than to every agent. One may be the internal default Coffer's own passes run on. |
| `channel`    | `channels`           | A messaging-channel binding (Telegram, SeaTalk). Carries transport config, credential refs and a default agent; a paired owner chats with managed agents from the IM app and receives notifications. Its per-agent scope is read **inverted** — it names the agents this channel may drive, since a channel is an inbound surface no agent consumes — narrowing `/agent` and the channel's own default agent; a channel that may drive nothing does not run. A channel converges with the sync remote and carries `runs_on` — the `machine_id` of the one machine whose daemon starts its adapter, so the document travels and the adapter does not (spec channels "Bind each channel to the one machine that runs it"). Channels are thin adapters over the turn-platform seams of spec chat, which the web Chat page also sits on — once a message reaches the turn orchestrator nothing downstream knows which surface it came from. |

`knowledge` was once two kinds — a `knowledge_base` you could only read and a `memory` only agents wrote to — but they shared their storage from the start, so the split bought nothing and forced every caller to classify its own data before it could pick a tool. They are now one kind over one storage root: a knowledge resource **is** the directory `~/.coffer/knowledge/<name>/`, and the markdown files in it are the whole of its content. The kind adds no table of its own — the `resources` row carries the collection's identity and description, the files carry everything else. A knowledge resource is **co-managed**: both you and your agents write into it.

Today's `memory` kind is a different thing from that retired one, and the distinction is load-bearing: it is **derived, not co-managed**. Coffer reads each agent's native memory and normalises it into facts; it never writes back.

New kinds plug into the same framework without modifying it. The encrypted credential store and vault sync are deliberately **cross-cutting concerns, not kinds**: they serve every kind rather than being managed entities in their own right.

The framework provides five things, and only five things:

| Concern               | What the framework does                                                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Identity**          | Mints each resource an immutable `uid` and records its `kind` beside a mutable `name` label.                                      |
| **Lifecycle**         | Defines and enforces the states a resource can be in: registered, enabled, disabled, deleted — and renaming, which is a field on `PATCH /api/v1/resources/{uid}` rather than a state change. |
| **Audit**             | Records every lifecycle change with a timestamp and an actor (`cli`, `api`, `ui`, `system`).                                      |
| **Schema validation** | Dispatches per-kind Pydantic schema validation at the application boundary, while the dispatch mechanism itself is kind-agnostic. |
| **Scope (reach)**     | An optional activation list of agent `uid`s (`null` meaning every agent). The framework owns the field; each kind declares whether it supports scope (`supports_scope`) and owns its enforcement point. Scope and `enabled` together are the resource's **reach**, and reach is machine-local: it is set on the machine it applies to and never converges (ADR per-agent-resource-scope). |

::: warning What the framework does NOT do
The Resource framework does not unify invocation semantics. Each kind defines how its capabilities are used. There is no god `invoke()` method, no shared call path, no cross-kind behavior. The framework describes how a resource is registered, described, and curated — not what happens when you use it. Nor does it *enforce* reach: each kind gates at its own choke point, where the asking identity is known.
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

**deleted** — the resource is removed. This is a terminal state. Re-adding a server with the same name is a new registration, with a new `uid`: the name is free to be reused, the identity never is. A kind may supply a **pre-write delete guard** (`Kind.validate_delete`), run once the resource is resolved and before its cleanup hook, so a refusal costs nothing and reads the same through the kind's own route and the kind-agnostic one — a validator, not a rejection from inside `on_delete`, which is a reaction to a delete already decided. Only `skill` supplies one (spec resource-framework "Let a kind refuse a deletion before anything is torn down").

Every state transition is recorded in the audit log with an actor. The audit log cannot be modified or deleted through the normal API — it is append-only.

For `mcp_server` specifically, there is a parallel capability-level state: each individual tool, resource, or prompt exposed by an upstream server can be individually enabled or disabled. The database stores only user preference flags for these capabilities — it does not cache capability schemas or descriptions. Those are fetched live from the upstream on each request and held in a per-session in-memory cache with a 60-second TTL.

## Kind registration at the composition root

The framework uses no global registry and no import side effects. Each kind exposes a factory — `make_<kind>_kind()` in `application/<kind>/kind.py` — that returns a frozen `Kind`, and the composition root wires the kind in explicitly: one `*_wiring.py` module per kind builds its services, registers its routers and returns a typed dataclass the root passes forward. The composition roots are `surfaces/http/app.py` (FastAPI wiring) and `surfaces/cli/main.py` (Typer wiring).

A `Kind` carries the small set of answers the framework needs and the kind alone can give: whether the generic `POST /api/v1/resources` may create one (`generic_create_allowed`), whether it has a per-agent activation scope (`supports_scope`), and whether its rows converge with the sync remote (`converges`). The last of those exists so the sync layer has one rule rather than a list of exceptions — `memory` is the only kind that answers no, because a partition row is derived from the agents installed on one machine. A kind nobody has declared anything about converges, so the flag can only ever withhold. A kind may refine that per row with `converges_row`: `skill` uses it to withhold the one derived `coffer-guide` row, which each machine renders for itself (see [Vault sync](/architecture/sync#what-travels)).

Adding a new kind is mechanical: create the kind's subdirectories in each layer (`domain/<kind>/`, `application/<kind>/`, `infrastructure/<kind>/`), its routes (a `surfaces/http/<kind>/` package or a `<kind>_routes.py` module) and a `surfaces/cli/<kind>_cmd.py` Typer group, implement the kind-specific logic, write its `make_<kind>_kind()` factory, and add one wiring module the composition root calls. The audit, retention, and resource-list surfaces are inherited automatically.

## The sidebar is grouped by role (ADR sidebar-grouped-by-role)

The domain model is kind-agnostic, but the navigation is not a single "every kind" axis. The sidebar has three role groups: **Agents** (the coding agents Coffer delivers to — stored as resources of kind `agent`, but surfaced on their own because everything else is delivered *to* them), **Resources** (one entry per asset kind: MCP servers, skills, knowledge, memory, providers, channels) and **System** (Activity, Sync, Settings).

A deliberate policy follows: **no "coming soon" placeholders**. A kind is not shown in the UI until it actually works, and the entries of a switched-off experimental feature are hidden rather than greyed out. The UI always reads as "here is what Coffer does", not "here is what Coffer plans to do". There is no frontend kind registry: each kind has its own pages.
