# Data Model —— 007 Memory（跨 agent 共享记忆）

> English: [data-model.md](./data-model.md)

> **历史文档 —— 2026-09-10。** spec knowledge（Knowledge Base）与 spec knowledge（Memory）
> 于当日合并为统一的 **Knowledge Layer（知识层）**。合并后的模型以
> [`spec.md`](./spec.md) 为准 —— 一个 `knowledge` kind、三种 scope、单一存储根
> `~/.coffer/knowledge/<scope>/`、六个 `coffer__*` 工具。本文档记录的是合并之前
> 的设计；凡出现「memory 面」「`memory` kind」`~/.coffer/memory/`
> `/api/v1/memory_stores` 或 `coffer memory …` 之处，请以 `spec.md` 中合并后的
> 对应物为准。目录名 `specs/knowledge/` 同样是历史遗留：它是所有入链与验收审计
> 所依赖的 spec id。

memory 面的实体、端口、统一 SQLite schema（与 knowledge base 共享）以及落盘规范化布局。

## Domain 实体 (`backend/coffer/domain/memory/`)

### `MemoryStoreConfig` (`domain/memory/config.py`)

Pydantic v2 `BaseModel`。当 `kind == "memory"` 时存于 `Resource.config`。与 KB 面共享检索模式词汇与 embedding 语义；字段布局刻意不同 —— 见下文。

| 字段                       | 类型                                       | 说明                                                                           |
| -------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------ |
| `retrieval_modes`          | `list[Literal["grep","keyword","vector","hybrid"]]` | 启用的模式。默认 `["grep","keyword"]`（零配置、离线）。`vector` 为可选项；`hybrid`（对 keyword+vector 做 RRF）与 KB 面共享。     |
| `default_mode`             | `Literal["grep","keyword","vector","hybrid"]`       | 默认 `"keyword"`。                                                             |
| `embedding_provider`       | `str \| None`                              | OpenAI 兼容 provider id（如 `openai`、`voyage`、`local`）。`vector` 必填。     |
| `embedding_model`          | `str \| None`                              | 如 `bge-m3`（本地）或某云端模型。`vector` 必填。                               |
| `embedding_base_url`       | `str \| None`                              | OpenAI 兼容 provider 的 base URL 覆盖。                                        |
| `embedding_credential_ref` | `str \| None`                              | embedding API key 的 keychain ref（绝不明文）。                                |
| `embedding_dimensions`     | `int`                                      | 默认 `768`；范围 `1–8192`。决定该 store 的 `vec_chunks` 表宽；随线上契约传输。 |
| `max_fact_chars`           | `int`                                      | 默认 `8192`；范围 `64–32768`。可变。                                           |

`merged_identities` 随跨作用域 AI 合并（FR-056…059）一起消失：它存在的唯一理由是让
被合并掉的项目 ULID 仍解析到幸存者，而如今已没有任何东西再铸这种别名。

embedding 模型 **可变** —— 改它会重嵌整个 store（文件是真相）。没有不可变锁。

与 spec knowledge 的形状差异是刻意的：007 把 embedding 字段保持**扁平**，让 memory 表单保持轻薄；006 则把它们嵌套在一个 `EmbeddingConfig` 对象里。自全局 embedding 重设计起，扁平字段已是遗留字段——为兼容性在 wire 上继续接受但被忽略；索引与 recall 都解析**全局** embedding 配置（见下文 `GlobalEmbeddingConfig`）。同理，007 recall 响应里的 `fallback` 是**布尔值** —— recall 跨多个 store，单一的回退模式字符串没有良定义；而 006 的单 store 搜索报告一个可空的模式枚举（`fallback: "keyword" | null`）。

### `GlobalEmbeddingConfig`（`domain/embedding_config.py`，表 `embedding_config`）

