# 实施计划：002 — UI Shell 与视觉语言

> English: [plan.md](./plan.md)

**Branch**: `feature/002-mcp-gateway-web`
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

把 `001-mcp-gateway` 交付时那个仅"能跑"的功能骨架，升级为一个真正的产品壳：一套统一的视觉语言、由 [ADR-007](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md)（资产是 resource kind；agent 是独立的消费者轴）决定的基于角色的信息架构（Agents / Resources / System），以及让首次来访者就能用上的端到端流程。

这是一份**完全建立在 001 之上的纯 UI 重设计**：不新增任何后端接口。每个界面都跑在 `001-mcp-gateway` 已经暴露的同一份 REST API 与 CLI 上；数据模型 (`Resource`、`Kind`、`Capability`、`AuditEvent`、`Invocation`、`RetentionPolicy`) 不变，落在 [`specs/001-mcp-gateway/data-model.md`](../001-mcp-gateway/data-model.md)。同理，本目录没有单独的 `tasks.md`——工作以 [spec.md](./spec.md) `## User Scenarios & Testing` 中的 user story 为单位，并在 PR 层面跟踪。

面向用户的契约见 [./spec.md](./spec.md)，终端用户走查见 [./quickstart.md](./quickstart.md)，IA 决策见 [ADR-007](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md)。

## Technical Context

| Dimension                | Value                                                                                                                                                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**   | TypeScript 5.x，React 18                                                                                                                                                                                                                                  |
| **Primary Dependencies** | React 18 + Vite 5；服务端状态用 TanStack Query 5；路由用 React Router 6；视觉语言用 Tailwind CSS 3 + shadcn/ui（基于 Radix 的基础组件）；i18n 用 react-i18next + i18next；表单用 react-hook-form + zod；API 客户端用 openapi-typescript + openapi-fetch。 |
| **Backend dependency**   | 纯消费方，使用 [`specs/001-mcp-gateway/contracts/api.openapi.yaml`](../001-mcp-gateway/contracts/api.openapi.yaml) 中的 REST 契约。不新增端点、不改 schema。                                                                                              |
| **Storage**              | 仅浏览器 localStorage——存放侧栏收起状态与所选语言。客户端不持久化任何用户数据。                                                                                                                                                                           |
| **Testing**              | `vitest` 跑单元 / 组件测试；`Playwright` 跑 `e2e/` 下的 e2e。Acceptance markers (`acceptance("002-ui-shell", "…", …)`) 把测试与 [spec.md](./spec.md) 中的 scenario 绑定；覆盖率由 `scripts/audit_acceptance.py` 审计。                                    |
| **Target Platforms**     | 主流常青浏览器（Chromium / Firefox / Safari 当前-2）。                                                                                                                                                                                                    |
| **Project Type**         | SPA，由 Vite 打包；生产环境由 daemon 的静态文件路由托管，开发环境由 `vite dev` 直连本地 daemon。                                                                                                                                                          |
| **Performance Goals**    | 冷启动针对本地 daemon 时首屏 2 秒内出内容 (spec 中 `cold-start renders authenticated content` scenario)。语言切换在下一次渲染内完成——不整页刷新。                                                                                                         |
| **Constraints**          | 本地优先（唯一的 HTTP origin 是 `127.0.0.1:<port>` 上的 daemon）；不调公网；不接入第三方分析；不引用字体 CDN。前端组件文件大小 ≤ 250 LOC（由 `scripts/check_file_sizes.py` 强制）。                                                                       |
| **Scale / Scope**        | 单用户；≤ 30 个已注册 resource；每服务器 ≤ 100 个能力（与 `001-mcp-gateway` plan 的边界一致）。                                                                                                                                                           |

## Constitution Check

| 章程条款                          | 合规性 | 说明                                                                                                                            |
| --------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------- |
| **I. 本地优先 (NON-NEGOTIABLE)**  | OK     | 唯一 HTTP origin 是本地 daemon；前端资产自托管；不走字体 CDN；不上分析。                                                        |
| **II. Spec-as-Truth**             | OK     | 本 plan 实现 [spec.md](./spec.md)；spec 先于代码提交。每条 acceptance scenario 至少有一条覆盖测试（acceptance audit 检查）。    |
| **III. 开源就绪**                 | OK     | Tailwind / shadcn / Radix / TanStack Query / React 均为宽松许可证，且已是 001 引入的依赖集合的一部分。                          |
| **Languages**                     | OK     | 仅 TypeScript 5；不引入新语言。                                                                                                 |
| **Architecture: layered**         | OK     | 前端目录沿用 layer-first 约定：`lib/`（横切）、`kinds/<kind>/`（按 kind UI）、`pages/`（合成路由）。                            |
| **Persistence: SQLite 控制平面**  | OK     | 本 spec 不持有持久化；持久化在 daemon。                                                                                         |
| **Credentials: 加密存储**         | OK     | Add-MCP-server 对话框把 secret env 值发到 `/api/v1/credentials`；UI 永不本地保存凭据。                                          |
| **Network defaults: loopback 限** | OK     | Vite dev server 通过 `~/.coffer/daemon.json` 拿到 `http://127.0.0.1:<port>`；生产构建由 daemon 在同一 loopback 上提供静态资源。 |

