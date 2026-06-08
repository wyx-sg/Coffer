# Implementation Plan: 007 — Memory (Shared Agent Memory)

> 中文版: [plan.zh.md](./plan.zh.md)

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.md](./spec.md)
**Status**: Draft (redesign)

## Summary

Memory is the **memory face** of one unified knowledge substrate shared with the knowledge base (spec 006). Each memory scope is a Resource of kind `memory`. Facts are per-fact markdown files (YAML frontmatter + body) plus a regenerated `MEMORY.md` index — Claude Code's auto-memory format — under `~/.coffer/memory/`. **Files are the source of truth; SQLite (`documents` + FTS5 + sqlite-vec) is a rebuildable index.** There are two scopes: global (sentinel ULID) and per-project (project ULID resolved from the agent's working directory).

No LLM runs at write time — the agent writes a clean fact directly. Sharing is hybrid: every agent reads/writes through Coffer's MCP gateway (`coffer__recall/remember/update_memory/forget/list_memory`), and the canonical files are **projected** into each agent's native location by an `AgentMemoryAdapter` (Claude Code = directory symlink; Codex = marker-fenced managed block in `AGENTS.md` with native `memories` disabled). The user does full CRUD in the Coffer UI/CLI.

This redesign **drops mem0, chroma, and LlamaIndex** and replaces `memory_records` with the unified `documents` table. There is no data migration (branch unreleased).

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                      |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x                                                                                                                                                                                               |
| **Primary Dependencies (added by this spec)** | Shared with KB: `sqlite-vec` (vector index), `fastembed` (optional local embeddings), `PyYAML` (frontmatter). Cloud embeddings via the existing OpenAI-compatible provider abstraction. **Removed:** `mem0ai`, `chromadb`. |
| **Storage**                                   | Markdown facts under `~/.coffer/memory/global/` and `~/.coffer/memory/projects/<project-ulid>/`; index rows in `~/.coffer/coffer.db` (`documents`, `chunks`, `documents_fts`, `vec_chunks`).                               |
| **Testing**                                   | 4-tier model with acceptance markers. `FakeEmbeddingProvider` for vector paths; keyword/grep need no embeddings. Projection tested against temp `~/.claude` / `~/.codex` roots.                                            |
| **Performance Goals**                         | SC-003: ≤ 300 ms keyword recall on a 200-fact scope.                                                                                                                                                                       |
| **Constraints**                               | Index engine confined to `coffer.infrastructure.knowledge.*` (importlinter); daemon starts even if the vector backend fails to load; `mem0`/`chroma`/`llama_index` imported nowhere.                                       |
| **Scale / Scope**                             | Single user; one global store + one store per active project; facts are short (default ≤ 8192 chars).                                                                                                                      |

## Constitution Check

Same layer rules as KB (one substrate). The memory kind reuses the shared retrieval engine, repository, and converters; only the memory-specific service (per-fact write, `MEMORY.md` regeneration, scope resolution) and the projection engine are memory-specific. Engine isolation and the cross-kind import bans extend symmetrically. The `WORKSPACE_GLOBAL_PROJECT_ID` sentinel is reused, not re-minted.

## Project Structure

```text
backend/coffer/
├── domain/
│   ├── knowledge/                       # shared substrate (KB + memory) — see spec 006
│   │   ├── document.py                  # Document, Chunk, Hit value objects
│   │   ├── retrieval.py                 # RetrievalPort, RetrievalMode (grep|keyword|vector)
│   │   └── errors.py                    # MemoryNotFound, MemoryRejected, ScopeUnresolved, ...
│   └── memory/
│       ├── config.py                    # MemoryStoreConfig (retrieval modes, embedding, max_fact_chars)
│       ├── fact.py                      # MemoryFact (frontmatter + body) value object
│       └── scope.py                     # MemoryScope (GLOBAL | PROJECT) + resolution result
├── application/
│   ├── knowledge/                       # shared indexing/retrieval service (spec 006)
│   └── memory/
│       ├── kind.py                      # make_memory_kind(...)
│       ├── service.py                   # remember/recall/update/forget/list/clear + MEMORY.md regen
│       ├── scope_resolver.py            # cwd → git-root → project ULID → store (lazy provision)
│       └── projection.py                # projection engine: dispatch on AgentMemoryAdapter.projection_mode
├── infrastructure/
│   ├── knowledge/                       # FTS5 + sqlite-vec + embedding providers + converters (spec 006)
│   │   ├── index.py                     # documents/chunks/FTS5/vec repo (sole index-engine importer)
│   │   └── embeddings/                  # OpenAI-compatible providers + fastembed local
│   └── memory/
│       ├── files.py                     # per-fact .md read/write, MEMORY.md render, dir scan (deltas)
│       └── paths.py                     # ~/.coffer/memory/{global,projects/<ulid>}
└── surfaces/
    ├── http/memory/                     # /api/v1/memory_stores/*
    └── cli/memory_cmd.py                # `coffer memory ...`
```

