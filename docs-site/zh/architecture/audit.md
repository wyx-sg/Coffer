# 审计与问责

::: tip 核心锚点
审计日志和调用日志是 Coffer 的问责记录——它们回答「谁做了什么」和「谁在何时调用了什么，结果如何」。它们与运维可观测性不同。两者都存储在本地，都可以剪裁，且都不会存储任何密钥材料或用户数据。
:::

关于运维可观测性（结构化日志、链路追踪关联、错误信封），请参阅[可观测性](/zh/architecture/observability)。

## 这解决了什么问题

一个开发者注册了一批 MCP 服务器、导入了技能、构建了知识库、积累了记忆、运行着聊天会话、配对了通知通道，并把这一切跨机器同步——这些操作由 Claude Code、Codex、UI 和自定义脚本驱动，常常同时进行。没有问责记录，甚至连基本的治理问题也变得不透明：「`filesystem__write_file` 工具是我还是 UI 禁用的？」「下午 2 点 Claude Code 调用的是哪个服务器的工具，结果如何？」「这个服务器的配置上次是什么时候变更的？」「凭据上次是什么时候轮换的，主密钥是什么时候迁移的？」审计日志和调用日志能回答这些问题，而无需用户运行独立的监控栈。

Coffer 的方案刻意保持精简：一对本地数据库表，而非时序数据库或日志管理 SaaS。所有记录都留在本机，并在 `~/.coffer/` 的备份范围内。

## 审计日志：生命周期变更

对任何资源或能力的每一次变更，都会在响应返回给调用者之前写入 `audit_log` 表。审计条目记录以下内容：

| 字段            | 它告诉你什么                                                                              |
| --------------- | ----------------------------------------------------------------------------------------- |
| `event_type`    | 发生了哪种生命周期操作（例如 `resource_created`、`capability_disabled`、`token_rotated`） |
| `resource_kind` | 受影响资源的 kind（例如 `mcp_server`），daemon 级别事件为 `null`                          |
| `resource_name` | 具体的资源名称，daemon 级别事件为 `null`                                                  |
| `actor`         | 谁触发了变更：`cli`、`api`、`ui` 或 `system`                                              |
| `timestamp`     | 事件发生的 UTC 时间                                                                       |
| `details`       | 描述变更的结构化 JSON payload（例如删除前的配置快照、新旧配置的差异）                     |

`actor` 字段值得特别关注。每个接口面都会显式设置它：Typer CLI 在向 daemon 的 HTTP 调用中传递 `X-Coffer-Actor: cli`；REST API 客户端可以设置 `X-Coffer-Actor: api` 或 `X-Coffer-Actor: ui`；如果 header 缺失，daemon 默认为 `"api"`。daemon 自身会为自动化操作（如保留策略清理）发出 `system` 事件。这意味着审计日志能准确反映一次变更是交互式发起的、程序化发起的，还是自动触发的。

`AuditEventType`（定义在 `domain/audit.py`）的完整事件类型集合，按领域分组：

**资源与能力：**

| 事件                                         | 触发时机                                        |
| -------------------------------------------- | ----------------------------------------------- |
| `resource_created`                           | `ResourceService.register` 之后                 |
| `resource_updated`                           | 配置或描述变更之后                              |
| `resource_enabled` / `resource_disabled`     | 状态确实发生翻转时，在 `set_enabled` 之后       |
| `resource_deleted`                           | `delete` 之后；`details` 中包含删除前的配置快照 |
| `capability_first_seen`                      | 发现服务时首次看到该能力                        |
| `capability_enabled` / `capability_disabled` | 用户切换能力状态时                              |

**Daemon：**

| 事件                                | 触发时机                                |
| ----------------------------------- | --------------------------------------- |
| `daemon_started` / `daemon_stopped` | daemon 启动 / 优雅关闭时                |
| `token_rotated`                     | `POST /api/v1/daemon/rotate-token` 之后 |
| `retention_updated`                 | 保留策略发生变更时                      |
| `backup_created`                    | `POST /api/v1/vault/backup` 之后        |

**凭据与主密钥：**

| 事件                                                        | 触发时机                                  |
| ----------------------------------------------------------- | ----------------------------------------- |
| `credential_set` / `credential_read` / `credential_deleted` | 加密凭据存储中写入 / 读取 / 删除之后       |
| `credential_migrated`                                       | 每个 ref：legacy 钥匙串密钥迁入存储时      |
| `master_key_relocated`                                      | 主密钥在文件与钥匙串存储之间迁移之后       |
| `master_key_exported` / `master_key_imported`               | 主密钥向 / 从另一台机器的带外传输          |
| `keychain_set` / `keychain_read` / `keychain_deleted`       | legacy（加密存储之前）事件，为历史行保留可渲染性 |

