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
│   ├── knowledge/                       # 共享底座（KB + memory）—— 见 spec 006
│   │   ├── document.py                  # Document、Chunk、Hit 值对象
│   │   ├── retrieval.py                 # RetrievalPort、RetrievalMode (grep|keyword|vector)
│   │   └── errors.py                    # MemoryNotFound、MemoryRejected、ScopeUnresolved、...
│   └── memory/
│       ├── config.py                    # MemoryStoreConfig（检索模式、embedding、max_fact_chars）
│       ├── fact.py                      # MemoryFact（frontmatter + 正文）值对象
│       └── scope.py                     # MemoryScope (GLOBAL | PROJECT) + 解析结果
├── application/
│   ├── knowledge/                       # 共享索引/检索 service（spec 006）
│   └── memory/
│       ├── kind.py                      # make_memory_kind(...)
│       ├── service.py                   # remember/recall/update/forget/list/clear + MEMORY.md 重生
│       ├── scope_resolver.py            # cwd → git-root → 项目 ULID → store（惰性置备）
│       └── projection.py                # 投影引擎：按 AgentMemoryAdapter.projection_mode 分派
├── infrastructure/
│   ├── knowledge/                       # FTS5 + sqlite-vec + embedding provider + converter（spec 006）
│   │   ├── index.py                     # documents/chunks/FTS5/vec 仓储（唯一 import 索引引擎处）
│   │   └── embeddings/                  # OpenAI 兼容 provider + fastembed 本地
│   └── memory/
│       ├── files.py                     # 每条事实 .md 读写、MEMORY.md 渲染、目录扫描（增量）
│       └── paths.py                     # ~/.coffer/memory/{global,projects/<ulid>}
└── surfaces/
    ├── http/memory/                     # /api/v1/memory_stores/*
    └── cli/memory_cmd.py                # `coffer memory ...`
```

agent 侧投影 adapter 随 **agent driver**（而非 memory kind）：

```text
backend/coffer/.../agents/
└── adapters/
    ├── base.py                          # AgentMemoryAdapter 协议
    ├── claude.py                        # SYMLINK；~/.claude/projects/<slug>/memory/
    └── codex.py                         # RENDER managed block；禁用原生 `memories`
```

修改的既有文件：

- `application/mcp/builtin_tools.py` —— 在 KB 工具旁加这五个 memory 工具。
- `surfaces/http/app.py` —— `_wire_memory_kind(...)`。
- `surfaces/cli/main.py` —— `app.add_typer(memory_cmd.app, name="memory")`。
- `infrastructure/persistence/migrations/` —— 一个 revision：删除 `memory_records`、删掉 chroma/LlamaIndex 目录、创建统一 schema。
- `backend/pyproject.toml` —— 删除 `mem0ai`/`chromadb`；加共享底座依赖；新 importlinter contract。
- `frontend/src/kinds.ts` —— 注册 `MEMORY_KIND_UI`。

## Frontend

```text
frontend/src/kinds/memory/
├── index.tsx                # MEMORY_KIND_UI
├── MemoryStoreDetailPage.tsx  # 作用域标签页（Global | Project）
├── FactList.tsx             # DataTable（name、description、type、actor、updated）
├── FactEditor.tsx           # 添加 / 就地编辑（markdown 正文 + name/description/type）
├── RecallBox.tsx            # 带模式选择的搜索（默认 keyword）
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
| MCP shim cwd 在某些 agent 上不传播（作用域解析失败） | 设计文档 open item #1；实现期在 Claude/Codex 上验证。无法解析时回退到 `scope=global` 并给清晰错误。 |
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
