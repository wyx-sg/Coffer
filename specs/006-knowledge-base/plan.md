# Implementation Plan: 006 — Knowledge Base (redesign)

> 中文版: [plan.zh.md](./plan.zh.md)

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted (redesign — in development)

## Summary

Rebuild the `knowledge_base` resource kind as the **KB face of a shared knowledge substrate**. A KB is a Resource holding retrieval config (enabled modes, chunk params, embedding provider). Ingestion accepts **any file format**, converts it to **Markdown on disk** (`~/.coffer/knowledge/<name>/docs/<doc-id>.md` = source of truth), keeps the original under `raw/`, and indexes the Markdown into the same `coffer.db` (unified `documents` + `chunks` + FTS5 + sqlite-vec). Retrieval has three modes — `grep` (ripgrep over files), `keyword` (FTS5 + BM25), `vector` (sqlite-vec + a configurable OpenAI-compatible embedding provider). Documents are **co-managed by humans and agents** (ADR-028): both read AND write through the MCP gateway, with a per-document lock and full F01 audit.

This redesign **drops LlamaIndex** and the per-corpus persist dirs, and shares its substrate (table, converter port, retrieval engine, embedding config) with the `memory` kind (spec 007). Both layers — converters and the vector/embedding stack — stay confined to `infrastructure/`.

## Amendment — documents co-managed (ADR-028, 2026-06-19)

A later slice reverses the original "agent-read-only, content-addressed id" stance per [ADR-028](../../docs/decisions/ADR-028-knowledge-base-documents-co-managed.md). Scope decision (within-spec, recorded here per AGENTS.md §4):

**Shipped in this slice (global scope):**

- **Stable ULID identity** (was `source_sha256[:16]`). `content_sha256` stays the reindex gate; `source_sha256` stays in `metadata` as provenance. Re-upload is matched by `original_filename` in-store: identical bytes = no-op; changed bytes + same name = in-place update of the same id (needs `replace=true`); new name = new doc (FR-007/FR-015).
- **Agent MCP write tools** `coffer__add_document` / `edit_document` / `delete_document` alongside the read tools (FR-017), sharing the REST service paths (lock + audit honoured).
- **Per-document lock** (`locked` column via migration `0025`): a locked doc refuses edit / reconvert / replace / delete for everyone (FR-021); lock/unlock audited (`KB_DOCUMENT_LOCKED` / `_UNLOCKED`).
- `DocumentLocked` (409) domain error; `DocumentOut` gains `locked` + `project_id`; `PATCH …/documents/{id}` lock endpoint; viewer gains a lock badge + toggle (stays read-only otherwise).

**Deferred to the unified-知识 UI slice (co-dependent with the UI that surfaces them):**

- **Per-project document scope** (the 全局/项目 axis for KB documents).
- **Recoverable soft-delete** (trash/restore). For now delete is hard, with an F01 audit trail; the lock guards curated docs.
- **In-app Markdown editor** — the viewer stays read-only with external-editor affordances (per the read-only-viewers decision); humans edit via external editor / edit API, agents via MCP.

## Amendment — per-project scope + soft-delete + unified 知识 UI (ADR-030, 2026-06-19)

The unified-知识 slice lands the two deferred backend pieces and the unified presentation, per [ADR-030](../../docs/decisions/ADR-030-per-project-kb-scope-and-soft-delete.md). User decisions this slice (recorded per AGENTS.md §4): ship as **one PR**; the **in-app editor stays dropped** (FR-020 read-only viewer is NOT reversed).

**Shipped in this slice:**