全安装级 embedding 设置——一条单例行。它**命名一条连接**，而不是再复述一遍 provider
（FR-077）：协议、base URL 与凭据都在 `provider` 资源上，使用时从它解析；这与内部引擎设置
已经在用的「先选 provider、再选模型」是同一形状。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | `bool` | 全安装级 embedding 是否开启。 |
| `connection` | `str \| None` | 一条已配置 LLM 连接（`provider` 资源）的**名字**。为空 ⇒ 配置不生效。 |
| `model` | `str \| None` | 该连接上的 embedding 模型 id。连接做了策展时，必须匹配其某个 `embedding` 模型。 |
| `dimensions` | `int` | 向量宽度；决定 `vec_chunks` 表。 |
| `default_chunk_size` | `int` | scope 未覆盖时的默认 chunk 大小。 |
| `default_chunk_overlap` | `int` | 默认 chunk 重叠。 |
| `updated_at` | `datetime` | 最后一次写入。 |

`provider`（旧的协议名枚举）、`base_url` 与 `credential_ref` 已从行里和 wire 上**消失**，
更新请求也不再携带 `secret_value`：key 属于连接，embedding 设置不再铸造 `embedding/key`
vault 条目。

`is_active()` 是 `enabled and connection and model`。未命名连接的配置不生效，因此检索退化为
keyword/grep，与未配置的安装完全一致。

解析把连接的 `protocol` 映射到 embedding 客户端——`openai` → openai 兼容，`ollama` → ollama，
`unknown` → 按 openai 兼容处理（未分类的网关几乎总是它）；`anthropic` 不提供任何 embedding
API，会被拒绝。连接的 `base_url` 与 `credential_ref` 原样使用。

以下情形在选择时以 **HTTP 422**（`CONFIG_INVALID`，与应用里其他配置拒绝同一个状态码）拒绝：命名了不存在的连接、协议不提供 embedding 的连接、
做了策展但其中没有 modality 为 `embedding` 的条目的连接，或该连接策展里无一匹配的模型。
完全不做策展的连接会被接受（空 = 不限制），并按用户填写的模型 id 取信。

**迁移：** 一条 Alembic 修订改写这条单例行——已有配置按 `base_url` 匹配到对应连接，匹配不上
再按 `credential_ref` 匹配；两者都匹配不上时，该行保留它的维度与 chunk 默认值，但留空
connection 且 `enabled = 0`，而不是凭空造一条连接。一次性完成：旧列在同一条修订里删除，
不留任何 load-time 垫片去读它们。

### `MemoryFact` (`domain/memory/fact.py`)

frozen dataclass；一个每条事实 markdown 文件（frontmatter + 正文）的内存视图。

| 字段                | 类型                      | 说明                                                                       |
| ------------------- | ------------------------- | -------------------------------------------------------------------------- |
| `id`                | `str`                     | 文档 id（ULID）；也是 `<fact-slug>.md` 文件名的基础。                      |
| `title`             | `str`                     | frontmatter `title`（短标题；旧 `name` key 仍兼容解析）。                |
| `description`       | `str`                     | frontmatter `description`（一行摘要）。                                   |
| `body`              | `str`                     | markdown 正文 = 事实文本。                                                 |
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
    project_id: str       # ULID; sentinel for GLOBAL
    store_dir: Path       # ~/.coffer/memory/global | projects/<ulid>
