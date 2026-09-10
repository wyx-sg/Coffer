# 实现计划：Memory（跨 agent 共享记忆）

> English: [plan.md](./plan.md)

> **历史文档 —— 2026-09-10。** Knowledge Base 与 Memory 两份规范于当日合并为统一的
> **Knowledge Layer（知识层）**。合并后的模型以
> [`spec.md`](./spec.md) 为准 —— 一个 `knowledge` kind、三种 scope、单一存储根
> `~/.coffer/knowledge/<scope>/`、八个 `coffer__*` 工具。本文档记录的是合并之前
> 的设计；凡出现「memory 面」「`memory` kind」`~/.coffer/memory/`
> `/api/v1/memory_stores` 或 `coffer memory …` 之处，请以 `spec.md` 中合并后的
> 对应物为准。目录名 `specs/knowledge/` 同样是历史遗留：它是所有入链与验收审计
> 所依赖的 spec id。

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.zh.md](./spec.zh.md)
**Status**: Accepted (redesign — in development)

---

# 2026-09-11 重新设计 —— 两个 lane

**状态**：设计已确认，尚未开始实现。以下内容取代其后历史计划中的对应部分。

## 为什么改

一个知识作用域在磁盘上有七条 lane，详情页把其中五条并列成同等份量的 tab ——
条目、文档、规则、交接、变更记录。它们是**存储 lane**，不是人认得出的分类，错位
处处可见：

- 有两个目录都叫 inbox。`knowledge/inbox/` 放刚写下的条目，`inbox/` 放导入的
  文档。UI 把前者叫「条目」后者叫「文档」—— 相同的目录名什么也没解释，不同的
  界面名解释错了方向。
- 「条目」tab 把两种不同的东西拍平进同一个列表：agent 刚写下的原始条目，和
  organizer 把它们合并出来的主题文档。
- 规则 lane 的投递通道已在 2026-09-10 删除（FR-049/050/052/055）。规则照写照存，
  但没有任何东西读它。
- 变更记录是 organizer 的审计流水，不是内容 —— 而 organizer 只能从 CLI 触发，
  于是页面展示了一趟它根本没提供入口去跑的整理的副产物。

人真正会区分的只有两类材料：**谁写下的**，和**谁上传的**。

## 磁盘布局

```text
~/.coffer/knowledge/<scope>/
├── notes/       # agent 或用户写下的内容（coffer__write 落这里）
├── docs/        # 上传的文档，统一转成 markdown
├── .raw/        # 上传的原件（隐藏）
└── .history/    # 整理覆盖前的旧版本（隐藏）
```

两条 lane。`knowledge/inbox/` 和它到主题文档的梯度一起消失：一条 note 就是一条
note，不管它是刚写下的还是已经被整理过。

`.history/` 放在作用域根目录、与 `.raw/` 平级，而不是嵌在 `notes/` 里面。嵌进去
的话，lane 扫描、重建索引、以及此后每一个读 `notes/` 的人都得记得跳过它；平级之
后它只是又一个隐藏归档，归在已经管着 `.raw/` 的那条规则底下 —— ripgrep 跳过隐藏
项，所以 `coffer__grep` 永远不会在正文旁边返回原件或被替换掉的旧版本。

## 迁移

按明确要求做破坏性迁移，不设 `.retired/` 缓冲区：

| 现在                                            | 之后                    |
| ----------------------------------------------- | ----------------------- |
| `knowledge/inbox/*.md` + `knowledge/*.md`       | 拍平进 `notes/`         |
| `inbox/`                                        | `docs/`                 |
| `.raw/`                                         | 不变                    |
| `rules/`、`handoff/`、`superseded/`             | **删除**                |
| `consolidation-log.md`、`knowledge/INDEX.md`    | **删除**                |

`documents.kind` 的两个取值由 `knowledge` / `inbox` 改为 `notes` / `docs`，一条
migration 完成。不留 load-time 垫片：数据在库里改干净，兼容分支在同一次改动里
删掉。

## 定期整理

`reorg.py` 已经在做用户想要的事 —— 一个有界的 agentic 循环，合并重复文档、拆分
过长文档 —— 只是目前必须由 CLI/REST 显式触发。保留它，把瞄准点改到 `notes/`。

