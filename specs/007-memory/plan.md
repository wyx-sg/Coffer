# Implementation Plan: 007 — Memory Manager

**Branch**: `feature/007-memory`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Add the `memory` resource kind to Coffer's kind-agnostic framework. Each memory store is a Resource holding configuration (embedding model, LLM provider, max text length). Memories are short derived facts written by either the coding agent (through Coffer's MCP gateway) or the user (UI / CLI), persisted by **mem0** behind a thin `MemoryStore` port. State lives under `~/.coffer/memory/<name>/`.

The agent integration goes through Coffer's existing MCP gateway: four new built-in tools (`coffer__list_memory_stores`, `coffer__add_memory`, `coffer__search_memory`, `coffer__delete_memory`) appear alongside the KB built-in tools and upstream MCP server tools.

This spec lands atop `006-knowledge-base`.

## Technical Context

| Dimension                                     | Value                                                                                                                                                                               |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x                                                                                                                                                        |
| **Primary Dependencies (added by this spec)** | `mem0ai` (memory framework, behind port); LLM provider is **user-configured** — either local Ollama (no Python dep) or OpenAI (lazy `pip install openai` already required by mem0). |
| **Storage**                                   | SQLite at `~/.coffer/coffer.db` for `memory_records` rows; mem0 state under `~/.coffer/memory/<name>/`.                                                                             |
| **Testing**                                   | 4-tier model with acceptance markers. Most paths use `FakeMemoryStore`; one integration test exercises the real mem0 adapter under `pytest.importorskip` with a fake LLM.           |
| **Performance Goals**                         | SC-002: ≤ 500 ms search wall-clock on a 200-memory store.                                                                                                                           |
| **Constraints**                               | mem0 confined to `coffer.infrastructure.memory.*` (importlinter); daemon starts even if mem0 fails to import.                                                                       |
| **Scale / Scope**                             | Single user; ≤ 10 memory stores; ≤ 10 000 memories per store.                                                                                                                       |

## Constitution Check

Identical analysis to 006 (knowledge_base). Layer rules and import-linter contracts extend symmetrically for the new `memory` kind.

## Project Structure

```text
backend/coffer/
├── domain/
│   └── memory/
│       ├── __init__.py
│       ├── config.py                    # MemoryStoreConfig pydantic schema
│       ├── record.py                    # MemoryRecord dataclass
│       └── store.py                     # MemoryStore port + MemoryHit value object
├── application/
│   └── memory/
│       ├── __init__.py
│       ├── kind.py                      # make_memory_kind(...)
│       └── service.py                   # MemoryService: add/list/get/search/edit/delete/clear
├── infrastructure/
│   └── memory/
│       ├── __init__.py
│       ├── mem0_store.py                # ONLY file that imports mem0
│       ├── persistence.py               # MemoryRecordModel, MemoryRecordRepo
│       └── paths.py
└── surfaces/
    ├── http/
    │   └── memory/
    │       ├── __init__.py
    │       ├── routes.py                # /api/v1/memory_stores/*
    │       └── schemas.py
    └── cli/
        └── memory_cmd.py                # `coffer memory ...`
```

Existing files modified (intersection with 005):

- `application/mcp/builtin_tools.py` — add memory tools alongside KB tools.
- `surfaces/http/app.py` — add `_wire_memory_kind(...)`.
- `surfaces/cli/main.py` — `app.add_typer(memory_cmd.app, name="memory")`.
- `infrastructure/persistence/migrations/env.py` — import memory persistence module.
- `backend/pyproject.toml` — new `mem0ai` dep; new importlinter contract 8.
- `frontend/src/kinds.ts` — register `MEMORY_KIND_UI`.

## Frontend

```text
frontend/src/kinds/memory/
├── index.tsx                # MEMORY_KIND_UI
├── MemoryStoreCard.tsx
├── MemoryStoreDetailPage.tsx
├── MemoryStoreForm.tsx
├── MemoryList.tsx
├── MemoryRow.tsx            # edit-in-place
├── SearchBox.tsx
└── schema.ts
```

## Tests

```text
backend/tests/
├── unit/memory/
│   ├── test_config_validation.py
│   ├── test_record_value_objects.py
│   └── test_memory_service_with_fake_store.py
├── integration/memory/
│   ├── test_memory_lifecycle.py
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   ├── test_cli_memory_cmd.py
│   └── test_mem0_store_real.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── MemoryStoreForm.test.tsx
├── MemoryStoreDetailPage.test.tsx
└── MemoryList.test.tsx
```

## Importlinter contracts (added or amended)

- **Extend Contract 5** (cross-kind imports forbidden): add `coffer.{domain,application,infrastructure,surfaces.http}.memory` to source modules; populate `forbidden_modules` per-kind across `mcp`, `knowledge_base`, and `memory`.
- **Extend Contract 6** (kind-agnostic core ↛ kind-specific): add `coffer.{...}.memory` to `forbidden_modules`.
- **New Contract 8** (mem0 engine confinement): `coffer.application.*` and `coffer.domain.*` MUST NOT import `mem0` (any submodule). Only `coffer.infrastructure.memory.mem0_store` may.

## Risks & mitigations

| Risk                                                               | Mitigation                                                                                                                                     |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| mem0's API has churned in 2024                                     | All mem0 types in one file; port expresses our needs, not theirs.                                                                              |
| mem0 requires an LLM at write time — friction for first-time users | UX: clear "configure LLM provider" CTA on first add; read paths work without LLM. Quickstart documents Ollama as the default zero-cost option. |
| mem0 brings transitively heavy deps (OpenAI client, etc.)          | Lock to `mem0ai` core; don't pin extras unless needed. Re-evaluate at lock time.                                                               |

## Out of scope (deferred)

- Memory "consolidation" runs (mem0 has it; we don't expose it yet).
- Cross-store search.
- Memory categories / tags / collections.
- Time-decay scoring.
- Memory export-to-markdown.
- Multi-user / multi-actor scoping (we treat the single user as the only `user_id` and use the store name as the scope).