Agent-side projection adapters live with the **agent driver** (not the memory kind):

```text
backend/coffer/.../agents/
└── adapters/
    ├── base.py                          # AgentMemoryAdapter protocol
    ├── claude.py                        # SYMLINK; ~/.claude/projects/<slug>/memory/
    └── codex.py                         # RENDER managed block; disable native `memories`
```

Existing files modified:

- `application/mcp/builtin_tools.py` — add the five memory tools alongside KB tools.
- `surfaces/http/app.py` — `_wire_memory_kind(...)`.
- `surfaces/cli/main.py` — `app.add_typer(memory_cmd.app, name="memory")`.
- `infrastructure/persistence/migrations/` — one revision: drop `memory_records`, delete chroma/LlamaIndex dirs, create unified schema.
- `backend/pyproject.toml` — drop `mem0ai`/`chromadb`; add shared substrate deps; new importlinter contract.
- `frontend/src/kinds.ts` — register `MEMORY_KIND_UI`.

## Frontend

```text
frontend/src/kinds/memory/
├── index.tsx                # MEMORY_KIND_UI
├── MemoryStoreDetailPage.tsx  # scope tabs (Global | Project)
├── FactList.tsx             # DataTable (name, description, type, actor, updated)
├── FactEditor.tsx           # add / edit-in-place (markdown body + name/description/type)
├── RecallBox.tsx            # search with mode selector (keyword default)
└── schema.ts
```

## Tests

```text
backend/tests/
├── unit/memory/
│   ├── test_config_validation.py
│   ├── test_fact_frontmatter_roundtrip.py
│   ├── test_memory_md_regeneration.py        # idempotent, derived from frontmatter
│   ├── test_scope_resolver.py                # cwd → git-root → ULID; global sentinel
│   └── test_projection_dispatch.py           # SYMLINK | RENDER | NONE; managed-block idempotency
├── integration/memory/
│   ├── test_remember_recall_roundtrip.py     # keyword + vector(fake) + grep
│   ├── test_lazy_reindex_on_read.py          # out-of-band edit visible on next recall
│   ├── test_two_layer_scope.py               # project + global; cross-project isolation
│   ├── test_projection_symlink_claude.py     # symlink + merge-existing-files
│   ├── test_projection_render_codex.py       # managed block + disable native memories
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   └── test_cli_memory_cmd.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── FactList.test.tsx
├── FactEditor.test.tsx
└── RecallBox.test.tsx
```

## Importlinter contracts (added or amended)

- **Extend cross-kind contract**: `coffer.{domain,application,...}.memory` must not import `mcp` or `knowledge_base` and vice versa (the shared `knowledge` substrate is allowed for both KB and memory).
- **New substrate-confinement contract**: `coffer.application.*` and `coffer.domain.*` MUST NOT import the index engine (`sqlite_vec`, FTS5 helpers, embedding SDKs); only `coffer.infrastructure.knowledge.*` may. `mem0`, `chromadb`, and `llama_index` MUST NOT be imported anywhere.

## Risks & mitigations

| Risk                                                                   | Mitigation                                                                                                                               |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| MCP shim cwd does not propagate on some agent (scope resolution fails) | Open item #1 in the design doc; verify on Claude/Codex during impl. Fall back to `scope=global` with a clear error when unresolved.      |
| Claude rewrites `MEMORY.md` or fact files out of band                  | `MEMORY.md` is a derived index regenerated idempotently; lazy reindex-on-read reconciles fact deltas by content hash — no watcher.       |
| Existing native memory files would be lost on first projection         | Adapter merges existing files into canonical first, then symlinks; never overwrites (FR-012).                                            |
| sqlite-vec packaging/loading on macOS arm64 / Linux                    | Open item #4; default retrieval is keyword+grep (no native ext needed); vector is opt-in and degrades gracefully when the ext is absent. |
| Embedding model embeds Chinese poorly                                  | Default is keyword+grep (language-agnostic); recommend local `bge-m3` or a cloud provider for bilingual vector recall.                   |

## Out of scope (deferred)

- Reranking / HyDE / multi-query / LLM synthesis on recall (the agent synthesizes).
- Bidirectional parsing of a proprietary agent memory format back into canonical (avoided by symlink-where-compatible + MCP elsewhere).
- Multi-machine sync (constitutional).
- Filesystem watcher on by default (memory uses lazy reindex-on-read instead).
- Memory categories beyond `metadata.type` free-form tagging.
