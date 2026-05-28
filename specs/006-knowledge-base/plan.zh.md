# 实现计划：006 —— Knowledge Base Manager

> English: [plan.md](./plan.md)

**Branch**: `feature/kb-manager`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

在 Coffer 与 kind 无关的资源框架上再加一种 `kind`：`knowledge_base`。每个 KB 是一个承载配置（embedding 模型、chunk size、chunk overlap、max 文档大小）的 Resource。文档以原始文件落在 `~/.coffer/kb/<name>/raw/`，索引（chunk + 向量）由 **LlamaIndex** 写到 `~/.coffer/kb/<name>/index/` —— LlamaIndex 藏在一个薄的 `KnowledgeBaseStore` 端口背后，application 与 domain 层从不 import 它的类型。

Agent 集成走既有的 MCP 网关：三个新的内置工具（`coffer__list_knowledge_bases`、`coffer__search_knowledge_base`、`coffer__get_document`）加入每个接入 MCP 客户端的工具清单，挂在保留前缀 `coffer__` 下，永远不会与上游 MCP server 冲突。

## Technical Context

| 维度             | 取值                                                                                                                                                                                                                       |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **语言 / 版本**  | Python 3.12+，TypeScript 5.x                                                                                                                                                                                               |
| **新增主要依赖** | `llama-index-core`（RAG 框架，藏在端口后）；`llama-index-embeddings-huggingface` + `sentence-transformers`（默认本地 embedding 模型：`BAAI/bge-small-en-v1.5`）；`pypdf`（PDF 抽取）；`langfuse`（可选，由环境变量门控）。 |
| **存储**         | 控制面行落在 `~/.coffer/coffer.db` 的 SQLite；文档以原始文件落在 `~/.coffer/kb/<name>/`。                                                                                                                                  |
| **测试**         | 四层模型。Acceptance marker 把测试串到 `spec.md` 的场景。真 SQLite + `FakeKnowledgeBaseStore` 覆盖大部分路径；一个 integration 测试在 `pytest.importorskip` 守护下走真 LlamaIndex adapter。                                |
| **性能目标**     | SC-002：50 篇文档 KB 上的 REST 检索墙钟延迟 ≤ 500 ms。                                                                                                                                                                     |
| **约束**         | LlamaIndex 限定在 `coffer.infrastructure.knowledge_base.*`（importlinter 强制）；摄入与检索均不出网；daemon 即使 LlamaIndex 无法 import 也能起（接口降级为 503）。                                                         |
| **规模 / 范围**  | 单用户；≤ 20 个 KB；每个 KB ≤ 500 篇文档；每篇文档默认 ≤ 25 MB。                                                                                                                                                           |

## Constitution Check

| 条款                              | 合规 | 备注                                                                                                                            |
| --------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First**                | ✅   | 本地 embedding；文档落盘；无云调用。                                                                                            |
| **II. Spec-as-Truth**             | ✅   | 规范先提交；acceptance 场景驱动测试。                                                                                           |
| **III. OSS-Readiness**            | ✅   | LlamaIndex (MIT)、sentence-transformers (Apache 2.0)、pypdf (BSD-3)。LangFuse (MIT) 可选。                                      |
| **Languages**                     | ✅   | 仅 Python 3.12 后端 + TS 5 前端。                                                                                               |
| **Architecture: layered**         | ✅   | 引擎限定在 `infrastructure/`。增加两条新 importlinter 子契约（见下）。                                                          |
| **Persistence**                   | ✅   | 控制面用 SQLite；大块用户内容（文档）落盘 —— 符合宪法「批量用户内容存为本地文件系统上的文件，按需建索引」原则。                 |
| **Credentials**                   | ✅   | 不需要；默认配置不接远程 API。                                                                                                  |
| **网络默认**                      | ✅   | 仅 loopback。开启时的 LangFuse 与用户自托管的 host 对话。                                                                       |
| **「第二个 feature 也需要再抽」** | ✅   | LangFuse tracer 端口在本 PR 内仍是 _kind-specific_ 的；若 `memory`（007）也要 trace，那时再抽 `infrastructure/observability/`。 |

## Project Structure

### Documentation (this feature)

```text
specs/006-knowledge-base/
├── spec.md
├── plan.md                # 本文件
├── research.md            # LlamaIndex / embedding 模型 / 切块选择
├── data-model.md          # 实体、端口、schema
├── contracts/
│   └── api.openapi.yaml   # /api/v1/knowledge_bases/* 的 REST 契约
├── quickstart.md
└── tasks.md
```

