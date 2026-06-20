# Data Model — 006 Knowledge Base (redesign)

> 中文版: [data-model.zh.md](./data-model.zh.md)

Entities, ports, the **unified** SQLite schema (shared with the `memory` kind, spec 007), and the on-disk layout for the KB face of the knowledge substrate. Architecture invariants live in [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md); this file describes only the model.

**Principle**: Markdown files on disk are the **sole source of truth**. Every SQLite row (`documents`, `chunks`, `documents_fts`, `vec_chunks`) is **derived and rebuildable** from the files via the reindex routine. There is no dual source of truth.

## Domain entities

The substrate domain (`backend/coffer/domain/knowledge/`) is shared with the memory kind; the KB-specific config and doc-id helper live in `backend/coffer/domain/knowledge_base/`.

### `KnowledgeBaseConfig` (`domain/knowledge_base/config.py`)

Pydantic v2 `BaseModel`. Held inside `Resource.config` when `kind == "knowledge_base"`. All fields are **mutable** post-creation (changing chunk params or the embedding model triggers reindex/re-embed — there is no immutability lock).

| Field                | Type                      | Notes                                                                                                               |
| -------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `enabled_modes`      | `list[RetrievalMode]`     | Subset of `{"grep","keyword","vector"}`. Default `["keyword","grep"]`. `vector` is opt-in and requires `embedding`. |
| `default_mode`       | `RetrievalMode`           | The mode used when a search omits `mode`. Default `"keyword"`.                                                      |
| `chunk_size`         | `int`                     | Default `512`; range `64–2048`.                                                                                     |
| `chunk_overlap`      | `int`                     | Default `64`; range `0–chunk_size/2`.                                                                               |
| `max_document_bytes` | `int`                     | Default `25 * 1024 * 1024`; range `1024–104857600`.                                                                 |
| `embedding`          | `EmbeddingConfig \| None` | Required only when `vector` is enabled. `None` ⇒ keyword/grep only.                                                 |

### `EmbeddingConfig` (`domain/knowledge/embedder.py`)

DevPilot-style OpenAI-compatible provider abstraction (one `AsyncOpenAI` client with a swappable `base_url`), plus an in-process `local` option.

| Field            | Type          | Notes                                                                                                                                       |
| ---------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `provider`       | `str`         | `"openai"`, `"openrouter"`, `"voyage"`, `"jina"`, `"gemini"`, `"azure"`, `"dashscope"`, `"ollama"`, `"lmstudio"`, or `"local"` (fastembed). |
| `model`          | `str`         | Embedding model id, e.g. `text-embedding-3-small`, `bge-m3`.                                                                                |
| `base_url`       | `str \| None` | OpenAI-compatible endpoint; `None` for the provider default; ignored for `local`.                                                           |
| `credential_ref` | `str \| None` | Encrypted-store ref (never plaintext); `None` for `local` / keyless endpoints. Optional fallback to the LLM credential ref.                 |
| `dimensions`     | `int`         | Vector width; fixes the `vec_chunks` column. Re-embedding on a width change rebuilds the vec table.                                         |

### `Document` (`domain/knowledge/document.py`)

Frozen dataclass; one per Markdown file, **discriminated by `kind`**. KB and memory share this entity; KB-specific data lives in `metadata`.

| Field                       | Type          | Notes                                                                                                                                                             |
| --------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                        | `str`         | Stable **ULID** minted at first ingest (KB + memory) — the doc id and `<doc-id>.md` filename. Decoupled from content; the source hash is kept as provenance only. |
| `kind`                      | `str`         | `"knowledge_base"` for KB rows.                                                                                                                                   |
| `resource_name`             | `str`         | KB resource name.                                                                                                                                                 |
| `path`                      | `str`         | Relative path of the Markdown file, `docs/<doc-id>.md`.                                                                                                           |
| `title`                     | `str`         | From frontmatter / first heading / filename.                                                                                                                      |
| `description`               | `str \| None` | Optional summary.                                                                                                                                                 |
| `content_sha256`            | `str`         | Hash of the **Markdown** body — the reindex no-op gate.                                                                                                           |
| `source_mode`               | `str`         | `"converted"` or `"edited"`.                                                                                                                                      |
| `metadata`                  | `dict`        | Per-face JSON; KB keys below.                                                                                                                                     |
| `created_at` / `updated_at` | `datetime`    | UTC.                                                                                                                                                              |

