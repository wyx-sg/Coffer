# Implementation Plan: 007 — Memory (Shared Agent Memory)

> 中文版: [plan.zh.md](./plan.zh.md)

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted (redesign — in development)

## Summary

Memory is the **memory face** of one unified knowledge substrate shared with the knowledge base (spec 006). Each memory scope is a Resource of kind `memory`. Facts are per-fact markdown files (YAML frontmatter + body) plus a regenerated `MEMORY.md` index under `~/.coffer/memory/`. **Files are the source of truth; SQLite (`documents` + FTS5 + sqlite-vec) is a rebuildable index.** There are two scopes: global (sentinel ULID) and per-project (project ULID resolved from the agent's working directory).

No LLM runs at write time — the agent writes a clean fact directly. Every agent reads and writes memory **only through Coffer's MCP gateway** (`coffer__recall/remember/list_memory/set_handoff/resume`); Coffer keeps its own canonical format and **does not touch agents' native memory files** (native projection was removed — see ADR-026). The user does full CRUD through the CLI/REST write surface; the Coffer UI is a **read-only** viewer that offers open-in-editor / reveal for each fact and its folder (curation happens in the user's own editor, picked up by lazy reindex-on-read).

This redesign **drops mem0, chroma, and LlamaIndex** and replaces `memory_records` with the unified `documents` table. There is no data migration (branch unreleased).

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                      |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x                                                                                                                                                                                               |
| **Primary Dependencies (added by this spec)** | Shared with KB: `sqlite-vec` (vector index), `fastembed` (optional local embeddings), `PyYAML` (frontmatter). Cloud embeddings via the existing OpenAI-compatible provider abstraction. **Removed:** `mem0ai`, `chromadb`. |
| **Storage**                                   | Markdown facts under `~/.coffer/memory/global/` and `~/.coffer/memory/projects/<project-ulid>/`; index rows in `~/.coffer/coffer.db` (`documents`, `chunks`, `documents_fts`, `vec_chunks`).                               |
| **Testing**                                   | 4-tier model with acceptance markers. `FakeEmbeddingProvider` for vector paths; keyword/grep need no embeddings.                                                                                                           |
| **Performance Goals**                         | SC-003: ≤ 300 ms keyword recall on a 200-fact scope.                                                                                                                                                                       |
| **Constraints**                               | Index engine confined to `coffer.infrastructure.knowledge.*` (importlinter); daemon starts even if the vector backend fails to load; `mem0`/`chroma`/`llama_index` imported nowhere.                                       |
| **Scale / Scope**                             | Single user; one global store + one store per active project; facts are short (default ≤ 8192 chars).                                                                                                                      |

## Constitution Check

Same layer rules as KB (one substrate). The memory kind reuses the shared retrieval engine, repository, and converters; only the memory-specific service (per-fact write, `MEMORY.md` regeneration, scope resolution) is memory-specific. Engine isolation and the cross-kind import bans extend symmetrically. The `WORKSPACE_GLOBAL_PROJECT_ID` sentinel is reused, not re-minted.

## Project Structure

```text
backend/coffer/
├── domain/
│   ├── errors.py                        # canonical hierarchy: MemoryStoreNotFound, MemoryNotFound, MemoryRejected, ScopeUnresolved, ...
│   ├── knowledge/                       # shared substrate (KB + memory) — see spec 006
│   │   ├── document.py                  # Document entity (kind-discriminated)
│   │   ├── retrieval.py                 # StoreRef, Passage, GrepHit/GrepResult, MemoryHit, SearchResult, RetrievalMode
│   │   ├── index.py                     # KnowledgeIndex / GrepPort / RetrievalPort protocols
│   │   └── errors.py                    # re-exports of the substrate errors (canonical classes in domain/errors.py)
│   └── memory/
│       ├── config.py                    # MemoryStoreConfig (retrieval modes, flat embedding fields, max_fact_chars)
│       ├── fact.py                      # MemoryFact (frontmatter + body) value object
│       └── scope.py                     # MemoryScope (GLOBAL | PROJECT) + ResolvedScope
├── application/
│   ├── knowledge/                       # shared substrate application layer (spec 006)
│   │   ├── retrieval.py                 # KnowledgeRetrieval facade (keyword/vector + flagged fallback)
│   │   ├── reindex.py                   # the single idempotent re-index routine (Reindexer)
│   │   └── locks.py                     # StoreLocks — per-store write serialization
│   ├── memory/
│   │   ├── kind.py                      # make_memory_kind(...)
│   │   ├── service.py / service_helpers.py  # remember/recall/update/forget/list/clear over the knowledge-lane inbox
│   │   ├── writes.py / queries.py       # fact write/read paths
│   │   ├── recall.py                    # recall orchestration + reciprocal-rank-fusion merge
│   │   ├── scope.py                     # ScopeResolver: cwd → git-root → project ULID → store (lazy provision); store-name validation
│   │   ├── stores.py                    # store-name ↔ ResolvedScope helpers
│   │   ├── sync.py                      # MemoryReconciler — lazy reindex-on-read
│   │   └── builtin_tools.py             # the five coffer__* memory MCP tools
├── infrastructure/
│   ├── knowledge/                       # shared substrate infra (spec 006): repository.py, sqlite_index.py,
│   │   …                                # vec_index.py (sole sqlite_vec importer), embeddings.py, grep.py,
│   │                                    # chunking.py, cleaning.py, frontmatter.py, paths.py, converters/
│   └── memory/
│       ├── files.py                     # per-fact .md read/write, MEMORY.md render, dir scan (deltas)
│       ├── paths.py                     # ~/.coffer/memory/{global,projects/<ulid>}
│       ├── scope_fs.py                  # filesystem scope helpers
│       └── project_root_repo.py         # project-root persistence (readable per-project store identity, FR-017a)
└── surfaces/
    ├── http/memory/                     # /api/v1/memory_stores/* (facts, recall)
    └── cli/memory_cmd.py                # `coffer memory ...`
```

Existing files modified:

- `application/mcp/gateway.py` / `gateway_builtin.py` — route the five memory tools (registered by `application/memory/builtin_tools.py`) alongside the KB tools.
- `surfaces/http/app.py` — `_wire_memory_kind(...)`.
- `surfaces/cli/main.py` — `app.add_typer(memory_cmd.app, name="memory")`.
- `infrastructure/persistence/migrations/` — one revision: drop `memory_records`, delete chroma/LlamaIndex dirs, create unified schema.
- `backend/pyproject.toml` — drop `mem0ai`/`chromadb`; add shared substrate deps; new importlinter contract.
- `frontend/src/kinds.ts` — register `MEMORY_KIND_UI`.

## Frontend

```text
frontend/src/pages/MemoryPage.tsx        # stores table (auto-provisioned; no "New store" action)
frontend/src/kinds/memory/
├── index.tsx                            # MEMORY_KIND_UI
├── MemoryStoreDetailPage.tsx            # per-store detail page (route /memory/:name)
├── MemoryFactList.tsx                   # DataTable (name, description, type, actor, updated)
├── MemoryFactViewer.tsx                 # read-only fact render + open-in-editor / reveal (file + folder)
├── MemoryRecallPanel.tsx                # recall box with mode selector (keyword default)
├── MemoryMetricsHeader.tsx              # fact count + disk bytes
├── api.ts / types.ts
└── schema.ts
```

## Tests

```text
backend/tests/
├── unit/memory/
│   ├── test_config_validation.py
│   ├── test_fact_frontmatter_roundtrip.py
│   ├── test_memory_md_regeneration.py        # idempotent, derived from frontmatter
│   └── test_scope_resolver.py                # cwd → git-root → ULID; global sentinel
├── integration/memory/
│   ├── test_remember_recall_roundtrip.py     # keyword + vector(fake) + grep
│   ├── test_lazy_reindex_on_read.py          # out-of-band edit visible on next recall
│   ├── test_two_layer_scope.py               # project + global; cross-project isolation
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   └── test_cli_memory_cmd.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── FactList.test.tsx
├── FactViewer.test.tsx                       # read-only render + open/reveal affordances
└── RecallBox.test.tsx
```

## Importlinter contracts (added or amended)

- **Extend cross-kind contract**: `coffer.{domain,application,...}.memory` must not import `mcp` or `knowledge_base` and vice versa (the shared `knowledge` substrate is allowed for both KB and memory).
- **New substrate-confinement contract**: `coffer.application.*` and `coffer.domain.*` MUST NOT import the index engine (`sqlite_vec`, FTS5 helpers, embedding SDKs); only `coffer.infrastructure.knowledge.*` may. `mem0`, `chromadb`, and `llama_index` MUST NOT be imported anywhere.

## Risks & mitigations

| Risk                                                                     | Mitigation                                                                                                                                                                                                         |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MCP shim cwd does not propagate on some agent (scope resolution fails)   | Open item #1 in [research.md](./research.md) (§11); verify on Claude/Codex during impl. An unresolved project scope is REJECTED with `ScopeUnresolved` (clear error; nothing written); `scope=global` still works. |
| A fact file or `MEMORY.md` is edited out of band (e.g. directly on disk) | `MEMORY.md` is a derived index regenerated idempotently; lazy reindex-on-read reconciles fact deltas by content hash — no watcher.                                                                                 |
| sqlite-vec packaging/loading on macOS arm64 / Linux                      | Open item #2 in [research.md](./research.md) (§11); default retrieval is keyword+grep (no native ext needed); vector is opt-in and degrades gracefully when the ext is absent.                                     |
| Embedding model embeds Chinese poorly                                    | Default is keyword+grep (language-agnostic); recommend local `bge-m3` or a cloud provider for bilingual vector recall.                                                                                             |

## Out of scope (deferred)

- Reranking / HyDE / multi-query / LLM synthesis on recall (the agent synthesizes).
- Native projection into agents' own memory surfaces (symlink / managed block); agents access memory only through the MCP tools (native projection was removed — see ADR-026).
- Multi-machine sync (constitutional).
- Filesystem watcher on by default (memory uses lazy reindex-on-read instead).
- Memory categories beyond `metadata.type` free-form tagging.
