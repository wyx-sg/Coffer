# Data Model — 001 MCP Gateway

> English: [data-model.md](./data-model.md)

实体、字段、关系，以及 MCP 网关的 SQLite schema。ORM 模型严格按照这里的命名；OpenAPI schema 字段名与之一致。迁移按三次 Alembic revision 拆分：

| Revision | File                                 | What it creates                                 |
| -------- | ------------------------------------ | ----------------------------------------------- |
| `0001`   | `20260520_0001_initial.py`           | `resources`、`audit_log`、`retention_policies`  |
| `0002`   | `20260521_0002_mcp_tables.py`        | `mcp_capability_preferences`、`mcp_invocations` |
| `0003`   | `20260522_0003_mcp_server_health.py` | `mcp_server_health`                             |

## Domain entities (`backend/coffer/domain/`)

### `ResourceRef` (`domain/resource.py`)

frozen dataclass / Pydantic 值对象。Resource 的对外标识符。

| Field  | Type  | Notes                                                  |
| ------ | ----- | ------------------------------------------------------ |
| `kind` | `str` | 与已注册 `Kind.name` 一致，例如 `"mcp_server"`         |
| `name` | `str` | 同 kind 内唯一；匹配 `^[a-zA-Z0-9_.-]+$`；最长 64 字符 |

行为：

- `__str__` → `f"{kind}:{name}"`
- `ResourceRef.parse("mcp_server:filesystem")` → `ResourceRef(kind="mcp_server", name="filesystem")`
- `parse` 在输入缺少唯一的 `:` 分隔符或任一边为空时抛 `ValueError`
- `frozen=True` 隐含 equality 与 hashing

### `Resource` (`domain/resource.py`)

普通 Python dataclass；**不是** Pydantic 模型（domain 保持纯净）。

| Field         | Type             | Notes                                              |
| ------------- | ---------------- | -------------------------------------------------- |
| `id`          | `int`            | DB 代理主键；内部使用，对外永不序列化              |
| `kind`        | `str`            | 与 `Kind.name` 一致                                |
| `name`        | `str`            | 同 kind 内唯一                                     |
| `description` | `str \| None`    | 可选自由文本                                       |
| `config`      | `dict[str, Any]` | kind 特定配置，已按 kind 的 `config_schema` 校验过 |
| `enabled`     | `bool`           | 用户控制的启用/禁用开关                            |
| `created_at`  | `datetime`       | UTC，插入时设置，永不更新                          |
| `updated_at`  | `datetime`       | UTC，每次变更都更新                                |

派生：`Resource.ref` 返回 `ResourceRef(self.kind, self.name)`。

### `Kind` (`domain/resource.py`)

frozen dataclass。一个资源 kind 的纯描述符。只属于 domain——不持有 router、service 或任何框架层适配器的引用。

| Field           | Type                                    | Notes                                         |
| --------------- | --------------------------------------- | --------------------------------------------- |
| `name`          | `str`                                   | 进程内唯一，例如 `"mcp_server"`               |
| `display_name`  | `str`                                   | UI 标签                                       |
| `config_schema` | `type[pydantic.BaseModel]`              | 用于校验 `Resource.config` 的 Pydantic schema |
| `on_delete`     | `Callable[[ResourceRef], None] \| None` | 可选的同步清理 hook；抛异常即中止 delete      |

### `AuditEntry` (`domain/audit.py`)

普通 dataclass。

| Field           | Type             | Notes                                  |
| --------------- | ---------------- | -------------------------------------- |
| `id`            | `int \| None`    | DB 代理主键，插入前为 `None`           |
| `timestamp`     | `datetime`       | UTC，默认 `utcnow()`                   |
| `event_type`    | `str`            | 见下文 `AuditEventType` 枚举字符串之一 |
| `resource_kind` | `str \| None`    | 可空；daemon 生命周期事件没有 resource |
| `resource_name` | `str \| None`    | 可空；daemon 生命周期事件没有 resource |
| `actor`         | `str`            | `"cli" \| "api" \| "ui" \| "system"`   |
| `details`       | `dict[str, Any]` | 可 JSON 序列化的载荷                   |