KB `metadata` keys: `original_filename` (the re-upload match key), `original_format`, `source_sha256` (provenance), `converted_at`, `conversion_engine`.

### `Passage`, `GrepHit`, `SearchResult` (`domain/knowledge/retrieval.py`)

Frozen value objects (not persisted):

- `Passage`: `document_id`, `title`, `text`, `score: float`, `position: int`.
- `GrepHit`: `path`, `line_number: int`, `line`.
- `GrepResult`: `hits: Sequence[GrepHit]`, `truncated: bool` — `truncated` is true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed).
- `SearchResult`: `mode: RetrievalMode`, `passages: Sequence[Passage]`, `fallback: RetrievalMode | None` (set when a requested `vector` search degraded to `keyword`).
- `StoreRef`: `kind`, `resource_name`, `project_id`, `docs_dir` — identifies one logical store (one KB or one memory scope) for the shared retrieval facade.

### Ports (`domain/knowledge/`)

`typing.Protocol`s expressing what Coffer needs, so concrete engines stay in `infrastructure/`:

```python
class MarkdownConverter(Protocol):
    def can_handle(self, fmt: str) -> bool: ...
    async def convert(self, data: bytes, fmt: str) -> tuple[str, dict]: ...  # (markdown, metadata)

class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    @property
    def dimensions(self) -> int: ...

class KnowledgeIndex(Protocol):
    async def upsert_chunks(self, document_id: str, chunks: Sequence[str],
                            vectors: Sequence[Sequence[float]] | None) -> int: ...
    async def delete_chunks(self, document_id: str) -> None: ...
    async def keyword_search(self, resource_name: str, query: str, top_k: int) -> Sequence[Passage]: ...
    async def vector_search(self, resource_name: str, vector: Sequence[float], top_k: int) -> Sequence[Passage]: ...
```

Grep is a separate `infrastructure/knowledge/grep.py` ripgrep wrapper (no index), bounded by max-matches + a timeout.

### Domain errors (added to `domain/errors.py`)

- `KBNotFound` — code `"KB_NOT_FOUND"`.
- `DocumentNotFound` — code `"DOCUMENT_NOT_FOUND"`.
- `IngestRejected` — code `"INGEST_REJECTED"`; reason ∈ `{"empty","too_large","unsupported_type","duplicate"}`.
- `EngineUnavailable` — code `"ENGINE_UNAVAILABLE"`; raised when a converter library / sqlite-vec / embedding provider needed for the requested operation is unavailable.
- `ReconversionBlocked` — code `"RECONVERSION_BLOCKED"`; raised when re-converting a document whose `source_mode == "edited"`.
- `SearchModeInvalid` — code `"SEARCH_MODE_INVALID"` (HTTP 400); raised when a search request names an EXPLICIT `mode=grep` (grep has its own endpoint) or any explicit mode not in the KB's `enabled_modes`. `vector` is the exception — it degrades to keyword with a flagged fallback instead of erroring.

## SQLite schema (unified substrate)

The substrate migration (`0006`) drops the old `kb_documents` / `memory_records` tables and creates the unified schema below (**no data migration** — the branch is unreleased). The `locked` column added by `0025` for the co-management lock is dropped again by a later additive migration (`0027`) when the per-document lock is withdrawn.

