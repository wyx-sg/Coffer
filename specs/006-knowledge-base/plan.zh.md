# 实现计划：006 —— Knowledge Base（重新设计）

> English: [plan.md](./plan.md)

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.md](./spec.md)
**Status**: Draft (redesign)

## Summary

把 `knowledge_base` 资源 kind 重建为**共享知识基底的 KB 面**。一个 KB 是承载检索配置（启用的模式、chunk 参数、embedding provider）的 Resource。ingestion 接受**任意文件格式**，将其转换为**磁盘上的 Markdown**（`~/.coffer/knowledge/<name>/docs/<doc-id>.md` = 真相源），把原件留在 `raw/` 下，并把 Markdown 索引进同一个 `coffer.db`（统一的 `documents` + `chunks` + FTS5 + sqlite-vec）。检索有三种模式 —— `grep`（对文件跑 ripgrep）、`keyword`（FTS5 + BM25）、`vector`（sqlite-vec + 一个可配置的 OpenAI 兼容 embedding provider）。agent 通过四个只读内置 MCP 工具读取 KB；KB 由用户策展。

本次重新设计**移除 LlamaIndex** 以及 per-corpus persist 目录，并把它的基底（表、转换器端口、检索引擎、embedding 配置）与 `memory` kind（spec 007）共享。两层 —— 转换器与 vector/embedding 栈 —— 都限制在 `infrastructure/` 内。

## Technical Context

| Dimension                                        | Value                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                           | Python 3.12+, TypeScript 5.x                                                                                                                                                                                                                                                                                                                                                                       |
| **Primary Dependencies (added by the redesign)** | `markitdown`（默认 Markdown 转换器，藏在 `MarkdownConverter` 端口后）；`sqlite-vec`（`coffer.db` 里的向量索引）；FTS5（SQLite 自带）；`openai`（一个 `AsyncOpenAI` 客户端，可换 `base_url`，用于 embedding）；可选 `fastembed`（in-process 本地 embedding）；grep 用的 `ripgrep` 二进制。**移除**：`llama-index-*`、`sentence-transformers`、`chromadb`、`mem0`。 |
| **Storage**                                      | `~/.coffer/coffer.db` 的 SQLite（resources / documents / chunks / FTS5 / sqlite-vec / audit）；`~/.coffer/knowledge/<name>/` 下的 Markdown + raw 文件。                                                                                                                                                                                                                                            |
| **Testing**                                      | 4 层。Acceptance 标记把测试绑定到 `spec.md` 场景。集成层用真实 SQLite（FTS5 + sqlite-vec）；`FakeMarkdownConverter` + `FakeEmbedder` 保持单元测试纯净；一个集成测试在 `pytest.importorskip` 后跑真实 MarkItDown。                                                                                                                                                                                  |
| **Performance Goals**                            | SC-002：50 文档 KB 上 keyword ≤ 200 ms、grep ≤ 500 ms 的 REST 墙钟。                                                                                                                                                                                                                                                                                                                               |
| **Constraints**                                  | 转换器 + sqlite-vec + embedding SDK 限制在 `coffer.infrastructure.*`（importlinter）；keyword+grep 零配置离线工作；vector 可调用第三方 embedding API；某转换库缺失时 daemon 照常启动（该格式降级为 `EngineUnavailable`）。                                                                                                                                                                         |
| **Scale / Scope**                                | 单用户；≤ 20 个 KB；每个 KB ≤ 500 文档；每文档 ≤ 25 MB（默认）。                                                                                                                                                                                                                                                                                                                                   |

## Constitution Check

