# 实施计划：001 — MCP Gateway

> English: [plan.md](./plan.md)

**Branch**: `feature/mcp-gateway`
**Date**: 2026-05-20
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

> 对于 agentic 工作流：推荐使用 `superpowers:subagent-driven-development`，
> 或使用 `superpowers:executing-plans`，按 [tasks.md](./tasks.md) 中的任务
> 逐条实施。每个任务都使用 checkbox (`- [ ]`) 语法追踪进度。

## Summary

构建 coffer MCP 网关 (gateway)：一个本地 daemon，聚合上游 MCP 服务器，并通过带命名空间的统一界面把它们的工具 (tool)、资源 (resource)、提示词 (prompt) 重新暴露给一个或多个 MCP 客户端（Claude Code、Codex）。配套交付 CLI 与 stdio shim。

本次实施同时把 kind-agnostic 的 Resource 框架铺好——首个具体 kind 是 `mcp_server`，后续 spec 再加更多。

面向用户的契约见 [./spec.md](./spec.md)；架构理由见 [ADR](../../docs/decisions/)。

## Technical Context

| Dimension                               | Value                                                                                                                                                                                                             |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                  | Python 3.12+, TypeScript 5.x (e2e)                                                                                                                                                                               |
| **Primary Dependencies** (本 spec 新增) | SQLAlchemy 2 + aiosqlite + Alembic, Typer + Rich, structlog, keyring, httpx, `mcp` SDK (官方), psutil。E2e：Playwright (`@playwright/test`)。                                                                     |
| **Storage**                             | SQLite，位于 `~/.coffer/coffer.db`，WAL 模式，daemon 是唯一写入方                                                                                                                                                 |
| **Testing**                             | Coffer 的 4 层模型：unit / integration / contract / e2e。`pytest`（后端）+ `Playwright`（MCP e2e）。Acceptance markers 把测试与 [spec.md](./spec.md) 中的 scenario 绑定。                                          |
| **Target Platforms**                    | macOS arm64+x64 (universal), Windows x64, Linux x64+arm64                                                                                                                                                         |
| **Project Type**                        | CLI + daemon + stdio shim（多进程 local-first）                                                                                                                                                                     |
| **Performance Goals**                   | 按 [spec.md](./spec.md) SC-003：每次工具调用网关开销 ≤ 50 ms（100 次采样的中位数）。daemon 冷启动 ≤ 5 s 进入 ready。                                                                                              |
| **Constraints**                         | Local-first（仅 127.0.0.1）；密钥以 Fernet 密文形式存于加密凭据存储（主密钥文件默认 / 钥匙串 opt-in）；分层架构（importlinter contracts 1–6）；单文件 ≤ 400 LOC（后端）。                                                                                 |
| **Scale / Scope**                       | 单用户；并发 MCP 客户端 ≤ 3；注册 MCP 服务器 ≤ 30；单服务器能力数 ≤ 100。                                                                                                                                         |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                     |
| ----------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | ✅         | 所有 HTTP 界面绑定 `127.0.0.1`。零云调用。SQLite 是唯一记录系统。                                                                         |
| **II. Spec-as-Truth**                     | ✅         | 本计划实现 [spec.md](./spec.md)；spec 在代码之前已提交。每个 acceptance scenario 至少被一个测试拥有（由 `make verify-acceptance` 审计）。 |
| **III. Open-Source-Readiness**            | ✅         | 仓库已具备 MIT 协议、CONTRIBUTING.md、Conventional Commits、dependabot。无闭源依赖。                                                      |
| **Languages**                             | ✅         | 仅 Python 3.12 + TypeScript 5 (e2e)。                                                                                                     |
| **Architecture: layered**                 | ✅         | importlinter contracts 1–4 已在 `backend/pyproject.toml`；本计划新增 contracts 5–6（cross-kind 隔离，kind-agnostic 核心边界）。           |
| **Persistence: SQLite for control plane** | ✅         | 所有状态进 `coffer.db`。本 spec 无文件型用户内容（暂无 `Memory` kind）。                                                                  |
| **Credentials: 加密存储**                 | ✅         | 密钥以 Fernet 密文形式存于 `credentials` 表；`infrastructure/credentials/` 是 `keyring` 的唯一引入点（主密钥 + legacy 迁移）。Resource 配置只持有凭据**引用**（字符串 key）。                |
| **Network defaults: loopback-only**       | ✅         | FastAPI 绑定 `127.0.0.1`。CORS 白名单堵住浏览器 CSRF。v0 不发起公网出站，除用户自行配置的上游 HTTP MCP 服务器外。                         |

