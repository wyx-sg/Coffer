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
- **`keyword`** — FTS5 `MATCH(query) ORDER BY bm25() LIMIT top_k`. Zero config, offline, CJK-capable (a **trigram** tokenizer matches Chinese and arbitrary substrings; `unicode61` did not segment CJK, so Chinese queries returned nothing). A query with no ≥3-char token (e.g. a 2-char CJK term) falls back to a bounded substring (LIKE) scan. A multi-term query is **AND-first**: the implicit-AND match (every term) runs first so chunks containing all terms outrank a chunk matching just one common term; only when AND returns fewer than `top_k` does it widen to OR and append the OR-only hits (deduped, AND kept first). The **default**.
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

**Decision**: **Boundary-aware (structure-preserving) Markdown chunking** — split on headings (a chunk never spans two sections), then **greedily pack whole structural blocks** (prose paragraphs, fenced code blocks, tables, list groups) into `chunk_size` windows (default 512) with `chunk_overlap` (default 64) carried between adjacent chunks. Both params are **per-KB and mutable**: changing them re-chunks + re-indexes the corpus (cheap, files = truth). This removes the original spec's partial-immutability smell where chunk params were frozen at creation.

Boundary-awareness is a **chunk-quality** property (not a new wire contract — FR-014 already governs the mutable char-based params): chunk boundaries are the unit of retrieval, so they must respect structure rather than slice blindly at `start + chunk_size`. Concretely:

- **Atomic blocks** — a fenced code block (```` ``` ```` / `~~~`, language tag included) or a Markdown table (a run of pipe-delimited rows — header, delimiter, body) is **never split internally**. The old char-window split mid-fence / mid-table, producing orphaned half-fences and headerless table fragments that embed and read poorly.
- **Greedy block packing** — whole blocks pack into a chunk until the next would overflow `chunk_size`, then a new chunk opens; breaks prefer blank-line / block boundaries. An oversized prose paragraph breaks at the nearest **sentence** boundary (`. ` / `。` / newline) rather than mid-word, with a hard split only as a last resort for a break-less paragraph.
- **Oversized atomic block** — a single fence or table larger than `chunk_size` is kept **whole** as its own (oversized) chunk; a half-fence is worse for retrieval than one big chunk.
- **Overlap** — adjacent chunks share context by re-including the previous chunk's trailing sentence/block up to ~`chunk_overlap` chars (snapped to a boundary); char-exact overlap is necessarily approximate once whole blocks are packed.

Sizing stays **char-based** (deterministic, dependency-free); token-based sizing is deferred (no tokenizer is pulled in). Semantic / hierarchical / source-code-aware splitters are out of scope for MVP; they add model-call cost disproportionate to expected corpus sizes and can be added behind the same chunker interface later.

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

## 9. Degraded-embed: decouple from the sha gate + surface the count (KB8)

**Question**: When the embedding provider is unavailable, how does the routine keep the embed retryable without breaking the no-op gate, and how does a degrade become visible on a read?

**Decision**: A dedicated persisted **`embed_pending`** flag, decoupled from `content_sha256` (which always carries the real body hash), plus a persisted-count surfacing.

- **Why decouple.** The old design overwrote `content_sha256` with an empty-string sentinel so the next reconcile would mismatch and retry the embed. But `"" == previous_sha` is never true, so EVERY scan re-chunked the degraded doc + rewrote its FTS rows + re-attempted the embed — one unrelated edit re-indexed the whole degraded corpus. The empty sha also corrupted the files-as-truth derivation. Splitting the retry state onto its own column lets the sha gate stay honest (unchanged body ⇒ no churn) while the embed still retries.
- **Why a retry-embed-only path.** When the body is unchanged but `embed_pending`, the chunks + FTS are already current — only the vectors are missing. The routine re-chunks **in memory** (deterministic positions), embeds, and calls a new index method `upsert_vectors` that writes ONLY the vec rows. No FTS / chunk rewrite ⇒ the degraded-corpus churn is gone, and the vectors align with the stored chunks by position.
- **Why surface from the persisted flag, not the transient scan count.** The degraded count was computed inside `reindex_scan` and only returned by the explicit `POST /reindex`; a degrade during a lazy reindex-on-read (list / get / search / grep) was silently dropped (`_reconcile_on_read -> None`). Querying the persisted `embed_pending` (`count_pending_embeds`) in `metrics()` makes `documents_degraded` correct on ANY read, with no need to thread the scan count through every read path.
- **Boundary.** `embed_pending` tracks ONLY a failed embedding **provider** call (`EngineUnavailable`). It is orthogonal to sqlite-vec extension availability: a provider success with an unavailable vec table is `embedded=True` (not pending) and is handled at query time by `SearchResponse.fallback` — same parity as the existing `embedded` flag.

## 10. Things explicitly NOT decided / out of scope here

- Hybrid RRF fusion of keyword + vector in a single call (optional future, same engine).
- Reranking / HyDE / multi-query / LLM synthesis on retrieval — the agent synthesizes.
- Agents editing KB documents — KB is user-curated; revisit later.
- Image OCR / audio transcription by default.
- A filesystem watcher on by default.
- Final converter library per format (MarkItDown vs Docling) and local-model MTEB/CPU benchmarks — operational tuning behind the converter/embedder ports; no re-modelling needed.
- sqlite-vec packaging on macOS arm64 + Linux — guarded by `importorskip`; a load failure degrades vector to keyword, never blocks.
