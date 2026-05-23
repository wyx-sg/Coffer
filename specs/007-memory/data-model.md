# Data Model — 007 Memory Manager

Entities, port interface, SQLite schema, and on-disk layout for the memory kind.

## Domain entities (`backend/coffer/domain/memory/`)

### `MemoryStoreConfig` (`domain/memory/config.py`)

Pydantic v2 `BaseModel`. Held inside `Resource.config` when `kind == "memory"`.

| Field                | Type                                | Notes                                                                                                |
| -------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `embedding_model`    | `str`                               | HuggingFace model id. Default `BAAI/bge-small-en-v1.5`. Immutable post-create.                       |
| `llm_provider`       | `Literal["none","ollama","openai"]` | Default `"none"`. Immutable post-create.                                                             |
| `llm_model`          | `str \| None`                       | e.g. `"llama3.1"` for ollama, `"gpt-4o-mini"` for openai. Required if provider != none.              |
| `llm_endpoint`       | `str \| None`                       | Required when provider == ollama (e.g. `http://localhost:11434`). Defaults to that value if omitted. |
| `llm_credential_ref` | `str \| None`                       | Keychain ref for cloud LLM API key. Required when provider == openai.                                |
| `max_memory_chars`   | `int`                               | Default `8192`; range `64–32768`.                                                                    |

### `MemoryRecord` (`domain/memory/record.py`)

Plain dataclass (domain stays pure).

| Field        | Type                      | Notes                                    |
| ------------ | ------------------------- | ---------------------------------------- |
| `id`         | `str`                     | mem0's memory id; opaque UUID-ish string |
| `store_name` | `str`                     | Resource name                            |
| `text`       | `str`                     | Memory body                              |
| `actor`      | `Literal["agent","user"]` | Who wrote it                             |
| `created_at` | `datetime`                | UTC                                      |
| `updated_at` | `datetime`                | UTC (== created_at until edited)         |

### `MemoryHit` (`domain/memory/store.py`)

Frozen dataclass; return value of `MemoryStore.search()`.

| Field        | Type       |
| ------------ | ---------- |
| `id`         | `str`      |
| `text`       | `str`      |
| `score`      | `float`    |
| `created_at` | `datetime` |

### `MemoryStore` (port) (`domain/memory/store.py`)

```python
class MemoryStore(Protocol):
    async def open(self, store_name: str, config: MemoryStoreConfig) -> None: ...
    async def add(
        self, store_name: str, text: str, actor: str
    ) -> MemoryRecord: ...
    async def get(self, store_name: str, memory_id: str) -> MemoryRecord | None: ...
    async def list(
        self, store_name: str, *, limit: int, offset: int
    ) -> Sequence[MemoryRecord]: ...
    async def update(
        self, store_name: str, memory_id: str, new_text: str
    ) -> MemoryRecord: ...
    async def delete(self, store_name: str, memory_id: str) -> bool: ...
    async def clear(self, store_name: str) -> int: ...      # returns count
    async def search(
        self, store_name: str, query: str, top_k: int
    ) -> Sequence[MemoryHit]: ...
    async def drop(self, store_name: str) -> None: ...
    async def close(self) -> None: ...
```

`Mem0MemoryStore` (infrastructure) is the only implementation that imports `mem0`. `FakeMemoryStore` for tests uses a dict.

### Domain errors (added to `domain/errors.py`)

- `MemoryStoreNotFound` — code `"MEMORY_STORE_NOT_FOUND"`.
- `MemoryNotFound` — code `"MEMORY_NOT_FOUND"`.
- `MemoryRejected` — code `"MEMORY_REJECTED"`; reasons: `"empty"`, `"too_long"`.
- `LLMNotConfigured` — code `"LLM_NOT_CONFIGURED"`; raised by `add` / `update` when provider is `"none"`.
- `EngineUnavailable` already exists in spec 006 (knowledge_base); reused.

## SQLite schema (Alembic revision `0004`)

```sql
CREATE TABLE memory_records (
    id            TEXT NOT NULL,                  -- mem0 memory id
    store_name    TEXT NOT NULL,                  -- memory resource name
    text          TEXT NOT NULL,
    actor         TEXT NOT NULL,                  -- 'agent' | 'user'
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (store_name, id)
);
CREATE INDEX idx_memory_records_store_time ON memory_records(store_name, created_at DESC);
```

The `text` column is denormalised — mem0 also holds it, but having the text in our SQL DB simplifies list / get / edit-audit paths without round-tripping through mem0's vector store on every read.

## SQLAlchemy ORM

`MemoryRecordModel` mapped to `memory_records`, with `to_domain` / `from_domain`. Thin `MemoryRecordRepo` with `create`, `get`, `list_by_store`, `count_by_store`, `update_text`, `delete`, `delete_all_by_store`.

## On-disk layout

```
~/.coffer/
└── memory/
    └── <store-name>/
        ├── chroma/          # mem0's vector backend persistent dir
        └── ... (mem0 internal files)
```

`infrastructure/memory/paths.py` is the only module that constructs these paths.

## Cascade & integrity rules

| Action                                       | Effect                                                                                                                                    |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Delete a memory record                       | Remove from mem0 + delete row + audit `memory_deleted`.                                                                                   |
| Clear a memory store                         | mem0 reset + delete all rows + audit `memory_cleared`.                                                                                    |
| Delete a memory-store Resource               | `on_delete`: dispose mem0 client, `rmtree(memory/<store-name>/)`, `MemoryRecordRepo.delete_all_by_store(name)`, audit `resource_deleted`. |
| Rename a memory store                        | Forbidden (Resource.name immutable).                                                                                                      |
| Change config (provider / model / embedding) | Forbidden post-create.                                                                                                                    |
| Change `max_memory_chars`                    | Allowed.                                                                                                                                  |

## Audit events added

| Value              | When emitted              |
| ------------------ | ------------------------- |
| `"memory_added"`   | After successful `add`    |
| `"memory_updated"` | After successful `update` |
| `"memory_deleted"` | After successful `delete` |
| `"memory_cleared"` | After successful `clear`  |

## Importlinter contracts amended

- Contract 5 — add `coffer.{...}.memory` to source modules; populate `forbidden_modules` so memory cannot import `mcp` or `knowledge_base` and vice versa.
- Contract 6 — add `coffer.{...}.memory` to `forbidden_modules`.
- **New Contract 8** — `coffer.application.*` and `coffer.domain.*` MUST NOT import `mem0`. Only `coffer.infrastructure.memory.mem0_store` may.

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Routes:

- `POST /api/v1/memory_stores` — create
- `GET /api/v1/memory_stores` — list
- `GET /api/v1/memory_stores/{name}` — get
- `GET /api/v1/memory_stores/{name}/metrics`
- `POST /api/v1/memory_stores/{name}/memories` — add
- `GET /api/v1/memory_stores/{name}/memories` — list (paginated)
- `GET /api/v1/memory_stores/{name}/memories/{id}` — get one
- `PATCH /api/v1/memory_stores/{name}/memories/{id}` — edit text
- `DELETE /api/v1/memory_stores/{name}/memories/{id}` — delete one
- `POST /api/v1/memory_stores/{name}/memories/clear` — clear all
- `POST /api/v1/memory_stores/{name}/search` — semantic search

Kind-agnostic `/api/v1/resources/...` continues to work for memory stores.