### `AuditEventType` (`domain/audit.py`)

字符串值枚举（使用 `StrEnum`）：

| Value                     | When emitted                                     |
| ------------------------- | ------------------------------------------------ |
| `"resource_created"`      | `ResourceService.register` 之后                  |
| `"resource_updated"`      | config 或 description 变更之后                   |
| `"resource_enabled"`      | `set_enabled(True)` 之后且状态确实翻转           |
| `"resource_disabled"`     | `set_enabled(False)` 之后且状态确实翻转          |
| `"resource_deleted"`      | `delete` 之后（`details` 含 pre-delete 快照）    |
| `"capability_first_seen"` | discovery 首次看到一个 capability                |
| `"capability_enabled"`    | 用户启用了原本禁用的 capability                  |
| `"capability_disabled"`   | 用户禁用了一个 capability                        |
| `"daemon_started"`        | daemon 启动并进入 ready 后                       |
| `"daemon_stopped"`        | daemon 优雅关闭时                                |
| `"token_rotated"`         | `POST /api/v1/daemon/rotate-token` 之后          |
| `"retention_updated"`     | retention policy 变更时                          |
| `"backup_created"`        | `POST /api/v1/daemon/backup` 之后                |
| `"credential_set"`        | `POST /api/v1/credentials` 存储 secret 之后      |
| `"credential_read"`       | `GET /api/v1/credentials/{ref}` 读取 secret 之后 |
| `"credential_deleted"`    | `DELETE /api/v1/credentials/{ref}` 删除 secret 之后 |
| `"credential_migrated"`   | 每个 ref：legacy 钥匙串密钥迁入存储时            |
| `"master_key_relocated"`  | `PUT /api/v1/settings/credentials` 迁移主密钥之后 |
| `"keychain_set"` / `"keychain_read"` / `"keychain_deleted"` | _Legacy_（信封加密之前）；对历史记录仍可渲染 |

### `RetentionPolicy` (`domain/retention.py`)

普通 dataclass。

| Field              | Type               | Notes                                          |
| ------------------ | ------------------ | ---------------------------------------------- |
| `table_name`       | `str`              | 主键；必须与已注册的 `PrunableTable.name` 匹配 |
| `retention_days`   | `int \| None`      | `None` = keep forever；`>0` = 天数；禁止 `0`   |
| `last_pruned_at`   | `datetime \| None` | 上次成功 prune 时间                            |
| `last_pruned_rows` | `int`              | 上次 prune 删除的行数                          |
| `updated_at`       | `datetime`         | 上次 policy 变更时间                           |

### `PrunableTable` (`infrastructure/persistence/retention.py`)

这是 composition root 使用的**注册表项**——尽管类型住在 `infrastructure/`（它驱动 SQL 执行），这里仍为完整性列出。

| Field                    | Type          | Notes                                       |
| ------------------------ | ------------- | ------------------------------------------- |
| `name`                   | `str`         | DB 表名；必须出现在 SQL 白名单集合中        |
| `timestamp_column`       | `str`         | 与 cutoff 比较的列名；必须出现在列白名单中  |
| `default_retention_days` | `int \| None` | 首次 daemon 启动时种入 `retention_policies` |
| `display_name`           | `str`         | UI 标签                                     |
| `description`            | `str`         | UI tooltip                                  |

## MCP kind value objects (`backend/coffer/domain/mcp/`)

### `StdioTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`。Discriminator 值：`"stdio"`。

| Field             | Type               | Notes                                                      |
| ----------------- | ------------------ | ---------------------------------------------------------- |
| `type`            | `Literal["stdio"]` | discriminator                                              |
| `command`         | `str`              | 可执行文件，例如 `"npx"`                                   |
| `args`            | `list[str]`        | 默认 `[]`                                                  |
| `env`             | `dict[str, str]`   | 静态 env，绝不含 secret；若值长得像 token（按正则）即被拒  |
| `credential_refs` | `dict[str, str]`   | 把 `env_var_name → ref`（指向加密凭据存储）映射；在 spawn 时解析（解密） |
| `cwd`             | `str \| None`      | 可选工作目录                                               |

