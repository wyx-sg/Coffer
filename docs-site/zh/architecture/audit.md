# 审计与问责

::: tip 核心锚点
审计日志和调用日志是 Coffer 的问责记录——它们回答「谁做了什么」和「谁在何时调用了什么，结果如何」。它们与运维可观测性不同。两者都存储在本地，都可以剪裁，且都不会存储任何密钥材料或用户数据。
:::

关于运维可观测性（结构化日志、链路追踪关联、错误信封），请参阅[可观测性](/zh/architecture/observability)。

## 这解决了什么问题

一个开发者注册了一批 MCP 服务器、导入了技能、积累了知识、运行着聊天会话、配对了通知通道，并把这一切跨机器同步——这些操作由 Claude Code、Codex、UI 和自定义脚本驱动，常常同时进行。没有问责记录，甚至连基本的治理问题也变得不透明：「`filesystem__write_file` 工具是我还是 UI 禁用的？」「下午 2 点 Claude Code 调用的是哪个服务器的工具，结果如何？」「这个服务器的配置上次是什么时候变更的？」「凭据上次是什么时候轮换的，主密钥是什么时候迁移的？」审计日志和调用日志能回答这些问题，而无需用户运行独立的监控栈。

Coffer 的方案刻意保持精简：一对本地数据库表，而非时序数据库或日志管理 SaaS。所有记录都留在本机，并在 `~/.coffer/` 的备份范围内。

## 这是给谁读的

**给 agent，不是给人。** 审计日志曾经有一个网页；它已被删除，因为没人打开过。
人不会专门坐下来浏览「我的金库里改了什么」——人是发现有东西坏了，然后去问那个
帮他的角色，而那个角色是 agent。

因此这两份记录都是按这个读者来塑形的：

- **`coffer__diagnose`** 是入口。一次调用同时返回审计日志（改了什么、谁改的）
  与守护进程日志（发生了什么，包括失败），放在同一条从新到旧的时间线上——因为
  撞上失败的 agent 并不知道自己需要哪一份，它需要知道的是发生了什么。
- **事件类型保持线上原值。** 它们曾为那个被删掉的页面翻译成口语化活动行
  （「Enabled demo-fs」）；每种语言 39 条字符串随页面一起消失。agent 要的是
  `resource_enabled`。
- **每个被审计的事件同时也是一行日志**，因此两份记录共用同一套词汇，
  agent grep 其中一份就能找到另一份。

`GET /api/v1/audit` 与 `coffer audit` 保持不变，供脚本使用。

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

