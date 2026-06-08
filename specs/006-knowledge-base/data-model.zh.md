# Data Model —— 006 Knowledge Base（重新设计）

> English: [data-model.md](./data-model.md)

知识基底 KB 面的实体、端口、**统一的** SQLite schema（与 `memory` kind，spec 007，共享）以及磁盘布局。架构不变量在 [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)；本文件只描述模型。

**原则**：磁盘上的 Markdown 文件是**唯一真相源**。每一行 SQLite（`documents`、`chunks`、`documents_fts`、`vec_chunks`）都是**可由文件经 reindex 例程派生重建**的。不存在双真相源。

## Domain 实体

基底 domain（`backend/coffer/domain/knowledge/`）与 memory kind 共享；KB 配置在 KB application 层。

### `KnowledgeBaseConfig` (`application/knowledge_base/config.py`)

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

| Field            | Type          | Notes                                                                                                                                        |
| ---------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `provider`       | `str`         | `"openai"`、`"openrouter"`、`"voyage"`、`"jina"`、`"gemini"`、`"azure"`、`"dashscope"`、`"ollama"`、`"lmstudio"` 或 `"local"`（fastembed）。 |
| `model`          | `str`         | embedding 模型 id，如 `text-embedding-3-small`、`bge-m3`。                                                                                   |
| `base_url`       | `str \| None` | OpenAI 兼容端点；`None` 用 provider 默认；`local` 时忽略。                                                                                   |
| `credential_ref` | `str \| None` | keychain ref（绝不明文）；`local` / 无密钥端点时为 `None`。可选回退到 LLM 凭据 ref。                                                         |
| `dimensions`     | `int`         | 向量宽度；固定 `vec_chunks` 列。宽度变化时重新 embedding 会重建 vec 表。                                                                     |

### `Document` (`domain/knowledge/document.py`)

Frozen dataclass；每个 Markdown 文件一行，**按 `kind` 区分**。KB 与 memory 共享此实体；KB 专属数据放在 `metadata`。

| Field                       | Type          | Notes                                                                           |
| --------------------------- | ------------- | ------------------------------------------------------------------------------- |
| `id`                        | `str`         | `source_sha256` 的前 16 个 hex 字符（KB）—— 即 doc id 与 `<doc-id>.md` 文件名。 |
| `kind`                      | `str`         | KB 行为 `"knowledge_base"`。                                                    |
| `resource_name`             | `str`         | KB resource 名。                                                                |
| `path`                      | `str`         | Markdown 文件相对路径，`docs/<doc-id>.md`。                                     |
| `title`                     | `str`         | 来自 frontmatter / 首个标题 / 文件名。                                          |
| `description`               | `str \| None` | 可选摘要。                                                                      |
| `content_sha256`            | `str`         | **Markdown** body 的哈希 —— reindex no-op 闸门。                                |
| `source_mode`               | `str`         | `"converted"` 或 `"edited"`。                                                   |
| `metadata`                  | `dict`        | per-face JSON；KB 键见下。                                                      |
| `created_at` / `updated_at` | `datetime`    | UTC。                                                                           |

KB `metadata` 键：`original_filename`、`original_format`、`source_sha256`、`converted_at`、`conversion_engine`。

### `Passage`、`GrepHit`、`SearchResult` (`domain/knowledge/retrieval.py`)

Frozen 值对象（不持久化）：

- `Passage`：`document_id`、`title`、`text`、`score: float`、`position: int`。
- `GrepHit`：`path`、`line_number: int`、`line`。
- `SearchResult`：`mode: RetrievalMode`、`passages: Sequence[Passage]`、`fallback: RetrievalMode | None`（当请求的 `vector` 检索降级为 `keyword` 时设置）。

### 端口 (`domain/knowledge/`)

用 `typing.Protocol` 表达 Coffer 需要的东西，让具体引擎留在 `infrastructure/`：

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

grep 是独立的 `infrastructure/knowledge/grep.py` ripgrep wrapper（无索引），由 max-matches + 超时限制。

### Domain errors（加到 `domain/errors.py`）

- `KBNotFound` —— code `"KB_NOT_FOUND"`。
- `DocumentNotFound` —— code `"DOCUMENT_NOT_FOUND"`。
- `IngestRejected` —— code `"INGEST_REJECTED"`；reason ∈ `{"empty","too_large","unsupported_type","duplicate"}`。
- `EngineUnavailable` —— code `"ENGINE_UNAVAILABLE"`；当请求操作所需的转换库 / sqlite-vec / embedding provider 不可用时抛出。
- `ReconversionBlocked` —— code `"RECONVERSION_BLOCKED"`；当对 `source_mode == "edited"` 的文档重新转换时抛出。

## SQLite schema（一个 Alembic 迁移；**删除** `kb_documents`）

