# Feature Specification: Knowledge Base (redesign)

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-06-09
**Status**: Accepted (redesign — in development)
**Input**: A from-scratch redesign of the `knowledge_base` resource kind. A Knowledge Base is one face of a shared **knowledge substrate**: the user uploads files in **any format**, Coffer cleans and normalizes each to **Markdown on disk** (the source of truth), and serves them back over three retrieval modes (`grep`, `keyword`, `vector`). SQLite is a rebuildable index only. Documents are **co-managed by humans and agents** ([ADR-028](../../docs/decisions/ADR-028-knowledge-base-documents-co-managed.md)): both read AND write through Coffer's MCP gateway, every write is audited (F01). See [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) for the substrate rationale and [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) for architecture.

## User Scenarios & Testing

### User Story 1 — Build a knowledge base from arbitrary files (Priority: P1)

A developer has design notes, ADRs, internal wikis, PDFs of papers, a spreadsheet, and some HTML pages. They drop them all into Coffer regardless of format. Coffer converts each to clean Markdown, keeps the original for provenance, and indexes the result so an agent can retrieve from it.

**Why this priority**: This is the core of the spec. Without it there is no knowledge base.

**Independent Test**: From a fresh install, create a KB `design-notes`, upload a `.md`, a `.pdf`, a `.docx`, and a `.csv`; observe each becomes a Markdown file under `~/.coffer/knowledge/design-notes/docs/`, the original under `raw/`, and a row in the unified `documents` table.

**Covering scenarios**: create a knowledge base; ingest converts any format to markdown; list documents in a knowledge base; delete a single document; delete a knowledge base cleans up files and index.

---

### User Story 2 — Retrieve in three modes (Priority: P1)

The same corpus is queried several ways: `grep` (exact/regex over the Markdown files, zero index), `keyword` (SQLite FTS5 + BM25), `vector` (sqlite-vec with a configured embedding provider), and `hybrid` (reciprocal rank fusion of keyword + vector, so exact/CJK/identifier hits and paraphrase hits reinforce each other). The KB declares a default mode; a caller may override it. Vector or hybrid requested without a configured embedding provider falls back to keyword, flagged — never blocked.

**Why this priority**: Retrieval is the product. The three modes cover offline/zero-config use through to semantic search.

**Independent Test**: With a populated KB, run a keyword search and a grep query (both work with no embedding config); configure an embedding provider, run a vector search; remove the config, request vector again, observe a keyword fallback flagged in the response.

**Covering scenarios**: keyword search returns ranked passages; grep returns file/line matches; vector search returns ranked passages; vector falls back to keyword when embedding unconfigured; hybrid search fuses keyword and vector via RRF.

---

### User Story 3 — Agent reads AND writes through the MCP gateway (Priority: P1)

The developer's coding agent connects to Coffer's MCP endpoint and gets built-in KB tools: read tools (list KBs, search, grep, read a full document) AND write tools (add a document, edit a document, delete a document). Documents are co-managed: an agent can contribute and curate alongside the human. Every agent write is audited (F01) with the agent as actor, funnels through the same idempotent re-index routine humans use.

**Why this priority**: Agent-side retrieval is what makes the KB useful during coding; agent-side curation makes it a living, co-managed knowledge store rather than a static vault (ADR-028).

**Independent Test**: With a populated KB, an MCP client sees `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document`, `coffer__add_document`, `coffer__edit_document`, and `coffer__delete_document`; calling `coffer__add_document` creates a searchable document.

**Covering scenarios**: built-in KB tools appear in client tool list; agent searches a knowledge base; agent greps a knowledge base; agent reads a document; agent adds a document via MCP; agent edits a document via MCP; agent deletes a document via MCP.

---

### User Story 4 — Curate the corpus: edit, reindex, re-embed (Priority: P2)

The user fixes a conversion artifact by opening the document's Markdown in their own external editor (or via the edit API), then the change is picked up. They re-upload an updated version of a file under the same name and Coffer updates the **same document in place** (stable ULID id — no duplicate). They change chunk parameters or the embedding model and Coffer re-indexes/re-embeds the corpus. The Coffer UI renders the Markdown read-only — it never offers an in-app text editor — and instead offers affordances to open the document (or its containing folder) in the user's external editor or reveal it in the file manager (daemon-backed on the web, native on the desktop). Once a document is edited (`source_mode = edited`), re-conversion from the raw original is blocked to avoid clobbering edits.

