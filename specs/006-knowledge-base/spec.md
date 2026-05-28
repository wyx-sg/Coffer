# Feature Specification: Knowledge Base Manager

**Feature Branch**: `feature/kb-manager`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Coffer's fifth feature — manage local knowledge bases that a coding agent can search through Coffer's MCP gateway. A Knowledge Base is a Resource (kind=knowledge_base) holding a collection of documents the user has explicitly added; Coffer chunks, embeds, indexes, and serves them. Built on top of the kind-agnostic Resource framework laid down by 001-mcp-gateway. Engine: LlamaIndex (industry-mainstream RAG framework), behind a thin port so Coffer's application layer never directly imports it."

## User Scenarios & Testing

### User Story 1 — Create a knowledge base from local documents (Priority: P1)

A developer keeps personal documentation — design notes, ADRs, internal wikis, a few PDFs of research papers — scattered across folders. They want to drop those files into Coffer so their coding agent can search across them naturally during work, without uploading anything to a third party.

**Why this priority**: This is the core of the spec. Without it, there is no knowledge base.

**Independent Test**: From a fresh Coffer install, create a knowledge base named "design-notes", upload three markdown files and one PDF, list the documents, run a search query, observe results citing the source files.

**Covering scenarios**:

- create a knowledge base
- ingest a single document
- list documents in a knowledge base
- search returns ranked passages with sources
- delete a single document
- delete a knowledge base cleans up files and index

---

### User Story 2 — Coding agent searches the knowledge base through Coffer's MCP gateway (Priority: P1)

The developer's coding agent (Claude Code, Cursor, etc.) connects to Coffer's MCP endpoint. Through Coffer's built-in tools, the agent can list knowledge bases, search inside one, and fetch a document's full text — without needing any extra MCP server.

**Why this priority**: Without agent-side access, the KB is just a personal file viewer. The agent integration is what makes it useful during coding.

**Independent Test**: With a knowledge base populated, an MCP client connected to Coffer sees `coffer__search_knowledge_base`, `coffer__get_document`, and `coffer__list_knowledge_bases` in its tool list; calling `search_knowledge_base` returns ranked passages.

**Covering scenarios**:

- built-in tools appear in client tool list
- agent searches a knowledge base
- agent fetches a document by id
- agent lists available knowledge bases

---

### User Story 3 — Manage knowledge bases from the desktop app (Priority: P2)

The developer prefers a visual interface for everyday management — creating a KB, dragging files in, browsing documents, trying out a search.

**Why this priority**: Required for non-CLI users and gives a smoother daily UX. Not required to demonstrate the core value.

**Independent Test**: Launch Coffer, create a KB through the form, drag files into the upload area, observe ingestion progress, open the KB detail view, search from the search box, see results.

**Covering scenarios**:

- create a KB through the desktop app
- upload documents through the desktop app
- search from the desktop app
- delete a document from the desktop app

---

### User Story 4 — Manage knowledge bases from the command line (Priority: P2)

The developer scripts ingestion (`for f in docs/*.md; do coffer kb ingest design-notes "$f"; done`) and bulk operations from a terminal.

**Why this priority**: Coffer's audience is developers; a full CLI is table stakes.

**Independent Test**: From a terminal, create a KB, ingest a directory of files, search, delete a document, delete the KB — all without touching the UI.

**Covering scenarios**:

- CLI covers every desktop operation
- CLI search returns machine-readable JSON

---

### User Story 5 — Observe knowledge base operations (Priority: P3)

The developer wants to see when documents were added, what was searched, and how much storage each KB uses, without those logs growing forever.

**Why this priority**: Necessary for trust and debugging but not blocking the basic flow. Retention defaults are sensible.

**Independent Test**: After ingesting and searching several times, open the audit view, see lifecycle entries; open the per-KB metrics, see counts and disk usage; change retention, wait, confirm old entries are pruned.

**Covering scenarios**:

- audit records KB lifecycle changes
- KB metrics show document count and disk usage
- retention policies apply to KB ingestion log

---

### Edge Cases