迁移删掉旧的 `kb_documents` / `memory_records` 表并创建统一 schema。**没有数据迁移**（分支未发布）。

```sql
-- One row per Markdown file, shared by KB and memory, discriminated by `kind`.
CREATE TABLE documents (
    id              TEXT      NOT NULL,             -- 16-hex doc id (== <doc-id>.md)
    kind            TEXT      NOT NULL,             -- 'knowledge_base' | 'memory'
    resource_name   TEXT      NOT NULL,             -- KB name (or memory scope key)
    path            TEXT      NOT NULL,             -- relative path of the markdown file
    title           TEXT      NOT NULL,
    description     TEXT,
    content_sha256  TEXT      NOT NULL,             -- hash of the markdown body (reindex no-op gate)
    source_mode     TEXT      NOT NULL,             -- 'converted' | 'edited'
    metadata        TEXT      NOT NULL,             -- JSON, per-face
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (kind, resource_name, id)
);
CREATE INDEX idx_documents_kind_res_time ON documents(kind, resource_name, updated_at DESC);
-- KB dedup is on metadata->>'source_sha256'; enforced in the repo, not a SQL unique index,
-- because memory rows have no source file.

CREATE TABLE chunks (
    id              TEXT      NOT NULL PRIMARY KEY, -- '<doc-id>:<position>'
    document_id     TEXT      NOT NULL,
    kind            TEXT      NOT NULL,
    resource_name   TEXT      NOT NULL,
    position        INTEGER   NOT NULL              -- 0-based ordinal within the document
    -- chunk TEXT is NOT stored here; it lives in documents_fts (external content) + on disk
);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- FTS5 external-content table over chunk text; bm25() ranks keyword search.
CREATE VIRTUAL TABLE documents_fts USING fts5(
    text,
    resource_name UNINDEXED,
    content='',                                     -- contentless: text not duplicated in SQLite
    tokenize='unicode61'
);

-- sqlite-vec virtual table; one row per chunk with a vector. Width = EmbeddingConfig.dimensions.
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[768]                            -- width set per KB at create/re-embed time
);
```

**为何用复合 `(kind, resource_name, id)` 主键**：同一个内容寻址的 doc id 可能在两张面、跨多个 resource 出现；复合键让统一表无歧义，并让 `on_delete` 把级联限定在一个 resource。

**级联是 application 级**（kind 的 `on_delete` hook），不是 FK：hook 删掉该 resource 的 `documents`/`chunks`/`documents_fts`/`vec_chunks` 行，再 `rmtree` 磁盘目录。

## SQLAlchemy ORM (`infrastructure/knowledge/sqlite_index.py`)

`DocumentModel` 与 `ChunkModel` 映射到 `documents` / `chunks`，注册在与其余表相同的 `Base.metadata` 上。同模块暴露 `KnowledgeIndexRepo`：

- `async upsert_document(d: Document) -> Document`
- `async list_documents(kind, resource_name, *, limit, offset) -> list[Document]`
- `async count_documents(kind, resource_name) -> int`
- `async get_document(kind, resource_name, doc_id) -> Document | None`
- `async exists_source(kind, resource_name, source_sha256) -> bool`（读 `metadata->>'source_sha256'`）
- `async delete_document(kind, resource_name, doc_id) -> bool`（同时删 chunks/fts/vec）
- `async delete_resource(kind, resource_name) -> int`
- `async replace_chunks(doc_id, chunks, vectors|None) -> int`（FTS5 + 可选 vec）
- `async keyword_search(...) -> list[Passage]` / `async vector_search(...) -> list[Passage]`

`vec_chunks` 的读写限制在 `infrastructure/knowledge/vec_index.py`（唯一 import `sqlite_vec` 的模块）。

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

没有 per-corpus `index/`、`text/` 或 `chroma/` 目录 —— 所有索引都在 `coffer.db`。`infrastructure/knowledge/paths.py` 是**唯一**构造这些路径的模块：

- `knowledge_root() -> Path` —— `~/.coffer/knowledge/`（测试经 `COFFER_KNOWLEDGE_ROOT` 覆盖）
- `kb_dir(name) -> Path` / `docs_dir(name) -> Path` / `raw_dir(name) -> Path`
- `doc_path(name, doc_id) -> Path` / `raw_path(name, doc_id, ext) -> Path`

### Markdown frontmatter

每个 `docs/<doc-id>.md` 自描述：

```yaml
---
title: Architecture Notes
source_filename: architecture.docx
source_format: docx
source_sha256: 9f8e…
ingested_at: 2026-06-09T10:11:12Z
converter: markitdown
source_mode: converted
---
```

## 单一 re-index 例程 (`application/knowledge_base/reindex.py`)

所有写路径（ingest、re-upload、edit、reindex scan）都汇入一个幂等例程：

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

