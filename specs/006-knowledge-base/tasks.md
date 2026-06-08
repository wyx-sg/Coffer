# Tasks — 006 Knowledge Base (redesign)

Numbered, checkbox-tracked work breakdown. Each task is independently committable. Order respects layered architecture (domain → application → infrastructure → surfaces) and TDD: failing test first, then implementation.

The substrate (`coffer.{domain,infrastructure}.knowledge`) is **shared with spec 007 (memory)** and lands in the same `feature/kb-memory-redesign` PR; substrate tasks are marked `(shared)`.

## Phase 1 — Spec docs

- [x] T-0001 Rewrite `spec.md` + `spec.zh.md` (KB face of the redesign; acceptance scenarios)
- [x] T-0002 Rewrite `plan.md` + `plan.zh.md`
- [x] T-0003 Rewrite `research.md` + `research.zh.md` (files+SQLite, MarkItDown, 3 modes, configurable embeddings)
- [x] T-0004 Rewrite `data-model.md` + `data-model.zh.md` (unified `documents`/`chunks`, FTS5, sqlite-vec, ports)
- [x] T-0005 Rewrite `contracts/api.openapi.yaml` (new REST surface + app-wide error envelope)
- [x] T-0006 Rewrite `quickstart.md` + `quickstart.zh.md`
- [ ] T-0007 New ADR (supersedes ADR-010 LlamaIndex + ADR-011 mem0): retrieval stack = files-as-truth + FTS5 + sqlite-vec + configurable embeddings; converters behind a port. Update `.specify/memory/architecture.md`.

## Phase 2 — Migration & dependencies

- [ ] T-0010 `backend/pyproject.toml` — drop `llama-index-*`, `sentence-transformers`, `chromadb`, `mem0`; add `markitdown`, `sqlite-vec`, `openai`, optional `fastembed`; require `ripgrep`
- [ ] T-0011 Alembic migration — drop `kb_documents` + `memory_records`; create unified `documents`, `chunks`, `documents_fts` (FTS5 contentless), `vec_chunks` (sqlite-vec); delete old per-corpus dirs on upgrade
- [ ] T-0012 Update `migrations/env.py` to import the unified `documents`/`chunks` ORM
- [ ] T-0013 Extend importlinter contracts 5 & 6; replace the LlamaIndex confinement rule with Contract 7 (no `markitdown`/`docling`/`sqlite_vec`/`openai`/`fastembed` in application/domain)

## Phase 3 — Substrate: domain layer (PURE, shared)

- [ ] T-0020 (shared) `domain/knowledge/document.py` — `Document` entity (kind-discriminated)
- [ ] T-0021 (shared) `domain/knowledge/retrieval.py` — `Passage`, `GrepHit`, `SearchResult`, `RetrievalMode`
- [ ] T-0022 (shared) `domain/knowledge/converter.py` — `MarkdownConverter` port
- [ ] T-0023 (shared) `domain/knowledge/embedder.py` — `Embedder` port + `EmbeddingConfig`
- [ ] T-0024 (shared) `domain/knowledge/index.py` — `KnowledgeIndex` port
- [ ] T-0025 Extend `domain/errors.py` — `KBNotFound`, `DocumentNotFound`, `IngestRejected`, `EngineUnavailable`, `ReconversionBlocked`
- [ ] T-0026 Unit tests for value objects + config validation

## Phase 4 — Substrate: infrastructure (engine confinement, shared)

- [ ] T-0030 (shared) `infrastructure/knowledge/paths.py` — `~/.coffer/knowledge/<name>/{docs,raw}` (sole path module)
- [ ] T-0031 (shared) `infrastructure/knowledge/converters/registry.py` + `passthrough_converter.py`
- [ ] T-0032 (shared) `infrastructure/knowledge/converters/markitdown_converter.py` — ONLY importer of `markitdown`
- [ ] T-0033 (shared) `infrastructure/knowledge/cleaning.py` + `frontmatter.py`
- [ ] T-0034 (shared) `infrastructure/knowledge/chunking.py` — markdown-aware chunker
- [ ] T-0035 (shared) `infrastructure/knowledge/sqlite_index.py` — `DocumentModel`, `ChunkModel`, `KnowledgeIndexRepo` (FTS5 + bm25)
- [ ] T-0036 (shared) `infrastructure/knowledge/vec_index.py` — ONLY importer of `sqlite_vec`
- [ ] T-0037 (shared) `infrastructure/knowledge/embedders.py` — OpenAI-compatible + `local` fastembed; ONLY importer of `openai`/`fastembed`
- [ ] T-0038 (shared) `infrastructure/knowledge/grep.py` — bounded ripgrep wrapper
- [ ] T-0039 Integration tests: `test_markitdown_real.py` (importorskip), FTS5 roundtrip, sqlite-vec roundtrip (importorskip)