```

### `MemoryHit`（`domain/knowledge/retrieval.py`，共享）

frozen dataclass；recall 结果。

| 字段     | 类型       | 说明                                                    |
| -------- | ---------- | ------------------------------------------------------- |
| `id`     | `str`      | 事实（document）id。                                    |
| `text`   | `str`      | 事实正文 / 命中的 passage。                             |
| `score`  | `float`    | 逐 store 的相关性分数（保留在线上契约里；见下文 RRF）。 |
| `source` | `str`      | 来源事实文件的 `<scope>:<fact file path>`。             |
| `time`   | `datetime` | 事实的 `updated_at`。                                   |

跨 store 的 recall 用**倒数排名融合**（reciprocal rank fusion，k=60）合并逐 store 的命中列表：不同 store/模式的原始分数不可比（翻转后的 bm25 无上界、vector ≤ 1、grep 是平坦分数），所以 RRF 按逐 store 的名次排序 —— 每条命中保留原始分数，只有合并后的**顺序**来自融合。`grep` recall 是真实服务的：ripgrep 扫该 store 的事实文件（对 FTS5 无法分词的内容必不可少，如 CJK）。store 名会被校验（`global` | `project-<26 字符 ULID>`）：形状合法的名字会惰性 provision 对应 store；其余一律 404。

### 端口

检索与 KB 面**共享**。值对象（`StoreRef`、`Passage`、`GrepHit`、`GrepResult`、`MemoryHit`、`SearchResult`、`RetrievalMode`）在 `domain/knowledge/retrieval.py`；协议（`KnowledgeIndex`、`GrepPort`、`RetrievalPort`）在 `domain/knowledge/index.py`。具体门面是 `KnowledgeRetrieval`（`application/knowledge/retrieval.py`）：它组合 chunk 索引（`infrastructure/knowledge/sqlite_index.py` + `vec_index.py`）、ripgrep 包装器（`grep.py`）与 embedder 客户端（`embeddings.py`），并持有 keyword↔vector 的决策（包括带标注的 vector→keyword 回退）—— 两个面都不重复这段逻辑。读时惰性 reindex 的对账由 memory 侧的 `MemoryReconciler`（`application/memory/sync.py`）驱动单一 re-index 例程（`application/knowledge/reindex.py`）完成。

agent 只通过 MCP 网关的六个工具读写记忆 —— `coffer__search`、`coffer__grep`、`coffer__read`、`coffer__list`、`coffer__write`、`coffer__delete`（FR-015）。`coffer__set_handoff` 与 `coffer__resume` 随交接 lane 一起退役。Coffer 从不改动 agent 的原生记忆文件（原生投影已移除 —— 见 Memory via MCP）。

### Domain 错误（规范类在 `domain/errors.py`，经 `domain/knowledge/errors.py` 再导出）

- `MemoryStoreNotFound` —— code `"MEMORY_STORE_NOT_FOUND"`（HTTP 404）；store 名形状非法时抛出（除 `global` / `project-<26 字符 ULID>` 之外的任何名字）。
- `MemoryNotFound` —— code `"MEMORY_NOT_FOUND"`。
- `MemoryRejected` —— code `"MEMORY_REJECTED"`；reason：`"empty"`、`"too_long"`。
- `ScopeUnresolved` —— code `"SCOPE_UNRESOLVED"`；当 `scope=project` 但 cwd 不在 git 项目里时抛出。
- `EmbeddingUnavailable` —— 对调用方不是错误：`vector` recall 降级为 `keyword` 并在结果里设置 `fallback`（绝不抛给用户）。

## 统一 SQLite schema（Alembic —— 一个重设计 revision）

重设计 revision **删除** `memory_records` 与所有 chroma/LlamaIndex 目录，然后创建与 KB 共享的、以 `documents` 为核心的统一 schema。没有数据迁移。

下面的 schema 与 KB 重设计迁移创建的是**同一份统一 schema**（迁移归 spec knowledge 所有；这里是它的 memory 视角）。重设计 revision **删除** `memory_records` 并创建这些表。

```sql
-- Shared across KB (kind='knowledge_base') and memory (kind='memory').
CREATE TABLE documents (
    id             TEXT NOT NULL,               -- ULID (KB + memory), minted at first write
    kind           TEXT NOT NULL,               -- 'knowledge'（2026-09-10 起只有一个 kind）
    resource_name  TEXT NOT NULL,               -- scope 名：'global' | 'project-<ULID>' | 用户命名的集合
    project_id     TEXT NOT NULL,               -- WORKSPACE_GLOBAL sentinel | project ULID
    path           TEXT NOT NULL,               -- canonical .md path on disk = truth
    title          TEXT NOT NULL,               -- memory: frontmatter `title`
    description    TEXT,                         -- memory: frontmatter `description`
    metadata       TEXT NOT NULL DEFAULT '{}',   -- JSON; memory: {actor, origin_session_id}
    content_sha256 TEXT NOT NULL,               -- for lazy-reindex delta detection
    source_mode    TEXT NOT NULL DEFAULT 'native', -- memory: 'native'
    lane           TEXT NOT NULL DEFAULT 'docs', -- 'notes'（谁写下的）| 'docs'（上传的文档）；迁移 0053 加入；取值由 0056 改名为 notes/docs（FR-073/FR-076）
    created_at     TIMESTAMP NOT NULL,
    updated_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (kind, resource_name, id)        -- composite (memory ULIDs are globally unique too)
);
CREATE INDEX idx_documents_kind_res_time ON documents(kind, resource_name, updated_at DESC);
CREATE INDEX idx_documents_project ON documents(project_id);

