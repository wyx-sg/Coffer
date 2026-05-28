# Implementation Plan: 001 — MCP Gateway

**Branch**: `feature/mcp-gateway`
**Date**: 2026-05-20
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

> For agentic workers: Use `superpowers:subagent-driven-development` (recommended)
> or `superpowers:executing-plans` to implement [tasks.md](./tasks.md)
> task-by-task. Each task uses checkbox (`- [ ]`) syntax for tracking.

## Summary

Build the coffer MCP gateway: a local daemon that aggregates upstream MCP
servers and re-exposes their tools, resources, and prompts to one or more MCP
clients (Claude Desktop / Cursor / Claude Code) through a namespaced surface.
Ships together with a CLI, a desktop UI, a stdio shim, and a single-bundle
installer.

The implementation also lays in the kind-agnostic Resource framework — the
first concrete kind is `mcp_server`; later specs add more.

See [./spec.md](./spec.md) for the user-visible contract and the seven
[ADRs](../../docs/decisions/) for architectural rationale.

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x, Rust stable (Tauri shell only)                                                                                                                                                             |
| **Primary Dependencies** (added by this spec) | SQLAlchemy 2 + aiosqlite + Alembic, Typer + Rich, structlog, keyring, httpx, `mcp` SDK (official), psutil. Frontend: TanStack Query, React Router 6, i18next, react-hook-form + zod, openapi-typescript + openapi-fetch. |
| **Storage**                                   | SQLite at `~/.coffer/coffer.db`, WAL mode, daemon as single writer                                                                                                                                                       |
| **Testing**                                   | Coffer's 4-tier model: unit / integration / contract / e2e. `pytest` + `vitest` + `Playwright`. Acceptance markers tie tests to scenarios in [spec.md](./spec.md).                                                       |
| **Target Platforms**                          | macOS arm64+x64 (universal), Windows x64, Linux x64+arm64                                                                                                                                                                |
| **Project Type**                              | Desktop app + CLI + daemon (multi-process local-first)                                                                                                                                                                   |
| **Performance Goals**                         | Per [spec.md](./spec.md) SC-003: ≤ 50 ms gateway overhead per tool call (median, 100-call sample). Daemon ready in ≤ 5 s from cold start.                                                                                |
| **Constraints**                               | Local-first (127.0.0.1 only); credentials in OS keychain only; layered architecture (importlinter contracts 1–6); file size ≤ 400 LOC backend / 250 frontend component.                                                  |
| **Scale / Scope**                             | Single user; ≤ 3 concurrent MCP clients; ≤ 30 registered MCP servers; ≤ 100 capabilities per server.                                                                                                                     |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                                                     |
| ----------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | ✅         | All HTTP surfaces bind `127.0.0.1`. No cloud calls. SQLite is the only system-of-record.                                                                                  |
| **II. Spec-as-Truth**                     | ✅         | This plan implements [spec.md](./spec.md); spec was committed before code. Every acceptance scenario is owned by at least one test (audited by `make verify-acceptance`). |
| **III. Open-Source-Readiness**            | ✅         | Repo already has MIT licence, CONTRIBUTING.md, Conventional Commits, dependabot. No closed-source dependencies added.                                                     |
| **Languages**                             | ✅         | Python 3.12 + TS 5 only. The Rust used is the Tauri shell (already constitutional per `agents/stack.md`).                                                                 |
| **Architecture: layered**                 | ✅         | importlinter contracts 1–4 already in `backend/pyproject.toml`; this plan adds contracts 5–6 (cross-kind isolation, kind-agnostic core boundary).                         |
| **Persistence: SQLite for control plane** | ✅         | All state in `coffer.db`. No file-backed user content in this spec (no `Memory` kind yet).                                                                                |
| **Credentials: keychain only**            | ✅         | `infrastructure/credentials/keyring_adapter.py` is the sole `keyring` importer. Resource configs hold only credential **refs** (string keys).                             |
| **Network defaults: loopback-only**       | ✅         | FastAPI binds `127.0.0.1`. CORS allowlist closes browser-CSRF surface. No outbound public-internet calls in v0 except to user-configured upstream HTTP MCP servers.       |

