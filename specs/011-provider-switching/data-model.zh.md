# 数据模型——011 Provider Switching

> English: [data-model.md](./data-model.md)

provider 注册表的实体、字段与复用锚点。
依赖 spec 004 的 agent kind 和 spec 001 的 kind-agnostic Resource 框架。

## 域实体（`backend/coffer/domain/provider/`）

### `ProviderConfig`（`domain/provider/config.py`）

Pydantic v2 `BaseModel`。这是存储在 Resource 行上的同步 `config` 字典。**绝不**持有原始 secret。

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `wire_format` | `WireFormat` | 必填；`"anthropic"`、`"openai"` 或 `"ollama"`。`ollama` 仅供内部——从不投影到 agent。 |
| `base_url` | `str` | 必填（所有 wire）；上游 LLM endpoint URL。 |
| `credential_ref` | `str \| None` | 可选；anthropic/openai 必填（Fernet vault ref，格式 `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`）；ollama 不存在（无 API key）。 |
| `model` | `str` | 必填；主模型 id（当此为内部默认时，亦即 Coffer 内部引擎运行的模型）。 |
| `fast_model` | `str \| None` | 可选；Claude Code 上为 `ANTHROPIC_SMALL_FAST_MODEL`；openai wire 忽略。 |
| `wire_api` | `WireApi` | 可选；`"chat"`（默认）或 `"responses"`；仅 openai。 |
| `is_active` | `bool` | 同一 `wire_format` 下最多一条为 `True`（FR-011）；ollama 始终为 `False`（从不投影）。 |
| `internal_default` | `bool` | 全局最多一条为 `True`（FR-021）；Coffer 内部引擎使用的 connection。导入时若 >1，则归一化（保留最近更新的）。 |

所有字段均 JSON 稳定（无 Python 对象），`model_dump(mode="json")` 可干净序列化，适用于 SQLite 和 sync export。

### `WireFormat` 和 `WireApi`（`domain/provider/config.py`）

这两个枚举与 `ProviderConfig` 同在 `config.py` 中定义，没有独立的 `wire.py` 模块。

```python
class WireFormat(str, Enum):
    anthropic = "anthropic"
    openai = "openai"
    ollama = "ollama"

class WireApi(str, Enum):
    chat = "chat"
    responses = "responses"
```

### 投影函数（`domain/provider/projection.py`）

纯粹（无 I/O）函数，直接返回新的原生配置文本，类比 `domain/agent/mcp_install.py` 中的 `apply_install`。**不存在** `ProjectionPatch` 数据类，也**不存在** `build_patch()` 函数。

- `apply_anthropic_settings(config: ProviderConfig, existing_text: str) -> str`
- `apply_codex_provider(config: ProviderConfig, profile_name: str, existing_text: str) -> str`
- `ProjectionTarget`——目标配置文件描述符
- `target_for(wire: WireFormat) -> ProjectionTarget | None`——对 `ollama` 返回 `None`（仅内部；无 agent 投影）
- 常量：`CODEX_PROVIDER_ID`、`CODEX_ENV_KEY`、`ANTHROPIC_API_KEY_HELPER`

### 内部引擎（`application/provider/service.py` + `infrastructure/chat/`）

内部引擎 connection 由全局 `internal_default` 标志选择：

- `ProviderService.set_internal_default(name)`——清除所有其他 connection 的 `internal_default`，再设置目标（顺序 clear-then-set，由单进程 daemon 串行化）；发出 `provider_internal_default_set`。
- `ProviderService.resolve_internal_connection() -> ProviderConfig | None`——返回 `internal_default` connection 的 config，或 `None`（→ 内部引擎是干净的 no-op）。
- `build_chat_model(connection, ...)` 消费解析出的 connection，按 `wire_format`（anthropic / openai / ollama）分派，构建内部引擎的 chat model——取代已退役 `ModelConfig` 注册表的模型选择。

### 每种 `wire_format` 的托管原生配置键

`domain/provider/projection.py` 中的纯函数（`apply_anthropic_settings` / `apply_codex_provider`）将下列键写入 agent 的原生配置；`ProjectionTarget` + `target_for(wire)` 将每种 `wire_format` 映射到其 agent、allowlist key 与文件格式。投影测试断言这些托管键，确保规范与实现始终一致。

**anthropic 托管键：**

| 托管键路径 | 来源 |
|---|---|
| `apiKeyHelper` | 字面量 `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model`（为 `None` 时省略） |