两趟整理、两个触发入口收敛成一个。`POST /{scope}/organize` 与
`POST /{scope}/reorg` 原本分别指向 organizer 和 reorg；organizer 既然没了，就只剩
一趟，那它也只保留一个名字 —— 路由和 CLI 都叫 `organize`，`/reorg` 删除。

`organizer.py` 与 `organizer_prompt.py` 删除。它们的职责是把 `knowledge/inbox/`
排空成主题文档；只剩一条扁平 lane 之后，这个梯度不再存在。

`NotesTidyTrigger` 取代原来那个按空闲防抖的 auto-organizer，用两条路径武装这趟
整理 —— 因为它们堵的是不同的漏：

- **空闲触发。** 每次写入重新武装同一个合并计时器，安静一段时间之后整理这期间
  变过的作用域。这是既有机制，只是改了瞄准点。
- **定时触发。** 对所有作用域的周期性巡检，照抄同目录下 `RetentionWorker` 的形状
  —— 开机跑一趟补齐，之后每隔几小时一轮，异常记日志但不打死循环。它能捞到空闲
  计时器结构上捞不到的那些：用户在自己编辑器里改的文件、计时器还没到点就重启的
  daemon、以及最近没人写过的作用域。

两条路径调用同一个入口、并且都持有该 store 的写锁，所以巡检和刚触发的空闲计时器
是串行而不是打架。未配置 internal model 时整趟空转。详情页另给一个手动的
**「整理」**按钮。

力度：这一趟可以合并重复、把多条 note 重写成主题文档。任何覆盖或合并之前，先把
旧版本移进 `.history/`，因此无人值守的重写始终可以捞回来。

每趟整理写进 Coffer 已有的审计日志。per-scope 的 `consolidation-log.md` 不再有
替代物 —— 一处日志，页面也不必为它单开一个 tab。

## 对外的面

- **MCP：8 个工具 → 6 个。** `search`、`grep`、`read`、`list`、`write`、`delete`。
  `set_handoff` 与 `resume` 随交接 lane 一起退役。
- **CLI。** 删除 `coffer knowledge rules` / `handoff` / `consolidation-log` /
  `merge`。`organize` 保留，作为整理的手动触发入口。
- **HTTP。** 删除 `lane_routes.py` 与 `merge_routes.py`。

## 页面

**列表页。** 删掉「作用域」列 —— 名称列已经显示 `global`、项目的绝对路径或集合
名，这个徽标只是把同一行已经说过的话再说一遍。「条目」列改名「Notes」。「AI 合并」
入口随 `merge` 一起消失。新增集合对话框去掉向量检索开关：一个作用域带哪种索引是
实现细节，不该在创建时拿去问用户。

**详情页。** 两个 tab：文档、Notes。树上方一个过滤框，输入即按文件名匹配 ——
纯本地，无按钮，不发请求。服务端检索留在它该在的地方：agent 走 `coffer__search`，
命令行走 `coffer knowledge recall`。

header 保留标题、重命名铅笔和项目路径；**「上传」**和**「整理」**是仅有的两个按钮，
设置 / 检查源文件 / 重建索引收进溢出菜单。六个徽标全部删除 —— 分块数、字节数、
Grep、关键词都是内部机制，而条目数与文档数树标题上已经有了。降级文档的警告保留，
且只在真的出现时显示。每条 lane 顶上的说明文案、以及与树标题重复的计数一并删掉。

## 删除清单

| 模块                                                          |   行数 |
| ------------------------------------------------------------- | -----: |
| `organizer.py` + `organizer_prompt.py`（含 deps/ports）       |  ~530 |
| `merge.py` + `merge_prompt.py` + `merge_routes.py` + CLI      |  ~560 |
| `rules_split.py` + `rules_files.py`                           |  ~290 |
| `handoff.py` + `handoff_files.py`                             |  ~190 |
| `lane_reads.py` + `lane_deletes.py` + `lane_routes.py`        |  ~270 |
| `knowledge_lane_cmd.py`（保留的 `organize` 除外）             |  ~100 |
| **后端合计**                                                  | ~1900 |
| 规则 / 交接 / 变更记录三个 lane 组件、`KnowledgeListLane`、合并对话框、检索条 | ~600（前端） |