**Resource framework upfront** (ADR-001) was evaluated against the constitution's
"Cross-cutting modules are extracted only after the second feature needs them"
rule and judged not to apply, because the framework is **core domain**, not
cross-cutting infrastructure. See [ADR-001 Decision § rationale].

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-gateway/
├── spec.md              # user-visible contract (committed)
├── plan.md              # this file
├── research.md          # library + protocol choices
├── data-model.md        # entities + SQL schema
├── contracts/
│   └── api.openapi.yaml # management REST contract
├── quickstart.md        # how the feature is used once shipped
├── tasks.md             # bite-sized work breakdown (TDD)
└── checklists/          # generated by /speckit-checklist (later)
```

### Source code (delivered in this PR)

```text
backend/coffer/
├── domain/
│   ├── resource.py                       # Resource, ResourceRef, Kind
│   ├── audit.py                          # AuditEntry, AuditEventType
│   ├── retention.py                      # RetentionPolicy
│   ├── errors.py                         # CofferError hierarchy
│   ├── kind_module.py                    # KindModule frozen dataclass (composition root data)
│   └── mcp/
│       ├── server_config.py              # MCPServerConfig + transports
│       ├── capability.py                 # MCPTool/Resource/Prompt + Preference + Invocation
│       └── namespace.py                  # prefix_tool / parse_prefixed_tool / URI helpers
├── application/
│   ├── resource_service.py               # kind-agnostic CRUD; takes Kind dict
│   ├── audit_service.py                  # AuditService
│   ├── retention_service.py              # PrunableRegistry-driven prune
│   ├── retention_worker.py               # background asyncio task
│   ├── repos.py                          # Protocol classes used by services
│   └── mcp/
│       ├── gateway.py                    # MCPGatewaySession entry + lifecycle
│       ├── gateway_handlers.py           # JSON-RPC method dispatch helpers
│       ├── gateway_aggregate_lists.py    # tools/resources/prompts list aggregation
│       ├── gateway_server_requests.py    # upstream→downstream request relay (roots/sampling)
│       ├── kind.py                       # MCP_KIND module (KindModule wiring)
│       ├── supervisor.py                 # subprocess lifecycle
│       ├── discovery.py                  # live capability discovery + cache
│       └── credential_resolver.py        # materialise credential refs at spawn
├── infrastructure/
│   ├── persistence/
│   │   ├── base.py                       # SQLAlchemy DeclarativeBase + metadata
│   │   ├── models.py                     # ResourceModel, AuditLogModel, RetentionPolicyModel
│   │   ├── repos.py                      # SqlAlchemy*Repo concrete impls
│   │   ├── engine.py                     # async_engine + PRAGMA setup
│   │   ├── retention.py                  # PrunableTable + PrunableRegistry
│   │   └── migrations/
│   │       ├── env.py
│   │       ├── alembic.ini
│   │       └── versions/
│   │           ├── 20260520_0001_initial.py
│   │           ├── 20260521_0002_mcp_tables.py
│   │           └── 20260522_0003_mcp_server_health.py
│   ├── credentials/
│   │   └── keyring_adapter.py            # ONLY file importing `keyring`
│   ├── daemon/
│   │   ├── pid_lock.py                   # daemon.json + flock
│   │   ├── port_alloc.py                 # 8000..8009 fallback
│   │   ├── orphan_sweep.py               # ~/.coffer/upstream-pids/ scan
│   │   ├── bootstrap.py                  # detect-or-spawn helper
│   │   └── entry.py                      # daemon process entrypoint (uvicorn)
│   ├── logging/
│   │   └── setup.py                      # structlog config; trace_id contextvar
│   └── mcp/
│       ├── subprocess.py                 # asyncio Popen wrapping for stdio MCP
│       ├── http_client.py                # httpx + SSE for HTTP MCP
│       └── persistence.py                # MCPCapabilityPreferenceModel + MCPInvocationModel + repos
├── surfaces/
│   ├── http/
│   │   ├── app.py                        # FastAPI composition root
│   │   ├── auth.py                       # X-Coffer-Token dependency
│   │   ├── cors.py                       # CORS allowlist
│   │   ├── errors.py                     # exception handler → ErrorResponse envelope
│   │   ├── schemas.py                    # Pydantic API models (match openapi.yaml)
│   │   ├── dependencies.py               # FastAPI dependency wiring (services, repos)
│   │   ├── resource_routes.py            # /api/v1/resources/* (kind-agnostic)
│   │   ├── audit_routes.py               # /api/v1/audit
│   │   ├── retention_routes.py           # /api/v1/retention/*
│   │   ├── daemon_routes.py              # /api/v1/daemon/*
│   │   ├── keychain_routes.py            # /api/v1/keychain/* (write + delete only)
│   │   └── mcp/
│   │       ├── capability_routes.py      # capability list / enable / disable / refresh / test
│   │       ├── invocation_routes.py      # invocation log query
│   │       └── protocol_routes.py        # /mcp endpoint (JSON-RPC over HTTP/SSE)
│   ├── cli/
│   │   ├── main.py                       # Typer composition root
│   │   ├── _client.py                    # HTTP client wrapper (reads daemon.json, attaches token)
│   │   ├── _options.py                   # shared Typer option/exit-code helpers
│   │   ├── _mcp_caps.py                  # mcp capability rendering helpers
│   │   ├── daemon_cmd.py                 # coffer daemon ...
│   │   ├── resource_cmd.py               # coffer resource ...
│   │   ├── audit_cmd.py                  # coffer audit ...
│   │   ├── retention_cmd.py              # coffer retention ...
│   │   ├── keychain_cmd.py               # coffer keychain set/delete ...
│   │   └── mcp.py                        # coffer mcp ... (kind subcommand group)
│   └── shim/
│       └── main.py                       # coffer-mcp-shim entry

