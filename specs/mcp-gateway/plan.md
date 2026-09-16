# Implementation Plan: MCP Gateway

**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

Build the coffer MCP gateway: a local daemon that aggregates upstream MCP
servers and re-exposes their tools, resources, and prompts to one or more MCP
clients (Claude Code, Codex) through a namespaced surface.
Ships together with a CLI and a stdio shim. The daemon that hosts it is
spec daemon's; the encrypted store its HTTP upstreams reference is spec
credentials'.

`mcp_server` is the first kind of spec
[resource-framework](../resource-framework/spec.md), which this spec is
implemented on top of and does not own: the kind-agnostic lifecycle, reach,
audit and retention all belong there, and this spec contributes one `Kind`
descriptor plus everything MCP-specific above it.

See [./spec.md](./spec.md) for the user-visible contract and the
[ADRs](../../docs/decisions/) for architectural rationale.

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x (e2e)                                                                                                                                                                                       |
| **Primary Dependencies** (added by this spec) | SQLAlchemy 2 + aiosqlite + Alembic, Typer + Rich, structlog, httpx, `mcp` SDK (official), psutil. E2e: Playwright (`@playwright/test`).                                                                          |
| **Storage**                                   | SQLite at `~/.coffer/coffer.db`, WAL mode, daemon as single writer                                                                                                                                                       |
| **Testing**                                   | Coffer's 4-tier model: unit / integration / contract / e2e. `pytest` (backend) + `Playwright` (MCP e2e). Acceptance markers tie tests to scenarios in [spec.md](./spec.md).                                              |
| **Target Platforms**                          | macOS arm64 — the only leg the release builds (spec daemon, distribution). Linux is exercised in CI.                                                                                                                       |
| **Project Type**                              | CLI + daemon + stdio shim (multi-process local-first)                                                                                                                                                                   |
| **Performance Goals**                         | Per [spec.md](./spec.md) SC-003: ≤ 50 ms gateway overhead per tool call (median, 100-call sample). Daemon ready in ≤ 5 s from cold start.                                                                                |
| **Constraints**                               | Local-first (127.0.0.1 only); secrets referenced by ref and never held in this spec's config (spec credentials); layered architecture (the importlinter contracts in `backend/pyproject.toml` — 1–4 are the layering rules every spec lives under, 5 is this kind's cross-kind fence, now written once per kind); file size ≤ 400 LOC (backend).                                                  |
| **Scale / Scope**                             | Single user; ≤ 3 concurrent MCP clients; ≤ 30 registered MCP servers; ≤ 100 capabilities per server.                                                                                                                     |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                                                     |
| ----------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | ✅         | All HTTP surfaces bind `127.0.0.1`. No cloud calls. SQLite is the only system-of-record.                                                                                  |
| **II. Spec-as-Truth**                     | ✅         | This plan implements [spec.md](./spec.md); spec was committed before code. Every acceptance scenario is owned by at least one test (audited by `make verify-acceptance`). |
| **III. Open-Source-Readiness**            | ✅         | Repo already has MIT licence, CONTRIBUTING.md, Conventional Commits, dependabot. No closed-source dependencies added.                                                     |
| **Languages**                             | ✅         | Python 3.12 + TypeScript 5 (e2e) only.                                                                                                                                   |
| **Architecture: layered**                 | ✅         | importlinter contracts 1–4 already in `backend/pyproject.toml`; this plan adds contract 5 (cross-kind isolation for `mcp`). Contract 6, the kind-agnostic core boundary, is spec resource-framework's. |
| **Persistence: SQLite for control plane** | ✅         | This spec's own state is all in `coffer.db`; it introduces no file-backed user content. (Later specs do — the knowledge, memory and skill trees — and they own their own files.) |
| **Credentials: encrypted store**          | ✅         | An `mcp_server` config holds only credential **refs** (string keys); the store behind them, and the master key that opens it, are spec credentials'.                                                                                              |
| **Network defaults: loopback-only**       | ✅         | The daemon binds `127.0.0.1` and guards its origin (spec daemon). This spec makes no outbound public-internet call except to a user-configured upstream HTTP MCP server. |

Building the resource framework before a second kind needed it was evaluated
against the constitution's "cross-cutting modules are extracted only after the
second feature needs them" rule and judged not to apply, because the framework
is **core domain** rather than cross-cutting infrastructure. That argument, and
the framework itself, now live in spec
[resource-framework](../resource-framework/plan.md); the record is
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