**Embedding：**

| 事件                       | 触发时机                          |
| -------------------------- | --------------------------------- |
| `embedding_config_updated` | embedding 提供方/模型变更时       |

**Agent 工作区：**

| 事件                                                      | 触发时机                                        |
| --------------------------------------------------------- | ----------------------------------------------- |
| `agent_config_file_written` / `agent_config_file_deleted` | agent 配置文件被写入 / 删除时                   |
| `agent_mcp_installed` / `agent_mcp_uninstalled`           | MCP 条目被安装到 / 从 agent 卸载时              |
| `agent_mcp_entry_removed` / `agent_mcp_entry_adopted`     | MCP 条目被从 agent 移除 / 被 agent 接管时       |
| `agent_plugin_toggled` / `agent_plugin_uninstalled`       | agent 插件被切换 / 卸载时                       |

**技能：**

| 事件                                        | 触发时机                                       |
| ------------------------------------------- | ---------------------------------------------- |
| `skill_imported` / `skill_fetched`          | 技能被本地导入 / 从来源拉取时                  |
| `skill_updated` / `skill_update_noop`       | 技能更新生效 / 为空操作时                      |
| `skill_renamed`                             | 技能被重命名时                                 |
| `skill_bound` / `skill_unbound`             | 技能被绑定到 / 从 agent 解绑时                 |
| `skill_autobind_skipped`                    | autobind 被跳过时                              |
| `skill_relinked`                            | 技能链接被修复时                               |
| `skill_drift_detected`                      | 检测到磁盘上的内容与受管技能产生漂移时         |
| `skill_adopted` / `skill_unmanaged_deleted` | 未受管技能被接管 / 散落技能被删除时            |

**知识库：**

| 事件                                                                  | 触发时机                            |
| --------------------------------------------------------------------- | ----------------------------------- |
| `kb_document_ingested` / `kb_document_updated` / `kb_document_deleted` | KB 文档被摄取 / 更新 / 删除时        |
| `kb_reindexed`                                                        | `coffer kb reindex` 重建索引之后    |

**记忆：**

| 事件                                                 | 触发时机                              |
| ---------------------------------------------------- | ------------------------------------- |
| `memory_added` / `memory_updated` / `memory_deleted` | 记忆 fact 被添加 / 更新 / 删除时       |
| `memory_cleared`                                     | 记忆 store 被清空时                   |
| `memory_projected`                                   | 记忆被投影到 agent/项目时             |

**聊天、会话与模型：**

| 事件                                                 | 触发时机                              |
| ---------------------------------------------------- | ------------------------------------- |
| `conversation_created` / `conversation_deleted`      | 会话被创建 / 删除时                   |
| `conversation_archived` / `conversation_unarchived`  | 会话被归档 / 取消归档时               |
| `chat_turn_completed`                                | 一次聊天回合完成之后                  |
| `model_created` / `model_updated` / `model_deleted`  | 聊天模型定义被创建 / 更新 / 删除时     |

**通道：**

| 事件                                        | 触发时机                              |
| ------------------------------------------- | ------------------------------------- |
| `channel_pairing_issued` / `channel_paired` | 通道配对码被签发 / 对端完成配对时     |
| `channel_notify_sent`                       | 向已配对通道发送通知时                |

**同步：**

| 事件                                | 触发时机                              |
| ----------------------------------- | ------------------------------------- |
| `sync_config_updated`               | 同步配置发生变更时                    |
| `sync_completed`                    | 一次同步运行完成之后                  |
| `sync_conflicted` / `sync_resolved` | 同步运行发生冲突 / 冲突被解决时       |

注意，`credential_set` 和 `credential_deleted` 都会被审计——密钥被存储或删除这一*事实*会被记录下来。密钥值本身永远不会出现在 `details` payload 中。（legacy 的 `keychain_set` / `keychain_deleted` 事件类型对历史记录仍可渲染。）

## 调用日志：什么流量经过了网关

daemon 通过网关路由的每一次工具调用、资源读取和提示词获取，都会在 `mcp_invocations` 中生成一行记录。该行记录以下内容：

