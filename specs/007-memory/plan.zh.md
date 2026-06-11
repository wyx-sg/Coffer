# 实现计划：007 —— Memory（跨 agent 共享记忆）

> English: [plan.md](./plan.md)

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.zh.md](./spec.zh.md)
**Status**: Draft (redesign)

## Summary

memory 是与 knowledge base（spec 006）共用同一套统一知识底座的 **memory 面**。每个记忆作用域是一个 kind 为 `memory` 的 Resource。事实 = 每条事实一个 markdown 文件（YAML frontmatter + 正文）加一个重新生成的 `MEMORY.md` 索引 —— 即 Claude Code 的 auto-memory 格式 —— 放在 `~/.coffer/memory/` 下。**文件是真相源；SQLite（`documents` + FTS5 + sqlite-vec）是可重建的索引。** 有两种作用域：global（sentinel ULID）与 per-project（由 agent 工作目录解析出的项目 ULID）。

写入时不调 LLM —— agent 直接写一条干净的事实。共享是混合式：每个 agent 经 Coffer MCP 网关读写（`coffer__recall/remember/update_memory/forget/list_memory`），且规范化文件由 `AgentMemoryAdapter` **投影** 进各 agent 的原生位置（Claude Code = 目录 symlink；Codex = `AGENTS.md` 中带标记栅栏的 managed block，并禁用原生 `memories`）。用户在 Coffer UI/CLI 里做完整 CRUD。

本次重设计 **删除 mem0、chroma、LlamaIndex**，并用统一 `documents` 表取代 `memory_records`。没有数据迁移（分支未发布）。

## Technical Context

| 维度                     | 取值                                                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **语言 / 版本**          | Python 3.12+，TypeScript 5.x                                                                                                                                                          |
| **本规范新增的主要依赖** | 与 KB 共享：`sqlite-vec`（向量索引）、`fastembed`（可选本地 embedding）、`PyYAML`（frontmatter）。云端 embedding 经既有 OpenAI 兼容 provider 抽象。**移除：** `mem0ai`、`chromadb`。  |
| **存储**                 | markdown 事实放在 `~/.coffer/memory/global/` 与 `~/.coffer/memory/projects/<project-ulid>/`；索引行在 `~/.coffer/coffer.db`（`documents`、`chunks`、`documents_fts`、`vec_chunks`）。 |
| **测试**                 | 4 层模型配 acceptance 标记。向量路径用 `FakeEmbeddingProvider`；keyword/grep 不需 embedding。投影对临时 `~/.claude` / `~/.codex` 根目录测试。                                         |
| **性能目标**             | SC-003：200 条事实作用域上 keyword recall ≤ 300 ms。                                                                                                                                  |
| **约束**                 | 索引引擎关在 `coffer.infrastructure.knowledge.*` 内（importlinter）；即便向量后端加载失败 daemon 仍能起；`mem0`/`chroma`/`llama_index` 任何地方都不被 import。                        |
| **规模 / 范围**          | 单用户；一个 global store + 每个活跃项目一个 store；事实很短（默认 ≤ 8192 字符）。                                                                                                    |

## Constitution Check

与 KB 相同的分层规则（一套底座）。memory kind 复用共享检索引擎、仓储与 converter；只有 memory 专属的 service（每条事实写入、`MEMORY.md` 重新生成、作用域解析）与投影引擎是 memory 专属。引擎隔离与跨 kind import 禁令对称扩展。`WORKSPACE_GLOBAL_PROJECT_ID` sentinel 复用、不重铸。

## Project Structure

