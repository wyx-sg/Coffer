# Tasks — 007 Memory (Shared Agent Memory)

Redesign on `feature/kb-memory-redesign`. Spec-first, then code. Memory is the
memory face of the unified knowledge substrate (shared with spec 006); tasks
marked **[shared]** are delivered by the substrate and reused here.

## Phase 1 — Spec docs

- [x] T-0001 Rewrite spec.md / spec.zh.md to the redesign (shared single source of truth, two-layer scope, lazy reindex-on-read)
- [x] T-0002 Rewrite plan.md / plan.zh.md, data-model.md / data-model.zh.md, research.md / research.zh.md, quickstart.md / quickstart.zh.md
- [x] T-0003 Rewrite contracts/api.openapi.yaml (facts + recall; app-wide error envelope)
- [x] T-0004 Commit `docs(007-memory): redesign spec — shared agent memory`

## Phase 2 — Migration (no data migration)

- [x] T-0010 Alembic revision: drop `memory_records`; delete chroma/LlamaIndex dirs; create unified `documents` / `chunks` / `documents_fts` **[shared]**. The per-store sqlite-vec `vec_chunks` tables are NOT created in the migration — `vec_index.py` creates them lazily at the configured width.
- [x] T-0011 Drop `mem0ai` + `chromadb` from `pyproject.toml`; add `sqlite-vec`, `fastembed`, `PyYAML` **[shared]**

## Phase 3 — Backend domain

- [x] T-0020 `domain/knowledge/document.py` — Document entity (kind-discriminated) **[shared]**
- [x] T-0021 `domain/knowledge/retrieval.py` (StoreRef / Passage / GrepHit / GrepResult / MemoryHit / SearchResult / RetrievalMode) + `domain/knowledge/index.py` (KnowledgeIndex / GrepPort / RetrievalPort) **[shared]**
- [x] T-0022 `domain/memory/config.py` — MemoryStoreConfig (retrieval modes, flat embedding fields incl. `embedding_dimensions`, max_fact_chars)
- [x] T-0023 `domain/memory/fact.py` — MemoryFact value object
- [x] T-0024 `domain/memory/scope.py` — MemoryScope + ResolvedScope
- [x] T-0025 Extend `domain/errors.py`: MemoryStoreNotFound, MemoryNotFound, MemoryRejected, ScopeUnresolved (re-exported via `domain/knowledge/errors.py`)

## Phase 4 — Backend infrastructure

- [x] T-0030 `infrastructure/knowledge/repository.py` + `sqlite_index.py` + `vec_index.py` — documents/chunks/FTS5/vec repos (`vec_index.py` is the sole `sqlite_vec` importer; lazy per-store vec tables) **[shared]**
- [x] T-0031 `infrastructure/knowledge/embeddings.py` — OpenAI-compatible providers + fastembed local **[shared]**
- [x] T-0032 `infrastructure/memory/paths.py` — `~/.coffer/memory/{global,projects/<ulid>}`
- [x] T-0033 `infrastructure/memory/files.py` — per-fact `.md` read/write, `MEMORY.md` render, dir delta scan

## Phase 5 — Backend application

- [x] T-0040 `application/memory/scope.py` — `ScopeResolver`: cwd → git-root → project ULID → store (lazy provision); global sentinel; store-name validation (`global` | `project-<26-char ULID>`)
- [x] T-0041 `application/memory/service.py` (+ `writes.py` / `queries.py` / `recall.py` / `sync.py`) — remember / recall (lazy reindex-on-read + RRF cross-store merge) / update / forget / list / clear over the knowledge-lane inbox
- [x] T-0043 `application/memory/kind.py` — make_memory_kind(...)

## Phase 7 — MCP built-in tools (shared file with KB)

- [x] T-0060 `application/memory/builtin_tools.py` — register `coffer__recall` (response carries the `fallback` boolean), `coffer__remember`, `coffer__list_memory`, `coffer__set_handoff`, `coffer__resume` with the MCP gateway's builtin registry
- [x] T-0061 Scope resolution from the shim's reported cwd at session handshake
- [x] T-0062 Integration test: `test_mcp_builtin_memory_tools.py`

## Phase 8 — Surfaces

- [x] T-0070 `surfaces/http/memory/schemas.py` + `routes.py` — `/api/v1/memory_stores/*` (facts, recall)
- [x] T-0071 `surfaces/cli/memory_cmd.py` — `coffer memory list/describe/add/facts/get/edit/delete/clear/configure/recall`
- [x] T-0072 `surfaces/http/app.py` — `_wire_memory_kind(...)`; `surfaces/cli/main.py` — register `memory` typer

## Phase 9 — Frontend

- [x] T-0080 `frontend/src/kinds/memory/schema.ts` + `api.ts` / `types.ts`
- [x] T-0081 `frontend/src/pages/MemoryPage.tsx` (stores table) + `MemoryStoreDetailPage.tsx` (per-store detail page, route `/memory/:name`)
- [x] T-0082 `MemoryFactList.tsx`, `MemoryAddFactForm.tsx`, `MemoryRecallPanel.tsx`, `MemoryMetricsHeader.tsx`
- [x] T-0083 `index.tsx` (MEMORY_KIND_UI); register in `frontend/src/kinds.ts`
- [x] T-0084 Frontend tests
- [ ] T-0085 Read-only-UI pivot: replace `MemoryAddFactForm.tsx` (in-app add/edit) with a read-only `MemoryFactViewer.tsx` (renders fact content; no in-app content editing). Add open-in-editor / reveal affordances for the fact file and its containing folder (desktop via the Tauri opener; web via the loopback daemon, spec 004 FR-039), driven by `FactOut.path`/`folder_path` and `MemoryStoreOut.store_dir`, using the global preferred-editor preference (002-ui-shell). Rename `FactEditor.test.tsx` → `FactViewer.test.tsx`. (FR-021/FR-022, US4.)

## Phase 10 — Tests

- [x] T-0090 Unit: config / fact-frontmatter-roundtrip / MEMORY.md regeneration / scope resolver
- [x] T-0091 Integration: remember→recall (keyword/vector-fake/grep) / lazy-reindex-on-read / two-layer scope
- [x] T-0092 Contract: OpenAPI conformance
- [x] T-0093 Importlinter: index engine confined to infrastructure; `mem0`/`chroma`/`llama_index` imported nowhere

## Phase 11 — Verification

- [x] T-0100 `make verify-acceptance` (every spec.md scenario has a covering marker)
- [x] T-0101 `make verify-unit` / `-integration` / `-contract`
- [x] T-0102 `make lint`
- [x] T-0103 Final commit + push; open PR

## Phase 12 — STOP

- [x] T-0110 PR opened; independent review.
