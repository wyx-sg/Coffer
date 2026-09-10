# Data Model —— 007 Memory（跨 agent 共享记忆）

> English: [data-model.md](./data-model.md)

> **历史文档 —— 2026-09-10。** spec 006（Knowledge Base）与 spec 007（Memory）
> 于当日合并为统一的 **Knowledge Layer（知识层）**。合并后的模型以
> [`spec.md`](./spec.md) 为准 —— 一个 `knowledge` kind、三种 scope、单一存储根
> `~/.coffer/knowledge/<scope>/`、八个 `coffer__*` 工具。本文档记录的是合并之前
> 的设计；凡出现「memory 面」「`memory` kind」`~/.coffer/memory/`
> `/api/v1/memory_stores` 或 `coffer memory …` 之处，请以 `spec.md` 中合并后的
> 对应物为准。目录名 `specs/007-memory/` 同样是历史遗留：它是所有入链与验收审计
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
| `merged_identities`        | `list[str]`                                | 已合并**进**本库的项目 ULID（FR-058，修订 2026-07-10）。系统管理（用户从不设置）；resolve 算出的身份在此列表中、且其自身库已不存在时，落到本库。随资源同步。默认 `[]`。 |

embedding 模型 **可变** —— 改它会重嵌整个 store（文件是真相）。没有不可变锁。

与 spec 006 的形状差异是刻意的：007 把 embedding 字段保持**扁平**，让 memory 表单保持轻薄；006 则把它们嵌套在一个 `EmbeddingConfig` 对象里。自全局 embedding 重设计起，扁平字段已是遗留字段——为兼容性在 wire 上继续接受但被忽略；索引与 recall 都解析**全局** embedding 配置。同理，007 recall 响应里的 `fallback` 是**布尔值** —— recall 跨多个 store，单一的回退模式字符串没有良定义；而 006 的单 store 搜索报告一个可空的模式枚举（`fallback: "keyword" | null`）。

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

agent 只通过 MCP 网关工具（`coffer__recall`/`remember`/`list_memory`）读写记忆；事实编辑/删除是用户面（REST/CLI/外部编辑器），不是 MCP 工具。Coffer 从不改动 agent 的原生记忆文件（原生投影已移除 —— 见 ADR-026）。

### Domain 错误（规范类在 `domain/errors.py`，经 `domain/knowledge/errors.py` 再导出）

- `MemoryStoreNotFound` —— code `"MEMORY_STORE_NOT_FOUND"`（HTTP 404）；store 名形状非法时抛出（除 `global` / `project-<26 字符 ULID>` 之外的任何名字）。
- `MemoryNotFound` —— code `"MEMORY_NOT_FOUND"`。
- `MemoryRejected` —— code `"MEMORY_REJECTED"`；reason：`"empty"`、`"too_long"`。
- `ScopeUnresolved` —— code `"SCOPE_UNRESOLVED"`；当 `scope=project` 但 cwd 不在 git 项目里时抛出。
- `EmbeddingUnavailable` —— 对调用方不是错误：`vector` recall 降级为 `keyword` 并在结果里设置 `fallback`（绝不抛给用户）。

## 统一 SQLite schema（Alembic —— 一个重设计 revision）

重设计 revision **删除** `memory_records` 与所有 chroma/LlamaIndex 目录，然后创建与 KB 共享的、以 `documents` 为核心的统一 schema。没有数据迁移。

下面的 schema 与 KB 重设计迁移创建的是**同一份统一 schema**（迁移归 spec 006 所有；这里是它的 memory 视角）。重设计 revision **删除** `memory_records` 并创建这些表。

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
    lane           TEXT NOT NULL DEFAULT 'inbox', -- 'knowledge'（写入的条目）| 'inbox'（摄取的文档）；迁移 0052
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
    position     INTEGER NOT NULL               -- memory: per-passage chunks (1 for a short inbox fact; N for a multi-section topic doc)
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

**一个仓库一个 store，跨 git worktree。** 项目 ULID = `sha256(git-root 路径)`。linked worktree 有自己的 `.git` *文件*，故 `git_root`（`infrastructure/memory/scope_fs.py`）会沿该指针的 `gitdir`/`commondir` 回溯到**主**仓库 toplevel —— 一个仓库的所有 worktree（含主 checkout）解析为同一个 ULID，即同一个 store。分支解析（`git_branch`）仍按 worktree 各自计算（handoff 按分支 key）。此前"每个 worktree 各自哈希"造成的碎裂 store，在 daemon 启动时由一次性、幂等、只增不删的合并（`application/memory/consolidate.py`）修复：重解析每个 `project_root`，凡 store 名不再等于其根规范 `project-<ULID>` 者，其 lane 文件并入规范 store（同名冲突保留为 `--from-<ulid>` 兄弟文件）后退休（resource + `documents` + label + root 行）。