### `HttpTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`。Discriminator 值：`"http"`。

| Field             | Type               | Notes                                    |
| ----------------- | ------------------ | ---------------------------------------- |
| `type`            | `Literal["http"]`  | discriminator                            |
| `url`             | `pydantic.HttpUrl` | 上游 MCP HTTP/SSE 端点                   |
| `headers`         | `dict[str, str]`   | 静态 header；与 `env` 同样的 secret 正则 |
| `credential_refs` | `dict[str, str]`   | 把 `header_name → ref`（指向加密凭据存储）映射 |

### `MCPServerConfig` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`——这是 `mcp_server` 对应的 `Resource.config`。

| Field                          | Type                                                                      | Notes                                                 |
| ------------------------------ | ------------------------------------------------------------------------- | ----------------------------------------------------- |
| `transport`                    | `Annotated[StdioTransport \| HttpTransport, Field(discriminator="type")]` | tagged union                                          |
| `auto_enable_new_capabilities` | `bool`                                                                    | 默认 `True`                                           |
| `spawn_timeout_seconds`        | `int`                                                                     | 默认 `30`；范围 `5–120`                               |
| `request_timeout_seconds`      | `int`                                                                     | 默认 `120`；范围 `5–1800`；progress 到来时重置        |
| `idle_timeout_seconds`         | `int`                                                                     | 默认 `600`；范围 `60–86400`；空闲超过此值即 GC 子进程 |

### `MCPTool` / `MCPResource` / `MCPPrompt` (`domain/mcp/capability.py`)

Pydantic `BaseModel`。上游查询返回的实时表示；从不持久化（按 [ADR-004](../../docs/decisions/ADR-004-capability-state-model.md)）。

`MCPTool`：
| Field | Type |
|---|---|
| `name` | `str`（原始，无前缀） |
| `description` | `str \| None` |
| `input_schema` | `dict[str, Any]` (JSON schema) |

`MCPResource`：
| Field | Type |
|---|---|
| `uri` | `str`（原始） |
| `name` | `str \| None` |
| `description` | `str \| None` |
| `mime_type` | `str \| None` |

`MCPPrompt`：
| Field | Type |
|---|---|
| `name` | `str`（原始） |
| `description` | `str \| None` |
| `arguments` | `list[MCPPromptArgument]` |

### `MCPCapabilityPreference` (`domain/mcp/capability.py`)

| Field             | Type                                    | Notes                                             |
| ----------------- | --------------------------------------- | ------------------------------------------------- |
| `id`              | `int \| None`                           | DB 代理主键                                       |
| `resource_id`     | `int`                                   | FK 指向 `resources.id`                            |
| `capability_type` | `Literal["tool", "resource", "prompt"]` |                                                   |
| `capability_key`  | `str`                                   | 原始（无前缀）名称；resource 则是原始 URI         |
| `enabled`         | `bool`                                  | 默认依赖该服务器的 `auto_enable_new_capabilities` |
| `first_seen_at`   | `datetime`                              |                                                   |
| `last_seen_at`    | `datetime`                              | 每次发现成功都会更新                              |

### `MCPInvocation` (`domain/mcp/capability.py`)

| Field             | Type                                          | Notes                      |
| ----------------- | --------------------------------------------- | -------------------------- |
| `id`              | `int \| None`                                 | DB 代理主键                |
| `timestamp`       | `datetime`                                    |                            |
| `resource_name`   | `str`                                         | MCP 服务器名               |
| `capability_type` | `Literal["tool", "resource", "prompt"]`       |                            |
| `capability_key`  | `str`                                         | 原始（无前缀）名称         |
| `duration_ms`     | `int`                                         | wall-clock 毫秒            |
| `status`          | `Literal["ok", "error", "timeout", "denied"]` |                            |
| `error_message`   | `str \| None`                                 | 当 `status != "ok"` 时填充 |
| `session_id`      | `str \| None`                                 | 按会话的关联 id            |