| 字段              | 它告诉你什么                          |
| ----------------- | ------------------------------------- |
| `timestamp`       | 调用开始的时间                        |
| `resource_name`   | 哪个已注册的 MCP 服务器处理了此次调用 |
| `capability_type` | `tool`、`resource` 或 `prompt`        |
| `capability_key`  | 原始（无前缀）的能力名称              |
| `duration_ms`     | 从收到请求到上游回复的挂钟毫秒数      |
| `status`          | `ok`、`error`、`timeout` 或 `denied`  |
| `error_message`   | 当 `status != "ok"` 时填充            |
| `session_id`      | 每个 MCP 客户端会话的关联 ID          |

::: tip 不变量：参数和结果永远不会被持久化存储
`mcp_invocations` 的 schema 中没有存储调用参数或返回内容的列。这是一个刻意且永久的设计决策，而非日后需要填补的遗漏。参数和结果可能包含敏感信息（文件内容、API 响应、用户数据）。存储它们会使调用日志成为潜在的数据泄露渠道，会显著增加存储占用，并带来无明确解决方案的保留策略问题。调用日志回答的是「谁调用了什么，何时，结果如何」——仅此而已。
:::

`status` 字段区分了四种在问责上有意义的结果：

- **`ok`** — 上游在超时时间内成功回复。
- **`error`** — 上游回复了 JSON-RPC 错误（错误消息被存储，但不存储完整响应 payload）。
- **`timeout`** — 上游未在 `request_timeout_seconds` 内回复。上游子进程或 HTTP 连接被关闭。
- **`denied`** — 调用在到达上游之前就被 Coffer 拒绝，因为该能力已被禁用或资源处于非就绪状态。这让用户可以区分「上游失败了」和「我昨天禁用了这个工具」。

`session_id` 字段关联来自同一个 MCP 客户端会话的所有调用。用户如果想知道「为什么 Claude Code 的工具调用失败了」，可以按 session ID 过滤 `mcp_invocations`，查看该会话发起的完整调用序列——无需查看 Claude Code 自身的日志。

## 保留策略：有界的日志增长

日志类表会无限增长，除非进行剪裁。`retention_policies` 表和 `RetentionService` 后台 worker 共同控制增长。

### 一张表如何加入保留策略

任何应该可剪裁的表都需要实现 `PrunableTable` 协议，并在组装入口 (composition root) 注册：

```python
PrunableTable(
    name="mcp_invocations",
    timestamp_column="timestamp",
    default_retention_days=30,
    display_name="工具调用",
    description="网关中每次能力调用的记录",
)
```

`name` 必须出现在 SQL allowlist 集合中。`timestamp_column` 必须出现在列 allowlist 中。这些 allowlist 硬编码在 `infrastructure/persistence/retention.py` 中，无法在运行时扩展。这意味着剪裁 worker 只能从开发者明确加入白名单的表中删除数据——不可能执行任意 SQL。

### retention_policies 表

每个已注册的可剪裁策略对应一行。daemon 首次启动时的默认值：

| 策略                    | 动作                               | 默认值 |
| ----------------------- | ---------------------------------- | ------ |
| `audit_log`             | 删除早于窗口的行                   | 365 天 |
| `mcp_invocations`       | 删除早于窗口的行                   | 30 天  |
| `conversations_archive` | 自动归档闲置达到指定天数的会话     | 7 天   |
| `conversations`         | 在归档后达到指定天数时删除已归档会话 | 30 天 |

用户可以通过 `PATCH /api/v1/retention/{table_name}` 修改任意一个。将 `retention_days` 设置为 `null` 表示「永久保留」。零值被禁止。变更会以 `retention_updated` 记录在审计日志中。

### 后台 worker

一个在 daemon 内部运行的 asyncio 任务，按可配置的间隔轮询 `retention_policies` 表，并对每个 `retention_days` 不为 null 的表执行 `DELETE FROM <table> WHERE <timestamp_column> < ?`。该 worker：

- 在事务内执行删除，确保不会产生半剪裁的表。
- 每次成功剪裁后更新 `retention_policies` 中的 `last_pruned_at` 和 `last_pruned_rows`。
- 不会在表之间的处理间隔中阻塞事件循环——它会在每张表的删除操作之间主动让出控制权。
- 不跨表进行级联删除：已删除服务器的审计条目会被保留（保留策略是按表的，而非按资源的）。

## 另请参阅

- [架构参考](/zh/reference/project/architecture) — 审计、保留策略和跨层关注点表
- [Spec 001 参考](/zh/reference/specs/001-mcp-gateway/spec) — 调用日志不变量、token 鉴权和 `X-Coffer-Actor` header 语义
