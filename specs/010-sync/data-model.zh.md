# Spec 010 — Data Model

> English: [data-model.md](./data-model.md)

## 持久化状态

### `sync_config`（单行）

沿用 `embedding_config` 的单例模式（一行，固定 id）。

| Field              | Type    | Notes                                              |
| ------------------ | ------- | -------------------------------------------------- |
| `id`               | String  | `SINGLETON` 常量主键。                              |
| `remote`           | String? | Git 远端 URL；配置前为 null。                       |
| `enabled`          | bool    | 同步的总开关。默认 `false`。                        |
| `auto`             | bool    | 守护进程是否运行自动同步 worker。默认 `false`。     |
| `interval_seconds` | int     | auto-sync 兜底轮询间隔。默认 `300`。                |
| `poll_remote_seconds` | int  | auto-sync 远端 HEAD 探测频率。默认 `15`，最小 `5`。 |
| `branch`           | String  | 同步所在的 Git 分支。默认 `main`。                  |
| `updated_at`       | String  | ISO-8601。                                          |

此处不存储任何密钥。Git 远端鉴权依赖用户当前环境的 git 凭据配置。

### `sync_state`（单行）

最近一次运行的状态，同样是单例行。

| Field             | Type    | Notes                                                          |
| ----------------- | ------- | -------------------------------------------------------------- |
| `id`              | String  | `SINGLETON`。                                                  |
| `status`          | String  | `clean` / `syncing` / `conflicted` / `error` / `credentials_locked` / `unconfigured`。 |
| `last_sync_at`    | String? | 最近一次成功运行的 ISO-8601 时间。                            |
| `last_error`      | String? | 最近一次错误信息（已脱敏，不含密钥）。                        |
| `conflict_paths`  | JSON    | 当前处于冲突状态的、相对于 workspace 的路径列表。             |
| `locked_refs`     | JSON    | 以密文形式存在、但在本机无法解密的凭据 ref。                  |
| `quarantined_refs`| JSON    | 在本机导入失败的 `<kind>:<name>` ref；每次运行重试。          |
| `updated_at`      | String  | ISO-8601。                                                      |

两张表都位于 `infrastructure/sync/persistence.py`；迁移 `0017`。

### `machine_identity`（单行）

本机的稳定身份（ADR-043）。它是*关于*这台机器的本机状态——永不作为 vault 数据
导出（workspace 的 `machines/` 注册项在导出时由它派生）。

| Field          | Type   | Notes                                       |
| -------------- | ------ | ------------------------------------------- |
| `id`           | int    | `1`（CHECK 约束的单例）。                    |
| `machine_id`   | String | 守护进程首次启动时铸造的 ULID；永不改变。    |
| `display_name` | String | 默认取主机名；用户可编辑。                   |
| `created_at`   | String | ISO-8601。                                   |
| `updated_at`   | String | ISO-8601。                                   |

位于 `infrastructure/sync/persistence.py`；迁移 `0042`。

### `sync_tombstones`（台账）

本机配置资源删除的本地记录，等待导出为 workspace 墓碑文件。资源在本机重新
注册、或超过 90 天 TTL 后，对应行被删除。

| Field        | Type   | Notes                            |
| ------------ | ------ | -------------------------------- |
| `id`         | int    | 自增主键。                        |
| `kind`       | String | 资源 kind。与 `name` 联合唯一。   |
| `name`       | String | 资源名。                          |
| `deleted_at` | String | 本地删除的 ISO-8601 时间。        |

位于 `infrastructure/sync/persistence.py`；迁移 `0043`。

## 文件系统状态（同步 workspace）

默认为 `~/.coffer/sync/`（测试时可通过 `$COFFER_SYNC_ROOT` 覆盖），这是一个
git 工作树，其 `origin` 指向用户的远端。

```
manifest.json
machines/<machine-id>.json      每机注册项（只由其所属机器写入）
machines/<machine-id>/overrides/<kind>/<name>.yaml   每机 merge patch
knowledge/                      mirror of ~/.coffer/knowledge
memory/                         mirror of ~/.coffer/memory
skills/                         mirror of ~/.coffer/skills
resources/<kind>/<name>.yaml    one deterministic file per config resource
tombstones/resources/<kind>/<name>.json   显式删除记录
state/<area>/...yaml            模块自有的共享状态文档
credentials/<ref>.enc           Fernet ciphertext, base64 text; never the key
```

### `manifest.json`

| Field             | Type   | Notes                                            |
| ----------------- | ------ | ------------------------------------------------ |
| `schema_version`  | int    | 当 workspace 布局发生不兼容变更时递增。           |

只有 schema 版本——manifest 在每台机器上字节一致，因此永远不会发生合并冲突。
每机信息改放在 `machines/` 区。`schema_version` 会在导入时校验；若 workspace 比
正在运行的构建版本更新，则会快速失败（`SYNC_WORKSPACE_TOO_NEW`），与数据库的
`DB_SCHEMA_TOO_NEW` 规则相对应。

### 机器注册项（`machines/<machine-id>.json`）