| Clause                    | Compliance | Notes                                                                                                                                                                       |
| ------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First**        | ✅         | 所有用户数据（Markdown + raw + SQLite）在磁盘。vector 模式可能调用第三方 embedding API —— 允许：用户数据留在本地，只有 query/文本被 embedding。默认 keyword+grep 完全离线。 |
| **II. Spec-as-Truth**     | ✅         | 规范先重写；acceptance 场景驱动测试。                                                                                                                                       |
| **III. OSS-Readiness**    | ✅         | MarkItDown (MIT)、sqlite-vec (Apache 2.0/MIT)、fastembed (Apache 2.0)、openai SDK (Apache 2.0)。                                                                            |
| **Languages**             | ✅         | 仅 Python 3.12 + TS 5。                                                                                                                                                     |
| **Architecture: layered** | ✅         | 转换器 + vector/embedding 引擎限制在 `infrastructure/`；新增 importlinter 条款（见下）。                                                                                    |
| **Persistence**           | ✅         | SQLite 控制面 + 派生索引；批量内容（Markdown + raw）作为文件 —— 符合宪法的文件落盘规则。                                                                                    |
| **Credentials**           | ✅         | embedding 凭据仅经 keychain ref（`embedding_credential_ref`）；DB 里无明文。                                                                                                |
| **Network defaults**      | ✅         | REST 仅 loopback；出站 embedding 调用走 SSRF 防护客户端。                                                                                                                   |

## Project Structure

### Documentation (this feature)

```text
specs/006-knowledge-base/
├── spec.md / spec.zh.md
├── plan.md / plan.zh.md          # this file
├── research.md / research.zh.md  # converter / retrieval / embedding choices
├── data-model.md / data-model.zh.md
├── contracts/
│   └── api.openapi.yaml          # REST contract for /api/v1/knowledge_bases/*
├── quickstart.md / quickstart.zh.md
└── tasks.md
```

### Source code (where each layer lands)

基底（`knowledge`）与 spec 007 共享；本计划列出 KB 面的部件。共享基底模块标注为 `(shared)`。

```text
backend/coffer/
├── domain/
│   ├── errors.py                                # add: KBNotFound, DocumentNotFound, IngestRejected, EngineUnavailable, ReconversionBlocked, SearchModeInvalid
│   ├── knowledge/                               # (shared) substrate domain
│   │   ├── document.py                          # Document entity (kind-discriminated)
│   │   ├── retrieval.py                         # Passage, GrepHit, GrepResult, MemoryHit, RetrievalMode, SearchResult, StoreRef value objects
│   │   ├── converter.py                         # MarkdownConverter port (Protocol)
│   │   ├── embedder.py                          # Embedder port (Protocol) + EmbeddingConfig
│   │   ├── index.py                             # KnowledgeIndex / GrepPort / RetrievalPort protocols
│   │   └── errors.py                            # re-exports of the substrate errors (canonical classes in domain/errors.py)
│   └── knowledge_base/
│       ├── config.py                            # KnowledgeBaseConfig (Pydantic v2)
│       └── document.py                          # kb_doc_id (16-hex doc-id helper)
├── application/
│   ├── knowledge/                               # (shared) substrate application layer
│   │   ├── retrieval.py                         # KnowledgeRetrieval facade (keyword/vector + flagged fallback)
│   │   ├── reindex.py                           # the single idempotent re-index routine (Reindexer)
│   │   └── locks.py                             # StoreLocks — per-store write serialization
│   └── knowledge_base/
│       ├── kind.py                              # make_kb_kind(...): Kind with on_delete
│       ├── service.py                           # KnowledgeBaseService: list/read/search/grep/metrics + mode validation
│       ├── pipeline.py / pipeline_helpers.py    # ingest / edit / reconvert / reindex write pipeline
│       └── builtin_tools.py                     # the 4 read-only coffer__*_knowledge MCP tools
├── infrastructure/
│   └── knowledge/                               # (shared) substrate infra — engine confinement boundary
│       ├── converters/
│       │   ├── markitdown_converter.py          # default engine; ONLY importer of markitdown
│       │   ├── passthrough_converter.py         # md / txt / source code
│       │   ├── csv_converter.py                 # csv → markdown table
│       │   └── registry.py                      # format → converter dispatch (passthrough → csv → markitdown)
│       ├── cleaning.py                          # whitespace / control-char / heading normalization
│       ├── frontmatter.py                       # YAML frontmatter prepend/parse
│       ├── chunking.py                          # markdown-aware chunker
│       ├── models.py / ddl.py / ids.py          # ORM models, documents_fts DDL hook, id helpers
│       ├── repository.py                        # DocumentRepo (document-row CRUD)
│       ├── sqlite_index.py                      # SqliteKnowledgeIndex — chunks + FTS5 (bm25)
│       ├── vec_index.py                         # VecIndex; ONLY importer of sqlite_vec (lazy per-store vec tables)
│       ├── embeddings.py                        # OpenAI-compatible + local fastembed; ONLY importer of openai/fastembed
│       ├── grep.py                              # ripgrep subprocess wrapper (bounded; truncated flag)
│       └── paths.py                             # ~/.coffer/knowledge/<name>/{docs,raw} layout helpers
└── surfaces/
    ├── http/knowledge_base/
    │   ├── routes.py                            # /api/v1/knowledge_bases/* (create/list/get/ingest/docs/edit/reconvert/delete/reindex/search/grep/metrics)
    │   └── schemas.py
    └── cli/knowledge_base_cmd.py                # coffer kb create/ingest/list-docs/get-doc(read)/edit/reconvert/reindex/search/grep/set-embedding/set-chunking/delete-doc/delete-kb/describe
```

