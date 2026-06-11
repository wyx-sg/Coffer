# Feature Specification: Knowledge Base (redesign)

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-06-09
**Status**: Accepted (redesign — in development)
**Input**: A from-scratch redesign of the `knowledge_base` resource kind. A Knowledge Base is one face of a shared **knowledge substrate**: the user uploads files in **any format**, Coffer cleans and normalizes each to **Markdown on disk** (the source of truth), and serves them back over three retrieval modes (`grep`, `keyword`, `vector`). SQLite is a rebuildable index only. The agent reads the KB through Coffer's MCP gateway; the KB is **user-curated and read-only to agents**. See [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) for the full design rationale and [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) for architecture.

## User Scenarios & Testing

### User Story 1 — Build a knowledge base from arbitrary files (Priority: P1)

A developer has design notes, ADRs, internal wikis, PDFs of papers, a spreadsheet, and some HTML pages. They drop them all into Coffer regardless of format. Coffer converts each to clean Markdown, keeps the original for provenance, and indexes the result so an agent can retrieve from it.

**Why this priority**: This is the core of the spec. Without it there is no knowledge base.

**Independent Test**: From a fresh install, create a KB `design-notes`, upload a `.md`, a `.pdf`, a `.docx`, and a `.csv`; observe each becomes a Markdown file under `~/.coffer/knowledge/design-notes/docs/`, the original under `raw/`, and a row in the unified `documents` table.

**Covering scenarios**: create a knowledge base; ingest converts any format to markdown; list documents; delete a single document; delete a knowledge base cleans up files and index.

---

### User Story 2 — Retrieve in three modes (Priority: P1)

The same corpus is queried three ways: `grep` (exact/regex over the Markdown files, zero index), `keyword` (SQLite FTS5 + BM25), and `vector` (sqlite-vec with a configured embedding provider). The KB declares a default mode; a caller may override it. Vector requested without a configured embedding provider falls back to keyword, flagged — never blocked.

**Why this priority**: Retrieval is the product. The three modes cover offline/zero-config use through to semantic search.

**Independent Test**: With a populated KB, run a keyword search and a grep query (both work with no embedding config); configure an embedding provider, run a vector search; remove the config, request vector again, observe a keyword fallback flagged in the response.

**Covering scenarios**: keyword search returns ranked passages; grep returns file/line matches; vector search returns ranked passages; vector falls back to keyword when embedding unconfigured.

---

### User Story 3 — Agent retrieves through the MCP gateway, read-only (Priority: P1)

The developer's coding agent connects to Coffer's MCP endpoint and gets built-in read-only KB tools: list KBs, search, grep, read a full document. The agent never writes to a KB.

**Why this priority**: Agent-side retrieval is what makes the KB useful during coding.