相对地，只新增一个约 60 行的 worker。

`merge`（FR-056…058）依维护者授权删除。它要愈合的「同一个仓库散在多个
`project-<ULID>` 作用域」这一碎片化，成因是各 worktree 算出不同的 ULID，而这个
根因已经在 worktree 感知的 `git_root` 修复里堵死；残留的碎片由 `consolidate.py`
在每次 daemon 启动时自动愈合。在同一个问题上再留一条需要人操心、还要拖着 LLM
判断与不可复活身份别名的手动路径，是项目不再愿意支付的一层抽象。

## 刻意保留

- **`consolidate.py`。** 名字容易误会，它并不属于整理流程：它是针对重复 per-project
  作用域的一次性启动愈合。原样不动。
- **向量检索。** 去掉创建对话框里的开关，去掉的是一个**提问**，不是能力本身。新建
  集合照旧带 keyword + grep + vector；embedding 模型仍是全装机唯一。
- **`coffer__search`。** UI 只按文件名过滤是 UI 的决定，面向 agent 的检索不受影响。

## 已接受的风险

整理无人值守、按定时触发、由 LLM 重写用户和 agent 写下的文字。`.history/`
是全部的安全网；没有复核环节，落盘前也没有 diff 可供确认。

## 同一次改动要更新的文档

- `spec.md` / `spec.zh.md` —— 删 FR-056…058、规则 lane 相关 FR 与交接相关 FR；
  重写 lane 布局；新增定期整理的 FR。
- `.specify/memory/architecture.md` —— `knowledge` kind 那一行。
- `.specify/memory/roadmap.md` —— 007 那一行。
- `docs/decisions/Files as Truth`、`One Shared Knowledge Store` —— 就地改写，不写新 ADR 去 supersede
  （仓库约定：该目录记录当前生效的设计，git history 是档案）。

---

## Summary

memory 是与 knowledge base（Knowledge Base 规范）共用同一套统一知识底座的 **memory 面**。每个记忆作用域是一个 kind 为 `memory` 的 Resource。事实 = 每条事实一个 markdown 文件（YAML frontmatter + 正文）加一个重新生成的 `MEMORY.md` 索引，放在 `~/.coffer/memory/` 下。**文件是真相源；SQLite（`documents` + FTS5 + sqlite-vec）是可重建的索引。** 有两种作用域：global（sentinel ULID）与 per-project（由 agent 工作目录解析出的项目 ULID）。

写入时不调 LLM —— agent 直接写一条干净的事实。每个 agent **只通过 Coffer MCP 网关读写记忆**（`coffer__recall/remember/list_memory/set_handoff/resume`）；Coffer 保留自己的规范化格式，**不触碰各 agent 的原生记忆文件**（原生投影已移除 —— 见 [Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.zh.md)）。用户经 CLI/REST 写入面做完整 CRUD；Coffer UI 是 **只读** 视图，为每条事实及其文件夹提供「在外部编辑器打开 / 显示」（维护在用户自己的编辑器里完成，经 lazy reindex-on-read 拾取）。

本次重设计 **删除 mem0、chroma、LlamaIndex**，并用统一 `documents` 表取代 `memory_records`。没有数据迁移（分支未发布）。

## Technical Context

| 维度                     | 取值                                                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **语言 / 版本**          | Python 3.12+，TypeScript 5.x                                                                                                                                                          |
| **本规范新增的主要依赖** | 与 KB 共享：`sqlite-vec`（向量索引）、`fastembed`（可选本地 embedding）、`PyYAML`（frontmatter）。云端 embedding 经既有 OpenAI 兼容 provider 抽象。**移除：** `mem0ai`、`chromadb`。  |
| **存储**                 | markdown 事实放在 `~/.coffer/memory/global/` 与 `~/.coffer/memory/projects/<project-ulid>/`；索引行在 `~/.coffer/coffer.db`（`documents`、`chunks`、`documents_fts`、`vec_chunks`）。 |
| **测试**                 | 4 层模型配 acceptance 标记。向量路径用 `FakeEmbeddingProvider`；keyword/grep 不需 embedding。                                                                                         |
| **性能目标**             | SC-003：200 条事实作用域上 keyword recall ≤ 300 ms。                                                                                                                                  |
| **约束**                 | 索引引擎关在 `coffer.infrastructure.knowledge.*` 内（importlinter）；即便向量后端加载失败 daemon 仍能起；`mem0`/`chroma`/`llama_index` 任何地方都不被 import。                        |
| **规模 / 范围**          | 单用户；一个 global store + 每个活跃项目一个 store；事实很短（默认 ≤ 8192 字符）。                                                                                                    |

