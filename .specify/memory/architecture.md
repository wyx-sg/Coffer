# Coffer Architecture

> Architectural snapshot of what is currently being built. The _why_ of each
> choice lives in `docs/decisions/ADR-*.md`. This file describes the system
> as scoped by the active specs in `roadmap.md`.

## Layering

```
surfaces  →  application  →  domain
                   ↓
            infrastructure
```

The import rules and the "extract cross-cutting modules only after the second
feature needs them" rule are invariants owned by
[`constitution.md`](./constitution.md); the rationale for the layer-first code
layout is in [Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md).
Enforced by `scripts/check_*.py` and importlinter contracts.

## Resource framework (kind-agnostic core)

Every user-managed entity in coffer is a **Resource** identified by
`<kind>:<name>`. The framework unifies:

- Identity (`kind`, `name`, stable `<kind>:<name>` string reference)
- Lifecycle (register / update / enable / disable / delete)
- Audit (every lifecycle change recorded with actor)
- Schema validation (per-kind Pydantic schema, kind-agnostic dispatch)
- Scope (optional per-agent activation list, framework-owned; each kind
  declares whether it supports scope and owns its enforcement point;
  registered-but-inactive semantics —
  [Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md))

It does **not** unify invocation semantics. Each kind defines how its
capabilities are used; the framework only describes how a kind is registered,
described, and curated.

Currently registered kinds:

| Kind             | Spec                                                         | Description                                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [mcp-gateway](../../specs/mcp-gateway/spec.md)       | A registered upstream MCP server. Carries transport configuration, credential references, and the per-server policies the gateway needs.                                                                                                                                                                                                                                                                                  |
| `agent`          | [agent-registry](../../specs/agent-registry/spec.md) | A registered coding agent (e.g. Claude Code). Carries its config directory and the Coffer-MCP install state. The workspace amendment also surfaces the agent's own files as **read-only** facets — MCP entries (listed, with adopt-into-Coffer the one write), plugins (listed only), and directory config entries with per-child edit — all derived at read time, never stored. Coffer no longer writes into another tool's private config to remove, toggle or uninstall an entry: the plugin toggle/uninstall surface and the MCP entry remove/toggle surface are gone, and with them the `agent_plugin_toggled`, `agent_plugin_uninstalled` and `agent_mcp_entry_removed` audit events.                                                       |
| `skill`          | [skill-manager](../../specs/skill-manager/spec.md)   | A master skill bundle Coffer can deliver into one or more agents' skill directories. The workspace amendment adds an unmanaged-skill scan (adopt hand-placed skills into the master store). Delivery is decided by the skill's own `enabled` flag intersected with its agent scope and reconciled on every change to either — the agent-side follow-master-library policy this row once described is gone.                                                                                                     |
| `knowledge`      | [knowledge](../../specs/knowledge/spec.md)                 | One **collection** — a top-level folder under `~/.coffer/knowledge/` holding markdown files, nested however the user likes. The collection is the only boundary the system knows, and it is a Resource so the framework's per-agent scope can authorize it; nothing is derived from a cwd and nothing auto-provisions. Agents read and write it over MCP, humans in their own editor, and both reach the same bytes. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md). |
| `channel`        | [channels](../../specs/channels/spec.md)             | A messaging-channel binding (Telegram, SeaTalk). Carries transport config + credential refs and a default agent; a paired owner chats with managed agents from the IM app and receives notifications. Thin adapters over the turn-platform seams (spec channels FR-043…FR-055) ([Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)).                                                                                              |

The knowledge layer is **a directory, not an index**. Markdown files under
`~/.coffer/knowledge/<collection>/` are the only copy of anything: there is no
`documents` table, no chunk table, no FTS5 index and no vectors, so nothing has
to be reconciled and a file edited in the user's own editor is live on the very
next read ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md),
which supersedes Files as Truth and Retrieval Mode Is Internal).

