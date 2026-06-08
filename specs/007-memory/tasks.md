# Tasks — 007 Memory (Shared Agent Memory)

Redesign on `feature/kb-memory-redesign`. Spec-first, then code. Memory is the
memory face of the unified knowledge substrate (shared with spec 006); tasks
marked **[shared]** are delivered by the substrate and reused here.

## Phase 1 — Spec docs

- [x] T-0001 Rewrite spec.md / spec.zh.md to the redesign (shared single source of truth, two-layer scope, projection, lazy reindex-on-read)
- [x] T-0002 Rewrite plan.md / plan.zh.md, data-model.md / data-model.zh.md, research.md / research.zh.md, quickstart.md / quickstart.zh.md
- [x] T-0003 Rewrite contracts/api.openapi.yaml (facts + recall + projection; app-wide error envelope)
- [ ] T-0004 Commit `docs(007-memory): redesign spec — shared agent memory`

## Phase 2 — Migration (no data migration)

- [ ] T-0010 Alembic revision: drop `memory_records`; delete chroma/LlamaIndex dirs; create unified `documents` / `chunks` / `documents_fts` / `vec_chunks` **[shared]**
- [ ] T-0011 Drop `mem0ai` + `chromadb` from `pyproject.toml`; add `sqlite-vec`, `fastembed`, `PyYAML` **[shared]**

## Phase 3 — Backend domain

- [ ] T-0020 `domain/knowledge/document.py` — Document / Chunk / Hit / SearchResult value objects **[shared]**
- [ ] T-0021 `domain/knowledge/retrieval.py` — RetrievalPort + RetrievalMode **[shared]**
- [ ] T-0022 `domain/memory/config.py` — MemoryStoreConfig (retrieval modes, embedding, max_fact_chars)
- [ ] T-0023 `domain/memory/fact.py` — MemoryFact value object
- [ ] T-0024 `domain/memory/scope.py` — MemoryScope + ResolvedScope
- [ ] T-0025 Extend `domain/knowledge/errors.py`: MemoryNotFound, MemoryRejected, ScopeUnresolved

## Phase 4 — Backend infrastructure

- [ ] T-0030 `infrastructure/knowledge/index.py` — documents/chunks/FTS5/vec repo (sole index-engine importer) **[shared]**
- [ ] T-0031 `infrastructure/knowledge/embeddings/` — OpenAI-compatible providers + fastembed local **[shared]**
- [ ] T-0032 `infrastructure/memory/paths.py` — `~/.coffer/memory/{global,projects/<ulid>}`
- [ ] T-0033 `infrastructure/memory/files.py` — per-fact `.md` read/write, `MEMORY.md` render, dir delta scan

## Phase 5 — Backend application

- [ ] T-0040 `application/memory/scope_resolver.py` — cwd → git-root → project ULID → store (lazy provision); global sentinel
- [ ] T-0041 `application/memory/service.py` — remember / recall (lazy reindex-on-read) / update / forget / list / clear + MEMORY.md regen
- [ ] T-0042 `application/memory/projection.py` — projection engine dispatch on AgentMemoryAdapter.projection_mode
- [ ] T-0043 `application/memory/kind.py` — make_memory_kind(...)

## Phase 6 — Agent projection adapters (with the agent driver)

- [ ] T-0050 `agents/adapters/base.py` — AgentMemoryAdapter protocol
- [ ] T-0051 `agents/adapters/claude.py` — SYMLINK into `~/.claude/projects/<slug>/memory/`; merge-existing-files-then-symlink
- [ ] T-0052 `agents/adapters/codex.py` — RENDER marker-fenced managed block into AGENTS.md; disable native `memories`

## Phase 7 — MCP built-in tools (shared file with KB)

- [ ] T-0060 Extend `application/mcp/builtin_tools.py` with `coffer__recall`, `coffer__remember`, `coffer__update_memory`, `coffer__forget`, `coffer__list_memory`
- [ ] T-0061 Scope resolution from the shim's reported cwd at session handshake
- [ ] T-0062 Integration test: `test_mcp_builtin_memory_tools.py`

## Phase 8 — Surfaces

- [ ] T-0070 `surfaces/http/memory/schemas.py` + `routes.py` — `/api/v1/memory_stores/*` (facts, recall, projections)
- [ ] T-0071 `surfaces/cli/memory_cmd.py` — `coffer memory add/list/recall/edit/forget/clear/configure/describe`
- [ ] T-0072 `surfaces/http/app.py` — `_wire_memory_kind(...)`; `surfaces/cli/main.py` — register `memory` typer

## Phase 9 — Frontend

- [ ] T-0080 `frontend/src/kinds/memory/schema.ts`
- [ ] T-0081 `MemoryStoreDetailPage.tsx` (Global | Project scope tabs)
- [ ] T-0082 `FactList.tsx`, `FactEditor.tsx`, `RecallBox.tsx`
- [ ] T-0083 `index.tsx` (MEMORY_KIND_UI); register in `frontend/src/kinds.ts`
- [ ] T-0084 Frontend tests

## Phase 10 — Tests

- [ ] T-0090 Unit: config / fact-frontmatter-roundtrip / MEMORY.md regeneration / scope resolver / projection dispatch
- [ ] T-0091 Integration: remember→recall (keyword/vector-fake/grep) / lazy-reindex-on-read / two-layer scope / projection symlink (Claude) / projection render (Codex)
- [ ] T-0092 Contract: OpenAPI conformance
- [ ] T-0093 Importlinter: index engine confined to infrastructure; `mem0`/`chroma`/`llama_index` imported nowhere

## Phase 11 — Verification

- [ ] T-0100 `make verify-acceptance` (every spec.md scenario has a covering marker)
- [ ] T-0101 `make verify-unit` / `-integration` / `-contract`
- [ ] T-0102 `make lint`
- [ ] T-0103 Final commit + push; open PR

## Phase 12 — STOP

- [ ] T-0110 PR opened; independent review.