## Project Structure

### Documentation (this feature)

```text
specs/002-ui-shell/
├── spec.md           # 面向用户的契约（已提交）
├── plan.md           # 本文件
└── quickstart.md     # 终端用户走查 (make dev → 第一台服务器 → 调用日志)
```

本目录刻意**不放** `data-model.md`（数据模型在 spec 001）也**不放** `tasks.md`（按 user story / PR 跟踪——这里的最小变更单元是"一个重设计的界面"，再往下拆原子任务并无收益）。

### Source code (delivered in this PR)

```text
frontend/src/
├── App.tsx                                # 全局 providers (QueryClient、i18n) + RouterProvider
├── main.tsx                               # bootstrap 入口
├── router.tsx                             # createBrowserRouter 路由表
├── kinds.ts                               # 组装入口：注册每个 kind 的 UI 模块
├── i18n/
│   ├── index.ts                           # i18next 配置
│   └── locales/{en,zh}.json               # 每种语言一份扁平词条
├── lib/
│   ├── api/                               # 类型化 API 客户端 + 各资源模块 (resources、agents、skills、fs)
│   ├── hooks/                             # TanStack Query hooks (useResources、useAudit、useAgents…)
│   ├── components/                        # kindRegistry.ts + 共享 ResourceListView
│   ├── auth.ts                            # daemon token 加载（由 dev 插件读 ~/.coffer/daemon.json）
│   ├── preferences.ts                     # 默认每页条数偏好 (General 设置)
│   ├── tauri.ts                           # isTauri() 守卫，用于桌面专属界面
│   └── queryClient.ts / statusColors.ts / timeRange.ts / utils.ts
├── components/                            # 共享 shell + 表格基础件
│   ├── Layout.tsx                         # AppShell + 可折叠侧栏 (localStorage "coffer.nav.collapsed")
│   ├── LanguageSwitcher.tsx
│   ├── DataTable.tsx / DataCardGrid.tsx / Pagination.tsx / SearchInput.tsx / …
│   ├── DaemonOfflineBanner.tsx
│   ├── agents/                            # agent kind UI 组件 (spec 004)
│   └── skills/                            # skill kind UI 组件 (spec 005)
├── kinds/
│   └── mcp/
│       ├── index.tsx                      # MCP_KIND_UI 入口，由 kinds.ts 注册
│       ├── McpServersTable.tsx / McpServerDetailPage.tsx / McpServerDetailTabs.tsx
│       └── AddMcpServerDialog.tsx / CapabilityList.tsx / InvocationsTable.tsx / …
└── pages/
    ├── ResourcesPage.tsx                  # /mcp-servers — kind-agnostic 分派 (/resources 重定向到这里)
    ├── ResourceDetailPage.tsx             # /mcp-servers/:kind/:name
    ├── AgentsPage.tsx / AgentDetailPage.tsx     # /agents、/agents/:name
    ├── SkillsPage.tsx / SkillDetailPage.tsx     # /skills、/skills/:name
    ├── audit/AuditLogPage.tsx             # /audit — 审计日志视图（/observability 重定向到这里）
    └── settings/                          # SettingsLayout + GeneralSettings、DataSettings、AppSettings、AboutPage

frontend/
├── vite.config.ts                         # dev 专用的 token 注入插件 (读 daemon.json)
├── tailwind.config.js                     # 视觉语言 token（详见 agents/ui-shell/visual-language.md）
└── components.json                        # shadcn 配置
```

### 扩展点：kind 注册表

`frontend/src/lib/components/kindRegistry.ts` 暴露 `registerKindUI`；每个 kind
在 `frontend/src/kinds/<kind>/` 下提供一个自包含的 UI 模块，其 `index.tsx`
导出该 kind 的展示名、侧栏图标以及列表/详情组件。组装入口
`frontend/src/kinds.ts` import 每个模块并注册；kind-agnostic 的
`ResourcesPage` 通过查注册表来分派——共享代码里没有任何按 kind 分支的逻辑。
新增一个 kind 时各自加一份模块，并在 `kinds.ts` 里加一行 import +
`registerKindUI` 调用即可，其它共享文件不需改。

这是后端 `KindModule` 组合模式（[ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)、[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)）在 UI 侧的镜像。

### 视觉语言

Tailwind 配置 (`frontend/tailwind.config.js`) 是 spacing、typography、color token 的唯一事实来源。详情与添加新界面时 agent 应遵循的约定见 [`agents/ui-shell/visual-language.md`](../../agents/ui-shell/visual-language.md)。

### 国际化

