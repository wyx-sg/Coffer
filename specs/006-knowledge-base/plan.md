# Implementation Plan: 006 — Knowledge Base Manager

**Branch**: `feature/kb-manager`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Add a second resource `kind` to Coffer's kind-agnostic framework: `knowledge_base`. Each KB is a Resource holding configuration (embedding model, chunk size, chunk overlap, max document size). Documents are stored as raw files on disk under `~/.coffer/kb/<name>/raw/` and indexed (chunks + vectors) under `~/.coffer/kb/<name>/index/` by **LlamaIndex** — kept behind a thin `KnowledgeBaseStore` port so the application and domain layers never import LlamaIndex types.

The agent integration goes through Coffer's existing MCP gateway: three new built-in tools (`coffer__list_knowledge_bases`, `coffer__search_knowledge_base`, `coffer__get_document`) are added to every connected MCP client's tool list, namespaced under a reserved `coffer__` prefix that cannot collide with upstream MCP servers.

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                          |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x                                                                                                                                                                                                   |
| **Primary Dependencies (added by this spec)** | `llama-index-core` (RAG framework, behind port); `llama-index-embeddings-huggingface` + `sentence-transformers` (default local embedding model: `BAAI/bge-small-en-v1.5`); `pypdf` (PDF extraction).                           |
| **Storage**                                   | SQLite at `~/.coffer/coffer.db` for control-plane rows; documents under `~/.coffer/kb/<name>/` as plain files.                                                                                                                 |
| **Testing**                                   | 4-tier model. Acceptance markers tie tests to `spec.md` scenarios. Real SQLite + a `FakeKnowledgeBaseStore` cover most paths; one integration test exercises the real LlamaIndex adapter behind a `pytest.importorskip` guard. |
| **Performance Goals**                         | SC-002: ≤ 500 ms search wall-clock at REST surface on a 50-document KB.                                                                                                                                                        |
| **Constraints**                               | LlamaIndex confined to `coffer.infrastructure.knowledge_base.*` (importlinter); no outbound network calls during ingest or search; daemon starts even if LlamaIndex fails to import (endpoints degrade to 503).                |
| **Scale / Scope**                             | Single user; ≤ 20 KBs; ≤ 500 documents per KB; ≤ 25 MB per document (default).                                                                                                                                                 |

## Constitution Check

| Clause                    | Compliance | Notes                                                                                                                                                                            |
| ------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First**        | ✅         | Local embeddings; documents on disk; no cloud calls.                                                                                                                             |
| **II. Spec-as-Truth**     | ✅         | Spec committed first; acceptance scenarios drive tests.                                                                                                                          |
| **III. OSS-Readiness**    | ✅         | LlamaIndex (MIT), sentence-transformers (Apache 2.0), pypdf (BSD-3).                                                                                                             |
| **Languages**             | ✅         | Python 3.12 backend + TS 5 frontend only.                                                                                                                                        |
| **Architecture: layered** | ✅         | Engine confined to `infrastructure/`. Two new importlinter clauses (see below).                                                                                                  |
| **Persistence**           | ✅         | SQLite for control plane; bulk content (documents) on disk — matches the constitution's "Bulk user content is stored as files on the local file system; indexed on demand" rule. |
| **Credentials**           | ✅         | None needed; no remote APIs in default config.                                                                                                                                   |
| **Network defaults**      | ✅         | Loopback-only.                                                                                                                                                                   |

## Project Structure

### Documentation (this feature)

```text
specs/006-knowledge-base/
├── spec.md
├── plan.md                # this file
├── research.md            # LlamaIndex / embedding model / chunking choices
├── data-model.md          # entities, ports, schema
├── contracts/
│   └── api.openapi.yaml   # REST contract for /api/v1/knowledge_bases/*
├── quickstart.md
└── tasks.md
```

### Source code (where each layer lands)

