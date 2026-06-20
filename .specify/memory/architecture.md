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
layout is in [ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md).
Enforced by `scripts/check_*.py` and importlinter contracts.

## Resource framework (kind-agnostic core)

Every user-managed entity in coffer is a **Resource** identified by
`<kind>:<name>`. The framework unifies:

- Identity (`kind`, `name`, stable `<kind>:<name>` string reference)
- Lifecycle (register / update / enable / disable / delete)
- Audit (every lifecycle change recorded with actor)
- Schema validation (per-kind Pydantic schema, kind-agnostic dispatch)

It does **not** unify invocation semantics. Each kind defines how its
capabilities are used; the framework only describes how a kind is registered,
described, and curated.

Currently registered kinds:

| Kind             | Spec                                                         | Description                                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md)       | A registered upstream MCP server. Carries transport configuration, credential references, and the per-server policies the gateway needs. The gateway also applies **per-agent server scoping** (`auto` = all enabled servers, `selected` = an allowlist) keyed by an `X-Coffer-Agent` identity the shim forwards; an anonymous session is unscoped ([ADR-026](../../docs/decisions/ADR-026-per-agent-mcp-scoping.md)). |
| `agent`          | [004-agent-registry](../../specs/004-agent-registry/spec.md) | A registered coding agent (e.g. Claude Code). Carries its config directory and the Coffer-MCP install state. The workspace amendment also surfaces the agent's own files as facets — MCP entries (remove/toggle/adopt into Coffer), plugins (toggle/Codex-uninstall), and directory config entries with per-child edit — all derived at read time, never stored.                                                       |
| `skill`          | [005-skill-manager](../../specs/005-skill-manager/spec.md)   | A master skill bundle Coffer can deliver into one or more agents' skill directories. The workspace amendment adds an unmanaged-skill scan (adopt hand-placed skills into the master store) and a per-agent follow-master-library policy (flag + exclusions on the agent's config) that the sync engine reconciles.                                                                                                     |
| `knowledge_base` | [006-knowledge-base](../../specs/006-knowledge-base/spec.md) | **KB face** of the shared knowledge substrate. Any-format upload → converted to markdown (any-format→markdown via a `MarkdownConverter` port, MarkItDown default), `docs/<doc-id>.md` = truth + `raw/` provenance. Agent-read-only; grep / FTS5 / sqlite-vec retrieval. See [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md).                                                                |
| `memory`         | [007-memory](../../specs/007-memory/spec.md)                 | **memory face** of the same substrate. Per-fact `<slug>.md` + regenerated `MEMORY.md` = truth, two-layer scope (global sentinel + per-project ULID). Shared across agents via MCP read/write + native projection (Claude symlink / Codex managed block) — one canonical store, no divergence. See [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md).                                               |
| `channel`        | [009-channels](../../specs/009-channels/spec.md)             | A messaging-channel binding (Telegram, SeaTalk). Carries transport config + credential refs and a default agent; a paired owner chats with chat-platform agents from the IM app and receives notifications. Thin adapters over the spec-008 seams ([ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md)).                                                                                              |

`knowledge_base` and `memory` are two faces of **one knowledge substrate**:
**markdown files on disk are the source of truth; SQLite is a rebuildable index**
(`coffer reindex` reconstructs it from the files). Retrieval is `grep` (raw
files) / `keyword` (FTS5 + `bm25()`) / `vector` (sqlite-vec, opt-in, embeddings
via a configurable OpenAI-compatible client). Format converters sit behind a
`MarkdownConverter` port in infrastructure; per-agent projection adapters live in
the agent layer (memory never authors L1 config). The substrate, retrieval, and
projection decisions are in
[ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) and
[ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md); they
supersede the LlamaIndex (ADR-010) and mem0 (ADR-011) engines.

## Code layout

Layer-first, with kind-specific subdirectories inside each layer. See
[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md).

```
backend/coffer/
├── domain/                       # kind-agnostic entities + kind protocol
│   ├── resource.py               # Resource, Kind, ResourceRef
│   ├── kind_module.py            # KindModule composition-root carrier
│   ├── audit.py
│   ├── mcp/                      # MCP-specific value objects
│   ├── agent/                   # agent-specific value objects (config, etc.)
│   ├── skill/                   # skill-specific value objects
│   └── channel/                 # channel config, envelopes, seatalk signing
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD; takes kinds dict
│   ├── audit_service.py
│   ├── retention_service.py
│   ├── credentials/              # shared CredentialResolver (refs → secrets)
│   ├── mcp/                      # MCP-specific application services
│   ├── agent/                   # agent services + make_agent_kind
│   ├── skill/                   # skill services + make_skill_kind
│   ├── channel/                 # adapter protocol, pairing, inbound, runtime
│   └── fs/                      # filesystem-browse service
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (central metadata)
│   ├── credentials/              # encrypted credential store + master key — only place importing `keyring`
│   ├── daemon/                   # pid_lock, port allocation
│   ├── mcp/                      # subprocess, http upstream client
│   ├── agent/                   # agent config-file store
│   ├── skill/                   # master store, sync engine
│   └── channel/                 # telegram/seatalk transports, peer repo, render
└── surfaces/
    ├── http/                     # FastAPI app + per-kind sub-routers (incl. agent/skill/fs routes)
    ├── cli/                      # Typer app + per-kind subcommand groups
    ├── shim/                     # coffer-mcp-shim entry
    └── callback/                 # channel callback listener (separate process)
```

