# 持久化

::: tip 核心锚点
所有 Coffer 状态都驻留在用户本机。daemon 是唯一的数据库写入者。恢复一个可工作的安装所需的一切——数据库、daemon 配置、日志、上游状态——都位于同一个目录：`~/.coffer/`。
:::

## 这解决了什么问题

Coffer 是一个本地优先的开发者工具：用户沉淀下来的 AI 资产——已注册的 MCP 服务器、能力偏好、审计历史——必须在不依赖任何云服务的情况下可读可写。这个约束要求持久化层必须是自包含的、零配置的，并且可以简单地备份。

答案是 SQLite。`~/.coffer/coffer.db` 中的单个文件是所有控制面状态的事实记录方 (system of record)。不需要安装独立的数据库服务进程，不需要调优连接池，daemon 与存储之间也没有网络跳转。用户的数据就是他们的文件。

## 为什么选择 SQLite 而非 Postgres

被否决的方案——Postgres 或 MySQL 这类服务端数据库——需要用户安装并管理一个数据库进程、配置凭据、并保持一个服务持续运行。对于单用户本地工具来说，这些开销纯粹是没有任何收益的摩擦成本。

::: tip 章程不变量
章程将 SQLite 指定为控制面状态的事实记录方。批量用户内容（按规范引入时）以文件形式存放于本地文件系统，按需建立索引。将控制面迁移到服务端数据库需要走章程修订流程。
:::

SQLite 选择的实际后果塑造了持久化层的每一个细节：

- **单写入者** — SQLite 的写并发有限；由一个写入者（daemon）负责，从设计上消除了所有写冲突。daemon 序列化每一次变更；需要写入的接口面（CLI 命令、HTTP handler）都通过 loopback HTTP 经由 daemon 进行。
- **WAL 模式** — Write-Ahead Logging 允许读取者（例如调用 REST API 的 `coffer mcp list` 命令）与写入者并发执行，而不会被锁阻塞。实际效果是 `coffer mcp list` 不会因等待正在进行的迁移而挂起。
- **零基础设施备份** — 由于所有 Coffer 状态都在 `~/.coffer/` 下，一条简单的 `cp -r ~/.coffer/ <destination>` 命令就能生成一份自包含的备份。daemon 提供 `/api/v1/daemon/backup` 端点，通过 SQLite 的在线备份 API 将一致性快照写入 `~/.coffer/backups/`，同时 daemon 继续提供服务。

## SQLAlchemy 2.0 异步 ORM

数据访问层使用 SQLAlchemy 2.0 的异步模式（`AsyncSession`、由 `aiosqlite` 驱动的 `create_async_engine`）。这与 FastAPI daemon 的异步 I/O 模型相匹配：请求 handler 以 `await` 等待数据库查询，而不阻塞事件循环，使 daemon 能够响应并发的 MCP 客户端连接。

所有 kind 的所有 ORM 模型——包括与 kind 无关的核心表以及 MCP 特定的表——都注册在**同一份中央 `Base.metadata`** 对象上。这正是让 Alembic 迁移变得简单的架构决策：只有一个迁移历史，一条 `alembic upgrade head` 命令，不需要在多个 kind 的迁移树之间进行协调。

ORM 与领域层之间的边界是显式的。每个 ORM 模型提供：

- `to_domain() → <DomainEntity>` — 将 ORM 行转换为纯 Python 领域对象（不携带 SQLAlchemy 状态）。
- `from_domain(entity) → <Model>` — 从领域对象创建 ORM 实例，可直接添加到会话中。

领域对象是普通的 Python dataclass，不携带任何 SQLAlchemy 插桩。应用层服务只与领域对象打交道；ORM 模型是基础设施层的实现细节。

## JSON 字段与 Pydantic 校验

kind 特定的配置以 `TEXT` 列（`resources` 表中的 `config_json`）存储。SQLite 没有原生的 JSON 类型；将任意结构化的配置存为文本，是 SQLite 能处理的最简单表示方式。

这个权衡在于数据库本身无法对 `TEXT` 列强制执行结构约束——对 SQLite 来说，字符串 `"garbage"` 和格式良好的 JSON 对象同样合法。保证来自 application 层边界：**Pydantic 在每次写入前和读取后都会校验 `Resource.config`**。领域层的 `Kind.config_schema` 是一个 Pydantic `BaseModel` 子类；应用层服务对每一个传入的 config dict 调用 `.model_validate()`，在写入前调用 `.model_dump(mode="json")`。未经验证的数据永远不会到达 SQLite，从 SQLite 读出的数据也都会经过 Pydantic 重新验证。

::: warning 序列化注意事项
使用了 `AnyUrl` 或 `datetime` 等类型的 Pydantic 字段，在传给 `json.dumps()` 之前必须使用 `model_dump(mode="json")` 进行序列化。默认的 `model_dump()` 会将这些类型保留为 Python 对象，而 `json.dumps` 无法处理它们。这是一条强制约定，而非可选的风格选择。
:::

## Alembic 迁移