CREATE TABLE chunks (
    id           TEXT PRIMARY KEY,              -- '<store-scope>:<doc-id>:<position>'
    -- store-scope = 12-hex digest of (kind, resource_name); keeps ids unique across stores
    document_id  TEXT NOT NULL,                 -- app-level cascade (not a FK; KB+memory share the table)
    kind         TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    position     INTEGER NOT NULL               -- memory: per-passage chunks (1 for a short note; N for a multi-section topic doc)
);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- FTS5 keyword index; the chunk text lives once inside the FTS index (not
-- duplicated into a base table), with chunk_id mapping a hit back to its row.
CREATE VIRTUAL TABLE documents_fts USING fts5(
    text, resource_name UNINDEXED, chunk_id UNINDEXED, tokenize='trigram'  -- CJK-capable (migration 0033)
);

-- sqlite-vec virtual table (only when a vector mode is enabled); created lazily
-- per store at the configured width.
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY,                  -- bare '<doc-id>:<position>' (the table itself is per-store)
    embedding FLOAT[<dim>]
);
```

document 删除时的级联是**应用层的**（索引的 `delete_chunks` + 仓储的 `delete_document`/`delete_resource`），不是 SQL 外键，因为 `documents` 表由两个面共享。

memory 面的 `documents.metadata` 经 Pydantic 校验为 `{actor, origin_session_id}`。按工程惯例，metadata JSON 用 `model_dump(mode="json")` 构造，使 `datetime`/`AnyUrl` 值能序列化进 SQLite。

### 两 lane 迁移（FR-076）

一条 Alembic revision（`0056`）就地改写判别值的两个取值 —— 这是取值改名，不是 schema
变更，所以写成两条 `UPDATE` 而不是重建表，列的 server default 随之一起改：

| `documents.lane` 之前 | 之后    |
| --------------------- | ------- |
| `knowledge`           | `notes` |
| `inbox`               | `docs`  |

被退役的那几条 lane（`rules/`、`handoff/`、`superseded/`、整合日志与
`knowledge/INDEX.md`）没有行要清 —— 它们本来就从不进 recall 索引。它们的文件由迁移
的落盘那一半处理：daemon 启动时跑的一次性、幂等、尽力而为的 sweep（形状照抄同侧的
worktree 作用域合并），把两条内容 lane 搬过去，其余删掉。

两半刻意彼此独立。revision 跑完的那一刻，行里的 `path` 仍指向**旧**目录，这无害：
落盘 sweep 之后的 lazy reindex-on-read 会按磁盘上真实存在的文件重新推导每条路径。
若把这条 revision 锚在存储的 path 上，反而会让它依赖「daemon 是否先跑到落盘那一趟」。

**不留任何 load-time 兼容垫片。** 旧的 lane 字符串在库里被改干净，读它们的每一处
分支在同一次改动里删除：运行时没有任何东西再把 `knowledge`→`notes`、
`inbox`→`docs` 做读时映射；没跑过这条迁移的库，就是代码已经不认识的库。

### Store 展示侧表

两张以 `store_name` 为主键的小侧表保存 memory store 的**展示元数据**（不属于规范的 `documents` 基底；二者互为镜像）：

```sql
CREATE TABLE memory_store_project_roots (
    store_name   TEXT PRIMARY KEY,   -- 例如 'project-<ULID>'
    project_root TEXT NOT NULL       -- provision 时记录的来源 git-root（FR-017a）
);
CREATE TABLE memory_store_labels (
    store_name TEXT PRIMARY KEY,     -- 例如 'project-<ULID>' 或 'global'
    label      TEXT NOT NULL         -- 用户设置的显示名（FR-017c）
);
```

渲染 store 的可读身份时，`label` 优先于由 `project_root` 推导的 basename；清除 label 即删除其行，退回 FR-017a 的推导 / 回退名。两张表都不改变 store 名（`project-<ULID>`）或 `project_id`。

**一个仓库一个 store，跨 git worktree。** 项目 ULID = `sha256(git-root 路径)`。linked worktree 有自己的 `.git` *文件*，故 `git_root`（`infrastructure/memory/scope_fs.py`）会沿该指针的 `gitdir`/`commondir` 回溯到**主**仓库 toplevel —— 一个仓库的所有 worktree（含主 checkout）解析为同一个 ULID，即同一个 store。此前"每个 worktree 各自哈希"造成的碎裂 store，在 daemon 启动时由一次性、幂等、只增不删的合并（`application/memory/consolidate.py`）修复：重解析每个 `project_root`，凡 store 名不再等于其根规范 `project-<ULID>` 者，其 lane 文件并入规范 store（同名冲突保留为 `--from-<ulid>` 兄弟文件）后退休（resource + `documents` + label + root 行）。

## 落盘规范布局（真相源）

```
~/.coffer/
└── memory/
    ├── global/                          # project_id = WORKSPACE_GLOBAL_PROJECT_ID (00000000000000000000000000)
    │   ├── notes/                       # agent 或用户写下的内容（coffer__write 落这里）
    │   │   ├── <note>.md                # 每条 note 一个文件 = 真相（frontmatter + 正文）
    │   │   └── .history/<slug>-<ts>.md  # 整理覆盖前的旧版本（隐藏）
    │   ├── docs/<document>.md           # 上传的文档，统一转成 markdown
    │   └── .raw/<document>.<ext>        # 上传的原件（隐藏）
    └── projects/<project-ulid>/         # 每项目一个目录
        ├── notes/
        │   ├── <note>.md
        │   └── .history/<slug>-<ts>.md
        ├── docs/<document>.md
        └── .raw/<document>.<ext>
