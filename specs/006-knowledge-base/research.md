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

## 10. Title as embedding context (KB5)

**Question**: A chunk taken from the middle of a document is embedded in isolation, so its vector loses the document's subject — how do we restore topic context for better vector recall?

**Decision**: Prepend the document **title** (`"{title}\n\n{chunk}"`) to the text that gets **EMBEDDED** only — a standard RAG technique. The text written to FTS (`documents_fts`) and to the chunk rows stays the **raw** chunk, so the returned `Passage.text` is never polluted (the title is already surfaced separately via `Passage.title` from the `documents` JOIN). The prefix lives solely inside `Reindexer._maybe_embed`; the caller still passes the raw `chunks` to `upsert_chunks`. Memory reuses this: the fact name is the title.

- **No mass re-embed.** `content_sha256` stays the hash of the **raw body** (the title is NOT folded in), so existing docs are not flagged "changed" — they keep their (title-less) vectors until a genuine content change or a `force` reconcile re-embeds them with the title. That gradual rollout is intended and acceptable: mixed title/no-title vectors share the same space with no correctness issue.
- **No migration / no schema change.** No new FR (a retrieval-quality change under the existing modes, like the KB4 chunker and KB2). No FTS schema change, no `upsert_chunks`/`upsert_vectors` signature change.
- **Deferred.** A keyword-side indexed `title` FTS column was deferred — it would need an FTS-rebuild migration and has a short-CJK-title trigram gap — until keyword title-matching proves needed.

## 11. Embedding request batching (KB9)

**Question**: Re-embedding runs serially under the per-store lock — one provider call per document — and a single `embed()` sends ALL of a document's chunks in one unbounded request. How much of this should be batched?

**Decision**: Bound the **request size**, do NOT add cross-document parallelism.

- **Bound request size (shipped).** `OpenAICompatibleEmbedder.embed` splits its input into sequential sub-requests of at most `_MAX_EMBED_BATCH` (128) texts and concatenates the results in input order. This prevents a many-chunk document — or a future batched caller — from sending one unbounded request that an OpenAI-compatible endpoint would reject on its inputs-per-call or token limit (a latent bug, made slightly more pressing by KB5 lengthening each embedded text with the title prefix). Per-sub-request `index` re-alignment + width validation are preserved; one sub-request failure raises `EngineUnavailable`, so the doc degrades whole and is retried via KB8's `embed_pending` (all-or-nothing per doc, unchanged). Local (fastembed) embeddings are in-process and need no bound.
- **Cross-document parallel/batch re-embed: deliberately deferred (not built).** Collapsing the serial per-document loop into a concurrent or cross-document batched sweep was evaluated and judged over-engineering for a single-user tool: the within-call batch already exists; a full re-embed only happens on a `force` reconcile (config change) or a provider-recovery sweep — both infrequent — and `CooldownEmbedder` already de-fangs the provider-down case (no O(N×timeout) stall). The cross-doc restructure would break the per-document `embed → upsert_chunks` atomicity that KB8's per-doc `embed_pending` isolation relies on, and bounded concurrency's payoff is cloud-provider-only on a rare operation. Revisit only if a real bulk-re-embed latency complaint appears.
- **No migration / no schema change. No new FR** (a reliability/robustness change under the existing retrieval modes).

## 12. Resource-list count uses the indexed count, not `metrics()` (KB14)

**Question**: The resource LIST endpoints (`GET /knowledge_bases`, `GET /memory_stores`) call the full `metrics()` per resource just to display a count. `metrics()` does expensive disk I/O the list output discards: KB's `metrics()` runs a recursive `du_bytes` disk walk per KB; memory's `store_metrics()` runs BOTH a `scan_store_dir` (read/parse every fact file) AND a `du_bytes` walk per store. Listing N resources triggers N disk walks (KB) / N file-scans + N walks (memory) for a number the list shows but never the `disk_bytes` it computes.

**Decision**: Give each list path a cheap count that hits ONLY the indexed DB `count_documents`, never `du_bytes` / `scan_store_dir`.

- **KB list** uses a thin `KnowledgeBaseService.document_count(kb_name)` → `count_documents(KIND_KNOWLEDGE_BASE, kb_name)` (the same indexed count `metrics()` already returns as `document_count`). No `du_bytes` walk on the list path.
- **Memory list** uses a thin `MemoryService.fact_count(store_name)` → `count_documents(KIND_MEMORY, store_name)`. The count SOURCE moves from the on-disk file count (`len(scan_store_dir().files)`) to the DB index — matching how KB already counts. The small index-vs-disk staleness window closes on the next recall/reconcile (lazy reindex-on-read), an acceptable tradeoff for a list-display number.
- **`metrics()` / `store_metrics()` are unchanged**: the per-resource DETAIL endpoint (`GET /{name}/metrics`) still walks the disk and reports `disk_bytes`. Only the LIST path changed.
- **No migration / no schema change. No new FR** (a perf change under the existing endpoints).