**绝不存参数或返回值**——schema 中没有可承载它们的字段。

## SQLite schema（跨三次 Alembic revision）

表分散在三次迁移中创建；下面的 schema 是三次 revision 全部应用后的合并结果。

```sql
-- Resources: kind-agnostic core
CREATE TABLE resources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT      NOT NULL,
    name          TEXT      NOT NULL,
    description   TEXT,
    config_json   TEXT      NOT NULL,                       -- validated JSON
    enabled       BOOLEAN   NOT NULL DEFAULT 1,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (kind, name)
);
CREATE INDEX idx_resources_kind_enabled ON resources(kind, enabled);

-- Audit log: kind-agnostic
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type      TEXT      NOT NULL,
    resource_kind   TEXT,                                   -- nullable
    resource_name   TEXT,
    actor           TEXT      NOT NULL,
    details_json    TEXT                                    -- nullable JSON payload
);
CREATE INDEX idx_audit_resource  ON audit_log(resource_kind, resource_name, timestamp DESC);
CREATE INDEX idx_audit_time      ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_eventtype ON audit_log(event_type, timestamp DESC);

-- Retention policy: kind-agnostic
CREATE TABLE retention_policies (
    table_name        TEXT PRIMARY KEY,
    retention_days    INTEGER,                              -- NULL = forever; >0 = days
    last_pruned_at    TIMESTAMP,
    last_pruned_rows  INTEGER NOT NULL DEFAULT 0,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (retention_days IS NULL OR retention_days > 0)
);

-- MCP-specific: user's capability preferences
CREATE TABLE mcp_capability_preferences (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id      INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    capability_type  TEXT    NOT NULL,                      -- 'tool' | 'resource' | 'prompt'
    capability_key   TEXT    NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT 1,
    first_seen_at    TIMESTAMP NOT NULL,
    last_seen_at     TIMESTAMP NOT NULL,
    UNIQUE (resource_id, capability_type, capability_key)
);
CREATE INDEX idx_prefs_resource ON mcp_capability_preferences(resource_id, capability_type, enabled);

-- MCP-specific: invocation log
CREATE TABLE mcp_invocations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resource_name    TEXT      NOT NULL,
    capability_type  TEXT      NOT NULL,
    capability_key   TEXT      NOT NULL,
    duration_ms      INTEGER   NOT NULL,
    status           TEXT      NOT NULL,                    -- 'ok' | 'error' | 'timeout' | 'denied'
    error_message    TEXT,
    session_id       TEXT
);
CREATE INDEX idx_invocations_resource ON mcp_invocations(resource_name, timestamp DESC);
CREATE INDEX idx_invocations_time     ON mcp_invocations(timestamp DESC);
CREATE INDEX idx_invocations_session  ON mcp_invocations(session_id, timestamp);

-- MCP-specific: persisted upstream health (revision 0003)
CREATE TABLE mcp_server_health (
    resource_name  TEXT      PRIMARY KEY,
    status         TEXT      NOT NULL,                    -- 'healthy' | 'failing' | 'unknown'
    checked_at     TIMESTAMP NOT NULL
);
```

## SQLAlchemy mapping (summary)

ORM 模型存放于 `backend/coffer/infrastructure/persistence/models.py`（kind-agnostic）和 `backend/coffer/infrastructure/mcp/persistence.py`（MCP 专属），全部注册到同一份 `Base.metadata` 之下：

| ORM class                      | Table                        | Lives in                               |
| ------------------------------ | ---------------------------- | -------------------------------------- |
| `ResourceModel`                | `resources`                  | `infrastructure/persistence/models.py` |
| `AuditLogModel`                | `audit_log`                  | `infrastructure/persistence/models.py` |
| `RetentionPolicyModel`         | `retention_policies`         | `infrastructure/persistence/models.py` |
| `MCPCapabilityPreferenceModel` | `mcp_capability_preferences` | `infrastructure/mcp/persistence.py`    |
| `MCPInvocationModel`           | `mcp_invocations`            | `infrastructure/mcp/persistence.py`    |
| `McpServerHealthModel`         | `mcp_server_health`          | `infrastructure/mcp/persistence.py`    |