与 spec 007 的交集（在同一个重新设计 PR 里落地）需修改的既有文件：

- `backend/coffer/surfaces/http/app.py` —— 在 lifespan 里 wire KB kind + routers。
- `backend/coffer/surfaces/cli/main.py` —— `app.add_typer(knowledge_base_cmd.app, name="kb")`。
- `backend/coffer/application/mcp/gateway.py` + `gateway_builtin.py` —— 把四个 `coffer__*_knowledge` 工具（由 `application/knowledge_base/builtin_tools.py` 注册）路由到内置处理器。
- `backend/coffer/infrastructure/persistence/migrations/env.py` —— 导入统一的 `documents`/`chunks` ORM。
- `backend/pyproject.toml` —— 换依赖（去 LlamaIndex/chroma/mem0，加 markitdown/sqlite-vec/openai/fastembed）+ 新 importlinter 条款。
- `frontend/src/kinds.ts` —— 注册 `KNOWLEDGE_BASE_KIND_UI`。

### Frontend

```text
frontend/src/kinds/knowledge_base/
├── index.tsx                 # KNOWLEDGE_BASE_KIND_UI (DataTable row + DetailPage + addPath)
├── KnowledgeBaseForm.tsx     # name, description, enabled modes, chunk params, embedding provider
├── KnowledgeBaseDetailPage.tsx
├── DocumentTable.tsx         # shared DataTable; source_mode badge
├── DocumentViewer.tsx        # render + edit Markdown; reindex action
├── UploadDropzone.tsx
├── SearchPanel.tsx           # mode selector (grep/keyword/vector) + results
└── schema.ts
```

### Tests

```text
backend/tests/
├── unit/knowledge_base/
│   ├── test_config_validation.py
│   ├── test_chunking.py
│   ├── test_cleaning.py
│   ├── test_converter_registry.py
│   └── test_kb_service_with_fakes.py            # FakeMarkdownConverter + FakeEmbedder
├── integration/knowledge_base/
│   ├── test_kb_lifecycle.py                     # create → ingest → search → edit → reindex → delete (acceptance)
│   ├── test_retrieval_modes.py                  # grep / keyword / vector + vector fallback (acceptance)
│   ├── test_reindex_idempotency.py
│   ├── test_mcp_builtin_tools.py                # list/search/grep/read via the gateway
│   ├── test_http_routes.py
│   └── test_markitdown_real.py                  # importorskip markitdown; convert a real docx/pdf
└── contract/
    └── test_kb_openapi.py                        # OpenAPI dump matches contracts/api.openapi.yaml
```

## Phase 1 — Spec & contract（本 PR 最先的提交）

1. spec.md ✅ 在任何代码之前重写。
2. data-model.md —— 统一 `documents`/`chunks` schema、FTS5 + sqlite-vec、端口、磁盘布局。
3. contracts/api.openapi.yaml —— 带全应用错误信封的 REST 表面。
4. research.md —— 转换器、检索栈、embedding provider 决策（取代 ADR-010/011）。

## Phase 2 — Substrate（TDD，与 007 共享）