## 13. Atomic writes for persisted source-of-truth files (KB19)

**Question**: Coffer's invariant is "files are truth, SQLite is a rebuildable index", yet the persisted Markdown / raw files were written non-atomically via plain `path.write_text` / `path.write_bytes`. A crash or power loss mid-write leaves a TRUNCATED file — a corrupt source of truth that the next reindex faithfully ingests.

**Decision**: Route every persisted-truth write through one shared helper, `coffer.infrastructure.knowledge.fs.atomic_write_text` / `atomic_write_bytes`, that writes to a temp file in the SAME directory, fsyncs it, then `os.replace`s it into place. `os.replace` is an atomic rename on the same filesystem, so a concurrent reader always sees either the complete OLD file or the complete NEW file, never a partial mix; on any failure the temp file is removed and the original is left untouched.

- **Sites converted**: KB doc writes (ingest via `mkparent_write`, edit, reconvert) and the KB raw-upload bytes; memory fact files, organizer topic docs + `INDEX.md`, and the per-branch handoff files. The helper is stdlib-only (no import cycle) and lives in the shared `infrastructure.knowledge` substrate — already the application-composable home for kind-agnostic helpers (chunking, frontmatter, ids, paths) that the import-linter contract lets `application/knowledge_base/*` import — so both `application/knowledge_base/*` and `infrastructure/memory/*` reuse it with no architecture-boundary change. The already-off-loop writes keep their `asyncio.to_thread` wrapping (the helper is sync).
- **Append-only logs are deliberately NOT converted**: `consolidation-log.md` is opened in append mode (`"a"`); it is an audit trail where atomic-replace would destroy prior history, and an interrupted append cannot corrupt earlier lines.
- **Directory fsync (rename-durability under power loss) is deliberately DEFERRED**: a single file-fsync + `os.replace` already delivers ATOMICITY (no partial/corrupt file), which is the KB19 goal. Guaranteeing the rename *itself* survives a power loss needs an extra fsync of the parent directory; it is a stronger durability guarantee that can be layered onto the shared helper later if a real need appears, with zero call-site churn.
- **No migration / no schema change. No new FR** (a robustness/quality change under existing behaviour). Memory's source-of-truth files (spec 007) share the helper; this is the single home for the atomicity guarantee.

## 14. Code-hygiene sweep (dead-code + stale comments)

**Question**: Several artefacts predate the spec-006 redesign and the ADR-028 ULID identity switch, leaving dead code, comments that misdescribe doc-id identity, unused i18n keys, and an undocumented scan bound. A deletion-safety audit verified each is truly dead/stale and safe to remove or correct.

**Decision**: A no-behaviour-change cleanup:

- **Removed the dead `kb_doc_id` / `DOC_ID_LEN`** helper (the old "first 16 hex chars of `source_sha256`" content-addressed doc id). Doc ids are now ULIDs (ADR-028: a re-upload mints a NEW id), so this helper has zero call sites; deleted from `domain/knowledge_base/document.py` and pruned from both `__all__` lists.
- **Reworded stale "content-addressed" doc-id comments** in `infrastructure/knowledge/models.py`, `infrastructure/knowledge/sqlite_index.py`, and the matching integration-test docstring. The store-scoped chunk-id rationale STANDS — a ULID is unique only within a store, so the same doc id can still appear across stores and must not collide — only the false "content-addressed / same file repeats its id" premise was corrected. The genuinely content-addressed path hash in `memory/scope_fs.py`, the immutable migration history, and ADR-028's description of the OLD scheme were left untouched.
- **Dropped 14 unused KB i18n keys** (the old per-KB embedding form `dialog.{vectorHint,provider,embeddingModel,dimensions,baseUrl,credential}`, now global; and `detail.{metrics,reindexResult,chunks,editAria,loadFailed,edit,save,cancel}`, superseded by `common.*`) from both `en.json` + `zh.json`, keeping the two locales structurally identical.
- **Documented the 100k per-scan document cap** as a single named constant `DOCUMENT_SCAN_LIMIT` in `domain/knowledge/document.py`, used at all three `list_documents(limit=…)` reconcile sites (KB reindex scan, KB source-tracking, memory sync). It is a safety bound — the max docs scanned/reconciled per store in one pass, NOT an enforced ingest limit; corpora are expected far below it. Value unchanged (100_000).
- **The per-KB `embedding` config field was reviewed and KEPT** — runtime-inert legacy but contract-live: it still backs a register-time credential-missing guarantee, an acceptance test, and a CLI/frontend surface. It is intentionally NOT removed.

