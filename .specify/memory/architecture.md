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
| `knowledge`      | [knowledge](../../specs/knowledge/spec.md)                 | The knowledge layer — one kind for everything an agent knows. Scope is read from the resource name: `global` and `project-<ULID>` (resolved from the cwd's git root) auto-provision on first use, any other name is a collection the user created deliberately and never auto-provisions. One storage root `~/.coffer/knowledge/<scope>/` with two lanes — `notes/` (what an agent or the user wrote; `coffer__write` lands here) and `docs/` (uploaded documents, normalized to markdown) — plus a hidden `.history/` holding pre-rewrite copies and a hidden `.raw/` holding the uploaded originals. Agents both read and write it over MCP; markdown files are truth, SQLite is a rebuildable index. See [Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md) + [One Shared Knowledge Store](../../docs/decisions/agent-native-shared-memory.md). |
| `channel`        | [channels](../../specs/channels/spec.md)             | A messaging-channel binding (Telegram, SeaTalk). Carries transport config + credential refs and a default agent; a paired owner chats with managed agents from the IM app and receives notifications. Thin adapters over the turn-platform seams (spec channels FR-043…FR-055) ([Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)).                                                                                              |

The knowledge layer is **one substrate**: **markdown files on disk are the
source of truth; SQLite is a rebuildable index** (`coffer reindex` reconstructs
it from the files). It was always one substrate — `documents`, `chunks`, FTS5
and sqlite-vec were shared from the start, and only the facade was split in two
(a `memory` kind and a `knowledge_base` kind) until the two merged into this one
kind on **2026-09-10**. A stored lane discriminator `documents.lane`
(`notes` | `docs`) records which writer owns an indexed row — note and
document counts are lane-scoped — but retrieval deliberately spans both lanes,
because unified search is the whole point of the merge. The classification axis
is what a person actually distinguishes: what someone wrote, and what someone
uploaded. Nothing else is a lane — the earlier `knowledge/inbox/` gradient,
`rules/`, `handoff/` and `superseded/` were retired on **2026-09-11**, and with
the handoff lane went the `coffer__set_handoff` and `coffer__resume` tools, so
the layer exposes six: `coffer__search`, `coffer__grep`, `coffer__read`,
`coffer__list`, `coffer__write`, `coffer__delete`.

`notes/` is kept readable by a **periodic tidy**: a bounded agentic pass that
merges duplicate notes and rewrites them into topic documents, copying the prior
revision into `.history/` before any overwrite or merge. It is run by a
background worker shaped like the `RetentionWorker` — one catch-up pass on boot,
then on an interval — no-ops when no internal model is configured, and can also
be triggered by hand from the UI or `coffer knowledge organize`. Each pass is
recorded in Coffer's own audit log; there is no per-scope changelog file.

Ingestion converts any format to markdown behind a `MarkdownConverter` port in
infrastructure (`markitdown[docx,pdf,pptx,xls,xlsx]` by default), keeps the
original under `.raw/` for provenance, chunks, tracks external sources
(`check-sources` / `update-source`) and reindexes. Retrieval modes — `grep` (raw
files), `keyword` (FTS5 + `bm25()`), `vector` (sqlite-vec) and `hybrid` — are an
**internal engine detail**, not a caller-facing choice
([Retrieval Mode Is Internal](../../docs/decisions/retrieval-mode-is-internal.md)).
Per-scope config carries no embedding fields: embedding resolves through the
installation-wide config, and a scope opts into vector search purely by listing
the retrieval mode. The substrate and retrieval decisions are in
[Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md) and
[One Shared Knowledge Store](../../docs/decisions/agent-native-shared-memory.md); they
supersede the LlamaIndex and mem0 engines. Agents reach the
layer over MCP only — native projection into agent config files was retired by
[Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md).

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
│   ├── knowledge/               # scope, lane, entry, document, retrieval VOs
│   └── channel/                 # channel config, envelopes, seatalk signing
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD; takes kinds dict
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── credentials/              # shared CredentialResolver (refs → secrets)
│   ├── mcp/                      # MCP-specific application services
│   ├── agent/                   # agent services + make_agent_kind
│   ├── skill/                   # skill services + make_skill_kind
│   ├── knowledge/               # knowledge services + make_knowledge_kind
│   ├── channel/                 # adapter protocol, pairing, inbound, runtime
│   └── fs/                      # filesystem-browse service
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (central metadata)
│   ├── credentials/              # encrypted credential store + master key — only place importing `keyring`
│   ├── daemon/                   # pid_lock, port allocation
│   ├── mcp/                      # subprocess, http upstream client
│   ├── agent/                   # agent config-file store
│   ├── skill/                   # master store, sync engine
│   ├── knowledge/               # file tree, converters, chunking, FTS5 + sqlite-vec index
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
| Web UI                         | daemon                 | The built frontend, served by the daemon as static files at its own loopback origin — same-origin with the API, so there is no desktop shell to rebuild and reinstall. `coffer open` mints a single-use, short-lived code, opens the browser at that origin with the code in the URL fragment, and the page exchanges it for the API token (spec mcp-gateway FR-024 / FR-025). |
| MCP protocol                   | daemon                 | `/mcp` HTTP/SSE endpoint speaking MCP JSON-RPC.                                                              |
| CLI (`coffer …`)               | short-lived child      | Calls daemon over loopback HTTP.                                                                             |
| Stdio shim (`coffer-mcp-shim`) | per MCP-client session | `stdin/stdout ↔ daemon HTTP/SSE` forwarder; detect-or-spawn daemon.                                         |
| Callback listener              | daemon-spawned child   | Signed channel webhooks only (`POST /seatalk/{channel}`); loopback port behind a user-run tunnel (spec channels). |

## Processes

- **`coffer-daemon`** — long-lived FastAPI service on `127.0.0.1:<auto-port>`.
  Owns all state; single SQLite writer.
- **Stdio shim** — short-lived; lifecycle bound to one MCP client process.
- **Callback listener** — daemon-spawned child serving only signed channel
  callback paths on `127.0.0.1:<callback-port>`; runs while any SeaTalk
  channel is enabled (spec channels, [Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)).

Both discover the daemon through `~/.coffer/daemon.json` (PID + port +
token, mode `0600`). See [Detect-or-Spawn](../../docs/decisions/daemon-detect-or-spawn.md).

## Persistence

- **SQLite** at `~/.coffer/coffer.db`, WAL mode, single writer.
- **SQLAlchemy 2.0 async** ORM; **Alembic** central migrations (all kinds
  register their ORM models against one metadata). Migrations run on daemon
  startup (`upgrade head`); if the DB's current revision is unknown to the
  running build (created by a newer/divergent version), startup fails fast
  with `DB_SCHEMA_TOO_NEW` instead of an opaque Alembic error.
- JSON fields stored as `TEXT` validated by Pydantic at the application
  boundary.
- **Knowledge substrate index in the same `coffer.db`:** SQLite **FTS5**
  (a regular FTS5 table storing the chunk text once inside its index, `bm25()`
  keyword ranking) + **sqlite-vec** (vector KNN over chunk embeddings). No
  separate chroma / LlamaIndex / mem0 store — the markdown files under
  `~/.coffer/knowledge/<scope>/` are the truth; the DB
  (including the FTS index) is rebuildable from them ([Files as Truth](../../docs/decisions/files-as-truth-sqlite-retrieval.md)).
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
| Converters        | `MarkdownConverter` port + per-format adapters in `infrastructure/`                              | Only place importing converter libs (passthrough for text/code, csv converter, MarkItDown for the rest; new engines pluggable per format). any-format → markdown.                                                                                                                                                                                                                                                                                                                                                                                                  |
| Export / import   | `application/sync/` + `infrastructure/sync/` + CLI and HTTP surfaces | One-shot vault **export to a directory** and **import of one back** (spec vault-export-import, [Vault Export and Import](../../docs/decisions/vault-export-import.md)). No git, no remote, no workspace, no background worker, no tombstones, and no tables of its own. Export mirrors the knowledge and skill file trees, serializes each config resource to one **deterministic** YAML, dumps module-owned shared state, and carries credentials as **ciphertext only** when explicitly asked (master key bootstrapped out-of-band). Import is bundle-wins per resource, never deletes, reports per-resource failures, and runs each kind's post-import hook. `$HOME`-relative path normalization makes a bundle portable between machines. Cross-cutting, not a kind. Resource `scope` — a list of agent names ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)) — rides the resource documents through export and import as an ordinary field. |
