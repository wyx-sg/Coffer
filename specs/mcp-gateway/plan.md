# Implementation Plan: MCP Gateway

**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

Build the coffer MCP gateway: a local daemon that aggregates upstream MCP
servers and re-exposes their tools, resources, and prompts to one or more MCP
clients (Claude Code, Codex) through a namespaced surface.
Ships together with a CLI and a stdio shim.

The implementation also lays in the kind-agnostic Resource framework — the
first concrete kind is `mcp_server`; later specs add more.

See [./spec.md](./spec.md) for the user-visible contract and the
[ADRs](../../docs/decisions/) for architectural rationale.

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x (e2e)                                                                                                                                                                                       |
| **Primary Dependencies** (added by this spec) | SQLAlchemy 2 + aiosqlite + Alembic, Typer + Rich, structlog, keyring, httpx, `mcp` SDK (official), psutil. E2e: Playwright (`@playwright/test`).                                                                          |
| **Storage**                                   | SQLite at `~/.coffer/coffer.db`, WAL mode, daemon as single writer                                                                                                                                                       |
| **Testing**                                   | Coffer's 4-tier model: unit / integration / contract / e2e. `pytest` (backend) + `Playwright` (MCP e2e). Acceptance markers tie tests to scenarios in [spec.md](./spec.md).                                              |
| **Target Platforms**                          | macOS arm64. FR-022 builds that leg only, and the covering test asserts it (`triples == {"aarch64-apple-darwin"}`); the x64, Windows and Linux legs were never validated end to end.                                       |
| **Project Type**                              | CLI + daemon + stdio shim (multi-process local-first)                                                                                                                                                                   |
| **Performance Goals**                         | Per [spec.md](./spec.md) SC-003: ≤ 50 ms gateway overhead per tool call (median, 100-call sample). Daemon ready in ≤ 5 s from cold start.                                                                                |
| **Constraints**                               | Local-first (127.0.0.1 only); secrets as Fernet ciphertext in the encrypted credential store (master key file-default / keychain opt-in); layered architecture (the importlinter contracts in `backend/pyproject.toml` — 1–4 predate this spec, 5–6 came with it, and the cross-kind fence is now written once per kind); file size ≤ 400 LOC (backend).                                                  |
| **Scale / Scope**                             | Single user; ≤ 3 concurrent MCP clients; ≤ 30 registered MCP servers; ≤ 100 capabilities per server.                                                                                                                     |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                                                     |
| ----------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | ✅         | All HTTP surfaces bind `127.0.0.1`. No cloud calls. SQLite is the only system-of-record.                                                                                  |
| **II. Spec-as-Truth**                     | ✅         | This plan implements [spec.md](./spec.md); spec was committed before code. Every acceptance scenario is owned by at least one test (audited by `make verify-acceptance`). |
| **III. Open-Source-Readiness**            | ✅         | Repo already has MIT licence, CONTRIBUTING.md, Conventional Commits, dependabot. No closed-source dependencies added.                                                     |
| **Languages**                             | ✅         | Python 3.12 + TypeScript 5 (e2e) only.                                                                                                                                   |
| **Architecture: layered**                 | ✅         | importlinter contracts 1–4 already in `backend/pyproject.toml`; this plan adds contracts 5–6 (cross-kind isolation, kind-agnostic core boundary).                         |
| **Persistence: SQLite for control plane** | ✅         | This spec's own state is all in `coffer.db`; it introduces no file-backed user content. (Later specs do — the knowledge, memory and skill trees — and they own their own files.) |
| **Credentials: encrypted store**          | ✅         | Secrets are Fernet ciphertext in the `credentials` table; `infrastructure/credentials/` is the sole `keyring` importer (master key + legacy migration). Resource configs hold only credential **refs** (string keys).                             |
| **Network defaults: loopback-only**       | ✅         | FastAPI binds `127.0.0.1`. CORS allowlist closes browser-CSRF surface. No outbound public-internet calls in v0 except to user-configured upstream HTTP MCP servers.       |

**Resource framework upfront** (ADR resource-framework-upfront) was evaluated against the constitution's
"Cross-cutting modules are extracted only after the second feature needs them"
rule and judged not to apply, because the framework is **core domain**, not
cross-cutting infrastructure. See the Decision § rationale in
[Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md).