**Why this priority**: A KB is curated over time; one-shot ingest is not enough. Not required to demonstrate the core value.

**Independent Test**: Edit a doc's Markdown via the edit API (or by editing the on-disk file in an external editor), confirm the next read/search reflects the edit via lazy reindex-on-read; re-upload a changed version of the same file with `replace=true` and observe the SAME document id updated in place; change the KB's chunk size and confirm the corpus is re-chunked and re-indexed.

**Covering scenarios**: edit a document and reindex; external edit picked up by reindex-on-read; re-conversion blocked once edited; re-upload of an updated file updates the document in place; re-upload of an identical file is a no-op; changing chunk params re-indexes; changing embedding model re-embeds.

---

### User Story 5 — Manage from desktop and CLI, and observe (Priority: P2)

The user manages KBs from the desktop UI under `Resources` and from `coffer kb …` subcommands, and inspects per-KB metrics (document count, chunk count, disk usage, indexed modes, and the count of documents whose vector embed is pending because the provider was unavailable).

**Why this priority**: Required for non-CLI users and for scripting; not blocking the core flow.

**Independent Test**: Create a KB in the UI, drag files in, search; from the terminal ingest a directory, grep, and read metrics as JSON.

**Covering scenarios**: KB metrics report counts and disk usage; degraded embed surfaces documents_degraded and retries without re-chunking; (UI/CLI flows deferred to e2e — see note).

---

### Edge Cases

- **Unsupported format**: A file with no converter for its type is rejected with `IngestRejected("unsupported_type")`; nothing is persisted.
- **Converter library missing**: If the converter engine for a format is not installed, ingest of that format returns `EngineUnavailable` naming the missing dependency; the daemon stays up and other formats still ingest.
- **Empty conversion**: A file that converts to empty/whitespace-only Markdown is rejected with `IngestRejected("empty")`. A **PDF** that converts empty is rejected with the more specific `IngestRejected("scanned_pdf")` (same 415 status) so the UI can surface an actionable "looks scanned/image-only — run OCR" message instead of the generic one.
- **Oversized file**: A file over `max_document_bytes` (default 25 MB) is rejected at the API boundary before any conversion runs.
- **Re-upload, identical bytes**: A re-upload of a file whose bytes are unchanged (its `source_sha256` matches the document already stored under that filename) is an idempotent no-op — the existing document is returned, nothing is re-written or re-audited.
- **Re-upload, changed bytes, same filename**: A re-upload of an updated file under a name already in the KB updates the **same document in place** (the ULID id is reused, `docs/`+`raw/` are overwritten keeping only the latest original, `source_mode` resets to `converted`) — but only when the caller passes `replace=true`; without it the upload is rejected (`duplicate`) so the overwrite is always explicit.
- **Vector requested, embedding unconfigured**: Search falls back to keyword and flags `fallback="keyword"` in the response; it never errors.
- **Re-conversion after edit**: Re-converting a document whose `source_mode == edited` is rejected; re-uploading a changed source (with `replace=true`) updates it in place and resets it to `converted`.
- **Reindex of unchanged content**: Reindexing a document whose Markdown `content_sha256` is unchanged is a no-op.
- **Concurrent searches**: Multiple searches against one KB run independently; no per-KB lock degrades read latency.
- **Tracked source moved/deleted**: When a document's tracked external `source_path` is moved or deleted, `check_sources` reports it as `missing` and never crashes; `source_path` is machine-local, so a `missing` result on a different machine (after sync) is expected and benign.

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

### Scenario: keyword search matches CJK (Chinese) content

- **Given** a knowledge base with a document whose Markdown body is Chinese (no word-boundary spaces),
- **When** the user runs a keyword search with a CJK query,
- **Then** a multi-character query (e.g. `向量检索`) matches via the FTS5 trigram index, and a short `< 3`-character query (e.g. `向量`) matches via the substring fallback — neither returns empty as the old `unicode61` tokenizer did.

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