A file's **path is its identity** — names are readable slugs, not ULIDs,
because with no index the file name is what an agent reads in a grep result.
Frontmatter carries `title`, `description`, `actor` and timestamps and nothing
else; `description` is required, since the catalogue is the retrieval surface
and a file that fails to describe itself cannot be found. A collection
describes itself in its own `README.md` rather than in a database row, so the
person browsing the folder sees the same sentence the catalogue does.

Retrieval is a **catalogue plus ripgrep**. `list` walks one level at a time —
collections, then a directory's children, each file with its title and
description — and the catalogue is generated by walking the tree at call time,
never materialized. `grep` matches literally or by regex over every collection
the caller may read; `read` returns a whole file. There are no modes, no
ranking, no chunking and no `top_k`, and there is no `search` tool: without a
ranked index it would be a second name for `grep`. Semantic matching moved from
embeddings to the model reading the catalogue, which works while the catalogue
fits in context — into the hundreds of files.

Five MCP tools: `coffer__list`, `coffer__grep`, `coffer__read`,
`coffer__write`, `coffer__delete`. Coffer also **delivers a knowledge skill**
through the existing skill channel (spec knowledge FR-042), because the audit
behind this design found agents never reach for the layer on a tool description
alone — every knowledge call in a month landed on the day the corpus was built.
Nothing is injected into a session and no agent's own memory is written to
([Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)).

A **tidy** pass survives: a bounded agentic rewrite of one collection, driven by
the internal-engine connection, archiving each prior revision into the hidden
`.history/` before touching it. It is always available by hand (the UI, and
`coffer knowledge organize`); the background worker that runs it on an interval
is governed by one installation-wide setting on `internal_engine_config`,
**off by default**, because an unattended rewriter of files a human and an agent
share should be something the operator switches on.

There is no ingestion surface. A human adds knowledge by putting a markdown
file in the directory — the filesystem is the upload path, and the next call
sees it.

## Code layout

Layer-first, with kind-specific subdirectories inside each layer. See
[Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md).

```
backend/coffer/
├── domain/                       # kind-agnostic entities + kind protocol
│   ├── resource.py               # Resource, Kind, ResourceRef
│   ├── kind_module.py            # KindModule composition-root carrier
│   ├── audit.py
│   ├── mcp/                      # MCP-specific value objects
│   ├── agent/                   # agent-specific value objects (config, etc.)
│   ├── skill/                   # skill-specific value objects
│   ├── knowledge/               # catalogue + file value objects, errors
│   └── channel/                 # channel config, envelopes, seatalk signing
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD; takes kinds dict
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── credentials/              # shared CredentialResolver (refs → secrets)
│   ├── mcp/                      # MCP-specific application services
│   ├── agent/                   # agent services + make_agent_kind
│   ├── skill/                   # skill services + make_skill_kind
│   ├── knowledge/               # one service, five tools, tidy, skill seed
│   ├── channel/                 # adapter protocol, pairing, inbound, runtime
│   └── fs/                      # filesystem-browse service
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (central metadata)
│   ├── credentials/              # encrypted credential store + master key — only place importing `keyring`
│   ├── daemon/                   # pid_lock, port allocation
│   ├── mcp/                      # subprocess, http upstream client
│   ├── agent/                   # agent config-file store
│   ├── skill/                   # master store, sync engine
│   ├── knowledge/               # paths, file tree, frontmatter, ripgrep
│   └── channel/                 # telegram/seatalk transports, peer repo, render
└── surfaces/
    ├── http/                     # FastAPI app + per-kind sub-routers (incl. agent/skill/fs routes)
    ├── cli/                      # Typer app + per-kind subcommand groups
    ├── shim/                     # coffer-mcp-shim entry
    └── callback/                 # channel callback listener (separate process)
```

