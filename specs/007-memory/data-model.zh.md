# Data Model —— 007 Memory（跨 agent 共享记忆）

> English: [data-model.md](./data-model.md)

memory 面的实体、端口、统一 SQLite schema（与 knowledge base 共享）以及落盘规范化布局。

## Domain entities (`backend/coffer/domain/memory/`)

### `MemoryStoreConfig` (`domain/memory/config.py`)

Pydantic v2 `BaseModel`。当 `kind == "memory"` 时存于 `Resource.config`。检索/embedding 配置形状与 KB 面共享。

| 字段                       | 类型                                       | 说明                                                                       |
| -------------------------- | ------------------------------------------ | -------------------------------------------------------------------------- |
| `retrieval_modes`          | `list[Literal["grep","keyword","vector"]]` | 启用的模式。默认 `["grep","keyword"]`（零配置、离线）。`vector` 为可选项。 |
| `default_mode`             | `Literal["grep","keyword","vector"]`       | 默认 `"keyword"`。                                                         |
| `embedding_provider`       | `str \| None`                              | OpenAI 兼容 provider id（如 `openai`、`voyage`、`local`）。`vector` 必填。 |
| `embedding_model`          | `str \| None`                              | 如 `bge-m3`（本地）或某云端模型。`vector` 必填。                           |
| `embedding_base_url`       | `str \| None`                              | OpenAI 兼容 provider 的 base URL 覆盖。                                    |
| `embedding_credential_ref` | `str \| None`                              | embedding API key 的 keychain ref（绝不明文）。                            |
| `max_fact_chars`           | `int`                                      | 默认 `8192`；范围 `64–32768`。可变。                                       |

embedding 模型 **可变** —— 改它会重嵌整个 store（文件是真相）。没有不可变锁。

### `MemoryFact` (`domain/memory/fact.py`)

frozen dataclass；一个每条事实 markdown 文件（frontmatter + 正文）的内存视图。

| 字段                | 类型                      | 说明                                                                       |
| ------------------- | ------------------------- | -------------------------------------------------------------------------- |
| `id`                | `str`                     | 文档 id（ULID）；也是 `<fact-slug>.md` 名字的依据。                        |
| `name`              | `str`                     | frontmatter `name`（短标题；出现在 `MEMORY.md`）。                         |
| `description`       | `str`                     | frontmatter `description`（单行；出现在 `MEMORY.md`）。                    |
| `body`              | `str`                     | markdown 正文 = 事实文本。                                                 |
| `type`              | `str \| None`             | frontmatter `metadata.type`（`project`/`feedback`/`reference`/`user`/…）。 |
| `actor`             | `Literal["agent","user"]` | frontmatter `metadata.actor` —— 谁写的。                                   |
| `origin_session_id` | `str \| None`             | frontmatter `origin_session_id`。                                          |
| `created_at`        | `datetime`                | UTC。                                                                      |
| `updated_at`        | `datetime`                | UTC（编辑前 == created_at）。                                              |

### `MemoryScope` (`domain/memory/scope.py`)

```python
class MemoryScope(StrEnum):
    GLOBAL = "global"     # project_id = WORKSPACE_GLOBAL_PROJECT_ID
    PROJECT = "project"   # project_id = <project ULID> resolved from cwd

@dataclass(frozen=True)
class ResolvedScope:
    scope: MemoryScope
    project_id: str       # ULID；GLOBAL 用 sentinel
    store_dir: Path       # ~/.coffer/memory/global | projects/<ulid>
```

### `MemoryHit` (`domain/knowledge/document.py`，共享)

frozen dataclass；recall 结果。

| 字段     | 类型       | 说明                        |
| -------- | ---------- | --------------------------- |
| `id`     | `str`      | 事实（文档）id。            |
| `text`   | `str`      | 事实正文 / 命中段。         |
| `score`  | `float`    | 相关性分数。                |
| `source` | `str`      | 源事实文件的作用域 + 路径。 |
| `time`   | `datetime` | 事实的 `updated_at`。       |

### Ports

检索/索引引擎是 **共享** 的 `RetrievalPort`（`domain/knowledge/retrieval.py`），KB 与 memory 共用：

