# ADR-012: Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec, Configurable Embeddings

> 中文版: [ADR-012-files-as-truth-sqlite-retrieval.zh.md](./ADR-012-files-as-truth-sqlite-retrieval.zh.md)

**Status**: Accepted
**Date**: 2026-06-09
**Deciders**: Yuxing Wu
**Supersedes**: [ADR-010](ADR-010-llamaindex-rag-engine.md) (LlamaIndex RAG engine), [ADR-011](ADR-011-mem0-memory-engine.md) (mem0 memory engine)
**Related**: spec `006-knowledge-base`, spec `007-memory`, [ADR-002](ADR-002-code-layout-layer-first.md), [ADR-007](ADR-007-everything-is-a-resource-kind.md), [ADR-013](ADR-013-agent-native-shared-memory.md)

## Context

The first cut of `knowledge_base` (ADR-010) and `memory` (ADR-011) shipped as
two near-symmetric "stores you query over MCP", each with its own heavyweight
engine:

- **KB** routed between a hand-rolled keyword backend and a LlamaIndex semantic
  backend through a `DispatchingKnowledgeBaseStore`. LlamaIndex persisted its
  own on-disk index alongside the raw documents.
- **Memory** used `mem0ai`, which requires an LLM at write time (mem0
  fact-extraction). The default `llm_provider="none"` made `add_memory` return
  503, and text was dual-written to both SQLite and chroma.

Three structural problems surfaced once both kinds were in use:

1. **Dual source of truth.** mem0/chroma stored fact text in chroma _and_ in
   SQLite; LlamaIndex stored a derived index that could silently diverge from
   the raw documents. There was no single authoritative copy to back up,
   diff, or rebuild from.
2. **Engine sprawl.** Two RAG/memory frameworks (LlamaIndex, mem0), a vector DB
   (chroma), a hand-rolled keyword store, and a dispatcher — four heavy moving
   parts plus glue — for what is, conceptually, "retrieve over markdown."
3. **LLM-at-write-time for memory is friction** when the consumer is already an
   LLM that can decide what to remember and write a clean fact itself.

