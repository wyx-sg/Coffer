# Research — 007 Memory Manager

## 1. Memory framework

**Question**: Which Python library is Coffer's backbone for long-term agent memory?

**Candidates**:

| Library                                  | Strengths                                                                                                     | Risks for Coffer                                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **mem0**                                 | Industry-mainstream (~24k stars); purpose-built memory framework; clean `add/search/delete` API; LLM-agnostic | Default config points at OpenAI; the user must opt into local Ollama; API has shifted slightly across versions |
| LangMem                                  | Official LangChain memory lib; great fit if everything is LangChain                                           | Locks Coffer into the LangChain ecosystem prematurely; less standalone usage than mem0                         |
| Letta (formerly MemGPT)                  | Strong research credibility                                                                                   | A full agent framework, not just memory; collides with the future LangGraph choice                             |
| Zep self-host                            | Production-grade with UI                                                                                      | Requires Postgres; heavy ops surface for a local-first single-user app                                         |
| LangGraph checkpointer                   | Same ecosystem as future agent                                                                                | Designed for in-conversation state, not durable cross-session memory                                           |
| Build our own (vector DB + facts schema) | Maximum control                                                                                               | Reinventing what mem0 already does                                                                             |

**Decision**: **mem0** (`mem0ai`). It is the most mainstream framework purpose-built for agent memory, matching the user's project-wide "industry mainstream" principle. The lock-in is contained by:

1. mem0 confined to `coffer.infrastructure.memory.mem0_store.py`; importlinter contract 8 enforces it.
2. The `MemoryStore` port exposes `add / search / list / get / update / delete / clear`. Returned types are Coffer's `MemoryRecord` / `MemoryHit`, not mem0's `Memory` objects.

## 2. LLM provider

mem0 calls an LLM at write time to extract facts. Coffer's local-first invariant means the default cannot be a cloud API.

**Decision**:

- Configurable per memory store (`MemoryStoreConfig.llm_provider`):
  - `none` (default) — read paths work, `add_memory` returns 503 with a setup pointer.
  - `ollama` — local; uses `http://localhost:11434` by default; model name configurable.
  - `openai` — cloud; uses `OPENAI_API_KEY` from the OS keychain via Coffer's existing credentials mechanism.
- Switching providers post-creation is disallowed for the same reason embedding-model swap is disallowed in KBs (consistency of stored facts).

## 3. Embedding model

mem0 also embeds memories for retrieval. We reuse the same default as KB (`BAAI/bge-small-en-v1.5`) for stylistic consistency and to share the HF cache. mem0's vector store backend defaults to `qdrant`/`chroma`; we explicitly configure mem0 to use a local file-backed store (mem0 supports a SQLite + faiss / chromadb-in-memory mode through its `vector_store` config).

**Decision**: Embedding model = `BAAI/bge-small-en-v1.5` (default; per-store configurable). Vector backend = mem0's built-in `chromadb` configured to persist under `~/.coffer/memory/<store-name>/chroma/`. This keeps every memory store self-contained on disk.

## 4. Per-store scoping (mem0's `user_id`)

mem0's API requires a `user_id` on every call. In Coffer (single-user) we map that field to the memory store's name. Every `add` / `search` / `delete` against store `<name>` passes `user_id=<name>` to mem0 internally. The port hides this entirely; `MemoryStore.add(memory_store_name, text, actor)` is the public surface.

## 5. Editing memories

mem0 supports `Memory.update(memory_id, data=...)`. Coffer's port exposes a `update(store_name, memory_id, new_text)`; the adapter calls mem0's update and re-embeds. Audit records the before/after text.

## 6. `Tracer` port promotion

Spec 006 (knowledge_base) introduces a tracer port inside `application/knowledge_base/`. Spec 007 (memory) needs the same trace surface for `add` / `search` / `edit` / `delete` operations. Per the constitution's "extract cross-cutting after the second feature needs it" rule, this spec **promotes** the tracer port from `application/knowledge_base/tracer.py` to `application/observability/tracer.py`. KB's existing imports update accordingly. The change is mechanical and happens in one commit.

## 7. Built-in MCP tools

Four tools, namespaced under `coffer__`:

- `coffer__list_memory_stores()` → `[ {name, description, memory_count, embedding_model}, ... ]`
- `coffer__add_memory(store: str, text: str)` → `{ memory_id, text, status }`
- `coffer__search_memory(store: str, query: str, top_k: int = 5)` → `[ {id, text, score, created_at}, ... ]`
- `coffer__delete_memory(store: str, memory_id: str)` → `{ deleted: bool }`

Invocations are recorded in `mcp_invocations` the same way KB tools and upstream-server tools are; `resource_name` is the sentinel `"coffer"`.

## 8. What we are NOT doing in this spec

- Memory consolidation runs (mem0's "process" step).
- Cross-store search.
- Memory categories / tags.
- Time-decay scoring.
- Multi-actor scoping beyond `actor in {"agent", "user"}`.

Each is a clean future spec.
