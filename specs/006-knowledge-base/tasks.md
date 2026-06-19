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
- [x] T-0007 New ADR (supersedes ADR-010 LlamaIndex + ADR-011 mem0): retrieval stack = files-as-truth + FTS5 + sqlite-vec + configurable embeddings; converters behind a port. Update `.specify/memory/architecture.md`.

## Phase 2 — Migration & dependencies

- [x] T-0010 `backend/pyproject.toml` — drop `llama-index-*`, `sentence-transformers`, `chromadb`, `mem0`; add `markitdown`, `sqlite-vec`, `openai`, optional `fastembed`; require `ripgrep`
- [x] T-0011 Alembic migration — drop `kb_documents` + `memory_records`; create unified `documents`, `chunks`, and `documents_fts` (a regular FTS5 table that stores the chunk text once inside its index; still rebuildable from the markdown files); delete old per-corpus dirs on upgrade. The per-store sqlite-vec `vec_chunks` tables are NOT created here — `vec_index.py` creates them lazily at the configured width.
- [x] T-0012 Update `migrations/env.py` to import the unified `documents`/`chunks` ORM
- [x] T-0013 Extend importlinter contracts 5 & 6; replace the LlamaIndex confinement rule with Contract 7 (no `markitdown`/`docling`/`sqlite_vec`/`openai`/`fastembed` in application/domain)

## Phase 3 — Substrate: domain layer (PURE, shared)

- [x] T-0020 (shared) `domain/knowledge/document.py` — `Document` entity (kind-discriminated)
- [x] T-0021 (shared) `domain/knowledge/retrieval.py` — `Passage`, `GrepHit`, `SearchResult`, `RetrievalMode`
- [x] T-0022 (shared) `domain/knowledge/converter.py` — `MarkdownConverter` port
- [x] T-0023 (shared) `domain/knowledge/embedder.py` — `Embedder` port + `EmbeddingConfig`
- [x] T-0024 (shared) `domain/knowledge/index.py` — `KnowledgeIndex` port
- [x] T-0025 Extend `domain/errors.py` — `KBNotFound`, `DocumentNotFound`, `IngestRejected`, `EngineUnavailable`, `ReconversionBlocked`, `SearchModeInvalid` (re-exported via `domain/knowledge/errors.py`)
- [x] T-0026 Unit tests for value objects + config validation

## Phase 4 — Substrate: infrastructure (engine confinement, shared)

- [x] T-0030 (shared) `infrastructure/knowledge/paths.py` — `~/.coffer/knowledge/<name>/{docs,raw}` (sole path module)
- [x] T-0031 (shared) `infrastructure/knowledge/converters/registry.py` + `passthrough_converter.py` + `csv_converter.py`
- [x] T-0032 (shared) `infrastructure/knowledge/converters/markitdown_converter.py` — ONLY importer of `markitdown`
- [x] T-0033 (shared) `infrastructure/knowledge/cleaning.py` + `frontmatter.py`
- [x] T-0034 (shared) `infrastructure/knowledge/chunking.py` — markdown-aware chunker
- [x] T-0035 (shared) `infrastructure/knowledge/models.py` + `ddl.py` + `repository.py` + `sqlite_index.py` — `DocumentModel`, `ChunkModel`, `DocumentRepo`, `SqliteKnowledgeIndex` (FTS5 + bm25)
- [x] T-0036 (shared) `infrastructure/knowledge/vec_index.py` — `VecIndex`; ONLY importer of `sqlite_vec`; creates the per-store vec tables lazily
- [x] T-0037 (shared) `infrastructure/knowledge/embeddings.py` — OpenAI-compatible + `local` fastembed; ONLY importer of `openai`/`fastembed`
- [x] T-0038 (shared) `infrastructure/knowledge/grep.py` — bounded ripgrep wrapper
- [x] T-0039 Integration tests: `test_markitdown_real.py` (importorskip), FTS5 roundtrip, sqlite-vec roundtrip (importorskip)

## Phase 5 — KB application layer

- [x] T-0040 `domain/knowledge_base/config.py` — `KnowledgeBaseConfig` (Pydantic v2; mutable fields)
- [x] T-0041 `application/knowledge/reindex.py` — the single idempotent re-index routine (`Reindexer`, shared with memory) + `application/knowledge/locks.py` (per-store write locks) + `application/knowledge/retrieval.py` (`KnowledgeRetrieval` facade)
- [x] T-0042 `application/knowledge_base/service.py` + `pipeline.py` — ingest / list / read / edit / reconvert / re-upload / reindex / search / grep / delete
- [x] T-0043 `application/knowledge_base/kind.py` — `make_kb_kind(...)` with on_delete cascade
- [x] T-0044 Unit test: `test_kb_service_with_fakes.py` (FakeMarkdownConverter + FakeEmbedder)

