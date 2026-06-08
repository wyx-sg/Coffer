# ADR-010: RAG Engine — LlamaIndex Behind an Application Port

**Status**: Superseded by [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `006-knowledge-base` (FR-014, SC-006, research.md §1), [ADR-002](ADR-002-code-layout-layer-first.md), [ADR-008](ADR-008-everything-is-a-resource-kind.md)

> **Superseded (2026-06-09) by [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md).**
> The KB/memory redesign drops LlamaIndex in favour of markdown-files-as-truth +
> SQLite FTS5 + sqlite-vec with a configurable OpenAI-compatible embedding client
> and a pluggable `MarkdownConverter` port. The content below is retained for
> historical context only.

## Context

Spec `006-knowledge-base` adds the `knowledge_base` resource kind: each KB
holds documents the user has explicitly added, chunked / embedded / indexed
on disk, and searchable via a top-k retrieval call. The agent reaches that
corpus through Coffer's MCP gateway (three built-in `coffer__*` tools), so
the daemon ends up shipping a small RAG engine.

A RAG engine is a non-trivial moving part: it owns chunking strategy, the
embedding adapter, an index data structure (in-memory or on-disk), the
retriever, persistence, and the lifecycle that connects them. Coffer has
two competing pressures on this choice:

1. **Local-first + small dependency footprint.** The constitution forbids
   cloud system-of-record. The default install must run end-to-end on a
   developer laptop with no outbound API calls, no GPU, and a tight
   dependency surface. Heavy "framework" SDKs that pull dozens of optional
   subpackages are a poor fit.
2. **Resume-signal mainstream.** Coffer is a personal-fit / open-source
   project; choosing a fringe library buys minor technical simplicity at
   the cost of project legibility to anyone reading the code or evaluating
   it.

Either pressure alone has an obvious answer; together they conflict.

## Decision

**Use `llama-index-core` as the RAG engine, confined to a single
infrastructure adapter behind a small kind-owned port
(`KnowledgeBaseStore`).**

Concrete shape:

- The port lives in `coffer.domain.knowledge_base.store` and expresses
  _Coffer's_ needs: `open(kb_name, config)`, `ingest(kb_name, document,
text) -> int`, `delete_document`, `search(kb_name, query, top_k) ->
Sequence[Passage]`, `drop`, `close`. The Protocol does not leak any
  LlamaIndex type.
- The real adapter is `coffer.infrastructure.knowledge_base.llamaindex_store`.
  It is the _only_ module in the entire codebase allowed to `import
llama_index.*`.
- A `FakeKnowledgeBaseStore` lives in tests; the entire `application/` and
  `domain/` test surface uses the fake, so a future engine swap leaves the
  test pyramid intact.
- A new importlinter contract (Contract 7 in `backend/pyproject.toml`)
  enforces the confinement: `coffer.application.*` and `coffer.domain.*`
  MUST NOT import `llama_index*`. CI fails if anyone breaks it.
- The dependency is pinned to `llama-index-core` (no meta-package); the
  default embedding integration is `llama-index-embeddings-huggingface` +
  `sentence-transformers` + the local `BAAI/bge-small-en-v1.5` model.

## Consequences

**Positive**

- Coffer ships a mainstream RAG stack with no in-house chunker/retriever
  glue to maintain.
- A future bump (or swap to Haystack / txtai / sqlite-vec) rewrites _one_
  file. The contract guarantees no creeping coupling.
- The dependency surface stays bounded: `llama-index-core` only, plus the
  one embedding integration package. Most LlamaIndex optional
  sub-packages (LLM adapters, cloud retrievers, ingestion-as-a-service)
  never enter the lockfile.
- Engine-down does not take the daemon down: if the engine or its model
  fails to load, the daemon still starts; only ingest and search endpoints
  return 503 (FR-015).

**Negative**

- LlamaIndex has historically refactored core APIs (Document/Node/Index/
  ServiceContext → Settings, twice in 2024). Each future bump may touch
  the adapter file. Mitigated by (a) the adapter being one file, (b) the
  port being our shape, (c) integration tests under
  `pytest.importorskip("llama_index.core")` catching breakage at CI time.
- First `coffer kb ingest` downloads ~130 MB of embedding model from
  HuggingFace Hub. Documented in quickstart; `coffer kb warmup` exists
  for offline / installer-time pre-warming.
- LlamaIndex is large code-wise. The dependency tree is bigger than a
  hand-rolled solution would be. We accept this in exchange for the
  framework's loaders, retrievers, and reranker hooks we get for free.

## Alternatives Considered

Five candidates were evaluated in
[`specs/006-knowledge-base/research.md` §1](../../specs/006-knowledge-base/research.md). Summary
of the rejections:

**Haystack 2.x** — Cleaner pipeline model than LlamaIndex but a smaller
community and noticeably fewer ready-made loaders. The resume-signal /
mainstream consideration outweighed the technical elegance.

**LangChain RAG** — Same ecosystem family as LangGraph (Coffer's likely
future agent runtime), which is appealing. Rejected because LangChain's
RAG submodule is even heavier than LlamaIndex and has a louder reputation
for over-abstraction. The constitution's "fewest moving parts" principle
weighed against it.

**txtai** — Lightweight, hybrid retrieval built in, single import.
Rejected for the same resume-signal reason — too fringe; first-time
readers and prospective collaborators would have to learn an unfamiliar
library to navigate `infrastructure/knowledge_base/`.

**LanceDB + fastembed** — Library combo, smallest deps. Would force
Coffer to write its own retriever / chunker / loader glue (~200+ LOC of
in-house orchestration). The savings in dependency size do not justify
re-implementing what LlamaIndex hands us.

**ChromaDB + sentence-transformers** — Popular embedded vector DB,
but lacks built-in hybrid (BM25 + vector) retrieval. We do not need
hybrid for MVP, but the lack of a coherent end-to-end pipeline means we
would still hand-roll the orchestration layer.

**sqlite-vec + FTS5** — Zero new deps beyond a SQLite extension.
Rejected because we would write everything ourselves — the loader, the
chunker, the retriever, the persistence — turning a 1-week spec into a
multi-week one. Revisit when scale or zero-dependency policy demands it.

## Lock-in mitigation summary

The confinement contract (importlinter Contract 7), the kind-owned port,
the test pyramid that runs entirely against the fake, and the single-file
adapter together constitute the mitigation. The cost of swapping engines
is bounded to one file's rewrite plus updating the embedding-integration
dependency line in `pyproject.toml`. No application or domain code
changes.