- **Per-project document scope (FR-022)**: a real `project_id` (global sentinel | git-root project ULID) threaded through `_store_ref` / `build_kb_document` / `document_from_frontmatter` / `find_by_filename` / `_write_files`; on-disk `knowledge/<kb>/projects/<ulid>/{docs,raw}/` alongside the existing global layout; list/read/grep/search scoped by `project_id`. `scope_fs` (`git_root`/`project_ulid`) lifts from `infrastructure/memory/` into the shared `infrastructure/knowledge/` substrate (no cross-kind import).
- **Recoverable soft-delete (FR-023)**: nullable `deleted_at` (migration `0026`); a live-document delete becomes a soft-delete (clear `docs/<id>.md` + index, keep `raw/` + row); restore re-converts from `raw/`; a trashed-document delete purges; reindex-on-read never resurrects (rebuild branch has no file; prune branch reads live rows only). New audit `KB_DOCUMENT_RESTORED` / `KB_DOCUMENT_PURGED`. The shared-repo `deleted_at IS NULL` filter is a no-op for memory.
- **Unified 知识 UI**: one nav entry (全局/项目 scope axis, notes+documents intermixed, add-by-shape input, trash/restore) replacing the split 记忆/知识库 pages; `/memory`+`/knowledge-bases` kept as legacy redirects (007 FR-017b).
- Surfaces: `POST …/documents/{id}/restore`; `project_id` ingest field; `deleted`/`project_id` list filters; `DocumentOut += deleted_at`; `coffer kb trash` / `coffer kb restore` CLI.

**Still deferred:** in-app Markdown editor; trash auto-expiry (purge is explicit; KB-delete clears trash).

## Technical Context

| Dimension                                        | Value                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**                           | Python 3.12+, TypeScript 5.x                                                                                                                                                                                                                                                                                                                                                               |
| **Primary Dependencies (added by the redesign)** | `markitdown` (default Markdown converter, behind a `MarkdownConverter` port); `sqlite-vec` (vector index in `coffer.db`); FTS5 (bundled with SQLite); `openai` (one `AsyncOpenAI` client, swappable `base_url`, for embeddings); optional `fastembed` (in-process local embeddings); `ripgrep` binary for grep. **Removed**: `llama-index-*`, `sentence-transformers`, `chromadb`, `mem0`. |
| **Storage**                                      | SQLite at `~/.coffer/coffer.db` (resources / documents / chunks / FTS5 / sqlite-vec / audit); Markdown + raw files under `~/.coffer/knowledge/<name>/`.                                                                                                                                                                                                                                    |
| **Testing**                                      | 4-tier. Acceptance markers tie tests to `spec.md` scenarios. Real SQLite (FTS5 + sqlite-vec) in integration; a `FakeMarkdownConverter` + `FakeEmbedder` keep unit tests pure; one integration test exercises real MarkItDown behind `pytest.importorskip`.                                                                                                                                 |
| **Performance Goals**                            | SC-002: keyword ≤ 200 ms, grep ≤ 500 ms wall-clock at REST on a 50-doc KB.                                                                                                                                                                                                                                                                                                                 |
| **Constraints**                                  | Converters + sqlite-vec + embedding SDKs confined to `coffer.infrastructure.*` (importlinter); keyword+grep work offline with zero config; vector may call a third-party embedding API; daemon starts even if a converter lib is missing (that format degrades to `EngineUnavailable`).                                                                                                    |
| **Scale / Scope**                                | Single user; ≤ 20 KBs; ≤ 500 documents per KB; ≤ 25 MB per document (default).                                                                                                                                                                                                                                                                                                             |

## Constitution Check

| Clause                    | Compliance | Notes                                                                                                                                                                                                       |
| ------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First**        | ✅         | All user data (Markdown + raw + SQLite) on disk. Vector mode may call a third-party embedding API — allowed: user data stays local; only the query/text is embedded. Default keyword+grep is fully offline. |
| **II. Spec-as-Truth**     | ✅         | Spec rewritten first; acceptance scenarios drive tests.                                                                                                                                                     |
| **III. OSS-Readiness**    | ✅         | MarkItDown (MIT), sqlite-vec (Apache 2.0/MIT), fastembed (Apache 2.0), openai SDK (Apache 2.0).                                                                                                             |
| **Languages**             | ✅         | Python 3.12 + TS 5 only.                                                                                                                                                                                    |
| **Architecture: layered** | ✅         | Converters + vector/embedding engines confined to `infrastructure/`; new importlinter clauses (below).                                                                                                      |
| **Persistence**           | ✅         | SQLite control plane + derived index; bulk content (Markdown + raw) as files — matches the constitution's files-on-disk rule.                                                                               |
| **Credentials**           | ✅         | Embedding credentials via encrypted-store refs only (`embedding_credential_ref`); secrets are ciphertext, no plaintext in the DB.                                                                           |
| **Network defaults**      | ✅         | Loopback REST; outbound embedding calls go through the SSRF-guarded client.                                                                                                                                 |