- **Unsupported file type**: Ingest of a file Coffer does not know how to extract text from (binary blob, image with no OCR pipeline) fails fast with a clear error and persists nothing.
- **Duplicate document**: Re-ingesting a file whose content hash already exists in the KB is rejected with a clear message; the user can pass `--replace` to overwrite (CLI) or confirm in the UI.
- **Very large document**: A document over the configured size limit (default 25 MB) is rejected at the API boundary, before any extraction or embedding runs.
- **Empty document**: A file that extracts to zero characters is rejected — there is nothing to index.
- **Engine unavailable**: If LlamaIndex (or its embedding model) fails to load at daemon startup, KB ingest endpoints return a 503 with a message naming the missing dependency; KBs can still be created and listed but ingest is gated.
- **Disk full mid-ingest**: A partial ingest is rolled back — raw file removed, index unchanged, no orphan row in `kb_documents`.
- **KB deletion while ingest in flight**: Reject the delete with a 409 conflict; the user retries after the in-flight ingest completes.
- **Concurrent search calls**: Multiple search calls against the same KB run independently; no per-KB lock degrades latency.
- **Embedding model swap mid-KB**: Switching a KB's embedding model after documents are indexed is rejected — embedding model is immutable per KB; the user re-creates the KB if they want a different model.

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="006-knowledge-base", scenario="…")`.

### Scenario: create a knowledge base

- **Given** the coffer daemon is running and no knowledge bases are registered,
- **When** the user creates a knowledge base with a unique name and an embedding model selection,
- **Then** the knowledge base is persisted, an empty document index is initialized on disk under `~/.coffer/kb/<name>/`, and listing knowledge bases shows it.

### Scenario: ingest a single document

- **Given** a knowledge base exists,
- **When** the user uploads a single file (markdown / plain text / pdf / source code),
- **Then** the raw file is saved under the KB directory, the text is extracted, chunked, embedded, and indexed, and a row is added to `kb_documents` with id / filename / size / content hash / ingested timestamp.

### Scenario: list documents in a knowledge base

- **Given** documents have been ingested into a knowledge base,
- **When** the user lists documents in that knowledge base,
- **Then** they see one row per document with stable ids, filenames, sizes, and ingested timestamps, paginated.

### Scenario: search returns ranked passages with sources

- **Given** documents have been ingested,
- **When** the user runs a search query against the knowledge base,
- **Then** they receive ranked passages with their source document id and filename, and a relevance score.

### Scenario: delete a single document

- **Given** a knowledge base has documents,
- **When** the user deletes one document by id,
- **Then** the raw file is removed, the corresponding chunks are removed from the index, the row in `kb_documents` is deleted, an audit entry is recorded, and subsequent search no longer returns that document.

### Scenario: delete a knowledge base cleans up files and index

- **Given** a knowledge base has documents and a populated index,
- **When** the user deletes the knowledge base,
- **Then** every document row is removed, the on-disk directory `~/.coffer/kb/<name>/` is removed, any in-memory engine instance is disposed, and the Resource row is deleted.

### Scenario: built-in tools appear in client tool list

- **Given** an MCP client connects to coffer's gateway,
- **When** the client lists tools,
- **Then** the list includes `coffer__list_knowledge_bases`, `coffer__search_knowledge_base`, and `coffer__get_document` alongside any upstream MCP server tools.

### Scenario: agent searches a knowledge base

- **Given** a knowledge base exists with indexed documents,
- **When** the MCP client calls `coffer__search_knowledge_base` with a kb name and query,
- **Then** coffer returns ranked passages structured for direct LLM consumption (text + source document id + score).

### Scenario: agent fetches a document by id

- **Given** a document exists in a knowledge base,
- **When** the MCP client calls `coffer__get_document` with a kb name and document id,
- **Then** coffer returns the document's extracted text and metadata, or a clear error if the id is unknown.

### Scenario: agent lists available knowledge bases

- **Given** zero or more knowledge bases are registered,
- **When** the MCP client calls `coffer__list_knowledge_bases`,
- **Then** coffer returns name, description, document count, and embedding model for each KB.

### Scenario: audit records KB lifecycle changes

- **Given** the user creates, ingests into, deletes from, and deletes a KB,
- **When** they view the audit log,
- **Then** they see one row per change with actor, timestamp, and a payload describing what changed.

### Scenario: KB metrics show document count and disk usage

- **Given** a KB has documents,
- **When** the user opens its detail view (UI or `coffer kb describe`),
- **Then** they see the number of documents and the on-disk byte size of `kb/<name>/`.

> **Deferred to future test work** (frontend Playwright + full-CLI integration): the following scenarios are part of the user-visible contract but their tests will land alongside the e2e test infrastructure rather than in this PR. They are listed here for spec completeness; `make verify-acceptance` does not gate on them.
>
> - create a KB through the desktop app
> - upload documents through the desktop app
> - search from the desktop app
> - delete a document from the desktop app
> - CLI covers every desktop operation (end-to-end with a running daemon)
> - CLI search returns machine-readable JSON
> - retention policies apply to KB ingestion log

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support a new resource kind `knowledge_base`; users MUST be able to create, list, view, update (description and `max_document_bytes` only — other config is immutable), enable, disable, and delete knowledge bases through the existing kind-agnostic Resource framework.
- **FR-002**: System MUST validate every knowledge base configuration (embedding model identifier, chunk size, chunk overlap) against a Pydantic schema, reject duplicates within the kind, and persist nothing on failure.
- **FR-003**: System MUST store each knowledge base's documents under a per-KB directory `~/.coffer/kb/<name>/`, with the raw original file under `raw/` and the index under `index/`. Deletion of the knowledge base MUST remove this directory and the corresponding `kb_documents` rows.

**Document lifecycle**

- **FR-004**: Users MUST be able to ingest a document into a knowledge base; the system MUST extract its text, chunk it, embed it, and add it to the index.
- **FR-005**: System MUST support at minimum the file types: `.md`, `.markdown`, `.txt`, `.rst`, `.pdf`, and common source-code text formats (`.py`, `.js`, `.ts`, `.go`, `.java`, `.rs`, `.c`, `.h`, `.cpp`, `.hpp`, `.sh`, `.yaml`, `.yml`, `.json`).
- **FR-006**: System MUST reject ingestion of files larger than 25 MB by default (configurable per KB), files of unknown text-extractable type, and files whose extracted text is empty.
- **FR-007**: System MUST compute a SHA-256 content hash for every ingested document and reject re-ingestion of an existing hash unless the caller passes an explicit override.
- **FR-008**: Users MUST be able to list documents in a knowledge base (paginated), get a single document's extracted text, and delete a single document. Deletion MUST remove the raw file, the corresponding index entries, and the database row.

**Retrieval**

- **FR-009**: Users MUST be able to search a knowledge base with a natural-language query and receive ranked passages, each carrying its source document id, filename, a text snippet, and a relevance score.
- **FR-010**: The search default MUST return the top 5 passages. Callers MUST be able to specify `top_k` in the range 1–20 inclusive.

**Agent integration via MCP**

- **FR-011**: Coffer's MCP gateway MUST expose built-in tools `coffer__list_knowledge_bases`, `coffer__search_knowledge_base`, and `coffer__get_document` to every connected MCP client, alongside upstream MCP server tools.
- **FR-012**: Built-in tools MUST namespace under the reserved prefix `coffer__` to guarantee no collision with upstream `<server>__<tool>` names.
- **FR-013**: Built-in tool invocations MUST be recorded in the existing `mcp_invocations` table the same way upstream tool calls are (timestamp, capability key, duration, status — no arguments or return content), so retention and audit work uniformly.

**Engine isolation**

- **FR-014**: System MUST keep the RAG engine (LlamaIndex) confined to `coffer/infrastructure/knowledge_base/`. The `domain/` and `application/` layers MUST NOT import LlamaIndex types directly; they interact through the `KnowledgeBaseStore` port.
- **FR-015**: If the engine or its embedding model fails to initialize, the daemon MUST still start; only ingest and search endpoints return 503 with a message naming the missing dependency.

**Observability (LangFuse, optional)**

- **FR-016**: System MUST emit traces around ingest and search through a `Tracer` port. The default tracer is a no-op; setting the environment variable `LANGFUSE_PUBLIC_KEY` (and the related secret/host vars) MUST enable a LangFuse backend transparently.

**Surfaces**

- **FR-017**: Users MUST be able to perform every operation through (a) a REST API under `/api/v1/knowledge_bases/`, (b) `coffer kb …` subcommands, and (c) a desktop UI under the existing `Resources` navigation.

### Key Entities

- **Knowledge Base** (a resource of kind `knowledge_base`): Holds the configuration for one KB — embedding model, chunk size, chunk overlap, max document size, description. Immutable after creation except for description.
- **Document**: One ingested file in a knowledge base. Identified by (kb_name, document_id). Stores filename, size, sha256, mime hint, ingested timestamp, and chunk count. The extracted text is computed on demand from the raw file under `kb/<name>/raw/<document_id><ext>`.
- **Passage** (retrieval result, not persisted): A chunk produced by retrieval — text snippet, document id, filename, score, ordinal position.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can create their first knowledge base and ingest their first document within 60 seconds, with no documentation consulted more than once.
- **SC-002**: With one knowledge base of 50 documents (mix of markdown and PDF totalling ≤ 50 MB), search latency for a typical query is ≤ 500 ms wall-clock on a developer laptop, measured at the REST surface.
- **SC-003**: Deleting a knowledge base removes 100% of its on-disk footprint and 100% of its database rows; verified by an automated test that walks `~/.coffer/kb/` and queries `kb_documents` before and after.
- **SC-004**: A coding agent connected through Coffer's MCP gateway can list KBs, search a KB, and fetch a document — all via built-in tools — within a single MCP session, with no separate MCP server installed.
- **SC-005**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="006-knowledge-base", scenario="…")`; `make verify-acceptance` reports zero uncovered scenarios.
- **SC-006**: Engine isolation is enforced by importlinter: no module under `coffer.application.*` or `coffer.domain.*` imports `llama_index` (verified by a contract listed in `backend/pyproject.toml`).
- **SC-007**: `make verify` (lint + unit + integration + contract + acceptance audit) passes locally and in CI.