Schema 演化由 Alembic 管理，配置文件为 `backend/alembic.ini`，迁移历史位于 `backend/coffer/infrastructure/persistence/migrations/` 下的单一迁移序列。Spec 001 随附四个修订版本（三个建表修订版本加一个审计索引）：

| 修订版本 | 文件                                 | 创建内容                                        |
| -------- | ------------------------------------ | ----------------------------------------------- |
| `0001`   | `20260520_0001_initial.py`           | `resources`、`audit_log`、`retention_policies`  |
| `0002`   | `20260521_0002_mcp_tables.py`        | `mcp_capability_preferences`、`mcp_invocations` |
| `0003`   | `20260522_0003_mcp_server_health.py` | `mcp_server_health`                             |

在 daemon 首次启动时，`alembic upgrade head` 会在 HTTP 服务开始接受连接之前运行。由于 Alembic 迁移作为数据文件被打包进 PyInstaller daemon 二进制文件，最终用户的安装在首次启动时也能正确创建 schema，无需单独的迁移步骤。

## 数据库表概览

应用所有四个修订版本后存在的六张表，按用途分组：

| 数据表                       | 用途                                                                                                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `resources`                  | 所有用户管理资源的与 kind 无关的注册表。每个已注册的 MCP 服务器（或未来的其他 kind）对应一行。包含 `kind`、`name`、`config_json`、`enabled` 标志和时间戳。 |
| `audit_log`                  | 所有资源或能力生命周期变更的仅追加历史记录。记录事件类型、actor、resource ref、时间戳和结构化 JSON payload。                                               |
| `retention_policies`         | 每个可剪裁表对应一行，记录配置的保留窗口（天数或永久保留）以及最近一次剪裁的元数据。                                                                       |
| `mcp_capability_preferences` | 持久化用户对每个已注册 MCP 服务器的逐能力启用/禁用决策。在上游重启和 schema 变更后依然有效。resource 删除时级联删除。                                      |
| `mcp_invocations`            | 网关中每次工具、资源和提示词调用的时序日志：服务器名称、能力键、耗时、状态、会话 ID。永远不存储参数或返回内容。                                            |
| `mcp_server_health`          | 每个已注册 MCP 服务器的最新健康状态（`healthy` / `failing` / `unknown`），在每次健康检查时写入。                                                           |

## 级联与完整性规则

Schema 强制执行了几条仅靠应用层无法表达的不变量：

- 删除资源会级联删除 `mcp_capability_preferences`（通过 `ON DELETE CASCADE`）。但**不会**级联删除 `audit_log` 或 `mcp_invocations`——即使服务器被删除，历史记录也会被保留。
- `kind` 和 `name` 一旦写入就不可变。应用层永远不会发出 `UPDATE resources SET kind=?` 或 `UPDATE resources SET name=?`。重命名意味着先删除再重新注册。
- `retention_policies` 中的行在 daemon 启动时进行 upsert，永不删除。应用层将其视为始终存在的配置。

## `~/.coffer/` 下的所有文件

Coffer 写入的完整文件集合：

| 路径                       | 内容                                             |
| -------------------------- | ------------------------------------------------ |
| `~/.coffer/coffer.db`      | SQLite 数据库（WAL 模式）——事实记录方            |
| `~/.coffer/daemon.json`    | Daemon PID、端口和 bearer token（权限位 `0600`） |
| `~/.coffer/logs/`          | `structlog` 输出的结构化 JSON 日志文件           |
| `~/.coffer/bin/`           | 由桌面应用部署的 `coffer-mcp-shim` 二进制文件    |
| `~/.coffer/backups/`       | 按时间点的 SQLite 备份副本                       |
| `~/.coffer/upstream-pids/` | 用于会话追踪的每个上游子进程的 PID 文件          |

将所有文件统一置于一个父目录下，使备份变得简单，迁移路径清晰，彻底卸载也能做到完整。daemon 的检测-或-拉起协议（ADR-006）也因此受益：每一个需要查找 daemon 的进程都读取 `~/.coffer/daemon.json`——没有注册表，没有环境变量，也不需要探测任何平台特定的服务目录。

## 保留策略默认值

daemon 启动时的 `RetentionService.initialize_defaults()` 调用会在 `retention_policies` 表行不存在时进行初始化。这些种子值在组装入口 (composition root) 定义，而非在迁移文件中，这样后续规范引入的新可剪裁表无需新的迁移修订即可注册各自的默认值：

| 数据表            | 默认保留期 |
| ----------------- | ---------- |
| `audit_log`       | 365 天     |
| `mcp_invocations` | 30 天      |

两者均可通过 `PATCH /api/v1/retention/{table_name}` 或等效的 CLI 命令由用户修改；变更本身会被审计。

## 另请参阅

- [数据模型参考](/zh/reference/specs/001-mcp-gateway/data-model) — 完整 DDL、ORM 映射表、级联规则和默认种子值
- [架构参考](/zh/reference/project/architecture) — 持久化章节和完整的跨层关注点表
