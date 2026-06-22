# Data Model —— 007 Memory（跨 agent 共享记忆）

> English: [data-model.md](./data-model.md)

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

embedding 模型 **可变** —— 改它会重嵌整个 store（文件是真相）。没有不可变锁。

与 spec 006 的形状差异是刻意的：007 把 embedding 字段保持**扁平**，让 memory 表单保持轻薄；006 则把它们嵌套在一个 `EmbeddingConfig` 对象里。自全局 embedding 重设计起，扁平字段已是遗留字段——为兼容性在 wire 上继续接受但被忽略；索引与 recall 都解析**全局** embedding 配置。同理，007 recall 响应里的 `fallback` 是**布尔值** —— recall 跨多个 store，单一的回退模式字符串没有良定义；而 006 的单 store 搜索报告一个可空的模式枚举（`fallback: "keyword" | null`）。

### `MemoryFact` (`domain/memory/fact.py`)

frozen dataclass；一个每条事实 markdown 文件（frontmatter + 正文）的内存视图。

| 字段                | 类型                      | 说明                                                                       |
| ------------------- | ------------------------- | -------------------------------------------------------------------------- |
| `id`                | `str`                     | 文档 id（ULID）；也是 `<fact-slug>.md` 文件名的基础。                      |
| `name`              | `str`                     | frontmatter `name`（短标题）。                                            |
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
    kind           TEXT NOT NULL,               -- 'knowledge_base' | 'memory'
    resource_name  TEXT NOT NULL,               -- store name (memory: scope store)
    project_id     TEXT NOT NULL,               -- WORKSPACE_GLOBAL sentinel | project ULID
    path           TEXT NOT NULL,               -- canonical .md path on disk = truth
    title          TEXT NOT NULL,               -- memory: frontmatter `name`
    description    TEXT,                         -- memory: frontmatter `description`
    metadata       TEXT NOT NULL DEFAULT '{}',   -- JSON; memory: {actor, origin_session_id}
    content_sha256 TEXT NOT NULL,               -- for lazy-reindex delta detection
    source_mode    TEXT NOT NULL DEFAULT 'native', -- memory: 'native'
    locked         BOOLEAN NOT NULL DEFAULT 0,  -- KB co-management lock (ADR-028); memory ignores it
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
    │   └── rules/rules.md             # 过程性 lane（store 根目录；在 recall 之外；session-start 注入；DO 同步）
    └── projects/<project-ulid>/       # 每项目一个目录
        ├── knowledge/
        │   ├── inbox/<item>.md
        │   ├── <topic>.md
        │   └── INDEX.md
        ├── consolidation-log.md
        ├── superseded/<slug>-<ts>.md
        ├── rules/rules.md
        └── journal/     <YYYY-MM>.md     # episodic, append-only, time-partitioned; synced AND indexed for recall (FR-043)