## Constitution Check

与 KB 相同的分层规则（一套底座）。memory kind 复用共享检索引擎、仓储与 converter；只有 memory 专属的 service（每条事实写入、`MEMORY.md` 重新生成、作用域解析）是 memory 专属。引擎隔离与跨 kind import 禁令对称扩展。`WORKSPACE_GLOBAL_PROJECT_ID` sentinel 复用、不重铸。

## Project Structure

```text
backend/coffer/
├── domain/
│   ├── errors.py                        # 规范错误层级：MemoryStoreNotFound、MemoryNotFound、MemoryRejected、ScopeUnresolved、...
│   ├── knowledge/                       # 共享底座（KB + memory）—— 见 Knowledge Base
│   │   ├── document.py                  # Document 实体（按 kind 区分）
│   │   ├── retrieval.py                 # StoreRef、Passage、GrepHit/GrepResult、MemoryHit、SearchResult、RetrievalMode
│   │   ├── index.py                     # KnowledgeIndex / GrepPort / RetrievalPort 协议
│   │   └── errors.py                    # 底座错误的再导出（规范类在 domain/errors.py）
│   └── memory/
│       ├── config.py                    # MemoryStoreConfig（检索模式、扁平 embedding 字段、max_fact_chars）
│       ├── fact.py                      # MemoryFact（frontmatter + 正文）值对象
│       └── scope.py                     # MemoryScope (GLOBAL | PROJECT) + ResolvedScope
├── application/
│   ├── knowledge/                       # 共享底座 application 层（Knowledge Base）
│   │   ├── retrieval.py                 # KnowledgeRetrieval 门面（keyword/vector + 带标注回退）
│   │   ├── reindex.py                   # 单一幂等 re-index 例程（Reindexer）
│   │   └── locks.py                     # StoreLocks —— 逐 store 写串行化
│   ├── memory/
│   │   ├── kind.py                      # make_memory_kind(...)
│   │   ├── service.py / service_helpers.py  # remember/recall/update/forget/list/clear（知识库 inbox）
│   │   ├── writes.py / queries.py       # 事实写/读路径
│   │   ├── recall.py                    # recall 编排 + 倒数排名融合（RRF）合并
│   │   ├── scope.py                     # ScopeResolver：cwd → git-root → 项目 ULID → store（惰性置备）；store 名校验
│   │   ├── stores.py                    # store 名 ↔ ResolvedScope 辅助
│   │   ├── sync.py                      # MemoryReconciler —— 读时惰性 reindex
│   │   └── builtin_tools.py             # 五个 coffer__* memory MCP 工具
├── infrastructure/
│   ├── knowledge/                       # 共享底座 infra（Knowledge Base）：repository.py、sqlite_index.py、
│   │   …                                # vec_index.py（唯一 sqlite_vec importer）、embeddings.py、grep.py、
│   │                                    # chunking.py、cleaning.py、frontmatter.py、paths.py、converters/
│   └── memory/
│       ├── files.py                     # 每条事实 .md 读写、MEMORY.md 渲染、目录扫描（增量）
│       ├── paths.py                     # ~/.coffer/memory/{global,projects/<ulid>}
│       ├── scope_fs.py                  # 文件系统作用域辅助
│       └── project_root_repo.py         # project-root 持久化（可读的 per-project store 身份，FR-017a）
└── surfaces/
    ├── http/memory/                     # /api/v1/memory_stores/*（facts、recall）
    └── cli/memory_cmd.py                # `coffer memory ...`
```

修改的既有文件：