```python
class RetrievalPort(Protocol):
    async def index_document(self, store: StoreRef, doc: Document) -> None: ...
    async def remove_document(self, store: StoreRef, doc_id: str) -> None: ...
    async def reconcile(self, store: StoreRef, on_disk: Sequence[FileDelta]) -> None: ...  # 惰性 reindex
    async def search(
        self, store: StoreRef, query: str, *, mode: RetrievalMode, top_k: int
    ) -> SearchResult: ...   # 携带 hits + fallback 标志
    async def grep(self, store: StoreRef, pattern: str, **caps) -> Sequence[GrepHit]: ...
```

`AgentMemoryAdapter`（`agents/adapters/base.py`）随 agent driver、而非 memory kind：

```python
class AgentMemoryAdapter(Protocol):
    def memory_location(self, project: ProjectRef) -> Path | None: ...
    @property
    def projection_mode(self) -> Literal["SYMLINK", "RENDER", "NONE"]: ...
    def disable_native_memory(self, agent_config) -> None: ...   # 仅当原生记忆会成为另一份副本时
    def render(self, facts: Sequence[MemoryFact]) -> bytes: ...  # RENDER 模式
```

### Domain errors (`domain/knowledge/errors.py`)

- `MemoryNotFound` —— code `"MEMORY_NOT_FOUND"`。
- `MemoryRejected` —— code `"MEMORY_REJECTED"`；reasons：`"empty"`、`"too_long"`。
- `ScopeUnresolved` —— code `"SCOPE_UNRESOLVED"`；当 `scope=project` 但 cwd 不在某个 git 项目里时抛出。
- `EmbeddingUnavailable` —— 对调用方不是错误：`vector` recall 降级到 `keyword` 并在结果里设 `fallback`（绝不抛给用户）。

## 统一 SQLite schema（Alembic —— 一个重设计 revision）

重设计 revision **删除** `memory_records` 与任何 chroma/LlamaIndex 目录，然后创建与 KB 共享的、基于 `documents` 的统一 schema。没有数据迁移。

```sql
-- KB (kind='knowledge_base') 与 memory (kind='memory') 共享。
CREATE TABLE documents (
    id             TEXT PRIMARY KEY,            -- ULID
    kind           TEXT NOT NULL,               -- 'knowledge_base' | 'memory'
    resource_name  TEXT NOT NULL,               -- store 名（memory：作用域 store）
    project_id     TEXT NOT NULL,               -- WORKSPACE_GLOBAL sentinel | 项目 ULID
    path           TEXT NOT NULL,               -- 落盘规范化 .md 路径 = 真相
    title          TEXT,                        -- memory：frontmatter `name`
    description    TEXT,                         -- memory：frontmatter `description`
    metadata       TEXT NOT NULL DEFAULT '{}',   -- JSON；memory：{type, actor, origin_session_id}
    content_sha256 TEXT NOT NULL,               -- 供 lazy-reindex 增量检测
    source_mode    TEXT NOT NULL DEFAULT 'native', -- memory：'native'
    created_at     TIMESTAMP NOT NULL,
    updated_at     TIMESTAMP NOT NULL
);
CREATE INDEX idx_documents_store ON documents(kind, resource_name, updated_at DESC);
CREATE INDEX idx_documents_project ON documents(project_id);

CREATE TABLE chunks (
    id           TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL               -- memory：每条事实一个 chunk
);

-- FTS5 external-content（文本留在文件里，不复制）。
CREATE VIRTUAL TABLE documents_fts USING fts5(
    text, content='', tokenize='unicode61'
);

-- sqlite-vec 虚拟表（仅当启用某个 vector 模式时）。
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY, embedding FLOAT[<dim>]
);
```

memory 面的 `documents.metadata` 被 Pydantic 校验为 `{type, actor, origin_session_id}`。按工程约定，metadata JSON 用 `model_dump(mode="json")` 构建，使 `datetime`/`AnyUrl` 能为 SQLite 序列化。

## 落盘规范化布局（真相源）