**openai 托管键：**

| 托管键路径 | 来源 |
|---|---|
| `model` | `profile.model` |
| `model_provider` | 字面量 `"coffer"` |
| `model_providers.coffer.name` | `f"Coffer ({profile_name})"` |
| `model_providers.coffer.base_url` | `profile.base_url` |
| `model_providers.coffer.wire_api` | `profile.wire_api` |
| `model_providers.coffer.env_key` | 字面量 `"COFFER_PROVIDER_KEY"` |

## 复用锚点

所有实现必须复用以下现有组件，不得重新实现。

### Fernet vault（凭证隔离）

| 组件 | 路径 | 用途 |
|---|---|---|
| `EncryptedCredentialStore` | `backend/coffer/infrastructure/credentials/encrypted_store.py` | `get/set/exists/delete`——存取原始 secret |
| credential resolver | `backend/coffer/application/credentials/resolver.py` | 将 ref 解析为明文（密钥解析） |
| HTTP adopt 模式 | `backend/coffer/application/agent/mcp_entry_service.py:303` | "存储 secret，只保留 ref"创建模式 |
| citation 守卫 | `ResourceService.find_credential_citations` | 删除自有 secret 前的守卫 |

### Config-file store（原生配置写入）

| 组件 | 路径 | 用途 |
|---|---|---|
| `ConfigFileStore.write_text_atomic` | `backend/coffer/infrastructure/agent/config_file_store.py` | 原子写 + `.bak` 备份 |
| `spec_for` / `config_files_for` | `backend/coffer/domain/agent/config_files.py` | 为给定 `AgentType` + key 解析规范路径 |
| `AgentType` descriptors | `backend/coffer/domain/agent/descriptor.py` | `claude_code` `settings` → `~/.claude/settings.json`；`codex` `config` → `~/.codex/config.toml` |

### 投影模板（MCP 注入）

| 组件 | 路径 | 用途 |
|---|---|---|
| `apply_install` | `backend/coffer/domain/agent/mcp_install.py` | 返回文本的纯投影函数结构模板 |
| `mcp_entries.py` | `backend/coffer/domain/agent/mcp_entries.py` | JSON 通过 `json.dumps`；TOML 通过 `tomlkit`——均复用 |
| MCP service | `backend/coffer/application/agent/mcp_service.py` | 驱动模式参考 |

### Resource Kind 模式

| 组件 | 路径 | 用途 |
|---|---|---|
| `Kind` dataclass | `backend/coffer/domain/resource.py` | 定义 `provider` Kind |
| kind factory | `backend/coffer/application/knowledge_base/kind.py` | `make_provider_kind(...)` 的模板 |
| `wire_kb_kind` | `backend/coffer/surfaces/http/wiring.py` | `wire_provider_kind(...)` 的模板 |
| composition root | `backend/coffer/surfaces/http/app.py` | 注册 `app.state.kinds["provider"]` 的位置 |

### 单活跃不变量

激活翻转通过顺序的 `ResourceService.update_config` 调用实现（先清除其他，再设置目标）；单进程 daemon 对请求串行化，切换操作不会交错。**不存在** `ProviderRepo` / `activate_atomic`。

| 组件 | 路径 | 用途 |
|---|---|---|
| `ModelConfig` 域 | `backend/coffer/domain/chat/model.py` | 每 wire 单活跃模式（镜像，不耦合） |
| `ResourceService.update_config` | 现有 resource service | 由 `ProviderService.activate()` 直接使用 |

### Sync

| 组件 | 路径 | 用途 |
|---|---|---|
| `ResourceDoc` / `resource_to_doc` | `backend/coffer/domain/sync/serialization.py` | 序列化 provider 行 |
| `SyncExporter` | `backend/coffer/application/sync/exporter.py` | 列出所有 kind（自动） |
| `SyncImporter` | `backend/coffer/application/sync/importer.py` | 按 `(kind, name)` reconcile（自动） |

### 审计

| 组件 | 路径 | 用途 |
|---|---|---|
| `AuditEventType` | `backend/coffer/domain/audit.py` | 添加 `PROVIDER_SWITCHED` |
| `AuditEntry` | `backend/coffer/domain/audit.py` | 事件形状 |
| `AuditService.record` | `backend/coffer/application/audit_service.py` | 从切换操作发出 `PROVIDER_SWITCHED` |

## SQLite schema 变更