### Source code (各层落点)

```text
backend/coffer/
├── domain/
│   ├── errors.py                                    # 新增：KBNotFound、DocumentNotFound、IngestRejected、EngineUnavailable
│   └── knowledge_base/
│       ├── __init__.py
│       ├── config.py                                # KnowledgeBaseConfig pydantic v2 schema
│       ├── document.py                              # Document dataclass（kind 内部实体）
│       └── store.py                                 # KnowledgeBaseStore 端口（Protocol）+ Passage 值对象
├── application/
│   └── knowledge_base/
│       ├── __init__.py
│       ├── kind.py                                  # make_kb_kind(...)：装配带 on_delete 的 Kind
│       └── service.py                               # KnowledgeBaseService：ingest / list_docs / search / delete_doc
├── infrastructure/
│   └── knowledge_base/
│       ├── __init__.py
│       ├── llamaindex_store.py                      # 唯一 import llama_index.* 的文件
│       ├── document_repo.py                         # kb_documents 的 SqlAlchemy repo
│       ├── persistence.py                           # kb_documents 的 SqlAlchemy ORM
│       ├── paths.py                                 # ~/.coffer/kb/<name>/{raw,index} 路径辅助
│       └── loaders.py                               # MIME / 扩展名 whitelist + 抽取器（PDF 用 pypdf）
├── application/mcp/
│   └── builtin_tools.py                             # KB 内置工具注册到 MCPGatewaySession
└── surfaces/
    ├── http/
    │   └── knowledge_base/
    │       ├── __init__.py
    │       ├── routes.py                            # /api/v1/knowledge_bases/* + ingest / search / list-docs
    │       └── schemas.py                           # KBCreate、KBOut、IngestResult、SearchHit、...
    └── cli/
        └── knowledge_base_cmd.py                    # `coffer kb create/ingest/search/list-docs/delete-doc/delete-kb/describe`
```

要改的既有文件（与 feature/skill-manager / feature/memory-manager 的交叉点 —— 用 rebase 处理）：

- `backend/coffer/surfaces/http/app.py` —— 在 lifespan 中加 `_wire_kb_kind(...)`；挂载 KB 路由。
- `backend/coffer/surfaces/cli/main.py` —— `app.add_typer(knowledge_base_cmd.app, name="kb")`。
- `backend/coffer/application/mcp/gateway.py`（或加一个 shim）—— 把 `coffer__*` 工具调用路由到内置 handler。
- `backend/coffer/infrastructure/persistence/migrations/env.py` —— 引入 KB ORM 让新表被 Alembic 看到。
- `backend/pyproject.toml` —— 新依赖 + 引擎隔离 importlinter 契约。
- `frontend/src/kinds.ts` —— 注册 `KNOWLEDGE_BASE_KIND_UI`。

### Frontend

```text
frontend/src/kinds/knowledge_base/
├── index.tsx                 # KNOWLEDGE_BASE_KIND_UI (Card + DetailPage + addPath)
├── KnowledgeBaseCard.tsx
├── KnowledgeBaseDetailPage.tsx
├── KnowledgeBaseForm.tsx
├── DocumentList.tsx
├── UploadDropzone.tsx
├── SearchBox.tsx
└── schema.ts
```

### Tests

```text
backend/tests/
├── unit/knowledge_base/
│   ├── test_config_validation.py
│   ├── test_document_value_objects.py
│   ├── test_loaders_extension_whitelist.py
│   └── test_kb_service_with_fake_store.py
├── integration/knowledge_base/
│   ├── test_kb_lifecycle.py                # create → ingest → search → delete-doc → delete-kb（acceptance）
│   ├── test_mcp_builtin_tools.py           # 通过 MCP 验证 search_knowledge_base / get_document / list_knowledge_bases
│   ├── test_http_routes.py                 # REST 接口
│   ├── test_cli_kb_cmd.py
│   └── test_llamaindex_store_real.py       # importorskip llama_index_core；smoke
└── contract/
    └── test_kb_openapi.py                  # OpenAPI dump 与 contracts/api.openapi.yaml 对齐

frontend/src/kinds/knowledge_base/
├── KnowledgeBaseForm.test.tsx
├── KnowledgeBaseDetailPage.test.tsx
└── DocumentList.test.tsx
```

## Phase 1 — 规范与契约（本 PR 的前几个 commit）

1. spec.md ✅ 在任何代码之前先提交。
2. data-model.md —— 实体、端口方法、SQL schema（`kb_documents` 表）。
3. contracts/api.openapi.yaml —— REST 接口。
4. research.md —— LlamaIndex 选型、embedding 模型选型、切块默认值。