Composition root (`surfaces/http/app.py`, `surfaces/cli/main.py`) explicitly
wires each of the five kinds — no global registry, no import side effects. Each
kind's `make_*_kind()` factory (`make_mcp_kind`, `make_agent_kind`,
`make_skill_kind`, `make_knowledge_kind`, `make_channel_kind`)
returns a frozen `Kind` (`domain/resource.py`), and the composition root
populates the per-app `app.state.kinds` dict (`kind_name → Kind`) directly:
`app_mcp_composition.py` sets `"mcp_server"`, `agent_skill_wiring.py` sets
`"agent"` and `"skill"`, `knowledge_wiring.py` sets `"knowledge"`,
and `channel_wiring.py` sets `"channel"`. `ResourceService` reads that dict
for kind-agnostic dispatch. The surface-layer
artefacts a kind contributes (HTTP routers, Typer groups) are carried by the
`KindModule` dataclass (`domain/kind_module.py`), which references them via
`Any`-typed fields so the domain layer never imports them.

FastAPI dependency providers (`surfaces/http/dependencies.py`) are plain
module-level `set_*` / `get_*` pairs over module-global singletons — the
composition root calls each `set_*` once at startup; the matching `get_*` is
the `Depends()` target and raises if accessed before initialisation. Kind-
specific services are typed `Any` there to keep the kind-agnostic core from
importing kind modules (Contract 6).

## Surfaces

| Surface                        | Process                | Role                                                                                                         |
| ------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| REST API                       | daemon                 | Management plane: `/api/v1/*`. Token authenticated; same-origin by default (`COFFER_DEV_CORS` opts the Vite dev origins in). |
| Web UI                         | daemon                 | The built frontend, served by the daemon as static files at its own loopback origin — same-origin with the API, so there is no desktop shell to rebuild and reinstall. The daemon injects its live API token into the `index.html` it serves (`window.__COFFER_TOKEN__`, every SPA route, `no-store`), so any page it serves is authenticated with nothing persisted; `coffer open` only resolves the daemon's current port and opens the browser there. The served token is what makes the loopback-`Host` check mandatory (spec mcp-gateway FR-024 / FR-025 / FR-027, [The Daemon Serves Its Token in the Page](../../docs/decisions/daemon-serves-the-token-in-the-page.md)). |
| MCP protocol                   | daemon                 | `/mcp` HTTP/SSE endpoint speaking MCP JSON-RPC.                                                              |
| CLI (`coffer …`)               | short-lived child      | Calls daemon over loopback HTTP.                                                                             |
| Stdio shim (`coffer-mcp-shim`) | per MCP-client session | `stdin/stdout ↔ daemon HTTP/SSE` forwarder; detect-or-spawn daemon.                                         |
| Callback listener              | daemon-spawned child   | Signed channel webhooks only (`POST /seatalk/{channel}`); loopback port behind a user-run tunnel (spec channels). |

## Processes

- **`coffer-daemon`** — long-lived FastAPI service on `127.0.0.1:<port>` — the
  port the user fixed in `~/.coffer/daemon-config.json`, else the first free one
  in 8000–8009. Owns all state; single SQLite writer.
- **Stdio shim** — short-lived; lifecycle bound to one MCP client process.
- **Callback listener** — daemon-spawned child serving only signed channel
  callback paths on `127.0.0.1:<callback-port>`; runs while any SeaTalk
  channel is enabled (spec channels, [Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)).

Both discover the daemon through `~/.coffer/daemon.json` (PID + port +
token, mode `0600`) — runtime state, written at start and unlinked at exit.
Its counterpart `~/.coffer/daemon-config.json` holds the settings the daemon
must read *before* it binds, and therefore before any database exists: today,
the optional fixed port. See [Detect-or-Spawn](../../docs/decisions/daemon-detect-or-spawn.md).

## Persistence

- **SQLite** at `~/.coffer/coffer.db`, WAL mode, single writer.
- **SQLAlchemy 2.0 async** ORM; **Alembic** central migrations (all kinds
  register their ORM models against one metadata). Migrations run on daemon
  startup (`upgrade head`); if the DB's current revision is unknown to the
  running build (created by a newer/divergent version), startup fails fast
  with `DB_SCHEMA_TOO_NEW` instead of an opaque Alembic error.