```

**两条 lane**（FR-002a/FR-048）：`notes/` 是一切由人或 agent 写下的东西 —— agent 的
`coffer__write`、一条 `coffer knowledge remember`、用户用自己编辑器扔进来的文件；
`docs/` 是一切上传进来、统一转成 markdown 的文档。一条 note 就是一条 note，不管它
是刚写下的还是已经被整理过；从 inbox 到主题文档的梯度不再存在，两个都叫 inbox 的
目录也随之消失。

落盘迁移与 schema 迁移（FR-076）同批执行，按明确决定做**破坏性迁移**，不设
`.retired/` 缓冲区：

| 之前                                            | 之后                |
| ----------------------------------------------- | ------------------- |
| `knowledge/inbox/*.md` + `knowledge/*.md`       | 拍平进 `notes/`     |
| `inbox/`                                        | `docs/`             |
| `.raw/`                                         | 不变                |
| `rules/`、`handoff/`、`superseded/`             | **删除**            |
| `consolidation-log.md`、`knowledge/INDEX.md`    | **删除**            |

**没有 `MEMORY.md`**，也没有 `INDEX.md` —— 两个派生投影都已移除。检索不按 lane 切分
（FR-008a）：`search`、`grep` 与 `recall` 一次同时覆盖 `notes/**/*.md` 与
`docs/**/*.md`，写下的 note 与上传的文档只凭相关性竞争。两条 lane 都是真相源，DO 同步。

`.history/` 与 `.raw/` 刻意加点前缀：ripgrep 默认跳过隐藏项，所以 `coffer__grep`
永远不会在正文旁边又返回一个归档旧版或一份上传原件，二者也都不进 recall 索引。
`.history/` **DO 同步** —— 它是可恢复的真相源历史，是无人值守重写之下唯一的
安全网；`.raw/` 则保存 `docs/` 文件转换前逐字节一致的原件。

启动时的 reindex sweep（`run_memory_reindex_sweep`）会把此前"写入磁盘却因该 store
未被检索而未索引"的 lane 内容补索引。

**定期整理**（`application/memory/reorg.py`，内部 LLM —— FR-033/034）是一个有界的
**agentic** 循环：一个 langgraph `create_react_agent`（按 Contract 9a 关在
`infrastructure/llm` 内，经注入的 memory 本地端口触达）驱动四个内部工具作用于
`notes/` —— `list_topics`、`read_topic`、`write_topic`、`supersede_topic`。它合并
重复与重叠的 note、把它们重写成主题文档，并拆分过长的那些。防丢数据的保证是一条
不变式：**没有任何一个字节离开 `notes/` 之前不被归档** —— `write_topic` 覆盖已有
note 前先把旧版本复制到 `.history/<slug>-<ts>.md`，`supersede_topic` 则把该
note 移进去。循环结束后这一趟对账索引，并在 Coffer 的审计日志里记一行；per-scope
的 `consolidation-log.md` 不再有替代物。这四个工具是由 memory 本地可调用对象构造的
**内部 LangChain `StructuredTool`** —— 从不注册到 MCP 网关，也从不面向 agent。note
`.md` 的 frontmatter 是 `{title, description, updated_at}` + 正文。

这一趟由 **`NotesTidyWorker`**（FR-035）驱动，形状完全照抄现有 `RetentionWorker`：
由 app lifespan 启动，开机跑一趟补齐，之后按间隔执行，异常记日志而不打死循环。未
配置内部模型时空转（`no_model`）；没有 note 时空转（`empty`）。同一趟整理也可以手动
触发：详情页的**「整理」**按钮，以及 `coffer knowledge organize`。

`organizer.py` 与 `organizer_prompt.py` 删除：它们的职责是把 `knowledge/inbox/`
排空成主题文档，只剩一条扁平 lane 之后这个梯度不再存在。随之删除的还有 `merge.py`、
`merge_prompt.py`、`merge_routes.py`、`rules_split.py`、`rules_files.py`、
`handoff.py`、`handoff_files.py`、`lane_reads.py`、`lane_deletes.py`、
`lane_routes.py`，以及 `knowledge_lane_cmd.py`（保留的 `organize` 命令除外）。
`consolidate.py` **不属于**整理流程，原样不动 —— 名字容易误会，它是上文那套针对重复
per-project 作用域的一次性启动愈合。

每条 note `.md` 的 frontmatter：

```markdown
---
kind: knowledge
title: deploy-via-make-release
description: This repo deploys via `make release`, never git push --tags directly.
metadata:
  actor: agent