| Field            | Type    | Notes                                        |
| ---------------- | ------- | -------------------------------------------- |
| `machine_id`     | String  | 所属机器的 ULID（= 文件名）。                 |
| `display_name`   | String  | 默认主机名；用户可编辑。                      |
| `platform`       | String  | 如 `darwin` / `linux`。                       |
| `os_version`     | String  | 人类可读的操作系统版本。                      |
| `coffer_version` | String  | 生产者版本，用于诊断。                        |
| `last_sync_at`   | String  | 该机器最近一次完成导出的 ISO-8601 时间。      |

每台机器**只写自己的**注册项；仅当本次运行的提交本就非空、或注册项已超过 24 小时
（心跳）时才重写，因此空闲机器不会产生纯注册项的提交链。

### 资源序列化（`resources/<kind>/<name>.yaml`）

`Resource` 的确定性投影：

```yaml
kind: mcp_server
name: confluence
description: "..."
enabled: true
config: { ... }     # the validated, json-mode config; keys sorted
```

`created_at` / `updated_at` 以及本地 `id` 被**排除**（属于机器本地数据，会让
diff 频繁变动）。导入时按 `<kind>:<name>` 对资源执行 upsert。**仅**当墓碑文件
存在时才删除本地资源——资源只是从 workspace 缺席永远不会导致删除（别处的导入
失败绝不能伪装成删除）。当同一 ref 的资源文档与墓碑同时存在时（合并残留），
资源文档胜出。

### 墓碑（`tombstones/resources/<kind>/<name>.json`）

| Field        | Type   | Notes                              |
| ------------ | ------ | ---------------------------------- |
| `deleted_at` | String | 删除的 ISO-8601 时间。              |
| `by`         | String | 执行删除的机器的 `machine_id`。     |

导出时由 `sync_tombstones` 台账写出；当资源重新存活时在导出中移除（重新注册
胜出）；90 天后清理。

### 状态区（`state/<area>/...yaml`）

随 vault 同步的模块自有共享状态。各模块实现 `SyncedStatePort`（确定性 YAML 文档的
导出/导入），由组合根注册提供者——sync 永不导入 kind 模块。当前区域：

- `channel-peers/<channel>/<chat>.yaml` —— 配对身份（chat_id、sender_id、显示名、
  首选 agent、paired_at；机器本地的 `active_conversation_id` 永不传播）。导入执行
  upsert；引用本地不存在渠道的文档被跳过并在下轮重试。
- `mcp-preferences/<server>.yaml` —— 每服务器被**禁用**的能力（启用为默认；
  seen 时间戳保持本机）。导入将本地存在的服务器收敛到文档内容；认领前缀 = 本地服务器。
  冲突语义按文档粒度：若两台机器在首次共同同步前对同一服务器禁用了不同能力，
  合并将冲突、被解决的一方整体获胜——落败机器的本地禁用会在其下一次导入被重新
  启用。凭证 ref 尚未解锁的机器上 embedding 会保持降级（锁定 ref 可正常导入；
  向量索引只是不激活）。
- `settings/embedding.yaml` + `settings/internal-engine.yaml` —— 两个引擎单例。
  机器只有在本地持久化过该单例后才认领（并发布）它，全新机器的默认值不会在首次
  合并时与舰队值同路径冲突。
- `memory-labels/<store>.yaml` —— 记忆库的用户显示标签（spec 007 FR-017c），让
  `project-<ULID>` 库在每台机器上都以其名字显示，而不是「未命名记忆库」。加性
  语义：设置或改名会传播（机器认领它标注过的库）；清除标签保持本机。

skill 投递绑定（`skill_agent_bindings`）**按决定保持本机**：投递是有副作用的文件
操作且没有行级 reconcile 循环——同步这些行会虚报投递状态。请在每台机器上经现有
skill 表面自行采用。

### 凭据 blob（`credentials/<ref>.enc`）

`ref` 对应的 Fernet 密文，以 base64 文本编码，使 git 存储稳定的行内容。不含主密钥、
不含明文，除 ref（即路径）外不含任何元数据。

`ref` 可带斜杠命名空间（如 `channel/seatalk/app-secret`、`provider/agnes/key`），
因此 blob 存放在对应的嵌套路径 `credentials/channel/seatalk/app-secret.enc`。导出时
会创建父目录；导入时递归遍历并由相对路径还原出完整的斜杠 ref。

## 仅本地、永不进入 workspace

`~/.coffer/logs/`、`coffer.db`、`daemon.json`、PID/端口文件，以及主密钥
文件 / keychain 条目。

## 派生索引（排除并重建）

由「事实源文件」重新生成的派生文件会被排除出镜像——它们逐机不同，若同步会
造成同路径的伪冲突。当前的例子是 memory store 的 `MEMORY.md` 索引：逐条
`<slug>.md` 事实文件照常同步，`MEMORY.md` 在导入后由合并后的事实文件重建。
排除集合见 `infrastructure/sync/workspace.DERIVED_INDEX_NAMES`。