- JSON fields stored as `TEXT` validated by Pydantic at the application
  boundary.
- **The knowledge layer owns no table at all.** A collection is a row in the
  kind-agnostic `resources` table like every other Resource, and its contents
  are files. The eleven tables the indexed layer used — `documents`, `chunks`,
  the six `documents_fts*` tables, `embedding_config` and the two scope side
  tables — were dropped by migration 0066 ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).
- The database file plus daemon discovery file, logs, the knowledge file tree,
  and per-upstream PID files all live under `~/.coffer/` for a single backup
  target.

## Cross-cutting concerns

| Concern           | Location                                                                                         | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Credentials       | `infrastructure/credentials/` (`encrypted_store.py`, `master_key.py`, `keyring_adapter.py`)      | Secrets stored only as Fernet ciphertext in the `credentials` table; the master key (`0600` file by default, OS keychain opt-in) and legacy migration are the sole `keyring` users. The **daemon is the sole credential-store owner**: every surface (web UI, CLI, shim) reaches secrets through the daemon's `/api/v1/credentials` routes and toggles master-key storage via `/api/v1/settings/credentials` — the CLI never touches the store in-process ([Envelope-Encrypted Credentials](../../docs/decisions/envelope-encrypted-credential-store.md)). Refs in config; materialized (decrypted) at upstream-spawn time; plaintext never persisted. |
| Audit             | `domain/audit.py` + `application/audit_service.py` + `audit_log` table                           | Every resource lifecycle change. Actor (cli / api / ui / system) required.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Retention         | `application/retention_service.py` + `retention_policies` table + asyncio worker                 | Each log-style table registers as a `PrunableTable`; central registry enforces SQL allowlist.                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Errors            | `domain/errors.py` + FastAPI global handlers                                                     | Uniform `{error: {code, message, details}}` envelope; `X-Coffer-Trace` header for correlation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Logging           | `structlog` JSON-per-line to `~/.coffer/logs/`                                                   | Per-request trace IDs via contextvar.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Document extraction | `DocumentExtractor` port + `infrastructure/chat/document_extract.py`                           | The only place importing a converter library (MarkItDown, imported lazily and optional). It serves **inbound channel attachments** (spec channels FR-030): a PDF or docx reaches the agent as extracted text rather than an opaque path, degrading to a file attachment when the library or the extraction fails. The knowledge layer converts nothing — the filesystem is its ingestion surface and Markdown is the only format it holds ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).                                                                                                                                                                                                                                                                                                                                                                                                  |
| Export / import   | `application/sync/` + `infrastructure/sync/` + CLI and HTTP surfaces | One-shot vault **export to a directory** and **import of one back** (spec vault-export-import, [Vault Export and Import](../../docs/decisions/vault-export-import.md)). Plus one **backup remote**: a git repository the user owns, that a timer worker exports into, commits to when the export changed, and pushes — one-way backup only, never a merge, never a system of record (constitution 0.5.0 exception). That adds a `sync_remotes` config row, a `GitMirror` port with a single subprocess adapter behind it, and a worker shaped like `RetentionWorker`; restore is an explicit command that can check out an earlier revision before importing. Still no tombstones, no machine registry and no file watcher — those belonged to convergence, which is not built. Export mirrors the knowledge and skill file trees, serializes each config resource to one **deterministic** YAML, dumps module-owned shared state, and carries credentials as **ciphertext only** when explicitly asked (master key bootstrapped out-of-band). Import is bundle-wins per resource, never deletes, reports per-resource failures, and runs each kind's post-import hook. `$HOME`-relative path normalization makes a bundle portable between machines. Cross-cutting, not a kind. Resource `scope` — a list of agent names ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)) — rides the resource documents through export and import as an ordinary field. |