## Project Structure

### Documentation (this feature)

```text
specs/mcp-gateway/
├── spec.md              # user-visible contract (committed)
├── plan.md              # this file
├── research.md          # library + protocol choices
├── data-model.md        # entities + SQL schema
├── contracts/
│   └── api.openapi.yaml # management REST contract
└── quickstart.md        # how the feature is used once shipped
```

### Source code

The modules this spec owns — the kind-agnostic core, the MCP kind, the daemon,
and their surfaces. Other kinds' packages sit beside these and belong to their
own specs.

```text
backend/coffer/
├── domain/
│   ├── resource.py                       # Resource, ResourceRef, Kind
│   ├── scope.py                          # Scope — the per-agent activation allow-list
│   ├── audit.py                          # AuditEntry, AuditEventType
│   ├── retention.py                      # RetentionPolicy
│   ├── errors.py / error_base.py / credential_errors.py   # CofferError hierarchy
│   └── mcp/
│       ├── server_config.py              # MCPServerConfig + transports
│       ├── capability.py                 # MCPTool/Resource/Prompt + Preference + Invocation
│       └── namespace.py                  # prefix_tool / parse_prefixed_tool / URI helpers
├── application/
│   ├── resource_service.py               # kind-agnostic CRUD; takes Kind dict
│   ├── resource_scope_ops.py             # the scope write path (validate → persist → react)
│   ├── resource_delete_ops.py            # the delete path, incl. credential release
│   ├── audit_service.py                  # AuditService
│   ├── retention_registry.py             # PrunableRegistry
│   ├── retention_service.py              # registry-driven prune
│   ├── retention_worker.py               # background asyncio task
│   ├── log_reader.py                     # the daemon-log reader behind /daemon/logs
│   ├── diagnostics.py                    # the three records, joined, behind coffer__diagnose
│   ├── binary_deploy.py                  # frozen-build sibling deploy into ~/.coffer/bin
│   ├── credential_migration.py           # legacy keychain → encrypted store
│   ├── repos.py                          # Protocol classes used by services
│   └── mcp/
│       ├── gateway.py                    # MCPGatewaySession entry + lifecycle
│       ├── gateway_handlers.py           # JSON-RPC method dispatch helpers
│       ├── gateway_parsing.py            # request parsing / envelope
│       ├── gateway_aggregate_lists.py    # tools/resources/prompts list aggregation
│       ├── gateway_scope.py              # the per-session scope filter (FR-020/FR-021)
│       ├── gateway_builtin.py            # Coffer's own builtin tools + search_tools
│       ├── gateway_tool_search.py        # the catalogue search behind search_tools
│       ├── gateway_tiering.py / tiering_config.py  # budget-driven tool tiering
│       ├── gateway_instructions.py       # the initialize-time instructions
│       ├── gateway_notifications.py      # list-changed fan-out
│       ├── gateway_recovery.py           # upstream crash recovery
│       ├── gateway_server_requests.py    # upstream→downstream relay (roots/sampling)
│       ├── kind.py                       # make_mcp_kind() → frozen Kind
│       ├── supervisor.py                 # subprocess lifecycle
│       ├── discovery.py                  # live capability discovery + cache
│       ├── runner_detect.py              # missing-launcher detection (FR-019)
│       ├── sync_state.py                 # what a converge round reads/writes for this kind
│       └── ports.py                      # the kind's application-layer ports
├── infrastructure/
│   ├── persistence/
│   │   ├── base.py                       # SQLAlchemy DeclarativeBase + metadata
│   │   ├── models.py                     # Resource / AuditLog / RetentionPolicy / Credential / …
│   │   ├── repos.py                      # SqlAlchemy*Repo concrete impls
│   │   ├── retention_repo.py             # PrunableTable + the prune SQL
│   │   ├── engine.py                     # async_engine + PRAGMA setup
│   │   └── migrations/                   # alembic.ini, env.py, versions/ (one file per revision)
│   ├── credentials/
│   │   ├── encrypted_store.py            # Fernet ciphertext in the `credentials` table
│   │   ├── master_key.py                 # file-default / keychain-opt-in key resolution
│   │   └── keyring_adapter.py            # ONLY file importing `keyring`
│   ├── daemon/
│   │   ├── pid_lock.py                   # daemon.json + flock
│   │   ├── config.py                     # daemon-config.json — read BEFORE the DB opens
│   │   ├── port_alloc.py                 # bind the fixed port; the range scan is test-only
│   │   ├── spawn.py / child_process.py   # detached spawn, child supervision
│   │   ├── atomic_write.py               # the temp-then-rename primitive
│   │   ├── version_skew.py               # CLI/shim vs daemon build comparison
│   │   ├── orphan_sweep.py               # ~/.coffer/upstream-pids/ scan
│   │   ├── bootstrap.py                  # detect-or-spawn helper
│   │   └── entry.py                      # daemon process entrypoint (uvicorn)
│   ├── logging/
│   │   ├── setup.py                      # structlog config; trace_id contextvar
│   │   └── files.py                      # the log file the Daemon tab reads
│   ├── net/
│   │   └── ssrf_guard.py                 # outbound guard for user-configured HTTP upstreams
│   └── mcp/
│       ├── subprocess.py                 # asyncio Popen wrapping for stdio MCP
│       ├── http_client.py                # httpx + SSE for HTTP MCP
│       ├── factory.py / dispatch.py      # upstream client construction + call dispatch
│       ├── persistence.py                # MCPCapabilityPreferenceModel + repo
│       ├── invocation_writer.py          # MCPInvocationModel + the write path
│       └── health_repo.py                # McpServerHealthModel + repo
├── surfaces/
│   ├── http/
│   │   ├── app.py                        # FastAPI composition root
│   │   ├── routing.py                    # every router, mounted in one place
│   │   ├── kind_wiring.py                # per-kind wiring, in dependency order
│   │   ├── auth.py                       # X-Coffer-Token dependency
│   │   ├── host_guard.py                 # the loopback Host check (FR-027)
│   │   ├── webui.py                      # serves frontend/dist + injects the token (FR-024/FR-025)
│   │   ├── cors.py                       # CORS allowlist
│   │   ├── errors.py                     # exception handler → ErrorResponse envelope
│   │   ├── schemas.py                    # Pydantic API models (match openapi.yaml)
│   │   ├── dependencies.py               # FastAPI dependency wiring (services, repos)
│   │   ├── migrations_runner.py          # alembic upgrade + the pre-upgrade DB copy
│   │   ├── background_workers.py         # retention + the other timed passes
│   │   ├── resource_routes.py            # /api/v1/resources/* (kind-agnostic, incl. /scope)
│   │   ├── audit_routes.py               # /api/v1/audit
│   │   ├── retention_routes.py           # /api/v1/retention/*
│   │   ├── daemon_routes.py              # /api/v1/daemon/* (status, logs, rotate-token, shutdown)
│   │   ├── settings_routes.py            # /api/v1/settings/* (credential storage mode)
│   │   ├── upkeep_routes.py              # /api/v1/upkeep/* — the timed passes' switches
│   │   ├── credential_routes.py          # /api/v1/credentials/*
│   │   ├── fs_routes.py                  # /api/v1/fs/* (owned by spec agent-registry)
│   │   └── mcp/
│   │       ├── capability_routes.py      # capability list / enable / disable / refresh
│   │       ├── capability_views.py       # the view models behind them
│   │       ├── server_test_routes.py     # POST /{name}/test
│   │       ├── invocation_routes.py      # invocation log query
│   │       └── protocol_routes.py        # /mcp endpoint (JSON-RPC over HTTP/SSE)
│   ├── cli/
│   │   ├── main.py                       # Typer composition root
│   │   ├── _client.py                    # HTTP client wrapper (reads daemon.json, attaches token)
│   │   ├── _options.py                   # shared Typer option/exit-code helpers
│   │   ├── _mcp_caps.py                  # mcp capability rendering helpers
│   │   ├── daemon_cmd.py                 # coffer daemon ...
│   │   ├── daemon_port_cmd.py            # coffer daemon port get|set — works with no daemon
│   │   ├── open_cmd.py                   # coffer open
│   │   ├── resource_cmd.py               # coffer resource ...
│   │   ├── scope_cmd.py                  # coffer scope ... (kind-agnostic reach)
│   │   ├── audit_cmd.py                  # coffer audit ...
│   │   ├── retention_cmd.py              # coffer retention ...
│   │   ├── credentials_cmd.py            # coffer credentials set/get/list/delete/storage ...
│   │   └── mcp.py                        # coffer mcp ... (kind subcommand group)
│   └── shim/
│       ├── main.py                       # coffer-mcp-shim entry
│       └── bootstrap.py                  # detect-or-spawn from the shim's side
```