全部被审计的事件类型（定义在 `domain/audit.py` 的 `AuditEventType`），按域分组。一共 39 个，这个列表是刻意保持短的——见下方 [什么值得审计](#什么值得审计)。

**资源与能力：**

| 事件                                         | 触发时机                                       |
| -------------------------------------------- | ---------------------------------------------- |
| `resource_created`                           | `ResourceService.register` 之后                |
| `resource_updated`                           | config 或 description 变更之后                 |
| `resource_enabled` / `resource_disabled`     | `set_enabled` 且状态确实翻转之后               |
| `resource_deleted`                           | `delete` 之后；`details` 含删除前的 config 快照 |
| `resource_scope_updated`                     | 资源的 per-agent 生效 scope 变更时             |
| `capability_enabled` / `capability_disabled` | 用户开关某项能力时                             |

**Daemon 与设置：**

| 事件                        | 触发时机                                 |
| --------------------------- | ---------------------------------------- |
| `token_rotated`             | `POST /api/v1/daemon/rotate-token` 之后  |
| `retention_updated`         | 保留策略变更时                           |
| `embedding_config_updated`  | embedding provider/模型变更时            |
| `internal_engine_model_set` | 选定内部引擎所用模型时                   |

**凭据与主密钥：**

| 事件                                                        | 触发时机                                       |
| ----------------------------------------------------------- | ---------------------------------------------- |
| `credential_set` / `credential_read` / `credential_deleted` | 加密凭据存储的写 / 读 / 删之后                 |
| `credential_migrated`                                       | 逐 ref，遗留 keychain 密钥迁入存储时           |
| `master_key_relocated`                                      | 主密钥在文件与 keychain 存储之间移动之后       |
| `master_key_exported` / `master_key_imported`               | 主密钥带外传输到 / 自另一台机器                |

**Agent 工作区** —— 这里每一条写的都是 Coffer 并不拥有的文件：

| 事件                                                      | 触发时机                                             |
| --------------------------------------------------------- | ---------------------------------------------------- |
| `agent_config_file_written` / `agent_config_file_deleted`  | agent 配置文件被写入 / 删除时                        |
| `agent_mcp_installed` / `agent_mcp_uninstalled`            | Coffer 的 MCP 条目被安装进 / 移出某个 agent 时       |
| `agent_mcp_entry_adopted`                                  | agent 自有配置里的 MCP 条目被收编进 Coffer 时        |

**技能：**

| 事件                                        | 触发时机                                     |
| ------------------------------------------- | -------------------------------------------- |
| `skill_imported` / `skill_updated`          | skill 被导入 / 更新进主库时                  |
| `skill_bound` / `skill_unbound`             | skill 被投递给 / 撤出某个 agent 时           |
| `skill_relinked`                            | skill 链接被修复时                           |
| `skill_drift_remediated`                    | 与受管 skill 的磁盘漂移被修复时              |
| `skill_adopted` / `skill_unmanaged_deleted` | 未托管 skill 被收编 / 游离副本被删除时       |

**知识** —— 只留破坏性的这几条：

| 事件                  | 触发时机                     |
| --------------------- | ---------------------------- |
| `kb_document_deleted` | 已摄入文档被删除时           |
| `memory_deleted`      | 条目被删除时                 |
| `memory_cleared`      | 某个知识 scope 被清空时      |

`kb_*` 与 `memory_*` 前缀是历史遗留：它们是两个 kind 合并为 `knowledge` 之前的线上取值，原样保留是为了让既有审计行与查询继续有效。

**通道：**

| 事件                                        | 触发时机                           |
| ------------------------------------------- | ---------------------------------- |
| `channel_pairing_issued` / `channel_paired` | 签发配对码时 / 某个 peer 认领它时  |

**Provider：**

| 事件                            | 触发时机                                     |
| ------------------------------- | -------------------------------------------- |
| `provider_switched`             | 某条连接被投射进 agent 的原生配置时          |
| `provider_internal_default_set` | 某条连接成为 Coffer 内部引擎时               |

**导出 / 导入：** 导入所执行的资源写入会记录为普通的资源生命周期事件，因此一次导入带来的变更和手工做出的变更一样可追溯。不存在配置事件与冲突事件，因为既没有同步配置、也没有冲突状态（[ADR-016](/zh/reference/adr/ADR-016-vault-export-import)）。

## 什么值得审计

一个事件必须至少满足以下三条之一，才配得上一行记录：

- **它落在 Coffer 之外。** 某个 agent 的配置文件、伸进别人 `~/.claude/` 的符号链接、投射进 `~/.codex/config.toml` 的密钥。Coffer 伸进了它并不拥有的地界，而审计日志是唯一写下这件事的地方。
- **它不可逆或安全敏感。** 删除、凭据读取、主密钥导出、token 轮换。事后已经没有状态可查，或者「读取」这个动作本身就是值得知道的事。
- **它是低频配置变更，且当前状态推不出它曾发生。** 保留窗口被改了；某项能力被关掉了。当前值看得见，但**是谁在什么时候改的**看不见。

2026-09 有 27 个事件类型因为一条都不满足而被退役。这些理由值得写下来，因为正是它们该阻止这个列表重新长回去：

- **运行遥测**（`daemon_started`、`chat_turn_completed`、`channel_turn_started`、`sync_completed` 等）—— daemon 跑起来了、一个 turn 完成了，这属于日志行，不属于「变更的持久记录」。
- **表里已经有的事实**（`capability_first_seen`）—— `mcp_capability_preferences.first_seen_at` **就是**这个事件，而且存在一个可以被查询的地方。
- **幂等重算**（`kb_reindexed`、`memory_organized`、`memory_reorganized`、`kb_document_ingested`、`memory_added` 等）—— 再跑一遍什么都不会变，而结果就在磁盘上。文件本身就是记录。
- **什么也没改的检测**（`skill_drift_detected`、`skill_autobind_skipped`）—— 发现不等于动手。**修复**会审计，发现不会。
- **低价值会话状态**（`conversation_created`、`conversation_archived`、`handoff_set`）—— 可恢复、在对象本身里看得见、而且量大。

单笔收益最大的是删掉 `journal_append`：它曾占全部审计行的 **98.5%**（4384 条里的 4318 条），却只记录了一个字符数——它所描述的内容早就躺在一个 Markdown 文件里。

注意 `credential_set` 与 `credential_deleted` 是被审计的——「一个密钥被存入或移除」这个**事实**会被记录。密钥值本身永远不会出现在 `details` 载荷里。

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