```sql
-- One row per Markdown file, shared by KB and memory, discriminated by `kind`.
CREATE TABLE documents (
    id              TEXT      NOT NULL,             -- ULID (KB + memory), minted at first ingest
    kind            TEXT      NOT NULL,             -- 'knowledge_base' | 'memory'
    resource_name   TEXT      NOT NULL,             -- KB name (or memory scope store name)
    project_id      TEXT      NOT NULL,             -- WORKSPACE_GLOBAL sentinel (KB/global) | project ULID
    path            TEXT      NOT NULL,             -- relative path of the markdown file
    title           TEXT      NOT NULL,
    description     TEXT,
    content_sha256  TEXT      NOT NULL,             -- hash of the markdown body (reindex no-op gate)
    source_mode     TEXT      NOT NULL,             -- 'converted' | 'edited' (KB) | 'native' (memory)
    metadata        TEXT      NOT NULL DEFAULT '{}',-- JSON, per-face
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (kind, resource_name, id)
);
CREATE INDEX idx_documents_kind_res_time ON documents(kind, resource_name, updated_at DESC);
CREATE INDEX idx_documents_project ON documents(project_id);
-- KB dedup is on metadata->>'source_sha256'; enforced in the repo, not a SQL unique index,
-- because memory rows have no source file.

CREATE TABLE chunks (
    id              TEXT      NOT NULL PRIMARY KEY, -- '<store-scope>:<doc-id>:<position>'
    -- store-scope = 12-hex digest of (kind, resource_name): retained as defense-in-depth
    -- (doc ids are now globally-unique ULIDs, but this keeps chunk ids store-scoped)
    document_id     TEXT      NOT NULL,
    kind            TEXT      NOT NULL,
    resource_name   TEXT      NOT NULL,
    position        INTEGER   NOT NULL              -- 0-based ordinal within the document
    -- chunk TEXT is NOT stored in a base table; it lives in documents_fts + on disk
);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- FTS5 index over chunk text; bm25() ranks keyword search. The text lives once
-- inside the FTS index (not duplicated into a base SQLite table). chunk_id maps
-- a hit back to its chunks row; resource_name scopes the search. (A `content=''`
-- contentless table cannot return its own column values, so passages would need
-- a file read on every hit — the text is kept in the FTS index instead.)
CREATE VIRTUAL TABLE documents_fts USING fts5(
    text,
    resource_name UNINDEXED,
    chunk_id UNINDEXED,
    tokenize='unicode61'
);

-- sqlite-vec virtual table; one row per chunk with a vector. Created LAZILY by
-- vec_index.py at the configured width (per store), not in the migration.
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY,                      -- bare '<doc-id>:<position>' (the table itself is per-store)
    embedding FLOAT[768]                            -- width set per KB at create/re-embed time
);
```

**Why a composite `(kind, resource_name, id)` PK**: doc ids are now globally-unique ULIDs (so a bare `id` would already be unique), but the composite key keeps the unified table unambiguous across faces/resources and lets `on_delete` scope a cascade to one resource. The same source file uploaded into two KBs is two independent documents with two ULIDs (no cross-store dedup — ADR-028).

**Why `project_id`**: the memory face keys stores by project (sentinel ULID for global, a project ULID otherwise). KB rows carry the global sentinel — the column is required by the unified table so memory scope queries have an index (`idx_documents_project`).