## Project Structure

### Documentation (this feature)

```text
specs/006-knowledge-base/
├── spec.md / spec.zh.md
├── plan.md / plan.zh.md          # this file
├── research.md / research.zh.md  # converter / retrieval / embedding choices
├── data-model.md / data-model.zh.md
├── contracts/
│   └── api.openapi.yaml          # REST contract for /api/v1/knowledge_bases/*
├── quickstart.md / quickstart.zh.md
└── tasks.md
```

### Source code (where each layer lands)

The substrate (`knowledge`) is shared with spec 007; this plan lists the KB-facing pieces. Shared substrate modules are noted as `(shared)`.

```text
backend/coffer/
├── domain/
│   ├── errors.py                                # add: KBNotFound, DocumentNotFound, IngestRejected, EngineUnavailable, ReconversionBlocked, SearchModeInvalid
│   ├── knowledge/                               # (shared) substrate domain
│   │   ├── document.py                          # Document entity (kind-discriminated)
│   │   ├── retrieval.py                         # Passage, GrepHit, GrepResult, MemoryHit, RetrievalMode, SearchResult, StoreRef value objects
│   │   ├── converter.py                         # MarkdownConverter port (Protocol)
│   │   ├── embedder.py                          # Embedder port (Protocol) + EmbeddingConfig
│   │   ├── index.py                             # KnowledgeIndex / GrepPort / RetrievalPort protocols
│   │   └── errors.py                            # re-exports of the substrate errors (canonical classes in domain/errors.py)
│   └── knowledge_base/
│       ├── config.py                            # KnowledgeBaseConfig (Pydantic v2)
│       └── document.py                          # KB doc-id = ULID (infrastructure/knowledge/ids.new_ulid; ADR-028)
├── application/
│   ├── knowledge/                               # (shared) substrate application layer
│   │   ├── retrieval.py                         # KnowledgeRetrieval facade (keyword/vector + flagged fallback)
│   │   ├── reindex.py                           # the single idempotent re-index routine (Reindexer)
│   │   └── locks.py                             # StoreLocks — per-store write serialization
│   └── knowledge_base/
│       ├── kind.py                              # make_kb_kind(...): Kind with on_delete
│       ├── service.py                           # KnowledgeBaseService: list/read/search/grep/metrics + mode validation
│       ├── pipeline.py / pipeline_helpers.py    # ingest / edit / reconvert / reindex write pipeline
│       └── builtin_tools.py                     # the 4 read-only coffer__*_knowledge MCP tools
├── infrastructure/
│   └── knowledge/                               # (shared) substrate infra — engine confinement boundary
│       ├── converters/
│       │   ├── markitdown_converter.py          # default engine; ONLY importer of markitdown
│       │   ├── passthrough_converter.py         # md / txt / source code
│       │   ├── csv_converter.py                 # csv → markdown table
│       │   └── registry.py                      # format → converter dispatch (passthrough → csv → markitdown)
│       ├── cleaning.py                          # whitespace / control-char / heading normalization
│       ├── frontmatter.py                       # YAML frontmatter prepend/parse
│       ├── chunking.py                          # markdown-aware chunker
│       ├── models.py / ddl.py / ids.py          # ORM models, documents_fts DDL hook, id helpers
│       ├── repository.py                        # DocumentRepo (document-row CRUD)
│       ├── sqlite_index.py                      # SqliteKnowledgeIndex — chunks + FTS5 (bm25)
│       ├── vec_index.py                         # VecIndex; ONLY importer of sqlite_vec (lazy per-store vec tables)
│       ├── embeddings.py                        # OpenAI-compatible + local fastembed; ONLY importer of openai/fastembed
│       ├── grep.py                              # ripgrep subprocess wrapper (bounded; truncated flag)
│       └── paths.py                             # ~/.coffer/knowledge/<name>/{docs,raw} layout helpers
└── surfaces/
    ├── http/knowledge_base/
    │   ├── routes.py                            # /api/v1/knowledge_bases/* (create/list/get/ingest/docs/edit/reconvert/delete/reindex/search/grep/metrics)
    │   └── schemas.py
    └── cli/knowledge_base_cmd.py                # coffer kb create/ingest/list-docs/get-doc(read)/edit/reconvert/reindex/search/grep/set-embedding/set-chunking/delete-doc/delete-kb/describe
```

