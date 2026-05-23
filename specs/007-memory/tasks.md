# Tasks — 007 Memory Manager

> Status as of PR #26: all phase 2–10 tasks are delivered on
> `feature/007-memory`. T-0023 and T-0035 (the tracer / observability
> promotion) were absorbed into PR #22 (006-knowledge-base) — by the time
> 007 landed the shared `application/observability/` and
> `infrastructure/observability/` modules already existed, so the tasks
> below are marked obsolete rather than re-done.

## Phase 1 — Spec docs

- [x] T-0001 spec.md, plan.md, research.md, data-model.md, contracts/api.openapi.yaml, quickstart.md
- [x] T-0002 Commit `chore(007-memory): seed spec/plan/research/data-model/contracts/quickstart`

## Phase 2 — Backend domain

- [x] T-0010 `domain/memory/__init__.py`
- [x] T-0011 `domain/memory/config.py` (MemoryStoreConfig)
- [x] T-0012 `domain/memory/record.py` (MemoryRecord)
- [x] T-0013 `domain/memory/store.py` (MemoryStore port + MemoryHit)
- [x] T-0014 Extend `domain/errors.py`: MemoryStoreNotFound, MemoryNotFound, MemoryRejected, LLMNotConfigured

## Phase 3 — Backend application

- [x] T-0020 `application/memory/__init__.py`
- [x] T-0021 `application/memory/service.py` (add/list/get/search/update/delete/clear)
- [x] T-0022 `application/memory/kind.py` (make_memory_kind)
- [x] ~~T-0023 PROMOTE tracer port: move from `application/knowledge_base/tracer.py` to `application/observability/tracer.py`; update KB imports.~~ — **Obsolete.** Delivered in PR #22 (006-knowledge-base); `application/observability/tracer.py` already existed before this spec started its impl phase.

## Phase 4 — Backend infrastructure

- [x] T-0030 `infrastructure/memory/__init__.py`
- [x] T-0031 `infrastructure/memory/paths.py`
- [x] T-0032 `infrastructure/memory/persistence.py` (MemoryRecordModel, MemoryRecordRepo)
- [x] T-0033 `infrastructure/memory/mem0_store.py` (sole importer of `mem0`)
- [x] T-0034 Alembic migration `0008_memory_tables.py` (chained after `0007_knowledge_tables`)
- [x] ~~T-0035 PROMOTE `infrastructure/observability/` from KB-only to shared module.~~ — **Obsolete.** Delivered in PR #22 (006-knowledge-base); `infrastructure/observability/` already shared before this spec started its impl phase.
- [x] T-0036 Update `migrations/env.py` to import memory persistence module

## Phase 5 — Surfaces

- [x] T-0040 `surfaces/http/memory/__init__.py`
- [x] T-0041 `surfaces/http/memory/schemas.py` + `routes.py`
- [x] T-0042 `surfaces/cli/memory_cmd.py`

## Phase 6 — MCP built-in tools (shared file with KB)

- [x] T-0050 Extend `application/mcp/builtin_tools.py` with memory tools.
- [x] T-0051 Integration test: `test_mcp_builtin_memory_tools.py`

## Phase 7 — Composition root + dependencies

- [x] T-0060 Update `pyproject.toml`: add `mem0ai`; new importlinter contract 8.
- [x] T-0061 Update `surfaces/http/app.py` — `_wire_memory_kind(...)`.
- [x] T-0062 Update `surfaces/cli/main.py` — `app.add_typer(memory_cmd.app, name="memory")`.
- [x] T-0063 Update `surfaces/http/dependencies.py` — memory service getter.

## Phase 8 — Frontend

- [x] T-0070 `frontend/src/kinds/memory/schema.ts`
- [x] T-0071 `MemoryStoreForm.tsx`
- [x] T-0072 `MemoryStoreCard.tsx`, `MemoryStoreDetailPage.tsx`
- [x] T-0073 `MemoryList.tsx`, `MemoryRow.tsx`, `SearchBox.tsx`
- [x] T-0074 `frontend/src/kinds/memory/index.tsx` (MEMORY_KIND_UI)
- [x] T-0075 Update `frontend/src/kinds.ts` to register the memory kind UI
- [x] T-0076 Frontend tests

## Phase 9 — Tests

- [x] T-0080 Unit: config / record / service-with-fake-store
- [x] T-0081 Integration: lifecycle / mcp-builtin / http / cli
- [x] T-0082 Contract: OpenAPI conformance

## Phase 10 — Verification

- [x] T-0090 `make verify-acceptance`
- [x] T-0091 `make verify-unit`
- [x] T-0092 `make verify-integration`
- [x] T-0093 `make verify-contract`
- [x] T-0094 `make lint`
- [x] T-0095 Final commit `feat(007-memory): memory kind (spec 007)`

## Phase 11 — STOP

- [x] T-0100 Branch pushed, PR #26 opened.