```

**没有 `MEMORY.md`** —— 此前的派生投影已移除。`recall` glob `knowledge/**/*.md`（排除 `INDEX.md`），所以 organizer 写入主题文档后会被透明拾取，手写的主题文档也会被立即发现。`INDEX.md` 与 store 根目录的 `consolidation-log.md` 是**派生/机器本地**的：排除在 recall 与同步镜像之外（每台机器从已同步的主题文档重新生成 `INDEX.md`；日志按机器各自维护）。主题文档本身是真相源，DO 同步。store 根的 **`superseded/`** tombstone 保存 reorg pass（FR-033/034）退役的旧版本：与 `handoff/` 一样在 `knowledge/` lane 之外，故**排除在 recall 之外**；但与派生文件不同，它**DO 同步** —— 它是可恢复的真相源历史，而非重新生成的派生物。store 根的 **`rules/rules.md`** 是**过程性 lane**（FR-036）：organizer 把规则形态的 inbox 条目分类追加进来（追加，而非主题合并）；它在 `knowledge/` lane 之外，故**排除在 recall 之外**（rules 由 session-start 注入交付 —— 那是之后的切片 —— 而非 `recall`），且作为真相源**DO 同步**（与 `handoff/` 一样）。它经 `GET /memory_stores/{name}/rules` / `coffer memory rules` 只读暴露。store 根的 **`journal/`** 是**情景 lane**(FR-040):与 `rules/`/`handoff/`/`superseded/` 不同,它**参与 recall** —— reconciler 把每个 `journal/<YYYY-MM>.md` 索引为一个记忆文档(像主题文档一样分块),grep 守卫保留 `journal/` 命中,使情景事件可被检索(FR-043)。它仍作为真相源历史 **DO 同步**,且**不**计入 store 的 `fact_count`(该计数只统计 `knowledge/` lane)。

**organizer**（`application/memory/organizer.py`，内部 LLM，仅显式 `organize` 触发）通过每条目一次 one-shot completion 把 `inbox/` 排空进主题文档：取回至多 3 个候选主题文档（不用 LLM）→ 一次 LLM 合并/创建调用 → 写 `knowledge/<slug>.md` → 删除 inbox 条目（仅在写入成功之后）→ 追加一行 changelog。畸形的 LLM 响应会跳过该条目（留在 inbox，绝不损坏文档）。主题文档 `.md` 的 frontmatter 是 `{title, description, updated_at}` + 正文。langchain 的 LLM 调用留在 `infrastructure/chat`（Contract 9）；`application/memory` 经一个 memory 本地的 `LlmCompletionPort` 触达它（克隆 distill 切片；Contract 5e 禁止 import `application.distill`）。

每条事实 `.md` 的 frontmatter：

```markdown
---
name: deploy-via-make-release
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
| 清空一个 scope                              | 删除 `knowledge/` 下每条记忆条目 → 移除全部索引行 → 审计。store Resource 保留。                                                                                  |
| 整理（显式触发；内部 LLM）                  | 逐 inbox 条目：取回 ≤3 个候选主题文档 → 一次 one-shot LLM 合并/创建/**分类** → 若 LLM 标记该条目为 **rule**，追加到 `rules/rules.md`（过程性 lane，FR-036）；否则写 `knowledge/<slug>.md` → 删除 inbox 条目（仅在写入/追加之后）→ 追加 `consolidation-log.md`。随后重新生成 `INDEX.md`、对账索引、审计 `memory_organized`（含 `rules_appended` 计数）。畸形 LLM 输出跳过该条目（留在 inbox）；未配置内部模型 → no-op。 |
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

## 对话记录提炼（Spec 007 扩展）

对话记录提炼是 memory 事实的一个**生产者** —— 它复用现有的 `MemoryFact` 底座（不新增表，不新增资源 kind）。

### 洞察不分类（无 type）

一次 LLM 调用返回一个洞察数组，每条洞察仅携带 `name` / `description` / `body` —— 蒸馏保持“笨”,MUST NOT 为每条洞察分类 `type`（旧的 `InsightType` 词汇 `decision` / `gotcha` / `convention` / `todo` 被废弃 —— FR-045）。每条洞察以 `actor="agent"` 追加到会话所属项目的 **journal** 记忆带（情景），而非带 type 的 `knowledge/` 事实；把复现的 journal 模式固化进 `knowledge`/`rules` 是 organizer 的职责（固化 —— FR-047）。`Lane` 是唯一分类轴（FR-048）；不存在自由格式的 `type`。

### 出处 —— `origin_session_id`

每条提炼出的事实在事实 frontmatter 与 `documents.metadata` 里都携带 `origin_session_id`（对话记录的 session id）。这使自动化来源可审计：用户可查看是哪个 session 产生了某条事实，必要时可删除或修正它。

提炼洞察的事实 frontmatter 示例：

```markdown
---
name: use-make-release-for-tagging
description: Always tag and push via make release; never git push --tags directly.
metadata:
  actor: agent
origin_session_id: 01JXYZ…
created_at: 2026-06-14T08:00:00+00:00
updated_at: 2026-06-14T08:00:00+00:00
---

Always tag and push via `make release`. The Makefile target is atomic — it
tags and pushes in one step. Running `git push --tags` directly bypasses the
release checks and can leave the repo in a half-tagged state.
```

### LLM 调用前必须抹除的不变量

原始记录**绝不落盘**，也不会出现在事实正文里。LLM 调用前：

- 所有 `tool_use` / `tool_result` 块（Claude/Codex）以及非 `text` 的 part —— tool、reasoning、file、step（OpenCode）—— 被丢弃。
- assistant 回复中嵌入的文件内容片段与命令输出被丢弃。
- 常见 secret 模式（API key、token、PEM block）经正则抹除器删除。
- 长片段被截断。

只有抹除后的自然语言文本（用户 + 助手的散文部分）发送给 LLM。只有提炼出的洞察文本写入事实 store。原始记录与抹除中间体均不存储于 `~/.coffer/` 的任何位置。

Coffer 读取 `~/.claude/projects/`、`~/.codex/sessions/` 以及 OpenCode 的存储树（`~/.local/share/opencode/storage/`），但在此流程中**绝不写入它们** —— Spec 004 的只读不变量得到完整保留。Cursor / OpenClaw / Hermes 的记录读取器被推迟（见 spec.md 的 US「distill transcript to memory」）：它们的存储要么临时、要么无文档、要么不带工作目录无法按项目归类。

### 审计

提炼复用现有的 memory 写入路径：每条写入的事实都会触发 `memory_added` 事件，并带上其
`origin_session_id`。不会发出提炼专属的审计事件。

### 对话会话摘要（历史列表视图）

对话**历史**面列出某 agent 的过往会话，供浏览与提炼。摘要是从每个会话 `.jsonl`
解析出的只读投影 —— 不持久化任何内容（Spec 004 只读不变量）：

| 字段               | 来源                                                                                                          |
| ------------------ | ----------------------------------------------------------------------------------------------------------- |
| `session_id`       | Claude Code 的 `sessionId` / Codex 的 `payload.id`；回退到文件路径。                                          |
| `title`            | Claude Code 的 `ai-title`（最新者胜），否则第一条*真实*用户消息（跳过前导/shell/斜杠命令）截断；可为 null。   |
| `project_path`     | Claude Code 顶层 `cwd` / Codex 的 `session_meta.payload.cwd`。                                                |
| `message_count`    | 对话轮次计数 —— Codex 仅计 `response_item` 消息（绝不计重复的 `event_msg` 事件）。                            |
| `started_at`       | 第一个事件时间戳。                                                                                            |
| `last_activity_at` | 最后一个事件时间戳。                                                                                          |
| `source_path`      | 会话 `.jsonl` 的绝对路径（经共享 `FileActions` 驱动在文件管理器中显示）。                                     |

列表端点应用服务端搜索（标题或项目路径）、筛选（精确项目；`started_at` 范围）与排序
（`started_at` / `last_activity_at` / `message_count`，升/降序），以 `limit`/`offset`
分页。读取器保留一份进程内、按 mtime 键控的已解析摘要缓存，使含数千会话的 agent
仅重新解析 mtime 变化的文件。

## 线上契约（REST）

位于 `contracts/api.openapi.yaml`。路由在 `/api/v1/memory_stores` 下（list/get/metrics；事实的 add/list/get/edit/delete/clear；recall）。写入端点（add/edit/delete/clear）保留 —— 它们是 agent（经 MCP）与 CLI 写入事实的途径；桌面/web UI 是只读视图。读 DTO 携带磁盘真相：`FactOut` 带事实的绝对 `.md` `path` 及其所在文件夹的 `folder_path`，`MemoryStoreOut` 带 store 的绝对 `store_dir`，使只读视图能提供「在外部编辑器打开 / 显示」。kind 无关的 `/api/v1/resources/...` 对 memory store 继续可用。全应用统一错误包络：`{ "error": { "code", "message", "details" } }`。