**Independent Test**: With a populated KB, an MCP client sees `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, and `coffer__read_document`; calling `coffer__search_knowledge` returns ranked passages; no write tool for KB exists.

**Covering scenarios**: built-in KB tools appear in client tool list; agent searches a knowledge base; agent greps a knowledge base; agent reads a document.

---

### User Story 4 — Curate the corpus: edit, reindex, re-embed (Priority: P2)

The user fixes a conversion artifact by editing the Markdown directly, then reindexes. They re-upload a newer source to re-convert. They change chunk parameters or the embedding model and Coffer re-indexes/re-embeds the corpus. Once a document is hand-edited (`source_mode = edited`), re-conversion from the raw original is blocked to avoid clobbering edits.

**Why this priority**: A KB is curated over time; one-shot ingest is not enough. Not required to demonstrate the core value.

**Independent Test**: Edit a doc's Markdown via the API, reindex, confirm search reflects the edit; attempt re-conversion of that doc and observe it is blocked; change the KB's chunk size and confirm the corpus is re-chunked and re-indexed.

**Covering scenarios**: edit a document and reindex; re-conversion blocked once edited; changing chunk params re-indexes; changing embedding model re-embeds.

---

### User Story 5 — Manage from desktop and CLI, and observe (Priority: P2)

The user manages KBs from the desktop UI under `Resources` and from `coffer kb …` subcommands, and inspects per-KB metrics (document count, chunk count, disk usage, indexed modes).

**Why this priority**: Required for non-CLI users and for scripting; not blocking the core flow.

**Independent Test**: Create a KB in the UI, drag files in, search; from the terminal ingest a directory, grep, and read metrics as JSON.

**Covering scenarios**: KB metrics report counts and disk usage; (UI/CLI flows deferred to e2e — see note).

---

### Edge Cases

- **Unsupported format**: A file with no converter for its type is rejected with `IngestRejected("unsupported_type")`; nothing is persisted.
- **Converter library missing**: If the converter engine for a format is not installed, ingest of that format returns `EngineUnavailable` naming the missing dependency; the daemon stays up and other formats still ingest.
- **Empty conversion**: A file that converts to empty/whitespace-only Markdown is rejected with `IngestRejected("empty")`.
- **Oversized file**: A file over `max_document_bytes` (default 25 MB) is rejected at the API boundary before any conversion runs.
- **Duplicate upload**: A re-upload whose `source_sha256` already exists is rejected unless the caller passes `replace=true`.
- **Vector requested, embedding unconfigured**: Search falls back to keyword and flags `fallback="keyword"` in the response; it never errors.
- **Re-conversion after edit**: Re-converting a document whose `source_mode == edited` is rejected; re-uploading a new source resets it to `converted`.
- **Reindex of unchanged content**: Reindexing a document whose Markdown `content_sha256` is unchanged is a no-op.
- **Concurrent searches**: Multiple searches against one KB run independently; no per-KB lock degrades read latency.

## Acceptance Scenarios

Per [`agents/sdd.md`](../../agents/sdd.md) and [`agents/testing.md`](../../agents/testing.md), every scenario below is referenced by at least one test marked `@pytest.mark.acceptance(spec="006-knowledge-base", scenario="…")`.

### Scenario: create a knowledge base

- **Given** the daemon is running and no knowledge bases are registered,
- **When** the user creates a KB with a unique name and a retrieval config,
- **Then** the KB is persisted, `~/.coffer/knowledge/<name>/docs/` and `raw/` are created, and listing KBs shows it.

### Scenario: ingest converts any format to markdown

- **Given** a knowledge base exists,
- **When** the user uploads a non-Markdown file (e.g. `.pdf`, `.docx`, `.csv`, `.html`),
- **Then** Coffer converts it to Markdown at `docs/<doc-id>.md` (with YAML frontmatter), preserves the original at `raw/<doc-id>.<ext>`, inserts a `documents` row (`kind="knowledge_base"`, `source_mode="converted"`), chunks it into FTS5, and records audit `KB_DOCUMENT_INGESTED`.

### Scenario: list documents in a knowledge base

- **Given** documents have been ingested,
- **When** the user lists documents,
- **Then** they see one row per document with stable doc ids, titles, original filenames, and timestamps, paginated.

### Scenario: keyword search returns ranked passages

- **Given** documents are indexed,
- **When** the user searches with `mode="keyword"` (or the KB default),
- **Then** they receive passages ranked by `bm25()`, each carrying its source doc id, title, snippet, and score.

### Scenario: grep returns file/line matches

- **Given** documents are on disk,
- **When** the user greps the KB with a pattern,
- **Then** Coffer runs ripgrep over `docs/` (bounded by max-matches and a timeout) and returns `{path, line_number, line}` hits with no index involved.

### Scenario: vector search returns ranked passages

- **Given** the KB has an embedding provider configured and documents embedded,
- **When** the user searches with `mode="vector"`,
- **Then** Coffer embeds the query, runs a sqlite-vec KNN, and returns top-k passages with similarity scores.

### Scenario: vector falls back to keyword when embedding unconfigured

- **Given** the KB has no embedding provider configured,
- **When** the user searches with `mode="vector"`,
- **Then** Coffer runs a keyword search instead and the response is flagged `fallback="keyword"`; no error is raised.

### Scenario: edit a document and reindex

- **Given** a converted document exists,
- **When** the user edits its Markdown body and triggers reindex,
- **Then** `source_mode` becomes `edited`, the single re-index routine deletes old chunks/FTS5/vec rows and re-chunks (re-embedding if vector is enabled), and subsequent search reflects the edit.

### Scenario: re-conversion blocked once edited

- **Given** a document whose `source_mode == edited`,
- **When** the user requests re-conversion from the raw original,
- **Then** Coffer rejects it with a clear error; re-uploading a new source file resets `source_mode` to `converted`.

### Scenario: changing chunk params re-indexes

- **Given** a KB with indexed documents,
- **When** the user changes `chunk_size` or `chunk_overlap`,
- **Then** Coffer re-chunks and re-indexes the corpus (and re-embeds if vector is enabled) — chunk params are mutable, not locked.

### Scenario: changing embedding model re-embeds

- **Given** a KB with vector indexing enabled and an embedding model set,
- **When** the user changes the embedding model,
- **Then** Coffer re-embeds the corpus into sqlite-vec — the embedding model is mutable, not locked.

### Scenario: delete a single document

- **Given** a KB has documents,
- **When** the user deletes one document by id,
- **Then** the `docs/<doc-id>.md` and `raw/<doc-id>.<ext>` files are removed, its chunks/FTS5/vec rows are deleted, the `documents` row is removed, audit `KB_DOCUMENT_DELETED` is recorded, and search no longer returns it.

### Scenario: delete a knowledge base cleans up files and index

- **Given** a KB has documents and an index,
- **When** the user deletes the KB,
- **Then** all of its `documents`/`chunks`/FTS5/vec rows are removed, `~/.coffer/knowledge/<name>/` is removed, and the Resource row is deleted.

### Scenario: built-in KB tools appear in client tool list

- **Given** an MCP client connects to Coffer's gateway,
- **When** it lists tools,
- **Then** `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, and `coffer__read_document` are present; no KB write tool exists.