## Phase 6 — Surfaces

- [x] T-0050 `surfaces/http/knowledge_base/schemas.py` (matches OpenAPI)
- [x] T-0051 `surfaces/http/knowledge_base/routes.py` — create/list/get/ingest/docs/edit/reconvert/delete/reindex/search/grep/metrics
- [x] T-0052 `surfaces/cli/knowledge_base_cmd.py` — `coffer kb create/ingest/list-docs/get-doc(read)/search/grep/edit/reconvert/reindex/set-embedding/set-chunking/delete-doc/delete-kb/describe`
- [x] T-0053 Integration tests: `test_http_routes.py`, `test_retrieval_modes.py` (grep/keyword/vector + fallback — acceptance), `test_reindex_idempotency.py`, `test_kb_lifecycle.py` (acceptance)

## Phase 7 — MCP built-in tools (read-only)

- [x] T-0060 `application/knowledge_base/builtin_tools.py` — register `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document`
- [x] T-0061 Update `application/mcp/gateway.py` / `gateway_builtin.py` to route the four `coffer__*_knowledge` tools; keep `coffer` server-name reservation
- [x] T-0062 Integration test: `test_mcp_builtin_tools.py` — list/search/grep/read via the gateway; assert no KB write tool exists _(superseded by T-0106/T-0108 — write tools now exist, ADR-028)_

## Phase 8 — Composition root + dependencies

- [x] T-0070 Update `surfaces/http/app.py` — wire the KB kind + routers in lifespan
- [x] T-0071 Update `surfaces/cli/main.py` — `app.add_typer(knowledge_base_cmd.app, name="kb")`
- [x] T-0072 Update `surfaces/http/dependencies.py` — KB service getter (converter registry, index repo, embedder factory)
- [x] T-0073 Contract test: `tests/contract/test_kb_openapi.py` (OpenAPI dump matches `contracts/api.openapi.yaml`)

## Phase 9 — Frontend

- [x] T-0080 `frontend/src/kinds/knowledge_base/schema.ts` (zod mirrors `KnowledgeBaseConfig` incl. embedding)
- [x] T-0081 `KnowledgeBaseForm.tsx` (enabled modes, chunk params, optional embedding provider)
- [x] T-0082 `KnowledgeBaseDetailPage.tsx` (DocumentTable + UploadDropzone + DocumentViewer + SearchPanel)
- [x] T-0083 `DocumentTable.tsx`, `DocumentViewer.tsx` (read-only render + open-in-editor / reveal / copy-path), `UploadDropzone.tsx`, `SearchPanel.tsx` (mode selector)
- [x] T-0084 `frontend/src/kinds/knowledge_base/index.tsx` (`KNOWLEDGE_BASE_KIND_UI`) + register in `frontend/src/kinds.ts`
- [x] T-0085 Frontend tests for form, table, detail page, search panel

## Phase 10 — Verification

- [x] T-0090 `make verify-acceptance` — every scenario covered by a marker
- [x] T-0091 `make verify-unit` — including purity guardrail
- [x] T-0092 `make verify-integration`
- [x] T-0093 `make verify-contract`
- [x] T-0094 `make lint` — including importlinter contracts 1-7
- [x] T-0095 Final squash + PR per `agents/workflow.md` (KB + memory land together in the redesign PR)

## Phase 11 — Documents co-managed (ADR-028; unified-knowledge slice)

Reverses the agent-read-only + content-addressed-id stance. Global scope only; per-project scope, soft-delete, and an in-app editor are deferred to the unified-知识 UI slice (see `plan.md` amendment).