**Cascade is application-level** (the kind's `on_delete` hook), not FK: the hook deletes the resource's `documents`/`chunks`/`documents_fts`/`vec_chunks` rows, then `rmtree`s the on-disk directory.

## SQLAlchemy ORM + repos (`infrastructure/knowledge/`)

`DocumentModel` and `ChunkModel` (`models.py`) map to `documents` / `chunks`, registered on the same `Base.metadata` as the rest. `documents_fts` is created via a `Base.metadata` `after_create` DDL hook (`ddl.py`) so `create_all` and the migration both build it. The repo surface is split across two modules to stay under the file-size limit:

`repository.py` — `DocumentRepo` (document-row CRUD):

- `async upsert_document(d: Document) -> Document` (insert or update by `(kind, resource_name, id)`)
- `async list_documents(kind, resource_name, *, limit, offset) -> list[Document]`
- `async count_documents(kind, resource_name) -> int`
- `async get_document(kind, resource_name, doc_id) -> Document | None`
- `async find_by_filename(kind, resource_name, project_id, original_filename) -> Document | None` (re-upload match key — reads `metadata->>'original_filename'`; replaces the old `exists_source` sha lookup)
- `async delete_document(kind, resource_name, doc_id) -> bool`
- `async delete_resource(kind, resource_name) -> int`

`sqlite_index.py` — `SqliteKnowledgeIndex` (chunk + FTS5 + optional vec), bound to one `(kind, resource_name)`:

- `async upsert_chunks(doc_id, chunks, vectors|None) -> int` (FTS5 + optional vec; replaces existing)
- `async delete_chunks(doc_id) -> None`
- `async keyword_search(resource_name, query, top_k) -> Sequence[Passage]` (bm25)
- `async vector_search(resource_name, vector, top_k) -> Sequence[Passage]` (sqlite-vec KNN)

`vec_chunks` writes/reads are confined to `infrastructure/knowledge/vec_index.py` (the only importer of `sqlite_vec`); the chunk text deletion + FTS5 lives in `sqlite_index.py`. The application layer composes these repos plus `grep.py` and the embedder clients (`infrastructure/knowledge/embeddings.py`) behind the shared retrieval facade `KnowledgeRetrieval` (`application/knowledge/retrieval.py`), which owns the keyword↔vector decision including the flagged vector→keyword fallback.

## On-disk layout

```
~/.coffer/
├── coffer.db                       # resources / documents / chunks / documents_fts / vec_chunks / audit
└── knowledge/
    └── <kb-name>/
        ├── docs/
        │   └── <doc-id>.md         # normalized markdown = truth (YAML frontmatter + body)
        └── raw/
            └── <doc-id>.<ext>      # original upload (provenance / re-convert)
```

No per-corpus `index/`, `text/`, or `chroma/` directories — all indexing lives in `coffer.db`. `infrastructure/knowledge/paths.py` is the **only** module that constructs these paths:

- `knowledge_root() -> Path` — `~/.coffer/knowledge/` (override via `COFFER_KNOWLEDGE_ROOT` for tests)
- `kb_dir(name) -> Path` / `docs_dir(name) -> Path` / `raw_dir(name) -> Path`
- `doc_path(name, doc_id) -> Path` / `raw_path(name, doc_id, ext) -> Path`

### Markdown frontmatter

Each `docs/<doc-id>.md` self-describes:

```yaml
---
title: Architecture Notes
source_filename: architecture.docx
source_format: docx
source_sha256: 9f8e…
converter: markitdown
source_mode: converted
---
```

## The single re-index routine (`application/knowledge/reindex.py`, shared with memory)

All write paths (ingest, re-upload, edit, reindex scan) funnel through one idempotent routine (`Reindexer`). Per-store asyncio locks (`application/knowledge/locks.py`, `StoreLocks`) serialize writes to one store so concurrent ingests/edits cannot interleave index updates:

```
compute content_sha256 of the new markdown body
 ├ unchanged → no-op (skip)
 └ changed   → delete old chunks / documents_fts / vec_chunks rows
             → markdown-aware chunk
             → if vector enabled: embed → write vec_chunks
             → write chunks + documents_fts
             → upsert documents row (bump updated_at)
             → audit KB_DOCUMENT_UPDATED  (or _INGESTED on first index)
```

`coffer kb reindex <name>` rescans the `docs/` directory for deltas and runs this routine per file, reconstructing all SQLite state from the files. The scan also prunes `documents` rows whose markdown file was removed out-of-band, reported in the optional `ReindexResult.documents_removed`; documents indexed keyword-only because the embed degraded are counted in the optional `documents_degraded`.

When an embed degrades (embedding provider unavailable), the routine indexes the document keyword-only and persists an **empty-string `content_sha256`** — a deliberate never-matching sentinel so the next reconcile retries the embed instead of treating the document as up to date. The empty value can appear on the wire in `DocumentOut`.

## Cascade & integrity rules

| Action                                | Effect                                                                                                                                                                                                                                                         |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Delete a Document                     | Remove `docs/<id>.md` + `raw/<id>.<ext>`; delete its `chunks`/`documents_fts`/`vec_chunks` rows; delete the `documents` row; audit `KB_DOCUMENT_DELETED`.                                                                                                      |
| Delete a KB                           | `on_delete` hook: `delete_resource(kind, name)` (documents + chunks + fts + vec); `rmtree(kb_dir(name))`; delete the `resources` row; audit `RESOURCE_DELETED` with a KB snapshot.                                                                             |
| Rename a KB                           | Forbidden (Resource name immutable; framework enforces).                                                                                                                                                                                                       |
| Change `chunk_size` / `chunk_overlap` | Allowed → re-chunk + re-index the corpus.                                                                                                                                                                                                                      |
| Change `embedding` model / dimensions | Allowed → re-embed the corpus (rebuild `vec_chunks` if width changes).                                                                                                                                                                                         |
| Edit a document's markdown            | Via the edit API or MCP `edit_document` → `source_mode = edited` → reindex routine. An external-editor edit to the on-disk file is picked up by lazy reindex-on-read (drifted `content_sha256` ⇒ same routine).                                                |
| Re-upload a changed source            | Matched by `original_filename` in-store → updates the SAME document in place (reuse ULID, overwrite `docs/`+`raw/`, keep only the latest original, `source_mode` → `converted`) with `replace=true`; byte-identical re-upload is a no-op.                      |
| Re-convert a document                 | Allowed only if `source_mode == converted`; `edited` ⇒ `ReconversionBlocked`.                                                                                                                                                                                 |
| Add / edit / delete via MCP           | Agents call `coffer__add_document` / `edit_document` / `delete_document`; same service paths as REST, audited with the agent as actor.                                                                                                                         |

## Audit events added

`AuditEventType` is an extensible `StrEnum`. Added:

| Value                    | When emitted                                                               |
| ------------------------ | -------------------------------------------------------------------------- |
| `"kb_document_ingested"` | After first index of a new document                                        |
| `"kb_document_updated"`  | After the reindex routine re-indexes a changed document (edit / re-upload) |
| `"kb_document_deleted"`  | After a document delete                                                    |
| `"kb_reindexed"`         | After a full `coffer kb reindex` (carries per-doc counts)                  |

`resource_created` / `resource_deleted` from the kind-agnostic core cover KB lifecycle. Built-in MCP tool calls log to `mcp_invocations` (tool name + who/when/duration/outcome only).

## Importlinter contracts (added or amended)

| Contract                                              | Effect                                                                                                                                                                     |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — layered architecture                              | unchanged                                                                                                                                                                  |
| 2 — infrastructure ↛ surfaces                         | unchanged                                                                                                                                                                  |
| 3 — domain is pure                                    | unchanged; `domain/knowledge/*` import only stdlib + Pydantic                                                                                                              |
| 4 — keyring confined to infrastructure                | unchanged (embedding `credential_ref` resolves via the credential module)                                                                                                  |
| 5 — cross-kind imports forbidden                      | **EXTEND**: add `coffer.{application,surfaces.http}.knowledge_base`; the shared `coffer.{domain,infrastructure}.knowledge` substrate is exempt (kind-agnostic)             |
| 6 — kind-agnostic core ↛ kind-specific                | **EXTEND**: add the `knowledge_base` modules to `forbidden_modules`                                                                                                        |
| 7 (REPLACES old LlamaIndex rule) — engine confinement | `coffer.application.*` and `coffer.domain.*` MUST NOT import `markitdown`, `docling`, `sqlite_vec`, `openai`, or `fastembed`; only `coffer.infrastructure.knowledge.*` may |

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Highlights (app-wide error envelope `{error:{code,message,details}}`):

- `POST /api/v1/knowledge_bases` — create KB
- `GET /api/v1/knowledge_bases` — list KBs
- `GET /api/v1/knowledge_bases/{name}` — get one KB
- `POST /api/v1/knowledge_bases/{name}/documents` — multipart upload + ingest (any format)
- `GET /api/v1/knowledge_bases/{name}/documents` — paginated list (each row carries its absolute `path` + containing-folder `folder_path`)
- `GET /api/v1/knowledge_bases/{name}/documents/{doc_id}` — read-only markdown body + frontmatter + absolute `path` + `folder_path`
- `PUT /api/v1/knowledge_bases/{name}/documents/{doc_id}` — edit markdown via API (sets `source_mode=edited`, reindexes); the UI is read-only and edits otherwise arrive via the external editor (picked up by reindex-on-read) or agent MCP
- `POST /api/v1/knowledge_bases/{name}/documents/{doc_id}/reconvert` — re-run conversion from `raw/` (blocked with `RECONVERSION_BLOCKED` once hand-edited)
- `DELETE /api/v1/knowledge_bases/{name}/documents/{doc_id}` — delete one document
- `POST /api/v1/knowledge_bases/{name}/reindex` — rescan + rebuild index from files
- `POST /api/v1/knowledge_bases/{name}/search` — `{query, top_k?, mode?}` → ranked passages (+ `fallback`)
- `POST /api/v1/knowledge_bases/{name}/grep` — `{pattern, max_matches?}` → file/line hits
- `GET /api/v1/knowledge_bases/{name}/metrics` — counts + indexed modes + disk bytes

The kind-agnostic `/api/v1/resources/...` endpoints continue to work for KBs (list / get / delete / enable / disable).