**无需新迁移。** `provider` kind 复用共享的 `resources` 表（新行 `kind='provider'`）。`ProviderConfig` 字典存储在现有的 `resources.config` JSON 列中。

无新表；无 SCHEMA_VERSION bump。

## 新增审计事件

在 `backend/coffer/domain/audit.py` 的 `AuditEventType` 中添加：

| 值 | 发出时机 |
|---|---|
| `provider_switched` | `POST /providers/{name}/activate` 成功；details：`{from, to, wire_format, agents: [...projected...]}` |
| `provider_internal_default_set` | `POST /providers/{name}/internal-default` 成功；details：`{from, to}`（先前内部默认名称或 null，及新的） |

`RESOURCE_CREATED`、`RESOURCE_UPDATED`、`RESOURCE_DELETED` 由 `ResourceService` 在 CRUD 操作时自动发出（无需新增）。

## 应用服务契约（`backend/coffer/application/provider/`）

### `ProviderService`（`application/provider/service.py`）

| 方法 | 用途 |
|---|---|
| `create(name, config, secret_value?, credential_ref?, actor) -> Resource` | 校验；若提供 `secret_value` 则存储 secret；注册 Resource。两者都提供或都没有时拒绝。 |
| `update(name, patch, secret_value?, actor) -> Resource` | 部分更新；若提供 `secret_value` 则轮换 vault 条目。 |
| `delete(name, actor) -> None` | 通过 `find_credential_citations` 守卫自有凭证；若自有则删除 vault 条目；删除 Resource。 |
| `activate(name, actor) -> ActivateResult` | 顺序 clear-then-set 实现单活跃不变量；向匹配的已注册 agent 投影；发出 `PROVIDER_SWITCHED`。 |
| `resolve_active_key(wire: WireFormat) -> str` | 找到给定 wire format 的活跃 profile；解密并返回 key（仅 stdout；调用方不得记录）。不支持按名称解析。 |
| `set_internal_default(name, actor) -> Resource` | 清除所有其他 connection 的 `internal_default`，再设置目标（全局单一内部默认不变量，FR-021）；发出 `PROVIDER_INTERNAL_DEFAULT_SET`。 |
| `resolve_internal_connection() -> ProviderConfig \| None` | 返回 `internal_default` connection 的 config，或 `None`（→ 内部引擎——memory organizer / reorg / distill / `coffer__ask`——是干净的 no-op）。 |

### `ActivateResult`（`application/provider/service.py`）

```python
@dataclass
class ActivateResult:
    activated: str
    projected: list[str]   # 已写入的 agent 名称
    skipped: list[str]     # 不匹配或未注册的 agent 名称
```

### `ProviderService._project`（`application/provider/service.py`）

投影作为 `ProviderService` 上的内联私有方法实现；**不存在**独立的 `application/provider/projector.py` / `ProviderProjector` 类。

`_project(profile_name, config, agent_config_dir)` 调用 `apply_anthropic_settings(...)` 或 `apply_codex_provider(...)`（纯域函数，返回文本），然后通过 `ConfigFileStore.write_text_atomic` 写入。

**不存在** `infrastructure/provider/persistence.py`，也**不存在** `ProviderRepo`。provider profile 是由现有 `ResourceService` 管理的普通 resource 行（CRUD + 审计 + sync 免费获得）。

## 磁盘 / sync 布局

无需新目录。provider profile 存入现有 sync workspace：

```
~/.coffer/sync/
  resources/
    provider/
      <name>.yaml      # 每条 profile 一个确定性 YAML 文件（不含 secret）
  credentials/
    provider/
      <name>/
        key.enc        # 原始 API key 的 Fernet 密文
```

provider 无新的 `~/.coffer/` 子目录（不同于 skill 有主内容存储）。唯一的磁盘副作用是投影写入的原生配置文件（`~/.claude/settings.json`、`~/.codex/config.toml`）及其 `.bak` 备份。

## 约束摘要

- `ProviderConfig` 任何时候都不得包含原始 secret。
- 域层投影函数（`apply_anthropic_settings`、`apply_codex_provider`）必须为纯函数（无 I/O），返回新的原生配置文本。
- 密钥解析不得将解密值记录到日志。
- 每 wire 单活跃不变量通过顺序的 `ResourceService.update_config` 调用在单进程 daemon 中串行执行。
- 所有 HTTP 路由仅限 loopback，受 `X-Coffer-Token` 门控。