`coffer kb reindex <name>` 重扫 `docs/` 目录找增量并对每个文件跑此例程，从文件重建全部 SQLite 状态。

## 级联与完整性规则

| Action                            | Effect                                                                                                                                                              |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 删一个 Document                   | 删 `docs/<id>.md` + `raw/<id>.<ext>`；删其 `chunks`/`documents_fts`/`vec_chunks` 行；删 `documents` 行；audit `KB_DOCUMENT_DELETED`。                               |
| 删一个 KB                         | `on_delete` hook：`delete_resource(kind, name)`（documents + chunks + fts + vec）；`rmtree(kb_dir(name))`；删 `resources` 行；audit `RESOURCE_DELETED` 带 KB 快照。 |
| 重命名 KB                         | 禁止（Resource 名不可变；框架强制）。                                                                                                                               |
| 改 `chunk_size` / `chunk_overlap` | 允许 → 重新切块 + 重建语料索引。                                                                                                                                    |
| 改 `embedding` 模型 / dimensions  | 允许 → 重新 embedding 语料（宽度变则重建 `vec_chunks`）。                                                                                                           |
| 编辑某文档的 markdown             | `source_mode = edited` → reindex 例程。                                                                                                                             |
| 重新转换某文档                    | 仅当 `source_mode == converted` 时允许；`edited` ⇒ `ReconversionBlocked`。重新上传新源重置为 `converted`。                                                          |

## 新增审计事件

`AuditEventType` 是可扩展的 `StrEnum`。新增：

| Value                    | When emitted                                           |
| ------------------------ | ------------------------------------------------------ |
| `"kb_document_ingested"` | 新文档首次索引之后                                     |
| `"kb_document_updated"`  | reindex 例程对变更文档重新索引之后（edit / re-upload） |
| `"kb_document_deleted"`  | 文档删除之后                                           |
| `"kb_reindexed"`         | 一次完整 `coffer kb reindex` 之后（带每文档计数）      |

kind 无关核心的 `resource_created` / `resource_deleted` 覆盖 KB 生命周期。内置 MCP 工具调用记入 `mcp_invocations`（仅 tool 名 + who/when/duration/outcome）。

## Importlinter contracts（新增或修订）

| Contract                                              | Effect                                                                                                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — layered architecture                              | 不变                                                                                                                                                                |
| 2 — infrastructure ↛ surfaces                         | 不变                                                                                                                                                                |
| 3 — domain is pure                                    | 不变；`domain/knowledge/*` 只 import stdlib + Pydantic                                                                                                              |
| 4 — keyring confined to infrastructure                | 不变（embedding `credential_ref` 经凭据模块解析）                                                                                                                   |
| 5 — cross-kind imports forbidden                      | **EXTEND**：加 `coffer.{application,surfaces.http}.knowledge_base`；共享的 `coffer.{domain,infrastructure}.knowledge` 基底豁免（kind 无关）                         |
| 6 — kind-agnostic core ↛ kind-specific                | **EXTEND**：把 `knowledge_base` 模块加入 `forbidden_modules`                                                                                                        |
| 7 (REPLACES old LlamaIndex rule) — engine confinement | `coffer.application.*` 与 `coffer.domain.*` 不得 import `markitdown`、`docling`、`sqlite_vec`、`openai`、`fastembed`；只有 `coffer.infrastructure.knowledge.*` 可以 |

## Wire contract (REST)

在 `contracts/api.openapi.yaml`。要点（全应用错误信封 `{error:{code,message,details}}`）：

- `POST /api/v1/knowledge_bases` —— 创建 KB
- `GET /api/v1/knowledge_bases` —— 列出 KB
- `GET /api/v1/knowledge_bases/{name}` —— 取单个 KB
- `POST /api/v1/knowledge_bases/{name}/documents` —— multipart 上传 + ingest（任意格式）
- `GET /api/v1/knowledge_bases/{name}/documents` —— 分页列表
- `GET /api/v1/knowledge_bases/{name}/documents/{doc_id}` —— markdown body + frontmatter
- `PUT /api/v1/knowledge_bases/{name}/documents/{doc_id}` —— 编辑 markdown（置 `source_mode=edited`，重建索引）
- `DELETE /api/v1/knowledge_bases/{name}/documents/{doc_id}` —— 删一个文档
- `POST /api/v1/knowledge_bases/{name}/reindex` —— 重扫 + 从文件重建索引
- `POST /api/v1/knowledge_bases/{name}/search` —— `{query, top_k?, mode?}` → 排序 passage（+ `fallback`）
- `POST /api/v1/knowledge_bases/{name}/grep` —— `{pattern, max_matches?}` → file/line 命中
- `GET /api/v1/knowledge_bases/{name}/metrics` —— counts + indexed modes + disk bytes

kind 无关的 `/api/v1/resources/...` 端点对 KB 继续有效（list / get / delete / enable / disable）。