origin_session_id: 01J...
created_at: 2026-06-09T10:11:12+00:00
updated_at: 2026-06-09T10:11:12+00:00
---

This repo deploys via `make release`. Never run `git push --tags` directly; the
release target tags and pushes atomically.
```

`created_at` / `updated_at` 持久化在 frontmatter 里（文件是真相源）；只有解析省略了它们的手写事实文件时，才回退用文件 mtime。

`infrastructure/memory/paths.py` 是唯一构造这些路径的模块。`infrastructure/memory/files.py` 是唯一读写每条记忆 `.md`、扫描两条 lane 找增量的模块。

## 级联与完整性规则

| 动作                                             | 效果                                                                                                                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `coffer__write` / 用户新增                  | 写 `notes/<note-slug>.md` → 以 `lane='notes'` 索引进 `documents`/`chunks`/FTS5/（vec）→ 审计。                                                                   |
| 上传文档                                    | 原件留在 `.raw/` → 写归一化后的 `docs/<document>.md` → 以 `lane='docs'` 索引 → 审计。                                                                            |
| 用户编辑（REST/CLI/外部编辑器）             | 重写 `.md` → 单一 re-index 例程（sha256 变化 → re-chunk/-embed）→ 审计。（直接的外部编辑器编辑在下一次 lazy reindex-on-read 时生效。）MCP 经 `coffer__write(id=…)` 就地改写。 |
| 删除单条（MCP/REST/CLI）                    | 删除 `.md` → 移除 `documents`/`chunks`/FTS5/vec 行 → 审计。`coffer__delete` 对 note 与文档都适用；删除 `docs/` 条目时连同它的 `.raw/` 原件一起删。                |
| 清空一个 scope                              | 删除 `notes/` 与 `docs/` 下每一条（含 `.history/` 与 `.raw/`）→ 移除全部索引行 → 审计。store Resource 保留。                                                      |
| 整理 Tidy（间隔 worker、「整理」按钮或 `coffer knowledge organize`；内部 agentic LLM） | 有界的 langgraph `create_react_agent` 循环，配 list/read/write/supersede 工具作用于 `notes/`：合并重复、把 note 重写成主题文档、拆分过长的。**每次覆盖/合并先把旧版本复制到 `.history/<slug>-<ts>.md`**（绝不硬删除）。随后对账索引并审计 `knowledge_tidied`。未配置内部模型 → no-op（`no_model`）；没有 note → no-op（`empty`）。 |
| 删除 store Resource                         | 移除该 store 的 `documents` 行、`rmtree(store_dir)`、审计。                                                                                                     |
| 检索 / recall                               | **读时惰性 reindex**：扫两条 lane 找增量（按 `content_sha256`）→ `reconcile` → 搜索。                                                                            |
| 修改 embedding 模型                              | 允许 → 下次索引时对 store 重新 embedding（文件是真相）。                                                                                                      |
| 修改 `max_fact_chars`                            | 允许。                                                                                                                                                        |

## 单一 re-index 例程（`application/knowledge/reindex.py`，与 KB 共享）

```
compute content_sha256 of the new markdown
 ├ unchanged → skip (no-op)
 └ changed   → delete old chunks/FTS5/vec rows → re-chunk → (vector) re-embed
              → insert new → update documents row → audit *_UPDATED