每个 ORM 模型提供：

- `to_domain() -> <DomainEntity>` 用于向外转换
- 模块级 `from_domain(entity) -> <Model>` helper 用于向内转换

## Cascade and integrity rules

| Action                             | Effect                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `DELETE FROM resources WHERE id=?` | 级联到 `mcp_capability_preferences`（通过 FK）。**不会**级联到 `audit_log` 或 `mcp_invocations`（保留历史）。 |
| `UPDATE resources SET kind=?`      | 禁止——application 层永不更新 `kind`。                                                                         |
| `UPDATE resources SET name=?`      | 禁止——rename = delete + register。                                                                            |
| `DELETE FROM retention_policies`   | 禁止——policy 在启动时 upsert，永不删除。                                                                      |

## Default retention policy seed (run on first daemon startup)

这些默认值在**组装入口** (`surfaces/http/app.py`，在 daemon 启动时调用
`RetentionService.initialize_defaults()`) 写入——**不**在 Alembic 迁移里
做。迁移只负责创建 `retention_policies` 表，留空；由 daemon 在启动时
upsert 每张表的默认值。这样未来 spec 新增可清理表 (prunable table) 时，
就能自行注册默认值，而无需再写一次迁移。

```python
defaults = [
    ("audit_log",         365),
    ("mcp_invocations",    30),
]
for table_name, days in defaults:
    if not exists(table_name):
        upsert(table_name=table_name, retention_days=days, updated_at=utcnow())
```

## API authentication

`/api/v1/*` 下的每条路由都要求 `X-Coffer-Token` header。唯一刻意豁免的是：

| Endpoint                    | 为什么免鉴权                                                                                                                                                                                                                      |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/daemon/status` | 被 CLI 与 `coffer-mcp-shim` 用作廉价的就绪探针，在还没从 `~/.coffer/daemon.json` 读到任何 token 之前调用。只返回生命周期阶段、版本、端口、started-at 以及一个聚合的 upstream 概要 —— 不含 secret、不含逐 resource 细节、不含审计数据。 |

所有改动型 endpoint（包括 `/daemon/backup`、`/daemon/rotate-token`、
`/daemon/shutdown`）都要求 token。`/mcp` JSON-RPC 面也要求 token。客户端
SHOULD 设置可选的 `X-Coffer-Actor` header（`cli` | `api` | `ui` | `system`），
使审计条目带上来源 surface；缺省时默认为 `"api"`。

## Invariants enforced by importlinter

下表重申了 `backend/pyproject.toml` 中已有的 `tool.importlinter.contracts`，外加本 spec setup 阶段要新增的两条契约（`Contract 5`、`Contract 6`）：

| Contract | Subject                                                                                                                                                                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1        | `surfaces → application → domain` 分层方向                                                                                                                                                                                                              |
| 2        | `infrastructure` 不导入 `surfaces`                                                                                                                                                                                                                      |
| 3        | `domain` 保持纯净（不引 infra/surfaces/sdk）                                                                                                                                                                                                            |
| 4        | `keyring` 仅限 infrastructure                                                                                                                                                                                                                           |
| **5**    | 禁止 cross-kind 导入：`coffer.{domain,application,infrastructure,surfaces}.mcp.*` 不导入 `coffer.{domain,application,infrastructure,surfaces}.<other_kind>.*`（目前只有一个 kind 时此契约空成立，但从第一天起就把规则立好，第二个 kind 落地时立即生效） |
| **6**    | kind-agnostic 核心不导入 kind 专属代码：`coffer.application.resource_service` 不导入 `coffer.domain.mcp` 或 `coffer.application.mcp`                                                                                                                    |

两条新契约在任务 `T-0010`（见 tasks.md）中添加。