```text
backend/coffer/
├── domain/
│   ├── errors.py                                    # add: KBNotFound, DocumentNotFound, IngestRejected, EngineUnavailable
│   └── knowledge_base/
│       ├── __init__.py
│       ├── config.py                                # KnowledgeBaseConfig pydantic v2 schema
│       ├── document.py                              # Document dataclass (kind-internal entity)
│       └── store.py                                 # KnowledgeBaseStore port (Protocol) + Passage value object
├── application/
│   └── knowledge_base/
│       ├── __init__.py
│       ├── kind.py                                  # make_kb_kind(...): builds Kind with on_delete
│       └── service.py                               # KnowledgeBaseService: ingest/list_docs/search/delete_doc
├── infrastructure/
│   └── knowledge_base/
│       ├── __init__.py
│       ├── llamaindex_store.py                      # ONLY file that imports llama_index.*
│       ├── document_repo.py                         # SqlAlchemy repo for kb_documents
│       ├── persistence.py                           # SqlAlchemy ORM for kb_documents
│       ├── paths.py                                 # ~/.coffer/kb/<name>/{raw,index} layout helpers
│       └── loaders.py                               # MIME / extension whitelist + extractor (pypdf for PDF)
├── application/mcp/
│   └── builtin_tools.py                             # KB built-in tools registered into MCPGatewaySession
└── surfaces/
    ├── http/
    │   └── knowledge_base/
    │       ├── __init__.py
    │       ├── routes.py                            # /api/v1/knowledge_bases/* + ingest/search/list-docs
    │       └── schemas.py                           # KBCreate, KBOut, IngestResult, SearchHit, ...
    └── cli/
        └── knowledge_base_cmd.py                    # `coffer kb create/ingest/search/list-docs/delete-doc/delete-kb/describe`
```

Existing files modified (intersection point with feature/skill-manager / feature/memory-manager — resolve via rebase):

- `backend/coffer/surfaces/http/app.py` — add `_wire_kb_kind(...)` in lifespan; include KB routers.
- `backend/coffer/surfaces/cli/main.py` — `app.add_typer(knowledge_base_cmd.app, name="kb")`.
- `backend/coffer/application/mcp/gateway.py` (or a new shim) — route `coffer__*` tools to the built-in handler.
- `backend/coffer/infrastructure/persistence/migrations/env.py` — add KB ORM import so the new table is picked up.
- `backend/pyproject.toml` — new deps + importlinter contract for engine isolation.
- `frontend/src/kinds.ts` — register `KNOWLEDGE_BASE_KIND_UI`.

### Frontend

```text
frontend/src/kinds/knowledge_base/
├── index.tsx                 # KNOWLEDGE_BASE_KIND_UI (Card + DetailPage + addPath)
├── KnowledgeBaseCard.tsx
├── KnowledgeBaseDetailPage.tsx
├── KnowledgeBaseForm.tsx
├── DocumentList.tsx
├── UploadDropzone.tsx
├── SearchBox.tsx
└── schema.ts
```

### Tests

```text
backend/tests/
├── unit/knowledge_base/
│   ├── test_config_validation.py
│   ├── test_document_value_objects.py
│   ├── test_loaders_extension_whitelist.py
│   └── test_kb_service_with_fake_store.py
├── integration/knowledge_base/
│   ├── test_kb_lifecycle.py                # create → ingest → search → delete-doc → delete-kb (acceptance)
│   ├── test_mcp_builtin_tools.py           # search_knowledge_base / get_document / list_knowledge_bases via MCP
│   ├── test_http_routes.py                 # REST surface
│   ├── test_cli_kb_cmd.py
│   └── test_llamaindex_store_real.py       # importorskip llama_index_core; smoke
└── contract/
    └── test_kb_openapi.py                  # OpenAPI dump matches contracts/api.openapi.yaml

frontend/src/kinds/knowledge_base/
├── KnowledgeBaseForm.test.tsx
├── KnowledgeBaseDetailPage.test.tsx
└── DocumentList.test.tsx
```

## Phase 1 — Spec & contract (this PR's first commits)

1. spec.md ✅ committed before any code.
2. data-model.md — entities, port methods, SQL schema (`kb_documents` table).
3. contracts/api.openapi.yaml — REST surface.
4. research.md — LlamaIndex choice rationale, embedding model selection, chunking defaults.

