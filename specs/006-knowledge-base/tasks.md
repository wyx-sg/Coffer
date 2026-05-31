# Tasks — 006 Knowledge Base Manager

Numbered, checkbox-tracked work breakdown. Each task is independently committable. Order respects layered architecture (domain → application → infrastructure → surfaces) and TDD: failing test first, then implementation.

## Phase 1 — Spec docs

- [x] T-0001 Write `spec.md` (user-visible contract + acceptance scenarios)
- [x] T-0002 Write `plan.md` (this implementation plan)
- [x] T-0003 Write `research.md` (engine + embedding + chunking choices)
- [x] T-0004 Write `data-model.md` (entities, ports, schema, on-disk layout)
- [x] T-0005 Write `contracts/api.openapi.yaml`
- [x] T-0006 Write `quickstart.md`
- [x] T-0007 Commit `chore(006-knowledge-base): seed spec/plan/research/data-model/contracts/quickstart`

## Phase 2 — Backend domain layer (PURE)

- [x] T-0010 `domain/knowledge_base/__init__.py`
- [x] T-0011 `domain/knowledge_base/config.py` — `KnowledgeBaseConfig` (Pydantic v2)
- [x] T-0012 `domain/knowledge_base/document.py` — `Document` dataclass
- [x] T-0013 `domain/knowledge_base/store.py` — `KnowledgeBaseStore` Protocol + `Passage`
- [x] T-0014 Extend `domain/errors.py` with `KBNotFound`, `DocumentNotFound`, `IngestRejected`, `EngineUnavailable`
- [x] T-0015 Unit tests: `tests/unit/knowledge_base/test_config_validation.py`, `test_document_value_objects.py`

## Phase 3 — Backend application layer

- [x] T-0020 `application/knowledge_base/__init__.py`
- [x] T-0021 `application/knowledge_base/service.py` — `KnowledgeBaseService` (ingest, list_docs, get_document, search, delete_document)
- [x] T-0022 `application/knowledge_base/kind.py` — `make_kb_kind(...)` returning a `Kind` with on_delete hook
- [x] T-0024 Unit test: `tests/unit/knowledge_base/test_kb_service_with_fake_store.py`

## Phase 4 — Backend infrastructure

- [x] T-0030 `infrastructure/knowledge_base/__init__.py`
- [x] T-0031 `infrastructure/knowledge_base/paths.py` (sole module that knows on-disk layout)
- [x] T-0032 `infrastructure/knowledge_base/loaders.py` (extension whitelist + extractor, pypdf for PDF)
- [x] T-0033 `infrastructure/knowledge_base/persistence.py` — `KBDocumentModel`, `KBDocumentRepo`
- [x] T-0034 `infrastructure/knowledge_base/llamaindex_store.py` — sole importer of `llama_index.*`
- [x] T-0036 Alembic migration `20260527_0007_knowledge_tables.py`
- [x] T-0037 Update `migrations/env.py` to import KB persistence module
- [x] T-0038 Integration tests: `tests/integration/knowledge_base/test_kb_lifecycle.py` (acceptance), `test_loaders.py`, `test_llamaindex_store_real.py` (importorskip)

## Phase 5 — Surfaces

- [x] T-0040 `surfaces/http/knowledge_base/__init__.py`
- [x] T-0041 `surfaces/http/knowledge_base/schemas.py` (matches OpenAPI)
- [x] T-0042 `surfaces/http/knowledge_base/routes.py` (REST endpoints)
- [x] T-0043 `surfaces/cli/knowledge_base_cmd.py` (`coffer kb …`)
- [x] T-0044 Integration tests: `test_http_routes.py`, `test_cli_kb_cmd.py` (CLI exercised via e2e tier)

## Phase 6 — MCP built-in tools

- [x] T-0050 `application/mcp/builtin_tools.py` — register-fn that augments MCPGatewaySession with `coffer__*` tools
- [x] T-0051 Reserve `coffer` server name in mcp_server registration (reject with clear error)
- [x] T-0052 Update existing `application/mcp/gateway.py` to route `coffer__*` tools to the built-in handler
- [x] T-0053 Integration test: `test_mcp_builtin_tools.py` — list/search/get-document via the gateway

## Phase 7 — Composition root + dependencies

- [x] T-0060 Update `backend/pyproject.toml` — add deps + new importlinter contract; extend contracts 5 & 6
- [x] T-0061 Update `surfaces/http/app.py` — add `_wire_kb_kind(...)` in lifespan
- [x] T-0062 Update `surfaces/cli/main.py` — `app.add_typer(knowledge_base_cmd.app, name="kb")`
- [x] T-0063 Update `surfaces/http/dependencies.py` — KB service getter
- [x] T-0064 Contract test: `tests/contract/test_kb_openapi.py` (OpenAPI dump matches `contracts/api.openapi.yaml`)

## Phase 8 — Frontend

- [x] T-0070 `frontend/src/kinds/knowledge_base/schema.ts` (zod schema mirroring `KnowledgeBaseConfig`)
- [x] T-0071 `KnowledgeBaseForm.tsx` (create form)
- [x] T-0072 `KnowledgeBaseCard.tsx` (resource list row)
- [x] T-0073 `KnowledgeBaseDetailPage.tsx` (documents + upload + search)
- [x] T-0074 `DocumentList.tsx`, `UploadDropzone.tsx`, `SearchBox.tsx`
- [x] T-0075 `frontend/src/kinds/knowledge_base/index.tsx` (`KNOWLEDGE_BASE_KIND_UI`)
- [x] T-0076 Update `frontend/src/kinds.ts` to register the KB kind UI
- [x] T-0077 Frontend tests for form, list, detail page

## Phase 9 — Verification

- [x] T-0090 `make verify-acceptance` — every scenario covered by a marker
- [x] T-0091 `make verify-unit` — including purity guardrail
- [x] T-0092 `make verify-integration`
- [x] T-0093 `make verify-contract`
- [x] T-0094 `make lint` — including importlinter contracts 1-7
- [x] T-0095 Final commit `feat(kb): knowledge base manager kind end-to-end`

## Phase 10 — STOP

- [x] T-0100 Branch pushed, PR **#22** opened (per `agents/workflow.md` and user policy on AI-driven merges)