### Scenario: agent searches a knowledge base

- **Given** a KB with indexed documents,
- **When** the client calls `coffer__search_knowledge(kb, query, top_k?, mode?)`,
- **Then** Coffer returns ranked passages structured for LLM consumption (passage + source doc id + score).

### Scenario: agent greps a knowledge base

- **Given** a KB with documents on disk,
- **When** the client calls `coffer__grep_knowledge(kb, pattern)`,
- **Then** Coffer returns file/line matches.

### Scenario: agent reads a document

- **Given** a document exists in a KB,
- **When** the client calls `coffer__read_document(kb, doc_id)`,
- **Then** Coffer returns the document's Markdown body and frontmatter, or a clear error if the id is unknown.

### Scenario: KB metrics report counts and disk usage

- **Given** a KB has documents,
- **When** the user opens its detail view (UI or `coffer kb describe`),
- **Then** they see document count, chunk count, the indexed retrieval modes, and the on-disk byte size of `knowledge/<name>/`.

> **Deferred to future test work** (frontend Playwright + full-CLI e2e): create/upload/search/delete a KB through the desktop app; CLI covers every desktop operation; CLI search/grep return machine-readable JSON. Listed for completeness; `make verify-acceptance` does not gate on them.

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support the resource kind `knowledge_base` on the shared knowledge substrate; users MUST create, list, view, update (description + retrieval config), enable, disable, and delete KBs through the kind-agnostic Resource framework.
- **FR-002**: System MUST validate each KB's config (enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref) against a Pydantic schema by `kind`, reject duplicate names, and persist nothing on failure.
- **FR-003**: System MUST store each KB under `~/.coffer/knowledge/<name>/` with normalized Markdown at `docs/<doc-id>.md` (source of truth) and the original at `raw/<doc-id>.<ext>` (provenance). There are NO per-corpus `index/`/`chroma/` directories — all indexing lives in `coffer.db`.

**Ingestion & conversion**