### Scenario: hybrid search fuses keyword and vector via RRF

- **Given** a KB with vector enabled and documents embedded,
- **When** the user searches with `mode="hybrid"`,
- **Then** Coffer runs BOTH keyword and vector searches and fuses them by reciprocal rank fusion (`K = 60`, deduped by `(document_id, position)`), so a passage ranked by both lists outranks single-list hits, and returns the fused top-k.

### Scenario: edit a document and reindex

- **Given** a converted document exists,
- **When** the user replaces its Markdown body through the edit API,
- **Then** `source_mode` becomes `edited`, the single re-index routine deletes old chunks/FTS5/vec rows and re-chunks (re-embedding if vector is enabled), and subsequent search reflects the edit.

### Scenario: external edit picked up by reindex-on-read

- **Given** a document whose Markdown file is edited out-of-band in the user's external editor (no API call),
- **When** the user next reads or searches that document,
- **Then** the lazy reindex-on-read scan detects the drifted `content_sha256`, re-indexes through the single idempotent routine, and the read/search reflects the edit — with no filesystem watcher running.

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
- **Then** the read tools `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document` AND the write tools `coffer__add_document`, `coffer__edit_document`, `coffer__delete_document` are present (documents are co-managed — ADR-028).

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

### Scenario: agent adds a document via MCP

- **Given** a knowledge base exists,
- **When** the client calls `coffer__add_document(kb, filename, content)` with Markdown content,
- **Then** Coffer ingests it like a human upload (a new ULID-id document, `docs/`+`raw/` written, indexed), records audit `KB_DOCUMENT_INGESTED` with the agent as actor, and the document is searchable.

### Scenario: agent edits a document via MCP

- **Given** a converted document exists,
- **When** the client calls `coffer__edit_document(kb, doc_id, content)`,
- **Then** the body is replaced, `source_mode` becomes `edited`, the corpus is reindexed, and audit `KB_DOCUMENT_UPDATED` is recorded with the agent as actor.

### Scenario: agent deletes a document via MCP

- **Given** a document exists in a KB,
- **When** the client calls `coffer__delete_document(kb, doc_id)`,
- **Then** the document's files and index rows are removed, audit `KB_DOCUMENT_DELETED` is recorded with the agent as actor, and search no longer returns it.

### Scenario: re-upload of an updated file updates the document in place

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads a changed `report.md` with `replace=true`,
- **Then** the SAME document id is updated in place (raw + markdown overwritten, only the latest original kept, `source_mode` reset to `converted`), no second document is created, and audit `KB_DOCUMENT_UPDATED` is recorded.

### Scenario: re-upload of an identical file is a no-op

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads the byte-identical `report.md`,
- **Then** it is an idempotent no-op: the existing document is returned, no second document is created, and no `KB_DOCUMENT_UPDATED` audit is recorded.

### Scenario: KB metrics report counts and disk usage

- **Given** a KB has documents,
- **When** the user opens its detail view (UI or `coffer kb describe`),
- **Then** they see document count, chunk count, the indexed retrieval modes, the count of documents with a pending vector embed (`documents_degraded`), and the on-disk byte size of `knowledge/<name>/`.

### Scenario: degraded embed surfaces documents_degraded and retries without re-chunking

- **Given** a vector-enabled KB whose embedding provider is unavailable when a document is ingested,
- **When** the document is indexed keyword-only and the user later reads the KB (list / search / metrics) with the provider still down, then again once it is restored,
- **Then** the document carries its real `content_sha256` and a persisted `embed_pending` flag, `documents_degraded` reports `1` on the degraded read, and the next reconcile retries **only** the embed (no re-chunk / FTS rewrite — the chunk rows are unchanged), clearing `embed_pending` so `documents_degraded` returns to `0`.

### Scenario: check sources detects changed, unchanged, and missing originals

- **Given** documents ingested from external files (their absolute `source_path` recorded in metadata),
- **When** the user runs `check_sources` after one original is edited on disk, one is left untouched, and one is deleted,
- **Then** the report classifies them as `changed`, `unchanged`, and `missing` respectively (by re-hashing each external file against the stored `source_sha256`), and nothing is re-indexed or audited by the detection itself.

