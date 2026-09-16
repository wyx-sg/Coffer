# Implementation Plan: Resource Framework

**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

The kind-agnostic core every other spec is built on: one `Resource` row shape
with a `<kind>:<name>` identity, a `Kind` descriptor each kind contributes, one
lifecycle service that validates / persists / audits / reacts, one per-agent
reach with one pair of routes serving every kind, one audit log, one retention
registry with a background prune, and one cross-kind read of the passes in
flight — behind a REST surface and a `coffer` surface that answer through the
same services.

Everything here is shipped. It was implemented alongside the first kind (spec
mcp-gateway) and carried in that spec's documents ever since; what was missing
was a spec naming the framework as its subject. See
[Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md)
for why it was built before the second kind needed it, and
[Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md)
for how far that generalisation was taken.

## Technical Context

| Dimension                | Value                                                                                                                             |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**   | Python 3.12+, TypeScript 5.x (frontend + e2e)                                                                                     |
| **Primary Dependencies** | SQLAlchemy 2 + aiosqlite + Alembic, Pydantic v2, Typer + Rich, FastAPI, structlog                                                 |
| **Storage**              | SQLite at `~/.coffer/coffer.db`, WAL mode, daemon as single writer                                                                |
| **Testing**              | Coffer's 4-tier model: unit / integration / contract / e2e. The core is exercised against a `fake_kind` registered only for tests |
| **Project Type**         | Library-in-a-daemon: services plus HTTP routers plus Typer groups, mounted by spec daemon's process                               |
| **Constraints**          | Local-first (127.0.0.1 only); layered architecture (importlinter contracts 1–4 and 6); file size ≤ 400 LOC (backend)              |
| **Scale / Scope**        | Single user; tens of resources per kind; log tables in the low hundreds of thousands of rows before retention bites               |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                               |
| ----------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | OK         | All surfaces bind `127.0.0.1`; SQLite is the system of record; no cloud call is made from any module here.                           |
| **II. Spec-as-Truth**                     | OK         | Every acceptance scenario is owned by at least one test, audited by `make verify-acceptance`.                                        |
| **III. Open-Source-Readiness**            | OK         | No closed-source dependency; nothing here is company-specific.                                                                       |
| **Architecture: layered**                 | OK         | Contract 6 is this spec's own: the kind-agnostic core imports no kind.                                                               |
| **Persistence: SQLite for control plane** | OK         | Three tables, no file-backed content. Kinds that own files own them themselves.                                                      |
| **Credentials: encrypted store**          | OK         | The framework probes and releases credential **refs**; the store and its key are spec credentials'.                                  |
| **Cross-cutting extracted after the second feature** | OK | Explicitly evaluated and judged not to apply: the framework is core domain rather than cross-cutting infrastructure — see the Decision § in [Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md). |

## Project Structure

### Documentation (this feature)

```text
specs/resource-framework/
├── spec.md              # user-visible contract
├── plan.md              # this file
├── data-model.md        # entities + SQL schema
├── contracts/
│   └── api.openapi.yaml # the kind-agnostic management REST contract
└── quickstart.md        # how the feature is used
```

### Source code