- **FR-004**: Users MUST be able to upload a file of any supported format; the system MUST detect format, convert to Markdown via a pluggable `MarkdownConverter` port, clean the output, prepend YAML frontmatter, write `docs/`+`raw/`, and index it.
- **FR-005**: Conversion MUST dispatch through a per-format converter registry confined to `infrastructure/`: Markdown/text/source files pass through unchanged, `csv` has a dedicated converter, and everything else (pdf / docx / pptx / xlsx / html / epub / odt / rtf / …) goes through the default MarkItDown engine. A higher-fidelity engine for a format is a new converter in the registry, not a substrate change.
- **FR-006**: System MUST reject files over `max_document_bytes` (default 25 MB, configurable), files of unsupported type, and files whose conversion yields empty Markdown.
- **FR-007**: System MUST compute `source_sha256` of the original and reject re-upload of an existing source unless `replace=true`.

**Storage as source of truth**

- **FR-008**: Markdown files MUST be the sole source of truth; SQLite (`documents`, `chunks`, FTS5, sqlite-vec) is a derived, rebuildable index. A reindex routine MUST be able to reconstruct all SQLite state from the files.
- **FR-009**: System MUST use one unified `documents` table shared with the `memory` kind, discriminated by `kind` and a per-face JSON `metadata` column. There is no `kb_documents` table.

**Retrieval**

- **FR-010**: Users MUST be able to search a KB and receive ranked passages (passage text + source doc id + title + score) via the requested or default mode. Default `top_k` is 5; callers MAY set `top_k` in 1–20.
- **FR-011**: System MUST support three retrieval modes: `grep` (ripgrep over `docs/`, bounded by max-matches + timeout, no index), `keyword` (FTS5 `MATCH` ordered by `bm25()`), and `vector` (sqlite-vec KNN over embeddings). Default enabled modes are `keyword`+`grep`; `vector` is opt-in. Grep responses carry a `truncated` flag that is true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed).
- **FR-011a**: An EXPLICIT `mode=grep` on the search endpoint — or any explicit mode not in the KB's `enabled_modes` — MUST be rejected with `400 SEARCH_MODE_INVALID` (grep is served by its own endpoint, never silently rewritten). `vector` is the one exception: it always reaches the retrieval facade so the keyword fallback is FLAGGED per FR-012. An implicit search (no `mode`) on a KB whose `default_mode` is `grep` serves `keyword` (grep is not a passage mode).
- **FR-012**: When `vector` is requested but no embedding provider is configured, the system MUST fall back to `keyword` and flag the fallback in the response — it MUST NOT error or block.

**Embedding configuration**

- **FR-013**: The embedding provider MUST be user-configurable per KB (DevPilot-style OpenAI-compatible: `embedding_provider`, `embedding_model`, `embedding_base_url`, `embedding_credential_ref`), with an optional in-process `local` provider (fastembed). Credentials MUST be referenced via the keychain, never stored in plaintext.
- **FR-014**: Chunk parameters and the embedding model MUST be mutable; changing chunk params re-chunks+re-indexes and changing the embedding model re-embeds the corpus. There is NO immutability lock on these fields.

**Curation & consistency**

- **FR-015**: Each document MUST carry a `source_mode` of `converted` (Markdown derived from raw, re-convertible) or `edited` (hand-edited; re-conversion blocked until a new source is uploaded). Users MUST be able to edit a document's Markdown, re-upload its source, delete it, and reindex.
- **FR-016**: All write paths (re-upload, edit, reindex scan) MUST funnel through one idempotent re-index routine: if `content_sha256` is unchanged it is a no-op; if changed it deletes old chunks/FTS5/vec rows, re-chunks, re-embeds (if vector enabled), updates the `documents` row, and audits `KB_DOCUMENT_UPDATED`. The KB is **agent-read-only**; agents MUST NOT write KB documents.

**Agent integration via MCP**