```
~/.coffer/
└── memory/
    ├── global/                        # project_id = WORKSPACE_GLOBAL_PROJECT_ID (00000000000000000000000000)
    │   ├── MEMORY.md                  # 重新生成的索引：- [name](file.md) — description
    │   └── <fact-slug>.md             # 每条事实文件 = 真相（frontmatter + 正文）
    └── projects/<project-ulid>/       # 每项目一个目录
        ├── MEMORY.md
        └── <fact-slug>.md
```

每条事实 `.md` 的 frontmatter：

```markdown
---
name: deploy-via-make-release
description: This repo deploys via `make release`, never git push --tags directly.
metadata:
  type: project
  actor: agent
origin_session_id: 01J...
---

This repo deploys via `make release`. Never run `git push --tags` directly; the
release target tags and pushes atomically.
```

`infrastructure/memory/paths.py` 是唯一构造这些路径的模块。`infrastructure/memory/files.py` 是唯一读写每条事实 `.md` 文件、渲染 `MEMORY.md`、扫描目录增量的模块。

## 原生投影目标（由 agent adapter 拥有，而非底座）

| Agent       | Project 层                                               | Global 层                             |
| ----------- | -------------------------------------------------------- | ------------------------------------- |
| Claude Code | SYMLINK 规范化目录 → `~/.claude/projects/<slug>/memory/` | RENDER block 进 `~/.claude/CLAUDE.md` |
| Codex       | RENDER block 进 `<project>/AGENTS.md`；禁用 `memories`   | RENDER block 进 `~/.codex/AGENTS.md`  |

managed block 标记（Next.js / claude-mem 先例）：

```
<!-- coffer:memory:start (managed, do not edit) -->
… rendered facts …
<!-- coffer:memory:end -->
```

## Cascade & integrity rules

| 动作                       | 效果                                                                                                         |
| -------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `remember` / 用户添加      | 写 `<fact-slug>.md` → 重生 `MEMORY.md` → 索引进 `documents`/`chunks`/FTS5/(vec) → 审计 → 重新投影。          |
| `update_memory` / 用户编辑 | 重写 `.md` → 单一 re-index 例程（sha256 变 → 重 chunk/embed）→ 重生 `MEMORY.md` → 审计 → 重新投影。          |
| `forget` / 用户删除        | 删 `.md` → 移除 `documents`/`chunks`/FTS5/vec 行 → 重生 `MEMORY.md` → 审计 → 重新投影。                      |
| 清空一个作用域             | 删 store 全部 `.md` → 移除全部索引行 → 清空 `MEMORY.md` → 重新投影为空 → 审计。store Resource 保留。         |
| 删除 store Resource        | 移除 store 的 `documents` 行、`rmtree(store_dir)`、拆除投影（还原 symlink / 剥离 managed block）、审计。     |
| Recall                     | **Lazy reindex-on-read**：按 `content_sha256` 扫描 `store_dir` 增量 → `reconcile` → 搜索。不写 `MEMORY.md`。 |
| 改 embedding 模型          | 允许 → 下次索引时重嵌整个 store（文件是真相）。                                                              |
| 改 `max_fact_chars`        | 允许。                                                                                                       |

## 单一 re-index 例程（与 KB 共享）

```
compute content_sha256 of the new markdown
 ├ unchanged → skip (no-op)
 └ changed   → delete old chunks/FTS5/vec rows → re-chunk → (vector) re-embed
              → insert new → update documents row → audit *_UPDATED
```

所有 memory 写路径（remember、update、用户编辑、lazy reindex 扫描）都汇入这一个例程。

## Audit events added

| 值                   | 何时发出                   |
| -------------------- | -------------------------- |
| `"memory_added"`     | 成功 `remember`/用户添加后 |
| `"memory_updated"`   | 成功 `update`/用户编辑后   |
| `"memory_deleted"`   | 成功 `forget`/用户删除后   |
| `"memory_cleared"`   | 清空一个作用域后           |
| `"memory_projected"` | 建立/刷新一次投影后        |

## Wire contract (REST)

在 `contracts/api.openapi.yaml`。路由在 `/api/v1/memory_stores` 下（list/get/metrics；事实的 add/list/get/edit/delete/clear；recall）加投影端点（list/establish/remove）。kind-agnostic 的 `/api/v1/resources/...` 对 memory store 继续可用。app-wide 错误信封：`{ "error": { "code", "message", "details" } }`。
