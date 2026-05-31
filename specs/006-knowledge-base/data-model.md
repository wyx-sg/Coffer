# Data Model — 006 Knowledge Base Manager

Entities, port interface, SQLite schema, and on-disk layout for the knowledge-base kind. Mirrors the data-model.md style used by 001-mcp-gateway.

## Domain entities (`backend/coffer/domain/knowledge_base/`)

### `KnowledgeBaseConfig` (`domain/knowledge_base/config.py`)

Pydantic v2 `BaseModel`. Held inside `Resource.config` when `kind == "knowledge_base"`.

| Field                | Type  | Notes                                                                                                        |
| -------------------- | ----- | ------------------------------------------------------------------------------------------------------------ |
| `embedding_model`    | `str` | HuggingFace model id (e.g. `BAAI/bge-small-en-v1.5`). Non-empty, must contain `/`. Immutable after creation. |
| `chunk_size`         | `int` | Default `512`; range `64–2048`.                                                                              |
| `chunk_overlap`      | `int` | Default `64`; range `0–chunk_size/2`.                                                                        |
| `max_document_bytes` | `int` | Default `25 * 1024 * 1024`; range `1024–104857600`.                                                          |

The `Resource.config` JSON for a freshly created KB looks like:

```json
{
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "chunk_size": 512,
  "chunk_overlap": 64,
  "max_document_bytes": 26214400
}
```

### `Document` (`domain/knowledge_base/document.py`)

Plain Python dataclass (not Pydantic — domain stays pure):

| Field         | Type       | Notes                                              |
| ------------- | ---------- | -------------------------------------------------- |
| `id`          | `str`      | First 16 hex chars of the SHA-256 content hash     |
| `kb_name`     | `str`      | KB resource name                                   |
| `filename`    | `str`      | Original filename (display only)                   |
| `extension`   | `str`      | Lowercased extension including the dot, e.g. `.md` |
| `size_bytes`  | `int`      | Raw file size                                      |
| `sha256`      | `str`      | Full 64-hex-char content hash                      |
| `chunk_count` | `int`      | Number of chunks indexed                           |
| `ingested_at` | `datetime` | UTC                                                |

### `Passage` (`domain/knowledge_base/store.py`)

Frozen dataclass. Return value of `KnowledgeBaseStore.search()`. Pure value object.

| Field         | Type    | Notes                                                    |
| ------------- | ------- | -------------------------------------------------------- |
| `document_id` | `str`   | Same id as `Document.id`                                 |
| `filename`    | `str`   | The originating document's filename                      |
| `text`        | `str`   | The chunk text (trimmed)                                 |
| `score`       | `float` | Relevance score in `[0.0, 1.0]`                          |
| `position`    | `int`   | 0-based ordinal of this chunk within the source document |

### `KnowledgeBaseStore` (port) (`domain/knowledge_base/store.py`)

`typing.Protocol`. Methods express **what Coffer needs**, not what LlamaIndex offers:

```python
class KnowledgeBaseStore(Protocol):
    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None: ...
    async def ingest(self, kb_name: str, document: Document, text: str) -> int: ...
    async def delete_document(self, kb_name: str, document_id: str) -> None: ...
    async def search(
        self, kb_name: str, query: str, top_k: int
    ) -> Sequence[Passage]: ...
    async def drop(self, kb_name: str) -> None: ...
    async def close(self) -> None: ...
```

`ingest` returns the number of chunks the adapter produced for the document; the application service persists that value as `Document.chunk_count`.

A real adapter (`LlamaIndexKnowledgeBaseStore`) is the only implementation that imports LlamaIndex. A `FakeKnowledgeBaseStore` for tests stores chunks in a dict and returns naive scores.

### Domain errors (added to `domain/errors.py`)

- `KBNotFound` — code `"KB_NOT_FOUND"`, raised by service on unknown kb_name.
- `DocumentNotFound` — code `"DOCUMENT_NOT_FOUND"`.
- `IngestRejected` — code `"INGEST_REJECTED"`; carries one of: `"empty_text"`, `"too_large"`, `"unsupported_type"`, `"duplicate"`.
- `EngineUnavailable` — code `"ENGINE_UNAVAILABLE"`; raised at startup if the engine adapter cannot be constructed.

## SQLite schema (Alembic revision `0007`)

The migration creates the single new table `kb_documents`. The `resources` table is reused (kind-agnostic).

```sql
CREATE TABLE kb_documents (
    id              TEXT      NOT NULL,             -- first 16 hex chars of sha256
    kb_name         TEXT      NOT NULL,             -- denormalized resource name; see note
    filename        TEXT      NOT NULL,
    extension       TEXT      NOT NULL,
    size_bytes      INTEGER   NOT NULL,
    sha256          TEXT      NOT NULL,             -- full 64-hex content hash
    chunk_count     INTEGER   NOT NULL,
    ingested_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (kb_name, id)
);
CREATE INDEX idx_kb_documents_kb_time ON kb_documents(kb_name, ingested_at DESC);
CREATE UNIQUE INDEX uq_kb_documents_kb_sha256 ON kb_documents(kb_name, sha256);
```

**Why `kb_name` (not `resource_id` FK)**: The other persisted KB state lives on the file system, keyed by name. Joining via `name` keeps the on-disk layout and the SQL table aligned. KB rename is forbidden by the kind-agnostic resource layer (`Resource.name` is not updated), so denormalisation does not drift.

Cascade on KB deletion is **application-level** (the on_delete hook), not FK — the hook walks the table and drops rows, then removes the on-disk directory, then disposes the in-memory store.

