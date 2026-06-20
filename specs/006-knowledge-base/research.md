# Research — 006 Knowledge Base (redesign)

> 中文版: [research.zh.md](./research.zh.md)

Background and rationale for the technology choices in this redesign. Each section closes with the **decision**; alternatives are recorded so future readers know the path not taken. This redesign **supersedes** the original 006 choices (LlamaIndex + sentence-transformers) and is captured in a new ADR that supersedes ADR-010 and ADR-011.

> **Later amendment — [ADR-028](../../docs/decisions/ADR-028-knowledge-base-documents-co-managed.md) (2026-06-19):** two decisions recorded below were subsequently reversed. The **doc id** is now a stable ULID (not the source-sha256 prefix in §3), and the KB is **co-managed** — agents may write documents via MCP, not read-only (§4) — guarded by the F01 audit. The text below is kept as the original record; ADR-028 is the authority where they differ.

## 1. Retrieval stack: files + SQLite, no RAG framework

**Question**: What is Coffer's backbone for storing, indexing, and retrieving knowledge?

**Candidates**:

| Approach                                      | Strengths                                                                  | Risks for Coffer                                                                                                            |
| --------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **LlamaIndex** (original 006)                 | Industry-mainstream, many loaders                                          | Heavy; refactored twice; persist dir is a second source of truth alongside files; abstractions leak; pulls a large dep tree |
| Haystack 2.x                                  | Cleaner pipeline model                                                     | Smaller community; still a framework                                                                                        |
| **Markdown files + SQLite FTS5 + sqlite-vec** | Zero framework; files are the truth; one `coffer.db`; offline keyword/grep | We write chunker + retriever glue (~modest LOC), all under our control                                                      |
| Chroma / Qdrant local                         | Popular vector DBs                                                         | A second process/store; hybrid not built-in; another source of truth                                                        |

**Decision**: **Markdown files as the source of truth + SQLite (FTS5 for keyword, sqlite-vec for vector), no RAG framework.** Drives the central redesign principle — _files are truth, SQLite is a rebuildable index_. Benefits:

1. Kills the original dual-source-of-truth smell (text in both a persist dir and SQLite). `coffer kb reindex` reconstructs every SQLite row from the files.
2. Keyword + grep work offline with zero config and zero model download.
3. Everything lives in one `coffer.db` next to the rest of Coffer's control plane — one backup, one delete.
4. The converters and the vector engine sit behind ports in `infrastructure/`; a future swap rewrites one file.

LlamaIndex, mem0, chroma, the hand-rolled keyword term-frequency scan, and the dispatcher are all removed.

## 2. Three retrieval modes

**Question**: How does a user / agent retrieve from a KB?

**Decision**: Three modes, one engine, face-tuned tools:

- **`grep`** — `ripgrep` over `docs/*.md`, bounded by `max_matches` and a timeout. No index, no embedding, regex/exact. Returns `{path, line_number, line}`. Always available the instant files exist.
- **`keyword`** — FTS5 `MATCH(query) ORDER BY bm25() LIMIT top_k`. Zero config, offline, language-agnostic (unicode61 tokenizer). The **default**.
- **`vector`** — embed the query → sqlite-vec KNN top_k. Opt-in; needs a configured embedding provider.

A KB declares `enabled_modes` + `default_mode`; a search call may override `mode`. **Hybrid (RRF fusion of keyword + vector)** is an optional future addition behind the same engine — listed as a non-blocking enhancement, not built in MVP.

**Vector fallback**: if `vector` is requested but no embedding provider is configured, the engine runs `keyword` and flags `fallback="keyword"` in the response. Retrieval never blocks on missing embedding config.

## 3. Converter library (any format → Markdown)

**Question**: How is an arbitrary upload normalized to Markdown?

**Candidates**:

| Library                         | Strengths                                                                                | Notes                                      |
| ------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------ |
| **MarkItDown** (Microsoft, MIT) | Broad coverage (PDF/docx/pptx/xlsx/html/csv/json/…), LLM-oriented Markdown output, light | Default                                    |
| Docling (IBM, MIT)              | High-fidelity PDF (layout, tables, optional OCR)                                         | Heavier; pluggable per format when present |
| pandoc                          | epub/odt/rtf and many formats                                                            | External binary; pluggable                 |
| readability + custom            | HTML boilerplate stripping                                                               | Used inside the HTML path                  |

**Decision**: A `MarkdownConverter` **port** (`can_handle(format)` + `convert(bytes) -> (markdown, metadata)`) with a per-format **registry**, confined to `infrastructure/knowledge/converters/`. Default engine **MarkItDown**; Markdown / plain text / source code use a passthrough converter and csv a dedicated converter. No Docling/pandoc converter ships today — the open item (MarkItDown vs Docling for PDF) is resolved _structurally_ by the registry: a higher-fidelity engine for a format would be a new converter under `infrastructure/knowledge/converters/`; no spec change is needed to swap.

After conversion the pipeline **cleans** (normalize whitespace, strip control chars, collapse blank lines, fix heading levels, strip HTML boilerplate; reject empty result) and prepends **YAML frontmatter** so the stored `.md` self-describes.

## 4. Embedding configuration (vector mode)

**Question**: Which embedding model, and how is it configured?