**Structure decision**: layer-first with kind subdirs ([Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)). Existing
`backend/coffer/{domain,application,infrastructure,surfaces}/__init__.py`
files stay; this spec fills them in.

## Layers and boundaries

What sits where, and what each layer is allowed to know. The order below is a
dependency order, not a schedule.

**The kind-agnostic core.** `Resource`, `Kind`, `ResourceService`,
`AuditService`, and the retention trio (`PrunableRegistry`,
`RetentionService`, `RetentionWorker`) know nothing about any kind. They are
exercised against a `fake_kind` registered only for tests, which is what keeps
them honest: a core that needed `mcp_server` to be testable would already have
leaked. Their surfaces — `/api/v1/resources/*` (including `/scope`),
`/api/v1/audit`, `/api/v1/retention/*`, `/api/v1/daemon/*` — and their Typer
groups are kind-agnostic in the same way, and the UI components over them
render any kind.

**The `mcp_server` kind.** `make_mcp_kind()` returns one frozen `Kind`; the
gateway session, subprocess supervisor, capability discovery, the `/mcp`
JSON-RPC endpoint, the `coffer-mcp-shim` binary and `coffer mcp …` hang off it.
Per-capability enable/disable lives here too, because it is the same code path
as listing. The importlinter cross-kind fence forbids this package from
importing another kind's, and forbids the core from importing it.