**No migration / no schema change / no new FR** (pure cleanup under existing behaviour).

## 15. Document timestamps in frontmatter (KB18)

**Question**: Coffer's invariant is "files are truth, SQLite is a rebuildable index", yet a KB document's on-disk `.md` frontmatter did NOT record `created_at` / `updated_at`. So when the database is lost and rows are rebuilt from the files (`document_from_frontmatter`), BOTH timestamps reset to `now()` — the original ingest/edit time was silently lost. The memory face (spec 007) already records these in each fact file and reads them back, so the gap was KB-only.

**Decision**: Write `created_at` / `updated_at` (ISO strings) into the KB doc frontmatter on every write path — ingest (`render_ingest_markdown`) and edit/reconvert (`render_doc_markdown`), keeping the two field sets identical so an ingest→edit→rebuild round-trip is stable. On first ingest both equal `now`; on a re-upload `created_at` is preserved from the existing document and `updated_at` is bumped; an edit/reconvert preserves `created_at` and bumps `updated_at`. The DB-loss rebuild (`document_from_frontmatter`) now reads them back so a rebuilt row restores the REAL timestamps instead of `now()`.

- **File-mtime fallback for back-compat**: a pre-existing / hand-written file lacking the keys (or with a blank/unparseable value) degrades to the file's `mtime` — NOT `now()` — mirroring memory's `parse_fact_markdown`. So existing corpora rebuild with a sensible time and need NO migration / NO backfill.
- **Local `_parse_dt` helper, no cross-kind import**: the ISO→aware-UTC parse helper is a local copy in `application/knowledge_base/pipeline_helpers.py`; the import-linter forbids importing from `infrastructure/memory/*` (memory↔knowledge_base are separate kinds), and a per-kind copy is the established pattern (memory's topic_files / handoff each keep their own).
- **`converted_at` is unchanged** — it tracks a conversion-engine run, not the document's age, so it stays `now` on a rebuild.
- **No new FR** — this closes a files-as-truth gap under the existing FR-008 / SC-005 rebuild guarantee. No schema/DB change (the `documents` table already has the two columns); only the on-disk file contents and the rebuild read path change.

## 16. Source-file update detection — frontend (FR-021..024)

**Question**: PR #140 shipped the backend for external source-file tracking — a `check-sources` scan that reports, per document with a tracked `source_path`, whether its original on-disk file is `unchanged` / `changed` / `missing` / `edited` (source moved on but the doc was locally edited, so a re-ingest is skipped) / `updated` (was changed and auto-re-ingested because the KB's `auto_update_sources` is on), plus a per-document `update-source` re-ingest and the per-KB `auto_update_sources` config flag. None of it was reachable from the UI.

**Decision**: Surface it on the KB detail page as purely additive UI (no backend change):

- A **"Check sources"** header action (next to Settings / Reindex / Upload) POSTs `check-sources` and opens a **report dialog**. Each row shows the document title, its source path, and a status badge for one of the five statuses. Only a **`changed`** row offers a per-row **"Update from source"** button (POST `update-source`, re-ingest in place); `missing` rows note the file is gone, `edited` rows note the doc was edited locally so updating is blocked (the backend refuses an `edited` doc with a typed error, surfaced as a toast). When the scan returns no rows the dialog explains that **web uploads aren't tracked** — only path-based ingests (CLI / desktop) carry a source file.
- The per-KB **`auto_update_sources`** flag gets a `<Switch>` row in the settings dialog. Because the config PATCH **replaces** the whole config (FR-014/FR-019), the toggle's value is threaded through the merged config built on submit, and the field was added to `KnowledgeBaseConfigOut` so a settings save can't silently reset it to false.
- **No new FR** — this delivers the existing FR-021..024 frontend; coverage is the new `SourceCheckDialog` vitest suite plus the extended detail-page test (asserts Check-sources opens the dialog and that the settings PATCH carries `auto_update_sources`).

## 17. Things explicitly NOT decided / out of scope here

- Hybrid RRF fusion of keyword + vector in a single call (optional future, same engine).
- Reranking / HyDE / multi-query / LLM synthesis on retrieval — the agent synthesizes.
- Agents editing KB documents — KB is user-curated; revisit later.
- Image OCR / audio transcription by default.
- A filesystem watcher on by default.
- Final converter library per format (MarkItDown vs Docling) and local-model MTEB/CPU benchmarks — operational tuning behind the converter/embedder ports; no re-modelling needed.
- sqlite-vec packaging on macOS arm64 + Linux — guarded by `importorskip`; a load failure degrades vector to keyword, never blocks.