- `application/mcp/gateway.py` / `gateway_builtin.py` —— 把五个 memory 工具（由 `application/memory/builtin_tools.py` 注册）与 KB 工具一起路由。
- `surfaces/http/app.py` —— `_wire_memory_kind(...)`。
- `surfaces/cli/main.py` —— `app.add_typer(memory_cmd.app, name="memory")`。
- `infrastructure/persistence/migrations/` —— 一个 revision：删除 `memory_records`、删掉 chroma/LlamaIndex 目录、创建统一 schema。
- `backend/pyproject.toml` —— 删除 `mem0ai`/`chromadb`；加共享底座依赖；新 importlinter contract。
- `frontend/src/kinds.ts` —— 注册 `MEMORY_KIND_UI`。

## Frontend

```text
frontend/src/pages/MemoryPage.tsx        # store 表格（自动置备；没有「New store」操作）
frontend/src/kinds/memory/
├── index.tsx                            # MEMORY_KIND_UI
├── MemoryStoreDetailPage.tsx            # 逐 store 详情页（路由 /memory/:name）
├── MemoryFactList.tsx                   # DataTable（name、description、type、actor、updated）
├── MemoryFactViewer.tsx                 # 只读事实渲染 + 在外部编辑器打开 / 显示（文件 + 文件夹）
├── MemoryRecallPanel.tsx                # 带模式选择的 recall 框（默认 keyword）
├── MemoryMetricsHeader.tsx              # 事实条数 + 磁盘字节
├── api.ts / types.ts
└── schema.ts
```

## Tests

```text
backend/tests/
├── unit/memory/
│   ├── test_config_validation.py
│   ├── test_fact_frontmatter_roundtrip.py
│   ├── test_memory_md_regeneration.py        # 幂等，由 frontmatter 派生
│   └── test_scope_resolver.py                # cwd → git-root → ULID；global sentinel
├── integration/memory/
│   ├── test_remember_recall_roundtrip.py     # keyword + vector(fake) + grep
│   ├── test_lazy_reindex_on_read.py          # 带外编辑在下次 recall 可见
│   ├── test_two_layer_scope.py               # project + global；跨项目隔离
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   └── test_cli_memory_cmd.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── FactList.test.tsx
├── FactViewer.test.tsx                       # 只读渲染 + 打开/显示能力
└── RecallBox.test.tsx
```

## Importlinter contracts（新增或修订）

- **扩展跨 kind contract**：`coffer.{domain,application,...}.memory` 不得 import `mcp` 或 `knowledge_base`，反之亦然（共享的 `knowledge` 底座对 KB 与 memory 都允许）。
- **新增底座限制 contract**：`coffer.application.*` 与 `coffer.domain.*` MUST NOT import 索引引擎（`sqlite_vec`、FTS5 helper、embedding SDK）；只有 `coffer.infrastructure.knowledge.*` 可以。`mem0`、`chromadb`、`llama_index` MUST NOT 在任何地方被 import。

## Risks & mitigations

| 风险                                                 | 缓解                                                                                                                                                                                             |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MCP shim cwd 在某些 agent 上不传播（作用域解析失败） | [research.zh.md](./research.zh.md)（§11）open item #1；实现期在 Claude/Codex 上验证。无法解析的 project 作用域被以 `ScopeUnresolved` **拒绝**（清晰错误；不写任何东西）；`scope=global` 仍可用。 |
| 事实文件或 `MEMORY.md` 被带外编辑（如直接在磁盘上）  | `MEMORY.md` 是幂等重生的派生索引；lazy reindex-on-read 按内容哈希对账事实增量 —— 无需 watcher。                                                                                                  |
| sqlite-vec 在 macOS arm64 / Linux 上打包/加载        | [research.zh.md](./research.zh.md)（§11）open item #2；默认检索是 keyword+grep（无需原生扩展）；vector 为可选项，扩展缺失时优雅降级。                                                            |
| embedding 模型对中文嵌入效果差                       | 默认是 keyword+grep（语言无关）；双语 vector recall 推荐本地 `bge-m3` 或某云端 provider。                                                                                                        |

## Out of scope（推迟）

- recall 上的 reranking / HyDE / multi-query / LLM 合成（由 agent 合成）。
- 向 agent 自己的记忆界面做原生投影（symlink / 受管块）；agent 只通过 MCP 工具访问记忆（原生投影已移除 —— 见 [Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.zh.md)）。
- 多机同步（constitutional）。
- 默认开启文件系统 watcher（memory 改用 lazy reindex-on-read）。
- 超出 `metadata.type` 自由标签之外的 memory 分类。
