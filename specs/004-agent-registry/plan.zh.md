# 实施计划：004 —— Agent Registry

> English: [plan.md](./plan.md)

**Feature Branch**: `feature/004-agent-registry`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## 摘要

向 Coffer 加入 `agent` 这一 Resource kind：本地安装 AI agent（Claude Code、Claude Desktop、Cursor、Codex CLI）的 registry。首次启动时由自动检测填充，用户可手工添加、编辑、移除 agent。该 kind 暴露一个 `on_delete` 钩子，由 spec 005 接入用于 skill binding 的级联清理。同时交付 REST 路由、CLI 子命令与桌面 Agents 页面。

本 spec 是 spec 001 中引入的 kind-agnostic Resource 框架的第二个消费者，用以验证该框架的可复用性。

## 技术上下文

| 维度             | 取值                                                                          |
| ---------------- | ----------------------------------------------------------------------------- |
| **语言 / 版本**  | Python 3.12+，TypeScript 5.x                                                  |
| **新运行时依赖** | 无（在 spec 001 已有依赖基础上不新增包）。                                    |
| **存储**         | SQLite，位于 `~/.coffer/coffer.db`。新增一张表：`suppressed_agent_types`。    |
| **测试**         | 4 层（unit / integration / contract / e2e）；acceptance 标记绑定到 scenario。 |
| **目标平台**     | macOS arm64+x64、Windows x64、Linux x64+arm64                                 |
| **性能目标**     | 冷启动自动检测 ≤ 200 ms。CRUD 单次操作 ≤ 50 ms。                              |
| **约束**         | local-first，仅 127.0.0.1；保留分层架构；不引入新的凭据存储。                 |
| **规模**         | 每个用户 ≤ 8 个已注册 agent。                                                 |

## Constitution 检查

| 条款                             | 合规 | 说明                                                                                 |
| -------------------------------- | ---- | ------------------------------------------------------------------------------------ |
| I. Local-First（NON-NEGOTIABLE） | ✅   | 纯本地 registry；无网络调用。                                                        |
| II. Spec-as-Truth                | ✅   | 本计划实现 `spec.md`；spec 先于代码提交。                                            |
| III. Open-Source-Readiness       | ✅   | 不新增闭源依赖。                                                                     |
| 语言                             | ✅   | 仅 Python + TypeScript。                                                             |
| 架构：分层                       | ✅   | 新代码遵循 `surfaces → application → domain → infrastructure`；domain 不依赖 infra。 |
| 持久化：控制面用 SQLite          | ✅   | Registry 在 SQLite 中。                                                              |
| 凭据                             | ✅   | 无。                                                                                 |
| 网络默认                         | ✅   | 仅 loopback HTTP。自动检测只读本地文件系统。                                         |

## 项目结构

### 文档

```
specs/004-agent-registry/
  spec.md
  plan.md              (本文件)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### 新增后端模块

```
backend/coffer/domain/agent/
  __init__.py
  types.py             # AgentType StrEnum + 默认路径 + 检测标记
  config.py            # AgentConfig (Pydantic)

backend/coffer/application/agent/
  __init__.py
  service.py           # AgentService (register/update/remove)
  auto_detect.py       # AutoDetectService (扫描标记、抑制列表)
  kind.py              # make_agent_kind(on_delete_hook) -> Kind

backend/coffer/infrastructure/agent/
  __init__.py
  repos.py             # SuppressedAgentTypeRepo (小型 SQLAlchemy repo)

backend/coffer/infrastructure/persistence/migrations/versions/
  20260525_0005_agent_tables.py   # suppressed_agent_types

backend/coffer/surfaces/http/agent_routes.py    # POST /agents, GET /agents, PATCH /agents/{name}, DELETE /agents/{name}, POST /agents/detect
backend/coffer/surfaces/cli/agent.py            # coffer agent {add, list, edit, rm, detect}
```

### 新增前端模块

```
frontend/src/pages/agents/
  agents-page.tsx
  agent-form.tsx           # 增/改
  agent-row.tsx
frontend/src/api/agents.ts
frontend/src/i18n/{en,zh}/agents.json
```

## 阶段

### Phase 0 —— Research（已在对话中关闭）

- 备选方案：在 Resource 框架之外另设独立 `agents` 表 → 否决（丧失 audit/CRUD/UI 统一性；agent-as-peer 也没有未来扩展空间）。
- 备选方案：把 agent 合入 spec 005 → 重新评估后否决（按 spec 体量切分更清晰；一份 PR 同时交付两者）。
- 自动检测启发式：检查已知标记目录（即 `default_skill_dir` 的父目录）是否存在。后续 spec 可能加入「PATH 上有命令」类型的检测。

### Phase 1 —— Data model + contracts

- 撰写 data-model.md（已完成）与 contracts/api.openapi.yaml（已完成）。
- 实现 Alembic 迁移 `20260525_0005_agent_tables.py`（创建 `suppressed_agent_types`）。
- 在 domain 中定义 `AgentType`、`AgentConfig` 与 audit event 值。

### Phase 2 —— 后端实现

1. Domain：`agent/types.py`、`agent/config.py`。为按平台默认路径解析与 skill_dir 校验添加单元测试。
2. Infrastructure：`SuppressedAgentTypeRepo`。配合真实 SQLite 写集成测试。
3. Application：`AgentService`（CRUD + 抑制集成）、`AutoDetectService`（扫描 + 注册）、`make_agent_kind`。
4. Surfaces：`agent_routes.py`（HTTP）、`agent.py`（CLI）、composition root 接线。
5. 在 agent `Kind` 上暴露 `on_delete` 钩子。spec 005-skill-manager（PR #21）提供真正的 `cleanup_bindings_for_agent` 回调；PR #25 只交付钩子的接口位（seam）。

### Phase 3 —— 测试

- 单元：按平台测 `AgentType.default_skill_dir()`（mock）；`AgentConfig` Pydantic 边界场景。
- 集成：register/update/remove 循环；移除自动检测 agent 后的抑制；重新注册解除抑制；二次启动的自动检测幂等。
- Contract：OpenAPI 快照测试；CLI `--json` 输出稳定。
- E2E：从 CLI 跑 `coffer agent add cursor` → 在 `coffer agent list --json` 中看到 → 桌面端同步反映。
- `spec.md` 中每一个 acceptance scenario 至少被一个带 `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")` 的测试覆盖。

### Phase 4 —— 前端

- 用 TanStack Query + openapi-fetch（现有技术栈）实现 `AgentsPage` React 页面。
- Add/edit 表单做表单级校验，与 `AgentConfig` 的 Pydantic schema 对齐。
- 移除时弹出确认对话框。
- 英文 + 简体中文 i18n 字符串（延续 001 的双语策略）。

## 风险 / 未知

- **Windows 路径处理**对 `Claude Desktop`：`%APPDATA%` 在不同版本之间的语义有细微差异；需要在 Windows CI 矩阵中测试。
- **首启动自动检测与用户 CRUD 的竞态**：用一个 startup-phase 锁串行化；CRUD endpoint 阻塞直到 lifespan 完成检测。

## 延期至后续 spec 的开放项

- agent **类型**扩展超出 v1 的四种（如 Gemini CLI、GitHub Copilot）—— 增加一个 enum 值和该类型对应的扫描器。
- agent **健康检查**（注册路径上的安装是否仍存在）—— 单独 spec。
- agent **作为 MCP peer**（把另一个 agent 通过 Coffer MCP 网关暴露为可调用工具）—— 探索性。