The original ADR-010 explicitly parked `sqlite-vec + FTS5` ("revisit when scale
or zero-dependency policy demands it") and ADR-011 mirrored that reasoning. The
redesign (see the design doc) revisits exactly that: the configurable-embedding
requirement and the files-as-truth requirement together change the calculus.

## Decision

**Drop LlamaIndex, mem0, chroma, the hand-rolled keyword store, and the
dispatcher. Make markdown files on disk the sole source of truth, and keep all
derived index/metadata in `coffer.db` via SQLite FTS5 (keyword/BM25) and
sqlite-vec (vector). Embeddings come from an OpenAI-compatible, user-configurable
provider. Any-format ingestion goes through a pluggable `MarkdownConverter`
port (MarkItDown default).**

Concrete shape:

- **Files are truth, SQLite is a rebuildable index.** KB documents live as
  normalized `docs/<doc-id>.md` (plus `raw/<doc-id>.<ext>` provenance); memory
  facts live as per-fact `<slug>.md` + a regenerated `MEMORY.md`. Anything in
  SQLite (`documents`, `chunks`, `documents_fts`, `vec_chunks`) is reconstructable
  by `coffer reindex` from the files. This kills the dual-source-of-truth bug at
  the root.
- **Three retrieval modes**, all over the same files/index:
  - `grep` — ripgrep over `docs/` (raw files, zero index, language-agnostic).
  - `keyword` — SQLite FTS5 `MATCH … ORDER BY bm25()`. A regular FTS5 table
    stores the chunk text once inside its index (still rebuildable from the
    markdown files, which remain the source of truth).
  - `vector` — sqlite-vec KNN over chunk embeddings.
  - Optional hybrid via reciprocal rank fusion. Default retrieval is
    `keyword`+`grep` (zero config, offline). Vector is opt-in; if vector is
    requested but embeddings are unconfigured, retrieval falls back to keyword
    and flags it — it never blocks.
- **Configurable, OpenAI-compatible embeddings** (DevPilot-style: one
  `AsyncOpenAI` client with a swappable `base_url`). Per-corpus config:
  `embedding_provider`, `embedding_model`, `embedding_base_url`,
  `embedding_credential_ref` (keychain ref, never plaintext). Works against
  OpenAI / OpenRouter / Voyage / Cohere / Jina / Gemini / Azure / DashScope and
  local Ollama / LM Studio through the same `.embeddings.create` call, plus an
  optional in-process `local` provider (fastembed) for zero-server offline
  embeddings. The embedding model is **mutable** — changing it re-embeds the
  corpus (files = truth), so there is no immutability lock.
- **Pluggable `MarkdownConverter` port** (`can_handle(format)` +
  `convert(bytes) -> (markdown, metadata)`), confined to infrastructure,
  dispatched by format. Default engine is **MarkItDown** (broad coverage,
  LLM-oriented, MIT); Docling / pandoc can be attached per format. Because
  `raw/` is retained, markdown can be regenerated with a better converter later.
- **One store, two faces.** A single `knowledge` retrieval engine backs both the
  KB face (any-format → markdown, agent-read-only) and the memory face (per-fact
  markdown, shared across agents). The import-confinement contract that ADR-010
  applied to `llama_index*` / ADR-011 to `mem0*` is re-pointed at the new
  third-party libs (sqlite-vec loader, the converter libs, the OpenAI client) so
  `application/` and `domain/` never import them directly.

## Consequences

**Positive**

- **One source of truth.** Markdown files are authoritative; SQLite is fully
  rebuildable. Backup is one directory tree; corruption recovery is `reindex`;
  a user can diff/grep/edit memory and KB content with ordinary tools.
- **One store, fewer deps.** Everything lives in `coffer.db` (FTS5 + sqlite-vec);
  chroma, LlamaIndex's persist layer, and mem0's vector path all leave the
  lockfile. The keyword path becomes BM25 instead of a hand-rolled
  term-frequency JSON scan, and the dispatcher disappears.
- **No LLM required to write memory.** The agent writes a clean fact directly;
  the default install makes zero outbound calls. Embeddings (and thus any
  outbound call) are strictly opt-in per corpus.
- **Configurable embeddings without a framework.** A thin OpenAI-compatible
  client covers every mainstream provider and local server, which is the exact
  flexibility LlamaIndex's embedding adapters were being used for — minus the
  framework.
- **Cheap mutability.** Because files are truth, changing chunk params or the
  embedding model is a re-chunk/re-embed, not a store rebuild from a lossy
  index. This fixes ADR-011's "config is immutable post-create" friction.

**Negative**

- **More in-house orchestration than ADR-010/011 accepted.** We now own the
  chunker, the FTS5/vec glue, the retrieval fusion, and the converter dispatch —
  the very ~200–300 LOC ADR-010 and ADR-011 paid LlamaIndex/mem0 to avoid. We
  accept this: the surface is small, the concepts are ours, and there is no
  framework churn to track.
- **sqlite-vec is a native extension.** It must load on macOS arm64 and Linux
  in the PyInstaller bundle ([ADR-008](ADR-008-distribution-pyinstaller-tauri-sidecar.md));
  packaging/loading is an open verification item.
- **Converter quality is now our problem.** MarkItDown's PDF/Docx fidelity, OCR,
  and the MarkItDown-vs-Docling choice are ours to validate per format. The
  `raw/` retention + re-convertibility is the mitigation.
- **Less "resume-signal mainstream".** ADR-010/011 valued legibility via
  well-known frameworks. SQLite FTS5 + sqlite-vec is arguably _more_ legible to a
  reader (it is just SQLite), but loses the "I used LlamaIndex/mem0" signal. We
  judge the architectural win to dominate.

## Alternatives Considered

**Keep LlamaIndex (ADR-010) for KB.** The strongest reason to keep it was its
embedding adapters and loaders. But the configurable-embedding need is met more
directly by a thin OpenAI-compatible client (one `base_url` swap reaches every
provider), and LlamaIndex's persisted index actively fights files-as-truth: it
wants to own a derived store that can diverge from the markdown. Rejected
because the single-source-of-truth requirement is incompatible with a framework
that insists on owning the index, and the one thing we wanted from it
(embeddings) is a 50-line client.

**Keep mem0 (ADR-011) for memory.** mem0's value is fact-extraction + dedup at
write time, which presupposes an LLM call we explicitly want to remove: the
agent _is_ the LLM and writes the fact itself. mem0 also dual-writes to chroma,
the exact bug being eliminated. Rejected — the framework's core feature is the
friction we are removing.

**Keep chroma as the vector store, FTS5 for keyword.** Workable, but it keeps a
second datastore (and a second source of truth for vectors) alongside SQLite.
sqlite-vec puts vectors in the same `coffer.db` as FTS5, the documents table,
and the audit log — one file to back up, one writer, one rebuild path. Rejected
for store uniformity: a second embedded DB earns nothing once vectors are
rebuildable from files.

**Hand-rolled keyword store (the current KB keyword backend) kept as-is.** It is
a term-frequency JSON scan — slower, no BM25, and a bespoke ranker to maintain.
FTS5 is built into SQLite, gives `bm25()` for free, and removes code. Rejected;
there is no reason to keep a worse re-implementation of what SQLite ships.

**Files-as-truth with no SQLite index (grep only).** Tempting for zero
infrastructure, and grep remains a first-class mode. But keyword ranking (BM25)
and vector recall need an index, and rebuilding one from files on every query
does not scale. Rejected as the _sole_ mode; retained as one of three.

## Lock-in mitigation summary

The same confinement discipline as ADR-010/011 applies, re-pointed: the
`MarkdownConverter` port and the OpenAI-compatible embedding client are the only
infrastructure seams that touch third-party libs, behind kind-owned ports with
fakes in tests and importlinter contracts keeping `application/` and `domain/`
clean. Swapping the converter, the embedding provider, or even the vector
extension is a one-adapter change. Crucially, because **files are the source of
truth**, the deepest possible lock-in — a proprietary index format you cannot
leave — is gone: any engine can be rebuilt from the markdown.