### Scenario: update from source refreshes a changed document in place

- **Given** a converted document whose external `source_path` original has changed on disk,
- **When** the user runs `update_from_source` for that document,
- **Then** Coffer re-ingests it from the tracked file in place (same ULID id, `source_mode` stays `converted`), the new content is searchable and the old content is gone, and `KB_DOCUMENT_UPDATED` is audited.

### Scenario: update from source refuses an edited document

- **Given** a document whose `source_mode == edited`,
- **When** the user runs `update_from_source` for it,
- **Then** Coffer refuses with the re-conversion-blocked error (hand edits are never clobbered), and `check_sources` reports that document as `edited` rather than overwriting it.

### Scenario: auto_update_sources refreshes changed sources on check

- **Given** a KB with `auto_update_sources` enabled and a document whose external original has changed,
- **When** the user runs `check_sources`,
- **Then** the changed document is auto-refreshed in place (reported `updated`) and `KB_DOCUMENT_UPDATED` is audited, while a hand-edited changed document would be skipped (reported `edited`).

### Scenario: test an embedding model

- **Given** an embedding provider, model id, and (where required) credential ref,
- **When** the user tests the embedding model,
- **Then** Coffer requests one embedding and reports success with the returned
  vector dimension, or a humanized failure message, without persisting anything.

> **Deferred to future test work** (frontend Playwright + full-CLI e2e): create/upload/search/delete a KB through the desktop app; CLI covers every desktop operation; CLI search/grep return machine-readable JSON. Listed for completeness; `make verify-acceptance` does not gate on them.

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support the resource kind `knowledge_base` on the shared knowledge substrate; users MUST create, list, view, update (description + retrieval config), enable, disable, and delete KBs through the kind-agnostic Resource framework.
- **FR-002**: System MUST validate each KB's config (enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref) against a Pydantic schema by `kind`, reject duplicate names, and persist nothing on failure.
- **FR-003**: System MUST store each KB under `~/.coffer/knowledge/<name>/` with normalized Markdown at `docs/<doc-id>.md` (source of truth) and the original at `raw/<doc-id>.<ext>` (provenance). There are NO per-corpus `index/`/`chroma/` directories — all indexing lives in `coffer.db`.

**Ingestion & conversion**

- **FR-004**: Users MUST be able to upload a file of any supported format; the system MUST detect format, convert to Markdown via a pluggable `MarkdownConverter` port, clean the output, prepend YAML frontmatter, write `docs/`+`raw/`, and index it.
- **FR-005**: Conversion MUST dispatch through a per-format converter registry confined to `infrastructure/`: Markdown/text/source files pass through unchanged, `csv` has a dedicated converter, and everything else (pdf / docx / pptx / xlsx / xls / html / epub / …) goes through the default MarkItDown engine. Formats MarkItDown has no converter for (legacy binary `.doc`/`.ppt`, `.rtf`, `.odt`) are rejected as `unsupported_type`, not advertised. A higher-fidelity engine for a format is a new converter in the registry, not a substrate change.
- **FR-006**: System MUST reject files over `max_document_bytes` (default 25 MB, configurable), files of unsupported type, and files whose conversion yields empty Markdown.
- **FR-007**: Each document MUST be identified by a **stable ULID** minted at first ingest (not a content hash). The system MUST compute `source_sha256` of the original (kept in `metadata` as provenance) and match a re-upload to an existing document by `original_filename` within the store: a **byte-identical** re-upload is an idempotent no-op; a **changed** re-upload of a filename already present updates the **same document in place** (reuse the id) only when `replace=true`, otherwise it is rejected (`duplicate`); a **new** filename is a new document. Re-uploading the SAME file (same name) into two different KBs yields two independent documents (KB documents are not deduplicated across stores).

**Storage as source of truth**