顺序：domain 值对象 + 端口 → 迁移（`documents`/`chunks`/FTS5/sqlite-vec）→ `sqlite_index` + `vec_index` repo → 转换器注册表 + cleaning + frontmatter + chunking → embedders → grep wrapper → 单一 `reindex` 例程。

## Phase 3 — KB application + surfaces（TDD）

每个 acceptance 场景：在正确层写失败测试 + acceptance 标记 → 最小代码 → 小提交。顺序：`KnowledgeBaseConfig` → `KnowledgeBaseService` + ingest/edit/reconvert pipeline → `make_kb_kind`（on_delete）→ HTTP routes（含 `reconvert`）→ CLI → 四个内置 MCP 工具 → composition-root wiring。

## Phase 4 — Frontend

`KnowledgeBaseForm`（zod 对齐 `KnowledgeBaseConfig`）→ `KnowledgeBaseDetailPage`（DocumentTable + UploadDropzone + DocumentViewer 编辑/重建索引 + 带模式选择器的 SearchPanel）→ 注册 `KNOWLEDGE_BASE_KIND_UI` → 每个 UI acceptance 场景一个测试。

## Phase 5 — Verification

`make lint`（importlinter 条款）→ `make verify-unit`（纯净护栏）→ `make verify-integration` → `make verify-contract`（OpenAPI）→ `make verify-acceptance` → 最终提交。

## Importlinter contracts to add / amend

- **Extend Contract 5**（禁止跨 kind import）：加 `coffer.{application,surfaces.http}.knowledge_base`；禁止它们 import `memory` kind 的同级。
- **Extend Contract 6**（与 kind 无关的核心 ↛ kind 专属）：把 `knowledge_base` 模块加入 `forbidden_modules`。
- **New Contract 7**（引擎封闭）：`coffer.application.*` 与 `coffer.domain.*` 不得 import `markitdown`、`docling`、`sqlite_vec`、`openai`、`fastembed` —— 只有 `coffer.infrastructure.knowledge.*` 可以。本条取代旧的「禁 `llama_index`」规则。
- 共享的 `coffer.{domain,infrastructure}.knowledge` 基底是 kind 无关的（KB 与 memory 共用），因此不受跨 kind 禁令约束。

## Risks & mitigations

| Risk                                                              | Mitigation                                                                                                                             |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| PDF 上 MarkItDown 的转换保真度(open item) | 转换器藏在端口 + 按格式注册表后；未来切换或为某格式接入更高保真引擎，只是在 `infrastructure/knowledge/converters/` 下新增一个转换器。    |
| sqlite-vec 在 macOS arm64 + Linux 的打包/加载         | `vec_index.py` 是唯一加载者；集成测试用 `pytest.importorskip` 守护；vector 模式可选，加载失败降级为 keyword（FR-012），不阻塞 daemon。 |
| embedding API 成本/延迟/可用性                                    | 默认 keyword+grep（无 embedding）。请求 vector 但未配置时回退 keyword 并标注。出站调用走 SSRF 防护客户端并带超时。                     |
| 本地 embedding 模型对中文的质量                   | 双语语料推荐 `bge-m3`（fastembed）或云 provider；在 quickstart 中记录。                                                                |
| 运行时转换库缺失                                                  | 按格式给出 `EngineUnavailable` 并指明缺失依赖；其他格式照常 ingest；daemon 不挂。                                                      |
| 参数变化时的重新切块/重新 embedding 成本                          | 文件是真相源，单一 reindex 例程便宜地重导；`content_sha256` no-op 跳过未变文档。                                                       |

## Out of scope (deferred)

- 检索时的 reranking、multi-query 扩展、HyDE、LLM 综合（由 agent 综合）。
- agent 编辑 KB 文档（KB 由用户策展；后续再议）。
- 在一次调用里对 keyword+vector 做 hybrid（RRF）融合 —— 设计里列为可选；若加入，沿用同一端口。
- 默认的图像 OCR / 音频转写。
- 默认开启的文件系统 watcher。
- 多机同步（宪法层面）。

端口表面（converter / embedder / index）刻意做小，让以上任何一项都是一个新适配器，而非重新建模。