```

memory 的所有写路径（写入、update、用户编辑、整理、惰性 reindex 扫描）都汇入这一个例程。

memory 对账器向该例程提供自己的**分块器**（见 FR-032）：共享的 `infrastructure/knowledge/chunking.chunk_markdown`，绑定固定的 memory 分块 size/overlap 常量（不是 per-store 配置），从而把一份整理过的主题文档切成**段落粒度的分块**（标题与块结构感知），使检索返回其最相关的段落。短的单段落 note 仍只切成一块。隐藏的 `.history/` 与 `.raw/` 会被扫描跳过，因此归档旧版永远不会与正文竞争。

当启用 vector 的 store 在 embed 时降级（embedding provider 不可用），该例程只做 keyword 索引并持久化一个**空字符串 `content_sha256`** —— 一个刻意永不匹配的哨兵值，使下一次惰性对账重试 embed，而不是把这条事实当作已是最新。

## 新增审计事件

| 值                 | 何时发出                              |
| ------------------ | ------------------------------------- |
| `"memory_deleted"` | 一次删除（MCP/REST/CLI）成功后        |
| `"memory_cleared"` | 清空一个 scope 后                     |
| `"knowledge_tidied"` | 确实改写了内容的那趟整理之后          |

删除这一对之所以要审计，是因为删除之后什么也不剩。写入、编辑与重建索引则不审计：
它们可恢复，而且结果都落在磁盘上 —— 文件本身就是记录，重跑一遍也不会改变读者需要
靠日志才能还原的任何东西。

整理进审计日志的理由不同。它**无人值守、按定时触发、由 LLM 重写用户和 agent 写下的
文字**，因此审计日志是读者唯一能看到「哪一趟跑过、什么时候、作用在哪个作用域、动了
什么」的地方 —— 过去承载这段叙事的 per-scope `consolidation-log.md` 已被删除，页面
也不再为它单开 tab。什么都没写、也没归档的那一趟，把 notes 原样留在原地，因此什么
也不记 —— 日志记的是「某个东西做了改动」，不是「定时器响了」。找回的路径是 `.history/`；而告诉你该去那里找的，是审计里
的那一行。

### 规则投递 —— 已删除（原 slice 6，FR-049/FR-050/FR-052/FR-055）

slice 6 曾把 rules lane 交付进一个运行中的 agent：Coffer 把一个 `coffer-hook`
SessionStart hook 装进 agent 自己的 hooks 配置，hook 调
`GET /api/v1/agents/{name}/session-context?cwd=<cwd>`，daemon 组装一个 bundle
（项目规则、全局规则、两条内置种子规则、一份仅标题的项目知识索引），由 hook 作为
`additionalContext` 输出。一个 per-agent 的 `disable_native_memory` 开关随行。

**全部已删除。** 随该切片一并删除的有：`coffer-hook` 二进制及其 PyInstaller spec、
`application/agent/hook_service.py`、`domain/agent/hook_install.py`、
`domain/agent/context_injection.py`、`infrastructure/agent/hook_resolver.py`、
原生记忆相关模块、`application/knowledge/rules_bundle.py`（bundle 组装器）、摘要
渲染器、`GET /api/v1/agents/{name}/session-context` 路由、hook-install 三件套，
以及 `contracts/session-context.openapi.yaml`。该切片定义的四个审计事件类型 ——
`agent_hook_installed`、`agent_hook_uninstalled`、`agent_native_memory_disabled`、
`agent_native_memory_restored` —— 已从 `AuditEventType` 移除。

**读的一侧也没有了。** 规则 lane 本身随两 lane 重设计一起删除：`rules/` 不再存在于
磁盘（FR-076 删掉它），`rules_split.py` 与 `rules_files.py` 删除，
`GET /api/v1/knowledge/{scope}/rules` 与 `coffer knowledge rules <scope>` 随之消失。
`application/knowledge/session_context.py` 只剩写后的 `notify_change` 钩子。规则如今
就是一条 note：像别的内容一样写进 `notes/`，由检索找到。

## Lane 读端点（FR-053/FR-054）

详情页把一个作用域呈现为**两个 tab：文档与 Notes**（FR-053），树上方一个按文件名
过滤的输入框 —— 不发检索请求，也没有第三个 tab。服务端检索留在它该在的地方：agent
走 `coffer__search`，命令行走 `coffer knowledge recall`。

两个 tab 都走留下来的 lane 读端点（FR-054），**按作用域名寻址**（而非 cwd）：它们是
对**磁盘 lane 文件的薄读投影**，不调 LLM（经解析出的作用域取 `store_dir`，经 lane
路径助手 + infra 读取器在请求线程外读取）。空作用域返回**空列表加 HTTP 200** ——
绝非 404。

| Method + path                            | 返回              | lane 来源                                    |
| ---------------------------------------- | ----------------- | -------------------------------------------- |
| `GET /api/v1/knowledge/{name}/entries`   | `EntryListOut`    | `notes/*.md` —— Notes tab（`lane='notes'`）。 |
| `GET /api/v1/knowledge/{name}/documents` | `DocumentListOut` | `docs/*.md` —— 文档 tab（`lane='docs'`）。    |

handoff 与 consolidation-log 端点随它们的 lane 一并**删除**，`HandoffOut`、
`HandoffSceneOut`、`ConsolidationLogOut` 同理；`lane_reads.py`、`lane_deletes.py`、
`lane_routes.py` 一起删除。留下的两个读端点都不暴露 `.history/` 或 `.raw/` ——
隐藏目录是整理的归档与上传的原件，不是页面内容。

两个读 DTO 都携带文件的磁盘真相（绝对 `.md` `path` + 所在 `folder_path`），使每个 tab
都能提供 FR-021 的在外部编辑器打开 / 显示 / 复制路径能力。它们的 schema 落在后端
拥有的 OpenAPI 契约里；spec/data-model 侧只记录上面的形状。

## 线上契约（REST）

位于 `contracts/api.openapi.yaml`。路由在 `/api/v1/memory_stores` 下（list/get/metrics；note 的 add/list/get/edit/delete/clear；文档的上传/列出/读取/删除；search/grep/recall；作为手动整理入口的 `organize`）。handoff、rules、consolidation-log 与 merge 路由随各自的功能一并删除。写入端点（add/edit/delete/clear）保留 —— 它们是 agent（经 MCP）与 CLI 写 note 的途径；Web UI 只在上传文档或跑一趟整理时写入，从不在应用内编辑 note 正文。读 DTO 携带磁盘真相：`FactOut` 带 note 的绝对 `.md` `path` 及其所在文件夹的 `folder_path`，`MemoryStoreOut` 带 store 的绝对 `store_dir`，使视图能提供「在外部编辑器打开 / 显示」。kind 无关的 `/api/v1/resources/...` 对 memory store 继续可用。全应用统一错误包络：`{ "error": { "code", "message", "details" } }`。

不再有第二份 agent 作用域契约：`contracts/session-context.openapi.yaml` 已随它描述的 `GET …/session-context` 路由一起删除（见上文「规则投递 —— 已删除」）。