## Assumptions

- The user runs Coffer on their own machine. No multi-tenant or remote-access requirement.
- The embedding model runs locally (CPU is sufficient for default model). No outbound cloud calls during ingest or search.
- LlamaIndex remains an actively maintained Python package. If a future version breaks API compatibility, the change is absorbed inside `infrastructure/knowledge_base/llamaindex_store.py` only.
- Single-user concurrency is small (one user, occasional concurrent ingest and search). The system is not designed for fleet-scale RAG.
- The knowledge base is **not** a memory store: it holds documents the user explicitly added. The `memory` kind (spec 007) holds short, derived facts. The two share no schema.

## Notes for reviewers

- **Observability port location**: The kind-agnostic `Tracer` port was extracted in this PR under `application/observability/` rather than left inside `application/knowledge_base/`. The motivation is forward-looking: spec 007 (memory) is anticipated to be the second consumer, and the constitution's "extract cross-cutting after the second feature needs it" rule is being honoured one step early to avoid an immediate refactor when 007 lands. The KB feature is the _only_ current consumer; the LangFuse adapter and the noop default both live there.
- **Retention seeding for KB-specific tables**: US5's last bullet ("retention policies apply to KB ingestion log") is partially deferred — the existing `audit_log` and `mcp_invocations` retention policies cover KB lifecycle and built-in-tool invocation rows respectively. Retention policy seeding for any KB-specific audit/log tables is deferred to a follow-up.
- **CLI test tier**: US4's CLI commands are exercised via the e2e test tier (a running daemon + a subprocess `coffer kb …` call). Unit/integration tests for the CLI module itself are not added in this PR; the CLI thin-shells onto the HTTP surface which has full integration coverage.