- **FR-008**: Markdown files MUST be the sole source of truth; SQLite (`documents`, `chunks`, FTS5, sqlite-vec) is a derived, rebuildable index. A reindex routine MUST be able to reconstruct all SQLite state from the files.
- **FR-008a**: The KB MUST use **lazy reindex-on-read**: a read or search first detects on-disk drift by `content_sha256` and reconciles the index through the single idempotent re-index routine (FR-016) before serving, so out-of-band edits — including edits made in the user's external editor — are visible immediately with no filesystem watcher running.
- **FR-009**: System MUST use one unified `documents` table shared with the `memory` kind, discriminated by `kind` and a per-face JSON `metadata` column. There is no `kb_documents` table.

**Retrieval**

- **FR-010**: Users MUST be able to search a KB and receive ranked passages (passage text + source doc id + title + score) via the requested or default mode. Default `top_k` is 5; callers MAY set `top_k` in 1–20.
- **FR-011**: System MUST support four retrieval modes: `grep` (ripgrep over `docs/`, bounded by max-matches + timeout, no index), `keyword` (FTS5 `MATCH` ordered by `bm25()`), `vector` (sqlite-vec KNN over embeddings), and `hybrid` (reciprocal rank fusion of `keyword` + `vector`, ADR-012). Default enabled modes are `keyword`+`grep`; `vector` is opt-in, and enabling `vector` also enables `hybrid` (which fuses both lists). Grep responses carry a `truncated` flag that is true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed). The keyword index uses an FTS5 **trigram** tokenizer so CJK and substring queries match — `unicode61` does not segment CJK text (no word-boundary spaces), so a query like `向量检索` returned nothing; a query with no token of ≥ 3 characters (e.g. a 2-character CJK term) falls back to a bounded substring (LIKE) scan rather than returning empty.
- **FR-011a**: An EXPLICIT `mode=grep` on the search endpoint — or any explicit mode not in the KB's `enabled_modes` — MUST be rejected with `400 SEARCH_MODE_INVALID` (grep is served by its own endpoint, never silently rewritten). `vector` and `hybrid` are the exceptions: they always reach the retrieval facade so the keyword fallback is FLAGGED per FR-012. An implicit search (no `mode`) on a KB whose `default_mode` is `grep` serves `keyword` (grep is not a passage mode); a vector-enabled KB's `default_mode` is `hybrid` so an implicit search fuses both lists.
- **FR-011b**: `hybrid` mode MUST run BOTH `keyword` and `vector` searches and fuse them by **reciprocal rank fusion** (RRF): each passage's fused score is `Σ_over_lists 1/(K + rank)` with `K = 60` and `rank` the 0-based position in that list; passages are deduped by chunk identity `(document_id, position)` so a passage in both lists sums both contributions and outranks single-list hits. The top-k by fused score are returned. This delivers the "optional hybrid via reciprocal rank fusion" promised by ADR-012.
- **FR-012**: When `vector` (or `hybrid`) is requested but no embedding provider is configured, the system MUST fall back to `keyword` and flag the fallback in the response — it MUST NOT error or block.

**Embedding configuration**

- **FR-013**: The embedding provider MUST be user-configurable per KB via the nested `embedding` config object (DevPilot-style OpenAI-compatible: `provider`, `model`, `base_url`, `credential_ref`, `dimensions`), with an optional in-process `local` provider (fastembed). Credentials MUST be referenced into the encrypted credential store, never stored in plaintext.
- **FR-014**: Chunk parameters and the embedding model MUST be mutable; changing chunk params re-chunks+re-indexes and changing the embedding model re-embeds the corpus. There is NO immutability lock on these fields.

**Curation & consistency**

- **FR-015**: Each document MUST carry a `source_mode` of `converted` (Markdown derived from raw, re-convertible) or `edited` (re-conversion blocked). Document ids are stable ULIDs (FR-007), so re-uploading a changed source under the same filename with `replace=true` updates the same document in place and resets `source_mode` to `converted`; uploading a different filename creates a new document and the edited one is untouched. Document edits arrive through the edit API, the agent MCP `edit_document` tool, or by editing the on-disk Markdown in the user's external editor — the Coffer UI does NOT provide an in-app text editor. An edit through the edit API or MCP sets `source_mode=edited`; an external edit is picked up by lazy reindex-on-read (FR-008a). Users and agents MUST be able to edit a document's Markdown, re-upload/replace its source, delete it, and reindex.
- **FR-016**: All write paths (re-upload, edit API, agent MCP write, external edit, reindex scan) MUST funnel through one idempotent re-index routine, invoked lazily on read when the on-disk `content_sha256` has drifted: if `content_sha256` is unchanged it is a no-op; if changed it deletes old chunks/FTS5/vec rows, re-chunks, re-embeds (if vector enabled), updates the `documents` row, and audits `KB_DOCUMENT_UPDATED`. Documents are **co-managed** (ADR-028): both humans and agents may add, edit, and delete documents; every agent write is audited (FR-018) with the agent as actor.

