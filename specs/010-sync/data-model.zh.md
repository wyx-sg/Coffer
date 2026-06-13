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
| `interval_seconds` | int     | 自动 pull/push 间隔。默认 `300`。                   |
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
| `updated_at`      | String  | ISO-8601。                                                      |

两张表都位于 `infrastructure/sync/persistence.py`；迁移 `0017`。

## 文件系统状态（同步 workspace）

默认为 `~/.coffer/sync/`（测试时可通过 `$COFFER_SYNC_ROOT` 覆盖），这是一个
git 工作树，其 `origin` 指向用户的远端。

```
manifest.json
knowledge/                      mirror of ~/.coffer/knowledge
memory/                         mirror of ~/.coffer/memory
resources/<kind>/<name>.yaml    one deterministic file per config resource
credentials/<ref>.enc           Fernet ciphertext, base64 text; never the key
```

### `manifest.json`

| Field             | Type   | Notes                                            |
| ----------------- | ------ | ------------------------------------------------ |
| `schema_version`  | int    | 当 workspace 布局发生不兼容变更时递增。           |
| `machine_id`      | String | 写入该 commit 的机器的稳定 id。                   |
| `coffer_version`  | String | 生产者版本，用于诊断。                            |
| `kinds`           | list   | 此 workspace 中包含的配置 kind。                  |

`schema_version` 会在导入时校验；若 workspace 比正在运行的构建版本更新，则会
快速失败（`SYNC_WORKSPACE_TOO_NEW`），与数据库的 `DB_SCHEMA_TOO_NEW` 规则相对应。

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
diff 频繁变动）。导入时按 `<kind>:<name>` 对资源执行 upsert；workspace 中不存在
但本地存在的资源会被删除（全量对账）。

### 凭据 blob（`credentials/<ref>.enc`）

`ref` 对应的 Fernet 密文，以 base64 文本编码，使 git 存储稳定的行内容。不含主密钥、
不含明文，除 ref（即文件名）外不含任何元数据。

## 仅本地、永不进入 workspace

`~/.coffer/logs/`、`coffer.db`、`daemon.json`、PID/端口文件，以及主密钥
文件 / keychain 条目。

## 派生索引（排除并重建）

由「事实源文件」重新生成的派生文件会被排除出镜像——它们逐机不同，若同步会
造成同路径的伪冲突。当前的例子是 memory store 的 `MEMORY.md` 索引：逐条
`<slug>.md` 事实文件照常同步，`MEMORY.md` 在导入后由合并后的事实文件重建。
排除集合见 `infrastructure/sync/workspace.DERIVED_INDEX_NAMES`。