Composition root (`surfaces/http/app.py`, `surfaces/cli/main.py`) explicitly
wires each of the six kinds — no global registry, no import side effects. Each
kind's `make_*_kind()` factory (`make_mcp_kind`, `make_agent_kind`,
`make_skill_kind`, `make_kb_kind`, `make_memory_kind`, `make_channel_kind`)
returns a frozen `Kind` (`domain/resource.py`), and the composition root
populates the per-app `app.state.kinds` dict (`kind_name → Kind`) directly:
`app_mcp_composition.py` sets `"mcp_server"`, `agent_skill_wiring.py` sets
`"agent"` and `"skill"`, `wiring.py` sets `"knowledge_base"` and `"memory"`,
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
| REST API                       | daemon                 | Management plane: `/api/v1/*`. Token + CORS authenticated.                                                   |
| MCP protocol                   | daemon                 | `/mcp` HTTP/SSE endpoint speaking MCP JSON-RPC.                                                              |
| CLI (`coffer …`)               | short-lived child      | Calls daemon over loopback HTTP.                                                                             |
| Stdio shim (`coffer-mcp-shim`) | per MCP-client session | `stdin/stdout ↔ daemon HTTP/SSE` forwarder; detect-or-spawn daemon.                                         |
| Callback listener              | daemon-spawned child   | Signed channel webhooks only (`POST /seatalk/{channel}`); loopback port behind a user-run tunnel (spec 009). |

## Processes

- **`coffer-daemon`** — long-lived FastAPI service on `127.0.0.1:<auto-port>`.
  Owns all state; single SQLite writer.
- **Stdio shim** — short-lived; lifecycle bound to one MCP client process.
- **Callback listener** — daemon-spawned child serving only signed channel
  callback paths on `127.0.0.1:<callback-port>`; runs while any SeaTalk
  channel is enabled (spec 009, [ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md)).

Both discover the daemon through `~/.coffer/daemon.json` (PID + port +
token, mode `0600`). See [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md).

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
  separate chroma / LlamaIndex / mem0 store — markdown files under
  `~/.coffer/knowledge/` and `~/.coffer/memory/` are the truth; the DB
  (including the FTS index) is rebuildable from them ([ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md)).
- The database file plus daemon discovery file, logs, the knowledge/memory file
  trees, and per-upstream PID files all live under `~/.coffer/` for a single
  backup target.

## Cross-cutting concerns

| Concern           | Location                                                                                         | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Credentials       | `infrastructure/credentials/` (`encrypted_store.py`, `master_key.py`, `keyring_adapter.py`)      | Secrets stored only as Fernet ciphertext in the `credentials` table; the master key (`0600` file by default, OS keychain opt-in) and legacy migration are the sole `keyring` users. The **daemon is the sole credential-store owner**: every surface (desktop, CLI, shim) reaches secrets through the daemon's `/api/v1/credentials` routes and toggles master-key storage via `/api/v1/settings/credentials` — the CLI never touches the store in-process (spec 006). Refs in config; materialized (decrypted) at upstream-spawn time; plaintext never persisted. |
| Audit             | `domain/audit.py` + `application/audit_service.py` + `audit_log` table                           | Every resource lifecycle change. Actor (cli / api / ui / system) required.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Retention         | `application/retention_service.py` + `retention_policies` table + asyncio worker                 | Each log-style table registers as a `PrunableTable`; central registry enforces SQL allowlist.                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Errors            | `domain/errors.py` + FastAPI global handlers                                                     | Uniform `{error: {code, message, details}}` envelope; `X-Coffer-Trace` header for correlation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Logging           | `structlog` JSON-per-line to `~/.coffer/logs/`                                                   | Per-request trace IDs via contextvar.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Converters        | `MarkdownConverter` port + per-format adapters in `infrastructure/`                              | Only place importing converter libs (passthrough for text/code, csv converter, MarkItDown for the rest; new engines pluggable per format). any-format → markdown.                                                                                                                                                                                                                                                                                                                                                                                                  |
| Memory projection | `AgentMemoryAdapter` in the **agent layer** (with the agent driver)                              | Projects the one canonical memory store into native locations (`SYMLINK` / `RENDER` / `NONE`); owns the L1 file mutations so memory stays agent-agnostic ([ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)).                                                                                                                                                                                                                                                                                                                                  |
| Sync              | `application/sync/` + `infrastructure/sync/` + `sync_config`/`sync_state` tables + daemon worker | Multi-machine sync over a user-owned git repo (spec 010, [ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md)). A run exports vault state to a separate workspace (`~/.coffer/sync/`), git-merges, then imports: knowledge/memory/skills files mirror, config resources reconcile via `ResourceService`, credentials travel as **ciphertext only** (master key bootstrapped out-of-band). Cross-cutting, not a kind. Opt-in auto-sync worker mirrors the retention worker.                                                                                |