**Credentials.** `POST`/`GET`/`DELETE /api/v1/credentials` plus the encrypted
store are a shared mechanism rather than the MCP kind's property, but they ship
with this spec because an HTTP upstream cannot reference a credential that has
nowhere to live. `infrastructure/credentials/keyring_adapter.py` is the only
module that may import `keyring`, and the CLI may not reach the keychain at all
— both are contracts, not conventions.

**The daemon itself.** The port is read before the database opens, from a file
(`daemon-config.json`), because nothing database-backed can be consulted that
early. `pid_lock` publishes `daemon.json` only once the socket is bound, so a
published token never names a port the daemon does not hold. The loopback
`Host` guard and the token injection into the served `index.html` are two
halves of one decision and are tested together.

**The surfaces are parity surfaces.** REST and CLI answer through the same
services, and the CLI's `--json`, `--verbose` tracebacks and per-error-class
exit codes exist so a script can depend on it. That parity is asserted by the
`command line covers every visual operation` scenario rather than left to
habit.

**Hardening that is part of the design, not a follow-up.** The orphan sweep on
startup, graceful-shutdown signal handling, the upstream health state machine
and bounded log rotation each answer an Edge Case in [spec.md](./spec.md), and
each Edge Case has a covering integration or e2e test.

## Complexity Tracking

| Decision                                                                                                      | Why needed                                                                                                                             | Simpler alternative rejected because                                                                                                             |
| ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Resource framework before second kind ([Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md)) | Schema, audit, retention, and surface routing all share the kind-agnostic pattern; extracting later would force re-modelling all four. | "Build MCP-specific now, generalise later" multiplies the refactor cost across four subsystems instead of designing them once.                   |
| Both stdio shim AND HTTP `/mcp` endpoint                                                                      | The MCP client ecosystem is split — popular clients ship stdio-only config, newer ones prefer HTTP.                                    | Stdio-only would lose remote MCP servers and the daemon's HTTP-native shape; HTTP-only would lose stdio-only clients. |
| Per-session subprocess set ([Session Subprocess Model](../../docs/decisions/session-subprocess-model.md))              | MCP `initialize` and `capabilities` are per-session; one upstream cannot serve two clients with different declared capabilities.       | Shared subprocess + multiplexing layer would re-implement session semantics at the gateway, ~3× the engineering.                                 |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Research: [research.md](./research.md)
- Data model: [data-model.md](./data-model.md)
- Wire contract: [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)
- Quickstart: [quickstart.md](./quickstart.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Decision records: [`docs/decisions/`](../../docs/decisions/)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
