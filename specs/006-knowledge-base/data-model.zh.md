# Data Model —— 006 Knowledge Base（重新设计）

> English: [data-model.md](./data-model.md)

知识基底 KB 面的实体、端口、**统一的** SQLite schema（与 `memory` kind，spec 007，共享）以及磁盘布局。架构不变量在 [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)；本文件只描述模型。

**原则**：磁盘上的 Markdown 文件是**唯一真相源**。每一行 SQLite（`documents`、`chunks`、`documents_fts`、`vec_chunks`）都是**可由文件经 reindex 例程派生重建**的。不存在双真相源。

## Domain 实体

基底 domain（`backend/coffer/domain/knowledge/`）与 memory kind 共享；KB 专属的配置与 doc-id 辅助函数在 `backend/coffer/domain/knowledge_base/`。

### `KnowledgeBaseConfig` (`domain/knowledge_base/config.py`)

Pydantic v2 `BaseModel`。当 `kind == "knowledge_base"` 时存在 `Resource.config` 里。所有字段创建后**可变**（改 chunk 参数或 embedding 模型会触发 reindex/重新 embedding —— 没有不可变锁）。

| Field                | Type                      | Notes                                                                                              |
| -------------------- | ------------------------- | -------------------------------------------------------------------------------------------------- |
| `enabled_modes`      | `list[RetrievalMode]`     | `{"grep","keyword","vector"}` 的子集。默认 `["keyword","grep"]`。`vector` 可选，需要 `embedding`。 |
| `default_mode`       | `RetrievalMode`           | search 省略 `mode` 时使用的模式。默认 `"keyword"`。                                                |
| `chunk_size`         | `int`                     | 默认 `512`；范围 `64–2048`。                                                                       |
| `chunk_overlap`      | `int`                     | 默认 `64`；范围 `0–chunk_size/2`。                                                                 |
| `max_document_bytes` | `int`                     | 默认 `25 * 1024 * 1024`；范围 `1024–104857600`。                                                   |
| `embedding`          | `EmbeddingConfig \| None` | 仅当启用 `vector` 时必需。`None` ⇒ 仅 keyword/grep。                                               |

### `EmbeddingConfig` (`domain/knowledge/embedder.py`)

DevPilot 风格的 OpenAI 兼容 provider 抽象（一个 `AsyncOpenAI` 客户端，可换 `base_url`），外加一个 in-process `local` 选项。

| Field            | Type          | Notes                                                                                                                                         |
| ---------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `provider`       | `str`         | `"openai"`、`"openrouter"`、`"voyage"`、`"jina"`、`"gemini"`、`"azure"`、`"dashscope"`、`"ollama"`、`"lmstudio"`，或 `"local"`（fastembed）。 |
| `model`          | `str`         | embedding 模型 id，如 `text-embedding-3-small`、`bge-m3`。                                                                                     |
| `base_url`       | `str \| None` | OpenAI 兼容端点；`None` 用 provider 默认值；`local` 时忽略。                                                                                    |
| `credential_ref` | `str \| None` | keychain 引用（绝不明文）；`local` / 免 key 端点用 `None`。可选回退到 LLM 凭据引用。                                                            |
| `dimensions`     | `int`         | 向量宽度；决定 `vec_chunks` 的列宽。宽度变化时重新 embedding 会重建 vec 表。                                                                    |

### `Document` (`domain/knowledge/document.py`)

frozen dataclass；一个 Markdown 文件一条，**按 `kind` 区分**。KB 与 memory 共享该实体；KB 专属数据放在 `metadata` 里。

| Field                       | Type          | Notes                                                                            |
| --------------------------- | ------------- | --------------------------------------------------------------------------------- |
| `id`                        | `str`         | `source_sha256` 的前 16 个 hex 字符（KB）—— 即 doc id 与 `<doc-id>.md` 文件名。  |
| `kind`                      | `str`         | KB 行是 `"knowledge_base"`。                                                     |
| `resource_name`             | `str`         | KB 资源名。                                                                      |
| `path`                      | `str`         | Markdown 文件的相对路径，`docs/<doc-id>.md`。                                    |
| `title`                     | `str`         | 来自 frontmatter / 第一个标题 / 文件名。                                          |
| `description`               | `str \| None` | 可选摘要。                                                                       |
| `content_sha256`            | `str`         | **Markdown** 正文的哈希 —— reindex 的 no-op 闸门。                               |
| `source_mode`               | `str`         | `"converted"` 或 `"edited"`。                                                    |
| `metadata`                  | `dict`        | 按面区分的 JSON；KB 的 key 见下。                                                |
| `created_at` / `updated_at` | `datetime`    | UTC。                                                                            |