## Phase 5 — KB application layer

- [ ] T-0040 `application/knowledge_base/config.py` — `KnowledgeBaseConfig` (Pydantic v2; mutable fields)
- [ ] T-0041 `application/knowledge_base/reindex.py` — the single idempotent re-index routine
- [ ] T-0042 `application/knowledge_base/service.py` — ingest / list / read / edit / re-upload / reindex / search / grep / delete
- [ ] T-0043 `application/knowledge_base/kind.py` — `make_kb_kind(...)` with on_delete cascade
- [ ] T-0044 Unit test: `test_kb_service_with_fakes.py` (FakeMarkdownConverter + FakeEmbedder)

## Phase 6 — Surfaces

- [ ] T-0050 `surfaces/http/knowledge_base/schemas.py` (matches OpenAPI)
- [ ] T-0051 `surfaces/http/knowledge_base/routes.py` — create/list/get/ingest/docs/edit/delete/reindex/search/grep/metrics
- [ ] T-0052 `surfaces/cli/knowledge_base_cmd.py` — `coffer kb create/ingest/list-docs/read/search/grep/edit/reindex/set-embedding/delete-doc/delete-kb/describe`
- [ ] T-0053 Integration tests: `test_http_routes.py`, `test_retrieval_modes.py` (grep/keyword/vector + fallback — acceptance), `test_reindex_idempotency.py`, `test_kb_lifecycle.py` (acceptance)

## Phase 7 — MCP built-in tools (read-only)

- [ ] T-0060 `application/mcp/builtin_tools.py` — register `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document`
- [ ] T-0061 Update `application/mcp/gateway.py` to route the four `coffer__*_knowledge` tools; keep `coffer` server-name reservation
- [ ] T-0062 Integration test: `test_mcp_builtin_tools.py` — list/search/grep/read via the gateway; assert no KB write tool exists

## Phase 8 — Composition root + dependencies

- [ ] T-0070 Update `surfaces/http/app.py` — wire the KB kind + routers in lifespan
- [ ] T-0071 Update `surfaces/cli/main.py` — `app.add_typer(knowledge_base_cmd.app, name="kb")`
- [ ] T-0072 Update `surfaces/http/dependencies.py` — KB service getter (converter registry, index repo, embedder factory)
- [ ] T-0073 Contract test: `tests/contract/test_kb_openapi.py` (OpenAPI dump matches `contracts/api.openapi.yaml`)

## Phase 9 — Frontend

- [ ] T-0080 `frontend/src/kinds/knowledge_base/schema.ts` (zod mirrors `KnowledgeBaseConfig` incl. embedding)
- [ ] T-0081 `KnowledgeBaseForm.tsx` (enabled modes, chunk params, optional embedding provider)
- [ ] T-0082 `KnowledgeBaseDetailPage.tsx` (DocumentTable + UploadDropzone + DocumentViewer + SearchPanel)
- [ ] T-0083 `DocumentTable.tsx`, `DocumentViewer.tsx` (render + edit + reindex), `UploadDropzone.tsx`, `SearchPanel.tsx` (mode selector)
- [ ] T-0084 `frontend/src/kinds/knowledge_base/index.tsx` (`KNOWLEDGE_BASE_KIND_UI`) + register in `frontend/src/kinds.ts`
- [ ] T-0085 Frontend tests for form, table, detail page, search panel

## Phase 10 — Verification

- [ ] T-0090 `make verify-acceptance` — every scenario covered by a marker
- [ ] T-0091 `make verify-unit` — including purity guardrail
- [ ] T-0092 `make verify-integration`
- [ ] T-0093 `make verify-contract`
- [ ] T-0094 `make lint` — including importlinter contracts 1-7
- [ ] T-0095 Final squash + PR per `agents/workflow.md` (KB + memory land together in the redesign PR)