- **FR-017**: Coffer's MCP gateway MUST expose read-only built-in tools `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, and `coffer__read_document` to every connected client, namespaced under the reserved `coffer__` prefix.
- **FR-018**: Built-in KB tool invocations MUST be recorded in `mcp_invocations` exactly as upstream calls (tool name, who/when/duration/outcome — no arguments or returned content).

**Surfaces**

- **FR-019**: Users MUST be able to perform every KB operation through (a) a REST API under `/api/v1/knowledge_bases/`, (b) `coffer kb …` subcommands, and (c) a desktop UI under the existing `Resources` navigation.

### Key Entities

- **Knowledge Base** (resource of kind `knowledge_base`): config = enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref, max document bytes, description.
- **Document** (unified `documents` row, `kind="knowledge_base"`): doc id, KB resource name, on-disk path, title, description, `content_sha256`, `source_mode`, per-face `metadata` (`original_filename`, `original_format`, `source_sha256`, `converted_at`, `conversion_engine`), timestamps.
- **Chunk** (`chunks` row): position within a document. The chunk text is stored once inside the regular FTS5 index (`documents_fts`), not duplicated into a base SQLite table; it remains rebuildable from the Markdown files, which stay the source of truth.
- **Passage** (retrieval result, not persisted): passage text, source doc id, title, score, position.
- **Grep hit** (retrieval result, not persisted): path, line number, line.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user creates a KB and ingests their first non-Markdown file (e.g. a PDF) within 60 seconds by following the quickstart alone.
- **SC-002**: With a 50-document KB (≤ 50 MB), keyword search latency for a typical query is ≤ 200 ms and grep ≤ 500 ms wall-clock at the REST surface on a developer laptop.
- **SC-003**: Deleting a KB removes 100% of its on-disk footprint and 100% of its SQLite rows; verified by a test that walks `~/.coffer/knowledge/` and queries `documents`/`chunks` before and after.
- **SC-004**: An agent connected through the MCP gateway can list KBs, search, grep, and read a document — all via read-only built-in tools — in one MCP session, with no separate MCP server installed.
- **SC-005**: `coffer kb reindex <name>` rebuilds all SQLite index state for the KB purely from the Markdown files (drop the rows, reindex, search returns identical results).
- **SC-006**: Every Acceptance Scenario is covered by at least one `acceptance(spec="006-knowledge-base", scenario="…")` test; `make verify-acceptance` reports zero uncovered scenarios.
- **SC-007**: Engine isolation holds: no module under `coffer.application.*` or `coffer.domain.*` imports `markitdown`, `docling`, `sqlite_vec`, or an embedding-provider SDK (importlinter contract).

## Assumptions

- The user runs Coffer on their own machine; no multi-tenant or remote-access requirement. Multi-machine sync is out of scope (constitutional).
- Keyword + grep are zero-config and offline; vector retrieval reaches a configured embedding provider, which MAY be a third-party API (allowed by the constitution — only user _data_ stays local).
- This branch is **unreleased**; there is **no data migration**. A single migration drops `kb_documents`, deletes old per-corpus dirs, and creates the unified schema.
- `ripgrep` is available on supported platforms (macOS arm64, Linux); sqlite-vec loads as a SQLite extension on those platforms.
- The KB is **not** a memory store: it holds user-curated documents. The `memory` kind (spec 007) is the writable face of the same substrate; both share the `documents` table but are discriminated by `kind`.

## Notes for reviewers

- **Shared substrate**: `documents`/`chunks`/FTS5/sqlite-vec and the converter port are shared with spec 007 (memory). This spec owns the KB face (any-format→Markdown, three-mode read, agent-read-only); 007 owns the memory face. Keep the substrate description in sync across both specs; architecture lives in the constitution and the redesign ADR, not restated here.
- **Embedding default**: vector is opt-in; the zero-config default is `keyword`+`grep` (offline, language-agnostic). For bilingual corpora a local `bge-m3` or a cloud provider is recommended (English-only small models embed Chinese poorly).
- **Deferred**: reranking / HyDE / multi-query / LLM synthesis on retrieval; agents editing KB documents; image OCR by default; a filesystem watcher on by default.