KB 的 `metadata` key：`original_filename`、`original_format`、`source_sha256`、`converted_at`、`conversion_engine`。

### `Passage`、`GrepHit`、`SearchResult` (`domain/knowledge/retrieval.py`)

frozen 值对象（不持久化）：

- `Passage`：`document_id`、`title`、`text`、`score: float`、`position: int`。
- `GrepHit`：`path`、`line_number: int`、`line`。
- `GrepResult`：`hits: Sequence[GrepHit]`、`truncated: bool` —— 当存在超出 `max_matches` 的匹配，**或**服务端超时截断了扫描时，`truncated` 为 true（grep 超时会返回零命中且 `truncated=true`，同时 `rg` 进程被 kill）。
- `SearchResult`：`mode: RetrievalMode`、`passages: Sequence[Passage]`、`fallback: RetrievalMode | None`（当请求的 `vector` 搜索降级为 `keyword` 时设置）。
- `StoreRef`：`kind`、`resource_name`、`project_id`、`docs_dir` —— 为共享检索门面标识一个逻辑 store（一个 KB 或一个 memory scope）。

### 端口 (`domain/knowledge/`)

用 `typing.Protocol` 表达 Coffer 需要什么，让具体引擎留在 `infrastructure/`：

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

grep 是独立的 `infrastructure/knowledge/grep.py` ripgrep 包装器（无索引），受 max-matches + 超时约束。

### Domain 错误（加进 `domain/errors.py`）

- `KBNotFound` —— code `"KB_NOT_FOUND"`。
- `DocumentNotFound` —— code `"DOCUMENT_NOT_FOUND"`。
- `IngestRejected` —— code `"INGEST_REJECTED"`；reason ∈ `{"empty","too_large","unsupported_type","duplicate"}`。
- `EngineUnavailable` —— code `"ENGINE_UNAVAILABLE"`；当请求操作所需的转换器库 / sqlite-vec / embedding provider 不可用时抛出。
- `ReconversionBlocked` —— code `"RECONVERSION_BLOCKED"`；对 `source_mode == "edited"` 的文档执行重转换时抛出。
- `SearchModeInvalid` —— code `"SEARCH_MODE_INVALID"`（HTTP 400）；当搜索请求**显式**指定 `mode=grep`（grep 有自己的端点）或任何不在该 KB `enabled_modes` 里的显式模式时抛出。`vector` 是例外 —— 它降级为 keyword 并标注 fallback，而不是报错。

## SQLite schema（一个 Alembic 迁移；**删除** `kb_documents`）

迁移删除旧的 `kb_documents` / `memory_records` 表并创建统一 schema。**没有数据迁移**（分支未发布）。

```sql
-- One row per Markdown file, shared by KB and memory, discriminated by `kind`.
CREATE TABLE documents (
    id              TEXT      NOT NULL,             -- 16-hex doc id (KB) / ULID (memory)
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
    id              TEXT      NOT NULL PRIMARY KEY, -- '<doc-id>:<position>'
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
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[768]                            -- width set per KB at create/re-embed time
);
```

**为什么用 `(kind, resource_name, id)` 复合主键**：同一个内容寻址的 doc id 可能同时出现在两个面、跨多个资源；复合键让统一表无歧义，并让 `on_delete` 能把级联限定在单个资源内。memory 的 id 是全局唯一的 ULID，因此复合键对每个 memory store 同样唯一。

**为什么要 `project_id`**：memory 面按 project 给 store 定键（global 用 sentinel ULID，其余用 project ULID）。KB 行携带 global sentinel —— 统一表需要这一列，让 memory 的 scope 查询有索引可用（`idx_documents_project`）。

**级联在应用层**（kind 的 `on_delete` 钩子），不是外键：钩子删除该资源的 `documents`/`chunks`/`documents_fts`/`vec_chunks` 行，然后 `rmtree` 掉磁盘目录。