## Phase 2 — Backend (TDD)

For each acceptance scenario in `spec.md`:

1. Write a failing test in the correct tier (unit if pure, integration otherwise) with the acceptance marker.
2. Write the minimal domain/application/infra code to make it pass.
3. Commit small chunk: `feat(kb): <scenario>` (Conventional Commits).

Order: domain types → port → `FakeKnowledgeBaseStore` in tests → application service → real `LlamaIndexKnowledgeBaseStore` → HTTP routes → CLI → built-in MCP tools → composition root wiring.

## Phase 3 — Frontend

1. `KnowledgeBaseForm` (zod schema; mirrors `KnowledgeBaseConfig`).
2. `KnowledgeBaseDetailPage` (document list + upload + search).
3. Register `KNOWLEDGE_BASE_KIND_UI` in `kinds.ts`.
4. One integration test per acceptance scenario that lives in the frontend (UI flows).

## Phase 4 — Verification

1. `make lint` — including the new importlinter contract.
2. `make verify-unit` (purity guardrail passes; no banned-I/O imports under `tests/unit/`).
3. `make verify-integration`.
4. `make verify-contract` — OpenAPI conformance.
5. `make verify-acceptance` — every scenario in `spec.md` has a covering marker.
6. Commit final.

## Importlinter contracts to add

The two new contracts extend the existing kind-isolation regime so the same rules that hold for `mcp` now hold for `knowledge_base`:

- **Extend Contract 5** (cross-kind imports forbidden): add `coffer.domain.knowledge_base`, `coffer.application.knowledge_base`, `coffer.infrastructure.knowledge_base`, `coffer.surfaces.http.knowledge_base` to the `source_modules` list, and add `coffer.*.mcp` to the `forbidden_modules` set per-kind. (The `memory` kind lands in spec 007; its cross-kind forbid rule is added then.)
- **Extend Contract 6** (kind-agnostic core ↛ kind-specific): add `coffer.domain.knowledge_base`, `coffer.application.knowledge_base`, etc. to `forbidden_modules`.
- **New Contract 7** (engine confinement): `coffer.application.*` and `coffer.domain.*` MUST NOT import `llama_index*`.

## Risks & mitigations

| Risk                                                                         | Mitigation                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LlamaIndex major-version churn (it broke API twice in 2024)                  | All LlamaIndex types are in one file (`infrastructure/knowledge_base/llamaindex_store.py`); a future bump touches that file only. The port is designed to express our needs, not LlamaIndex's.             |
| LlamaIndex install heavy / slow on CI                                        | Mark integration tests that need the real engine with `pytest.importorskip("llama_index.core")`; the unit suite uses `FakeKnowledgeBaseStore`. CI installs `llama-index-core` only (not the meta-package). |
| Embedding model download on first ingest                                     | Document this clearly in `quickstart.md`. Provide a `coffer kb warmup <name>` command that triggers the download deterministically.                                                                        |
| `pypdf` text extraction quality varies                                       | Pre-flight extraction in the loader; reject empty extractions with a clear error; document the supported-format expectation in `quickstart.md`.                                                            |
| Concurrent ingest on the same KB                                             | Per-KB asyncio.Lock around index mutations inside the store adapter; reads are not locked.                                                                                                                 |
| LlamaIndex pulls in transitively heavy deps that conflict with existing pins | Lock to `llama-index-core` only (no meta-package); add the specific embedding integration we need (`llama-index-embeddings-huggingface`).                                                                  |

## Out of scope (deferred)

- LLM synthesis on top of retrieval (the agent does that itself — Coffer just returns passages).
- Rerankers, multi-query expansion, HyDE.
- Document version history (re-ingest replaces).
- Source-code-aware chunking beyond the default recursive splitter.
- Image OCR, audio transcription.
- Multi-modal retrieval.
- Cloud embedding providers.

These can land as later specs after MVP usage settles. The port surface is intentionally minimal so adding any of these means a new adapter or method, not a re-modelling.
