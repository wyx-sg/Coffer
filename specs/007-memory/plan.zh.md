# 实现计划：007 —— Memory Manager

> English: [plan.md](./plan.md)

**Branch**: `feature/007-memory`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

在 Coffer 与 kind 无关的资源框架上再加一种 `kind`：`memory`。每个 memory store 是一个承载配置（embedding 模型、LLM provider、最大文本长度）的 Resource。memory 是由编码 agent（经由 Coffer 的 MCP 网关）或用户（UI / CLI）写入的短派生事实，由 **mem0** 在一个薄 `MemoryStore` 端口背后持久化。状态落在 `~/.coffer/memory/<name>/`。

Agent 集成走既有的 MCP 网关：四个新的内置工具（`coffer__list_memory_stores`、`coffer__add_memory`、`coffer__search_memory`、`coffer__delete_memory`）与 KB 的内置工具及上游 MCP 工具一起出现。

本规范在 `006-knowledge-base` 之上落地。

## Technical Context

| Dimension                                     | Value                                                                                                                                             |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                        | Python 3.12+，TypeScript 5.x                                                                                                                      |
| **Primary Dependencies (added by this spec)** | `mem0ai`（memory 框架，藏在端口背后）；LLM provider **由用户配置** —— 本地 Ollama（无 Python 依赖）或 OpenAI（mem0 已经隐式要求的 `openai` 包）。 |
| **Storage**                                   | `~/.coffer/coffer.db` 下的 SQLite 存 `memory_records` 行；mem0 状态落在 `~/.coffer/memory/<name>/`。                                              |
| **Testing**                                   | 4 层测试模型，带 acceptance 标记。大多数路径用 `FakeMemoryStore`；一个集成测试用 `pytest.importorskip` 跑真实 mem0 adapter（配 fake LLM）。       |
| **Performance Goals**                         | SC-002：200 条 memory 的 store 下搜索 wall-clock ≤ 500 ms。                                                                                       |
| **Constraints**                               | mem0 关在 `coffer.infrastructure.memory.*`（importlinter 强制）；mem0 import 失败 daemon 仍能起。                                                 |
| **Scale / Scope**                             | 单用户；≤ 10 个 memory store；每个 store ≤ 10 000 条 memory。                                                                                     |

## Constitution Check

跟 006（knowledge_base）的分析一致。新 kind `memory` 沿着同一套层规则与 import-linter 契约对称扩展。

## Project Structure

```text
backend/coffer/
├── domain/
│   └── memory/
│       ├── __init__.py
│       ├── config.py                    # MemoryStoreConfig pydantic schema
│       ├── record.py                    # MemoryRecord dataclass
│       └── store.py                     # MemoryStore 端口 + MemoryHit value object
├── application/
│   └── memory/
│       ├── __init__.py
│       ├── kind.py                      # make_memory_kind(...)
│       └── service.py                   # MemoryService: add/list/get/search/edit/delete/clear
├── infrastructure/
│   └── memory/
│       ├── __init__.py
│       ├── mem0_store.py                # 唯一 import mem0 的文件
│       ├── persistence.py               # MemoryRecordModel, MemoryRecordRepo
│       └── paths.py
└── surfaces/
    ├── http/
    │   └── memory/
    │       ├── __init__.py
    │       ├── routes.py                # /api/v1/memory_stores/*
    │       └── schemas.py
    └── cli/
        └── memory_cmd.py                # `coffer memory ...`
```

与 006 交集的既有文件修改：

- `application/mcp/builtin_tools.py` —— 在 KB 工具旁追加 memory 工具。
- `surfaces/http/app.py` —— 追加 `_wire_memory_kind(...)`。
- `surfaces/cli/main.py` —— `app.add_typer(memory_cmd.app, name="memory")`。
- `infrastructure/persistence/migrations/env.py` —— import memory persistence 模块。
- `backend/pyproject.toml` —— 新增 `mem0ai` 依赖；新增 importlinter Contract 8。
- `frontend/src/kinds.ts` —— 注册 `MEMORY_KIND_UI`。

## Frontend

```text
frontend/src/kinds/memory/
├── index.tsx                # MEMORY_KIND_UI
├── MemoryStoreCard.tsx
├── MemoryStoreDetailPage.tsx
├── MemoryStoreForm.tsx
├── MemoryList.tsx
├── MemoryRow.tsx            # 就地编辑
├── SearchBox.tsx
└── schema.ts
```

## Tests

```text
backend/tests/
├── unit/memory/
│   ├── test_config_validation.py
│   ├── test_record_value_objects.py
│   └── test_memory_service_with_fake_store.py
├── integration/memory/
│   ├── test_memory_lifecycle.py
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   ├── test_cli_memory_cmd.py
│   └── test_mem0_store_real.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── MemoryStoreForm.test.tsx
├── MemoryStoreDetailPage.test.tsx
└── MemoryList.test.tsx
```

## Importlinter contracts（新增或扩展）

- **扩展 Contract 5**（跨 kind import 禁止）：把 `coffer.{domain,application,infrastructure,surfaces.http}.memory` 加入源模块；按 kind 给 `mcp`、`knowledge_base`、`memory` 都补 `forbidden_modules`。
- **扩展 Contract 6**（kind-agnostic core ↛ kind-specific）：把 `coffer.{...}.memory` 加入 `forbidden_modules`。
- **新增 Contract 8**（mem0 引擎隔离）：`coffer.application.*` 与 `coffer.domain.*` MUST NOT import `mem0`（含任何子模块）。只有 `coffer.infrastructure.memory.mem0_store` 可以。

## Risks & mitigations

| Risk                                        | Mitigation                                                                                                            |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| mem0 在 2024 年间动过 API                   | 所有 mem0 类型集中在一个文件；端口形状由我们定，不由 mem0 定。                                                        |
| mem0 写入必须调 LLM —— 对首次用户是真实摩擦 | UX：首次 add 时显眼的「configure LLM provider」CTA；读路径不需要 LLM。Quickstart 把 Ollama 作为零成本的本地默认推荐。 |
| mem0 传递性拖来重依赖（OpenAI 客户端等）    | 锁定 `mem0ai` core；除非必要不引 extras。锁文件时再评估。                                                             |

## Out of scope (deferred)

- memory 的「consolidation」运行（mem0 自带，本规范不暴露）。
- 跨 store 搜索。
- memory 的类别 / tag / 集合。
- 时间衰减打分。
- memory export-to-markdown。
- 多用户 / 多 actor 作用域（我们把单用户视作唯一 `user_id`，用 store 名做作用域）。
