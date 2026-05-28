# Data Model —— 006 Knowledge Base Manager

> English: [data-model.md](./data-model.md)

知识库 kind 的实体、端口接口、SQLite schema 与磁盘布局。沿用 001-mcp-gateway 的 data-model.md 写法。

## Domain 实体 (`backend/coffer/domain/knowledge_base/`)

### `KnowledgeBaseConfig` (`domain/knowledge_base/config.py`)

Pydantic v2 `BaseModel`。在 `kind == "knowledge_base"` 时挂在 `Resource.config` 中。

| 字段                 | 类型  | 说明                                                                                 |
| -------------------- | ----- | ------------------------------------------------------------------------------------ |
| `embedding_model`    | `str` | HuggingFace 模型 id（如 `BAAI/bge-small-en-v1.5`）。非空，必须含 `/`。创建后不可变。 |
| `chunk_size`         | `int` | 默认 `512`；范围 `64–2048`。                                                         |
| `chunk_overlap`      | `int` | 默认 `64`；范围 `0–chunk_size/2`。                                                   |
| `max_document_bytes` | `int` | 默认 `25 * 1024 * 1024`；范围 `1024–104857600`。                                     |

新建 KB 的 `Resource.config` JSON 大致如下：

```json
{
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "chunk_size": 512,
  "chunk_overlap": 64,
  "max_document_bytes": 26214400
}
```

### `Document` (`domain/knowledge_base/document.py`)

朴素 Python dataclass（不用 Pydantic —— domain 保持 pure）：

| 字段          | 类型       | 说明                                   |
| ------------- | ---------- | -------------------------------------- |
| `id`          | `str`      | SHA-256 内容哈希的前 16 个十六进制字符 |
| `kb_name`     | `str`      | KB 的资源名                            |
| `filename`    | `str`      | 原始文件名（仅显示用）                 |
| `extension`   | `str`      | 小写扩展名含点号，如 `.md`             |
| `size_bytes`  | `int`      | 原始文件大小                           |
| `sha256`      | `str`      | 完整的 64 字符内容哈希                 |
| `chunk_count` | `int`      | 已索引的 chunk 数                      |
| `ingested_at` | `datetime` | UTC                                    |

### `Passage` (`domain/knowledge_base/store.py`)

frozen dataclass。`KnowledgeBaseStore.search()` 的返回值。pure 值对象。

| 字段          | 类型    | 说明                            |
| ------------- | ------- | ------------------------------- |
| `document_id` | `str`   | 与 `Document.id` 相同           |
| `filename`    | `str`   | 源文档文件名                    |
| `text`        | `str`   | chunk 文本（已 trim）           |
| `score`       | `float` | 相关性分数 `[0.0, 1.0]`         |
| `position`    | `int`   | chunk 在源文档中的 0-based 序号 |

### `KnowledgeBaseStore`（端口） (`domain/knowledge_base/store.py`)

`typing.Protocol`。方法按 **Coffer 的需要** 定义，不按 LlamaIndex 提供的形状：

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

`ingest` 返回 adapter 为该文档生成的 chunk 数；application 服务把这个值持久化为 `Document.chunk_count`。

真实 adapter（`LlamaIndexKnowledgeBaseStore`）是唯一 import LlamaIndex 的实现。测试用的 `FakeKnowledgeBaseStore` 把 chunk 存在 dict 里，返回朴素分数。

### Domain errors（追加到 `domain/errors.py`）

- `KBNotFound` —— code `"KB_NOT_FOUND"`，服务在未知 kb_name 时抛。
- `DocumentNotFound` —— code `"DOCUMENT_NOT_FOUND"`。
- `IngestRejected` —— code `"INGEST_REJECTED"`；携带 `"empty_text"` / `"too_large"` / `"unsupported_type"` / `"duplicate"` 之一。
- `EngineUnavailable` —— code `"ENGINE_UNAVAILABLE"`；启动时引擎 adapter 无法构造则抛。

## SQLite schema（Alembic revision `0007`）

迁移仅新增 `kb_documents` 一张表。`resources` 表照旧（与 kind 无关）。

```sql
CREATE TABLE kb_documents (
    id              TEXT      NOT NULL,             -- sha256 前 16 个十六进制
    kb_name         TEXT      NOT NULL,             -- 反规范化的资源名；见下方说明
    filename        TEXT      NOT NULL,
    extension       TEXT      NOT NULL,
    size_bytes      INTEGER   NOT NULL,
    sha256          TEXT      NOT NULL,             -- 完整 64 字符内容哈希
    chunk_count     INTEGER   NOT NULL,
    ingested_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (kb_name, id)
);
CREATE INDEX idx_kb_documents_kb_time ON kb_documents(kb_name, ingested_at DESC);
CREATE UNIQUE INDEX uq_kb_documents_kb_sha256 ON kb_documents(kb_name, sha256);
```

**为什么用 `kb_name` 而非 `resource_id` 外键**：KB 的其他持久态在文件系统上按 name 编址，按 name join 让磁盘布局与 SQL 表保持对齐。KB 改名被 kind-agnostic 内核禁止（`Resource.name` 不可变），所以反规范化不会漂。

KB 删除时的级联是 **application 级**（在 on_delete 钩子里），不是 FK —— 钩子遍历表删行、再删磁盘目录、再 dispose 内存 store。

## SQLAlchemy ORM (`infrastructure/knowledge_base/persistence.py`)

一个 ORM 模型 `KBDocumentModel` 映射到 `kb_documents`，注册到与 MCP 表相同的 `Base.metadata`。转换：`to_domain() -> Document`，模块级 `from_domain(d: Document) -> KBDocumentModel`。