```text
backend/coffer/
├── domain/
│   ├── errors.py                        # 规范错误层级：MemoryStoreNotFound、MemoryNotFound、MemoryRejected、ScopeUnresolved、...
│   ├── knowledge/                       # 共享底座（KB + memory）—— 见 spec 006
│   │   ├── document.py                  # Document 实体（按 kind 区分）
│   │   ├── retrieval.py                 # StoreRef、Passage、GrepHit/GrepResult、MemoryHit、SearchResult、RetrievalMode
│   │   ├── index.py                     # KnowledgeIndex / GrepPort / RetrievalPort 协议
│   │   └── errors.py                    # 底座错误的再导出（规范类在 domain/errors.py）
│   └── memory/
│       ├── config.py                    # MemoryStoreConfig（检索模式、扁平 embedding 字段、max_fact_chars）
│       ├── fact.py                      # MemoryFact（frontmatter + 正文）值对象
│       └── scope.py                     # MemoryScope (GLOBAL | PROJECT) + ResolvedScope
├── application/
│   ├── knowledge/                       # 共享底座 application 层（spec 006）
│   │   ├── retrieval.py                 # KnowledgeRetrieval 门面（keyword/vector + 带标注回退）
│   │   ├── reindex.py                   # 单一幂等 re-index 例程（Reindexer）
│   │   └── locks.py                     # StoreLocks —— 逐 store 写串行化
│   ├── memory/
│   │   ├── kind.py                      # make_memory_kind(...)
│   │   ├── service.py / service_helpers.py  # remember/recall/update/forget/list/clear + MEMORY.md 重生
│   │   ├── writes.py / queries.py       # 事实写/读路径
│   │   ├── recall.py                    # recall 编排 + 倒数排名融合（RRF）合并
│   │   ├── scope.py                     # ScopeResolver：cwd → git-root → 项目 ULID → store（惰性置备）；store 名校验
│   │   ├── stores.py                    # store 名 ↔ ResolvedScope 辅助
│   │   ├── sync.py                      # MemoryReconciler —— 读时惰性 reindex
│   │   └── builtin_tools.py             # 五个 coffer__* memory MCP 工具
│   └── agent/projection/                # 投影随 agent driver，而非 memory kind
│       ├── adapters.py                  # AgentMemoryAdapter 实现（Claude SYMLINK + CLAUDE.md RENDER；Codex RENDER + 禁用 `memories`）
│       ├── engine.py                    # 按 projection_mode 分派；受管块幂等渲染
│       └── types.py
├── infrastructure/
│   ├── knowledge/                       # 共享底座 infra（spec 006）：repository.py、sqlite_index.py、
│   │   …                                # vec_index.py（唯一 sqlite_vec importer）、embeddings.py、grep.py、
│   │                                    # chunking.py、cleaning.py、frontmatter.py、paths.py、converters/
│   └── memory/
│       ├── files.py                     # 每条事实 .md 读写、MEMORY.md 渲染、目录扫描（增量）
│       ├── paths.py                     # ~/.coffer/memory/{global,projects/<ulid>}
│       ├── scope_fs.py                  # 文件系统作用域辅助
│       └── project_root_repo.py         # 投影所需的 project-root 持久化
└── surfaces/
    ├── http/memory/                     # /api/v1/memory_stores/*（facts、recall）
    ├── http/projection_routes.py        # /api/v1/memory_stores/{name}/projections（+ projection_service.py / projection_wiring.py）
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
├── MemoryAddFactForm.tsx                # 添加 / 编辑（markdown 正文 + name/description/type）
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
│   ├── test_scope_resolver.py                # cwd → git-root → ULID；global sentinel
│   └── test_projection_dispatch.py           # SYMLINK | RENDER | NONE；managed-block 幂等
├── integration/memory/
│   ├── test_remember_recall_roundtrip.py     # keyword + vector(fake) + grep
│   ├── test_lazy_reindex_on_read.py          # 带外编辑在下次 recall 可见
│   ├── test_two_layer_scope.py               # project + global；跨项目隔离
│   ├── test_projection_symlink_claude.py     # symlink + 合并已存在文件
│   ├── test_projection_render_codex.py       # managed block + 禁用原生 memories
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   └── test_cli_memory_cmd.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── FactList.test.tsx
├── FactEditor.test.tsx
└── RecallBox.test.tsx
```

## Importlinter contracts（新增或修订）

- **扩展跨 kind contract**：`coffer.{domain,application,...}.memory` 不得 import `mcp` 或 `knowledge_base`，反之亦然（共享的 `knowledge` 底座对 KB 与 memory 都允许）。
- **新增底座限制 contract**：`coffer.application.*` 与 `coffer.domain.*` MUST NOT import 索引引擎（`sqlite_vec`、FTS5 helper、embedding SDK）；只有 `coffer.infrastructure.knowledge.*` 可以。`mem0`、`chromadb`、`llama_index` MUST NOT 在任何地方被 import。

## Risks & mitigations

| 风险                                                 | 缓解                                                                                                |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| MCP shim cwd 在某些 agent 上不传播（作用域解析失败） | 设计文档 open item #1；实现期在 Claude/Codex 上验证。无法解析的 project 作用域被以 `ScopeUnresolved` **拒绝**（清晰错误；不写任何东西）；`scope=global` 仍可用。 |
| Claude 带外改写 `MEMORY.md` 或事实文件               | `MEMORY.md` 是幂等重生的派生索引；lazy reindex-on-read 按内容哈希对账事实增量 —— 无需 watcher。     |
| 首次投影会丢失已存在的原生记忆文件                   | adapter 先把已存在文件合并进规范化，再 symlink；绝不覆盖（FR-012）。                                |
| sqlite-vec 在 macOS arm64 / Linux 上打包/加载        | open item #4；默认检索是 keyword+grep（无需原生扩展）；vector 为可选项，扩展缺失时优雅降级。        |
| embedding 模型对中文嵌入效果差                       | 默认是 keyword+grep（语言无关）；双语 vector recall 推荐本地 `bge-m3` 或某云端 provider。           |

## Out of scope（推迟）

- recall 上的 reranking / HyDE / multi-query / LLM 合成（由 agent 合成）。
- 把某专有 agent 记忆格式双向解析回规范化（用 symlink-where-compatible + 别处 MCP 规避）。
- 多机同步（constitutional）。
- 默认开启文件系统 watcher（memory 改用 lazy reindex-on-read）。
- 超出 `metadata.type` 自由标签之外的 memory 分类。