## Phase 2 — 后端（TDD）

对 `spec.md` 中的每一个 acceptance 场景：

1. 先在正确层（pure 在 unit、其他在 integration）写一个失败测试，带 acceptance marker。
2. 写最少量的 domain / application / infra 代码让它通过。
3. 小步提交：`feat(kb): <scenario>`（Conventional Commits）。

顺序：domain 类型 → 端口 → 测试用 `FakeKnowledgeBaseStore` → application 服务 → 真 `LlamaIndexKnowledgeBaseStore` → HTTP 路由 → CLI → 内置 MCP 工具 → composition root 装配。

## Phase 3 — 前端

1. `KnowledgeBaseForm`（zod schema；与 `KnowledgeBaseConfig` 对齐）。
2. `KnowledgeBaseDetailPage`（文档列表 + 上传 + 检索）。
3. 在 `kinds.ts` 注册 `KNOWLEDGE_BASE_KIND_UI`。
4. 在前端范围内为每条 acceptance 场景写一个 integration 测试（UI 流）。

## Phase 4 — 验证

1. `make lint` —— 含新增 importlinter 契约。
2. `make verify-unit`（purity 守护通过；`tests/unit/` 下无被禁的 I/O import）。
3. `make verify-integration`。
4. `make verify-contract` —— OpenAPI 对齐。
5. `make verify-acceptance` —— `spec.md` 中每个场景都有覆盖 marker。
6. 终版 commit。

## 要新增的 Importlinter 契约

下面两条新契约把既有的 kind-isolation 规范从 `mcp` 复制到 `knowledge_base`：

- **扩展 Contract 5**（禁止跨 kind import）：把 `coffer.domain.knowledge_base`、`coffer.application.knowledge_base`、`coffer.infrastructure.knowledge_base`、`coffer.surfaces.http.knowledge_base` 加入 `source_modules` 列表，并把 `coffer.*.mcp` 加入逐 kind 的 `forbidden_modules`。（`memory` kind 在 spec 007 中落地；其跨 kind 禁止规则到那时再加。）
- **扩展 Contract 6**（kind-agnostic 内核 ↛ kind-specific）：把 `coffer.domain.knowledge_base`、`coffer.application.knowledge_base` 等加入 `forbidden_modules`。
- **新增 Contract 7**（引擎隔离）：`coffer.application.*` 与 `coffer.domain.*` 不得 import `llama_index*`。

## Risks & mitigations

| 风险                                                | 缓解                                                                                                                                                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LlamaIndex 大版本 churn（2024 两次破坏性 refactor） | 所有 LlamaIndex 类型集中在一个文件 `infrastructure/knowledge_base/llamaindex_store.py`；未来升级只动这一个文件。端口形状按 Coffer 的需求来，不按 LlamaIndex 的。        |
| LlamaIndex 安装在 CI 上重 / 慢                      | 需要真引擎的 integration 测试用 `pytest.importorskip("llama_index.core")` 守护；unit 套件走 `FakeKnowledgeBaseStore`。CI 只装 `llama-index-core`（不装 meta-package）。 |
| 首次摄入要下载 embedding 模型                       | 在 `quickstart.md` 中明示。提供 `coffer kb warmup <name>` 命令显式触发下载。                                                                                            |
| `pypdf` 文本抽取质量参差                            | 在 loader 里做 pre-flight 抽取；空抽取明确拒绝；在 `quickstart.md` 中阐明支持格式。                                                                                     |
| 同 KB 并发摄入                                      | 在 store adapter 内对每个 KB 持一个 asyncio.Lock，只在写索引阶段持有；读不锁。                                                                                          |
| LlamaIndex 拖入沉重的传递依赖与既有 pin 冲突        | 锁到 `llama-index-core`（不引 meta-package）；只装我们用到的具体 embedding 集成（`llama-index-embeddings-huggingface`）。                                               |

## Out of scope (deferred)

- 在检索之上做 LLM 合成（agent 自己做 —— Coffer 只回片段）。
- Reranker、multi-query expansion、HyDE。
- 文档历史版本（重新摄入即替换）。
- 默认 recursive splitter 之外的源代码感知切块。
- 图像 OCR、音频转写。
- 多模态检索。
- 云端 embedding provider。

以上每一项都可作为 MVP 之后的后续规范。端口面有意保持最小，添加它们只需新 adapter 或新方法，而不是重新建模。