The modules this spec owns — the MCP kind and its surfaces. The kind-agnostic
modules they sit on (`domain/{resource,scope,audit,retention}.py`, the services
at the root of `application/`, `surfaces/http/{resource,audit,retention,upkeep}_routes.py`
and their Typer groups) are spec resource-framework's; other kinds' packages
sit beside these and belong to their own specs.

```text
backend/coffer/
├── domain/
│   └── mcp/
│       ├── server_config.py              # MCPServerConfig + transports
│       ├── capability.py                 # MCPTool/Resource/Prompt + Preference + Invocation
│       └── namespace.py                  # prefix_tool / parse_prefixed_tool / URI helpers
├── application/
│   ├── diagnostics.py                    # the three records, joined, behind coffer__diagnose
│   └── mcp/
│       ├── gateway.py                    # MCPGatewaySession entry + lifecycle
│       ├── gateway_handlers.py           # JSON-RPC method dispatch helpers
│       ├── gateway_parsing.py            # request parsing / envelope
│       ├── gateway_aggregate_lists.py    # tools/resources/prompts list aggregation
│       ├── gateway_scope.py              # the per-session scope filter (FR-012/FR-013)
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
│       ├── runner_detect.py              # missing-launcher detection (FR-011)
│       ├── sync_state.py                 # what a converge round reads/writes for this kind
│       └── ports.py                      # the kind's application-layer ports
├── infrastructure/
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
│   │   └── mcp/
│   │       ├── capability_routes.py      # capability list / enable / disable / refresh
│   │       ├── capability_views.py       # the view models behind them
│   │       ├── server_test_routes.py     # POST /{name}/test
│   │       ├── invocation_routes.py      # invocation log query
│   │       └── protocol_routes.py        # /mcp endpoint (JSON-RPC over HTTP/SSE)
│   ├── cli/
│   │   ├── _mcp_caps.py                  # mcp capability rendering helpers
│   │   └── mcp.py                        # coffer mcp ... (kind subcommand group)
│   └── shim/
│       ├── main.py                       # coffer-mcp-shim entry
│       └── bootstrap.py                  # the shim's side of spec daemon's detect-or-spawn
```

**Structure decision**: layer-first with kind subdirs ([Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)). Existing
`backend/coffer/{domain,application,infrastructure,surfaces}/__init__.py`
files stay; this spec fills them in.

## Layers and boundaries

What sits where, and what each layer is allowed to know. The order below is a
dependency order, not a schedule.

**The kind-agnostic core is consumed, not owned.** `Resource`, `Kind`,
`ResourceService`, `AuditService` and the retention trio know nothing about any
kind, and their surfaces — `/api/v1/resources/*` (including `/scope`),
`/api/v1/audit`, `/api/v1/retention/*` — serve every kind alike. They are spec
resource-framework's; this spec registers one kind with them and writes into
their records.

**The `mcp_server` kind.** `make_mcp_kind()` returns one frozen `Kind`; the
gateway session, subprocess supervisor, capability discovery, the `/mcp`
JSON-RPC endpoint, the `coffer-mcp-shim` binary and `coffer mcp …` hang off it.
Per-capability enable/disable lives here too, because it is the same code path
as listing. The importlinter cross-kind fence (contract 5) forbids this package from
importing another kind's, and spec resource-framework's contract 6 forbids the
core from importing it.

**Credentials are consumed, not owned.** An HTTP upstream's `credential_refs`
name entries in spec credentials' encrypted store; this spec persists the refs,
probes them before a write, and resolves them at spawn time. No module of this
spec opens the store's key or imports `keyring`.

**The daemon is assumed, not built.** The process this gateway is mounted in,
its port, its discovery file, its token and its `Host` guard are spec daemon's.
This spec contributes routers and Typer groups to it.

**The surfaces are parity surfaces.** REST and CLI answer through the same
services, and the CLI's `--json`, `--verbose` tracebacks and per-error-class
exit codes exist so a script can depend on it. That parity is asserted across every spec's commands at once by spec
resource-framework's `command line covers every visual operation` scenario,
rather than left to habit here.

**Hardening that is part of the design, not a follow-up.** The orphan sweep on
startup, graceful-shutdown signal handling, the upstream health state machine
and bounded log rotation each answer an Edge Case in [spec.md](./spec.md), and
each Edge Case has a covering integration or e2e test.

## Complexity Tracking

| Decision                                                                                                      | Why needed                                                                                                                             | Simpler alternative rejected because                                                                                                             |
| ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
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