**Resource framework upfront**（ADR-001）针对宪法 "Cross-cutting modules are
extracted only after the second feature needs them" 一条做过评估，判定不适用——因为该框架是**核心领域**，不是横切的基础设施。详见 [ADR-001 Decision § rationale]。

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-gateway/
├── spec.md              # user-visible contract (committed)
├── plan.md              # this file
├── research.md          # library + protocol choices
├── data-model.md        # entities + SQL schema
├── contracts/
│   └── api.openapi.yaml # management REST contract
├── quickstart.md        # how the feature is used once shipped
├── tasks.md             # bite-sized work breakdown (TDD)
└── checklists/          # generated by /speckit-checklist (later)
```

### 源码（本 PR 实际交付）

```text
backend/coffer/
├── domain/
│   ├── resource.py                       # Resource, ResourceRef, Kind
│   ├── audit.py                          # AuditEntry, AuditEventType
│   ├── retention.py                      # RetentionPolicy
│   ├── errors.py                         # CofferError hierarchy
│   ├── kind_module.py                    # KindModule frozen dataclass
│   └── mcp/
│       ├── server_config.py              # MCPServerConfig + transports
│       ├── capability.py                 # MCPTool/Resource/Prompt + Preference + Invocation
│       └── namespace.py                  # prefix_tool / parse_prefixed_tool / URI helpers
├── application/
│   ├── resource_service.py               # kind-agnostic CRUD
│   ├── audit_service.py                  # AuditService
│   ├── retention_service.py              # PrunableRegistry-driven prune
│   ├── retention_worker.py               # background asyncio task
│   ├── repos.py                          # Protocol classes used by services
│   └── mcp/
│       ├── gateway.py                    # MCPGatewaySession 入口与生命周期
│       ├── gateway_handlers.py           # JSON-RPC 方法分派
│       ├── gateway_aggregate_lists.py    # tools/resources/prompts 列表聚合
│       ├── gateway_server_requests.py    # upstream→downstream 请求中继 (roots/sampling)
│       ├── kind.py                       # MCP_KIND 组装 (KindModule wiring)
│       ├── supervisor.py                 # subprocess 生命周期
│       ├── discovery.py                  # 能力实时发现 + 缓存
│       └── credential_resolver.py        # 拉起时物化凭据引用
├── infrastructure/
│   ├── persistence/
│   │   ├── base.py
│   │   ├── models.py                     # ResourceModel/AuditLogModel/RetentionPolicyModel
│   │   ├── repos.py
│   │   ├── engine.py                     # async_engine + PRAGMA
│   │   ├── retention.py                  # PrunableTable + PrunableRegistry
│   │   └── migrations/
│   │       ├── env.py
│   │       ├── alembic.ini
│   │       └── versions/
│   │           ├── 20260520_0001_initial.py
│   │           ├── 20260521_0002_mcp_tables.py
│   │           └── 20260522_0003_mcp_server_health.py
│   ├── credentials/
│   │   └── keyring_adapter.py            # 唯一可 import `keyring` 的文件
│   ├── daemon/
│   │   ├── pid_lock.py
│   │   ├── port_alloc.py
│   │   ├── orphan_sweep.py
│   │   ├── bootstrap.py                  # detect-or-spawn helper
│   │   └── entry.py                      # daemon 进程入口 (uvicorn)
│   ├── logging/
│   │   └── setup.py                      # structlog + trace_id contextvar
│   └── mcp/
│       ├── subprocess.py                 # stdio MCP 的 asyncio Popen 封装
│       ├── http_client.py                # HTTP MCP 的 httpx + SSE
│       └── persistence.py                # MCPCapabilityPreferenceModel + MCPInvocationModel + repo
├── surfaces/
│   ├── http/
│   │   ├── app.py                        # FastAPI 组装入口
│   │   ├── auth.py                       # X-Coffer-Token 依赖
│   │   ├── cors.py
│   │   ├── errors.py                     # 全局异常 → ErrorResponse 信封
│   │   ├── schemas.py                    # 与 openapi.yaml 对齐的 Pydantic 模型
│   │   ├── dependencies.py               # FastAPI 依赖接线 (服务 / 仓库)
│   │   ├── resource_routes.py            # /api/v1/resources/* (kind-agnostic)
│   │   ├── audit_routes.py               # /api/v1/audit
│   │   ├── retention_routes.py           # /api/v1/retention/*
│   │   ├── daemon_routes.py              # /api/v1/daemon/*
│   │   ├── credential_routes.py          # /api/v1/credentials/* (写入、带审计的读取、exists、删除)
│   │   └── mcp/
│   │       ├── capability_routes.py
│   │       ├── invocation_routes.py
│   │       └── protocol_routes.py        # /mcp JSON-RPC over HTTP/SSE
│   ├── cli/
│   │   ├── main.py                       # Typer 组装入口
│   │   ├── _client.py                    # HTTP 客户端封装（读取 daemon.json + token）
│   │   ├── _options.py                   # 共用 Typer option / 退出码辅助
│   │   ├── _mcp_caps.py                  # mcp 能力渲染辅助
│   │   ├── daemon_cmd.py                 # coffer daemon ...
│   │   ├── resource_cmd.py               # coffer resource ...
│   │   ├── audit_cmd.py                  # coffer audit ...
│   │   ├── retention_cmd.py              # coffer retention ...
│   │   ├── credentials_cmd.py            # coffer credentials set/get/list/delete/storage ...
│   │   └── mcp.py                        # coffer mcp ... (kind 子命令组)
│   └── shim/
│       └── main.py                       # coffer-mcp-shim 入口
```

**Structure decision**: 层优先、kind 在子目录（[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)）。既有的
`backend/coffer/{domain,application,infrastructure,surfaces}/__init__.py`
保留；本 spec 负责把内容填进去。

## Phases (high-level)

Phase 是**交付边界**；具体任务粒度在 [tasks.md](./tasks.md)。

### Phase 1 — Setup (shared infrastructure)

加运行时依赖、importlinter contracts 5–6、structlog 配置、SQLAlchemy + Alembic
骨架、与 `contracts/api.openapi.yaml` 对应的 Pydantic schema、错误信封、FastAPI
composition root 脚手架、Typer composition root 脚手架。尚无业务逻辑；CI 在占位代码上跑绿。

**Done when:** `make verify` 通过；daemon 可启动并暴露
`GET /api/v1/daemon/status`，返回 `status: "starting"` 然后 `"ready"`。

### Phase 2 — Foundational (kind-agnostic core)

实现 Resource 框架（`Resource`、`Kind`、`KindModule`、`ResourceService`、
`AuditService`）和 retention 框架（`PrunableRegistry`、`RetentionService`、
`RetentionWorker`），以及 `/api/v1/resources/*`、`/api/v1/audit`、
`/api/v1/retention/*`、`/api/v1/daemon/*` 路由 + 对应 Typer 子命令组 + 对应通用 UI
组件。

**Done when:** kind-agnostic 界面能在测试中针对一个注册为 `fake_kind` 的 kind 跑通完整 CRUD + audit + retention 测试覆盖。

### Phase 3 — MVP：US1 + US2（聚合 + 筛选）

注册 `mcp_server` kind。实现 `MCPGatewaySession`、
`SubprocessSupervisor`、`CapabilityDiscovery`、`/mcp` JSON-RPC 端点、
`coffer-mcp-shim` 二进制以及 `coffer mcp …` CLI 子命令。按工具的启用/禁用
（US2）也在这里落地——它们与 US1 共享同一代码路径，因此一起实现。
credential 管理端点（FR-011）也在本阶段落地——写入、带审计的读取、exists
与删除——以便 HTTP MCP 服务器可以端到端引用凭据。

**Done when:** User Story 1 与 User Story 2 的 acceptance scenario 在
`make verify` 与 `make verify-e2e`（`e2e/mcp/` 的子进程驱动套件）下通过。

**MVP gate:** Phase 3 之后，即可通过 `pip install -e ./backend`
把此功能交付早期用户。这是刻意的 MVP 切线。

### Phase 4 — User Story 3 (P2)：CLI 完备性（与 REST 对齐）

很多 CLI 子命令在 Phase 2（`resource`、`daemon`、`credentials`）和 Phase 3
（`mcp`）已经落地。Phase 4 补两阶段留下的缺口——通常是 `--json` 输出开关、
`--verbose` traceback 渲染，以及脚本所依赖的按错误类别返回的退出码。

**Done when:** User Story 3 的 acceptance scenario 通过（`command line
covers every visual operation`、`command line surfaces same errors`、`CLI
returns non-zero exit on daemon unreachable`、`CLI --json output is
machine-readable`）。

### Phase 5 — User Story 4 (P3)：审计与活动日志（audit + invocations + retention CLI）

audit 日志、invocation 日志、retention 框架本身在 Phase 2 作为 kind-agnostic
组件落地；Phase 5 完成它们的 CLI 接口（`coffer audit …`、`coffer mcp invocations …`、
`coffer retention …`），并验证 retention prune 不会阻塞在线 API 调用。

**Done when:** User Story 4 的 acceptance scenario 通过（`audit lifecycle
changes`、`invocation log records calls without arguments`、`configure
retention per log`、`daemon backup produces a portable SQLite copy`）。

### Phase 6 — 加固

启动时的孤儿子进程清扫；daemon 优雅关闭的信号处理；上游健康状态机；
带上限的日志轮转；并发客户端负载冒烟。覆盖 [spec.md](./spec.md) Edge Cases
中尚未涵盖的项目。

**Done when:** [spec.md](./spec.md) 中每条 Edge Case 都有覆盖它的 integration
或 e2e 测试。

## Complexity Tracking

| Decision                                                                                                    | Why needed                                                                                                  | Simpler alternative rejected because                                                                           |
| ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 第二个 kind 之前先做 Resource 框架（[ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)） | schema、audit、retention、surface routing 都共享 kind-agnostic 模式；事后再抽离会迫使四个子系统全部重建模。 | "现在只做 MCP，以后再泛化" 会把这四个子系统的重构成本叠加，而不是一次到位地设计。                              |
| 同时提供 stdio shim 与 HTTP `/mcp` 端点                                                                     | MCP 客户端生态分裂——主流客户端只支持 stdio 配置，新一批偏好 HTTP。                                          | 仅 stdio 会失去远端 MCP 服务器和 daemon HTTP 原生形态；仅 HTTP 会失去仅支持 stdio 的客户端。 |
| 按会话的子进程集合（[ADR-005](../../docs/decisions/ADR-005-session-subprocess-model.md)）                   | MCP `initialize` 和 `capabilities` 是按会话的；一个上游无法同时服务两个声明能力不同的客户端。               | 共享子进程 + 多路复用层会在网关上重新实现会话语义，工程量约为 3 倍。                                           |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Research: [research.md](./research.md)
- Data model: [data-model.md](./data-model.md)
- Wire contract: [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)
- Quickstart: [quickstart.md](./quickstart.md)
- Tasks: [tasks.md](./tasks.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Decision records: [`docs/decisions/`](../../docs/decisions/)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
