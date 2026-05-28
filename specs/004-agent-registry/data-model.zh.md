# Data Model —— 004 Agent Registry

> English: [data-model.md](./data-model.md)

agent registry 的实体、字段、关系与 SQLite schema 增量。建立在 spec 001 引入的 kind-agnostic Resource 框架之上。

## Domain 实体 (`backend/coffer/domain/agent/`)

### `AgentType` (`domain/agent/types.py`)

字符串值的 enum（`StrEnum`）。

| 值               | 显示名           | 默认 `skill_dir`（POSIX 展开）                                                                                             |
| ---------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `claude_code`    | Claude Code      | `~/.claude/skills`                                                                                                         |
| `claude_desktop` | Claude Desktop   | macOS: `~/Library/Application Support/Claude/skills`；Linux: `~/.config/Claude/skills`；Windows: `%APPDATA%/Claude/skills` |
| `cursor`         | Cursor           | `~/.cursor/skills`                                                                                                         |
| `codex_cli`      | OpenAI Codex CLI | `~/.codex/skills`                                                                                                          |

每个 enum 值携带：

- `display_name: str`
- `default_skill_dir() -> Path`（按宿主平台计算）
- `detect_marker() -> Path`（自动检测时检查的路径；通常是 `default_skill_dir` 的父目录）

### `AgentConfig` (`domain/agent/config.py`)

Pydantic v2 `BaseModel`。注册给 `ResourceService` 的 kind 专属 config schema。

| 字段            | 类型           | 说明                                                      |
| --------------- | -------------- | --------------------------------------------------------- |
| `type`          | `AgentType`    | 必填；enum 值                                             |
| `skill_dir`     | `Path \| None` | 可选覆盖；读取时若为空则回退到 `type.default_skill_dir()` |
| `auto_detected` | `bool`         | 来源标志；默认 `False`                                    |

校验器：

- `skill_dir`（若设置）必须解析为一个存在、可写的目录。
- `skill_dir` 不得指向 `/etc`、`/usr`、`/bin`、`/sbin`、`/System`（POSIX）或 `C:\Windows`、`C:\Program Files`（Windows）。
- `model_config = ConfigDict(extra="forbid")`，未知字段被拒绝。

## SQLite schema 增量

迁移 `20260525_0005_agent_tables.py` 新增：

### `suppressed_agent_types`

一张小表，记录用户在自动检测之后移除掉的 agent 类型，使后续扫描不再重建它们。

| 列              | 类型        | 约束               |
| --------------- | ----------- | ------------------ |
| `agent_type`    | `text`      | 主键；每种类型一行 |
| `suppressed_at` | `timestamp` | UTC，insert 时设置 |

不与 `resources` 建立外键关系。用户再次注册某个已抑制类型的 agent 时解除抑制（注册时删除该行）。

### 已有表的复用

- `resources`：新增 `kind='agent'` 的行。无 schema 变化。
- `audit_log`：新增 event 类型（见下）。无 schema 变化。

## 新增 audit event 类型

向 `AuditEventType` (`domain/audit.py`) 添加 —— 只新增两个无 kind-agnostic 对应的 agent 专属事件：

| 值                      | 触发时机                                                                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| `agent_auto_registered` | daemon 启动时自动检测注册了一个新 agent                                                        |
| `agent_type_suppressed` | 内部使用：与移除一个自动检测 agent 的 resource 删除事件成对，记录被加入抑制列表的 `agent_type` |

FR-011 要求的其他生命周期步骤 —— 手工注册、更新、启用、禁用、移除 —— 沿用已有的 kind-agnostic `resource_created`、`resource_updated`、`resource_enabled`、`resource_disabled`、`resource_removed` 事件（每一条都携带受影响的 `agent:<name>` 引用）。这些步骤**不**额外再发一份 `agent_*` 副本；surface 端通过 `kind='agent'` + 上述 kind-agnostic event type 过滤。

## Application service 契约 (`backend/coffer/application/agent/`)

### `AgentService`

| 方法                                                                        | 用途                                                                                                       |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `register(type, name, skill_dir=None, description=None, actor) -> Resource` | 校验后委托给 `ResourceService.register(kind='agent', ...)`。若该 `type` 存在抑制行，注册时删除。           |
| `update_skill_dir(ref, new_path, actor) -> Resource`                        | 委托给 `ResourceService.update_config`。                                                                   |
| `list() -> list[Resource]`                                                  | 委托给 `ResourceService.list(kind='agent')`。                                                              |
| `remove(ref, actor) -> None`                                                | 若 `config.auto_detected=True`，在调用 `ResourceService.delete` 之前向 `suppressed_agent_types` 插入一行。 |

### `AutoDetectService`

| 方法                                         | 用途                                                                                                                                                                                                                                            |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run_once(actor='system') -> list[Resource]` | 扫描每个 `AgentType` 的安装标记；对每一个既不在 `resources` 也不在 `suppressed_agent_types` 中的类型，注册一个带 `auto_detected=True` 的 agent。返回新注册的 agent 列表。在 daemon 启动时调用一次（也通过 `POST /api/v1/agents/detect` 暴露）。 |

## Kind 接线 (`backend/coffer/application/agent/kind.py`)

`make_agent_kind(...)` 返回一个 `Kind`：

- `name='agent'`
- `display_name='Agent'`
- `config_schema=AgentConfig`
- `on_delete=...` —— 由 `ResourceService.delete` 调用的级联钩子，用于触发**skill 侧**的 binding 清理（callback 由 skill 模块提供；agent kind 不直接 import skill 模块，而是通过 composition root 在 kind 模块上的 setter 注入）。

## Composition root 接线

在 `surfaces/http/app.py` 中新增一个 helper `_wire_agent_kind(app, resource_svc, audit, sm)`（与 `_wire_mcp_kind` 对应）：

1. 构造 `AgentService` + `AutoDetectService`。
2. 通过 `make_agent_kind(on_delete_hook)` 构造 `Kind`。
3. 注册到 `app.state.kinds['agent']`。
4. 挂载 `agent_routes` 与 `agent_detect_routes`。
5. 在启动 lifespan 中调用一次 `AutoDetectService.run_once(actor='system')`。

`on_delete_hook` 绑定一个由 skill 模块（spec 005）提供的 callable，从而在 resource 行被删除之前同步触发 `SkillService.cleanup_bindings_for_agent(...)` —— 一旦 spec 005 接线到位。spec 004 只暴露钩子接口位；PR #25 在 spec 005 提供 callable 之前把它保持为 no-op。

## 约束摘要

- 所有 HTTP 路由绑定 `127.0.0.1`，共享 `X-Coffer-Token` 鉴权（按 spec 001）。
- 不新增 keychain 条目 —— `agent` config 没有凭据。
- spec 004 单独执行时不向 `~/.coffer/` 之外写入任何文件内容；spec 005 可能向 agent 的 `skill_dir` 写入。
