# Research — 006 Knowledge Base Manager

Background and rationale for the major technology choices in this spec. Each section closes with the **decision** taken; alternatives are documented so future readers know the path not taken (and why), without re-litigating it.

## 1. RAG engine library

**Question**: Which Python library is Coffer's backbone for chunking, embedding, indexing, and retrieval?

**Candidates evaluated**:

| Library                          | Type                    | Strengths                                                                         | Risks for Coffer                                                                                                                                         |
| -------------------------------- | ----------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LlamaIndex**                   | Heavy RAG framework     | Industry-mainstream (~37k stars), most documented, most loaders, swap-in backends | Refactored twice in 2024 (`Document/Node/Index/ServiceContext→Settings`); abstractions tend to leak into application code if not deliberately walled off |
| Haystack 2.x                     | Heavy RAG framework     | Pipeline/Component model cleaner than LlamaIndex                                  | Smaller community; fewer ready-made loaders                                                                                                              |
| LangChain RAG                    | Multi-purpose framework | Same ecosystem as LangGraph (future agent)                                        | Even heavier than LlamaIndex; criticised for over-abstraction                                                                                            |
| txtai                            | Lightweight all-in-one  | One import, hybrid built-in, stable API                                           | Less mainstream — weaker portfolio / resume signal                                                                                                       |
| LanceDB + fastembed              | Library combo           | Minimal deps; bypass framework lock-in                                            | Coffer would have to write its own retriever, chunker, loader glue (~200+ LOC)                                                                           |
| ChromaDB + sentence-transformers | Library combo           | Popular embedded vector DB                                                        | Hybrid (BM25 + vector) not built-in                                                                                                                      |
| sqlite-vec + FTS5                | Pure SQLite extension   | Zero new deps beyond an extension                                                 | Most code-writing required; loader and orchestration entirely ours                                                                                       |

**Decision**: **LlamaIndex (`llama-index-core`)**. The user explicitly prioritised "industry mainstream" over "fewest abstractions" so the project has clearer hiring-signal value. The lock-in concern is mitigated by:

1. Engine confined to `coffer.infrastructure.knowledge_base.llamaindex_store.py` — a single file. Importlinter contract 7 enforces it.
2. The `KnowledgeBaseStore` port expresses _Coffer's_ needs (ingest a document, list documents, search with a top-k), not LlamaIndex types. A future swap to Haystack / txtai / a custom stack rewrites this one file.
3. We pin `llama-index-core` (not the meta-package), keeping the dependency surface small.

## 2. Embedding model

**Question**: Which embedding model is the default? How is it configured?

**Candidates**:

| Model                    | Provider                                | Size    | Notes                                                                                   |
| ------------------------ | --------------------------------------- | ------- | --------------------------------------------------------------------------------------- |
| `BAAI/bge-small-en-v1.5` | HuggingFace via `sentence-transformers` | ~130 MB | Strong English retrieval at small CPU cost; default for many local RAG defaults in 2025 |
| `BAAI/bge-m3`            | HuggingFace via `sentence-transformers` | ~570 MB | Multilingual + multi-functionality (dense + sparse + multi-vector) — overkill for MVP   |
| `nomic-embed-text-v1.5`  | HuggingFace                             | ~270 MB | Long-context (8k); Apache 2.0; competitive                                              |
| `text-embedding-3-small` | OpenAI API                              | n/a     | Cloud — violates Coffer's local-first invariant by default                              |
| `mxbai-embed-large-v1`   | HuggingFace                             | ~670 MB | Higher quality, larger                                                                  |

**Decision**: Default = **`BAAI/bge-small-en-v1.5`**. Reasons:

- Smallest, fastest model with widely-accepted-good retrieval quality.
- Apache 2.0; bundled with sentence-transformers without extra license accept dialogs.
- Runs comfortably on CPU; first-load downloads from HF Hub.

The embedding model is **per-KB**, recorded in `KnowledgeBaseConfig.embedding_model`. Once set, it is immutable — swapping models would invalidate all existing chunks. A user wanting a different model recreates the KB.

We allow the user to specify _any_ HuggingFace model identifier accepted by sentence-transformers; we do not whitelist. The configuration validator only checks that the string is non-empty and (heuristically) of the form `org/name`.

## 3. Chunking strategy

**Question**: How is text split into chunks before embedding?

**Decision**: Use LlamaIndex's `SentenceSplitter` with `chunk_size=512` tokens and `chunk_overlap=64` tokens as defaults. Both values are configurable per KB.

Rationale:

- 512 tokens at the default model's 512-token max window keeps chunks meaningful but well-bounded.
- 64-token overlap reduces "fact straddles boundary" misses.
- The splitter is well-understood, deterministic, and recommended in LlamaIndex docs for general-purpose ingest.

Semantic / hierarchical / source-code-aware splitters are out of scope for MVP — they introduce model-call cost and complexity disproportionate to expected MVP corpus sizes.