- [x] T-0100 Spec surgery: `spec.md`/`spec.zh.md` (US3 read+write, FR-007/015/016/017 + new FR-021 lock, edge cases, scenarios), `data-model.md`/`.zh.md` (ULID id, `locked`, `DocumentLocked`, `find_by_filename`/`set_locked`, audit events), `plan.md`/`.zh.md` (amendment), `quickstart.md`/`.zh.md`, `contracts/api.openapi.yaml`; new ADR-028 (+zh)
- [ ] T-0101 Migration `0025` — add `documents.locked BOOLEAN NOT NULL DEFAULT 0` (idempotent `_has_column`); bump `HEAD_REVISION` + assert the column in `test_migrations_roundtrip.py`
- [ ] T-0102 Domain: `Document.locked`; `DocumentModel.locked`; `DocumentLocked` error (409); audit `KB_DOCUMENT_LOCKED` / `KB_DOCUMENT_UNLOCKED`
- [ ] T-0103 Repo: `_to_domain`/`upsert` carry `locked`; add `find_by_filename` + `set_locked`; drop dead `exists_source`
- [ ] T-0104 Pipeline: ULID doc id (`new_ulid()`); re-upload match-by-filename (no-op / in-place update / new); lock enforcement
- [ ] T-0105 Service: ingest status → audit (ingested/updated/skip); lock guards on edit/reconvert/delete; `set_document_lock` (+audit)
- [ ] T-0106 MCP write tools `coffer__add_document` / `edit_document` / `delete_document`; reverse the read-only docstring
- [ ] T-0107 Surfaces: `PATCH …/documents/{id}` lock endpoint; `DocumentOut` += `locked` + `project_id`; `coffer kb lock/unlock` CLI (FR-019 parity)
- [ ] T-0108 Backend tests: identity/update-replace, lock-blocks-mutation, set-lock audit, agent-write tools (+ lock respect); update dedup + cross-KB tests for ULID semantics
- [ ] T-0109 Frontend: `setDocumentLock` api + `locked`/`project_id` types; lock badge + toggle in the viewer; i18n; api/schema tests
- [ ] T-0110 `make verify` (with optional engines + `rg`); self-review; squash + PR + CI + merge

## Phase 12 — Per-project scope + soft-delete + unified 知识 UI (ADR-030; unified-knowledge slice)

Completes the unified-knowledge redesign: per-project document scope (FR-022), recoverable soft-delete (FR-023), and the unified 知识 presentation (FR-019 + 007 FR-017b). The in-app editor stays out (FR-020 read-only viewer unchanged).

- [ ] T-0120 Spec surgery: `spec.md`/`.zh` (US4 trash, US6 scope, FR-003/007/019/022/023, scenarios, edge cases, SC-008/009), `data-model.md`/`.zh` (`deleted_at`, project layout, repo methods, cascade, audit, wire), `contracts/api.openapi.yaml` (restore endpoint, `project_id` ingest field, `deleted`/`project_id` list filters, `deleted_at`), 007 `data-model.md`/`.zh` (`deleted_at` sync) + `spec.md`/`.zh` (FR-017b), new ADR-030 (+zh)
- [ ] T-0121 Lift `scope_fs` (`git_root`/`project_ulid`) into shared `infrastructure/knowledge/scope_fs.py`; re-point memory's wiring; `paths.py` scope-bearing builders gain `project_id` + a `kb_store_dir` router
- [ ] T-0122 Migration `0026` — add `documents.deleted_at TIMESTAMP` (nullable, idempotent `_has_column`); bump `HEAD_REVISION` + assert the column in `test_migrations_roundtrip.py`
- [ ] T-0123 Domain/repo: `Document.deleted_at`; `DocumentModel.deleted_at`; repo reads filter `deleted_at IS NULL` + `project_id`/`deleted` params; `soft_delete_document`; `find_by_filename` live-only
- [ ] T-0124 Pipeline (extract first — `pipeline.py` is at the 400-line cap): thread `project_id` through `_store_ref`/`build_kb_document`/`document_from_frontmatter`/`find_by_filename`/`_write_files`; `reindex_scan` walks `projects/*/docs` + skips tombstones (no resurrect/prune); `soft_delete` + `restore` paths
- [ ] T-0125 Service: `_store_ref(project_id)`; `delete_document` → soft-delete (live) / purge (trashed); `restore_document` (+audit `KB_DOCUMENT_RESTORED`/`KB_DOCUMENT_PURGED`); `_require_document` treats tombstone as not-found; scope-filtered list/search/grep
- [ ] T-0126 MCP: `add_document`/write tools resolve project scope from injected `cwd` (declare `cwd` in input_schema); `delete_document` is now a soft-delete
- [ ] T-0127 Surfaces: `POST …/documents/{id}/restore`; `project_id` ingest form field; `deleted`/`project_id` list query; `DocumentOut += deleted_at`; `coffer kb trash` + `coffer kb restore` CLI
- [ ] T-0128 Backend tests (acceptance markers for the 7 new scenarios + revised delete): project-scope isolation, re-upload scoped, soft-delete-to-trash, restore-from-raw, reindex-no-resurrect, purge, scope-filtered search; memory unaffected by the shared `deleted_at` filter
- [ ] T-0129 Frontend: unified 知识 nav (one entry replacing 记忆/知识库), scope axis (全局/legible project list), intermixed notes+documents, add-by-shape input, trash/restore surface; `/memory`+`/knowledge-bases` legacy redirects; api/types/hooks unify; i18n; component + api tests; `tsc --noEmit` + vitest
- [ ] T-0130 `make verify` (optional engines + `rg`) + frontend `tsc`/vitest; 3-agent self-review; rebase onto current main; squash + PR + CI + merge