**Agent integration via MCP**

- **FR-017**: Coffer's MCP gateway MUST expose built-in KB tools to every connected client, namespaced under the reserved `coffer__` prefix: the read tools `coffer__list_knowledge_bases`, `coffer__search_knowledge`, `coffer__grep_knowledge`, `coffer__read_document`, AND the write tools `coffer__add_document` (ingest Markdown content under a filename), `coffer__edit_document` (replace a document's body), and `coffer__delete_document`. The write tools share the same service paths as the REST surface, so they honour the F01 audit (FR-018).
- **FR-018**: Built-in KB tool invocations MUST be recorded in `mcp_invocations` exactly as upstream calls (tool name, who/when/duration/outcome — no arguments or returned content); the document-level effect of a write tool is additionally recorded in the F01 audit trail (`KB_DOCUMENT_INGESTED` / `_UPDATED` / `_DELETED`) with the agent as actor.

**Surfaces**

- **FR-019**: Users MUST be able to perform every KB operation through (a) a REST API under `/api/v1/knowledge_bases/`, (b) `coffer kb …` subcommands, and (c) a desktop UI under the existing `Resources` navigation.
- **FR-020**: The UI document viewer MUST render the Markdown **read-only** — it MUST NOT offer an in-app text editor for document content (humans edit via the external editor or the edit API; agents via MCP). Instead, at both file and containing-folder granularity, the viewer MUST offer affordances to **open in external editor** and **reveal in file manager / Finder**. Open/reveal perform the real OS action on **both** surfaces (honouring the global preferred-editor preference specced in `002-ui-shell`): desktop (Tauri) via the OS opener, the web client via the loopback daemon's filesystem-action endpoints (spec 004 FR-039) — the daemon is always on the user's own machine, so it acts on the user's behalf (ADR-033). There is no copy-path fallback. To support these affordances, read API responses (FR/§Wire) MUST surface the document's absolute on-disk path and its containing folder's absolute path.

**Source-file tracking**