## 落盘规范布局（真相源）

```
~/.coffer/
└── memory/
    ├── global/                        # project_id = WORKSPACE_GLOBAL_PROJECT_ID (00000000000000000000000000)
    │   ├── knowledge/                 # 语义 lane（recall 在此搜索）
    │   │   ├── inbox/<item>.md        # per-item file = truth（frontmatter + body），新记住的条目
    │   │   ├── <topic>.md             # 经整理的主题文档（由整合 organizer 写入）
    │   │   └── INDEX.md               # 人类审阅入口（由 organizer 重新生成）
    │   ├── consolidation-log.md       # 只追加 changelog（store 根目录；机器本地，在 recall 之外）
    │   ├── superseded/<slug>-<ts>.md  # reorg tombstone（store 根目录；在 recall 之外；可恢复；DO 同步）
    │   └── rules/*.md                 # 过程性 lane：rules.md + 拆分后的 per-topic <slug>.md（store 根目录；在 recall 之外；按需读取；DO 同步）
    └── projects/<project-ulid>/       # 每项目一个目录
        ├── knowledge/
        │   ├── inbox/<item>.md
        │   ├── <topic>.md
        │   └── INDEX.md
        ├── consolidation-log.md
        ├── superseded/<slug>-<ts>.md
        └── rules/*.md                    # rules.md + per-topic <slug>.md（超阈值后自主拆分）
```

**没有 `MEMORY.md`** —— 此前的派生投影已移除。`recall` glob `knowledge/**/*.md`（排除 `INDEX.md`），所以 organizer 写入主题文档后会被透明拾取，手写的主题文档也会被立即发现。`INDEX.md` 与 store 根目录的 `consolidation-log.md` 是**派生/机器本地**的：排除在 recall 与同步镜像之外（每台机器从已同步的主题文档重新生成 `INDEX.md`；日志按机器各自维护）。主题文档本身是真相源，DO 同步。store 根的 **`superseded/`** tombstone 保存 reorg pass（FR-033/034）退役的旧版本：与 `handoff/` 一样在 `knowledge/` lane 之外，故**排除在 recall 之外**；但与派生文件不同，它**DO 同步** —— 它是可恢复的真相源历史，而非重新生成的派生物。store 根的 **`rules/`** 是**过程性 lane**（FR-036）：organizer 把规则形态的 inbox 条目分类追加进 `rules/rules.md`（追加，而非主题合并）；任一 `rules/*.md` 超过阈值后，reorg pass 按主题（one-shot LLM）把它拆分为 per-topic `rules/<slug>.md`（amendment 2026-06-22），读取面拼接全部 `rules/*.md`。它在 `knowledge/` lane 之外，故**排除在 recall 之外**（规则是常驻指令，不是检索命中），且作为真相源**DO 同步**（与 `handoff/` 一样）。它**只按需读取** —— 曾经把它推送进 agent 的 session-start 注入已被移除（spec FR-049/FR-050/FR-052/FR-055 删除）。它经 `GET /memory_stores/{name}/rules` / `coffer memory rules` 只读暴露。启动时的 reindex sweep（`run_memory_reindex_sweep`）会把此前"写入磁盘却因 store 未被 recall 而未索引"的 `knowledge/` lane 内容补索引。

**organizer**（`application/memory/organizer.py`，内部 LLM，仅显式 `organize` 触发）通过每条目一次 one-shot completion 把 `inbox/` 排空进主题文档：取回至多 3 个候选主题文档（不用 LLM）→ 一次 LLM 合并/创建调用 → 写 `knowledge/<slug>.md` → 删除 inbox 条目（仅在写入成功之后）→ 追加一行 changelog。畸形的 LLM 响应会跳过该条目（留在 inbox，绝不损坏文档）。主题文档 `.md` 的 frontmatter 是 `{title, description, updated_at}` + 正文。langchain 的 LLM 调用留在 `infrastructure/chat`（Contract 9）；`application/memory` 经一个 memory 本地的 `LlmCompletionPort` 触达它。

每条事实 `.md` 的 frontmatter：

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

`infrastructure/memory/paths.py` 是唯一构造这些路径的模块。`infrastructure/memory/files.py` 是唯一读写每条记忆 `.md`、扫描 `knowledge/` lane 找增量的模块。

## 级联与完整性规则