## SQLAlchemy ORM + 仓储 (`infrastructure/knowledge/`)

`DocumentModel` 与 `ChunkModel`（`models.py`）映射到 `documents` / `chunks`，与其余模型注册在同一个 `Base.metadata` 上。`documents_fts` 经 `Base.metadata` 的 `after_create` DDL 钩子（`ddl.py`）创建，使 `create_all` 与迁移都会建出它。仓储面拆成两个模块以满足文件大小上限：

`repository.py` —— `DocumentRepo`（document 行 CRUD）：

- `async upsert_document(d: Document) -> Document`（按 `(kind, resource_name, id)` 插入或更新）
- `async list_documents(kind, resource_name, *, limit, offset) -> list[Document]`
- `async count_documents(kind, resource_name) -> int`
- `async get_document(kind, resource_name, doc_id) -> Document | None`
- `async exists_source(kind, resource_name, source_sha256) -> bool`（读 `metadata->>'source_sha256'`）
- `async delete_document(kind, resource_name, doc_id) -> bool`
- `async delete_resource(kind, resource_name) -> int`
- `async all_document_ids(kind, resource_name) -> Sequence[str]`

`sqlite_index.py` —— `SqliteKnowledgeIndex`（chunk + FTS5 + 可选 vec），绑定到一个 `(kind, resource_name)`：

- `async upsert_chunks(doc_id, chunks, vectors|None) -> int`（FTS5 + 可选 vec；替换既有行）
- `async delete_chunks(doc_id) -> None`
- `async keyword_search(resource_name, query, top_k) -> Sequence[Passage]`（bm25）
- `async vector_search(resource_name, vector, top_k) -> Sequence[Passage]`（sqlite-vec KNN）

`vec_chunks` 的读写限定在 `infrastructure/knowledge/vec_index.py`（`sqlite_vec` 的唯一 importer）；chunk 文本删除 + FTS5 在 `sqlite_index.py`。应用层把这些仓储加上 `grep.py` 与 embedder 客户端（`infrastructure/knowledge/embeddings.py`）组合在共享检索门面 `KnowledgeRetrieval`（`application/knowledge/retrieval.py`）之后，由它持有 keyword↔vector 的决策（包括带标注的 vector→keyword 回退）。

## 磁盘布局

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

没有逐语料的 `index/`、`text/` 或 `chroma/` 目录 —— 所有索引都在 `coffer.db` 里。`infrastructure/knowledge/paths.py` 是**唯一**构造这些路径的模块：

- `knowledge_root() -> Path` —— `~/.coffer/knowledge/`（测试可经 `COFFER_KNOWLEDGE_ROOT` 覆盖）
- `kb_dir(name) -> Path` / `docs_dir(name) -> Path` / `raw_dir(name) -> Path`
- `doc_path(name, doc_id) -> Path` / `raw_path(name, doc_id, ext) -> Path`

### Markdown frontmatter

每个 `docs/<doc-id>.md` 自我描述：

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

## 单一 re-index 例程（`application/knowledge/reindex.py`，与 memory 共享）

所有写路径（ingest、重新上传、编辑、reindex 扫描）都汇入一个幂等例程（`Reindexer`）。逐 store 的 asyncio 锁（`application/knowledge/locks.py`，`StoreLocks`）串行化对同一 store 的写入，使并发 ingest/编辑不会交错更新索引：

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

`coffer kb reindex <name>` 重新扫描 `docs/` 目录找增量，逐文件运行该例程，从文件重建全部 SQLite 状态。

## 级联与完整性规则

| 动作                                | 效果                                                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 删除一个 Document                   | 移除 `docs/<id>.md` + `raw/<id>.<ext>`；删除其 `chunks`/`documents_fts`/`vec_chunks` 行；删除 `documents` 行；审计 `KB_DOCUMENT_DELETED`。                |
| 删除一个 KB                         | `on_delete` 钩子：`delete_resource(kind, name)`（documents + chunks + fts + vec）；`rmtree(kb_dir(name))`；删除 `resources` 行；审计 `RESOURCE_DELETED` 带 KB 快照。 |
| 重命名 KB                           | 禁止（Resource 名不可变；框架强制）。                                                                                                                       |
| 修改 `chunk_size` / `chunk_overlap` | 允许 → 对语料 re-chunk + re-index。                                                                                                                         |
| 修改 `embedding` 模型 / dimensions  | 允许 → 对语料重新 embedding（宽度变化时重建 `vec_chunks`）。                                                                                                |
| 编辑文档的 markdown                 | `source_mode = edited` → reindex 例程。                                                                                                                     |
| 重转换文档                          | 仅当 `source_mode == converted` 时允许；`edited` ⇒ `ReconversionBlocked`。重新上传新 source 会重置为 `converted`。                                          |