`react-i18next` 配两套词条 (`locales/en/*.json`、`locales/zh/*.json`)。所选语言以 `coffer.language` 为 key 存在 localStorage；切换器挂在侧栏，从任意界面都能到达。切换在下一次渲染内生效——不整页刷新——见 language-switcher acceptance scenario。

## Phases (high-level)

Phases 是**交付边界**，不是原子任务拆分。它们对应 [spec.md](./spec.md) 中的 user story 优先级。

### Phase 1 — 视觉语言 + AppShell（基础）

Tailwind 配置 (`frontend/tailwind.config.js`)、shadcn primitives、`AppShell`（侧栏 + 主内容）、`Sidebar` / `SidebarGroup`、语言切换器、`DaemonOfflineBanner`、i18n 词条、openapi-fetch 客户端，以及 dev 专用 token 注入插件。

**Done when:** AppShell 能跑在已运行的 daemon 之上，侧栏收起 + 恢复从 localStorage 起作用，语言切换在 English ↔ 中文 之间来回切换正常，daemon 不可达时 banner 自动出现。

### Phase 2 — US1：首次访问流

`/mcp-servers` 在没有资源时的欢迎视图（以及 index 落地的 `/agents` Agents 欢迎视图）、带「重新加载」恢复操作（桌面应用为「重启」）的"Daemon not running"视图，以及通过 dev token 插件实现的冷启动自动鉴权渲染。

**Done when:** US1 的三个 representative scenarios 通过。

### Phase 3 — US2：MCP 日常流

`AddMcpServerDialog`（JSON 导入、secret env review 步骤、register-first-then-credential 顺序——见 spec scenario）、重设计的服务器列表（搜索 / 状态过滤 / 分页）、服务器详情页（Overview / Tools / Resources / Prompts / Invocations tabs，其中 invocation 行可展开为它的原始日志 JSON）、能力开关，以及重设计的空 / 错误 / 加载态。

**Done when:** US2 的 representative scenarios 通过，MCP 流程的 `make verify-e2e` 绿。

### Phase 4 — US3：审计日志

`/audit` 路由 + 审计日志视图（filter bar、分页表格、行展开为它的原始日志 JSON——与 invocation 日志共用的 `RawLog` 视图），legacy `/observability` → `/audit` 重定向。（Observability——系统健康 / 指标——是一个独立的未来界面，不是这个审计日志视图。）

**Done when:** US3 的 representative scenarios 通过。

### Phase 5 — US4：Settings 重组

Settings tabs 侧栏、`DataSettings` (retention + prune + backup)、`AboutSettings`，删除 Shutdown / Rotate-token / Daemon-status / 重复语言选择器 / kind 列表等控件。

**Done when:** US4 的 representative scenarios 通过。

### Phase 6 — 抛光 + verify

Acceptance 审计、`make verify`、`make verify-e2e`、跨浏览器手动冒烟、语言 QA pass。

**Done when:** spec 002 的 `audit_acceptance: OK`，CI 绿。

## Complexity Tracking

| 决策                                                    | 为什么需要                                                                                           | 拒绝更简单方案的原因                                                                                                               |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Tailwind + shadcn 取代裸 CSS                            | 视觉语言一致性是本 spec 的头号目标；ad-hoc CSS 恰是 US2 反对的"像脚手架"状态。                       | 裸 CSS 会让每个组件重新讨论 spacing / typography / color；shadcn 给我们一组被审计过的 Radix 基础件，又不带笨重的 UI 框架。         |
| TanStack Query 取代原生 fetch                           | 审计 / 调用 / 能力表格都需要 stale-while-revalidate 和切换后自动 refetch；自己重造一遍只会做得更差。 | 原生 fetch 会让每个页面手摇 loading / error / refetch 状态。                                                                       |
| Per-kind 注册表 (`kindRegistry.ts`)                     | 未来的 kind 接入时不动共享代码；与后端的 `KindModule` 模式镜像。                                     | 在 `ResourcesPage` 里写 `if (kind === "mcp_server") { … }` 分支，会随 kind 数线性膨胀，并在每个界面重新挑战 kind-agnostic 不变式。 |
| AddMcpServerDialog 中 register-first-then-credential 顺序 | 注册失败时避免遗留 orphan 凭据条目（实现阶段确定；见 spec scenario）。                              | credential-first 看起来对称，但注册失败时会留死的凭据条目；清理 orphan 比重试注册更难。                                            |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Quickstart: [quickstart.md](./quickstart.md)
- IA 决策: [ADR-007](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md)
- Resource 框架: [ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)
- 后端契约（消费，不持有）: [`specs/001-mcp-gateway/contracts/api.openapi.yaml`](../001-mcp-gateway/contracts/api.openapi.yaml)
- 后端数据模型（消费，不持有）: [`specs/001-mcp-gateway/data-model.md`](../001-mcp-gateway/data-model.md)
- 视觉语言参考: [`agents/ui-shell/visual-language.md`](../../agents/ui-shell/visual-language.md)
- 架构概览: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- 章程: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