## SQLAlchemy ORM (`infrastructure/knowledge_base/persistence.py`)

A single ORM model `KBDocumentModel` mapped to `kb_documents`, registered against the same `Base.metadata` as MCP tables. Conversions: `to_domain() -> Document`, module-level `from_domain(d: Document) -> KBDocumentModel`.

The same module exposes a thin `KBDocumentRepo` with:

- `async create(d: Document) -> Document`
- `async list_by_kb(kb_name: str, *, limit: int, offset: int) -> list[Document]`
- `async count_by_kb(kb_name: str) -> int`
- `async get(kb_name: str, document_id: str) -> Document | None`
- `async exists_by_hash(kb_name: str, sha256: str) -> bool`
- `async delete(kb_name: str, document_id: str) -> bool`
- `async delete_all(kb_name: str) -> int`

## On-disk layout

```
~/.coffer/
└── kb/
    └── <kb-name>/
        ├── raw/
        │   └── <document_id><original_ext>     # original bytes preserved
        └── index/
            └── ...                              # LlamaIndex persist directory
```

`<kb-name>` is the user-chosen Resource name; allowed characters match Resource naming rules (no `:`, no leading dot).

The `infrastructure/knowledge_base/paths.py` module is the **only** module that constructs these paths. It exposes:

- `kb_root() -> Path` — `~/.coffer/kb/` (configurable via `COFFER_KB_ROOT` env for tests)
- `kb_dir(kb_name: str) -> Path`
- `kb_raw_dir(kb_name: str) -> Path`
- `kb_index_dir(kb_name: str) -> Path`
- `raw_file_path(kb_name: str, document_id: str, extension: str) -> Path`

## Cascade & integrity rules

| Action                                                    | Effect                                                                                                                                                                                                                             |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Delete a Document (`kb_documents` row)                    | Remove the raw file `<id><ext>`; remove the document's chunks from the LlamaIndex index; insert audit row `kb_document_deleted`.                                                                                                   |
| Delete a KB (Resource deletion)                           | `on_delete` hook: dispose the in-memory store entry; drop chunks; `KBDocumentRepo.delete_all`; `shutil.rmtree(kb_dir(kb_name))`; cascade to `resources` row via standard delete; audit row `resource_deleted` carries kb-snapshot. |
| Rename a KB                                               | Forbidden (Resource name is immutable; framework already enforces).                                                                                                                                                                |
| Change `embedding_model` / `chunk_size` / `chunk_overlap` | Forbidden post-creation (validator rejects in `ResourceService.update_config`).                                                                                                                                                    |
| Change `max_document_bytes`                               | Allowed (does not invalidate existing chunks).                                                                                                                                                                                     |

## Audit events added

`AuditEventType` already exists as an extensible `StrEnum`. This spec adds:

| Value                    | When emitted                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| `"kb_document_ingested"` | After `KnowledgeBaseService.ingest`                                                                   |
| `"kb_document_deleted"`  | After `KnowledgeBaseService.delete_document`                                                          |
| `"kb_searched"`          | (optional, default off) per search call — gated by `COFFER_KB_AUDIT_SEARCHES` because it can be noisy |

`resource_created` / `resource_deleted` from the kind-agnostic core already cover the lifecycle; the new events cover document-level activity that the core does not see.

## Default retention policy seed

The KB ingest does **not** add a new prunable table. Documents are user-owned content; they are never auto-pruned. The existing `audit_log` and `mcp_invocations` policies cover the related logs.

## Importlinter contracts (added or amended)

| Contract                               | Effect on this spec                                                                                                                                                |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 — layered architecture               | unchanged (the new modules respect surfaces → application → domain)                                                                                                |
| 2 — infrastructure ↛ surfaces          | unchanged                                                                                                                                                          |
| 3 — domain is pure                     | unchanged; the new `domain/knowledge_base/*` files import only stdlib + Pydantic                                                                                   |
| 4 — keyring confined to infrastructure | unchanged                                                                                                                                                          |
| 5 — cross-kind imports forbidden       | **EXTEND**: add `coffer.{domain,application,infrastructure,surfaces.http}.knowledge_base` to source modules; forbid them from importing each other's sibling kinds |
| 6 — kind-agnostic core ↛ kind-specific | **EXTEND**: add `coffer.{...}.knowledge_base` to the `forbidden_modules` list                                                                                      |
| 7 (NEW) — RAG engine confinement       | `coffer.application.*` and `coffer.domain.*` MUST NOT import `llama_index` (any submodule). Only `coffer.infrastructure.knowledge_base.llamaindex_store` may.      |

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Highlights:

- `POST /api/v1/knowledge_bases` — create KB (delegates to kind-agnostic resource POST internally; the convenience endpoint exists for symmetry with `POST /api/v1/resources` and clearer naming in clients)
- `POST /api/v1/knowledge_bases/{name}/documents` — multipart upload, `multipart/form-data` with `file=<binary>`
- `GET /api/v1/knowledge_bases/{name}/documents` — paginated list
- `GET /api/v1/knowledge_bases/{name}/documents/{document_id}` — single document metadata + text
- `DELETE /api/v1/knowledge_bases/{name}/documents/{document_id}` — single document delete
- `POST /api/v1/knowledge_bases/{name}/search` — body: `{ "query": str, "top_k": int? }` → `[ Passage, ... ]`
- `GET /api/v1/knowledge_bases/{name}/metrics` — `{ document_count: int, disk_bytes: int }`

The kind-agnostic `/api/v1/resources/...` endpoints continue to work for KBs (list / get / delete / enable / disable) — those operations are entirely kind-agnostic.