## 新增审计事件

`AuditEventType` 是可扩展的 `StrEnum`。新增：

| 值                       | 何时发出                                                       |
| ------------------------ | ---------------------------------------------------------------- |
| `"kb_document_ingested"` | 新文档首次索引后                                                 |
| `"kb_document_updated"`  | reindex 例程对变更文档重建索引后（编辑 / 重新上传）              |
| `"kb_document_deleted"`  | 文档删除后                                                       |
| `"kb_reindexed"`         | 一次完整 `coffer kb reindex` 后（携带逐文档计数）                |

KB 生命周期由 kind 无关核心的 `resource_created` / `resource_deleted` 覆盖。内建 MCP 工具调用记录到 `mcp_invocations`（仅工具名 + who/when/duration/outcome）。

## Importlinter 契约（新增或修订）

| 契约                                                | 效果                                                                                                                                                                |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 —— 分层架构                                       | 不变                                                                                                                                                                  |
| 2 —— infrastructure ↛ surfaces                      | 不变                                                                                                                                                                  |
| 3 —— domain 纯净                                    | 不变；`domain/knowledge/*` 只 import 标准库 + Pydantic                                                                                                                |
| 4 —— keyring 限定于 infrastructure                  | 不变（embedding `credential_ref` 经凭据模块解析）                                                                                                                     |
| 5 —— 禁止跨 kind import                             | **扩展**：加入 `coffer.{application,surfaces.http}.knowledge_base`；共享的 `coffer.{domain,infrastructure}.knowledge` 基底豁免（kind 无关）                           |
| 6 —— kind 无关核心 ↛ kind 专属                      | **扩展**：把 `knowledge_base` 模块加入 `forbidden_modules`                                                                                                            |
| 7（取代旧 LlamaIndex 规则）—— 引擎限定              | `coffer.application.*` 与 `coffer.domain.*` 不得 import `markitdown`、`docling`、`sqlite_vec`、`openai` 或 `fastembed`；只有 `coffer.infrastructure.knowledge.*` 可以 |

## 线上契约（REST）

位于 `contracts/api.openapi.yaml`。要点（全应用统一错误包络 `{error:{code,message,details}}`）：

- `POST /api/v1/knowledge_bases` —— 创建 KB
- `GET /api/v1/knowledge_bases` —— 列出 KB
- `GET /api/v1/knowledge_bases/{name}` —— 获取单个 KB
- `POST /api/v1/knowledge_bases/{name}/documents` —— multipart 上传 + ingest（任意格式）
- `GET /api/v1/knowledge_bases/{name}/documents` —— 分页列表
- `GET /api/v1/knowledge_bases/{name}/documents/{doc_id}` —— markdown 正文 + frontmatter
- `PUT /api/v1/knowledge_bases/{name}/documents/{doc_id}` —— 编辑 markdown（置 `source_mode=edited`，重建索引）
- `POST /api/v1/knowledge_bases/{name}/documents/{doc_id}/reconvert` —— 从 `raw/` 重跑转换（一旦手工编辑过即被 `RECONVERSION_BLOCKED` 拦截）
- `DELETE /api/v1/knowledge_bases/{name}/documents/{doc_id}` —— 删除单个文档
- `POST /api/v1/knowledge_bases/{name}/reindex` —— 重扫描 + 从文件重建索引
- `POST /api/v1/knowledge_bases/{name}/search` —— `{query, top_k?, mode?}` → 排序 passage（+ `fallback`）
- `POST /api/v1/knowledge_bases/{name}/grep` —— `{pattern, max_matches?}` → 文件/行命中
- `GET /api/v1/knowledge_bases/{name}/metrics` —— 计数 + 已建索引模式 + 磁盘字节数

kind 无关的 `/api/v1/resources/...` 端点对 KB 继续可用（list / get / delete / enable / disable）。