## 4. Document storage layout

**Question**: Where do raw files and the index live on disk?

**Decision**:

```
~/.coffer/
  kb/
    <kb-name>/
      raw/
        <document_id>.<original_ext>   # SHA-256-derived ids; original extension preserved
      index/
        ... (LlamaIndex persist dir)
      meta.json                         # optional human-readable manifest
```

Rationale:

- Constitution says "Bulk user content is stored as files on the local file system". Raw files honour this directly.
- Index lives next to raw files so the entire KB is a self-contained directory — easy to back up, easy to delete (one `rmtree`).
- Per-KB directories make on-disk size auditing trivial (`du -sh kb/<name>`).
- LlamaIndex persists indexes as JSON + a vector store file; we use the default `SimpleVectorStore` which writes to the persist dir. No external vector DB process needed.

## 5. Document identifier

**Question**: What is a document's id?

**Decision**: The first 16 hex chars of the document's SHA-256 content hash (the same value that gates duplicate ingest). Examples:

- A file `notes/design.md` containing 4 KB of markdown → `document_id = "8a3f…1c2b"` (16 chars).
- Re-ingesting the _same_ bytes → same id → rejected as duplicate unless `--replace`.

Reasons:

- Content-addressable: same bytes → same id, regardless of filename.
- Fits the project's "no surprise persistence" rule: ids are derived, not assigned by a sequence.
- 16 hex chars is enough at expected KB sizes (≤ 500 docs) to never collide.

The original filename is stored as a metadata column (`filename`); the document_id is the join key everywhere.

## 6. PDF extraction

**Decision**: `pypdf` (BSD-3). It is pure-Python, no JVM dependency (unlike `Apache Tika`), handles 90 %+ of typical PDFs, and is the recommended starter PDF tool in the Python ecosystem. Extraction failure → reject with a clear error; the user can convert the PDF themselves and re-ingest as text.

OCR is out of scope.

## 7. Observability (LangFuse)

**Question**: How do we surface ingest / search traces?

**Decision**: Define an in-process `Tracer` port in `application/`. Default adapter is a **no-op**. A **LangFuse** adapter is wired in only when `LANGFUSE_PUBLIC_KEY` is set in the environment. This keeps:

- Local-first invariant: zero outbound traffic by default.
- The deps for LangFuse are imported lazily inside the adapter (failed import in CI is fine).
- The tracer port has been extracted into `application/observability/` in this PR (one step earlier than the strict "second feature" rule) because spec 007 (memory) is anticipated to land next and will be the second consumer; this avoids an immediate refactor when 007 ships. The KB feature is the only current consumer.

The trace span names are stable and worth listing here:

- `kb.ingest_document` — attrs: kb_name, byte_size, char_size, chunk_count, duration_ms.
- `kb.search` — attrs: kb_name, query_len, top_k, hit_count, duration_ms.
- `kb.delete_document` — attrs: kb_name, document_id.
- `kb.delete` — attrs: kb_name, document_count.

Neither passage text nor query text is sent to LangFuse — only sizes and counts.

## 8. Built-in MCP tool surface

**Question**: How does Coffer's MCP gateway expose KB capabilities to a connected MCP client?

**Decision**: Three tools, namespaced under the reserved `coffer__` prefix:

- `coffer__list_knowledge_bases() -> [ {name, description, document_count, embedding_model}, ... ]`
- `coffer__search_knowledge_base(kb: str, query: str, top_k: int = 5) -> [ {text, document_id, filename, score, position}, ... ]`
- `coffer__get_document(kb: str, document_id: str) -> { document_id, filename, text, size_bytes }`

These appear in **every** MCP client's `tools/list` response, alongside upstream-MCP-server tools. The `coffer__` prefix is reserved (rejected as a server name in mcp_server registration); no upstream tool can ever produce a name starting with `coffer__` because upstream names are prefixed `<server_name>__`. A registration that names a server `coffer` is rejected with a clear error.

Built-in tool invocations are recorded in the same `mcp_invocations` table as upstream-tool calls. The `resource_name` column is set to the sentinel `"coffer"`. Retention and audit work uniformly.

## 9. Per-KB asyncio lock

Concurrent ingest into the same KB would race the index-write step inside LlamaIndex. Decision: one `asyncio.Lock` per KB (lazy-created, weak-referenced in the store adapter), held only across the index-mutating phase of ingest / delete. Search reads are unsynchronised — LlamaIndex's in-memory store handles concurrent reads cleanly.

## 10. Things explicitly NOT decided here

- Whether we eventually swap the vector store for Qdrant local. Listed in `out of scope` of the plan; revisit when corpus scale demands it.
- Source-code-aware chunkers.
- An incremental re-index flag.
- A "watch this folder" auto-ingest source.

Each is a clean future spec on top of this one; the port surface is designed not to need re-modelling for any of them.