**Decision**: A **user-configurable, OpenAI-compatible provider abstraction** (DevPilot-style: one `AsyncOpenAI` client with a swappable `base_url`). Per-KB `EmbeddingConfig`: `provider`, `model`, `base_url`, `credential_ref` (encrypted-store ref, never plaintext), `dimensions`. Providers reachable through the same `.embeddings.create` call: OpenAI / OpenRouter / Voyage / Jina / Gemini / Azure / DashScope and local Ollama / LM Studio; plus an in-process **`local`** provider (fastembed) for zero-server offline embeddings.

- **Default retrieval is `keyword`+`grep`** (zero config, offline). Vector is opt-in — the user is never forced to pick a model or download anything to get a working KB.
- **The embedding model is mutable.** Changing it re-embeds the corpus (files are the truth, so this is cheap to re-derive). No immutability lock — this fixes the original spec's "recreate the KB to change the model" friction.
- For **bilingual** content, recommend a local `bge-m3` (fastembed) or a cloud provider; English-only small models embed Chinese poorly. Hard MTEB/CPU benchmarks for local models are an optional pre-finalize step, not a blocker.

Outbound embedding calls go through Coffer's SSRF-guarded HTTP client. Vector mode reaching a third-party API does not violate local-first: only the query/chunk text is embedded; user data stays on disk (constitution Principle I; see the local-first memory note).

## 5. Chunking strategy

**Question**: How is Markdown split before indexing?

**Decision**: **Markdown-aware chunking** — split on headings, then bound by `chunk_size` (default 512) and `chunk_overlap` (default 64). Both are **per-KB and mutable**: changing them re-chunks + re-indexes the corpus (cheap, files = truth). This removes the original spec's partial-immutability smell where chunk params were frozen at creation.

Semantic / hierarchical / source-code-aware splitters are out of scope for MVP; they add model-call cost disproportionate to expected corpus sizes and can be added behind the same chunker interface later.

## 6. Document storage layout & identifier

**Decision**: `~/.coffer/knowledge/<kb-name>/docs/<doc-id>.md` (normalized Markdown = truth) + `raw/<doc-id>.<ext>` (original upload = provenance, re-convertible). **No** per-corpus `index/` or `chroma/` directory — all indexing is in `coffer.db`.

`doc-id` = first 16 hex chars of the original's `source_sha256` (same value that gates duplicate uploads). Content-addressable, derived not assigned, collision-safe at expected KB sizes (≤ 500 docs). Keeping `raw/` means a document can be re-converted later with a better engine.

## 7. Editing & the single re-index routine

**Question**: How are user edits and re-uploads kept consistent?

**Decision**: KB is **user-curated, agent-read-only** (design option A). Two edit paths: re-upload a new source (re-convert → new Markdown) or edit the Markdown directly — either through the edit API (REST/CLI) or by opening the on-disk file in the user's external editor. The Coffer UI viewer is **read-only**; it offers open-in-editor / reveal / copy-path affordances rather than an in-app text editor. `source_mode` is `converted` (Markdown derived from raw; re-convertible) or `edited` (re-conversion blocked to avoid clobbering; re-upload resets to `converted`). One idempotent re-index routine serves ingest, re-upload, edit, and the reindex scan: `content_sha256` unchanged ⇒ no-op; changed ⇒ delete old chunks/FTS5/vec, re-chunk, re-embed (if vector), upsert the `documents` row, audit. Consistency triggers: API edits + explicit `coffer kb reindex` (rescans deltas) + **lazy reindex-on-read** (a read/search detects drifted `content_sha256` and reconciles before serving) — there is no filesystem watcher, so external-editor edits surface on the next read.

## 8. Built-in MCP tool surface (read-only)

**Decision**: Four read-only tools under the reserved `coffer__` prefix, served by the gateway to every client:

- `coffer__list_knowledge_bases() -> [{name, description, document_count, modes}, ...]`
- `coffer__search_knowledge(kb, query, top_k=5, mode?) -> {mode, fallback?, passages:[{text, document_id, title, score, position}, ...]}`
- `coffer__grep_knowledge(kb, pattern, max_matches?) -> [{path, line_number, line}, ...]`
- `coffer__read_document(kb, doc_id) -> {document_id, title, markdown, metadata}`

No KB write tool exists — the KB is user-curated. Invocations log to `mcp_invocations` (tool name + who/when/duration/outcome only; no arguments or returned content), matching the existing privacy stance. The `coffer__` prefix is reserved (a server named `coffer` is rejected at registration); upstream tools are prefixed `<server>__` and can never collide.

## 9. Things explicitly NOT decided / out of scope here

- Hybrid RRF fusion of keyword + vector in a single call (optional future, same engine).
- Reranking / HyDE / multi-query / LLM synthesis on retrieval — the agent synthesizes.
- Agents editing KB documents — KB is user-curated; revisit later.
- Image OCR / audio transcription by default.
- A filesystem watcher on by default.
- Final converter library per format (MarkItDown vs Docling) and local-model MTEB/CPU benchmarks — operational tuning behind the converter/embedder ports; no re-modelling needed.
- sqlite-vec packaging on macOS arm64 + Linux — guarded by `importorskip`; a load failure degrades vector to keyword, never blocks.