Existing files modified (intersection with spec 007 — land in the same redesign PR):

- `backend/coffer/surfaces/http/app.py` — wire the KB kind + routers in lifespan.
- `backend/coffer/surfaces/cli/main.py` — `app.add_typer(knowledge_base_cmd.app, name="kb")`.
- `backend/coffer/application/mcp/gateway.py` + `gateway_builtin.py` — route the four `coffer__*_knowledge` tools (registered by `application/knowledge_base/builtin_tools.py`) to the built-in handler.
- `backend/coffer/infrastructure/persistence/migrations/env.py` — import the unified `documents`/`chunks` ORM.
- `backend/pyproject.toml` — swap deps (drop LlamaIndex/chroma/mem0, add markitdown/sqlite-vec/openai/fastembed) + new importlinter contracts.
- `frontend/src/kinds.ts` — register `KNOWLEDGE_BASE_KIND_UI`.

### Frontend

```text
frontend/src/kinds/knowledge_base/
├── index.tsx                 # KNOWLEDGE_BASE_KIND_UI (DataTable row + DetailPage + addPath)
├── KnowledgeBaseForm.tsx     # name, description, enabled modes, chunk params, embedding provider
├── KnowledgeBaseDetailPage.tsx
├── DocumentTable.tsx         # shared DataTable; source_mode badge
├── DocumentViewer.tsx        # read-only Markdown render + open-in-editor / reveal / copy-path
├── UploadDropzone.tsx
├── SearchPanel.tsx           # mode selector (grep/keyword/vector) + results
└── schema.ts
```

### Tests

```text
backend/tests/
├── unit/knowledge_base/
│   ├── test_config_validation.py
│   ├── test_chunking.py
│   ├── test_cleaning.py
│   ├── test_converter_registry.py
│   └── test_kb_service_with_fakes.py            # FakeMarkdownConverter + FakeEmbedder
├── integration/knowledge_base/
│   ├── test_kb_lifecycle.py                     # create → ingest → search → edit → reindex → delete (acceptance)
│   ├── test_retrieval_modes.py                  # grep / keyword / vector + vector fallback (acceptance)
│   ├── test_reindex_idempotency.py
│   ├── test_mcp_builtin_tools.py                # list/search/grep/read via the gateway
│   ├── test_http_routes.py
│   └── test_markitdown_real.py                  # importorskip markitdown; convert a real docx/pdf
└── contract/
    └── test_kb_openapi.py                        # OpenAPI dump matches contracts/api.openapi.yaml
```

## Phase 1 — Spec & contract (this PR's first commits)

1. spec.md ✅ rewritten before any code.
2. data-model.md — unified `documents`/`chunks` schema, FTS5 + sqlite-vec, ports, on-disk layout.
3. contracts/api.openapi.yaml — REST surface with the app-wide error envelope.
4. research.md — converter, retrieval-stack, and embedding-provider decisions (supersedes ADR-010/011).

## Phase 2 — Substrate (TDD, shared with 007)