- **FR-021**: A **path-based** ingest (the `coffer kb ingest` CLI, and a future desktop file picker) MUST record the external original's **absolute path** in the document's free-form `metadata` as `source_path` — there is no schema/DB migration; it rides in the existing JSON `metadata`. A web byte-upload and the agent `add_document` MCP tool MUST NOT set or infer `source_path` (an untrusted surface must never populate an arbitrary server path). `source_path` is machine-local: it is meaningful only on the machine that ingested the file.
- **FR-022**: `check_sources` MUST classify each path-tracked document (those with a `source_path`) by re-hashing the external file with sha256 — streamed in chunks so a multi-GB original is never read fully into memory — and comparing to the stored `source_sha256`: `unchanged` (digests match), `changed` (they differ), or `missing` (the file is gone). Detection is **on-demand only** (no filesystem watcher), and detect-only changes nothing and audits nothing.
- **FR-023**: `update_from_source` MUST re-ingest a document from its `source_path` in place — reading the tracked file's bytes and replaying the existing `replace=true` re-ingest path, so the document's stable ULID id is preserved and the corpus is re-chunked/re-indexed (audited via the existing `KB_DOCUMENT_UPDATED`). A document whose `source_mode == edited` MUST be refused (the existing `ReconversionBlocked` error) so hand edits are never clobbered; a vanished or untracked source is reported via the existing `IngestRejected`.
- **FR-024**: A per-KB `auto_update_sources` flag (default **false**) governs `check_sources`: when false, detection only classifies; when true, each `changed` document whose `source_mode != edited` is auto-refreshed in place via `update_from_source` (reported `updated`), while a `changed` hand-edited document is skipped (reported `edited`). Toggling `auto_update_sources` MUST NOT re-chunk or re-embed the corpus (it is not a reindex-triggering field).
- **FR-025**: When an embed degrades because the embedding provider is unavailable (`EngineUnavailable`), the document MUST be indexed keyword-only and its retry state MUST be tracked on a dedicated persisted `embed_pending` flag — decoupled from `content_sha256`, which MUST always carry the real Markdown body hash (so a degraded document is no longer re-chunked + re-FTS'd on every scan, and the files-as-truth sha stays correct). The KB MUST surface the count of such documents as `documents_degraded` in its metrics, computed from the persisted `embed_pending` flag so the count reflects a degrade observed during **any** read (list / get / search / grep), not only an explicit `POST /reindex`. The next reconcile MUST retry **only** the embed for a still-pending document whose body is unchanged — re-chunking it in memory and upserting only the vectors (no FTS / chunk rewrite), clearing `embed_pending` on success.

### Key Entities

- **Knowledge Base** (resource of kind `knowledge_base`): config = enabled retrieval modes, chunk size/overlap, embedding provider/model/base_url/credential_ref, max document bytes, description.
- **Document** (unified `documents` row, `kind="knowledge_base"`): doc id (stable ULID), KB resource name, on-disk path, title, description, `content_sha256` (always the real body hash), `embed_pending` (index-derived retry flag — true when the embed degraded; not file-truth), `source_mode`, per-face `metadata` (`original_filename`, `original_format`, `source_sha256`, `converted_at`, `conversion_engine`), timestamps.
- **Chunk** (`chunks` row): position within a document. The chunk text is stored once inside the regular FTS5 index (`documents_fts`), not duplicated into a base SQLite table; it remains rebuildable from the Markdown files, which stay the source of truth.
- **Passage** (retrieval result, not persisted): passage text, source doc id, title, score, position.
- **Grep hit** (retrieval result, not persisted): path, line number, line.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user creates a KB and ingests their first non-Markdown file (e.g. a PDF) within 60 seconds by following the quickstart alone.
- **SC-002**: With a 50-document KB (≤ 50 MB), keyword search latency for a typical query is ≤ 200 ms and grep ≤ 500 ms wall-clock at the REST surface on a developer laptop.
- **SC-003**: Deleting a KB removes 100% of its on-disk footprint and 100% of its SQLite rows; verified by a test that walks `~/.coffer/knowledge/` and queries `documents`/`chunks` before and after.
- **SC-004**: An agent connected through the MCP gateway can list KBs, search, grep, read a document, AND add / edit / delete a document — all via built-in tools — in one MCP session, with no separate MCP server installed.
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

- **Shared substrate**: `documents`/`chunks`/FTS5/sqlite-vec and the converter port are shared with spec 007 (memory). This spec owns the KB face (any-format→Markdown, three-mode read, human+agent co-managed writes — ADR-028); 007 owns the memory face. Keep the substrate description in sync across both specs; architecture lives in the constitution and the redesign ADR, not restated here.
- **Embedding default**: vector is opt-in; the zero-config default is `keyword`+`grep` (offline, language-agnostic). For bilingual corpora a local `bge-m3` or a cloud provider is recommended (English-only small models embed Chinese poorly).
- **Co-management (ADR-028)**: documents are co-managed by humans and agents. This spec slice ships the co-management core at **global scope** — stable ULID identity + re-upload-updates-in-place (FR-007), agent MCP write tools (FR-017). Two related pieces land with the later unified-知识 UI slice that surfaces them: **per-project document scope** (the 全局/项目 axis, co-dependent with that UI) and a **recoverable soft-delete** (trash/restore, which needs its own UI — for now delete is a hard delete with an F01 audit trail).
- **Deferred**: reranking / HyDE / multi-query / LLM synthesis on retrieval; per-project KB document scope and recoverable soft-delete (next slice, above); an in-app Markdown editor (the viewer stays read-only with external-editor affordances); image OCR by default; a filesystem watcher on by default.
