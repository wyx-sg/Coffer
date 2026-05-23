# Data Model —— 007 Memory Manager

> English: [data-model.md](./data-model.md)

memory kind 的实体、端口接口、SQLite schema 与磁盘布局。

## Domain 实体（`backend/coffer/domain/memory/`）

### `MemoryStoreConfig`（`domain/memory/config.py`）

Pydantic v2 `BaseModel`。在 `kind == "memory"` 时挂在 `Resource.config` 内。

| Field                | Type                                | Notes                                                                            |
| -------------------- | ----------------------------------- | -------------------------------------------------------------------------------- |
| `embedding_model`    | `str`                               | HuggingFace 模型 id。默认 `BAAI/bge-small-en-v1.5`。创建后不可变。               |
| `llm_provider`       | `Literal["none","ollama","openai"]` | 默认 `"none"`。创建后不可变。                                                    |
| `llm_model`          | `str \| None`                       | 例：ollama 用 `"llama3.1"`，openai 用 `"gpt-4o-mini"`。provider 非 none 时必填。 |
| `llm_endpoint`       | `str \| None`                       | provider == ollama 时必填（例如 `http://localhost:11434`）；省略时取该默认。     |
| `llm_credential_ref` | `str \| None`                       | 云端 LLM API key 的 keychain ref。provider == openai 时必填。                    |
| `max_memory_chars`   | `int`                               | 默认 `8192`；范围 `64–32768`。                                                   |

### `MemoryRecord`（`domain/memory/record.py`）

普通 dataclass（domain 保持纯粹）。

| Field        | Type                      | Notes                                      |
| ------------ | ------------------------- | ------------------------------------------ |
| `id`         | `str`                     | mem0 的 memory id；不透明的 UUID 形 string |
| `store_name` | `str`                     | Resource name                              |
| `text`       | `str`                     | memory 主体                                |
| `actor`      | `Literal["agent","user"]` | 谁写的                                     |
| `created_at` | `datetime`                | UTC                                        |
| `updated_at` | `datetime`                | UTC（未编辑前 == created_at）              |

### `MemoryHit`（`domain/memory/store.py`）

Frozen dataclass；`MemoryStore.search()` 的返回值。

| Field        | Type       |
| ------------ | ---------- |
| `id`         | `str`      |
| `text`       | `str`      |
| `score`      | `float`    |
| `created_at` | `datetime` |

### `MemoryStore`（端口）（`domain/memory/store.py`）

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
    async def clear(self, store_name: str) -> int: ...      # 返回清掉的条数
    async def search(
        self, store_name: str, query: str, top_k: int
    ) -> Sequence[MemoryHit]: ...
    async def drop(self, store_name: str) -> None: ...
    async def close(self) -> None: ...
```

`Mem0MemoryStore`（infrastructure）是唯一 import `mem0` 的实现。`FakeMemoryStore` 给测试用，内部一个 dict。

### Domain errors（追加到 `domain/errors.py`）

- `MemoryStoreNotFound` —— code `"MEMORY_STORE_NOT_FOUND"`。
- `MemoryNotFound` —— code `"MEMORY_NOT_FOUND"`。
- `MemoryRejected` —— code `"MEMORY_REJECTED"`；reason：`"empty"`、`"too_long"`。
- `LLMNotConfigured` —— code `"LLM_NOT_CONFIGURED"`；provider 为 `"none"` 时由 `add` / `update` 抛出。
- `EngineUnavailable` 已在 spec 006（knowledge_base）中存在；复用即可。

## SQLite schema（Alembic revision `0008_memory_tables`）

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

`text` 列是冗余的 —— mem0 自己也存这份 —— 把它放在我们 SQL DB 里能让 list / get / 编辑审计路径不必每次读都绕一圈 mem0 的向量存储。

## SQLAlchemy ORM

`MemoryRecordModel` 映射到 `memory_records`，带 `to_domain` / `from_domain`。薄 `MemoryRecordRepo`，提供 `create`、`get`、`list_by_store`、`count_by_store`、`update_text`、`delete`、`delete_all_by_store`。

## 磁盘布局

```
~/.coffer/
└── memory/
    └── <store-name>/
        ├── chroma/          # mem0 的向量后端持久目录
        └── ... (mem0 内部文件)
```

`infrastructure/memory/paths.py` 是唯一构造这些路径的模块。

## Cascade & 完整性规则

| Action                                    | Effect                                                                                                                                 |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 删除一条 memory record                    | 从 mem0 中移除 + 删行 + 审计 `memory_deleted`。                                                                                        |
| 清空一个 memory store                     | mem0 reset + 删所有行 + 审计 `memory_cleared`。                                                                                        |
| 删除 memory-store Resource                | `on_delete`：销毁 mem0 客户端、`rmtree(memory/<store-name>/)`、`MemoryRecordRepo.delete_all_by_store(name)`、审计 `resource_deleted`。 |
| 改 memory store 名                        | 禁止（Resource.name 不可变）。                                                                                                         |
| 改 config（provider / model / embedding） | 创建后禁止。                                                                                                                           |
| 改 `max_memory_chars`                     | 允许。                                                                                                                                 |

## 审计事件新增

| Value              | When emitted    |
| ------------------ | --------------- |
| `"memory_added"`   | `add` 成功后    |
| `"memory_updated"` | `update` 成功后 |
| `"memory_deleted"` | `delete` 成功后 |
| `"memory_cleared"` | `clear` 成功后  |

## Importlinter 契约扩展

- Contract 5 —— 把 `coffer.{...}.memory` 加入源模块；填充 `forbidden_modules`，使得 memory 不能 import `mcp` 或 `knowledge_base`，反之亦然。
- Contract 6 —— 把 `coffer.{...}.memory` 加入 `forbidden_modules`。
- **新增 Contract 8** —— `coffer.application.*` 与 `coffer.domain.*` MUST NOT import `mem0`。只有 `coffer.infrastructure.memory.mem0_store` 可以。

## REST 契约

落在 `contracts/api.openapi.yaml`。路由：

- `POST /api/v1/memory_stores` —— 创建
- `GET /api/v1/memory_stores` —— 列出
- `GET /api/v1/memory_stores/{name}` —— 取一个
- `GET /api/v1/memory_stores/{name}/metrics`
- `POST /api/v1/memory_stores/{name}/memories` —— 写入
- `GET /api/v1/memory_stores/{name}/memories` —— 分页列出
- `GET /api/v1/memory_stores/{name}/memories/{id}` —— 取单条
- `PATCH /api/v1/memory_stores/{name}/memories/{id}` —— 改文本
- `DELETE /api/v1/memory_stores/{name}/memories/{id}` —— 删单条
- `POST /api/v1/memory_stores/{name}/memories/clear` —— 清空
- `POST /api/v1/memory_stores/{name}/search` —— 语义检索

Kind-agnostic 的 `/api/v1/resources/...` 对 memory store 仍然有效。