```text
backend/coffer/
├── domain/
│   ├── resource.py                   # Resource, ResourceRef, Kind
│   ├── scope.py                      # Scope — the per-agent allow-list
│   ├── audit.py                      # AuditEntry, AuditEventType
│   ├── retention.py                  # RetentionPolicy
│   └── errors.py / error_base.py     # the CofferError hierarchy the surfaces map
├── application/
│   ├── resource_service.py           # kind-agnostic CRUD; takes the Kind dict
│   ├── resource_scope_ops.py         # the reach write path (validate → persist → react)
│   ├── resource_delete_ops.py        # the delete path, incl. credential release
│   ├── audit_service.py              # AuditService
│   ├── retention_registry.py         # PrunableRegistry + PrunableTable
│   ├── retention_service.py          # registry-driven prune
│   ├── retention_worker.py           # the background asyncio pass
│   ├── upkeep_runs.py                # the in-process registry of passes in flight
│   └── repos.py                      # Protocol classes the services depend on
├── infrastructure/persistence/
│   ├── base.py                       # SQLAlchemy DeclarativeBase + metadata
│   ├── models.py                     # Resource / AuditLog / RetentionPolicy
│   ├── repos.py                      # SqlAlchemy*Repo concrete impls
│   ├── retention_repo.py             # the prune SQL + its allowlists
│   ├── engine.py                     # async_engine + PRAGMA setup
│   └── migrations/                   # alembic.ini, env.py, versions/
└── surfaces/
    ├── http/
    │   ├── resource_routes.py        # /api/v1/resources/* (incl. /scope)
    │   ├── audit_routes.py           # /api/v1/audit
    │   ├── retention_routes.py       # /api/v1/retention/*
    │   ├── upkeep_routes.py          # /api/v1/upkeep/runs
    │   ├── kind_wiring.py            # per-kind wiring, in dependency order
    │   ├── background_workers.py     # retention + the other timed passes
    │   └── errors.py                 # exception handler → ErrorResponse envelope
    └── cli/
        ├── resource_cmd.py           # coffer resource ...
        ├── scope_cmd.py              # coffer scope ...
        ├── audit_cmd.py              # coffer audit ...
        └── retention_cmd.py          # coffer retention ...
```

**Structure decision**: layer-first with kind subdirs
([Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)).
Everything above sits at each layer's root — a module at the root of a layer is
kind-agnostic by construction, and contract 6 keeps it that way.

## Layers and boundaries

**The core knows no kind.** `Resource`, `Kind`, `ResourceService`,
`AuditService` and the retention trio (`PrunableRegistry`, `RetentionService`,
`RetentionWorker`) are exercised against a `fake_kind` registered only for
tests, which is what keeps them honest: a core that needed `mcp_server` to be
testable would already have leaked. Their surfaces and Typer groups are
kind-agnostic in the same way, and the UI components over them render any kind.

**A kind plugs in through one frozen descriptor.** Pre-write validators may
reject; post-write reactions may not. That asymmetry is the whole plug-in
contract: validation decides whether a change happens, reactions catch up with
one that already did, and a reaction that raises must not be able to undo a
persisted, audited change.

**Creation is the one operation the framework does not generalise.** A kind
that owns a creation invariant beyond config validation sets
`generic_create_allowed = False` and registers through its own surface. The
framework therefore has no `coffer resource create`, and a caller that wants
one is asking the wrong layer — the kind's own CLI is where the invariant can
be held. Everything after creation is generic.

**Reach is written here and enforced there.** The value, its validation and its
write path are the framework's; the gate is each kind's, at the choke point
where the asking identity is known. One central gate would have to be reachable
from every kind's read path, and every kind's read path already runs downstream
of its own.

**The daemon is assumed, not built.** The process, its port, its token, its
`Host` guard and its startup sequence are spec daemon's. This spec contributes
routers, Typer groups, a startup seed and a background worker to it.

**The surfaces are parity surfaces.** REST and CLI answer through the same
services, and the CLI's `--json`, `--verbose` tracebacks and per-error-class
exit codes exist so a script can depend on it. That parity is asserted by the
`command line covers every visual operation` scenario rather than left to
habit — and the assertion covers every spec's commands, not only this one's,
which is why the scenario lives here.

## Complexity Tracking

| Decision                                                              | Why needed                                                                                                                            | Simpler alternative rejected because                                                                                            |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| A framework before the second kind ([Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md)) | Schema validation, audit, retention and surface routing all share the kind-agnostic pattern; extracting later would force re-modelling all four. | "Build MCP-specific now, generalise later" multiplies the refactor cost across four subsystems instead of designing them once.    |
| Two ops modules beside `resource_service.py`                          | The service would otherwise exceed the 400-LOC file ceiling.                                                                          | One large module hides the two paths with the most branching (reach and delete) inside the file least likely to be read closely. |
| An in-process upkeep registry with no persistence                     | A pass belongs to the process running it; a claim that outlived its runner would wedge a target forever.                              | A table with a lease needs an expiry, a reaper and a story for clock skew, to record something no one needs after a restart.      |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Data model: [data-model.md](./data-model.md)
- Wire contract: [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)
- Quickstart: [quickstart.md](./quickstart.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Decision records: [`docs/decisions/`](../../docs/decisions/)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