| 动作                                             | 效果                                                                                                                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `remember` / 用户新增                       | 写 `knowledge/inbox/<item-slug>.md` → 索引进 `documents`/`chunks`/FTS5/（vec）→ 审计。                                                                          |
| 用户编辑（REST/CLI/外部编辑器）             | 重写 `.md` → 单一 re-index 例程（sha256 变化 → re-chunk/-embed）→ 审计。（直接的外部编辑器编辑在下一次 lazy reindex-on-read 时生效。）MCP 无编辑工具 —— 仅 REST/CLI。 |
| 用户删除（REST/CLI）                        | 删除 `.md` → 移除 `documents`/`chunks`/FTS5/vec 行 → 审计。MCP 无删除工具 —— 仅 REST/CLI。                                                                       |
| Lane 删除（REST）                           | `DELETE /memory_stores/{name}/{handoff/<branch>,rules,consolidation-log}` → 删除 lane 文件（这些 lane 均不进 recall 索引）→ 向 `consolidation-log.md` 追加一行人类可读记录（删除 changelog 自身时除外）→ 审计 `memory_deleted`。文件不存在 → 404（与 fact-delete 一致）。 |
| 清空一个 scope                              | 删除 `knowledge/` 下每条记忆条目 → 移除全部索引行 → 审计。store Resource 保留。                                                                                  |
| 整理（显式触发；内部 LLM）                  | 逐 inbox 条目：取回 ≤3 个候选主题文档 → 一次 one-shot LLM 合并/创建/**分类** → 若 LLM 标记该条目为 **rule**，追加到 `rules/rules.md`（过程性 lane，FR-036）；否则写 `knowledge/<slug>.md` → 删除 inbox 条目（仅在写入/追加之后）→ 追加 `consolidation-log.md`。随后重新生成 `INDEX.md`、对账索引、**把任一超阈值 `rules/*.md` 经 one-shot LLM 分类拆分为 per-topic `rules/<slug>.md`**（amendment 2026-06-22）、审计 `memory_organized`（含 `rules_appended` 计数）。畸形 LLM 输出跳过该条目（留在 inbox）；未配置内部模型 → no-op。 |
| 重组 reorg（显式触发；内部 agentic LLM）    | 有界的 langgraph `create_react_agent` 循环，配 list/read/write/supersede 工具作用于主题文档：合并重复 + 拆分过长文档。**每次覆盖/supersede 先把旧版本归档到 `superseded/<slug>-<ts>.md`**（绝不硬删除）。随后重新生成 `INDEX.md`、对账、审计 `memory_reorganized`。未配置内部模型 → no-op（`no_model`）；无主题文档 → no-op（`empty`）。 |
| 自动整理 auto-organize（静默触发；opt-in，默认关闭） | memory 写入通知钩子（重新）武装单个**去抖**定时器；store 静默达延迟后，对发生变化的 store 作为**后台任务**运行上面的「整理 Organize」—— 一个 session-end 代理（FR-035）。非阻塞：daemon 关停时取消（未触发的 inbox 原样留给之后的 pass；不丢数据）。失败被吞掉并记日志。无新增 REST/CLI 面。 |
| 删除 store Resource                         | 移除该 store 的 `documents` 行、`rmtree(store_dir)`、审计。                                                                                                     |
| Recall                                      | **读时惰性 reindex**：扫 `knowledge/` lane 找增量（按 `content_sha256`）→ `reconcile` → 搜索。                                                                   |
| 修改 embedding 模型                              | 允许 → 下次索引时对 store 重新 embedding（文件是真相）。                                                                                                      |
| 修改 `max_fact_chars`                            | 允许。                                                                                                                                                        |

## 单一 re-index 例程（`application/knowledge/reindex.py`，与 KB 共享）

```
compute content_sha256 of the new markdown
 ├ unchanged → skip (no-op)
 └ changed   → delete old chunks/FTS5/vec rows → re-chunk → (vector) re-embed
              → insert new → update documents row → audit *_UPDATED
```

memory 的所有写路径（remember、update、用户编辑、惰性 reindex 扫描）都汇入这一个例程。

memory 对账器向该例程提供自己的**分块器**（见 FR-032）：共享的 `infrastructure/knowledge/chunking.chunk_markdown`，绑定固定的 memory 分块 size/overlap 常量（不是 per-store 配置），从而把一份已整理的主题文档切成**段落粒度的分块**（标题与块结构感知），使 `recall` 返回其最相关的段落。短的单段落事实仍只切成一块，因此 inbox 与主题文档之分、以及 `INDEX.md`/`handoff/` 的 recall 隔离都不受影响。

当启用 vector 的 store 在 embed 时降级（embedding provider 不可用），该例程只做 keyword 索引并持久化一个**空字符串 `content_sha256`** —— 一个刻意永不匹配的哨兵值，使下一次惰性对账重试 embed，而不是把这条事实当作已是最新。

## 新增审计事件

| 值                 | 何时发出                  |
| ------------------ | ------------------------- |
| `"memory_added"`   | `remember`/用户新增成功后 |
| `"memory_updated"` | 用户编辑（REST/CLI）成功后 |
| `"memory_deleted"` | 用户删除（REST/CLI）成功后 |
| `"memory_cleared"` | 清空一个 scope 后         |

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

留下的只有读的一侧。`application/knowledge/session_context.py` 名字未变，但只剩读侧助手
—— `get_rules(scope)`（拼接全部 `rules/*.md`）以及写后的 `notify_change` 钩子 —— 供
`GET /api/v1/knowledge/{scope}/rules` 与 `coffer knowledge rules <scope>` 使用。
没有任何东西再把这条 lane 推进会话；想要它的 agent 必须自己开口。这笔取舍为何被
接受，见 spec 的「投递 —— 已删除」。

## Lane 读端点（slice 7 —— FR-053/FR-054）

memory store 详情页把 store 呈现为三个 lane 区块（Knowledge / Rules /
Handoff）外加一个整合 changelog 视图（FR-053）。Knowledge 复用既有事实读面
（`GET …/facts`），也是 `recall` 操作的对象；Rules 已有 `GET …/{name}/rules`
（FR-036）。slice 7 再加两个**只读** lane 端点（FR-054），每个**按 store 名寻址**
（而非 cwd）—— 它们是对**磁盘 lane 文件的薄读投影**，不调 LLM，镜像 `MemoryService`
上的 `get_rules`/metrics（经解析出的作用域取 `store_dir`，经 lane 路径助手 + infra
读取器在请求线程外读取）。空 store 返回**空列表 / `null` 加 HTTP 200** —— 绝非 404。

| Method + path                                        | 返回                  | lane 来源                                                                 |
| ---------------------------------------------------- | --------------------- | ------------------------------------------------------------------------- |
| `GET /api/v1/memory_stores/{name}/handoff`           | `HandoffOut`          | `handoff/<branch-slug>.md` 现场，每分支一个（连续性；FR-023）。           |
| `GET /api/v1/memory_stores/{name}/consolidation-log` | `ConsolidationLogOut` | store 根的 `consolidation-log.md`；不存在时 `text = null`（FR-031）。     |

### 响应实体（只读投影）

它们是**只读 DTO** —— 不是新的领域实体或表。每个都携带 lane 文件的磁盘真相（绝对
`.md` `path` + 所在 `folder_path`），使只读 lane 视图能提供 FR-021 的在外部编辑器打开
/ 显示 / 复制路径能力，与 `FactOut` 完全一致。

**`HandoffSceneOut`** —— 一个按分支的 handoff 现场。

| 字段         | 类型              | 说明                                              |
| ------------ | ----------------- | ------------------------------------------------- |
| `branch`     | `str`             | 现场所属分支（frontmatter `branch`）。            |
| `text`       | `str`             | 现场的自由 markdown 正文。                        |
| `updated_at` | `str`（date-time）| 现场最后写入时间（frontmatter `updated_at`）。    |
| `path`       | `str`             | handoff 现场文件的绝对磁盘 `.md` 路径。           |
| `folder_path`| `str`             | 所在 `handoff/` 文件夹的绝对路径。                |

**`HandoffOut`**

| 字段     | 类型                | 说明                                                |
| -------- | ------------------- | --------------------------------------------------- |
| `scenes` | `HandoffSceneOut[]` | 每分支一个现场；无 handoff 的 store 为空列表。       |

**`ConsolidationLogOut`** —— organizer 的追加式整合 changelog。

| 字段          | 类型          | 说明                                                       |
| ------------- | ------------- | ---------------------------------------------------------- |
| `text`        | `str \| None` | `consolidation-log.md` 正文；文件不存在时为 `null`。       |
| `path`        | `str`         | `consolidation-log.md` 的绝对磁盘路径（store 根）。        |
| `folder_path` | `str`         | 所在 store 目录的绝对路径。                                |

这些读端点（及其 schema）落在后端拥有的 OpenAPI 契约里；spec/data-model 侧只记录上面的形状。

## 线上契约（REST）

位于 `contracts/api.openapi.yaml`。路由在 `/api/v1/memory_stores` 下（list/get/metrics；事实的 add/list/get/edit/delete/clear；recall；FR-054 的 slice-7 handoff/consolidation-log lane 读取）。写入端点（add/edit/delete/clear）保留 —— 它们是 agent（经 MCP）与 CLI 写入事实的途径；Web UI 是只读视图。读 DTO 携带磁盘真相：`FactOut` 带事实的绝对 `.md` `path` 及其所在文件夹的 `folder_path`，`MemoryStoreOut` 带 store 的绝对 `store_dir`，使只读视图能提供「在外部编辑器打开 / 显示」。kind 无关的 `/api/v1/resources/...` 对 memory store 继续可用。全应用统一错误包络：`{ "error": { "code", "message", "details" } }`。

不再有第二份 agent 作用域契约：`contracts/session-context.openapi.yaml` 已随它描述的 `GET …/session-context` 路由一起删除（见上文「规则投递 —— 已删除」）。