backend/
├── coffer-daemon.spec                    # PyInstaller daemon entry (see ADR-007)
└── coffer-mcp-shim.spec                  # PyInstaller shim entry  (see ADR-007)

# Distribution
Makefile  bundle-binaries                 # invokes scripts/build_binaries.sh
```

### Future (planned in the UI spec — to be drafted as `002-ui-shell` in a follow-up PR)

The desktop UI and stdio-shim-on-PATH installer are NOT delivered by this PR.
They are listed here for forward visibility only.

```text
frontend/src/                              # React + Vite desktop UI (planned)
├── lib/{api,i18n,auth,store,components}/
├── kinds/mcp/{pages,components,routes}
├── locales/{en,zh}/
├── pages/{ResourcesPage,AuditPage,settings/*}
└── App.tsx

desktop/                                   # Tauri 2 shell (planned)
├── src/{main,lib,daemon_supervisor,tray,window}.rs
├── tauri.conf.json                        # sidecar wiring for daemon + shim
└── icons/

scripts/
├── build_binaries.sh                      # delivered (driver for bundle-binaries)
└── smoke_test_bundle.sh                   # planned (post-build matrix smoke test)
.github/workflows/
└── release.yml                            # planned (matrix build for distributable)
```

**Structure decision**: layer-first with kind subdirs ([ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)). Existing
`backend/coffer/{domain,application,infrastructure,surfaces}/__init__.py`
files stay; this spec fills them in.

## Phases (high-level)

Phases are **delivery boundaries**; granular tasks live in [tasks.md](./tasks.md).

### Phase 1 — Setup (shared infrastructure)

Add runtime dependencies, importlinter contracts 5–6, structlog setup,
SQLAlchemy + Alembic skeleton, the Pydantic schemas matching
`contracts/api.openapi.yaml`, error envelope, FastAPI composition-root scaffold,
Typer composition-root scaffold. No business logic yet; CI green on placeholders.

**Done when:** `make verify` passes; the daemon can boot, expose
`GET /api/v1/daemon/status`, return `status: "starting"` then `"ready"`.

### Phase 2 — Foundational (kind-agnostic core)

Implements the Resource framework (`Resource`, `Kind`, `KindModule`,
`ResourceService`, `AuditService`), the retention framework
(`PrunableRegistry`, `RetentionService`, `RetentionWorker`), and the
`/api/v1/resources/*`, `/api/v1/audit`, `/api/v1/retention/*`,
`/api/v1/daemon/*` routes + their Typer subcommand groups + their generic UI
components.

**Done when:** kind-agnostic surfaces work against a `fake_kind` registered
for tests, with full CRUD + audit + retention test coverage.

### Phase 3 — MVP: US1 + US2 (aggregate + curate)

Register the `mcp_server` kind. Implement `MCPGatewaySession`,
`SubprocessSupervisor`, `CapabilityDiscovery`, the `/mcp` JSON-RPC endpoint,
the `coffer-mcp-shim` binary, and the `coffer mcp …` CLI subcommands. Per-tool
enable/disable lands here too (US2 is a P1 in the spec; both user stories
share the same code paths so we implement them together). The keychain
write/delete management endpoints (FR-011) land in this phase as well, so
HTTP MCP servers can reference credentials end-to-end.

**Done when:** Acceptance scenarios from User Story 1 and User Story 2 pass
under `make verify` and `make verify-e2e` (the `e2e/mcp/` subprocess-driven
suite).

**MVP gate:** After Phase 3, the feature is shippable to early users via
`pip install -e ./backend` (and via the PyInstaller binaries, see Phase 6),
even though there is no desktop UI yet. This is the deliberate MVP cut.

### Phase 4 — US4: Observability (audit + invocations + retention CLIs)

The audit log, invocation log, and retention framework all land in Phase 2 as
kind-agnostic plumbing; Phase 4 finishes their CLI surface (`coffer audit …`,
`coffer mcp invocations …`, `coffer retention …`) and verifies retention
prune doesn't block live API calls.

**Done when:** Acceptance scenarios for User Story 4 pass (`audit lifecycle
changes`, `invocation log records calls without arguments`, `configure
retention per log`, `daemon backup produces a portable SQLite copy`).

### Phase 5 — US3: CLI completeness (parity with REST)

Many CLI subcommands already land in Phase 2 (`resource`, `daemon`, `keychain`)
and Phase 3 (`mcp`). Phase 5 fills in gaps from those two phases — typically
`--json` output flags, `--verbose` traceback rendering, and the per-error-class
exit codes that scripts depend on.

**Done when:** Acceptance scenarios for User Story 3 pass (`command line
covers every visual operation`, `command line surfaces same errors`, `CLI
returns non-zero exit on daemon unreachable`, `CLI --json output is
machine-readable`).

### Phase 6 — Distribution (PyInstaller daemon + shim)

PyInstaller specs for daemon + shim (`backend/coffer-daemon.spec`,
`backend/coffer-mcp-shim.spec`); the `make bundle-binaries` driver
(`scripts/build_binaries.sh`). The single-bundle desktop installer (Tauri
sidecar wiring, GitHub Actions release matrix, post-build smoke test) is
deferred to the planned UI spec (to be drafted as `002-ui-shell` in a
follow-up PR) because Tauri sidecar configuration is itself part of that
spec.

**Done when:** `make bundle-binaries` produces working `coffer-daemon` +
`coffer-mcp-shim` binaries on the host platform, and both reach `status:
ready` against a clean `~/.coffer/`. The cross-platform release matrix is
the responsibility of the planned UI spec.

### Phase 7 — Hardening

Subprocess orphan sweep on startup; daemon graceful-shutdown signal handling;
upstream health state machine; bounded log rotation; concurrent-client load
smoke. Anything from [spec.md](./spec.md) Edge Cases not yet covered.

**Done when:** Every Edge Case in [spec.md](./spec.md) has a covering
integration or e2e test.

_(Tray / launch-at-login / observability UI / i18n are deferred to the
planned UI spec (to be drafted as `002-ui-shell` in a follow-up PR).)_

## Complexity Tracking

| Decision                                                                                                      | Why needed                                                                                                                             | Simpler alternative rejected because                                                                                                             |
| ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Resource framework before second kind ([ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)) | Schema, audit, retention, and surface routing all share the kind-agnostic pattern; extracting later would force re-modelling all four. | "Build MCP-specific now, generalise later" multiplies the refactor cost across four subsystems instead of designing them once.                   |
| Both stdio shim AND HTTP `/mcp` endpoint                                                                      | The MCP client ecosystem is split — popular clients ship stdio-only config, newer ones prefer HTTP.                                    | Stdio-only would lose remote MCP servers and the daemon's HTTP-native shape; HTTP-only would lose Claude Desktop and similar stdio-only clients. |
| Per-session subprocess set ([ADR-005](../../docs/decisions/ADR-005-session-subprocess-model.md))              | MCP `initialize` and `capabilities` are per-session; one upstream cannot serve two clients with different declared capabilities.       | Shared subprocess + multiplexing layer would re-implement session semantics at the gateway, ~3× the engineering.                                 |
| PyInstaller bundling ([ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md))      | The spec promises "install one bundle, it just works"; requiring system Python excludes most target users.                             | "Require Python 3.12" violates SC-009 and excludes most non-Python developer audiences.                                                          |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Research: [research.md](./research.md)
- Data model: [data-model.md](./data-model.md)
- Wire contract: [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)
- Quickstart: [quickstart.md](./quickstart.md)
- Tasks: [tasks.md](./tasks.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Decision records: [`docs/decisions/`](../../docs/decisions/)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