同一模块给出薄薄的 `KBDocumentRepo`：

- `async create(d: Document) -> Document`
- `async list_by_kb(kb_name: str, *, limit: int, offset: int) -> list[Document]`
- `async count_by_kb(kb_name: str) -> int`
- `async get(kb_name: str, document_id: str) -> Document | None`
- `async exists_by_hash(kb_name: str, sha256: str) -> bool`
- `async delete(kb_name: str, document_id: str) -> bool`
- `async delete_all(kb_name: str) -> int`

## 磁盘布局

```
~/.coffer/
└── kb/
    └── <kb-name>/
        ├── raw/
        │   └── <document_id><original_ext>     # 保留原始字节
        └── index/
            └── ...                              # LlamaIndex persist 目录
```

`<kb-name>` 是用户选定的资源名；允许的字符遵循资源命名规则（不含 `:`、不以 `.` 开头）。

`infrastructure/knowledge_base/paths.py` 是 **唯一** 构造这些路径的模块，对外暴露：

- `kb_root() -> Path` —— `~/.coffer/kb/`（测试可通过 `COFFER_KB_ROOT` 环境变量改）
- `kb_dir(kb_name: str) -> Path`
- `kb_raw_dir(kb_name: str) -> Path`
- `kb_index_dir(kb_name: str) -> Path`
- `raw_file_path(kb_name: str, document_id: str, extension: str) -> Path`

## 级联与一致性规则

| 操作                                                  | 效果                                                                                                                                                                                     |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 删除一个 Document（`kb_documents` 行）                | 删除原始文件 `<id><ext>`；从 LlamaIndex 索引中移除该文档的 chunk；写一行审计 `kb_document_deleted`。                                                                                     |
| 删除一个 KB（Resource 删除）                          | `on_delete` 钩子：dispose 内存 store；删除 chunk；`KBDocumentRepo.delete_all`；`shutil.rmtree(kb_dir(kb_name))`；按标准删除级联到 `resources` 行；审计 `resource_deleted` 携带 kb 快照。 |
| 改 KB 名                                              | 禁止（Resource 名不可变，框架已强制）。                                                                                                                                                  |
| 改 `embedding_model` / `chunk_size` / `chunk_overlap` | 创建后禁止（`ResourceService.update_config` 校验拒绝）。                                                                                                                                 |
| 改 `max_document_bytes`                               | 允许（不会让既有 chunk 失效）。                                                                                                                                                          |

## 新增审计事件

`AuditEventType` 已有，可扩展为 `StrEnum`。本规范新增：

| 值                       | 触发时机                                                                     |
| ------------------------ | ---------------------------------------------------------------------------- |
| `"kb_document_ingested"` | `KnowledgeBaseService.ingest` 后                                             |
| `"kb_document_deleted"`  | `KnowledgeBaseService.delete_document` 后                                    |
| `"kb_searched"`          | （可选，默认关）每次检索 —— 由 `COFFER_KB_AUDIT_SEARCHES` 门控，因为可能太吵 |

`resource_created` / `resource_deleted` 已由 kind-agnostic 内核负责；新增事件覆盖内核看不见的文档级活动。

## 默认保留策略种子

本 KB 摄入 **不** 新增可清理表。文档是用户自己的内容，从不自动清理。相关日志由既有的 `audit_log` 和 `mcp_invocations` 策略覆盖。

## Importlinter 契约（新增或扩展）

| 契约                                    | 对本规范的影响                                                                                                                                         |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 —— 分层                               | 不变（新模块遵循 surfaces → application → domain）                                                                                                     |
| 2 —— infrastructure ↛ surfaces          | 不变                                                                                                                                                   |
| 3 —— domain 是 pure                     | 不变；新 `domain/knowledge_base/*` 只 import 标准库 + Pydantic                                                                                         |
| 4 —— keyring 限定在 infrastructure      | 不变                                                                                                                                                   |
| 5 —— 禁止跨 kind import                 | **扩展**：把 `coffer.{domain,application,infrastructure,surfaces.http}.knowledge_base` 加入 source；禁止其互相 import 同级别其他 kind                  |
| 6 —— kind-agnostic 内核 ↛ kind-specific | **扩展**：把 `coffer.{...}.knowledge_base` 加入 `forbidden_modules`                                                                                    |
| 7（新增）—— RAG 引擎隔离                | `coffer.application.*` 与 `coffer.domain.*` 不得 import `llama_index`（任何子模块）。仅 `coffer.infrastructure.knowledge_base.llamaindex_store` 可以。 |

## Wire contract (REST)

落在 `contracts/api.openapi.yaml`。要点：

- `POST /api/v1/knowledge_bases` —— 创建 KB（内部委派给 kind-agnostic 资源 POST；这个 convenience endpoint 是为了与 `POST /api/v1/resources` 对称、对客户端命名更清楚）
- `POST /api/v1/knowledge_bases/{name}/documents` —— 多部分上传，`multipart/form-data` 含 `file=<binary>`
- `GET /api/v1/knowledge_bases/{name}/documents` —— 分页列出
- `GET /api/v1/knowledge_bases/{name}/documents/{document_id}` —— 单文档 metadata + 文本
- `DELETE /api/v1/knowledge_bases/{name}/documents/{document_id}` —— 删除单文档
- `POST /api/v1/knowledge_bases/{name}/search` —— body：`{ "query": str, "top_k": int? }` → `[ Passage, ... ]`
- `GET /api/v1/knowledge_bases/{name}/metrics` —— `{ document_count: int, disk_bytes: int }`

kind-agnostic 的 `/api/v1/resources/...` 端点对 KB 继续可用（list / get / delete / enable / disable）—— 这些操作完全与 kind 无关。