Order: domain value objects + ports → migration (`documents`/`chunks`/FTS5/sqlite-vec) → `sqlite_index` + `vec_index` repos → converter registry + cleaning + frontmatter + chunking → embedders → grep wrapper → the single `reindex` routine.

## Phase 3 — KB application + surfaces (TDD)

For each acceptance scenario: failing test in the right tier with the acceptance marker → minimal code → small commit. Order: `KnowledgeBaseConfig` → `KnowledgeBaseService` + the ingest/edit/reconvert pipeline → `make_kb_kind` (on_delete) → HTTP routes (incl. `reconvert`) → CLI → the four built-in MCP tools → composition-root wiring.

## Phase 4 — Frontend

`KnowledgeBaseForm` (zod mirrors `KnowledgeBaseConfig`) → `KnowledgeBaseDetailPage` (DocumentTable + UploadDropzone + read-only DocumentViewer with open-in-editor / reveal / copy-path + SearchPanel with mode selector) → register `KNOWLEDGE_BASE_KIND_UI` → one test per UI acceptance scenario.

## Phase 5 — Verification

`make lint` (importlinter contracts) → `make verify-unit` (purity guardrail) → `make verify-integration` → `make verify-contract` (OpenAPI) → `make verify-acceptance` → final commit.

## Importlinter contracts to add / amend

- **Extend Contract 5** (cross-kind imports forbidden): add `coffer.{application,surfaces.http}.knowledge_base`; forbid them from importing the `memory` kind's siblings.
- **Extend Contract 6** (kind-agnostic core ↛ kind-specific): add the `knowledge_base` modules to `forbidden_modules`.
- **New Contract 7** (engine confinement): `coffer.application.*` and `coffer.domain.*` MUST NOT import `markitdown`, `docling`, `sqlite_vec`, `openai`, or `fastembed` — only `coffer.infrastructure.knowledge.*` may. This supersedes the old "no `llama_index`" rule.
- The shared `coffer.{domain,infrastructure}.knowledge` substrate is kind-agnostic (used by both KB and memory) and is therefore NOT subject to the cross-kind forbid.

## Risks & mitigations

| Risk                                                | Mitigation                                                                                                                                                                                 |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MarkItDown conversion fidelity for PDFs (open item) | Converter behind a port + per-format registry; a future swap or a higher-fidelity per-format engine is a new converter under `infrastructure/knowledge/converters/` only.                  |
| sqlite-vec packaging/loading on macOS arm64 + Linux | `vec_index.py` is the only loader; integration test guards with `pytest.importorskip`; vector mode is opt-in so a load failure degrades to keyword (FR-012), it does not block the daemon. |
| Embedding API cost/latency/availability             | Default is keyword+grep (no embedding). Vector requested without config falls back to keyword, flagged. Outbound calls go through the SSRF-guarded client with a timeout.                  |
| Local embedding model quality for Chinese           | Recommend `bge-m3` (fastembed) or a cloud provider for bilingual corpora; documented in quickstart.                                                                                        |
| Converter library missing at runtime                | Per-format `EngineUnavailable` naming the missing dep; other formats still ingest; daemon stays up.                                                                                        |
| Re-chunk/re-embed cost when params change           | Files are the source of truth, so the single reindex routine re-derives cheaply; `content_sha256` no-op skips unchanged docs.                                                              |

## Out of scope (deferred)

- Reranking, multi-query expansion, HyDE, LLM synthesis on retrieval (the agent synthesizes).
- ~~Agents editing KB documents~~ — **shipped** via the co-management amendment (ADR-028, above).
- Per-project KB document scope, recoverable soft-delete, and an in-app Markdown editor — deferred to the unified-知识 UI slice (see the amendment).
- Hybrid (RRF) fusion of keyword+vector in one call — listed as optional in the design; ships behind the same port if added.
- Image OCR / audio transcription by default.
- A filesystem watcher on by default.
- Multi-machine sync (constitutional).

The port surface (converter / embedder / index) is intentionally minimal so any of these is a new adapter, not a re-modelling.
